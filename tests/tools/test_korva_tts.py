"""Korva provider: discovery, selection, worker protocol and narration contract.

The real ``korva_worker.py`` runs in a subprocess against a fake ``korvatts``
package, so no model, network or Korva runtime is needed.
"""
import json
import shutil
import sys
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scripts import story_to_video as cli
from tools.audio import korva_tts as korva
from tools.audio import local_narration as local
from tools.audio.korva_tts import KorvaTTS
from tools.audio.local_wav import wav_duration
from tools.base_tool import ToolResult, ToolStatus

FAKE_SDK = {
    "__init__.py": """
import os
import numpy as np


class _Sessions:
    active_provider = "CPUExecutionProvider"


class TTS:
    sample_rate = 44100

    def __init__(self, assets_dir, device, auto_download, num_threads):
        assert auto_download is False and device == "cpu"
        if os.environ.get("FAKE_KORVA") == "crash_start":
            raise RuntimeError("onnx load failed")
        self.sessions = _Sessions()

    def list_voices(self):
        return ["hoang_nam"]

    def synthesize(self, text, voice, lang, total_steps, speed, silence_between_chunks, seed):
        mode = os.environ.get("FAKE_KORVA", "ok")
        if mode == "raise" and "boom" in text:
            raise ValueError("bad chunk")
        if mode == "exit_mid":
            os._exit(9)
        if mode == "silent":
            return np.zeros(4410, dtype=np.float32), 0.1
        if mode in ("burst", "late_word"):
            tone = lambda seconds, amp: amp * np.sin(np.arange(int(44100 * seconds)) * 2 * np.pi * 220 / 44100)
            gap = lambda seconds: np.zeros(int(44100 * seconds))
            tail = tone(0.2, 1.7) if mode == "burst" else tone(0.5, 0.5)
            audio = np.concatenate([gap(0.5), tone(1.0, 0.5), gap(0.5), tail, gap(0.04)])
            return audio.astype(np.float32), len(audio) / 44100
        print("native library chatter on stdout")
        samples = int(44100 * 0.05 * len(text.split()))
        wave = 1.25 * np.sin(np.arange(samples) * 2 * np.pi * 220 / 44100)
        return wave.astype(np.float32), samples / 44100
""",
    "assets.py": """
from pathlib import Path


def is_valid_assets_dir(path):
    return (Path(path) / "onnx" / "tts.json").is_file()


def list_voices(path):
    return sorted(p.stem for p in (Path(path) / "voice_styles").glob("*.json"))
""",
    "text_processor.py": """
def chunk_text(text, max_len=300):
    return [p for p in text.split("\\n\\n") if p.strip()]
""",
}


@pytest.fixture
def assets(tmp_path):
    root = tmp_path / "hub" / korva.HF_REPO_DIR / "snapshots" / korva.PINNED_REVISION
    (root / "onnx").mkdir(parents=True)
    for name in korva.ONNX_FILES:
        (root / "onnx" / name).write_bytes(name.encode())
    (root / "voice_styles").mkdir()
    (root / "voice_styles" / "hoang_nam.json").write_text('{"style": 1}', encoding="utf-8")
    return root


