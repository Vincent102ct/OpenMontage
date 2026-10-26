"""Existing-IK chair contact and opt-in emission controls; no source-story inference."""
import copy
import math
import pytest
from lib.scene_staging import lamp_bindings,validate_runtime,StagingError
from tools.character import horror_assets as assets
from tools.character.horror_acting import ActorBuilder
from tools.character.story_video import actor_limb_distances,_reachable,_sample


@pytest.mark.parametrize('facing',[-1,1])
@pytest.mark.parametrize('character',['nora_vale','victor_hale'])
def test_seated_listening_supported_at_every_frame(facing,character):
    char=assets.get('character',character);look={'design':{'id':character,'revision':1}}
    b=ActorBuilder('actor',look,192,rest_posture=char['rest_posture'],facing=facing)
    b.seated_listening([192,540],620,0,3)
    actor=b.build(3)
    for i in range(91):
        t=i/30;assert _sample(actor['root'],t)==[192,540]
        for name,d in actor_limb_distances(actor,t).items():assert _reachable(name,d)
        for foot in ('left_foot','right_foot'):
            p=_sample(actor[foot],t);assert p[1]==620 and 40<=facing*(p[0]-192)<=60
            assert math.dist([192,540],p)<110


@pytest.mark.parametrize('facing',[-1,1])
def test_real_sit_down_keeps_feet_planted_and_bends_legs(facing):
    c=assets.get('character','nora_vale')
    b=ActorBuilder('actor',{},192+facing*40,rest_posture=c['rest_posture'],facing=facing)
    b.pose['left_foot']=[192+facing*44,620];b.pose['right_foot']=[192+facing*56,620];b._key(0)
    initial=copy.deepcopy(b.pose);b.seated_listening([192,540],620,0,1.2,sit_down=True);b.hold(3)
    a=b.build(3)
    for i in range(91):
        t=i/30
        for foot in ('left_foot','right_foot'):assert _sample(a[foot],t)==initial[foot]
        for name,d in actor_limb_distances(a,t).items():assert _reachable(name,d)
    assert _sample(a['root'],0)!=_sample(a['root'],1.2)==[192,540]


def test_bad_seat_or_transition_is_not_a_standing_substitute():
    b=ActorBuilder('actor',{},192,rest_posture=[5,-99,10,-160])
    with pytest.raises(ValueError):b.seated_listening([192,300],620,0,3)
    with pytest.raises(ValueError):b.seated_listening([192,540],620,0,.5,sit_down=True)


def test_lamp_geometry_mapping_and_frozen_asset_hashes():
    before=assets.content_hash(assets.get('environment','dark_apartment_corridor'))
    env=assets.environment('dark_apartment_corridor')
    g=assets.lighting_geometry(env,'flickering_interior',flicker_lamp='lamp_mid')
    bindings=lamp_bindings({'cinematic':g})
    assert set(bindings)=={'lamp_west','lamp_mid','lamp_east'}
    assert len({v['beam'] for v in bindings.values()})==3 and len({v['pool'] for v in bindings.values()})==3
    assert assets.content_hash(assets.get('environment','dark_apartment_corridor'))==before
    assert [l['driver'] for l in g['lamps']]==['constant','flicker','constant']  # legacy unchanged
    assert min(k[1] for k in assets.flicker_track(3,[1]))==.04  # legacy never silently redefined
