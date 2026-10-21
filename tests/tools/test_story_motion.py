"""Contact and continuity acceptance tests for the authored pilot, not just schemas."""
import json
import subprocess
from pathlib import Path

import pytest

from tools.character.character_animation import ActionTimelineCompiler, CharacterRigRenderer
from tools.character.story_motion import validate_motion

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "examples/story-to-action"


def pilot():
    motion = json.loads((FIXTURE / "pilot.motion.json").read_text())
    for key in ("background_svg", "foreground_svg"):
        motion[key] = str(ROOT / motion[key])
    actions = json.loads((FIXTURE / "pilot.actions.json").read_text())
    timeline = {"version": "1.0", "fps": 30, "scenes": [{"scene_id": "kitchen",
                "start_seconds": 0, "end_seconds": motion["duration_seconds"], "actions": actions}]}
    return motion, timeline


def test_explicit_actions_survive_compilation():
    motion, timeline = pilot()
    actions = timeline["scenes"][0]["actions"]
    result = ActionTimelineCompiler().execute({"character_ids": ["minh"],
        "scene_plan": {"scenes": [{"id": "kitchen", "start_seconds": 0,
                        "end_seconds": motion["duration_seconds"]}]},
        "timed_actions": {"kitchen": actions}})
    assert result.success, result.error
    assert result.data["action_timeline"]["scenes"][0]["actions"] == actions


@pytest.mark.parametrize("kind", ["bounds", "entity", "unknown", "keys", "attachment", "missing_action"])
def test_invalid_motion_fails_closed(kind):
    motion, timeline = pilot()
    if kind == "bounds": timeline["scenes"][0]["actions"][0]["duration_seconds"] = 100
    if kind == "entity": timeline["scenes"][0]["actions"][0]["target"] = "other-cup"
    if kind == "unknown": timeline["scenes"][0]["actions"][0]["action"] = "fly"
    if kind == "keys": motion["prop"]["track"][1][0] = float("nan")
    if kind == "attachment": motion["actor"]["right_hand"][3][1] += 30
    if kind == "missing_action": timeline["scenes"][0]["actions"].pop()
    with pytest.raises(ValueError): validate_motion(motion, timeline)


def test_native_remotion_handoff(tmp_path):
    motion, timeline = pilot()
    result = CharacterRigRenderer().execute({"story_motion": motion,
        "action_timeline": timeline, "workspace_path": str(tmp_path)})
    assert result.success, result.error
    edit = result.data["edit_decisions"]
    assert edit["render_runtime"] == "remotion"
    assert Path(edit["bespoke"]["entry"]).is_file()


def test_rendered_skeleton_all_frames_has_contact_and_continuity():
    # Execute the SAME pure frame evaluator that Remotion renders; no duplicate
    # Python animator or wall-clock approximation is used by the assertions.
    script = r'''
const fs = require('fs'), assert = require('assert'), Module = require('module');
const ts = require('./remotion-composer/node_modules/typescript');
const code = ts.transpileModule(fs.readFileSync('tools/character/remotion/motion.ts','utf8'),
  {compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
const mod = new Module('motion'); mod._compile(code, 'motion.js');
const {stateAt} = mod.exports;
const m = JSON.parse(fs.readFileSync('examples/story-to-action/pilot.motion.json'));
const dist=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1]);
let previous, washX=[], planted=0, maxCupDelta=0;
for(let frame=0;frame<=Math.ceil(m.duration_seconds*m.fps);frame++) {
 const t=frame/m.fps;
 let s; try {s=stateAt(m,t);} catch(e) {throw new Error(`Frame ${frame} (${t}s): ${e.message}`);}
 for(const [a,b,len] of [[s.shoulder,s.le,65],[s.le,s.left,68],[s.shoulder,s.re,65],
   [s.re,s.right,68],[s.hip,s.lk,57],[s.lk,s.lf,58],[s.hip,s.rk,57],[s.rk,s.rf,58]]) {
   assert(Math.abs(dist(a,b)-len)<.001,'bone length changed');
 }
 if(s.held) assert(dist(s.right,s.grip)<.001,'grasp detached');
 if(t>m.prop.release_seconds) {
   assert(dist(s.cup,[645,466])<.001,'released cup moved');
   assert(Math.abs(s.cup[2]-180)<.001,'cup lost inversion');
 }
 if(s.water) washX.push(s.left[0]);
 if(previous) {
   const delta=dist(previous.cup,s.cup); maxCupDelta=Math.max(maxCupDelta,delta);
   assert(delta<8,'prop teleported');
   assert(dist(previous.left,s.left)<14 && dist(previous.right,s.right)<14,'wrist jumped');
   if(t>11.5&&t<17.8&& (dist(previous.lf,s.lf)<.001 || dist(previous.rf,s.rf)<.001)) planted++;
 }
 previous=s;
}
assert(Math.max(...washX)-Math.min(...washX)>10,'washing hand is frozen');
assert(planted>100,'walking lacks planted foot contacts');
// Seeking out of order must produce byte-identical state.
assert.deepStrictEqual(stateAt(m,8),stateAt(m,8));
console.log(JSON.stringify({frames:Math.ceil(m.duration_seconds*m.fps)+1,planted,maxCupDelta}));
'''
    result = subprocess.run(["node", "-e", script], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["frames"] == 556
