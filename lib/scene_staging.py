"""Opt-in P3.5 visual staging v1; frozen Scene Plans and asset revisions are inputs.

This contract adds reviewed execution state, never infers it from narrative prose.
"""
from __future__ import annotations
import copy
import hashlib
import math
from pathlib import Path
from tools.character import horror_assets as assets
from tools.character.horror_acting import ActorBuilder
from lib.story_visual_bible import fingerprint

VERSION = '1.0'


def capability_signature():
    root=Path(__file__).resolve().parents[1]
    paths=('lib/scene_staging.py','tools/character/horror_acting.py','tools/character/remotion/CinematicHorror.tsx')
    return {'version':VERSION,'implementation_sha256':{p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in paths}}


class StagingError(ValueError):
    def __init__(self,code,message):super().__init__(message);self.code=code


def reject(message):raise StagingError('visual_staging_invalid',message)


def evidence(plan, refs):
    if not isinstance(refs,list) or not refs:reject('Exact canonical source evidence is required.')
    units=[s['source']['narration'] for f in plan['formats'].values() for s in f['shots'] if s['kind']=='narrative']
    segments={}
    for n in units:
        spans=n['sources']
        sizes=[s['char_end']-s['char_start'] for s in spans]
        if n['mode']!='verbatim' or len(n['text'])!=sum(sizes)+max(0,len(sizes)-1):continue
        cursor=0
        for span,size in zip(spans,sizes):
            segments.setdefault(span['segment_id'],[]).append(n['text'][cursor:cursor+size]);cursor+=size+1
    for ref in refs:
        if (not isinstance(ref,dict) or set(ref)!={'segment_id','quote'} or not isinstance(ref['quote'],str)
                or not ref['quote'] or not any(ref['quote'] in text for text in segments.get(ref['segment_id'],[]))):
            reject('Source quote/segment is not in the verified approved narration.')


def number(value):return type(value) in (int,float) and math.isfinite(value)


def keys(track,length):
    if not isinstance(track,list) or len(track)<2:reject('Lamp intensity needs a complete track.')
    previous=-1
    for key in track:
        if (not isinstance(key,list) or len(key)!=2 or not all(number(v) for v in key)
                or not previous<key[0]<=length+1e-8 or not 0<=key[1]<=1):reject('Invalid lamp intensity track.')
        previous=key[0]
    if track[0][0]!=0 or abs(track[-1][0]-length)>1e-8:reject('Lamp track must cover its exact shot.')


def lamp_bindings(location):
    """Associate existing immutable geometry with its own verified fixture IDs."""
    g=location['cinematic'];lamps=g['lamps'];out={}
    for l in lamps:
        beams=[i for i,b in enumerate(g['beams']) if b['driver'] in ('constant','flicker') and
               abs((b['points'][0][0]+b['points'][1][0])/2-l['x'])<1e-8 and abs(b['points'][0][1]-l['y']-4)<1e-8]
        pools=[i for i,p in enumerate(g['pools']) if p['driver'] in ('constant','flicker') and abs(p['cx']-l['x'])<1e-8]
        if len(beams)!=1 or len(pools)!=1:reject('Pinned lighting cannot unambiguously bind lamp glow/beam/pool.')
        out[l['id']]={'beam':beams[0],'pool':pools[0]}
    return out


def validate_package(plan, timed, package, binding):
    try:return _validate_package(plan,timed,package,binding)
    except (ValueError,TypeError,KeyError,StopIteration,ZeroDivisionError) as exc:
        if isinstance(exc,StagingError):raise
        reject(f'Malformed visual staging contract: {exc}')


