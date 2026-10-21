"""Story-to-video M1: analysis, planning and fail-closed validation on unseen stories."""
import copy
import json
import re
import wave
from pathlib import Path

import pytest

from tools.audio.procedural_sfx import ProceduralSFX
from tools.character.story_video import validate_story_video
from tools.story import story_analyzer as SA
from tools.story.story_planner import plan_story

ROOT = Path(__file__).resolve().parents[2]
STORIES = ROOT / "examples/story-to-video/stories"
# Written for this test only: names, rooms and props that no source file mentions.
INLINE = """# The Parcel

Mai walked into the kitchen and put the box on the table. She sat on the stool and read a letter.

Tom knocked on the door. Mai stood up, opened the door and gave him the box. "Thank you," he said.
Tom waved and left.
"""


def _silent(path: Path, seconds: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1); out.setsampwidth(2); out.setframerate(24000)
        out.writeframes(b"\0\0" * int(seconds * 24000))


def _build(path: Path, tmp: Path):
    analysis = SA.analyze_story(path, backend="rules")
    narration = {}
    for b in analysis["beats"]:
        d = max(1.0, len(b["text"]) / 14)
        wav = tmp / "audio" / f"{b['id']}.wav"
        _silent(wav, d)
        narration[b["id"]] = {"path": str(wav), "duration_seconds": d}
    video, timeline = plan_story(analysis, narration)
    for i, cue in enumerate(video["sfx"]):  # silent stand-ins with the planned length
        wav = tmp / "sfx" / f"{i}.wav"
        _silent(wav, 0.1)
        video["sfx"][i] = {"id": f"c{i}", "path": str(wav), "start_seconds": cue["t"],
                           "duration_seconds": cue["duration"], "volume": cue["volume"]}
    return analysis, video, timeline


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    inline = tmp_path_factory.mktemp("inline") / "parcel.md"
    inline.write_text(INLINE, encoding="utf-8")
    out = {}
    for name, path in (("vi", STORIES / "chiec-o-mau-vang.vi.md"), ("en", STORIES / "the-last-loaf.en.md"),
                       ("inline", inline)):
        out[name] = _build(path, tmp_path_factory.mktemp(name))
    return out


def test_segmentation_reproduces_source_and_keeps_quotes_whole():
    story = SA.load_story(STORIES / "the-last-loaf.en.md")
    segs = SA.segment_story(story)
    assert " ".join(s["text"] for s in segs) == " ".join(story["paragraphs"])
    assert '"Are you open?" she asked.' in [s["text"] for s in segs]
    vi_story = SA.load_story(STORIES / "chiec-o-mau-vang.vi.md")
    vi = SA.segment_story(vi_story)
    # A quotation with two sentences stays inside one segment.
    quote = re.search(r':\s*("[^"]+\.[^"]+")', " ".join(vi_story["paragraphs"])).group(1)
    assert any(s["text"].endswith(quote) for s in vi)
    assert SA.detect_language(" ".join(s["text"] for s in vi)) == "vi"


def test_rule_analysis_finds_cast_rooms_and_actions(built):
    vi, en, inline = built["vi"][0], built["en"][0], built["inline"][0]
    assert {c["id"] for c in vi["characters"]} == {"lan", "ong-cu"}
    assert {l["id"] for l in vi["locations"]} == {"office", "street", "living_room"}
    assert {c["id"] for c in en["characters"]} == {"ben", "girl"}
    assert next(c for c in en["characters"] if c["id"] == "girl")["age"] == "child"
    acts = {(a["character_id"], a["action"]) for b in inline["beats"] for a in b["actions"]}
    assert {("mai", "put_down"), ("mai", "sit"), ("mai", "read"), ("tom", "knock"), ("mai", "give"),
            ("tom", "talk"), ("tom", "wave"), ("tom", "exit")} <= acts
    give = next(a for b in inline["beats"] for a in b["actions"] if a["action"] == "give")
    assert give["target"] == {"type": "character", "id": "tom"}
    # Actor of a clause comes from its own subject, not the previous sentence.
    board = next(a for b in vi["beats"] for a in b["actions"] if a["action"] == "board")
    assert board["character_id"] == "ong-cu"


