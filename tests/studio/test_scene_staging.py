"""Synthetic-only approvals here are test fixtures, not approval of the live repair candidate."""
import copy
import json
import shutil
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from lib.scene_staging import StagingError,validate_package,capability_signature
from lib.scene_video import compile_video,validate_compilation
from lib.story_visual_bible import fingerprint
from studio import scene_staging as staging
from studio import story_video as production
from studio.catalog import ApprovedPackages
from studio.reviewed import _bytes
from studio.store import ProductionStore
from tests.studio.test_story_video import proof

ROOT=Path(__file__).resolve().parents[2]


def make_store(proof,tmp):
    old,view,visual,results=proof;shutil.copytree(old.root,tmp/'p')
    store=ProductionStore(tmp/'p',ApprovedPackages(ROOT));binding=production._current(store,'fx')[1]
    formats={}
    for fmt in ('short','long'):
        bundle,audio,timed,_,_=results[fmt]
        relative=f'{production.OUTPUT}/audio/{fmt}';target=store.root/'fx'/relative
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(audio,target)
        (target/'bundle.json').write_bytes(_bytes(bundle))
        formats[fmt]={'cache':relative,'manifest_sha256':bundle['manifest_sha256'],
                      'duration_seconds':timed['duration_seconds'],'units':len(bundle['units'])}
    ident='1'*16;folder=store.root/'fx'/production.OUTPUT/'jobs'/ident;folder.mkdir(parents=True)
    result=production._seal({'artifact':'scene_video_narration_set','formats':formats,'plan':binding,'voice':{'test_tone_only':True}})
    (folder/'result.json').write_bytes(_bytes(result))
    (folder/'request.json').write_bytes(_bytes(production._seal({'kind':'narration','plan':binding,'payload':{}})))
    (folder/'events.jsonl').write_text(json.dumps({'state':'complete','message':'test tones only','at':'2026-10-26T00:00:00Z'})+'\n')
    return store,{'plan':binding,'narration':{'job_id':ident,'manifest_sha256':result['manifest_sha256']},
                  'base_version':None,'overrides':{'short':{},'long':{}},'cut_relocations':{'short':[],'long':[]}}


def propose(store,payload):
    view,_,timed=staging.context(store,'fx',payload['narration'])
    for fmt in ('short','long'):
        shots=view['package']['formats'][fmt]['shots'];sid=next(s['shot_id'] for s in shots if s['source']['location_id']=='LOC_HALL')
        n=next(s['source']['narration'] for s in shots if s['shot_id']==sid)
        t=next(s for s in timed[fmt]['shots'] if s['shot_id']==sid);length=t['frame_count']/30
        payload['overrides'][fmt][sid]={'evidence':[{'segment_id':n['sources'][0]['segment_id'],'quote':n['text']}],
            'lamps':{lamp:[[0,1 if lamp=='lamp_mid' else 0],[length,1 if lamp=='lamp_mid' else 0]]
                     for lamp in ('lamp_west','lamp_mid','lamp_east')}}
    return payload


def approve(store,candidate):
    return staging.approve_staging(store,'fx',candidate['version'],{'package_sha256':candidate['reference']['package_sha256'],
        'manifest_sha256':candidate['reference']['manifest_sha256'],'reviewed_items':candidate['review_items'],'consent':True})


def test_candidate_does_not_approve_and_history_is_immutable(proof,tmp_path):
    store,payload=make_store(proof,tmp_path);candidate=staging.prepare_staging(store,'fx',propose(store,payload))
    assert not candidate['ready_for_render'] and candidate['approval'] is None
    with pytest.raises(StagingError):staging.approved_staging(store,'fx',candidate['reference'])
    current=approve(store,candidate);assert current['ready_for_render']
    first={p.name:p.read_bytes() for p in (store.root/'fx'/staging.OUTPUT/'v1').iterdir()}
    payload['base_version']='v1';second=staging.prepare_staging(store,'fx',payload)
    assert second['version']=='v2' and not second['approval']
    assert first=={p.name:p.read_bytes() for p in (store.root/'fx'/staging.OUTPUT/'v1').iterdir()}
    with pytest.raises(StagingError):staging.approved_staging(store,'fx',current['reference'])


@pytest.mark.parametrize('fault',['consent','missing_items','duplicate_items','manifest','package'])
def test_separate_exact_review_gate(proof,tmp_path,fault):
    store,payload=make_store(proof,tmp_path);c=staging.prepare_staging(store,'fx',propose(store,payload))
    body={'package_sha256':c['reference']['package_sha256'],'manifest_sha256':c['reference']['manifest_sha256'],
          'reviewed_items':c['review_items'],'consent':True}
    if fault=='consent':body['consent']=False
    elif fault=='missing_items':body['reviewed_items']=[]
    elif fault=='duplicate_items':body['reviewed_items']=body['reviewed_items']*2
    else:body[{'manifest':'manifest_sha256','package':'package_sha256'}[fault]]='0'*64
    with pytest.raises(StagingError):staging.approve_staging(store,'fx','v1',body)
    assert not (store.root/'fx'/staging.OUTPUT/'v1/approval.json').exists()


