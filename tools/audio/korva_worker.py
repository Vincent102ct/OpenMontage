"""KorvaTTS inference worker, executed by the separate Korva Python runtime.

Runs inside the isolated interpreter that has ``korvatts`` installed (the M1.2
benchmark used CPython 3.11), never inside the OpenMontage process. It imports
nothing from OpenMontage. Protocol: one JSON object per line.

    --probe  print {"event": "probe", ...} without loading ONNX sessions, exit.
    default  load the model once, print {"event": "ready", ...}, then answer one
             {"id", "text", "output_path", "voice", ...} request per stdin line
             until EOF.

Inference is offline only: explicit assets directory, ``auto_download=False``,
Hugging Face offline flags and a socket guard. Output is mono PCM16 at the
model's native rate. Leading/trailing silence beyond a short pad is trimmed (it
skews the planner's verb-to-time mapping); interior pauses and any audible tail
are kept, because a short loud segment after a pause can be a real final word.
Korva float output often peaks above 1.0 (M1.2: 1.04-1.35),
so every request gets the same static NARRATION_GAIN, lowered further only when
a peak would exceed -1 dBFS. No limiter, compressor, tempo or pitch change.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
import wave

HEADROOM = 10 ** (-1 / 20)
# One gain for all beats keeps narration level consistent across a story.
NARRATION_GAIN = 0.6
EDGE = {"frame_s": 0.02, "silence_dbfs": -45, "pad_s": 0.1, "fade_s": 0.01}


def _deny_network(*args, **kwargs):
    raise RuntimeError("Korva offline inference: network connection forbidden")


def _offline() -> None:
    os.environ.update(HF_HUB_OFFLINE="1", HF_DATASETS_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    socket.socket.connect = _deny_network
    socket.socket.connect_ex = _deny_network
    socket.create_connection = _deny_network


def _versions() -> dict:
    import importlib.metadata
    packages = {}
    for name in ("korvatts", "onnxruntime", "numpy"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            pass
    return {"sdk_version": packages.get("korvatts"), "packages": packages,
            "python": sys.version.split()[0], "python_executable": sys.executable,
            "pcm_export": {"format": "mono PCM16 native rate", "gain": NARRATION_GAIN, "ceiling_dbfs": -1,
                           "edge_trim": EDGE}}


def _trim_edges(audio, sample_rate: int):
    """Trim leading/trailing frames below the silence threshold to a pad; return (audio, report)."""
    import numpy as np
    frame = int(EDGE["frame_s"] * sample_rate)
    count = len(audio) // frame
    if count == 0:
        return audio, {}
    rms = np.sqrt(np.mean(audio[: count * frame].reshape(count, frame).astype(np.float64) ** 2, axis=1))
    voiced = np.flatnonzero(rms >= 10 ** (EDGE["silence_dbfs"] / 20))
    if voiced.size == 0:
        raise ValueError("Korva returned no audio above the silence threshold")
    first, last = int(voiced[0]), int(voiced[-1])
    pad = int(EDGE["pad_s"] * sample_rate)
    begin = max(0, first * frame - pad)
    end = min(len(audio), (last + 1) * frame + pad)
    trimmed = np.array(audio[begin:end], dtype=np.float32)
    fade = min(len(trimmed) // 2, int(EDGE["fade_s"] * sample_rate))
    if fade and begin > 0:
        trimmed[:fade] *= np.linspace(0.0, 1.0, fade, dtype=np.float32)
    if fade and end < len(audio):
        trimmed[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)
    return trimmed, {"lead_trimmed_seconds": begin / sample_rate,
                     "tail_trimmed_seconds": (len(audio) - end) / sample_rate}


def _write_pcm16(path: str, audio, sample_rate: int) -> dict:
    import numpy as np
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    if audio.size == 0 or not np.isfinite(audio).all():
        raise ValueError("Korva returned empty or non-finite audio")
    if float(np.max(np.abs(audio))) == 0:
        raise ValueError("Korva returned digital silence")
    native_samples = int(audio.size)
    audio, trim = _trim_edges(audio, sample_rate)
    peak = float(np.max(np.abs(audio)))
    gain = min(NARRATION_GAIN, HEADROOM / peak)
    pcm = np.clip(np.round(audio * gain * 32767), -32768, 32767).astype("<i2")
    with wave.open(path, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(sample_rate)
        out.writeframes(pcm.tobytes())
    return {"samples": int(pcm.size), "native_samples": native_samples, "sample_rate": sample_rate,
            "float_peak": peak, "export_gain": gain, "edge_trim": trim}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assets", required=True)
    parser.add_argument("--threads", type=int, default=None)
    parser.add_argument("--probe", action="store_true")
    args = parser.parse_args()
    # Native libraries may print; keep the protocol channel clean.
    channel = os.fdopen(os.dup(sys.stdout.fileno()), "w", encoding="utf-8", buffering=1)
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())

    def send(message: dict) -> None:
        channel.write(json.dumps(message, ensure_ascii=False) + "\n")
        channel.flush()

    _offline()
    try:
        from pathlib import Path
        from korvatts.assets import is_valid_assets_dir, list_voices
        assets = Path(args.assets)
        if not is_valid_assets_dir(assets):
            raise FileNotFoundError(f"Korva assets dir {assets} is missing required ONNX files")
        if args.probe:
            send({"event": "probe", "voices": list_voices(assets), **_versions()})
            return 0
        from korvatts import TTS
        started = time.perf_counter()
        tts = TTS(assets_dir=str(assets), device="cpu", auto_download=False, num_threads=args.threads)
        send({"event": "ready", "voices": tts.list_voices(), "sample_rate": tts.sample_rate,
              "execution_provider": tts.sessions.active_provider,
              "load_seconds": time.perf_counter() - started, **_versions()})
    except Exception as exc:  # report startup failures on the protocol channel
        send({"event": "error", "error": f"{type(exc).__name__}: {exc}"})
        return 2

    from korvatts.text_processor import chunk_text
    for line in sys.stdin:
        if not line.strip():
            continue
        request = {}
        try:
            request = json.loads(line)
            started = time.perf_counter()
            audio, _ = tts.synthesize(request["text"], voice=request["voice"], lang=request["lang"],
                                      total_steps=request["total_steps"], speed=request["speed"],
                                      silence_between_chunks=request["silence_between_chunks"],
                                      seed=request["seed"])
            seconds = time.perf_counter() - started
            info = _write_pcm16(request["output_path"], audio, tts.sample_rate)
            send({"id": request.get("id"), "ok": True, "synthesis_seconds": seconds,
                  "chunks": len(chunk_text(request["text"], max_len=300)), **info})
        except Exception as exc:
            send({"id": request.get("id"), "ok": False, "error": f"{type(exc).__name__}: {exc}"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
