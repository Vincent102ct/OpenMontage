"""P3.5 executable bridge over P3.4 approvals, not an alternative story planner."""
from __future__ import annotations

import copy
import hashlib
import math
import wave
from array import array
from pathlib import Path

from lib import story_scene_plan as planner
from lib.story_visual_bible import fingerprint
from lib.scene_staging import apply_review
from tools.audio.local_narration import file_hash, language_matches, narration_key
from tools.audio.local_wav import wav_duration
from tools.character import horror_assets as assets
from tools.character.horror_acting import ActorBuilder
from tools.character.story_video import validate_story_video


class SceneVideoError(ValueError):
    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code, self.details = code, details or []


def fail(code, message, **details):
    raise SceneVideoError(code, message, [details] if details else [])


def pcm_info(path: Path) -> dict:
    """Real PCM samples, not a container duration or word-count estimate."""
    try:
        duration = wav_duration(path)
        with wave.open(str(path), 'rb') as f:
            frames, rate = f.getnframes(), f.getframerate()
            values = array('h', f.readframes(frames))
        peak = max(abs(v) for v in values) / 32768
        rms = math.sqrt(sum(float(v) ** 2 for v in values) / len(values)) / 32768
        clipped = sum(abs(v) >= 32767 for v in values) / len(values)
        if rms < 0.001 or clipped > 0.0001:
            fail('invalid_audio', 'Silent/near-silent or clipped narration is not accepted.', path=path.name)
        return {'sample_count': frames, 'sample_rate_hz': rate, 'duration_seconds': duration,
                'audio_sha256': file_hash(path), 'peak': peak, 'rms_dbfs': 20 * math.log10(rms),
                'clipped_sample_fraction': clipped}
    except (OSError, EOFError, wave.Error, ValueError) as exc:
        if isinstance(exc, SceneVideoError):
            raise
        fail('invalid_audio', f'Invalid PCM narration: {exc}', path=path.name)


def verify_narration(view: dict, fmt: str, bundle: dict, folder: Path) -> dict:
    contract = planner.measurement_contract(view['package'], fmt, approved=view)
    try:
        if (bundle['plan'] != contract['plan'] or bundle['format'] != fmt
                or bundle['manifest_sha256'] != fingerprint({k: v for k, v in bundle.items() if k != 'manifest_sha256'})
                or not language_matches(bundle['voice']['settings']['language_code'], view['package']['language'])
                or [{k: u[k] for k in ('unit_id', 'shot_id', 'text_sha256')} for u in bundle['units']] != contract['units']):
            fail('stale_audio', 'Narration binding, voice language, unit order or manifest differs.')
        expected_text = {s['timing']['narration_unit_id']: s['source']['narration']['text']
                         for s in view['package']['formats'][fmt]['shots'] if s['kind'] == 'narrative'}
        for u in bundle['units']:
            if (u['text'] != expected_text[u['unit_id']] or u['file'] != u['unit_id'] + '.wav'
                    or u['voice_identity'] != narration_key(bundle['voice'], u['text'])):
                fail('invalid_audio', 'Narration text or safe filename differs.')
            path = folder / u['file']
            if path.is_symlink() or not path.resolve().is_relative_to(folder.resolve()):
                fail('invalid_audio', 'Narration path escapes the bound cache.')
            actual = pcm_info(path)
            if any(actual[k] != u[k] for k in actual):
                fail('invalid_audio', 'Cached WAV samples, hash or measured duration changed.', unit_id=u['unit_id'])
        measurement = {'artifact': 'scene_plan_measurements', 'schema_version': '1.0', 'plan': bundle['plan'],
                       'format': fmt, 'units': [{k: u[k] for k in ('unit_id', 'shot_id', 'text_sha256',
                           'duration_seconds', 'audio_sha256', 'sample_rate_hz')} for u in bundle['units']],
                       'provenance': {'kind': 'measured_audio', 'producer': 'P3.5 verified local PCM samples',
                                      'recorded_at': bundle['recorded_at']}}
        measurement['manifest_sha256'] = fingerprint(measurement)
        planner.retime(view['package'], fmt, measurement, approved=view)
        return measurement
    except (KeyError, TypeError) as exc:
        fail('invalid_audio', f'Incomplete narration manifest: {exc}')