@pytest.fixture
def runtime(tmp_path, assets, monkeypatch):
    """Fake SDK importable by the real worker; current interpreter acts as the Korva Python."""
    package = tmp_path / "sdk" / "korvatts"
    package.mkdir(parents=True)
    for name, body in FAKE_SDK.items():
        (package / name).write_text(body, encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", str(package.parent))
    monkeypatch.setenv("OPENMONTAGE_KORVA_PYTHON", sys.executable)
    monkeypatch.setenv("OPENMONTAGE_KORVA_ASSETS", str(assets))
    monkeypatch.delenv("FAKE_KORVA", raising=False)
    return {"python": sys.executable, "assets_dir": str(assets)}


@pytest.fixture(autouse=True)
def no_installed_korva(monkeypatch):
    """Hermetic discovery: ignore any Korva runtime/model installed on the test machine."""
    for name in ("OPENMONTAGE_KORVA_PYTHON", "OPENMONTAGE_KORVA_ASSETS", "KORVATTS_ASSETS_DIR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(korva, "_python_candidates", lambda: [])
    monkeypatch.setattr(korva, "_hub_dirs", lambda: [])


def _wav(path, frames=2400):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24000)
        audio.writeframes(b"\x01\x00" * frames)


def _native(name, voices):
    return SimpleNamespace(name=name + "_tts", version="test", list_voices=lambda: voices,
                           get_status=lambda: ToolStatus.AVAILABLE)


needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg normalizes Korva audio")


# --- discovery / model unavailable -------------------------------------------------------

def test_missing_runtime_or_model_is_explicit_and_never_downloads(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="Korva Python runtime not found"):
        korva.find_runtime()
    monkeypatch.setenv("OPENMONTAGE_KORVA_PYTHON", sys.executable)
    with pytest.raises(ValueError, match="no automatic download"):
        korva.find_runtime()
    assert KorvaTTS().get_status() == ToolStatus.UNAVAILABLE
    with pytest.raises(ValueError, match="lacks onnx"):
        korva.find_runtime(assets=str(tmp_path))


def test_discovers_pinned_snapshot_and_explicit_path_never_falls_through(tmp_path, assets, monkeypatch):
    monkeypatch.setenv("OPENMONTAGE_KORVA_PYTHON", sys.executable)
    monkeypatch.setattr(korva, "_hub_dirs", lambda: [tmp_path / "hub"])
    assert korva.find_runtime()["assets_dir"] == str(assets.resolve())
    other = assets.parent / "0123456789abcdef"
    shutil.copytree(assets, other)
    assert korva.find_runtime()["assets_dir"] == str(assets.resolve())  # pinned revision wins
    shutil.rmtree(assets)
    assert korva.find_runtime()["assets_dir"] == str(other.resolve())
    with pytest.raises(ValueError, match="lacks onnx"):
        korva.find_runtime(assets=str(assets))
    with pytest.raises(ValueError, match="runtime not found"):
        korva.find_runtime(python=str(tmp_path / "missing" / "python.exe"))


def test_explicit_korva_fails_closed_instead_of_switching_voice(monkeypatch):
    monkeypatch.setattr(local.platform, "system", lambda: "Windows")
    sapi = _native("windows_sapi", [{"name": "Microsoft An", "language_code": "vi-VN", "speech_host": "pwsh"}])
    tools = {"korva_tts": KorvaTTS(), "windows_sapi_tts": sapi}
    with pytest.raises(ValueError, match="korva: Korva Python runtime not found"):
        local.select_local_voice(tools.__getitem__, "vi", provider="korva")


# --- selection ------------------------------------------------------------------------------

def test_auto_prefers_installed_korva_for_vietnamese_with_model_metadata(runtime, monkeypatch):
    monkeypatch.setattr(local.platform, "system", lambda: "Windows")
    lookup = {"korva_tts": KorvaTTS(), "windows_sapi_tts": Mock()}.__getitem__
    selection = local.select_local_voice(lookup, "vi")
    assert selection["provider"] == "korva" and selection["tool"] == "korva_tts"
    settings = selection["settings"]
    assert settings["voice"] == "hoang_nam" and settings["language_code"] == "vi"
    assert settings["speed"] == 1.05 and settings["total_steps"] == 32 and settings["seed"] == 20261022
    assert settings["python"] == sys.executable and settings["assets_dir"] == runtime["assets_dir"]
    model = selection["model"]
    assert model["revision"] == korva.PINNED_REVISION and model["preset"] == "hoang_nam"
    assert len(model["checkpoint_sha256"]) == 64 and len(model["preset_sha256"]) == 64
    assert model["pcm_export"]["gain"] == 0.6 and "Apache-2.0" in model["license"]
    assert "auto_skipped" not in selection


def test_preset_and_speed_are_validated(runtime):
    lookup = {"korva_tts": KorvaTTS()}.__getitem__
    with pytest.raises(ValueError, match="preset 'Microsoft An' not installed"):
        local.select_local_voice(lookup, "vi", provider="korva", voice="Microsoft An")
    with pytest.raises(ValueError, match="speed, between 0.5 and 2.0"):
        local.select_local_voice(lookup, "vi", provider="korva", rate=-1)
    assert local.select_local_voice(lookup, "vi", provider="korva", rate=0.9)["settings"]["speed"] == 0.9


def test_vietnamese_only_and_english_auto_selection_is_unchanged(runtime, monkeypatch):
    monkeypatch.setattr(local.platform, "system", lambda: "Windows")
    zira = _native("windows_sapi", [{"name": "Microsoft Zira Desktop", "language_code": "en-US",
                                    "speech_host": "powershell"}])
    calls = []
    def lookup(name):
        calls.append(name)
        return KorvaTTS() if name == "korva_tts" else zira
    selection = local.select_local_voice(lookup, "en")
    assert calls == ["windows_sapi_tts"] and selection["provider"] == "windows_sapi"
    with pytest.raises(ValueError, match=r"Vietnamese \(vi\) only"):
        local.select_local_voice(lookup, "en", provider="korva")
    result = KorvaTTS().execute({"text": "Hello", "language_code": "en-US"})
    assert not result.success and "Vietnamese only" in result.error


def test_auto_falls_back_to_native_only_when_not_explicit_and_records_why(runtime, monkeypatch):
    monkeypatch.setattr(local.platform, "system", lambda: "Windows")
    an = _native("windows_sapi", [{"name": "Microsoft An", "language_code": "vi-VN", "speech_host": "pwsh"}])
    broken = KorvaTTS()
    broken.probe = Mock(side_effect=ValueError("Korva runtime probe failed: no module"))
    lookup = {"korva_tts": broken, "windows_sapi_tts": an}.__getitem__
    selection = local.select_local_voice(lookup, "vi")
    assert selection["provider"] == "windows_sapi"
    assert "probe failed" in selection["auto_skipped"][0]
    clean = {k: v for k, v in selection.items() if k != "auto_skipped"}
    assert local.narration_key(selection, "x") == local.narration_key(clean, "x")
    with pytest.raises(ValueError, match="probe failed"):
        local.select_local_voice(lookup, "vi", provider="korva")


@pytest.mark.parametrize("system,native,voice,locale", [("Windows", "windows_sapi", "Microsoft An", "vi-VN"),
                                                       ("Darwin", "macos_say", "Linh", "vi_VN")])
def test_native_selection_identical_when_korva_absent(monkeypatch, system, native, voice, locale):
    monkeypatch.setattr(local.platform, "system", lambda: system)
    row = {"name": voice, "language_code": locale, **({"speech_host": "pwsh"} if native == "windows_sapi" else {})}
    lookup = Mock(return_value=_native(native, [row]))
    selection = local.select_local_voice(lookup, "vi")
    lookup.assert_called_once_with(native + "_tts")
    assert set(selection) == {"provider", "tool", "version", "settings", "model_identity"}


# --- worker / tool execution ------------------------------------------------------------------

@needs_ffmpeg
def test_one_worker_serves_a_story_and_duration_comes_from_samples(runtime, tmp_path):
    tts = KorvaTTS()
    words = ["Lan opens the door.", "Beat two has a few more words."]
    with tts.session():
        results = [tts.execute({"text": text, "voice": "hoang_nam", "language_code": "vi",
                                "output_path": str(tmp_path / f"b{i}.wav"), **runtime})
                   for i, text in enumerate(words)]
        worker = tts._worker
        assert worker is not None and worker.alive()
    assert tts._worker is None and worker.process.poll() is not None
    for result, text in zip(results, words):
        assert result.success, result.error
        native = int(44100 * 0.05 * len(text.split()))
        assert result.data["generation"]["samples"] == native
        assert result.data["audio_duration_seconds"] == wav_duration(Path(result.data["output"]))
        assert abs(result.data["audio_duration_seconds"] - native / 44100) < 0.002
        # 1.25 float peak -> fixed 0.6 gain, no integer clipping
        assert result.data["generation"]["export_gain"] == 0.6
        assert result.data["generation"]["worker"]["execution_provider"] == "CPUExecutionProvider"
    assert results[0].data["generation"]["worker"] == results[1].data["generation"]["worker"]
    with wave.open(results[1].data["output"], "rb") as audio:
        assert (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) == (1, 2, 24000)


@pytest.mark.parametrize("mode,text,message", [
    ("crash_start", "Lan opens the door.", "failed to start: RuntimeError: onnx load failed"),
    ("raise", "boom", "Korva synthesis failed: ValueError: bad chunk"),
    ("exit_mid", "Lan opens the door.", "worker exited (code 9)"),
    ("silent", "Lan opens the door.", "digital silence"),
])
def test_worker_failures_fail_closed_without_output(runtime, tmp_path, monkeypatch, mode, text, message):
    monkeypatch.setenv("FAKE_KORVA", mode)
    output = tmp_path / "beat.wav"
    result = KorvaTTS().execute({"text": text, "output_path": str(output), **runtime})
    assert not result.success and message in result.error
    assert not output.exists()


@needs_ffmpeg
@pytest.mark.parametrize("mode,seconds,gain", [("burst", 1.84, 10 ** (-1 / 20) / 1.7), ("late_word", 2.14, 0.6)])
def test_only_edge_silence_is_trimmed_and_final_segments_are_kept(runtime, tmp_path, monkeypatch,
                                                                  mode, seconds, gain):
    monkeypatch.setenv("FAKE_KORVA", mode)
    result = KorvaTTS().execute({"text": "Final word test.", "output_path": str(tmp_path / "b.wav"), **runtime})
    assert result.success, result.error
    trim = result.data["generation"]["edge_trim"]
    assert trim["lead_trimmed_seconds"] == pytest.approx(0.4, abs=0.021)
    assert trim["tail_trimmed_seconds"] == pytest.approx(0.0, abs=0.021)
    # A short loud segment after a pause may be a real final word: never dropped.
    assert result.data["audio_duration_seconds"] == pytest.approx(seconds, abs=0.03)
    assert result.data["generation"]["export_gain"] == pytest.approx(gain, rel=1e-4)


def test_worker_that_writes_no_wav_is_rejected(runtime, tmp_path, monkeypatch):
    tts = KorvaTTS()
    fake = SimpleNamespace(request=lambda payload: {"ok": True}, ready={}, alive=lambda: True,
                           key=None, close=lambda: None)
    monkeypatch.setattr(tts, "_acquire", lambda *args: fake)
    result = tts.execute({"text": "Lan opens the door.", "output_path": str(tmp_path / "x.wav"), **runtime})
    assert not result.success and "wrote no WAV" in result.error


def test_probe_reports_presets_without_loading_model(runtime):
    probe = KorvaTTS().probe(runtime["python"], runtime["assets_dir"])
    assert probe["voices"] == ["hoang_nam"] and probe["pcm_export"]["ceiling_dbfs"] == -1
    with pytest.raises(ValueError, match="probe failed"):
        KorvaTTS().probe(runtime["python"], str(Path(runtime["assets_dir"]).parent))


def test_worker_module_is_import_safe_for_registry_discovery():
    import importlib
    importlib.import_module("tools.audio.korva_worker")
    assert "korvatts" not in sys.modules


# --- narration cache / CLI -------------------------------------------------------------------------

def _korva_selection(checkpoint="c1", preset="p1", **settings):
    return {"provider": "korva", "tool": "korva_tts", "version": "0.1.0",
            "settings": {"voice": "hoang_nam", "language_code": "vi", "speed": 1.05, **settings},
            "model_identity": checkpoint + preset,
            "model": {"checkpoint_sha256": checkpoint, "preset_sha256": preset, "sdk_version": "0.1.3"}}


def test_cache_invalidates_on_provider_checkpoint_preset_and_settings(tmp_path, monkeypatch):
    def generate(params):
        _wav(Path(params["output_path"]))
        return ToolResult(success=True, data={"generation": {"synthesis_seconds": 0.5, "export_gain": 0.6}})
    tts = SimpleNamespace(execute=Mock(side_effect=generate))
    monkeypatch.setattr(cli, "tool", lambda name: tts)
    analysis = {"beats": [{"id": "b01", "text": "Lan opens the door."}]}
    an = {"provider": "windows_sapi", "tool": "windows_sapi_tts", "version": "0.1.0",
          "settings": {"voice": "Microsoft An", "language_code": "vi-VN", "rate": -1}, "model_identity": "Microsoft An"}
    cli.narrate(analysis, tmp_path, an)
    for selection in (_korva_selection(), _korva_selection(), _korva_selection(checkpoint="c2"),
                      _korva_selection(checkpoint="c2", preset="p2"),
                      _korva_selection(checkpoint="c2", preset="p2", speed=1.0)):
        cli.narrate(analysis, tmp_path, selection)
    # An WAV is never reused for Korva; identical Korva selection hits the cache once.
    assert tts.execute.call_count == 5
    manifest = json.loads((tmp_path / "narration_manifest.json").read_text(encoding="utf-8"))
    assert manifest["b01"]["provider"] == "korva" and manifest["b01"]["generation"]["export_gain"] == 0.6
    summary = cli.narration_summary(tmp_path, analysis["beats"])
    assert summary["beats"] == 1 and summary["synthesis_seconds"] == 0.5 and summary["export_gains"] == [0.6]


def test_narrate_rejects_invalid_wav_from_provider(tmp_path, monkeypatch):
    def generate(params):
        Path(params["output_path"]).write_bytes(b"RIFF-not-really")
        return ToolResult(success=True)
    monkeypatch.setattr(cli, "tool", lambda name: SimpleNamespace(execute=generate))
    with pytest.raises(SystemExit, match="Invalid narration WAV for b01"):
        cli.narrate({"beats": [{"id": "b01", "text": "Lan opens the door."}]}, tmp_path, _korva_selection())


def test_narrate_uses_one_session_and_stops_on_failure(tmp_path, monkeypatch):
    events = []
    class Session:
        def __enter__(self):
            events.append("open")
        def __exit__(self, *exc):
            events.append("close")
    def generate(params):
        events.append(params["text"])
        if params["text"] == "fail":
            return ToolResult(success=False, error="Korva TTS failed: worker exited")
        _wav(Path(params["output_path"]))
        return ToolResult(success=True)
    monkeypatch.setattr(cli, "tool", lambda name: SimpleNamespace(execute=generate, session=Session))
    beats = [{"id": "b01", "text": "one"}, {"id": "b02", "text": "two"}, {"id": "b03", "text": "fail"},
             {"id": "b04", "text": "four"}]
    with pytest.raises(SystemExit, match="Narration failed for b03: Korva TTS failed"):
        cli.narrate({"beats": beats}, tmp_path, _korva_selection())
    assert events == ["open", "one", "two", "fail", "close"]


def test_cli_korva_dry_run_never_probes_and_no_render_passes_korva_paths(tmp_path, monkeypatch):
    source = tmp_path / "story.vi.md"
    source.write_text("# Story\n\nLan opens the door.", encoding="utf-8")
    analysis = {"language": "vi", "beats": [{"id": "b01", "text": "Lan opens the door."}], "characters": [],
                "locations": [], "analyzer": {"backend": "rules"}}
    selector = Mock(side_effect=AssertionError("dry-run must not select TTS"))
    monkeypatch.setattr(cli, "select_local_voice", selector)
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setattr(cli, "tool", lambda name: SimpleNamespace(
        execute=lambda params: ToolResult(success=True, data={"story_analysis": analysis})))
    monkeypatch.setattr(sys, "argv", ["story_to_video", str(source), "--dry-run", "--tts-provider", "korva",
                                      "--analyzer", "rules"])
    cli.main()
    selector.assert_not_called()
    selector = Mock(side_effect=ValueError("No offline TTS for language 'vi'. korva: model missing"))
    monkeypatch.setattr(cli, "select_local_voice", selector)
    monkeypatch.setattr(sys, "argv", ["story_to_video", str(source), "--no-render", "--tts-provider", "korva",
                                      "--korva-python", "py311.exe", "--korva-assets", "snap", "--voice", "hoang_nam"])
    with pytest.raises(SystemExit, match="korva: model missing"):
        cli.main()
    kwargs = selector.call_args.kwargs
    assert kwargs["provider"] == "korva" and kwargs["voice"] == "hoang_nam"
    assert kwargs["korva_python"] == "py311.exe" and kwargs["korva_assets"] == "snap"
    assert not list(tmp_path.glob("projects/**/*.wav"))
