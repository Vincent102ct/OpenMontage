"""Synthetic-only coverage for the additive skin, viewport and SFX-only handoff."""
import json
from pathlib import Path
import subprocess

import pytest

from tools.character.character_animation import CharacterRigRenderer
from tools.character.stickman_preview import build_preview
from tools.character.story_video import validate_story_video

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def preview(tmp_path):
    # Validator needs files, not the private pilot or generated project data.
    cue = tmp_path / "synthetic.wav"
    cue.write_bytes(b"fixture")
    return build_preview(dict.fromkeys(("room_tone", "furniture_scrape", "footstep"), cue))


def test_sfx_only_handoff_and_rendered_skeleton(preview, tmp_path):
    video, timeline = preview
    result = CharacterRigRenderer().execute({"story_video": video, "action_timeline": timeline,
                                              "workspace_path": str(tmp_path / "render")})
    assert result.success, result.error
    assert result.data["validation"] == {"frames_checked": 301, "shots": 1, "narration": 0, "actions": 4}
    props = json.loads(Path(result.data["props_path"]).read_text())
    assert props["viewport"] == {"width": 720, "height": 1280}
    assert all((tmp_path / "render/public" / cue["path"]).is_file() for cue in props["sfx"])
    source = tmp_path / "preview.json"
    source.write_text(json.dumps(video), encoding="utf-8")
    output = subprocess.run(["node", "tests/tools/stickman_frame_checks.cjs", str(source)],
                            cwd=ROOT, capture_output=True, text=True)
    assert output.returncode == 0, output.stderr
    assert json.loads(output.stdout)["frames"] == 300


@pytest.mark.parametrize("change", ["odd", "bool", "oversize", "skin", "camera", "tts", "mode", "missing_mode"])
def test_invalid_preview_fails_closed(preview, change):
    video, timeline = preview
    if change == "odd": video["viewport"]["width"] = 721
    if change == "bool": video["viewport"]["width"] = True
    if change == "oversize": video["viewport"]["height"] = 8192
    if change == "skin": video["character_skin"] = "unknown"
    if change == "camera": video["shots"][0]["camera"][0][1] = 10
    if change == "tts": video["narration"] = [{"id": "no-tts", "start_seconds": 0, "end_seconds": 1,
                                               "path": video["sfx"][0]["path"], "text": "synthetic"}]
    if change == "mode": video["audio_mode"] = "unknown"
    if change == "missing_mode": video.pop("audio_mode")
    with pytest.raises((ValueError, KeyError)):
        validate_story_video(video, timeline)


def test_horizontal_defaults_still_validate(preview):
    video, timeline = preview
    video.pop("viewport")
    video.pop("character_skin")
    video["shots"][0]["camera"] = [[0, 640, 360, 1], [10, 640, 360, 1]]
    assert validate_story_video(video, timeline)["frames_checked"] == 301