def asset_binding(plan: dict, visual: dict) -> dict:
    """Adapt only pinned structured Visual Bible data to the existing P3.2A binding."""
    if (visual['version'] != plan['inputs']['visual_bible']['version']
            or visual['package_sha256'] != plan['inputs']['visual_bible']['package_sha256']
            or fingerprint(visual) != plan['inputs']['visual_bible']['handoff_sha256']):
        fail('stale_visual', 'Visual Bible handoff no longer matches the approved Scene Plan.')
    for pin in plan['inputs']['assets'] + plan['inputs']['acting_presets']:
        if assets.content_hash(assets.get(pin['kind'], pin['id'], pin['revision'])) != pin['sha256']:
            fail('stale_asset', 'Pinned asset revision or bytes changed.', asset=pin['id'])
    cast = {c['canonical_id']: {'character': c['asset']['id'], 'revision': c['asset']['revision']}
            for c in visual['characters'] if c['asset'] and c['asset']['kind'] == 'character'}
    locations = {}
    for loc in visual['locations']:
        lighting = loc['lighting']
        entry = {'environment': loc['environment']['id'], 'revision': loc['environment']['revision'],
                 'lighting': {'id': lighting['id'], 'revision': lighting['revision']}}
        flickering = [lamp['id'] for lamp in loc['geometry']['lamps'] if lamp['driver'] == 'flicker']
        if flickering:
            if len(flickering) != 1:
                fail('lighting_capability', 'Renderer requires one pinned flickering lamp.')
            entry['lighting']['flicker_lamp'] = flickering[0]
        if loc.get('presence'):
            silhouette = next(c for c in visual['characters'] if c['canonical_id'] == loc['presence']['character_id'])
            entry['presence'] = {'anchor': loc['presence']['anchor'], 'silhouette': silhouette['asset']['id'],
                                 'revision': silhouette['asset']['revision']}
        locations[loc['canonical_id']] = entry
    binding = {'story_id': plan['project_id'], 'library': visual['library']['id'],
               'library_version': visual['library']['version'], 'cast': cast, 'locations': locations}
    assets.validate_binding(binding)
    return binding


def _actor(cast, motion, window, length, look):
    b = ActorBuilder(cast['character_id'], look, cast['start_x'], facing=cast['facing'],
                     rest_posture=assets.get('character', cast['asset']['id'], cast['asset']['revision'])['rest_posture'])
    times = {(m['character_id'], m['step_index']): m for m in window['motion']}
    for i, original in enumerate(motion['steps']):
        m, p = times[(cast['character_id'], i)], original['params']
        t0, t1 = m['start_frame'] / 30, m['end_frame'] / 30
        if t0 > b.t:
            b.hold(t0)
        preset = original['preset']
        if preset == 'cautious_walk':
            b.cautious_walk(p['to_x'], t0, t1)
        elif preset == 'guarded_reach':
            b.guarded_reach(p['target'], t0, t1, hand=p['hand'])
        elif preset == 'listening_freeze':
            b.listening_freeze(t0, t1, gaze=tuple(p['gaze']), tilt=p['tilt'])
        elif preset == 'startled_reaction':
            b.startled_reaction(t0, toward=p['toward'], hold=p['hold'], strength=p['strength'])
            if b.t > t1 + 1e-8:
                fail('unsupported_motion', 'Preset cannot fit its verified time interval.')
            b.hold(t1)
        elif preset == 'hold':
            b.hold(t1)
        else:
            fail('unsupported_motion', 'No executable preset for selected action.', preset=preset)
    actor = b.build(length)
    # ActorBuilder stores seconds at four decimals. Retimed 30fps boundaries
    # are rational values; retain those exact boundaries in the adapter.
    for track in ('root', 'left_hand', 'right_hand', 'left_foot', 'right_foot', 'posture', 'face'):
        if abs(actor[track][-1][0] - length) <= .000051:
            actor[track][-1][0] = length
    if not cast['visible']:
        actor['opacity'] = [[0, 0], [length, 0]]
    return actor


