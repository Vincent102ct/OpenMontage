"""Synthetic integration and failure coverage for the P3.1 opt-in drawing."""
import json
from pathlib import Path
import subprocess

import pytest

from tools.character.cartoon_horror_preview import build_preview, build_cinematic_preview
from tools.character.character_animation import CharacterRigRenderer
from tools.character.story_video import validate_story_video

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def preview(tmp_path):
    audio = tmp_path / "fixture.wav"
    audio.write_bytes(b"synthetic")
    return build_preview(dict.fromkeys(("room_tone", "furniture_scrape", "footstep"), audio))


def test_cartoon_package_and_actual_frame_geometry(preview, tmp_path):
    video, timeline = preview
    result = CharacterRigRenderer().execute({"story_video": video, "action_timeline": timeline,
                                             "workspace_path": str(tmp_path / "render")})
    assert result.success, result.error
    assert result.data["validation"] == {"frames_checked": 301, "shots": 1, "narration": 0, "actions": 4}
    workspace = Path(result.data["workspace_path"])
    assert (workspace / "CartoonHorror.tsx").is_file()
    assert json.loads((workspace / "props.json").read_text())["character_skin"] == "cartoon_horror"
    source = tmp_path / "video.json"
    source.write_text(json.dumps(video), encoding="utf-8")
    output = subprocess.run(["node", "tests/tools/cartoon_horror_frame_checks.cjs", str(source)],
                            cwd=ROOT, capture_output=True, text=True)
    assert output.returncode == 0, output.stderr
    qa = json.loads(output.stdout)
    assert qa["cartoonArtworkFrames"] == 300
    assert qa["contactFrames"] >= 19 and qa["maxPostContactDrift"] < .001


@pytest.mark.parametrize("change", ["width", "nan", "coverage", "unreachable"])
def test_posture_fails_before_render(preview, change):
    video, timeline = preview
    keys = video["shots"][0]["actors"][0]["posture"]
    if change == "width": keys[1].pop()
    if change == "nan": keys[1][1] = float("nan")
    if change == "coverage": keys.pop()
    if change == "unreachable": keys[1][1] = 500
    with pytest.raises(ValueError):
        validate_story_video(video, timeline)


def test_cinematic_revision_uses_same_handoff_and_reachable_rig(tmp_path):
    audio = tmp_path / "fixture.wav"
    audio.write_bytes(b"synthetic")
    video, timeline = build_cinematic_preview(dict.fromkeys(("room_tone", "furniture_scrape", "footstep", "door_open"), audio))
    result = CharacterRigRenderer().execute({"story_video": video, "action_timeline": timeline,
                                             "workspace_path": str(tmp_path / "render")})
    assert result.success, result.error
    assert (tmp_path / "render/CinematicHorror.tsx").is_file()
    source = tmp_path / "cinematic.json"
    source.write_text(json.dumps(video), encoding="utf-8")
    output = subprocess.run(["node", "tests/tools/cartoon_horror_frame_checks.cjs", str(source)],
                            cwd=ROOT, capture_output=True, text=True)
    assert output.returncode == 0, output.stderr


def test_cinematic_light_and_presence_cannot_skip_validation(tmp_path):
    audio = tmp_path / "fixture.wav"
    audio.write_bytes(b"synthetic")
    for malformed in ("coverage", "range", "skin"):
        video, timeline = build_cinematic_preview(dict.fromkeys(("room_tone", "furniture_scrape", "footstep", "door_open"), audio))
        if malformed == "coverage": video["horror"]["presence"].pop()
        if malformed == "range": video["horror"]["spill"][1][1] = 2
        if malformed == "skin": video["character_skin"] = "stickman_horror"
        with pytest.raises(ValueError): validate_story_video(video, timeline)
