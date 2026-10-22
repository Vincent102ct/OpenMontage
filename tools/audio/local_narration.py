"""Select only installed offline voices; never route through a paid selector."""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from pathlib import Path

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


def select_local_voice(get_tool, language: str, *, provider: str = "auto", voice: str | None = None,
                       rate: float | None = None, piper_model: str | None = None) -> dict:
    native = {"Windows": "windows_sapi", "Darwin": "macos_say"}.get(platform.system())
    candidates = (([native] if native else []) + (["piper"] if piper_model else [])
                  if provider == "auto" else [provider])
    errors = []
    for candidate in candidates:
        tts = get_tool(candidate + "_tts")
        if tts.get_status() != ToolStatus.AVAILABLE:
            errors.append(f"{candidate}: unavailable")
            continue
        try:
            if candidate == "piper":
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
            return {"provider": candidate, "tool": tts.name, "version": tts.version,
                    "settings": settings, "model_identity": identity}
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            errors.append(f"{candidate}: {exc}")
    raise ValueError(f"No offline TTS for language {language!r}. {'; '.join(errors)}. "
                     "Install a native voice exposed by System.Speech/macOS say, or install Piper and supply "
                     "a matching local .onnx + .onnx.json with --piper-model. No English substitution or paid API. "
                     "Use --dry-run for analysis without narration.")


def narration_key(selection: dict, text: str) -> str:
    return hashlib.sha256(json.dumps({"selection": selection, "text": text, "pcm": "mono-24k-s16-v1"},
                                     ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
