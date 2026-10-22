"""Windows SAPI local text-to-speech provider tool.

This provider deliberately uses only the voices installed with Windows.  It is
unavailable on other operating systems and never sends narration to a network
service.
"""

from __future__ import annotations

import os
import json
import platform
import shutil
import subprocess
import tempfile
import time
import wave
from pathlib import Path
from typing import Any

from tools.audio.local_wav import normalize_wav

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)


class WindowsSapiTTS(BaseTool):
    """Generate a WAV narration with an installed Windows SAPI voice."""

    name = "windows_sapi_tts"
    version = "0.1.0"
    tier = ToolTier.VOICE
    capability = "tts"
    provider = "windows_sapi"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL

    dependencies = ["cmd:powershell", "cmd:ffmpeg", "os:windows"]
    install_instructions = (
        "Requires Windows System.Speech, an installed voice, PowerShell and FFmpeg on PATH. "
        "PowerShell 7 (pwsh) can expose additional installed voices. No network provider is used."
    )
    agent_skills = ["text-to-speech"]
    capabilities = ["text_to_speech", "offline_generation", "wav_output"]
    supports = {
        "voice_cloning": False,
        "multilingual": "installed_voices_only",
        "offline": True,
        "native_audio": True,
    }
    best_for = ["Windows-only offline narration", "zero-cost local fallback"]
    not_good_for = ["cross-platform rendering", "voice cloning"]

    input_schema = {
        "type": "object",
        "required": ["text"],
        "properties": {
            "text": {"type": "string", "minLength": 1},
            "voice": {"type": "string", "default": "Microsoft Zira Desktop"},
            "language_code": {"type": "string", "description": "Must match the installed voice culture when supplied"},
            "speech_host": {"type": "string", "enum": ["powershell", "pwsh"]},
            "rate": {"type": "integer", "minimum": -10, "maximum": 10, "default": -1},
            "output_path": {"type": "string"},
        },
    }
    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=128, vram_mb=0, disk_mb=20, network_required=False
    )
    idempotency_key_fields = ["text", "voice", "rate"]
    side_effects = ["writes WAV audio file to output_path"]
    user_visible_verification = ["Listen to narration for intelligibility and pronunciation"]

    def get_status(self) -> ToolStatus:
        if platform.system() == "Windows" and shutil.which("powershell") and shutil.which("ffmpeg"):
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    def list_voices(self) -> list[dict]:
        """Query the same System.Speech engine used for synthesis, not the registry."""
        script = """
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
  $voices = @($synth.GetInstalledVoices() | Where-Object { $_.Enabled } | ForEach-Object {
    @{name=$_.VoiceInfo.Name; language_code=$_.VoiceInfo.Culture.Name}
  })
  ConvertTo-Json -InputObject $voices -Compress
} finally { $synth.Dispose() }
"""
        voices, errors = [], []
        for host in ("powershell", "pwsh"):
            executable = shutil.which(host)
            if not executable:
                continue
            try:
                result = subprocess.run([executable, "-NoProfile", "-NonInteractive", "-Command", script],
                                        capture_output=True, text=True, encoding="utf-8", errors="strict",
                                        check=True, timeout=30)
                voices.extend({**v, "speech_host": host} for v in json.loads(result.stdout.lstrip("\ufeff")))
            except (ValueError, OSError, subprocess.SubprocessError) as exc:
                errors.append(f"{host}: {exc}")
        if not voices and errors:
            raise ValueError("System.Speech voice enumeration failed: " + "; ".join(errors))
        return voices

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        if not inputs.get("text", "").strip():
            return ToolResult(success=False, error="Text is required for Windows SAPI TTS.")
        try:
            return self._synthesize(inputs)
        except (ValueError, OSError, EOFError, wave.Error, subprocess.SubprocessError) as exc:
            return ToolResult(success=False, error=f"Windows SAPI failed: {exc}")

    def _synthesize(self, inputs: dict[str, Any]) -> ToolResult:
        if self.get_status() != ToolStatus.AVAILABLE:
            return ToolResult(success=False, error="Windows SAPI TTS is unavailable. " + self.install_instructions)

        text = inputs["text"].strip()
        if not text:
            return ToolResult(success=False, error="Text is required for Windows SAPI TTS.")

        output_path = Path(inputs.get("output_path", "tts_output.wav")).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        voice = inputs.get("voice", "Microsoft Zira Desktop")
        rate = int(inputs.get("rate", -1))
        if rate != float(inputs.get("rate", -1)) or not -10 <= rate <= 10:
            raise ValueError("SAPI rate must be an integer between -10 and 10 (not macOS words/minute)")
        if output_path.suffix.lower() != ".wav":
            raise ValueError("output_path must end in .wav")
        matches = [v for v in self.list_voices() if v["name"] == voice and
                   (not inputs.get("speech_host") or v["speech_host"] == inputs["speech_host"])]
        # The same Desktop voice can be visible in both runtimes. Use the first
        # enumerated host, and keep that host for synthesis as well.
        matches = matches[:1]
        locale = inputs.get("language_code", "").replace("_", "-").lower()
        if len(matches) != 1 or (locale and not (matches[0]["language_code"].lower() == locale
                                               or matches[0]["language_code"].lower().startswith(locale + "-"))):
            raise ValueError(f"Installed voice {voice!r} for {locale!r} was not found; no voice fallback")

        script = """
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$text = [System.IO.File]::ReadAllText($env:OPENMONTAGE_SAPI_INPUT)
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
  $synth.SelectVoice($env:OPENMONTAGE_SAPI_VOICE)
  $synth.Rate = [int]$env:OPENMONTAGE_SAPI_RATE
  $synth.SetOutputToWaveFile($env:OPENMONTAGE_SAPI_OUTPUT)
  $synth.Speak($text)
} finally {
  $synth.Dispose()
}
"""

        start = time.time()
        with tempfile.TemporaryDirectory(prefix="openmontage-sapi-") as temp_dir:
            input_path = Path(temp_dir) / "narration.txt"
            input_path.write_text(text, encoding="utf-8")
            environment = os.environ.copy()
            environment.update({
                "OPENMONTAGE_SAPI_INPUT": str(input_path),
                "OPENMONTAGE_SAPI_OUTPUT": str(Path(temp_dir) / "raw.wav"),
                "OPENMONTAGE_SAPI_VOICE": voice,
                "OPENMONTAGE_SAPI_RATE": str(rate),
            })
            completed = subprocess.run(
                [shutil.which(matches[0]["speech_host"]), "-NoProfile", "-NonInteractive", "-Command", script],
                timeout=300,
                env=environment,
                capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
            )
            audio_duration = normalize_wav(Path(temp_dir) / "raw.wav", output_path)

        if completed.returncode != 0:
            return ToolResult(
                success=False,
                error=f"Windows SAPI failed (exit {completed.returncode}).",
            )
        if not output_path.is_file() or output_path.stat().st_size == 0:
            return ToolResult(success=False, error=f"Windows SAPI output file is missing or empty: {output_path}")

        return ToolResult(
            success=True,
            data={
                "provider": self.provider,
                "voice": voice,
                "rate": rate,
                "text_length": len(text),
                "output": str(output_path),
                "format": "wav",
                "local_only": True,
                "language_code": matches[0]["language_code"],
                "speech_host": matches[0]["speech_host"],
                "audio_duration_seconds": audio_duration,
            },
            artifacts=[str(output_path)],
            model=f"windows-sapi:{voice}",
            cost_usd=0.0,
            duration_seconds=round(time.time() - start, 2),
        )
