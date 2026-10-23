"""P3.2A asset library: registry, anchors, lighting geometry, presets and bindings."""
import copy
from functools import partial
import json
from pathlib import Path
import subprocess

import pytest

from tools.character import horror_assets as lib
from tools.character.asset_library_demo import (AUDIO_RECIPES, STORY_A_BINDING, STORY_B_BINDING, build_environment_still,
                                                build_pose_reel, build_story_a, build_story_b)
from tools.character.cartoon_horror_preview import build_cinematic_preview
from tools.character.character_animation import CharacterRigRenderer
from tools.character.horror_acting import ActorBuilder
from tools.character.horror_environments import door_handle
from tools.character.story_video import validate_story_video

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def audio(tmp_path):
    wav = tmp_path / "fixture.wav"
    wav.write_bytes(b"synthetic")
    return {recipe: wav for recipe, _ in AUDIO_RECIPES}


def test_manifest_ids_revisions_and_hashes_are_stable():
    first, second = lib.manifest(), lib.manifest()
    assert first == second
    keys = [(a["kind"], a["id"]) for a in first["assets"]]
    assert len(keys) == len(set(keys))
    assert all(type(a["revision"]) is int and a["revision"] >= 1 and len(a["sha256"]) == 64 for a in first["assets"])
    kinds = {a["kind"] for a in first["assets"]}
    assert kinds == {"rig", "character", "silhouette", "prop", "environment", "acting", "lighting"}


def test_revision_pin_fails_closed():
    with pytest.raises(ValueError):
        lib.get("character", "nora_vale", 2)
    with pytest.raises(ValueError):
        lib.get("environment", "haunted_castle")


@pytest.mark.parametrize("kind,asset_id", [(a["kind"], a["id"]) for a in lib.manifest()["assets"]])
def test_stored_revision_rejects_silent_content_change(kind, asset_id, monkeypatch):
    original = lib.get(kind, asset_id, 1)
    assert lib.content_hash(original) == lib.REVISION_HASHES[kind, asset_id, 1]
    altered = copy.deepcopy(original)
    if kind == "environment":
        builder = original["builder"]
        def moved_anchor():
            env = builder()
            env["features"]["doors"][0]["handle"][0] += 1
            return env
        altered["builder"] = moved_anchor
    elif kind == "character":
        altered["design"]["palette"]["top"] = "#111111"
    else:
        altered["summary"] = "Changed without a new revision"
    monkeypatch.setitem(lib.REGISTRIES[kind], asset_id, altered)
    for read in (lambda: lib.get(kind, asset_id, 1), lib.manifest,
                 lambda: lib.resolve_binding(STORY_A_BINDING)):
        with pytest.raises(ValueError, match="content hash mismatch"):
            read()


def test_registry_reads_do_not_expose_mutable_definitions():
    before = lib.manifest()
    lib.get("character", "nora_vale", 1)["design"]["palette"]["skin"] = "#000000"
    lib.character_look("victor_hale", 1)["design"]["build"]["head"] = 2
    lib.environment("old_apartment_room", 1)["features"]["doors"][0]["handle"][0] = 0
    assert lib.manifest() == before


@pytest.mark.parametrize("bad", [None, True, 1.0, "1", 0, -1, 2])
@pytest.mark.parametrize("ref", ["character", "environment", "lighting", "silhouette"])
def test_binding_revisions_are_required_positive_integer_pins(bad, ref):
    binding = copy.deepcopy(STORY_B_BINDING)
    refs = {"character": binding["cast"]["resident"], "environment": binding["locations"]["hall"],
            "lighting": binding["locations"]["hall"]["lighting"], "silhouette": binding["locations"]["hall"]["presence"]}
    refs[ref]["revision"] = bad
    with pytest.raises(ValueError):
        lib.validate_binding(binding)


@pytest.mark.parametrize("mutation", ["no_light", "light_extra", "presence_extra", "null_presence", "empty_id",
                                     "null_cast", "wrong_feature", "bad_lamp", "ignored_lamp", "missing_anchor"])
