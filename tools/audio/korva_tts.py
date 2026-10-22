"""KorvaTTS local Vietnamese narration provider (offline ONNX, bundled presets only).

KorvaTTS needs its own Python runtime (the M1.2 benchmark pinned CPython 3.11 +
korvatts 0.1.3 + onnxruntime), while OpenMontage may run on a newer Python. This
tool therefore never imports ``korvatts``: it drives ``korva_worker.py`` in the
Korva interpreter over a JSON-lines pipe. Inside ``session()`` one worker (one
model load) serves every narration request of a story.

Runtime and assets are discovered, never downloaded: explicit arguments, then
``OPENMONTAGE_KORVA_PYTHON`` / ``OPENMONTAGE_KORVA_ASSETS`` (or the SDK's own
``KORVATTS_ASSETS_DIR``), then the documented local install locations.
"""
from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
import wave
from contextlib import contextmanager
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

ROOT = Path(__file__).resolve().parents[2]
WORKER = Path(__file__).resolve().with_name("korva_worker.py")
# Where the M1.2 benchmark installed the pinned runtime and model on this checkout.
BENCHMARK_ROOT = ROOT / "projects" / "m12-vietnamese-tts-review"
HF_REPO = "dogenthq/KorvaTTS"
HF_REPO_DIR = "models--dogenthq--KorvaTTS"
PINNED_REVISION = "e5c8c218e93c1d8daa53bfe0e62b8fbc5a5e991d"
ONNX_FILES = ["duration_predictor.onnx", "text_encoder.onnx", "vector_estimator.onnx",
              "vocoder.onnx", "tts.json", "unicode_indexer.json"]
DEFAULTS = {"voice": "hoang_nam", "speed": 1.05, "total_steps": 32,
            "silence_between_chunks": 0.3, "seed": 20261022}
SPEED_RANGE = (0.5, 2.0)
STARTUP_TIMEOUT = 180
REQUEST_TIMEOUT = 900
_HASHES: dict[tuple, str] = {}


def default_threads() -> int:
    return max(1, min(6, os.cpu_count() or 1))


def _python_candidates() -> list[Path]:
    env = BENCHMARK_ROOT / "envs" / "korva"
    return [env / "Scripts" / "python.exe", env / "bin" / "python"]


def _hub_dirs() -> list[Path]:
    dirs = []
    if os.environ.get("HF_HUB_CACHE"):
        dirs.append(Path(os.environ["HF_HUB_CACHE"]))
    if os.environ.get("HF_HOME"):
        dirs.append(Path(os.environ["HF_HOME"]) / "hub")
    dirs += [Path.home() / ".cache" / "huggingface" / "hub", BENCHMARK_ROOT / "cache" / "huggingface" / "hub"]
    return dirs


def valid_assets(path: Path) -> bool:
    return all((path / "onnx" / name).is_file() for name in ONNX_FILES) and (path / "voice_styles").is_dir()


def find_runtime(python: str | None = None, assets: str | None = None) -> dict:
    """Return {"python", "assets_dir"} or raise ValueError; explicit values never fall through."""
    explicit = python or os.environ.get("OPENMONTAGE_KORVA_PYTHON")
    if explicit:
        interpreter = Path(explicit).expanduser().resolve()
        if not interpreter.is_file():
            raise ValueError(f"Korva Python runtime not found: {interpreter}")
    else:
        interpreter = next((p for p in _python_candidates() if p.is_file()), None)
        if interpreter is None:
            raise ValueError("Korva Python runtime not found. Pass --korva-python or set "
                             "OPENMONTAGE_KORVA_PYTHON to the interpreter that has korvatts installed")
    explicit = assets or os.environ.get("OPENMONTAGE_KORVA_ASSETS") or os.environ.get("KORVATTS_ASSETS_DIR")
    if explicit:
        directory = Path(explicit).expanduser().resolve()
        if not valid_assets(directory):
            raise ValueError(f"Korva assets dir {directory} lacks onnx/{{{','.join(ONNX_FILES)}}} or voice_styles/")
    else:
        found = []
        for hub in _hub_dirs():
            snapshots = hub / HF_REPO_DIR / "snapshots"
            if snapshots.is_dir():
                found += [p.resolve() for p in sorted(snapshots.iterdir()) if valid_assets(p)]
        found = list(dict.fromkeys(found))
        pinned = [p for p in found if p.name == PINNED_REVISION]
        if pinned or len(found) == 1:
            directory = (pinned or found)[0]
        elif found:
            raise ValueError("Several Korva checkpoints installed; choose one with --korva-assets: "
                             + ", ".join(map(str, found)))
        else:
            raise ValueError("Korva model assets not found (no automatic download). Pass --korva-assets or set "
                             f"OPENMONTAGE_KORVA_ASSETS to a local {HF_REPO} snapshot with onnx/ and voice_styles/")
    return {"python": str(interpreter), "assets_dir": str(directory)}


