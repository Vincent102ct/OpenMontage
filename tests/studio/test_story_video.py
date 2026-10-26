"""P3.5 failure injection. Test tones are never production narration evidence."""
import copy
import hashlib
import json
import math
import shutil
import struct
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lib import story_scene_plan as planner
from lib.scene_video import (SceneVideoError, asset_binding, compile_video, pcm_info,
                             validate_compilation, verify_narration)
from lib.story_visual_bible import fingerprint
from tools.audio.local_narration import narration_key
from studio import story_video as service
from studio.catalog import ApprovedPackages
from studio.scene_plan import approve_scene_plan, prepare_scene_plan, read_scene_plan
from studio.store import ProductionStore
from studio.visual_bible import scene_planning_handoff
from tests.studio.scene_plan_fixture import prepare, resolved_choices, STORY
from tests.studio.story_video_fixture import VI_STORY, prepare_vi

ROOT = Path(__file__).resolve().parents[2]


def seal(value):
    value['manifest_sha256'] = fingerprint({k:v for k,v in value.items() if k != 'manifest_sha256'})
    return value


@pytest.fixture(scope='module')
def proof(tmp_path_factory):
    folder = tmp_path_factory.mktemp('p35')
    store = ProductionStore(folder / 'p', ApprovedPackages(ROOT))
    prepare(store)
    v = prepare_scene_plan(store, 'fx', {})
    v = prepare_scene_plan(store, 'fx', {'base_version':v['version'], 'package_sha256':v['package_sha256'],
        'manifest_sha256':v['manifest_sha256'], 'choices':resolved_choices(v)})
    v = approve_scene_plan(store, 'fx', v['version'], v['package_sha256'], v['manifest_sha256'])
    before = {str(p.relative_to(store.root)):hashlib.sha256(p.read_bytes()).hexdigest()
              for p in store.root.rglob('*') if p.is_file()}
    visual = scene_planning_handoff(store, 'fx')
    results = {}
    voice={'provider':'windows_sapi','tool':'windows_sapi_tts','version':'test',
           'settings':{'voice':'Test tone, not TTS','language_code':'en-US','rate':-1},'model_identity':'test-tone-only'}
    for fmt in ('short','long'):
        audio = folder / fmt; audio.mkdir()
        contract = planner.measurement_contract(v['package'],fmt,approved=v)
        texts = {s['timing']['narration_unit_id']:s['source']['narration']['text']
                 for s in v['package']['formats'][fmt]['shots'] if s['kind']=='narrative'}
        units = []
        for u in contract['units']:
            path=audio/(u['unit_id']+'.wav')
            with wave.open(str(path),'wb') as wav:
                wav.setparams((1,2,24000,0,'NONE','not compressed'))
                wav.writeframes(b''.join(struct.pack('<h',int(3000*math.sin(i*2*math.pi*220/24000))) for i in range(48000)))
            units.append({**u,**pcm_info(path),'file':path.name,'text':texts[u['unit_id']], 'voice_identity':narration_key(voice,texts[u['unit_id']])})
        bundle=seal({'plan':contract['plan'],'format':fmt,'voice':voice,
                     'units':units,'recorded_at':'2026-10-26T00:00:00Z'})
        measurement=verify_narration(v,fmt,bundle,audio)
        timed=planner.retime(v['package'],fmt,measurement,approved=v)
        source=audio/'narration.txt';source.write_bytes('\n\n'.join(u['text'] for u in units).encode('utf-8'))
        video,timeline=compile_video(v,visual,fmt,bundle,audio,timed,source)
        results[fmt]=(bundle,audio,timed,video,timeline)
    yield store,v,visual,results
    after={str(p.relative_to(store.root)):hashlib.sha256(p.read_bytes()).hexdigest()
           for p in store.root.rglob('*') if p.is_file()}
    assert before==after, 'P3.5 verification modified frozen inputs'


@pytest.mark.parametrize('fmt',['short','long'])
def test_complete_lossless_compilation(proof,fmt):
    _,v,_,results=proof
    bundle,audio,timed,video,timeline=results[fmt]
    validate_compilation(v,fmt,timed,video,timeline)
    assert [s['id'] for s in video['shots']]==[s['shot_id'] for s in v['package']['formats'][fmt]['shots']]
    assert len(video['shots'])==(13 if fmt=='short' else 20)
    assert timeline['metadata']['renderable'] is True
    assert planner.action_timeline(v['package'],fmt,timed,approved=v)['metadata']['renderable'] is False
    assert video['shots'][-1]['end_seconds']==timed['duration_seconds']
    assert video['asset_binding']['locations']['LOC_HALL']['lighting']['flicker_lamp']=='lamp_mid'