def test_no_story_content_is_hardcoded_in_pipeline_source():
    # Character names of every story built so far, plus the story-specific props of the pilot.
    names = {"Lan", "lan", "ong-cu", "Ben", "ben", "Minh", "minh", "Mai", "mai", "Tom", "tom", "fridge"}
    for path in [*(ROOT / "tools/story").glob("*.py"), ROOT / "tools/character/story_video.py",
                 ROOT / "tools/character/remotion/StoryVideo.tsx", ROOT / "scripts/story_to_video.py"]:
        words = set(re.findall(r"[\w-]+", path.read_text(encoding="utf-8")))
        assert not names & words, (path.name, names & words)


@pytest.mark.parametrize("name", ["vi", "en", "inline"])
def test_plans_validate_on_every_frame(built, name):
    _, video, timeline = built[name]
    counters = validate_story_video(video, timeline)
    assert counters["frames_checked"] >= int(video["duration_seconds"] * video["fps"])
    assert counters["narration"] == len(video["narration"])
    assert not [n for n in video["planner_notes"] if "skipped" in n]


def test_inline_story_props_follow_hands(built):
    _, video, _ = built["inline"]
    holds = [h for s in video["shots"] for it in s["items"] for h in it["holds"] if it["id"] == "box"]
    assert {h["actor"] for h in holds} == {"mai", "tom"}  # handed over, never teleported


def _mutations():
    def text(v, tl): v["narration"][2]["text"] += " x"
    def gap(v, tl): v["shots"][2]["start_seconds"] += 0.1
    def camera(v, tl): v["shots"][1]["camera"][-1][1] = 1200
    def reach(v, tl):
        a = next(a for s in v["shots"] for a in s["actors"])
        a["right_hand"][-1][1] += 300
    def hand(v, tl):
        it = next(it for s in v["shots"] for it in s["items"] if it["holds"])
        h = it["holds"][0]
        for k in it["track"]:
            if h["from"] <= k[0] <= h["to"]:
                k[2] += 30
    def unlinked(v, tl): tl["metadata"]["narration_links"].pop()
    def cut(v, tl): v["narration"][0]["end_seconds"] = v["shots"][1]["end_seconds"] + 0.5
    return [text, gap, camera, reach, hand, unlinked, cut]


@pytest.mark.parametrize("mutate", _mutations(), ids=lambda f: f.__name__)
def test_invalid_plan_fails_closed(built, mutate):
    _, video, timeline = built["vi"]
    v, tl = copy.deepcopy(video), copy.deepcopy(timeline)
    mutate(v, tl)
    with pytest.raises(ValueError):
        validate_story_video(v, tl)


def test_llm_labels_are_grounded_and_never_override_rules(built):
    analysis = copy.deepcopy(built["vi"][0])
    empty = next(b for b in analysis["beats"] if not b["actions"] and "ai" not in b["text"].lower())
    with_rule = next(b for b in analysis["beats"] if b["actions"])
    llm = {"characters": [{"name": "Lan", "gender": "female", "age": "adult"}],
           "segments": [{"id": empty["id"], "location": "office", "actions": [
                            {"actor": "Lan", "action": "exit"},          # Lan is not in that sentence
                            {"actor": "none", "action": "vehicle_arrive"}]},
                        {"id": with_rule["id"], "location": "office", "actions": [
                            {"actor": "Lan", "action": "fly"}]}]}
    merged, report = SA.merge_llm(analysis, llm, "vi")
    beat = next(b for b in merged["beats"] if b["id"] == empty["id"])
    assert [a["action"] for a in beat["actions"]] == ["vehicle_arrive"]
    assert report["ungrounded_actions"] == 1 and report["rejected_actions"] == 1
    assert next(b for b in merged["beats"] if b["id"] == with_rule["id"])["actions"] == with_rule["actions"]


