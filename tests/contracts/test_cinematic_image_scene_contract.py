from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_cinematic_renderer_supports_licensed_still_images_without_video_decoding():
    source = (REPO_ROOT / "remotion-composer/src/CinematicRenderer.tsx").read_text(
        encoding="utf-8"
    )
    types = (REPO_ROOT / "remotion-composer/src/cinematic/types.ts").read_text(
        encoding="utf-8"
    )

    assert 'kind: "image"' in types
    assert "CinematicImageScene" in types
    assert "const SceneImage" in source
    assert "<Img" in source
    assert 'scene.kind === "image"' in source
