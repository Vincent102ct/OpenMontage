"""Offline routing, measured timing and CLI mode regressions; no cloud calls."""
import json
import sys
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scripts import story_to_video as cli
from tools.audio import korva_tts
from tools.audio import local_narration as local
from tools.audio.local_wav import wav_duration
from tools.audio.piper_tts import PiperTTS
from tools.audio.windows_sapi_tts import WindowsSapiTTS
from tools.base_tool import ToolStatus, ToolResult


@pytest.fixture(autouse=True)
def no_installed_korva(monkeypatch):
    """These native/Piper regressions must not depend on a Korva install on the test machine."""
    for name in ("OPENMONTAGE_KORVA_PYTHON", "OPENMONTAGE_KORVA_ASSETS", "KORVATTS_ASSETS_DIR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(korva_tts, "_python_candidates", lambda: [])
    monkeypatch.setattr(korva_tts, "_hub_dirs", lambda: [])


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


@pytest.mark.parametrize("language,voice,host", [("en", "Microsoft Zira Desktop", "powershell"),
                                               ("vi", "Microsoft An", "pwsh")])
def test_windows_matches_real_inventory_and_uses_sapi_units(monkeypatch, language, voice, host):
    monkeypatch.setattr(local.platform, "system", lambda: "Windows")
    locale = {"en": "en-US", "vi": "vi-VN"}[language]
    native = _native("windows_sapi", [{"name": voice, "language_code": locale,
                                      "speech_host": host}])
    selection = local.select_local_voice(lambda name: native, language, rate=0)
    assert selection["settings"] == {"voice": voice, "language_code": locale, "rate": 0,
                                      "speech_host": host}
    assert local.select_local_voice(lambda name: native, language)["settings"]["rate"] == -1
    with pytest.raises(ValueError, match="integer in -10..10"):
        local.select_local_voice(lambda name: native, language, rate=165)


def test_windows_never_uses_english_for_vietnamese(monkeypatch):
    monkeypatch.setattr(local.platform, "system", lambda: "Windows")
    native = _native("windows_sapi", [{"name": "Zira", "language_code": "en-US", "speech_host": "powershell"}])
    with pytest.raises(ValueError, match="No offline TTS.*vi"):
        local.select_local_voice(lambda name: native, "vi")
    with pytest.raises(ValueError, match="no installed en voice"):
        local.select_local_voice(lambda name: native, "en", voice="Missing")


@pytest.mark.parametrize("language,voice,locale,rate", [("vi", "Linh", "vi_VN", 145),
                                                     ("en", "Samantha", "en_US", 165)])
def test_mac_baseline_voice_locale_and_speed(monkeypatch, language, voice, locale, rate):
    monkeypatch.setattr(local.platform, "system", lambda: "Darwin")
    decorated = voice + " (Installed)"
    native = _native("macos_say", [{"name": decorated, "language_code": locale}])
    result = local.select_local_voice(lambda name: native, language)
    assert result["settings"] == {"voice": decorated, "language_code": locale, "rate": rate}
    assert result["tool"] == "macos_say_tts"


def test_linux_without_model_is_an_explicit_blocker(monkeypatch):
    monkeypatch.setattr(local.platform, "system", lambda: "Linux")
    lookup = Mock()
    with pytest.raises(ValueError, match="matching local .onnx"):
        local.select_local_voice(lookup, "vi")
    lookup.assert_not_called()


def test_piper_requires_local_model_and_matching_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(local.platform, "system", lambda: "Linux")
    model = tmp_path / "voice.onnx"
    model.write_bytes(b"model-fixture")
    config = Path(str(model) + ".json")
    config.write_text(json.dumps({"language": {"code": "vi_VN"}}), encoding="utf-8")
    piper = PiperTTS()
    monkeypatch.setattr(piper, "get_status", lambda: ToolStatus.AVAILABLE)
    result = local.select_local_voice(lambda name: piper, "vi", piper_model=str(model))
    assert result["settings"]["length_scale"] == 1.0
    identity = result["model_identity"]
    model.write_bytes(b"changed-weights")
    assert local.select_local_voice(lambda name: piper, "vi", piper_model=str(model))["model_identity"] != identity
    with pytest.raises(ValueError, match="model language vi_VN does not match en"):
        local.select_local_voice(lambda name: piper, "en", piper_model=str(model))
    config.write_text('{}', encoding="utf-8")
    with pytest.raises(ValueError, match="language.code"):
        PiperTTS.model_language(str(model))


def test_sapi_rejects_language_and_rate_before_synthesis(tmp_path, monkeypatch):
    sapi = WindowsSapiTTS()
    monkeypatch.setattr(sapi, "get_status", lambda: ToolStatus.AVAILABLE)
    monkeypatch.setattr(sapi, "list_voices", lambda: [{"name": "Zira", "language_code": "en-US",
                                                      "speech_host": "powershell"}])
    params = {"text": "Xin chào", "voice": "Zira", "language_code": "vi-VN", "output_path": str(tmp_path / "x.wav")}
    result = sapi.execute(params)
    assert not result.success and "no voice fallback" in result.error
    result = sapi.execute({**params, "rate": 145})
    assert not result.success and "not macOS words/minute" in result.error


def test_sapi_enumerates_and_synthesizes_in_same_host(tmp_path, monkeypatch):
    from tools.audio import windows_sapi_tts as module
    sapi = WindowsSapiTTS()
    monkeypatch.setattr(sapi, "get_status", lambda: ToolStatus.AVAILABLE)
    monkeypatch.setattr(module.shutil, "which", lambda name: name)
    def run(args, **kwargs):
        host = args[0]
        if "env" not in kwargs:
            rows = [{"name": "Zira", "language_code": "en-US"}] if host == "powershell" else [
                {"name": "An", "language_code": "vi-VN"}]
            return SimpleNamespace(stdout=json.dumps(rows), returncode=0)
        assert host == "pwsh"
        env = kwargs["env"]
        assert Path(env["OPENMONTAGE_SAPI_INPUT"]).read_text(encoding="utf-8") == 'Xin chào "bạn"; $test'
        assert env["OPENMONTAGE_SAPI_RATE"] == "-1"
        _wav(Path(env["OPENMONTAGE_SAPI_OUTPUT"]))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(module.subprocess, "run", run)
    def normalize(source, output):
        output.write_bytes(source.read_bytes())
        return wav_duration(output)
    monkeypatch.setattr(module, "normalize_wav", normalize)
    result = sapi.execute({"text": 'Xin chào "bạn"; $test', "voice": "An", "language_code": "vi-VN",
                           "speech_host": "pwsh", "output_path": str(tmp_path / "space dir" / "an.wav")})
    assert result.success, result.error
    assert result.data["audio_duration_seconds"] == 0.1
    assert result.data["speech_host"] == "pwsh"


def test_cache_checks_provider_text_settings_content_and_actual_samples(tmp_path, monkeypatch):
    selection = {"tool": "fake_tts", "provider": "windows_sapi", "version": "1", "settings": {"rate": -1}}
    def generate(params):
        _wav(Path(params["output_path"]))
        return ToolResult(success=True, data={"audio_duration_seconds": 999})
    tts = SimpleNamespace(execute=Mock(side_effect=generate))
    monkeypatch.setattr(cli, "tool", lambda name: tts)
    analysis = {"beats": [{"id": "b01", "text": "Hello"}]}
    assert cli.narrate(analysis, tmp_path, selection)["b01"]["duration_seconds"] == 0.1
    cli.narrate(analysis, tmp_path, selection)
    assert tts.execute.call_count == 1
    # Tampered cache duration must not become a fake action timeline.
    manifest_path = tmp_path / "narration_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["b01"]["duration_seconds"] = 99
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert cli.narrate(analysis, tmp_path, selection)["b01"]["duration_seconds"] == 0.1
    (tmp_path / "b01.wav").write_bytes(b"corrupt")
    cli.narrate(analysis, tmp_path, selection)
    cli.narrate(analysis, tmp_path, {**selection, "provider": "piper"})
    cli.narrate(analysis, tmp_path, {**selection, "settings": {"rate": 0}})
    cli.narrate({"beats": [{"id": "b01", "text": "Changed text"}]}, tmp_path, selection)
    assert tts.execute.call_count == 5


def test_dry_run_never_calls_tts_planner_or_renderer(tmp_path, monkeypatch):
    source = tmp_path / "new story.vi.md"
    source.write_text("# Truyện\n\nLan mở cửa.", encoding="utf-8")
    calls = []
    def lookup(name):
        calls.append(name)
        assert name == "story_analyzer"
        return SimpleNamespace(execute=lambda params: ToolResult(success=True, data={"story_analysis": {
            "language": "vi", "beats": [{"id": "b01", "text": "Lan mở cửa."}], "characters": [],
            "locations": [], "analyzer": {"backend": "rules"}}}))
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setattr(cli, "tool", lookup)
    monkeypatch.setattr(sys, "argv", ["story_to_video", str(source), "--dry-run", "--analyzer", "rules"])
    cli.main()
    assert calls == ["story_analyzer"]
    assert len(list(tmp_path.glob("projects/*-dry-run/artifacts/dry_run_report.json"))) == 1
    assert not list(tmp_path.glob("projects/**/action_timeline.json"))
    assert not list(tmp_path.glob("projects/**/*.wav"))


@pytest.mark.parametrize("frames", [0, 2400])
def test_pcm_contract_rejects_empty_audio(tmp_path, frames):
    path = tmp_path / "voice.wav"
    _wav(path, frames)
    if frames:
        assert wav_duration(path) == 0.1
    else:
        with pytest.raises(ValueError, match="zero audio samples"):
            wav_duration(path)


def test_no_render_builds_package_from_real_wav_but_never_starts_browser(tmp_path, monkeypatch):
    source = tmp_path / "new-story.en.md"
    source.write_text("# Morning\n\nBen walked into the shop.", encoding="utf-8")
    selection = {"tool": "fixture_tts", "provider": "fixture", "version": "1", "settings": {}}
    monkeypatch.setattr(cli, "select_local_voice", lambda *args, **kwargs: selection)
    real_lookup = cli.tool
    calls = []
    def generate(params):
        _wav(Path(params["output_path"]), 24000)
        return ToolResult(success=True, data={"audio_duration_seconds": 999})
    def lookup(name):
        calls.append(name)
        assert name != "video_compose"
        return SimpleNamespace(execute=generate) if name == "fixture_tts" else real_lookup(name)
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setattr(cli, "tool", lookup)
    monkeypatch.setattr(sys, "argv", ["story_to_video", str(source), "--no-render", "--analyzer", "rules"])
    cli.main()
    assert "fixture_tts" in calls and "story_planner" in calls and "character_rig_renderer" in calls
    project = next((tmp_path / "projects").iterdir())
    video = json.loads((project / "artifacts/story_video.json").read_text(encoding="utf-8"))
    narration = video["narration"][0]
    assert narration["end_seconds"] - narration["start_seconds"] == pytest.approx(1.0)
    assert (project / "artifacts/edit_decisions.json").is_file()
    assert not list(project.glob("renders/*.mp4"))


def test_piper_normalizes_and_measures_output_with_utf8_stdin(tmp_path, monkeypatch):
    from tools.audio import piper_tts as module
    model = tmp_path / "vietnamese.onnx"
    model.write_bytes(b"fixture")
    Path(str(model) + ".json").write_text('{"language":{"code":"vi_VN"}}', encoding="utf-8")
    piper = PiperTTS()
    monkeypatch.setattr(piper, "get_status", lambda: ToolStatus.AVAILABLE)
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        if args[0] == "piper":
            assert kwargs["encoding"] == "utf-8" and kwargs["input"] == "Xin chào"
            assert args[args.index("--model") + 1] == str(model)
            _wav(Path(args[-1]))
        else:
            assert args[0] == "ffmpeg" and "pcm_s16le" in args
            _wav(Path(args[-1]))
        return SimpleNamespace(returncode=0, stderr="")
    monkeypatch.setattr(module.subprocess, "run", run)
    result = piper.execute({"text": "Xin chào", "model": str(model), "language_code": "vi",
                            "output_path": str(tmp_path / "voice.wav")})
    assert result.success, result.error
    assert result.data["audio_duration_seconds"] == 0.1
    assert len(calls) == 2
    calls.clear()
    result = piper.execute({"text": "Hello", "model": str(model), "language_code": "en"})
    assert not result.success and "no voice fallback" in result.error
    assert calls == []