def test_auto_backend_falls_back_to_rules_without_ollama():
    analysis = SA.analyze_story(STORIES / "the-last-loaf.en.md", backend="auto", endpoint="http://127.0.0.1:9")
    assert analysis["analyzer"]["backend"] == "rules" and "not reachable" in analysis["analyzer"]["note"]
    with pytest.raises(RuntimeError):
        SA.analyze_story(STORIES / "the-last-loaf.en.md", backend="ollama", endpoint="http://127.0.0.1:9")


@pytest.mark.parametrize("recipe", ["rain", "street_ambience", "knock", "door_open", "engine", "paper", "switch",
                                    "soft_place"])
def test_new_sfx_recipes_are_audible(tmp_path, recipe):
    res = ProceduralSFX().execute({"recipe": recipe, "duration_seconds": 0.4, "output_path": str(tmp_path / "a.wav")})
    assert res.success, res.error


# ---------------------------------------------------------------------------
# Quality regressions (M1 review): staging, proportions, prop/face, hand-over,
# boarding, sitting, close-ups. Each test targets one failure class seen in an MP4.
# ---------------------------------------------------------------------------
from tools.character.story_video import head_center  # noqa: E402
from tools.story.story_planner import CHILD_SCALE, SIT_Y, VEHICLE, sample, step  # noqa: E402


def _shot(video, pred):
    return next(s for s in video["shots"] if pred(s))


def _actions(timeline, name, who=None):
    return [(sc, a) for sc in timeline["scenes"] for a in sc["actions"]
            if a["action"] == name and (who is None or a["character_id"] == who)]


def test_child_is_drawn_smaller_than_adults(built):
    _, video, _ = built["en"]
    shot = _shot(video, lambda s: {a["id"] for a in s["actors"]} == {"ben", "girl"})
    girl = next(a for a in shot["actors"] if a["id"] == "girl")
    ben = next(a for a in shot["actors"] if a["id"] == "ben")
    assert girl["scale"] == CHILD_SCALE and ben["scale"] == 1.0
    height = lambda a: 620 - (head_center(a, 0.0)[1] - 50 * a["scale"])  # noqa: E731
    assert 0.65 < height(girl) / height(ben) < 0.8


def test_overlapping_people_fail_validation(built):
    _, video, timeline = built["en"]
    v = copy.deepcopy(video)
    shot = _shot(v, lambda s: len(s["actors"]) >= 2 and not s["contacts"])
    a, b = shot["actors"][0], shot["actors"][1]
    for limb in ("root", "left_hand", "right_hand", "left_foot", "right_foot"):
        b[limb] = [[k[0], k[1] + 8, k[2]] for k in a[limb]]  # b stands inside a
    b["facing_keys"], b["scale"], b["opacity"] = a["facing_keys"], 1.0, [[0, 1], [shot["end_seconds"] - shot["start_seconds"], 1]]
    with pytest.raises(ValueError, match="overlap"):
        validate_story_video(v, timeline)


def test_umbrella_is_raised_from_the_first_frame_and_never_covers_a_face(built):
    _, video, timeline = built["vi"]
    rainy = [s for s in video["shots"] if s["weather"] == "rain" and s["location"] == "street"]
    checked = 0
    for shot in rainy:
        for it in shot["items"]:
            if it["kind"] == "umbrella" and step(it["held"], 0.0) > 0:
                holder = next(a for a in shot["actors"] if a["id"] == it["holds"][0]["actor"])
                _, face_y, face_r = head_center(holder, 0.0)
                assert sample(it["track"], 0.0)[1] - 128 < face_y - face_r  # canopy rim above the face
                checked += 1
    assert checked >= 2
    v = copy.deepcopy(video)
    shot = _shot(v, lambda s: any(i["kind"] == "umbrella" and step(i["open"], 1.0) > 0.5 for i in s["items"]))
    it = next(i for i in shot["items"] if i["kind"] == "umbrella")
    it["track"] = [[k[0], k[1], k[2] + 110, k[3]] for k in it["track"]]  # canopy dropped to face height
    it["holds"] = []
    with pytest.raises(ValueError, match="covers"):
        validate_story_video(v, timeline)


