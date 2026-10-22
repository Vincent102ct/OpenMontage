"""Piper local text-to-speech provider tool."""

from __future__ import annotations

import shutil
import json
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from tools.audio.local_wav import normalize_wav

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    RetryPolicy,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)


class PiperTTS(BaseTool):
    name = "piper_tts"
    version = "0.1.0"
    tier = ToolTier.VOICE
    capability = "tts"
    provider = "piper"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL

    dependencies = ["cmd:piper", "cmd:ffmpeg"]
    install_instructions = (
        "Install Piper TTS:\n"
        "  pip install piper-tts\n"
        "Or download from https://github.com/rhasspy/piper/releases\n"
        "Separately obtain a licensed .onnx voice and adjacent .onnx.json config. "
        "Pass its local path as model; synthesis never downloads a model."
    )
    agent_skills = ["text-to-speech"]

    capabilities = [
        "text_to_speech",
        "offline_generation",
    ]
    supports = {
        "voice_cloning": False,
        "multilingual": "installed_model_only",
        "offline": True,
        "native_audio": True,
    }
    best_for = [
        "offline narration fallback",
        "privacy-sensitive local-only workflows",
    ]
    not_good_for = [
        "best-in-class expressive voice quality",
        "voice clone matching",
    ]

    input_schema = {
        "type": "object",
        "required": ["text"],
        "properties": {
            "text": {"type": "string"},
            "model": {
                "type": "string",
                "default": "en_US-lessac-medium",
            },
            "speaker_id": {
                "type": "integer",
                "default": 0,
            },
            "length_scale": {
                "type": "number",
                "default": 1.0,
            },
            "sentence_silence": {
                "type": "number",
                "default": 0.3,
            },
            "output_path": {"type": "string"},
            "language_code": {"type": "string"},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=2, ram_mb=512, vram_mb=0, disk_mb=200, network_required=False
    )
    retry_policy = RetryPolicy(max_retries=1, retryable_errors=[])
    idempotency_key_fields = ["text", "model", "speaker_id", "length_scale"]
    side_effects = ["writes audio file to output_path"]
    user_visible_verification = ["Listen to generated audio for intelligibility"]

    def get_status(self) -> ToolStatus:
        if shutil.which("piper") and shutil.which("ffmpeg"):
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    @staticmethod
    def model_language(model: str) -> str:
        path = Path(model).resolve()
        if not path.is_file() or path.suffix.lower() != ".onnx":
            raise ValueError("Piper requires an existing local .onnx model (no automatic download)")
        config = json.loads(Path(str(path) + ".json").read_text(encoding="utf-8"))
        locale = config.get("language", {}).get("code")
        if not isinstance(locale, str) or not locale:
            raise ValueError("Piper .onnx.json must declare language.code; no voice fallback")
        return locale

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        if self.get_status() != ToolStatus.AVAILABLE:
            return ToolResult(success=False, error="Piper TTS not available. " + self.install_instructions)

        start = time.time()
        try:
            result = self._generate(inputs)
        except Exception as exc:
            return ToolResult(success=False, error=f"Local TTS generation failed: {exc}")

        result.duration_seconds = round(time.time() - start, 2)
        return result

    def _generate(self, inputs: dict[str, Any]) -> ToolResult:
        output_path = Path(inputs.get("output_path", "tts_output.wav")).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        model = str(Path(inputs.get("model", "en_US-lessac-medium")).resolve())
        locale = self.model_language(model)
        requested = inputs.get("language_code", locale).replace("_", "-").lower()
        actual = locale.replace("_", "-").lower()
        if actual != requested and not actual.startswith(requested + "-"):
            raise ValueError(f"Piper model language {locale} does not match {requested}; no voice fallback")
        scale = float(inputs.get("length_scale", 1.0))
        if not 0.25 <= scale <= 4 or not inputs["text"].strip():
            raise ValueError("Piper needs nonempty text and length_scale between 0.25 and 4")
        if output_path.suffix.lower() != ".wav":
            raise ValueError("output_path must end in .wav")
        with tempfile.TemporaryDirectory(prefix="openmontage-piper-") as temp_dir:
            raw = Path(temp_dir) / "raw.wav"
            proc = subprocess.run(
                [
                    "piper",
                    "--model", model,
                    "--speaker", str(inputs.get("speaker_id", 0)),
                    "--length-scale", str(scale),
                    "--sentence-silence", str(inputs.get("sentence_silence", 0.3)),
                    "--output_file", str(raw),
                ],
                input=inputs["text"], capture_output=True, text=True, encoding="utf-8", timeout=300,
            )
            if proc.returncode != 0:
                return ToolResult(success=False, error=f"Piper failed (exit {proc.returncode}): {proc.stderr}")
            audio_duration = normalize_wav(raw, output_path)

        return ToolResult(
            success=True,
            data={
                "provider": self.provider,
                "model": inputs.get("model", "en_US-lessac-medium"),
                "speaker_id": inputs.get("speaker_id", 0),
                "text_length": len(inputs["text"]),
                "output": str(output_path),
                "format": "wav",
                "language_code": locale,
                "local_only": True,
                "audio_duration_seconds": audio_duration,
            },
            artifacts=[str(output_path)],
            model=inputs.get("model", "en_US-lessac-medium"),
        )