def _validate_package(plan, timed, package, binding):
    if (set(package)!={'artifact','schema_version','capabilities','plan','timing_sha256','overrides','cut_relocations'}
            or package['artifact']!='scene_visual_staging' or package['schema_version']!=VERSION
            or package['capabilities']!=capability_signature()
            or package['plan']!=binding or package['timing_sha256']!={f:fingerprint(t) for f,t in timed.items()}
            or set(package['overrides'])!={'short','long'}):reject('Wrong staging version, plan, or measured timing binding.')
    for fmt,overrides in package['overrides'].items():
        shots={s['shot_id']:s for s in plan['formats'][fmt]['shots']}
        scenes={s['scene_id']:s for s in plan['formats'][fmt]['scenes']}
        windows={s['shot_id']:s for s in timed[fmt]['shots']}
        if not isinstance(overrides,dict) or set(overrides)-set(shots):reject('Unknown approved shot override.')
        for sid,pick in overrides.items():
            if not isinstance(pick,dict) or set(pick)-{'evidence','lamps','actors','camera'} or not set(pick)&{'lamps','actors'}:
                reject('Use only explicit lamp, seated-actor and camera review fields.')
            evidence(plan,pick.get('evidence'))
            shot=shots[sid];length=windows[sid]['frame_count']/30
            pin=scenes[shot['scene_id']]['environment']
            env=assets.environment(pin['id'],pin['revision'])
            if 'lamps' in pick:
                if set(pick['lamps'])!={l['id'] for l in env['features']['lamps']}:reject('Review every verified environment lamp ID.')
                for track in pick['lamps'].values():keys(track,length)
            if 'actors' in pick:
                cast={c['character_id']:c for c in shot['staging']['cast']}
                if not pick['actors'] or set(pick['actors'])-set(cast):reject('Unknown seated actor.')
                for cid,row in pick['actors'].items():
                    if (set(row)!={'mode','anchor','facing'} or row['mode']!='seated_at_cut'
                            or row['anchor']!='armchair_seat' or row['anchor'] not in env['features']['props']
                            or type(row['facing']) is not int or row['facing'] not in (-1,1)):
                        reject('Seated-at-cut requires an existing chair anchor and explicit facing.')
                    motion=next(a for a in shot['motion_plan']['actors'] if a['character_id']==cid)
                    if any(s['preset'] not in ('hold','listening_freeze') for s in motion['steps']):
                        reject('Seated substitution cannot remove a walk/reach/action; create a newly timed plan first.')
            if 'camera' in pick:
                c=pick['camera']
                if set(c)!={'x','y','zoom'} or not all(number(v) for v in c.values()):reject('Explicit static camera coordinates required.')
                w=plan['formats'][fmt]['viewport'];half=w['width']*720/w['height']/2/c['zoom'] if c['zoom']>0 else float('inf')
                if c['zoom']<1 or not half<=c['x']<=1280-half or not 360/c['zoom']<=c['y']<=720-360/c['zoom']:
                    reject('Reviewed camera leaves the artwork.')
    if set(package['cut_relocations'])!={'short','long'}:reject('Both format cut reviews required.')
    for fmt,rows in package['cut_relocations'].items():
        shots=plan['formats'][fmt]['shots'];ids=[s['shot_id'] for s in shots];seen=set()
        for row in rows:
            if set(row)!={'from','to','character_id','treatment','evidence'} or row['treatment']!='time_ellipsis':reject('Explicit cut relocation review required.')
            if row['from'] not in ids or ids.index(row['from'])+1>=len(ids) or ids[ids.index(row['from'])+1]!=row['to']:
                reject('Cut review must reference adjacent approved shots.')
            a,b=shots[ids.index(row['from'])],shots[ids.index(row['to'])]
            if row['character_id'] not in {c['character_id'] for c in a['staging']['cast']} & {c['character_id'] for c in b['staging']['cast']}:
                reject('Cut relocation actor must appear in both adjacent shots.')
            evidence(plan,row['evidence']);key=(row['from'],row['to'],row['character_id'])
            if key in seen:reject('Duplicate cut relocation.')
            seen.add(key)
        # A seated hold must persist until an explicitly reviewed ellipsis permits a move.
        for a,b in zip(shots,shots[1:]):
            if a['source']['location_id']!=b['source']['location_id']:continue
            previous=package['overrides'][fmt].get(a['shot_id'],{}).get('actors',{})
            current=package['overrides'][fmt].get(b['shot_id'],{}).get('actors',{})
            for cid in set(previous)|set(current):
                if previous.get(cid)!=current.get(cid) and (a['shot_id'],b['shot_id'],cid) not in seen:
                    reject('Changed seated/standing state across a cut needs explicit time-ellipsis review.')


