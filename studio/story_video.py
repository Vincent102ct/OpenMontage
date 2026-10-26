"""Local synthetic production jobs with separate render consent and immutable outputs."""
from __future__ import annotations

import contextlib
import copy
import json
import os
import re
import shutil
import threading
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

from lib import story_scene_plan as planner
from lib.scene_video import SceneVideoError, compile_video, fail, pcm_info, verify_narration, validate_compilation
from lib.story_visual_bible import fingerprint
from studio.review import safe_review_path, write_once
from studio.reviewed import _bytes, read_reviewed_story
from studio.scene_plan import read_scene_plan, retime_scene_plan
from studio.visual_bible import scene_planning_handoff
from tools.audio.local_narration import language_matches, narration_key, select_local_voice

OUTPUT = 'artifacts/story_video'
JOB_ID = re.compile(r'[a-f0-9]{16}\Z')
# Exact authored source digests, never a client supplied synthetic/approved flag.
PROOF_SOURCES = {'0206a77c2a81970c0c40b342f491f0f77b5b7181b99f8737b9d3c590185f5833',
                 '677663dcb9247ce442992ffabecc0cc1fd5b167b497a37c6832c307fadc6f064'}
_ACTIVE: set[tuple[str, str, str]] = set()
_LOCK = threading.Lock()


def _tool(name):
    if name == 'windows_sapi_tts':
        from tools.audio.windows_sapi_tts import WindowsSapiTTS
        return WindowsSapiTTS()
    if name == 'macos_say_tts':
        from tools.audio.macos_say_tts import MacosSayTTS
        return MacosSayTTS()
    if name == 'piper_tts':
        from tools.audio.piper_tts import PiperTTS
        return PiperTTS()
    if name == 'korva_tts':
        from tools.audio.korva_tts import KorvaTTS
        return KorvaTTS()
    if name == 'procedural_sfx':
        from tools.audio.procedural_sfx import ProceduralSFX
        return ProceduralSFX()
    if name == 'subtitle_gen':
        from tools.subtitle.subtitle_gen import SubtitleGen
        return SubtitleGen()
    if name == 'character_rig_renderer':
        from tools.character.character_animation import CharacterRigRenderer
        return CharacterRigRenderer()
    if name == 'video_compose':
        from tools.video.video_compose import VideoCompose
        return VideoCompose()
    fail('unsupported_provider', 'Only installed offline tools are eligible.')


def _current(store, project_id, binding=None):
    view = read_scene_plan(store, project_id)
    if not view.get('ready_for_next_stage'):
        fail('approval_required', 'Current approved story, Visual Bible and Scene Plan are required.')
    if view['package']['inputs']['reviewed_story']['source_sha256'] not in PROOF_SOURCES:
        fail('synthetic_only', 'P3.5 production is limited to exact registered synthetic fixtures. Real production is not authorized.')
    expected = planner.measurement_contract(view['package'], 'short', approved=view)['plan']
    if binding is not None and binding != expected:
        fail('stale_plan', 'Displayed scene-plan binding changed. Reload before production.')
    return view, expected


def readiness(store, project_id):
    view, binding = _current(store, project_id)
    language = view['package']['language']
    voices, blockers = [], []
    try:
        voices = [{'provider': 'windows_sapi', 'voice': v['name'], 'language': v['language_code'],
                   'speech_host': v['speech_host']} for v in _tool('windows_sapi_tts').list_voices()
                  if language_matches(v['language_code'], language)] if os.name == 'nt' else []
        selected = select_local_voice(_tool, language, piper_model=os.environ.get('OPENMONTAGE_PIPER_MODEL'))
        default = {'provider': selected['provider'], 'voice': selected['settings'].get('voice'), 'rate': None}
        if not any(v['provider'] == selected['provider'] and v['voice'] == default['voice'] for v in voices):
            voices.append({'provider': selected['provider'], 'voice': default['voice'], 'language': language})
    except (OSError, ValueError) as exc:
        blockers.append({'code': 'tts_unavailable', 'message': str(exc)});default = None
    for binary in ('ffmpeg', 'ffprobe', 'node', 'npx'):
        if not shutil.which(binary):
            blockers.append({'code': 'dependency_missing', 'message': f'{binary} is not executable in this process.'})
    return {'synthetic_only': True, 'plan': binding, 'language': language, 'voices': voices, 'default_voice': default,
            'blockers': blockers, 'ready': not blockers, 'render_authorized': False, 'publishing_enabled': False}