def test_hand_over_is_a_shared_hold_framed_close(built):
    for name in ("en", "inline"):
        _, video, timeline = built[name]
        (scene, give), = _actions(timeline, "give")
        shot = _shot(video, lambda s: s["id"] == scene["scene_id"])
        contact = shot["contacts"][0]
        item = next(i for i in shot["items"] if len(i["holds"]) >= 2 and
                    {h["actor"] for h in i["holds"]} == {contact["a"], contact["b"]})
        handover = next(h for h in item["holds"] if h["actor"] == contact["b"])["from"]
        giver = next(a for a in shot["actors"] if a["id"] == contact["a"])
        taker = next(a for a in shot["actors"] if a["id"] == contact["b"])
        g_hand = next(h["hand"] for h in item["holds"] if h["actor"] == contact["a"])
        t_hand = next(h["hand"] for h in item["holds"] if h["actor"] == contact["b"])
        for t in (handover - 0.45, handover):  # both hands on the item for the shared hold
            assert abs(sample(giver[g_hand], t)[0] - sample(taker[t_hand], t)[0]) < 1.0
        gap = abs(sample(giver["root"], handover)[0] - sample(taker["root"], handover)[0])
        assert 95 < gap < 130
        assert sample(shot["camera"], handover)[2] >= 1.6


def test_boarding_steps_in_and_rides_away(built):
    _, video, timeline = built["vi"]
    (scene, board), = _actions(timeline, "board")
    shot = _shot(video, lambda s: s["id"] == scene["scene_id"])
    bus = shot["vehicles"][0]
    rider = next(a for a in shot["actors"] if a["id"] == board["character_id"])
    t_in = next(k[0] for k in rider["layer"] if k[1] == 1)
    door_x = sample(bus["track"], t_in)[0] + VEHICLE["bus"]["door_dx"]
    assert abs(sample(rider["root"], t_in)[0] - door_x) < 2          # at the door when stepping in
    assert sample(rider["root"], t_in)[1] < sample(rider["root"], t_in - 0.4)[1] - 20  # stepped up
    assert sample(rider["opacity"], t_in + 1.0)[0] == 1.0            # still visible inside
    t_go = bus["track"][-2][0]
    assert step(bus["door"], t_go) == 0.0 or sample(bus["door"], t_go)[0] < 0.05  # door shut first
    offsets = [sample(rider["root"], t)[0] - sample(bus["track"], t)[0]
               for t in (t_go, (t_go + bus["track"][-1][0]) / 2, bus["track"][-1][0])]
    assert max(offsets) - min(offsets) < 0.5                         # rides with the bus


def test_sitting_plants_feet_touches_seat_and_rests_on_it(built):
    _, video, timeline = built["vi"]
    for scene, sit in _actions(timeline, "sit"):
        shot = _shot(video, lambda s: s["id"] == scene["scene_id"])
        a = next(x for x in shot["actors"] if x["id"] == sit["character_id"])
        t0 = sit["at_seconds"] - shot["start_seconds"]
        t1 = t0 + sit["duration_seconds"] + 0.01  # float slack from global->local
        root_end = sample(a["root"], t1)
        assert abs(root_end[1] - SIT_Y) < 1.0                       # pelvis on the 556 seat
        final = sample(a["left_foot"], t1)[0]
        keys = [k for k in a["left_foot"] if t0 <= k[0] <= t1]
        t_plant = next(k[0] for i, k in enumerate(keys) if all(abs(q[1] - final) < 0.5 for q in keys[i:]))
        t_seated = next(k[0] for k in a["root"] if t0 <= k[0] <= t1 and abs(k[2] - SIT_Y) < 1)
        assert t_seated - t_plant >= 0.6                            # feet planted before the hips go down
        hands = [min(abs(sample(a[h], t)[1] - 550) for h in ("left_hand", "right_hand"))
                 for t in [k[0] for k in a["root"] if t0 <= k[0] <= t1]]
        assert min(hands) < 3.0                                     # a hand on the seat edge