def compile_video(view: dict, visual: dict, fmt: str, bundle: dict, audio_dir: Path,
                  derivative: dict, source_path: Path, staging=None) -> tuple[dict, dict]:
    """Keep frozen source/context; only structured presets become renderer tracks."""
    plan = view['package']
    measurement = verify_narration(view, fmt, bundle, audio_dir)
    if derivative != planner.retime(plan, fmt, measurement, approved=view):
        fail('stale_timing', 'Retimed derivative is not the exact bound measured result.')
    original_ir = planner.action_timeline(plan, fmt, derivative, approved=view)
    binding = asset_binding(plan, visual)
    resolved = assets.resolve_binding(binding)
    fp, rows = plan['formats'][fmt], derivative['shots']
    text = '\n\n'.join(u['text'] for u in bundle['units'])
    # The raw derivative retains exact approved units. The legacy renderer's paragraph
    # loader normalizes whitespace; expose that distinct representation explicitly.
    if source_path.read_text(encoding='utf-8') != text:
        fail('source_representation', 'Immutable format narration text differs from approved units.')
    units = {u['unit_id']: u for u in bundle['units']}
    shots, narration, links, cue_specs, presence, spill, flicker = [], [], [], [], [], [], []
    for source, window, scene in zip(fp['shots'], rows, original_ir['scenes']):
        length = window['frame_count'] / 30
        start, end = window['start_frame'] / 30, window['end_frame'] / 30
        st = source['staging']; lid = source['source']['location_id']
        if any(i['status'] == 'requires_new_capability' for i in source['capability']['items']):
            fail('unsupported_motion', 'Unavailable capability remains in selected staging.', shot_id=source['shot_id'])
        if source['capability']['status'] == 'editorial_review' and not source['editorial_acknowledged']:
            fail('editorial_review', 'Editorial choice was not acknowledged.', shot_id=source['shot_id'])
        motions = {a['character_id']: a for a in source['motion_plan']['actors']}
        actors = [_actor(c, motions[c['character_id']], window, length, resolved['cast'][c['character_id']]) for c in st['cast']]
        door_states = [p['state'] for p in source['continuity']['before']['props'].values()
                       if p['location_id'] == lid and p['state'] in ('open', 'closed')]
        opened = int('open' in door_states)
        shots.append({'id': source['shot_id'], 'start_seconds': start, 'end_seconds': end, 'view': 'world',
                      'location': lid, 'weather': None, 'camera': copy.deepcopy(window['camera_keys']),
                      'light': [[0, .12, 0], [length, .12, 0]], 'door': [[0, opened], [length, opened]],
                      'actors': actors, 'items': [], 'vehicles': []})
        # Distinct one-frame keys across cuts avoid interpolating a reveal into earlier shots.
        a, z = start, max(start, end - 1 / 30)
        for track, value in ((presence, [0.8 if st['presence'] else 0, 0]), (spill, [.55])):
            track.extend([[a, *value], [z, *value]])
        local_flicker = assets.flicker_track(length, st['lighting']['flicker_bursts_seconds'])
        if st['lighting']['state'] != 'flicker_bursts':
            local_flicker = [[0, 1], [length, 1]]
        flicker.extend([[start + k[0], k[1]] for k in local_flicker if k[0] < length])
        if source['kind'] == 'narrative':
            u, n = units[source['timing']['narration_unit_id']], window['narration']
            n0 = n['start_frame'] / 30
            narration.append({'id': u['unit_id'], 'path': str((audio_dir / u['file']).resolve()),
                              'text': ' '.join(u['text'].split()),
                              'start_seconds': n0, 'end_seconds': n0 + u['duration_seconds']})
            for i in n['action_indices']:
                links.append({'narration_id': u['unit_id'], 'scene_id': source['shot_id'], 'action_index': i})
        for cue in st['sound']['cues']:
            cue_specs.append({'shot_id': source['shot_id'], 'start_seconds': start, 'end_seconds': end,
                              'narration_end': narration[-1]['end_seconds'] if source['kind'] == 'narrative' else start,
                              'cue': copy.deepcopy(cue)})
    duration = derivative['duration_seconds']
    for track in (presence, spill, flicker):
        track.append([duration, *track[-1][1:]])
    video = {'duration_seconds': duration, 'fps': 30, 'title': plan['title'], 'character_skin': 'cartoon_horror',
             'viewport': fp['viewport'], 'audio_mode': 'narrated', 'source_path': str(source_path.resolve()),
             'art_direction': 'Approved cinematic 2D cartoon supernatural horror; pinned cast and locations, restrained reveals.',
             'asset_binding': binding, 'locations': resolved['locations'], 'shots': shots,
             'narration': narration, 'sfx': [], 'horror': {'presence': presence, 'spill': spill, 'flicker': flicker},
             'metadata': {'stage': 'p3.5', 'format':fmt, 'plan': bundle['plan'], 'narration_manifest_sha256': bundle['manifest_sha256'],
                          'source_derivative_sha256': hashlib.sha256(text.encode()).hexdigest(),
                          'renderer_text_rule': 'Whitespace-only paragraph representation; raw TTS units and hashes remain authoritative.',
                          'approved_format': copy.deepcopy(fp), 'cue_specs': cue_specs,
                          'source_ir_sha256': fingerprint(original_ir)}}
    timeline = copy.deepcopy(original_ir)
    timeline['metadata']['narration_links'] = links
    timeline['metadata']['source_ir_sha256'] = fingerprint(original_ir)
    timeline['metadata']['renderable'] = True
    if staging:
        apply_review(video,timeline,staging['package'],staging['reference'])
    validate_compilation(view, fmt, derivative, video, timeline, staging)
    return video, timeline


