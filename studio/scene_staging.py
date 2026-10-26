"""Immutable, separately reviewed visual execution extension over approved P3.4.

No GET, candidate preparation, renderer update or scene approval approves this gate.
"""
from __future__ import annotations
import json
import re
from datetime import datetime,timezone
from pathlib import Path

from lib import story_scene_plan as planner
from lib.scene_staging import StagingError, validate_package, capability_signature, VERSION
from lib.scene_video import verify_narration
from lib.story_visual_bible import fingerprint
from studio.review import review_lock,safe_review_path,write_once
from studio.reviewed import _bytes,_sha
from tools.character import horror_assets as assets

OUTPUT='artifacts/scene_visual_staging'
V=re.compile(r'v[1-9][0-9]*\Z')


def error(code,message):raise StagingError(code,message)


def seal(data):return {**data,'manifest_sha256':fingerprint(data)}


def context(store,project_id,narration):
    from studio import story_video as production
    view,binding=production._current(store,project_id)
    if not isinstance(narration,dict) or set(narration)!={'job_id','manifest_sha256'}:error('stale_staging','Exact narration job binding required.')
    job=production.job(store,project_id,narration['job_id'])
    if (job['state']!='complete' or job['kind']!='narration' or not job['is_current']
            or job['result']['manifest_sha256']!=narration['manifest_sha256']):error('stale_staging','Narration reference is stale or unverified.')
    timed={}
    for fmt,ref in job['result']['formats'].items():
        folder=safe_review_path(store._project(project_id),ref['cache'])
        bundle=production._json(store._project(project_id),ref['cache']+'/bundle.json')
        if bundle['manifest_sha256']!=ref['manifest_sha256']:error('stale_staging','Audio bundle hash changed.')
        measured=verify_narration(view,fmt,bundle,folder)
        timed[fmt]=planner.retime(view['package'],fmt,measured,approved=view)
    return view,binding,timed


def items(package):
    out=[f'{fmt}/{sid}' for fmt,rows in package['overrides'].items() for sid in rows]
    out += [f"{fmt}/cut/{r['from']}/{r['to']}/{r['character_id']}" for fmt,rows in package['cut_relocations'].items() for r in rows]
    return sorted(out)


def versions(project):
    folder=safe_review_path(project,OUTPUT)
    return sorted([p.name for p in folder.iterdir() if V.fullmatch(p.name) and p.is_dir()],key=lambda s:int(s[1:])) if folder.is_dir() else []


def _history(project):
    history=[];previous=None
    try:
        for i,version in enumerate(versions(project),1):
            if version!=f'v{i}':error('staging_invalid','Visual staging history is not contiguous.')
            base=safe_review_path(project,f'{OUTPUT}/{version}')
            raw=safe_review_path(project,f'{OUTPUT}/{version}/package.json').read_bytes();package=json.loads(raw)
            manifest_raw=safe_review_path(project,f'{OUTPUT}/{version}/manifest.json').read_bytes();manifest=json.loads(manifest_raw)
            if (manifest.get('artifact')!='scene_visual_staging_manifest' or manifest.get('schema_version')!=VERSION
                    or manifest.get('version')!=version or manifest.get('project_id')!=project.name
                    or manifest.get('package_sha256')!=_sha(raw) or manifest.get('previous_manifest_sha256')!=previous
                    or manifest.get('manifest_sha256')!=fingerprint({k:v for k,v in manifest.items() if k!='manifest_sha256'})
                    or manifest.get('plan')!=package.get('plan') or manifest.get('timing_sha256')!=package.get('timing_sha256')
                    or manifest_raw!=_bytes(manifest) or raw!=_bytes(package)):
                error('staging_invalid','Visual staging package/manifest history integrity failed.')
            previous=manifest['manifest_sha256'];approval=None
            if (base/'approval.json').exists():
                approval_raw=safe_review_path(project,f'{OUTPUT}/{version}/approval.json').read_bytes();approval=json.loads(approval_raw)
                if (approval.get('artifact')!='scene_visual_staging_approval' or approval.get('schema_version')!=VERSION
                        or approval.get('version')!=version or approval.get('project_id')!=project.name
                        or approval.get('package_sha256')!=manifest['package_sha256']
                        or approval.get('candidate_manifest_sha256')!=manifest['manifest_sha256']
                        or approval.get('plan')!=manifest['plan'] or approval.get('narration')!=manifest['narration']
                        or approval.get('reviewed_items')!=items(package) or approval.get('consent') is not True
                        or approval.get('manifest_sha256')!=fingerprint({k:v for k,v in approval.items() if k!='manifest_sha256'})
                        or approval_raw!=_bytes(approval)):
                    error('staging_invalid','Visual staging approval integrity failed.')
            history.append((package,manifest,approval))
        return history
    except (OSError,ValueError,KeyError,TypeError) as exc:
        if isinstance(exc,StagingError):raise
        error('staging_invalid',f'Visual staging artifacts cannot be verified: {exc}')


