"""Opening-episode acceptance: source fidelity, narration/action links and all-frame continuity."""
import copy
import importlib.util
import json
import subprocess
import wave
from pathlib import Path

import pytest

from tools.audio.procedural_sfx import RECIPES, ProceduralSFX
from tools.character.character_animation import CharacterRigRenderer
from tools.character.story_motion import validate_episode, walk_clip

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "examples/story-to-action"


def _silent_wav(path: Path, frames: int, rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1); out.setsampwidth(2); out.setframerate(rate)
        out.writeframes(b"\0\0" * frames)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """Build from the recorded real sample counts; media are silent stand-ins of equal length."""
    tmp = tmp_path_factory.mktemp("episode")
    for sid, d in json.loads((FIX / "opening.durations.json").read_text())["segments"].items():
        _silent_wav(tmp / "audio" / f"{sid}.wav", d["frames"], d["rate"])
    spec = importlib.util.spec_from_file_location("build_opening", FIX / "build_opening_episode.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    episode, timeline, renders = module.build(tmp / "audio", tmp / "sfx")
    for r in renders:
        _silent_wav(Path(r["output_path"]), 480, 48000)
    path = tmp / "story_episode.json"
    path.write_text(json.dumps(episode))
    return {"episode": episode, "timeline": timeline, "path": path, "module": module, "tmp": tmp}


def test_episode_validates_and_reproduces_source(built):
    ep = built["episode"]
    validate_episode(ep, built["timeline"])
    assert len(ep["narration"]) == 24 and len(ep["shots"]) == 11
    # Natural pacing from measured speech, not a forced 60 s: report the real length.
    assert 70 < ep["duration_seconds"] < 90


def test_every_narration_is_linked_to_an_overlapping_action(built):
    links = built["timeline"]["metadata"]["narration_links"]
    assert {l["narration_id"] for l in links} == {n["id"] for n in built["episode"]["narration"]}
    actions = {(s["scene_id"], i): a["action"] for s in built["timeline"]["scenes"] for i, a in enumerate(s["actions"])}
    linked = {l["narration_id"]: actions[(l["scene_id"], l["action_index"])] for l in links}
    # Story beats the user named: wash, inversion, sleep, chair, fridge, bottle.
    assert linked["n10a"] == "wash" and linked["n10b"] == "invert_place" and linked["n10c"] == "walk_to_bedroom"
    assert linked["n05b"] == "look_down" and linked["n14"] == "open_fridge" and linked["n15"] == "insert_close_up"


def _mutations():
    def text(ep, tl): ep["narration"][3]["text"] += " x"
    def gap(ep, tl): ep["shots"][1]["start_seconds"] += 0.1
    def camera(ep, tl): ep["shots"][1]["camera"][-1][1] = 1500
    def cut(ep, tl): ep["narration"][0]["end_seconds"] = ep["shots"][0]["end_seconds"] + 0.2
    def unlinked(ep, tl): tl["metadata"]["narration_links"].pop()
    def handle(ep, tl):
        shot = next(s for s in ep["shots"] if s["motion"]["attachments"])
        hand = shot["motion"]["actor"]["right_hand"]
        at = shot["motion"]["attachments"][0]["to"]
        next(k for k in hand if k[0] == at)[1] += 25
    def grip(ep, tl):
        shot = next(s for s in ep["shots"] if s["motion"]["prop"]["grip_seconds"] is not None)
        next(k for k in shot["motion"]["actor"]["right_hand"] if k[0] == shot["motion"]["prop"]["grip_seconds"])[2] += 20
    def action(ep, tl): tl["scenes"][2]["actions"][0]["action"] = "fly"
    return [text, gap, camera, cut, unlinked, handle, grip, action]


@pytest.mark.parametrize("mutate", _mutations(), ids=lambda f: f.__name__)
def test_invalid_episode_fails_closed(built, mutate):
    ep, tl = copy.deepcopy(built["episode"]), copy.deepcopy(built["timeline"])
    mutate(ep, tl)
    with pytest.raises(ValueError):
        validate_episode(ep, tl)


def test_walk_clip_plants_feet_and_ends_at_rest():
    clip = walk_clip(380, -28, 0, 4.7, -1)
    for foot, u in (("left_foot", -12), ("right_foot", 12)):
        assert clip["tracks"][foot][0][1] == 380 - u and clip["tracks"][foot][-1][1] == -28 - u
    assert len(clip["landings"]) >= 10
    with pytest.raises(ValueError):
        walk_clip(0, 100, 0, 3, -1)


def test_native_remotion_episode_handoff(built, tmp_path):
    result = CharacterRigRenderer().execute({"story_episode": built["episode"],
        "action_timeline": built["timeline"], "workspace_path": str(tmp_path)})
    assert result.success, result.error
    bespoke = result.data["edit_decisions"]["bespoke"]
    assert bespoke["composition_id"] == "StoryEpisode" and Path(bespoke["entry"]).is_file()
    assert (tmp_path / "shots.ts").is_file()


def test_all_frames_continuity_and_story_state(built):
    # Same pure evaluator Remotion renders; assertions encode the story's object states.
    script = r'''
const fs=require('fs'),assert=require('assert'),Module=require('module');
const ts=require('./remotion-composer/node_modules/typescript');
const load=(f,deps)=>{const code=ts.transpileModule(fs.readFileSync(f,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
  const m=new Module(f); m.require=(n)=>deps[n]; m._compile(code,f); return m.exports;};
const motion=load('tools/character/remotion/motion.ts',{});
const shots=load('tools/character/remotion/shots.ts',{'./motion':motion});
const ep=JSON.parse(fs.readFileSync(process.argv[1]));
const dist=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1]);
const idx=Object.fromEntries(ep.shots.map((s,i)=>[s.id,i]));
const release=ep.shots[idx.s07_evening_wash].start_seconds+1e-9;
let prev=null, frames=0, attached=0, wash=0, maxCup=0;
for(let f=0;f<=Math.ceil(ep.duration_seconds*ep.fps);f++){
  const t=f/ep.fps, e=shots.episodeAt(ep,t), s=e.actor, i=idx[e.shot.id]; frames++;
  for(const [a,b,len] of [[s.shoulder,s.le,65],[s.le,s.left,68],[s.shoulder,s.re,65],[s.re,s.right,68],
    [s.hip,s.lk,57],[s.lk,s.lf,58],[s.hip,s.rk,57],[s.rk,s.rf,58]]) assert(Math.abs(dist(a,b)-len)<.001,`bone ${t}`);
  if(s.held) assert(dist(s.right,s.grip)<.001,`grasp detached ${t}`);
  const [cx,cy,z]=e.camera, w=e.shot.view==='world'?[ep.world.x0,ep.world.x0+ep.world.width]:[0,1280];
  assert(cx-640/z>=w[0]-1e-6&&cx+640/z<=w[1]+1e-6&&cy-360/z>=-1e-6&&cy+360/z<=720+1e-6,`camera ${t}`);
  // Cup: in the sink (upright) before the evening; inverted on the rack after it.
  if(i<idx.s07_evening_wash) assert(dist(s.cup,[500,478])<1e-6&&s.cup[2]===0,`monday cup ${t}`);
  if(i>idx.s07_evening_wash) assert(dist(s.cup,[645,466])<1e-6&&Math.abs(s.cup[2]-180)<1e-9,`rack cup ${t}`);
  if(i===idx.s07_evening_wash&&e.mt>ep.shots[i].motion.prop.release_seconds) assert(Math.abs(s.cup[2]-180)<1e-9,'lost inversion');
  if(i===idx.s07_evening_wash&&s.water) wash++;
  // Dried ring: present on every frame until it is washed off in the evening, never after.
  const stained=e.shot.stain_until!=null&&e.mt<e.shot.stain_until;
  if(i<idx.s07_evening_wash) assert(stained,`stain missing ${t}`);
  if(i>idx.s07_evening_wash||(i===idx.s07_evening_wash&&s.water===false&&e.mt>ep.shots[i].motion.wash_window[1])) assert(!stained,`stain after wash ${t}`);
  // Chair: tucked until the next morning, pulled out from then on. Fridge closed until opened.
  assert((i<idx.s08_chair)===(e.chair[0]===0),`chair state ${t}`);
  if(i<idx.s09_fridge) assert(e.door===0,`door ${t}`);
  if(i>idx.s09_fridge) assert(Math.abs(e.door-105)<1e-9,`door stays open ${t}`);
  if(i>=idx.s09_fridge) assert(s.facing===-1,'faces the fridge');
  for(const a of e.shot.motion.attachments||[]) if(e.mt>=a.from&&e.mt<=a.to){
    attached++; assert(dist(motion.toWorld(s,s.right),shots.fridgeHandle(ep.world.fridge,e.door))<.001,`handle ${t}`);}
  if(prev&&prev.shot.id===e.shot.id){
    const d=dist(prev.actor.cup,s.cup); maxCup=Math.max(maxCup,d); assert(d<8,`cup teleport ${t}`);
    assert(dist(motion.toWorld(prev.actor,prev.actor.right),motion.toWorld(s,s.right))<16,`wrist jump ${t}`);
    assert(Math.abs(prev.door-e.door)<6,`door jump ${t}`);
  }
  prev=e;
}
assert(attached>10&&wash>60,'missing fridge grip or washing');
console.log(JSON.stringify({frames,attached,wash,maxCup}));
'''
    result = subprocess.run(["node", "-e", script, str(built["path"])], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["frames"] == round(built["episode"]["duration_seconds"] * 30) + 1


@pytest.mark.parametrize("recipe", sorted(RECIPES))
def test_procedural_sfx_recipes_are_non_silent(recipe, tmp_path):
    result = ProceduralSFX().execute({"recipe": recipe, "duration_seconds": 0.5, "output_path": str(tmp_path / "x.wav")})
    assert result.success, result.error
    assert abs(result.data["audio_duration_seconds"] - 0.5) < 0.01


def test_procedural_sfx_rejects_unknown_recipe(tmp_path):
    assert not ProceduralSFX().execute({"recipe": "scream", "duration_seconds": 1,
                                        "output_path": str(tmp_path / "x.wav")}).success