def _seal(value):
    return {**value, 'manifest_sha256': fingerprint(value)}


def _json(project, relative):
    path = safe_review_path(project, relative)
    try:
        value = json.loads(path.read_bytes())
        if value['manifest_sha256'] != fingerprint({k: v for k, v in value.items() if k != 'manifest_sha256'}):
            fail('artifact_invalid', 'Production manifest integrity failed.')
        return value
    except (OSError, ValueError, KeyError) as exc:
        if isinstance(exc, SceneVideoError):
            raise
        fail('artifact_invalid', f'Production artifact cannot be verified: {exc}')


def _narrate(store, project_id, request, progress):
    view, binding = _current(store, project_id, request['plan'])
    spec = request['voice']
    if (not isinstance(spec, dict) or set(spec) - {'provider', 'voice', 'rate'}
            or spec.get('provider') not in {'auto', 'windows_sapi', 'macos_say', 'piper', 'korva'}):
        fail('invalid_voice', 'Use an installed offline voice selection.')
    try:
        selection = select_local_voice(_tool, view['package']['language'], provider=spec['provider'],
                    voice=spec.get('voice'), rate=spec.get('rate'), piper_model=os.environ.get('OPENMONTAGE_PIPER_MODEL'))
    except ValueError as exc:
        fail('tts_unavailable', str(exc))
    project = store._project(project_id)
    results = {}
    tts = _tool(selection['tool'])
    session = getattr(tts, 'session', None)
    with session() if session else contextlib.nullcontext():
        for fmt in ('short', 'long'):
            contract = planner.measurement_contract(view['package'], fmt, approved=view)
            shots = {s['shot_id']: s for s in view['package']['formats'][fmt]['shots']}
            key = fingerprint({'plan': binding, 'format': fmt, 'voice': selection, 'units': contract['units']})
            relative = f'{OUTPUT}/audio/{key[:16]}'
            target = safe_review_path(project, relative)
            if target.exists():
                bundle = _json(project, relative + '/bundle.json')
                if bundle['cache_key'] != key or bundle['voice'] != selection:
                    fail('cache_invalid', 'Existing audio cache identity differs; nothing overwritten.')
                verify_narration(view, fmt, bundle, target)
            else:
                staging = safe_review_path(project, f'{OUTPUT}/audio/.tmp-{uuid.uuid4().hex[:12]}')
                staging.mkdir(parents=True, exist_ok=False)
                units = []
                for unit in contract['units']:
                    progress(f"Narrating {fmt} {unit['unit_id']}")
                    text = shots[unit['shot_id']]['source']['narration']['text']
                    output = staging / (unit['unit_id'] + '.wav')
                    result = tts.execute({**selection['settings'], 'text': text, 'output_path': str(output)})
                    if not result.success:
                        fail('synthesis_failed', str(result.error), unit_id=unit['unit_id'])
                    if not language_matches(result.data.get('language_code', ''), view['package']['language']):
                        fail('wrong_language', 'TTS result did not confirm the requested narration language.')
                    info = pcm_info(output)
                    if (result.data.get('audio_duration_seconds') is not None
                            and abs(result.data['audio_duration_seconds'] - info['duration_seconds']) > 1 / 24000):
                        fail('invalid_audio', 'Provider duration does not agree with actual PCM samples.')
                    units.append({**unit, **info, 'text': text, 'file': output.name,
                                  'voice_identity': narration_key(selection, text)})
                bundle = _seal({'artifact': 'scene_video_narration', 'schema_version': '1.0', 'plan': binding,
                    'format': fmt, 'voice': selection, 'cache_key': key, 'units': units,
                    'recorded_at': datetime.now(timezone.utc).isoformat(), 'audio_verified': True})
                verify_narration(view, fmt, bundle, staging)
                _current(store, project_id, binding)
                write_once(staging / 'bundle.json', _bytes(bundle))
                if target.exists():
                    fail('cache_conflict', 'Another writer published this audio cache; no output was overwritten.')
                os.rename(staging, target)
            measured = verify_narration(view, fmt, bundle, target)
            retimed = retime_scene_plan(store, project_id, fmt, measured)
            results[fmt] = {'cache': relative, 'manifest_sha256': bundle['manifest_sha256'],
                            'duration_seconds': retimed['retimed_plan']['duration_seconds'],
                            'narration_samples': sum(u['sample_count'] for u in bundle['units']),
                            'units': len(bundle['units'])}
    _current(store, project_id, binding)
    return _seal({'artifact': 'scene_video_narration_set', 'plan': binding, 'voice': selection, 'formats': results,
                  'audio_verified': True, 'render_authorized': False, 'publishing_enabled': False})