def _sha256(path: Path) -> str:
    stat = path.stat()
    memo = (str(path), stat.st_size, stat.st_mtime_ns)
    if memo not in _HASHES:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        _HASHES[memo] = digest.hexdigest()
    return _HASHES[memo]


def model_identity(assets_dir: str, voice: str) -> dict:
    """Content identity of the checkpoint and preset actually used (for cache keys and reports)."""
    assets = Path(assets_dir)
    preset = assets / "voice_styles" / f"{voice}.json"
    if not preset.is_file():
        raise ValueError(f"Korva preset {voice!r} not found in {assets / 'voice_styles'}")
    files = {name: _sha256(assets / "onnx" / name) for name in ONNX_FILES}
    checkpoint = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    return {"source_repo": HF_REPO,
            "revision": assets.name if assets.parent.name == "snapshots" else None,
            "checkpoint_sha256": checkpoint, "onnx_files_sha256": files,
            "preset": voice, "preset_sha256": _sha256(preset),
            "license": "Apache-2.0 per publisher; training-data commercial rights not independently verified"}


class _Worker:
    """One Korva interpreter process with the model loaded once."""

    def __init__(self, python: str, assets: str, threads: int):
        self.key = (python, assets, threads)
        self.log = tempfile.TemporaryFile()
        env = os.environ.copy()
        env.update(PYTHONIOENCODING="utf-8", HF_HUB_OFFLINE="1", OMP_NUM_THREADS=str(threads))
        self.process = subprocess.Popen(
            [python, "-X", "utf8", str(WORKER), "--assets", assets, "--threads", str(threads)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log,
            text=True, encoding="utf-8", errors="replace", env=env)
        self.lines: queue.Queue = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()
        self.next_id = 0
        self.ready = self._read(STARTUP_TIMEOUT)
        if self.ready.get("event") != "ready":
            self.close()
            raise RuntimeError(f"Korva worker failed to start: {self.ready.get('error', self.ready)}")

    def _pump(self) -> None:
        for line in self.process.stdout:
            self.lines.put(line)
        self.lines.put(None)

    def _stderr_tail(self) -> str:
        try:
            self.log.seek(0)
            return self.log.read().decode("utf-8", "replace")[-1500:].strip()
        except (OSError, ValueError):
            return ""

    def _read(self, timeout: float) -> dict:
        try:
            line = self.lines.get(timeout=timeout)
        except queue.Empty:
            self.close()
            raise RuntimeError(f"Korva worker timed out after {timeout}s") from None
        if line is None:
            try:
                code = self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                code = "unknown"
            tail = self._stderr_tail()
            self.close()
            raise RuntimeError(f"Korva worker exited (code {code}){': ' + tail if tail else ''}")
        try:
            return json.loads(line)
        except ValueError:
            self.close()
            raise RuntimeError(f"Korva worker protocol error: {line[:200]!r}") from None

    def request(self, payload: dict) -> dict:
        self.next_id += 1
        payload = {**payload, "id": self.next_id}
        try:
            self.process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self.process.stdin.flush()
        except OSError as exc:
            reply = self._read(10)  # surfaces the exit code and stderr when the process died
            raise RuntimeError(f"Korva worker pipe failed: {exc}; {reply}") from exc
        reply = self._read(REQUEST_TIMEOUT)
        if reply.get("id") != payload["id"]:
            self.close()
            raise RuntimeError(f"Korva worker protocol error: unexpected reply {reply}")
        if not reply.get("ok"):
            raise RuntimeError(f"Korva synthesis failed: {reply.get('error')}")
        return reply

    def alive(self) -> bool:
        return self.process.poll() is None

    def close(self) -> None:
        if self.process.poll() is None:
            try:
                self.process.stdin.close()
                self.process.wait(timeout=10)
            except (OSError, subprocess.TimeoutExpired):
                self.process.kill()
                self.process.wait()
        self.log.close()


class KorvaTTS(BaseTool):
    """Vietnamese narration with a bundled KorvaTTS preset, run fully offline on CPU."""

    name = "korva_tts"
    version = "0.1.0"
    tier = ToolTier.VOICE
    capability = "tts"
    provider = "korva"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.SEEDED
    runtime = ToolRuntime.LOCAL

    dependencies = ["cmd:ffmpeg"]
    install_instructions = (
        "Install korvatts 0.1.3 into a separate Python 3.11 venv and fetch the pinned "
        f"{HF_REPO}@{PINNED_REVISION[:8]} onnx/ + voice_styles/ once (see docs/WINDOWS_STORY_TO_VIDEO.md). "
        "Point OPENMONTAGE_KORVA_PYTHON / OPENMONTAGE_KORVA_ASSETS (or --korva-python / --korva-assets) at them. "
        "Synthesis never downloads a model and never calls a network service."
    )
    agent_skills = ["text-to-speech"]
    capabilities = ["text_to_speech", "offline_generation", "wav_output"]
    supports = {
        "voice_cloning": False,
        "multilingual": "vietnamese_only",
        "offline": True,
        "native_audio": True,
    }
    best_for = ["offline Vietnamese story narration", "zero-cost local narration"]
    not_good_for = ["English narration", "voice cloning", "fast drafts on slow CPUs"]

    input_schema = {
        "type": "object",
        "required": ["text"],
        "properties": {
            "text": {"type": "string", "minLength": 1},
            "voice": {"type": "string", "default": DEFAULTS["voice"], "description": "Bundled preset name only"},
            "language_code": {"type": "string", "default": "vi"},
            "speed": {"type": "number", "minimum": SPEED_RANGE[0], "maximum": SPEED_RANGE[1],
                      "default": DEFAULTS["speed"]},
            "total_steps": {"type": "integer", "minimum": 1, "maximum": 32, "default": DEFAULTS["total_steps"]},
            "silence_between_chunks": {"type": "number", "minimum": 0,
                                       "default": DEFAULTS["silence_between_chunks"]},
            "seed": {"type": "integer", "default": DEFAULTS["seed"]},
            "num_threads": {"type": "integer", "minimum": 1},
            "python": {"type": "string", "description": "Korva interpreter (korvatts installed)"},
            "assets_dir": {"type": "string", "description": "Local snapshot with onnx/ and voice_styles/"},
            "output_path": {"type": "string"},
        },
    }
    resource_profile = ResourceProfile(cpu_cores=6, ram_mb=1024, vram_mb=0, disk_mb=400, network_required=False)
    idempotency_key_fields = ["text", "voice", "speed", "total_steps", "silence_between_chunks", "seed"]
    side_effects = ["writes WAV audio file to output_path"]
    user_visible_verification = ["Listen to narration for pronunciation, omissions and repetitions"]

    def __init__(self) -> None:
        super().__init__()
        self._worker: _Worker | None = None
        self._persistent = False

    def get_status(self) -> ToolStatus:
        if not shutil.which("ffmpeg"):
            return ToolStatus.UNAVAILABLE
        try:
            find_runtime()
        except ValueError:
            return ToolStatus.UNAVAILABLE
        return ToolStatus.AVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    def probe(self, python: str, assets: str) -> dict:
        """Import the SDK in the Korva runtime and list presets, without loading the model."""
        try:
            completed = subprocess.run([python, "-X", "utf8", str(WORKER), "--assets", assets, "--probe"],
                                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                                       timeout=120, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        except (OSError, subprocess.SubprocessError) as exc:
            raise ValueError(f"Korva runtime {python} could not start: {exc}") from exc
        try:
            reply = json.loads(completed.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            reply = {}
        if completed.returncode != 0 or reply.get("event") != "probe":
            detail = reply.get("error") or completed.stderr.strip()[-800:] or f"exit {completed.returncode}"
            raise ValueError(f"Korva runtime probe failed: {detail}")
        return reply

    @contextmanager
    def session(self):
        """Keep one worker (one model load) for every execute() inside the block."""
        self._persistent = True
        try:
            yield self
        finally:
            self._persistent = False
            self._close_worker()

    def _close_worker(self) -> None:
        if self._worker is not None:
            self._worker.close()
            self._worker = None

    def _acquire(self, python: str, assets: str, threads: int) -> _Worker:
        worker = self._worker
        if worker is None or not worker.alive() or worker.key != (python, assets, threads):
            self._close_worker()
            self._worker = worker = _Worker(python, assets, threads)
        return worker

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        text = inputs.get("text", "")
        if not text.strip():
            return ToolResult(success=False, error="Text is required for Korva TTS.")
        start = time.time()
        try:
            return self._synthesize(inputs, text, start)
        except (ValueError, OSError, RuntimeError, EOFError, wave.Error, subprocess.SubprocessError) as exc:
            self._close_worker()
            return ToolResult(success=False, error=f"Korva TTS failed: {exc}")
        finally:
            if not self._persistent:
                self._close_worker()

    def _synthesize(self, inputs: dict[str, Any], text: str, start: float) -> ToolResult:
        locale = inputs.get("language_code", "vi").replace("_", "-").lower()
        if locale != "vi" and not locale.startswith("vi-"):
            raise ValueError(f"Korva provider is validated for Vietnamese only, not {locale!r}; no voice fallback")
        voice = inputs.get("voice", DEFAULTS["voice"])
        if not re.fullmatch(r"[a-z0-9_]+", voice):
            raise ValueError(f"Korva voice must be a bundled preset name, got {voice!r}")
        settings = {key: inputs.get(key, default) for key, default in DEFAULTS.items() if key != "voice"}
        if not SPEED_RANGE[0] <= float(settings["speed"]) <= SPEED_RANGE[1]:
            raise ValueError(f"Korva speed must be between {SPEED_RANGE[0]} and {SPEED_RANGE[1]}")
        if int(settings["total_steps"]) != settings["total_steps"] or not 1 <= settings["total_steps"] <= 32:
            raise ValueError("Korva total_steps must be an integer between 1 and 32")
        if float(settings["silence_between_chunks"]) < 0:
            raise ValueError("Korva silence_between_chunks must be >= 0")
        output_path = Path(inputs.get("output_path", "tts_output.wav")).resolve()
        if output_path.suffix.lower() != ".wav":
            raise ValueError("output_path must end in .wav")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        runtime = find_runtime(inputs.get("python"), inputs.get("assets_dir"))
        if not (Path(runtime["assets_dir"]) / "voice_styles" / f"{voice}.json").is_file():
            raise ValueError(f"Korva preset {voice!r} is not installed; no voice fallback")
        worker = self._acquire(runtime["python"], runtime["assets_dir"],
                               int(inputs.get("num_threads") or default_threads()))
        with tempfile.TemporaryDirectory(prefix="openmontage-korva-") as temp_dir:
            raw = Path(temp_dir) / "native.wav"
            reply = worker.request({"text": text, "output_path": str(raw), "voice": voice, "lang": "vi",
                                    "total_steps": int(settings["total_steps"]),
                                    "speed": float(settings["speed"]),
                                    "silence_between_chunks": float(settings["silence_between_chunks"]),
                                    "seed": int(settings["seed"])})
            if not raw.is_file() or raw.stat().st_size == 0:
                raise ValueError("Korva worker reported success but wrote no WAV")
            audio_duration = normalize_wav(raw, output_path)
        generation = {key: reply[key] for key in ("synthesis_seconds", "chunks", "float_peak", "export_gain",
                                                  "sample_rate", "native_samples", "samples", "edge_trim")
                      if key in reply}
        generation["worker"] = {key: worker.ready.get(key) for key in
                                ("sdk_version", "python", "execution_provider", "load_seconds")}
        return ToolResult(
            success=True,
            data={"provider": self.provider, "voice": voice, "language_code": "vi", **settings,
                  "text_length": len(text), "output": str(output_path), "format": "wav", "local_only": True,
                  "audio_duration_seconds": audio_duration, "generation": generation},
            artifacts=[str(output_path)],
            model=f"korva:{voice}",
            cost_usd=0.0,
            seed=int(settings["seed"]),
            duration_seconds=round(time.time() - start, 2),
        )