def test_small_and_written_items_get_close_ups(built):
    _, video, timeline = built["vi"]
    (scene, rev), = [x for x in _actions(timeline, "reveal") if x[1]["target"] == "letter"]
    shot = _shot(video, lambda s: s["id"] == scene["scene_id"])
    t0 = rev["at_seconds"] - shot["start_seconds"]
    zooms = [sample(shot["camera"], t0 + i * 0.1)[2] for i in range(80)]
    assert max(zooms) >= 3.0
    ins = shot["inserts"][0]
    assert ins["kind"] == "letter" and ins["end"] - ins["start"] >= 2.5
    assert ins["text"] in " ".join(n["text"] for n in video["narration"])  # the story's own words
    _, video_en, timeline_en = built["en"]
    (scene, coin), = [x for x in _actions(timeline_en, "reveal") if x[1]["target"] == "coin"]
    shot = _shot(video_en, lambda s: s["id"] == scene["scene_id"])
    t0 = coin["at_seconds"] - shot["start_seconds"]
    assert max(sample(shot["camera"], t0 + i * 0.1)[2] for i in range(60)) >= 3.0


def test_item_used_without_placement_is_hidden_until_it_appears(built):
    _, video, _ = built["en"]
    for shot in video["shots"]:
        for it in shot["items"]:
            if it["id"] == "tray":
                assert sample(it["visible"], 0.0)[0] == 0.0
                assert sample(it["visible"], it["holds"][0]["from"] - 0.05)[0] == 0.0


def test_pointing_arm_does_not_cross_another_person(built):
    _, video, timeline = built["en"]
    (scene, point), = _actions(timeline, "point")
    shot = _shot(video, lambda s: s["id"] == scene["scene_id"])
    t = point["at_seconds"] - shot["start_seconds"] + 0.6 * point["duration_seconds"]
    me = next(a for a in shot["actors"] if a["id"] == point["character_id"])
    for other in shot["actors"]:
        if other is not me:
            hand_x = max((sample(me[h], t)[0] for h in ("left_hand", "right_hand")),
                         key=lambda x: abs(x - sample(me["root"], t)[0]))
            assert abs(hand_x - sample(other["root"], t)[0]) > 40


def test_walking_through_someone_on_the_same_lane_fails(tmp_path, monkeypatch):
    """With the depth lane disabled the planner would walk people through each other."""
    import tools.story.story_planner as planner
    analysis, video, timeline = _build(STORIES / "the-last-loaf.en.md", tmp_path / "lane")
    assert any("passes behind" in n for n in video["planner_notes"])
    validate_story_video(video, timeline)
    monkeypatch.setattr(planner, "DEPTH_LANE", 0.0)
    _, flat, flat_tl = _build(STORIES / "the-last-loaf.en.md", tmp_path / "flat")
    with pytest.raises(ValueError, match="overlap"):
        validate_story_video(flat, flat_tl)


def test_m1_umbrella_grip_is_rejected(tmp_path, monkeypatch):
    """The M1 grip (hand at chest, shaft through the face) must not pass validation."""
    import tools.story.story_planner as planner
    monkeypatch.setattr(planner, "UMBRELLA_UP", (24, -66))
    _, video, timeline = _build(STORIES / "chiec-o-mau-vang.vi.md", tmp_path)
    with pytest.raises(ValueError, match="covers"):
        validate_story_video(video, timeline)


def test_items_never_rest_on_top_of_each_other(built):
    for name in ("vi", "en", "inline"):
        _, video, _ = built[name]
        for shot in video["shots"]:
            length = shot["end_seconds"] - shot["start_seconds"]
            for i in range(int(length * 10) + 1):
                t = min(length, i / 10)
                resting = [sample(it["track"], t) for it in shot["items"]
                           if sample(it["visible"], t)[0] > 0.5 and step(it["held"], t) == 0]
                for a_i, p in enumerate(resting):
                    for q in resting[a_i + 1:]:
                        assert not (abs(p[0] - q[0]) < 30 and abs(p[1] - q[1]) < 30), (name, shot["id"], t)