def validate_compilation(view, fmt, derivative, video, timeline, staging=None):
    expected = planner.action_timeline(view['package'], fmt, derivative, approved=view)
    expected_links = [{'narration_id': w['narration']['unit_id'], 'scene_id': w['shot_id'], 'action_index': i}
                      for w in derivative['shots'] if w.get('narration')
                      for i in w['narration']['action_indices']]
    exact_timeline = copy.deepcopy(expected)
    exact_timeline['metadata'].update(renderable=True, source_ir_sha256=fingerprint(expected), narration_links=expected_links)
    resolved = assets.resolve_binding(video['asset_binding'])
    execution=copy.deepcopy(video)
    execution.pop('visual_state',None)
    for source,window,shot in zip(view['package']['formats'][fmt]['shots'],derivative['shots'],execution['shots']):
        motions={a['character_id']:a for a in source['motion_plan']['actors']}
        shot['camera']=copy.deepcopy(window['camera_keys'])
        shot['actors']=[_actor(c,motions[c['character_id']],window,window['frame_count']/30,
                              resolved['cast'][c['character_id']]) for c in source['staging']['cast']]
    if staging:
        if (not staging.get('approval') or not staging.get('ready_for_render')
                or staging['package']['plan']!=derivative['plan']
                or staging['package']['timing_sha256'][fmt]!=fingerprint(derivative)):
            fail('staging_review_required','Current separately approved visual staging and exact timing are required.')
        apply_review(execution,exact_timeline,staging['package'],staging['reference'])
    if video.get('visual_state')!=execution.get('visual_state'):
        fail('compilation_invalid','Visual runtime state differs from the approved staging extension.')
    if ([s['id'] for s in video['shots']] != [s['shot_id'] for s in view['package']['formats'][fmt]['shots']]
            or timeline != exact_timeline
            or video['metadata']['approved_format'] != view['package']['formats'][fmt]
            or video['metadata']['plan'] != derivative['plan'] or video['metadata'].get('format')!=fmt
            or video['duration_seconds'] != derivative['duration_seconds']):
        fail('compilation_invalid', 'Compiled source, shots, order, plan or duration differs.')
    for shot, row, compiled in zip(video['shots'], derivative['shots'], execution['shots']):
        if (shot['start_seconds'], shot['end_seconds'], shot['camera']) != (
                row['start_frame'] / 30, row['end_frame'] / 30, compiled['camera']):
            fail('compilation_invalid', 'Shot timing/camera differs from verified retiming.')
        if shot['actors']!=compiled['actors']:
            fail('compilation_invalid','Executable tracks differ from the approved plan/staging version.')
    originals = [s for s in view['package']['formats'][fmt]['shots'] if s['kind'] == 'narrative']
    if [n['id'] for n in video['narration']] != [s['timing']['narration_unit_id'] for s in originals]:
        fail('compilation_invalid', 'Missing, duplicated or reordered narration units.')
    measured = {u['unit_id']: u for u in derivative['measurement_set']['units']}
    windows = {w['shot_id']: w for w in derivative['shots']}
    for source, n in zip(originals, video['narration']):
        value = measured[n['id']]
        start = windows[source['shot_id']]['narration']['start_frame'] / 30
        if (n['text'] != ' '.join(source['source']['narration']['text'].split())
                or n['start_seconds'] != start or n['end_seconds'] != start + value['duration_seconds']
                or file_hash(Path(n['path'])) != value['audio_sha256']):
            fail('compilation_invalid', 'Narration text, actual WAV, unit binding or window differs.')
    if video['locations'] != resolved['locations']:
        fail('compilation_invalid', 'Resolved environment geometry or pinned prop anchors changed.')
    if hashlib.sha256(Path(video['source_path']).read_bytes()).hexdigest() != video['metadata']['source_derivative_sha256']:
        fail('compilation_invalid', 'Immutable format narration source changed.')
    try:
        validate_story_video(video, timeline)
    except ValueError as exc:
        fail('compilation_invalid', str(exc))
