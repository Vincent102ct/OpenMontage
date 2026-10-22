"""Select only installed offline voices; never route through a paid selector."""
from __future__ import annotations

import hashlib
import json
import platform
import shutil
import subprocess
from pathlib import Path

from tools.audio import korva_tts as korva
from tools.base_tool import ToolStatus


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def language_matches(actual: str, requested: str) -> bool:
    actual, requested = actual.lower().replace("_", "-"), requested.lower().replace("_", "-")
    return actual == requested or actual.startswith(requested + "-")


def korva_configured(korva_python: str | None = None, korva_assets: str | None = None) -> bool:
    try:
        korva.find_runtime(korva_python, korva_assets)
    except ValueError:
        return False
    return True


def _select_korva(tts, language: str, voice: str | None, rate: float | None,
                  korva_python: str | None, korva_assets: str | None) -> tuple[dict, str, dict]:
    if not language_matches(language, "vi"):
        raise ValueError(f"Korva is validated for Vietnamese (vi) only, not {language!r}; no voice fallback")
    if not shutil.which("ffmpeg"):
        raise ValueError("FFmpeg is required to normalize Korva audio")
    runtime = korva.find_runtime(korva_python, korva_assets)
    probe = tts.probe(runtime["python"], runtime["assets_dir"])
    preset = voice or korva.DEFAULTS["voice"]
    if preset not in probe["voices"]:
        raise ValueError(f"Korva preset {preset!r} not installed; available: {', '.join(probe['voices'])}")
    speed = korva.DEFAULTS["speed"] if rate is None else rate
    if not korva.SPEED_RANGE[0] <= speed <= korva.SPEED_RANGE[1]:
        raise ValueError("Korva --rate is speed, between 0.5 and 2.0")
    settings = {**korva.DEFAULTS, "voice": preset, "language_code": "vi", "speed": speed,
                "num_threads": korva.default_threads(), **runtime}
    model = {**korva.model_identity(runtime["assets_dir"], preset), "sdk_version": probe["sdk_version"],
             "runtime_python": probe["python"], "packages": probe["packages"], "pcm_export": probe["pcm_export"]}
    identity = hashlib.sha256(json.dumps([model["checkpoint_sha256"], model["preset_sha256"],
                                          model["sdk_version"]]).encode()).hexdigest()
    return settings, identity, model


def select_local_voice(get_tool, language: str, *, provider: str = "auto", voice: str | None = None,
                       rate: float | None = None, piper_model: str | None = None,
                       korva_python: str | None = None, korva_assets: str | None = None) -> dict:
    native = {"Windows": "windows_sapi", "Darwin": "macos_say"}.get(platform.system())
    # Auto prefers Korva only for Vietnamese and only when a local install is found.
    preferred = (["korva"] if language_matches(language, "vi") and korva_configured(korva_python, korva_assets)
                 else [])
    candidates = (preferred + ([native] if native else []) + (["piper"] if piper_model else [])
                  if provider == "auto" else [provider])
    errors = []
    for candidate in candidates:
        tts = get_tool(candidate + "_tts")
        # Korva status reflects default discovery only; explicit paths are validated below.
        if tts.get_status() != ToolStatus.AVAILABLE and candidate != "korva":
            errors.append(f"{candidate}: unavailable")
            continue
        try:
            extra = {}
            if candidate == "korva":
                settings, identity, extra["model"] = _select_korva(tts, language, voice, rate,
                                                                   korva_python, korva_assets)
            elif candidate == "piper":
                if voice:
                    raise ValueError("Use --piper-model instead of --voice for Piper")
                locale = tts.model_language(piper_model or "")
                if not language_matches(locale, language):
                    raise ValueError(f"model language {locale} does not match {language}")
                model = Path(piper_model).resolve()
                settings = {"model": str(model), "language_code": locale,
                            "length_scale": 1.0 if rate is None else rate}
                if not 0.25 <= settings["length_scale"] <= 4:
                    raise ValueError("Piper --rate is length_scale, between 0.25 and 4")
                identity = file_hash(model) + file_hash(Path(str(model) + ".json"))
            else:
                voices = [v for v in tts.list_voices() if language_matches(v["language_code"], language)]
                if voice:
                    voices = [v for v in voices if v["name"] == voice or
                              (candidate == "macos_say" and v["name"].startswith(voice + " ("))]
                preferred = ({"vi": "Linh", "en": "Samantha"}.get(language, "") if candidate == "macos_say"
                             else "Microsoft Zira Desktop")
                voices.sort(key=lambda v: (not (v["name"] == preferred or v["name"].startswith(preferred + " (")), v["name"]))
                if not voices:
                    raise ValueError(f"no installed {language} voice matching {voice or 'auto'}")
                chosen = voices[0]
                default_rate = ({"vi": 145, "en": 165}[language] if candidate == "macos_say" else -1)
                actual_rate = default_rate if rate is None else rate
                low, high = (80, 300) if candidate == "macos_say" else (-10, 10)
                if not low <= actual_rate <= high or int(actual_rate) != actual_rate:
                    raise ValueError(f"{candidate} --rate must be an integer in {low}..{high}")
                settings = {"voice": chosen["name"], "language_code": chosen["language_code"], "rate": int(actual_rate)}
                if candidate == "windows_sapi":
                    settings["speech_host"] = chosen["speech_host"]
                identity = chosen["name"]
            if errors:
                extra["auto_skipped"] = errors
            return {"provider": candidate, "tool": tts.name, "version": tts.version,
                    "settings": settings, "model_identity": identity, **extra}
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            errors.append(f"{candidate}: {exc}")
    raise ValueError(f"No offline TTS for language {language!r}. {'; '.join(errors)}. "
                     "Install a native voice exposed by System.Speech/macOS say, configure a local Korva runtime "
                     "(--korva-python/--korva-assets, Vietnamese only), or install Piper and supply "
                     "a matching local .onnx + .onnx.json with --piper-model. No English substitution or paid API. "
                     "Use --dry-run for analysis without narration.")


def narration_key(selection: dict, text: str) -> str:
    # Diagnostics about skipped auto candidates must not invalidate audio.
    selection = {k: v for k, v in selection.items() if k != "auto_skipped"}
    return hashlib.sha256(json.dumps({"selection": selection, "text": text, "pcm": "mono-24k-s16-v1"},
                                     ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