def _sound(video, folder):
    """Explicit synthetic cue review; no prose/keyword action analyzer."""
    # IDs are canonical fixture cues, not guesses from text labels.
    recipes = {'SND_KNOCKS': ('knock', .24, .55), 'SND_SOFT_KNOCKS': ('knock', .24, .3),
               'SND_LAMP_BUZZ': ('fridge_hum', .7, .12), 'SND_VI_BUZZ': ('fridge_hum', .7, .12),
               'SND_VI_KNOCK': ('knock', .24, .4)}
    cache = {}
    def cue(recipe, seconds, start, volume, ident):
        if seconds <= 0:
            return
        key = fingerprint([recipe, seconds]);path = folder / (key[:12] + '.wav')
        if key not in cache:
            result = _tool('procedural_sfx').execute({'recipe': recipe, 'duration_seconds': seconds,
                                                     'output_path': str(path)})
            if not result.success:
                fail('sfx_failed', str(result.error), cue=ident)
            cache[key] = path
        video['sfx'].append({'id': ident, 'path': str(path), 'start_seconds': start,
                             'duration_seconds': seconds, 'volume': volume})
    for i, shot in enumerate(video['metadata']['approved_format']['shots']):
        window = video['shots'][i];length = window['end_seconds'] - window['start_seconds']
        # Quiet ambience under narration, none inside intentional reaction/silence holds.
        if shot['kind'] == 'narrative':
            n = next(n for n in video['narration'] if n['id'] == shot['timing']['narration_unit_id'])
            cue('room_tone', n['end_seconds'] - window['start_seconds'], window['start_seconds'], .08, f'room-{i}')
    for i, spec in enumerate(video['metadata']['cue_specs']):
        source = spec['cue']
        if source['kind'] == 'silence':
            continue
        if source['id'] not in recipes:
            fail('sound_capability', 'No reviewed sound representation for this required cue.', cue_id=source['id'])
        recipe, length, gain = recipes[source['id']]
        count = 3 if recipe == 'knock' else 1
        for j in range(count):
            start = spec['start_seconds'] + j * .34
            if start + length > spec['end_seconds']:
                fail('sound_timing', 'Required sound cue cannot fit its approved shot.')
            cue(recipe, length, start, gain, f'cue-{i}-{j}')