@pytest.mark.parametrize('fault',['language','plan_version','plan_hash','missing_unit','duplicate_unit','reordered_unit',
    'text','text_hash','audio_hash','sample_count','sample_rate','duration','manifest'])
def test_reject_measurement_and_cache_drift(proof,fault):
    _,v,_,results=proof
    b,a,*_=results['long'];b=copy.deepcopy(b)
    if fault=='language':b['voice']['settings']['language_code']='vi-VN'
    elif fault=='plan_version':b['plan']['version']='v999'
    elif fault=='plan_hash':b['plan']['package_sha256']='0'*64
    elif fault=='missing_unit':b['units'].pop()
    elif fault=='duplicate_unit':b['units'][1]=copy.deepcopy(b['units'][0])
    elif fault=='reordered_unit':b['units'][0],b['units'][1]=b['units'][1],b['units'][0]
    elif fault in ('text','text_hash','audio_hash'):b['units'][0][{'text':'text','text_hash':'text_sha256','audio_hash':'audio_sha256'}[fault]]='tampered'
    elif fault in ('sample_count','sample_rate','duration'):b['units'][0][{'sample_count':'sample_count','sample_rate':'sample_rate_hz','duration':'duration_seconds'}[fault]]+=1
    if fault!='manifest':seal(b)
    else:b['manifest_sha256']='f'*64
    with pytest.raises(SceneVideoError):verify_narration(v,'long',b,a)


@pytest.mark.parametrize('fault',['missing','corrupt','truncated','silence','clipping'])
def test_reject_bad_pcm(proof,tmp_path,fault):
    _,v,_,results=proof
    b,a,*_=results['short'];shutil.copytree(a,tmp_path/'a');a=tmp_path/'a';p=a/b['units'][0]['file']
    if fault=='missing':p.unlink()
    elif fault=='corrupt':p.write_bytes(b'not WAV')
    elif fault=='truncated':p.write_bytes(p.read_bytes()[:-2])
    else:
        with wave.open(str(p),'wb') as w:
            w.setparams((1,2,24000,0,'NONE','not compressed'));w.writeframes(struct.pack('<h',0 if fault=='silence' else 32767)*48000)
    with pytest.raises(SceneVideoError):verify_narration(v,'short',b,a)


@pytest.mark.parametrize('fault',['missing_shot','duplicate_shot','reorder','missing_final','cut','final_truncation',
    'unsupported_motion','camera','anchor','environment','source','timeline_context'])
def test_reject_compiled_loss(proof,fault):
    _,v,_,results=proof
    _,_,t,video,timeline=results['long'];video,timeline=copy.deepcopy((video,timeline))
    if fault=='missing_shot':video['shots'].pop(0)
    elif fault=='duplicate_shot':video['shots'][1]=copy.deepcopy(video['shots'][0])
    elif fault=='reorder':video['shots'][0],video['shots'][1]=video['shots'][1],video['shots'][0]
    elif fault=='missing_final':video['shots'].pop()
    elif fault=='cut':video['narration'][0]['end_seconds']=video['shots'][1]['end_seconds']+.5
    elif fault=='final_truncation':video['duration_seconds']-=1
    elif fault=='unsupported_motion':video['shots'][0]['actors'][0]['root'][0][1]+=1
    elif fault=='camera':video['shots'][0]['camera'][0][1]+=1
    elif fault=='anchor':video['locations']['LOC_ROOM']['door']['x']+=1
    elif fault=='environment':video['asset_binding']['locations']['LOC_ROOM']['revision']=999
    elif fault=='source':video['metadata']['approved_format']['shots'][0]['source']['event_ids']=[]
    elif fault=='timeline_context':timeline['metadata']['approved_format']['shots'][0]['source']['event_ids']=[]
    with pytest.raises((SceneVideoError,ValueError)):validate_compilation(v,'long',t,video,timeline)


@pytest.mark.parametrize('fault',['visual','asset'])
def test_stale_visual_and_asset(proof,fault):
    _,v,visual,_=proof;v,visual=copy.deepcopy((v,visual))
    if fault=='visual':visual['version']='v999'
    else:v['package']['inputs']['assets'][0]['sha256']='0'*64
    with pytest.raises(SceneVideoError):asset_binding(v['package'],visual)


def test_wrong_language_and_missing_voice(proof):
    from tools.audio.local_narration import select_local_voice
    from tools.base_tool import ToolStatus
    class Installed:
        def get_status(self):return ToolStatus.AVAILABLE
        def list_voices(self):return [{'name':'English only','language_code':'en-US','speech_host':'powershell'}]
    for language,voice in [('vi','English only'),('en','missing')]:
        with pytest.raises(ValueError):select_local_voice(lambda _:Installed(),language,provider='windows_sapi',voice=voice)