def _view(store,project_id,package,manifest,approval):
    view,binding,timed=context(store,project_id,manifest['narration'])
    validate_package(view['package'],timed,package,binding)
    changes=[]
    for fmt,rows in package['overrides'].items():
        source={s['shot_id']:s for s in view['package']['formats'][fmt]['shots']}
        for sid,pick in rows.items():
            lamps=None
            if 'lamps' in pick:
                scene=next(s for s in view['package']['formats'][fmt]['scenes'] if s['scene_id']==source[sid]['scene_id'])
                env=assets.environment(scene['environment']['id'],scene['environment']['revision'])
                lighting=source[sid]['staging']['lighting']
                geometry=assets.lighting_geometry(env,lighting['preset']['id'],flicker_lamp=lighting['flicker_lamp'])
                lamps={l['id']:{'driver':l['driver'],'enabled_without_override':True} for l in geometry['lamps']}
            changes.append({'item':f'{fmt}/{sid}','format':fmt,'shot_id':sid,'before':source[sid]['staging'],
                            'before_motion':source[sid]['motion_plan'],'before_lamp_emissions':lamps,'proposed':pick})
    reference={'version':manifest['version'],'package_sha256':manifest['package_sha256'],
               'manifest_sha256':manifest['manifest_sha256'],
               'approval_sha256':_sha(_bytes(approval)) if approval else None}
    return {'status':'approved' if approval else 'awaiting_review','version':manifest['version'],'package':package,
            'manifest':manifest,'approval':approval,'reference':reference,'review_items':items(package),'changes':changes,
            'ready_for_render':bool(approval),'artistic_audio_acceptance':'pending','publishing_enabled':False}


def read_staging(store,project_id,version=None):
    project=store._project(project_id);history=_history(project)
    if not history:return {'status':'not_prepared','ready_for_render':False,'publishing_enabled':False}
    if version is not None and not V.fullmatch(version):error('staging_invalid','Invalid visual staging version.')
    selected=next((row for row in history if row[1]['version']==version),None) if version else history[-1]
    if selected is None:error('staging_missing','Visual staging version not found.')
    result=_view(store,project_id,*selected)
    result['is_current']=selected[1]['version']==history[-1][1]['version']
    result['ready_for_render']=result['ready_for_render'] and result['is_current']
    return result


def prepare_staging(store,project_id,payload):
    expected={'plan','narration','base_version','overrides','cut_relocations'}
    if not isinstance(payload,dict) or set(payload)!=expected:error('staging_invalid','Exact staging candidate fields required.')
    project=store._project(project_id)
    with review_lock(project):
        history=_history(project);current=history[-1][1]['version'] if history else None
        if payload['base_version']!=current:error('stale_staging','Reload current staging history before saving.')
        view,binding,timed=context(store,project_id,payload['narration'])
        if payload['plan']!=binding:error('stale_staging','Scene Plan binding changed.')
        package={'artifact':'scene_visual_staging','schema_version':VERSION,'capabilities':capability_signature(),'plan':binding,
                 'timing_sha256':{f:fingerprint(t) for f,t in timed.items()},'overrides':payload['overrides'],
                 'cut_relocations':payload['cut_relocations']}
        validate_package(view['package'],timed,package,binding)
        version=f'v{len(history)+1}';raw=_bytes(package)
        manifest=seal({'artifact':'scene_visual_staging_manifest','schema_version':VERSION,'version':version,
            'project_id':project_id,'created_at':datetime.now(timezone.utc).isoformat(),'plan':binding,
            'narration':payload['narration'],'timing_sha256':package['timing_sha256'],'package_sha256':_sha(raw),
            'previous_manifest_sha256':history[-1][1]['manifest_sha256'] if history else None})
        base=safe_review_path(project,f'{OUTPUT}/{version}');base.mkdir(parents=True,exist_ok=False)
        write_once(base/'package.json',raw);write_once(base/'manifest.json',_bytes(manifest))
        return _view(store,project_id,package,manifest,None)


def approve_staging(store,project_id,version,payload):
    if (not isinstance(payload,dict) or set(payload)!={'package_sha256','manifest_sha256','reviewed_items','consent'}
            or payload['consent'] is not True):error('staging_review_required','Separate explicit staging consent is required.')
    project=store._project(project_id)
    with review_lock(project):
        view=read_staging(store,project_id,version)
        if (not view['is_current'] or payload['package_sha256']!=view['reference']['package_sha256']
                or payload['manifest_sha256']!=view['reference']['manifest_sha256']
                or not isinstance(payload['reviewed_items'],list) or sorted(payload['reviewed_items'])!=view['review_items']):
            error('stale_staging','Review every exact current shot/cut item and displayed hashes.')
        if view['approval']:return view
        approval=seal({'artifact':'scene_visual_staging_approval','schema_version':VERSION,'version':version,
            'project_id':project_id,'approved_at':datetime.now(timezone.utc).isoformat(),'plan':view['manifest']['plan'],
            'narration':view['manifest']['narration'],'package_sha256':payload['package_sha256'],
            'candidate_manifest_sha256':payload['manifest_sha256'],'reviewed_items':view['review_items'],'consent':True,
            'scope':'Visual execution extension only; artistic/audio acceptance and production consent remain separate.'})
        write_once(safe_review_path(project,f'{OUTPUT}/{version}/approval.json'),_bytes(approval))
        return read_staging(store,project_id,version)


def approved_staging(store,project_id,reference):
    if not isinstance(reference,dict):error('staging_review_required','An explicitly approved visual staging version is required.')
    view=read_staging(store,project_id,reference.get('version'))
    if not view['ready_for_render'] or view['reference']!=reference:error('stale_staging','Visual staging approval/reference is stale or incomplete.')
    return view