def test_invalid_nested_bindings_fail_clearly(mutation):
    binding = copy.deepcopy(STORY_B_BINDING)
    loc = binding["locations"]["hall"]
    if mutation == "no_light": del loc["lighting"]
    if mutation == "light_extra": loc["lighting"]["fallback"] = "room"
    if mutation == "presence_extra": loc["presence"]["fallback"] = "window"
    if mutation == "null_presence": loc["presence"] = None
    if mutation == "empty_id": binding["story_id"] = " "
    if mutation == "null_cast": binding["cast"] = None
    if mutation == "wrong_feature": loc["lighting"] = {"id": "cold_moonlight", "revision": 1}
    if mutation == "bad_lamp": loc["lighting"]["flicker_lamp"] = "floor_lamp"
    if mutation == "ignored_lamp": loc["lighting"]["id"] = "dim_corridor"
    if mutation == "missing_anchor": del loc["presence"]["anchor"]
    with pytest.raises(ValueError):
        lib.validate_binding(binding)


@pytest.mark.parametrize("mutation", ["appearance", "costume", "anchor", "geometry", "missing_geometry", "skin"])
def test_renderer_rejects_drift_from_pinned_binding(audio, tmp_path, mutation):
    video, timeline = build_story_a(audio)
    # Break aliasing between shots so a single-shot continuity defect is exercised.
    video["shots"][1]["actors"][0]["look"] = copy.deepcopy(video["shots"][1]["actors"][0]["look"])
    if mutation == "appearance": video["shots"][1]["actors"][0]["look"]["design"]["face"]["outline"] += " Z"
    if mutation == "costume": video["shots"][1]["actors"][0]["look"]["design"]["outfit"] = "cardigan"
    if mutation == "anchor": video["locations"]["flat"]["anchors"]["doors"][0]["handle"][0] += 1
    if mutation == "geometry": video["locations"]["flat"]["cinematic"]["seams"][0]["x0"] += 1
    if mutation == "missing_geometry": del video["locations"]["flat"]["cinematic"]
    if mutation == "skin": video["character_skin"] = "cartoon"
    result = CharacterRigRenderer().execute({"story_video": video, "action_timeline": timeline,
                                            "workspace_path": str(tmp_path / "invalid")})
    assert not result.success and "Asset binding" in result.error
    assert not (tmp_path / "invalid").exists()


def test_characters_differ_beyond_shirt_color():
    nora, victor = (lib.CHARACTERS[c]["design"] for c in ("nora_vale", "victor_hale"))
    for path in (("face", "outline"), ("hair", "front"), ("face", "eyes", "shape"), ("outfit",), ("footwear",)):
        a, b = nora, victor
        for key in path:
            a, b = a[key], b[key]
        assert a != b, path
    assert nora["build"]["shoulder"] < victor["build"]["shoulder"] and nora["build"]["head"] != victor["build"]["head"]
    assert "back" in nora["hair"] and "back" not in victor["hair"]
    assert lib.CHARACTERS["nora_vale"]["rest_posture"] != lib.CHARACTERS["victor_hale"]["rest_posture"]


def test_library_rejects_unsafe_character_data():
    original = copy.deepcopy(lib.CHARACTERS["victor_hale"])
    try:
        lib.CHARACTERS["victor_hale"]["rest_posture"] = [8, -160, 15, -157]
        with pytest.raises(ValueError):
            lib.check_library()
        lib.CHARACTERS["victor_hale"] = copy.deepcopy(original)
        lib.CHARACTERS["victor_hale"]["design"]["palette"]["top"] = "olive"
        with pytest.raises(ValueError):
            lib.check_library()
    finally:
        lib.CHARACTERS["victor_hale"] = original
    lib.check_library()


@pytest.mark.parametrize("env_id", sorted(lib.ENVIRONMENTS))
def test_environment_anchors_are_explicit_and_coherent(env_id):
    env = lib.environment(env_id)
    assert env == lib.environment(env_id)
    assert "<image" not in env["svg"] and "http" not in env["svg"].replace("http://www.w3.org/2000/svg", "")
    f = env["features"]
    assert f["floor_y"] == 620 and 0 <= f["walk_range"][0] < f["walk_range"][1] <= 1280
    interactive = [d for d in f["doors"] if d["interactive"]]
    assert interactive and interactive[0]["rect"] == env["door"]
    for door in f["doors"]:
        r = door["rect"]
        assert door["handle"] == door_handle(r) and r["y"] + r["h"] == f["floor_y"]
        assert door["seam"][2] == f["floor_y"] - 1 and r["x"] < door["seam"][0] < door["seam"][1] < r["x"] + r["w"]
    for w in f["windows"]:
        r = w["rect"]
        assert all(r["x"] <= x <= r["x"] + r["w"] and r["y"] <= y <= r["y"] + r["h"] for pane in w["panes"] for x, y in pane)
    for a in f["presence_anchors"].values():
        assert all(0 <= x <= 1280 and 0 <= y <= 720 for poly in a["clip"] for x, y in poly)
    assert all(0 <= x <= 1280 and 0 <= y <= 720 for x, y in f["props"].values())