def _render(store, project_id, request, directory, progress):
    view, binding = _current(store, project_id, request['plan'])
    from studio.scene_staging import approved_staging
    staging=approved_staging(store,project_id,request.get('staging'))
    prior = job(store, project_id, request['narration_job'])
    if (prior['state'] != 'complete' or prior['kind'] != 'narration'
            or prior['result']['manifest_sha256'] != request['narration_sha256'] or prior['plan'] != binding):
        fail('stale_audio', 'Use the exact current verified narration job and manifest.')
    if staging['manifest']['narration']['manifest_sha256']!=prior['result']['manifest_sha256']:
        fail('stale_audio','Reviewed staging is bound to a different measured narration set.')
    visual = scene_planning_handoff(store, project_id)
    from tools.story.scene_video_qa import inspect_render
    results = {}
    for fmt in ('short', 'long'):
        _current(store, project_id, binding)
        progress(f'Compiling {fmt}')
        ref = prior['result']['formats'][fmt]
        folder = safe_review_path(store.root / project_id, ref['cache'])
        bundle = _json(store.root / project_id, ref['cache'] + '/bundle.json')
        if bundle['manifest_sha256'] != ref['manifest_sha256']:
            fail('cache_invalid', 'Narration bundle hash changed.')
        measured = verify_narration(view, fmt, bundle, folder)
        timed = retime_scene_plan(store, project_id, fmt, measured)['retimed_plan']
        output = directory / fmt;output.mkdir()
        source = output / 'narration.txt'
        write_once(source, '\n\n'.join(u['text'] for u in bundle['units']).encode('utf-8'))
        video, timeline = compile_video(view, visual, fmt, bundle, folder, timed, source, staging)
        _sound(video, output)
        validate_compilation(view, fmt, timed, video, timeline, staging)
        for name, data in (('story_video.json', video), ('action_timeline.json', timeline), ('retimed.json', timed)):
            write_once(output / name, _bytes(data))
        # Existing subtitle generator, per-unit retimed windows; exact raw/renderer mapping is in the bundle.
        subtitle = output / 'subtitles.srt'
        sub = _tool('subtitle_gen').execute({'segments': [{'text': n['text'], 'start': n['start_seconds'], 'end': n['end_seconds']}
                 for n in video['narration']], 'format': 'srt', 'output_path': str(subtitle),
                 'max_words_per_cue': 1, 'max_chars_per_line': 1})
        if not sub.success:
            fail('subtitle_failed', str(sub.error))
        rendered = _tool('character_rig_renderer').execute({'story_video': video, 'action_timeline': timeline,
                    'workspace_path': str(output / 'composition'), 'concurrency': 2, 'scale': request['scale']})
        if not rendered.success:
            fail('compile_failed', str(rendered.error))
        write_once(output / 'edit_decisions.json', _bytes(rendered.data['edit_decisions']))
        progress(f'Rendering full {fmt}: {len(video["shots"])} shots')
        pending = output / 'pending.mp4'
        result = _tool('video_compose').execute({'operation': 'render', 'edit_decisions': rendered.data['edit_decisions'],
                  'asset_manifest': rendered.data['asset_manifest'], 'output_path': str(pending)})
        if not result.success:
            fail('render_failed', str(result.error))
        progress(f'Inspecting full {fmt} MP4')
        qa = inspect_render(pending, video, timeline, subtitle, output / 'qa', scale=request['scale'])
        write_once(output / 'qa.json', _bytes(qa))
        if not qa['passed']:
            fail('qa_failed', 'Rendered video failed technical QA.', issues=qa['issues'])
        _current(store, project_id, binding)
        approved_staging(store,project_id,request['staging'])
        final = output / 'full-story.mp4';os.rename(pending, final)
        from tools.audio.local_narration import file_hash
        results[fmt] = {'file': f'{fmt}/full-story.mp4', 'sha256': file_hash(final), 'qa_file': f'{fmt}/qa.json',
                        'qa': qa, 'draft': request['scale'] != 1, 'scale': request['scale']}
    return _seal({'artifact': 'scene_video_render', 'plan': binding, 'formats': results, 'synthetic_only': True,
                  'staging':staging['reference'],'render_consent': True, 'publishing_enabled': False, 'artistic_audio_acceptance': 'pending'})