def test_synthetic_allowlist_is_exact():
    assert hashlib.sha256(STORY.encode()).hexdigest() in service.PROOF_SOURCES
    assert hashlib.sha256(VI_STORY.encode()).hexdigest() in service.PROOF_SOURCES
    assert 'Phương' in VI_STORY and 'Lena' not in VI_STORY


def test_vietnamese_canonical_workflow(tmp_path):
    store=ProductionStore(tmp_path/'p',ApprovedPackages(ROOT))
    v=prepare_vi(store)
    assert v['ready_for_next_stage'] and v['package']['language']=='vi'
    assert service._current(store,'vi-proof')[1]['version']==v['version']


def test_api_consent_and_local_origin(proof):
    from studio.server import create_app
    store,v,_,_=proof
    with TestClient(create_app(store),base_url='http://localhost') as client:
        base='/studio/api/productions/fx/story-video'
        status=client.get(base).json();assert status['eligible'] and not status['publishing_enabled']
        payload={'plan':status['plan'],'narration_job':'a'*16,'narration_sha256':'b'*64,'render_consent':False,'scale':.5}
        assert client.post(base+'/jobs/render',json=payload).status_code==409
        assert client.post(base+'/jobs/render',json=payload,headers={'Origin':'https://evil.example'}).status_code==403
        assert client.get(base+'/jobs/not-a-job').status_code==409


def test_interrupted_render_not_served(proof,tmp_path):
    original,_,_,_=proof;shutil.copytree(original.root,tmp_path/'p');store=ProductionStore(tmp_path/'p',ApprovedPackages(ROOT))
    ident='a'*16;folder=store.root/'fx'/service.OUTPUT/'jobs'/ident;folder.mkdir(parents=True)
    binding=service._current(store,'fx')[1]
    (folder/'request.json').write_text(json.dumps(service._seal({'kind':'render','plan':binding,'payload':{}})))
    (folder/'events.jsonl').write_text(json.dumps({'state':'running','message':'rendering'})+'\n')
    (folder/'short').mkdir();(folder/'short'/'pending.mp4').write_bytes(b'partial')
    assert service.job(store,'fx',ident)['state']=='interrupted'
    with pytest.raises(SceneVideoError):service.media_file(store,'fx',ident,'short','video')


def test_jobs_order_by_creation_not_random_uuid(proof,tmp_path):
    original,_,_,_=proof;shutil.copytree(original.root,tmp_path/'p');store=ProductionStore(tmp_path/'p',ApprovedPackages(ROOT))
    binding=service._current(store,'fx')[1]
    for ident,at in [('f'*16,'2026-10-26T00:00:00Z'),('a'*16,'2026-10-26T01:00:00Z')]:
        folder=store.root/'fx'/service.OUTPUT/'jobs'/ident;folder.mkdir(parents=True)
        (folder/'request.json').write_bytes(json.dumps(service._seal({'kind':'narration','plan':binding,'payload':{}})).encode())
        (folder/'events.jsonl').write_text(json.dumps({'state':'running','message':'working','at':at})+'\n')
    assert [j['job_id'] for j in service.status(store,'fx')['jobs']]==['f'*16,'a'*16]


@pytest.mark.parametrize('dependency',['FFmpeg','Chrome'])
def test_failed_real_render_subprocess_is_not_published(proof,tmp_path,monkeypatch,dependency):
    # Failure injection at the composition tool boundary, after actual validation
    # and actual package/SFX generation. No fabricated successful render result.
    from tools.base_tool import ToolResult
    from tests.studio.test_scene_staging import make_store,approve
    from studio.scene_staging import prepare_staging
    original,v,_,results=proof
    store,payload=make_store(proof,tmp_path)
    reviewed=approve(store,prepare_staging(store,'fx',payload))  # Explicit synthetic test-only review.
    binding=payload['plan']
    original_tool=service._tool
    class FailedCompose:
        def execute(self,inputs):return ToolResult(success=False,error=dependency+' subprocess failed (injected)')
    monkeypatch.setattr(service,'_tool',lambda name:FailedCompose() if name=='video_compose' else original_tool(name))
    output=tmp_path/'output';output.mkdir()
    with pytest.raises(SceneVideoError,match=dependency):
        service._render(store,'fx',{'plan':binding,'narration_job':payload['narration']['job_id'],
            'narration_sha256':payload['narration']['manifest_sha256'],'staging':reviewed['reference'],'scale':.5},output,lambda _:None)
    assert not list(output.rglob('full-story.mp4'))
    assert read_scene_plan(store,'fx')['package_sha256']==v['package_sha256']
