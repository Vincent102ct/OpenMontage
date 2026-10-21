"""Deterministic local sound effects synthesized with FFmpeg lavfi sources.

Named recipes only: no samples, network, credentials or model downloads.
"""
from __future__ import annotations

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

# Each recipe is a lavfi graph producing mono audio; {d} is the duration in seconds.
RECIPES = {
    "room_tone": "anoisesrc=color=brown:amplitude=0.06:seed=7:d={d},lowpass=f=320,highpass=f=35",
    "fridge_hum": ("sine=f=50:d={d},volume=0.35[a];sine=f=100:d={d},volume=0.18[b];"
                   "anoisesrc=color=pink:amplitude=0.02:seed=11:d={d},lowpass=f=900[c];"
                   "[a][b][c]amix=inputs=3:normalize=0,tremolo=f=0.4:d=0.2"),
    "tap_water": ("anoisesrc=color=white:amplitude=0.35:seed=3:d={d},highpass=f=500,"
                  "lowpass=f=5200,tremolo=f=11:d=0.35"),
    "ceramic_clink": ("aevalsrc=exprs='0.45*exp(-30*t)*sin(2*PI*2093*t)+0.25*exp(-38*t)*sin(2*PI*3371*t)"
                      "+0.14*exp(-52*t)*sin(2*PI*5227*t)':s=48000:d={d}"),
    "footstep": ("aevalsrc=exprs='0.55*exp(-42*t)*sin(2*PI*82*t)+0.25*exp(-60*t)*sin(2*PI*147*t)':s=48000:d={d},"
                 "lowpass=f=1200"),
    "fridge_door_open": ("aevalsrc=exprs='0.5*exp(-55*t)*sin(2*PI*170*t)+0.18*exp(-9*t)*sin(2*PI*61*t)':s=48000:d={d}[a];"
                         "anoisesrc=color=pink:amplitude=0.12:seed=5:d={d},lowpass=f=700,afade=t=out:st=0:d={d}[b];"
                         "[a][b]amix=inputs=2:normalize=0"),
    "low_drone": ("sine=f=55:d={d},volume=0.3[a];sine=f=82.4:d={d},volume=0.16[b];"
                  "[a][b]amix=inputs=2:normalize=0,tremolo=f=0.25:d=0.4,lowpass=f=400"),
    # Generic story cues (story_planner); additive, the recipes above are unchanged.
    "rain": ("anoisesrc=color=pink:amplitude=0.32:seed=21:d={d},highpass=f=900,lowpass=f=7000[a];"
             "anoisesrc=color=white:amplitude=0.08:seed=22:d={d},highpass=f=3000,tremolo=f=17:d=0.6[b];"
             "[a][b]amix=inputs=2:normalize=0"),
    "street_ambience": ("anoisesrc=color=brown:amplitude=0.09:seed=31:d={d},lowpass=f=450,highpass=f=40[a];"
                        "sine=f=92:d={d},volume=0.03[b];[a][b]amix=inputs=2:normalize=0,tremolo=f=0.1:d=0.3"),
    "knock": ("aevalsrc=exprs='0.8*exp(-60*t)*sin(2*PI*180*t)+0.3*exp(-90*t)*sin(2*PI*420*t)':s=48000:d={d},"
              "lowpass=f=2000"),
    "door_open": ("aevalsrc=exprs='0.18*sin(2*PI*(310+90*sin(2*PI*1.3*t))*t)*exp(-2.5*t)':s=48000:d={d}[a];"
                  "aevalsrc=exprs='0.5*exp(-30*abs(t-0.12))*sin(2*PI*95*t)':s=48000:d={d}[b];"
                  "[a][b]amix=inputs=2:normalize=0,lowpass=f=2500"),
    "engine": ("sine=f=38:d={d},volume=0.35[a];anoisesrc=color=brown:amplitude=0.18:seed=41:d={d},"
               "lowpass=f=260[b];[a][b]amix=inputs=2:normalize=0,tremolo=f=9:d=0.3"),
    "paper": ("anoisesrc=color=white:amplitude=0.25:seed=51:d={d},highpass=f=1800,lowpass=f=8000,"
              "tremolo=f=23:d=0.9,afade=t=out:st=0:d={d}"),
    "switch": "aevalsrc=exprs='0.6*exp(-220*t)*sin(2*PI*2400*t)+0.3*exp(-150*t)*sin(2*PI*900*t)':s=48000:d={d}",
    "soft_place": "aevalsrc=exprs='0.5*exp(-35*t)*sin(2*PI*140*t)+0.15*exp(-60*t)*sin(2*PI*620*t)':s=48000:d={d}",
}