def start_job(store, project_id, kind, payload):
    expected = {'plan', 'voice'} if kind == 'narration' else {'plan', 'narration_job', 'narration_sha256', 'render_consent', 'scale', 'staging'}
    if kind not in ('narration', 'render') or not isinstance(payload, dict) or set(payload) != expected:
        fail('invalid_request', 'Use the exact displayed production request fields.')
    view, binding = _current(store, project_id, payload['plan'])
    if kind == 'render' and (payload['render_consent'] is not True or type(payload['scale']) not in (int, float)
                             or payload['scale'] not in (.5, 1)):
        fail('render_consent_required', 'Explicit synthetic render consent and draft/full scale are required.')
    if kind=='render':
        from studio.scene_staging import approved_staging
        approved_staging(store,project_id,payload['staging'])
    ident = uuid.uuid4().hex[:16]
    project = store._project(project_id)
    directory = safe_review_path(project, f'{OUTPUT}/jobs/{ident}')
    key = (str(store.root.resolve()), project_id)
    with _LOCK:
        if any(item[:2] == key for item in _ACTIVE):
            fail('production_busy', 'Another local production job is active for this project.')
        _ACTIVE.add((*key, ident))
    try:
        directory.mkdir(parents=True, exist_ok=False)
        write_once(directory / 'request.json', _bytes(_seal({'kind': kind, 'plan': binding, 'payload': payload})))
    except Exception:
        with _LOCK:_ACTIVE.discard((*key, ident))
        raise
    def event(state, message):
        with (directory / 'events.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps({'state': state, 'message': message, 'at': datetime.now(timezone.utc).isoformat()}) + '\n')
    def work():
        event('running', 'Local synthetic production started by explicit request.')
        try:
            result = (_narrate(store, project_id, payload, lambda m:event('running', m)) if kind == 'narration'
                      else _render(store, project_id, payload, directory, lambda m:event('running', m)))
            _current(store, project_id, binding)
            write_once(directory / 'result.json', _bytes(result))
            event('complete', 'Technical output ready; artistic/audio acceptance pending.')
        except Exception as exc:
            event('failed', str(exc))
            write_once(directory / 'failure-trace.txt', traceback.format_exc().encode('utf-8'))
            write_once(directory / 'failure.json', _bytes({'code': getattr(exc, 'code', 'production_failed'),
                      'message': str(exc), 'details': getattr(exc, 'details', [])}))
        finally:
            with _LOCK:_ACTIVE.discard((*key, ident))
    event('queued', 'Requested; no Scene Plan approval was treated as render consent.')
    threading.Thread(target=work, name=f'scene-video-{ident}', daemon=True).start()
    return {'job_id': ident, 'kind': kind, 'state': 'queued', 'plan': binding}


def job(store, project_id, ident):
    if not isinstance(ident, str) or not JOB_ID.fullmatch(ident):
        fail('invalid_job', 'Invalid local production job ID.')
    project = store._project(project_id)
    folder = safe_review_path(project, f'{OUTPUT}/jobs/{ident}')
    request = _json(project, f'{OUTPUT}/jobs/{ident}/request.json')
    try:
        events = [json.loads(line) for line in (folder / 'events.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
        state = events[-1]['state']
        if state in ('queued', 'running') and (str(store.root.resolve()), project_id, ident) not in _ACTIVE:
            state = 'interrupted'
        result = _json(project, f'{OUTPUT}/jobs/{ident}/result.json') if state == 'complete' else None
        error = json.loads((folder / 'failure.json').read_bytes()) if state == 'failed' else None
        try:_current(store, project_id, request['plan']);current = True
        except (SceneVideoError, planner.ScenePlanError):current = False
        if current and result and request['kind']=='render' and result.get('staging'):
            from studio.scene_staging import approved_staging
            from lib.scene_staging import StagingError
            try:approved_staging(store,project_id,result['staging'])
            except (StagingError,SceneVideoError,planner.ScenePlanError):current=False
        return {'job_id': ident, 'kind': request['kind'], 'state': state, 'plan': request['plan'],
                'created_at': events[0].get('at', ''),
                'message': events[-1]['message'], 'result': result, 'error': error, 'is_current': current,
                'publishing_enabled': False}
    except (OSError, ValueError, KeyError) as exc:
        if isinstance(exc, SceneVideoError):raise
        fail('job_invalid', f'Local production job cannot be read: {exc}')


def status(store, project_id):
    try:
        view, binding = _current(store, project_id)
        eligible, blockers = True, []
    except (SceneVideoError, planner.ScenePlanError) as exc:
        eligible, binding = False, None
        blockers = [{'code': getattr(exc, 'code', 'not_ready'), 'message': str(exc)}]
    project = store._project(project_id)
    folder = safe_review_path(project, OUTPUT + '/jobs')
    jobs = [job(store, project_id, p.name) for p in folder.iterdir()
            if JOB_ID.fullmatch(p.name) and p.is_dir() and (p/'request.json').is_file()
            and (p/'events.jsonl').is_file()] if folder.is_dir() else []
    jobs.sort(key=lambda j: (j['created_at'], j['job_id']))
    return {'eligible': eligible, 'plan': binding, 'synthetic_only': True, 'blockers': blockers,
            'jobs': jobs, 'production_started': bool(jobs), 'publishing_enabled': False}


def media_file(store, project_id, ident, fmt, kind):
    if fmt not in ('short', 'long') or kind not in ('video', 'qa', 'subtitles', 'contact'):
        fail('invalid_media', 'Unknown production output.')
    value = job(store, project_id, ident)
    if value['state'] != 'complete' or value['kind'] != 'render' or not value['is_current']:
        fail('not_ready', 'Only current, complete and QA-verified renders can be viewed.')
    row = value['result']['formats'][fmt]
    relative = {'video': row['file'], 'qa': row['qa_file'], 'subtitles': fmt + '/subtitles.srt',
                'contact': fmt + '/qa/contact-sheet.jpg'}[kind]
    folder = safe_review_path(store.root / project_id, f'{OUTPUT}/jobs/{ident}')
    path = safe_review_path(folder, relative)
    from tools.audio.local_narration import file_hash
    try:
        if kind == 'video' and file_hash(path) != row['sha256']:
            fail('artifact_invalid', 'Rendered MP4 content hash changed.')
    except OSError:
        fail('artifact_invalid', 'Published output is missing or inaccessible.')
    return path