@pytest.mark.parametrize('fault',['unknown_lamp','missing_lamp','out_of_range','nan','missing_end','source','segment_mismatch','shot','timing','version','capabilities'])
def test_bad_opt_in_state_fails_closed(proof,tmp_path,fault):
    store,payload=make_store(proof,tmp_path);payload=propose(store,payload)
    v,b,t=staging.context(store,'fx',payload['narration'])
    p={'artifact':'scene_visual_staging','schema_version':'1.0','capabilities':capability_signature(),'plan':b,'timing_sha256':{f:fingerprint(x) for f,x in t.items()},
       'overrides':payload['overrides'],'cut_relocations':payload['cut_relocations']}
    validate_package(v['package'],t,p,b)
    row=next(iter(p['overrides']['long'].values()))
    if fault=='unknown_lamp':row['lamps']['not_real']=[[0,0],[1,0]]
    elif fault=='missing_lamp':row['lamps'].pop('lamp_east')
    elif fault=='out_of_range':row['lamps']['lamp_mid'][0][1]=2
    elif fault=='nan':row['lamps']['lamp_mid'][0][1]=float('nan')
    elif fault=='missing_end':row['lamps']['lamp_mid'].pop()
    elif fault=='source':row['evidence'][0]['quote']='invented'
    elif fault=='segment_mismatch':row['evidence']=[{'segment_id':'SEG_0009','quote':'Lena nodded.'}]
    elif fault=='shot':p['overrides']['long']['SH_UNKNOWN']=row
    elif fault=='timing':p['timing_sha256']['long']='0'*64
    elif fault=='version':p['schema_version']='2.0'
    elif fault=='capabilities':p['capabilities']['version']='wrong'
    with pytest.raises(StagingError):validate_package(v['package'],t,p,b)


def test_approved_extension_compiles_without_rewriting_scene_plan(proof,tmp_path):
    store,payload=make_store(proof,tmp_path);c=approve(store,staging.prepare_staging(store,'fx',propose(store,payload)))
    _,view,visual,results=proof
    for fmt in ('short','long'):
        bundle,audio,timed,_,_=results[fmt]
        video,timeline=compile_video(view,visual,fmt,bundle,audio,timed,audio/'narration.txt',c)
        validate_compilation(view,fmt,timed,video,timeline,c)
        assert video['visual_state']['review']==c['reference']
        assert len(video['shots'])==(13 if fmt=='short' else 20)
        bad=copy.deepcopy(video);next(iter(bad['visual_state']['shots'].values()))['lamps']['lamp_east'][0][1]=1
        with pytest.raises(ValueError):validate_compilation(view,fmt,timed,bad,timeline,c)


def test_ui_api_requires_local_origin_and_explicit_review(proof,tmp_path):
    from studio.server import create_app
    store,payload=make_store(proof,tmp_path);c=staging.prepare_staging(store,'fx',propose(store,payload))
    with TestClient(create_app(store),base_url='http://localhost') as client:
        url='/studio/api/productions/fx/story-video/staging'
        assert client.get(url).json()['status']=='awaiting_review'
        assert client.post(url,json=payload,headers={'Origin':'https://evil.example'}).status_code==403
        assert client.post(url+'/v1/approve',json={'consent':False}).status_code==409
        assert not client.get(url).json()['approval']
        body={'package_sha256':c['reference']['package_sha256'],'manifest_sha256':c['reference']['manifest_sha256'],
              'reviewed_items':c['review_items'],'consent':True}
        assert client.post(url+'/v1/approve',json=body).json()['ready_for_render']


def test_seated_state_camera_and_explicit_cut_derivative(proof,tmp_path):
    store,payload=make_store(proof,tmp_path);view,binding,timed=staging.context(store,'fx',payload['narration'])
    actor=view['package']['formats']['long']['shots'][0]['staging']['cast'][0]['character_id']
    for fmt,fp in view['package']['formats'].items():
        for s in fp['shots']:
            if s['source']['location_id']!='LOC_ROOM':continue
            m=next(a for a in s['motion_plan']['actors'] if a['character_id']==actor)
            if any(step['preset'] not in ('hold','listening_freeze') for step in m['steps']):continue
            payload['overrides'][fmt][s['shot_id']]={'evidence':[{'segment_id':'SEG_0002','quote':'Lena sat alone'}],
                'actors':{actor:{'mode':'seated_at_cut','anchor':'armchair_seat','facing':1}},
                'camera':{'x':252,'y':360,'zoom':1} if fmt=='short' else {'x':320,'y':480,'zoom':2}}
        for a,b in zip(fp['shots'],fp['shots'][1:]):
            if a['source']['location_id']==b['source']['location_id']=='LOC_ROOM':
                previous=payload['overrides'][fmt].get(a['shot_id'],{}).get('actors',{})
                current=payload['overrides'][fmt].get(b['shot_id'],{}).get('actors',{})
                if previous!=current:payload['cut_relocations'][fmt].append({'from':a['shot_id'],'to':b['shot_id'],
                    'character_id':actor,'treatment':'time_ellipsis','evidence':[{'segment_id':'SEG_0006','quote':'Lena crossed the room'}]})
    candidate=staging.prepare_staging(store,'fx',payload)
    _,source,visual,results=proof
    bundle,audio,t,_,_=results['long']
    with pytest.raises(ValueError):compile_video(source,visual,'long',bundle,audio,t,audio/'narration.txt',candidate)
    approved=approve(store,candidate)
    video,timeline=compile_video(source,visual,'long',bundle,audio,t,audio/'narration.txt',approved)
    seated=[a for s in video['shots'] for a in s['actors'] if a.get('seat_support')]
    assert len(seated)==9 and all(a['root'][0][1:]==[192,540] for a in seated)
    assert all(s['camera'][0][1:]==[320,480,2] for s in video['shots'] if any(a.get('seat_support') for a in s['actors']))
    assert any(a['action']=='seated_listening' for s in timeline['scenes'] for a in s['actions'])
    validate_compilation(source,'long',t,video,timeline,approved)
    payload['base_version']='v1';payload['cut_relocations']={'short':[],'long':[]}
    with pytest.raises(StagingError):staging.prepare_staging(store,'fx',payload)
