"""Shared PCM contract for offline story narration (duration is sample based)."""
from __future__ import annotations

import subprocess
import wave
from pathlib import Path


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as audio:
        if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (1, 2, 24000):
            raise ValueError("Narration must be mono 24000 Hz PCM16 WAV")
        frames = audio.getnframes()
        if not frames or len(audio.readframes(frames)) != frames * 2:
            raise ValueError("Narration contains zero audio samples or truncated PCM data")
        return frames / audio.getframerate()


def normalize_wav(source: Path, output: Path) -> float:
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(source),
                    "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", str(output)],
                   capture_output=True, text=True, encoding="utf-8", errors="replace",
                   check=True, timeout=60)
    return wav_duration(output)