def test_lighting_presets_follow_environment_features():
    room, hall = lib.environment("old_apartment_room"), lib.environment("dark_apartment_corridor")
    moon = lib.lighting_geometry(room, "cold_moonlight", presence=("window", "featureless_figure"))
    w = room["window"]
    assert moon["beams"][0]["points"][0][0] == w["x"] and moon["beams"][0]["points"][1][0] == w["x"] + w["w"]
    assert moon["presence"]["clip"] == room["features"]["presence_anchors"]["window"]["clip"]
    flick = lib.lighting_geometry(hall, "flickering_interior", flicker_lamp="lamp_mid",
                                  presence=("corridor_end", "tall_hooded"))
    assert [l["driver"] for l in flick["lamps"]] == ["constant", "flicker", "constant"]
    assert [(l["x"], l["y"]) for l in flick["lamps"]] == [(l["x"], l["y"]) for l in hall["features"]["lamps"]]
    assert flick["presence"]["y"] + 62 * flick["presence"]["scale"] == pytest.approx(620)
    for bad in (lambda: lib.lighting_geometry(hall, "cold_moonlight"),
                lambda: lib.lighting_geometry(hall, "flickering_interior", flicker_lamp="lamp_attic"),
                lambda: lib.lighting_geometry(room, "dim_corridor", presence=("corridor_end", "tall_hooded"))):
        with pytest.raises(ValueError):
            bad()
    track = lib.flicker_track(10, [3.7, 4.3])
    assert track == lib.flicker_track(10, [4.3, 3.7]) and all(a[0] < b[0] for a, b in zip(track, track[1:]))


@pytest.mark.parametrize("mutation", ["point", "color", "driver", "flicker_track", "no_horror", "extra_key",
                                      "version", "clip", "presence_scale"])
def test_invalid_geometry_fails_validation(audio, mutation):
    video, timeline = build_story_b(audio)
    g = video["locations"]["hall"]["cinematic"]
    if mutation == "point": g["beams"][0]["points"][2] = [1500, 620]
    if mutation == "color": g["lamps"][0]["color"] = "yellow"
    if mutation == "driver": g["pools"][0]["driver"] = "strobe"
    if mutation == "flicker_track": del video["horror"]["flicker"]
    if mutation == "no_horror": del video["horror"]
    if mutation == "extra_key": g["room"] = "p31-preview"
    if mutation == "version": g["version"] = 2
    if mutation == "clip": g["presence"]["clip"] = [[[1010, 240], [1170, 240]]]
    if mutation == "presence_scale": g["presence"]["scale"] = float("nan")
    with pytest.raises(ValueError):
        validate_story_video(video, timeline)


def test_legacy_packages_without_geometry_still_validate(tmp_path, monkeypatch):
    wav = tmp_path / "fixture.wav"
    wav.write_bytes(b"synthetic")
    video, timeline = build_cinematic_preview(dict.fromkeys(("room_tone", "furniture_scrape", "footstep", "door_open"), wav))
    assert "cinematic" not in video["locations"]["preview-room"]
    def unavailable(*args, **kwargs):
        raise AssertionError("Legacy packages must not use the registry")
    monkeypatch.setattr(lib, "resolve_binding", unavailable)
    validate_story_video(video, timeline)


def test_acting_presets_are_deterministic_and_keep_contact():
    look = lib.character_look("nora_vale")

    def perform():
        return (ActorBuilder("a", look, 690, rest_posture=[5, -99, 10, -160]).hold(.2)
                .cautious_walk(770, .2, 2.6).listening_freeze(2.6, 3.4).guarded_reach([836, 420], 3.4, 4.6)).build(5)
    first = perform()
    assert first == perform()
    from tools.character.story_video import _sample
    for limb in ("root", "left_foot", "right_foot"):
        assert _sample(first[limb], 2.65) == _sample(first[limb], 3.4) == _sample(first[limb], 5)
    assert _sample(first["right_hand"], 4.6) == [836, 420] == _sample(first["right_hand"], 5)


