"""Offline narration using an explicitly installed macOS voice."""
from __future__ import annotations

import platform
import shutil
import subprocess
import time
import wave
from pathlib import Path
from typing import Any

from tools.base_tool import (
    BaseTool, Determinism, ExecutionMode, ResourceProfile, ToolResult,
    ToolRuntime, ToolStability, ToolStatus, ToolTier,
)


class MacOSSayTTS(BaseTool):
    name = "macos_say_tts"
    version = "0.1.0"
    tier = ToolTier.VOICE
    capability = "tts"
    provider = "macos_say"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL
    dependencies = ["cmd:say", "cmd:ffmpeg"]
    install_instructions = "Requires macOS say, an installed voice for the requested locale, and FFmpeg."
    agent_skills = ["text-to-speech"]
    capabilities = ["text_to_speech", "offline_generation", "wav_output"]
    supports = {"offline": True, "multilingual": "installed_voices_only", "voice_cloning": False}
    best_for = ["Local macOS narration with an explicitly installed voice"]
    not_good_for = ["Cross-platform use", "Expressive neural voice acting"]
    resource_profile = ResourceProfile(cpu_cores=1, ram_mb=128, vram_mb=0, disk_mb=20)
    input_schema = {
        "type": "object", "required": ["text", "voice", "language_code", "output_path"],
        "properties": {
            "text": {"type": "string", "minLength": 1},
            "voice": {"type": "string"}, "language_code": {"type": "string"},
            "rate": {"type": "integer", "minimum": 80, "maximum": 300, "default": 145},
            "output_path": {"type": "string"},
        },
    }
    side_effects = ["Writes narration WAV and intermediate AIFF beside output_path"]
    user_visible_verification = ["Listen for intelligibility; verify duration and actual audio stream"]

    def get_status(self) -> ToolStatus:
        return (ToolStatus.AVAILABLE if platform.system() == "Darwin"
                and shutil.which("say") and shutil.which("ffmpeg") else ToolStatus.UNAVAILABLE)

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    def list_voices(self) -> list[dict]:
        voices = subprocess.run(["say", "-v", "?"], capture_output=True, text=True,
                                check=True, timeout=15).stdout
        installed = [line.split("#", 1)[0].strip().rsplit(None, 1) for line in voices.splitlines()]
        return [{"name": row[0], "language_code": row[1]} for row in installed if len(row) == 2]

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        if self.get_status() != ToolStatus.AVAILABLE:
            return ToolResult(success=False, error=self.install_instructions)
        start = time.monotonic()
        try:
            text = inputs["text"].strip()
            voice = inputs["voice"]
            locale = inputs["language_code"].replace("-", "_")
            rate = int(inputs.get("rate", 145))
            if not text or not 80 <= rate <= 300:
                raise ValueError("Nonempty text and rate between 80 and 300 are required")
            matches = sorted({row["name"] for row in self.list_voices() if row["language_code"] == locale
                              and (row["name"] == voice or row["name"].startswith(voice + " ("))})
            if len(matches) != 1:
                raise ValueError(f"Installed voice {voice!r} for {locale!r} was not found; no voice fallback")
            resolved_voice = matches[0]
            output = Path(inputs["output_path"]).resolve()
            if output.suffix.lower() != ".wav":
                raise ValueError("output_path must end in .wav")
            output.parent.mkdir(parents=True, exist_ok=True)
            intermediate = output.with_suffix(".aiff")
            # Narration is stdin, never a shell command or an option to say.
            subprocess.run(["say", "-v", resolved_voice, "-r", str(rate), "-o", str(intermediate)],
                           input=text, capture_output=True, text=True, check=True, timeout=120)
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(intermediate),
                            "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", str(output)],
                           capture_output=True, text=True, check=True, timeout=60)
            with wave.open(str(output), "rb") as audio:
                if audio.getnframes() == 0:
                    raise ValueError("Narration contains zero audio samples; macOS speech service may be sandbox-blocked")
                audio_duration = audio.getnframes() / audio.getframerate()
        except (KeyError, ValueError, OSError, EOFError, wave.Error, subprocess.SubprocessError) as exc:
            return ToolResult(success=False, error=f"macOS local speech failed: {exc}")
        return ToolResult(success=True, data={"output": str(output), "format": "wav",
                          "provider": self.provider, "voice": resolved_voice, "language_code": locale,
                          "rate": rate, "text": text, "local_only": True,
                          "audio_duration_seconds": audio_duration},
                          artifacts=[str(output)], model=f"macos-say:{voice}", cost_usd=0,
                          duration_seconds=round(time.monotonic() - start, 2))