def seat_actor(cast, location, length, selection):
    env=assets.environment(location['asset']['environment'],location['asset']['revision'])
    seat=env['features']['props'][selection['anchor']];floor=env['features']['floor_y']
    b=ActorBuilder(cast['id'],cast['look'],seat[0],facing=selection['facing'],
                   rest_posture=assets.get('character',cast['look']['design']['id'],cast['look']['design']['revision'])['rest_posture'])
    b.seated_listening(seat,floor,0,length)
    actor=b.build(length)
    for track in ('root','left_hand','right_hand','left_foot','right_foot','posture','face'):
        actor[track][-1][0]=length
    actor['opacity']=copy.deepcopy(cast['opacity'])
    actor['seat_support']={'schema_version':VERSION,'anchor':selection['anchor'],'position':list(seat),'floor_y':floor,'mode':'seated_at_cut'}
    return actor


def apply_review(video,timeline,package,reference):
    fmt=video['metadata']['format']
    visual={'schema_version':VERSION,'review':reference,'shots':{}}
    for shot,scene in zip(video['shots'],timeline['scenes']):
        pick=package['overrides'][fmt].get(shot['id'])
        if not pick:continue
        loc=video['locations'][shot['location']];length=shot['end_seconds']-shot['start_seconds'];state={}
        if 'lamps' in pick:
            state={'lamps':copy.deepcopy(pick['lamps']),'bindings':lamp_bindings(loc)}
            scene['effects'].append('reviewed_per_lamp_state:'+reference['version'])
        if 'actors' in pick:
            shot['actors']=[seat_actor(a,loc,length,pick['actors'][a['id']]) if a['id'] in pick['actors'] else a for a in shot['actors']]
            for action in scene['actions']:
                if action['character_id'] in pick['actors']:action['action']='seated_listening'
        if 'camera' in pick:
            c=pick['camera'];shot['camera']=[[0,c['x'],c['y'],c['zoom']],[length,c['x'],c['y'],c['zoom']]]
            scene['camera']={'move':'static','size':'reviewed_seated_framing','keys':copy.deepcopy(shot['camera'])}
        visual['shots'][shot['id']]=state
    video['visual_state']=visual
    video['metadata']['staging_review']=copy.deepcopy(reference)
    timeline['metadata']['staging_review']=copy.deepcopy(reference)


def validate_runtime(video):
    v=video.get('visual_state')
    if v is None:return
    if not isinstance(v,dict) or set(v)!={'schema_version','review','shots'} or v['schema_version']!=VERSION:reject('Unknown runtime visual state version.')
    shots={s['id']:s for s in video['shots']}
    if set(v['shots'])-set(shots):reject('Unknown runtime visual-state shot.')
    for sid,row in v['shots'].items():
        shot=shots[sid];loc=video['locations'][shot['location']];length=shot['end_seconds']-shot['start_seconds']
        if set(row)-{'lamps','bindings'}:reject('Unknown runtime emission field.')
        if 'lamps' in row:
            if row.get('bindings')!=lamp_bindings(loc) or set(row['lamps'])!=set(row['bindings']):reject('Runtime lamp binding mismatch.')
            for track in row['lamps'].values():keys(track,length)
    for shot in video['shots']:
        env=video['locations'][shot['location']]
        for actor in shot['actors']:
            support=actor.get('seat_support')
            if not support:continue
            real=assets.environment(env['asset']['environment'],env['asset']['revision'])['features']
            if (support.get('schema_version')!=VERSION or support.get('anchor')!='armchair_seat'
                    or support['position']!=real['props'].get('armchair_seat') or support['floor_y']!=real['floor_y']):reject('Seat support differs from pinned anchor.')
            x,y=support['position'];length=shot['end_seconds']-shot['start_seconds']
            from tools.character.story_video import _sample
            for frame in range(round(length*video['fps'])+1):
                t=min(length,frame/video['fps']);root=_sample(actor['root'],t)
                if math.dist(root,[x,y])>.001:reject('Seated pelvis left the chair support.')
                for foot in ('left_foot','right_foot'):
                    p=_sample(actor[foot],t)
                    if abs(p[1]-support['floor_y'])>.001 or not 80<math.dist(root,p)<110:reject('Seated leg/foot geometry is not supported.')