class ProceduralSFX(BaseTool):
    name = "procedural_sfx"
    version = "0.1.0"
    tier = ToolTier.CORE
    capability = "audio_processing"
    provider = "ffmpeg"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL
    dependencies = ["cmd:ffmpeg"]
    install_instructions = "Requires FFmpeg with lavfi sources (bundled in standard builds)."
    agent_skills = ["ffmpeg"]
    capabilities = ["sound_effects", "offline_generation", "wav_output"]
    supports = {"offline": True, "recipes": sorted(RECIPES)}
    best_for = ["Zero-cost room tone, hums, footsteps, water and contact sounds for local drafts"]
    not_good_for = ["Realistic Foley replacement", "Music"]
    resource_profile = ResourceProfile(cpu_cores=1, ram_mb=64, vram_mb=0, disk_mb=5)
    input_schema = {
        "type": "object", "required": ["recipe", "duration_seconds", "output_path"],
        "properties": {
            "recipe": {"type": "string", "enum": sorted(RECIPES)},
            "duration_seconds": {"type": "number", "exclusiveMinimum": 0, "maximum": 600},
            "fade_seconds": {"type": "number", "minimum": 0, "default": 0},
            "output_path": {"type": "string"},
        },
    }
    side_effects = ["Writes one 48 kHz mono WAV to output_path"]
    user_visible_verification = ["Listen to the cue in context; verify duration and non-silent samples"]

    def get_status(self) -> ToolStatus:
        return ToolStatus.AVAILABLE if shutil.which("ffmpeg") else ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        if self.get_status() != ToolStatus.AVAILABLE:
            return ToolResult(success=False, error=self.install_instructions)
        start = time.monotonic()
        try:
            recipe = inputs["recipe"]
            if recipe not in RECIPES:
                raise ValueError(f"Unknown recipe {recipe!r}")
            duration = float(inputs["duration_seconds"])
            fade = float(inputs.get("fade_seconds", 0))
            if not 0 < duration <= 600 or not 0 <= fade <= duration / 2:
                raise ValueError("Duration must be in (0, 600] and fade at most half of it")
            output = Path(inputs["output_path"]).resolve()
            if output.suffix.lower() != ".wav":
                raise ValueError("output_path must end in .wav")
            output.parent.mkdir(parents=True, exist_ok=True)
            graph = RECIPES[recipe].format(d=f"{duration:.3f}")
            if fade:
                graph += f",afade=t=in:d={fade:.3f},afade=t=out:st={duration - fade:.3f}:d={fade:.3f}"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-filter_complex", graph + ",aformat=channel_layouts=mono",
                            "-t", f"{duration:.3f}", "-ar", "48000", "-c:a", "pcm_s16le", str(output)],
                           capture_output=True, text=True, check=True, timeout=120)
            with wave.open(str(output), "rb") as audio:
                frames = audio.readframes(audio.getnframes())
                measured = audio.getnframes() / audio.getframerate()
            if not frames or max(frames) == 0:
                raise ValueError("Synthesized cue is silent")
        except (KeyError, ValueError, OSError, EOFError, wave.Error, subprocess.SubprocessError) as exc:
            return ToolResult(success=False, error=f"Procedural SFX failed: {exc}")
        return ToolResult(success=True, data={"output": str(output), "recipe": recipe, "format": "wav",
                          "audio_duration_seconds": measured, "local_only": True},
                          artifacts=[str(output)], model=f"ffmpeg-lavfi:{recipe}", cost_usd=0,
                          duration_seconds=round(time.monotonic() - start, 2))