def test_acting_presets_fail_closed():
    look = lib.character_look("victor_hale")
    with pytest.raises(ValueError, match="unreachable"):
        ActorBuilder("b", look, 400, rest_posture=[8, -96, 15, -157]).guarded_reach([656, 420], 0, 1)
    with pytest.raises(ValueError, match="cautious"):
        ActorBuilder("b", look, 200, rest_posture=[8, -96, 15, -157]).cautious_walk(500, 0, 2)
    with pytest.raises(ValueError):
        ActorBuilder("b", look, 200, rest_posture=[8, -96, 15, -157]).hold(2).listening_freeze(1, 3)


def test_bindings_pin_assets_and_reject_ambiguity():
    lib.validate_binding(STORY_A_BINDING)
    for change in ("version", "revision", "duplicate_role", "anchor", "extra"):
        binding = copy.deepcopy(STORY_B_BINDING)
        if change == "version": binding["library_version"] = "p3.2a.0"
        if change == "revision": binding["cast"]["resident"]["revision"] = 7
        if change == "duplicate_role": binding["cast"]["twin"] = {"character": "victor_hale", "revision": 1}
        if change == "anchor": binding["locations"]["hall"]["presence"]["anchor"] = "window"
        if change == "extra": binding["story_bible"] = "private"
        with pytest.raises(ValueError):
            lib.validate_binding(binding)


def test_two_stories_share_library_but_not_identity(audio):
    a, _ = build_story_a(audio)
    b, _ = build_story_b(audio)
    looks_a = [s["actors"][0]["look"] for s in a["shots"]]
    looks_b = [s["actors"][0]["look"] for s in b["shots"]]
    assert looks_a[0] == looks_a[1] and looks_b[0] == looks_b[1]
    assert looks_a[0]["design"]["id"] == "nora_vale" and looks_b[0]["design"]["id"] == "victor_hale"
    assert a["asset_binding"]["library"] == b["asset_binding"]["library"] == lib.LIBRARY_ID
    assert {s["location"] for s in a["shots"]} == {"flat"} and {s["location"] for s in b["shots"]} == {"hall"}


def test_reference_material_validates():
    for c in lib.CHARACTERS:
        for e in lib.ENVIRONMENTS:
            validate_story_video(*build_pose_reel(c, e))
    validate_story_video(*build_environment_still("dark_apartment_corridor", "flickering_interior",
                                                  presence=("corridor_end", "tall_hooded"), flicker_off=True))


def test_handoff_and_actual_ts_frame_checks(audio, tmp_path):
    files = []
    for name, builder in (("a", build_story_a), ("b", build_story_b),
                          ("nora-hall", partial(build_story_b, character_id="nora_vale")),
                          ("victor-room", partial(build_story_a, character_id="victor_hale"))):
        video, timeline = builder(audio)
        result = CharacterRigRenderer().execute({"story_video": video, "action_timeline": timeline,
                                                 "workspace_path": str(tmp_path / name / "render")})
        assert result.success, result.error
        assert (tmp_path / name / "render" / "CartoonCast.tsx").is_file()
        props = json.loads((tmp_path / name / "render" / "props.json").read_text(encoding="utf-8"))
        assert props["shots"][0]["actors"][0]["look"]["design"]["revision"] == 1
        source = tmp_path / name / "story_video.json"
        source.write_text(json.dumps(video), encoding="utf-8")
        files.append(str(source))
    output = subprocess.run(["node", "tests/tools/asset_library_checks.cjs", *files], cwd=ROOT, capture_output=True, text=True)
    assert output.returncode == 0, output.stderr
    qa = json.loads(output.stdout)
    assert [list(r["identity"]) for r in qa] == [["nora_vale"], ["victor_hale"], ["nora_vale"], ["victor_hale"]]
    assert qa[0]["appearance"] == qa[2]["appearance"] and qa[1]["appearance"] == qa[3]["appearance"]
    assert all(r["frames"] == 300 and r["contacts"][-1]["heldFrames"] >= 10 for r in qa)
