"""Canonical Short narration: resolved Short -> measured timeline -> SRT -> quality gates.

Pure functions over a validated Master Story Package (``lib/master_story.py``);
no TTS or file-system side effects except where a path is passed in. The driver
is ``scripts/master_story_short.py``. Nothing here rewrites narration: every beat
is one master segment with its original text and canonical references.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
import wave
from pathlib import Path

from lib import master_story as ms

TIMING_DEFAULTS = {"lead_in_seconds": 0.3, "gap_seconds": 0.4, "tail_seconds": 0.5}
# Marks used by Vietnamese but not by English or Portuguese names (checked after NFD):
# dot below, hook above, horn, breve; plus d with stroke.
_VI_MARKS = re.compile("[" + "".join(map(chr, (0x323, 0x309, 0x31B, 0x306, 0x111, 0x110))) + "]")
_SENTENCE = re.compile(r"(?<=[.!?:" + chr(0x2026) + r"])\s+")


class ShortNarrationError(ValueError):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("\n".join(problems))


def narration_language(package: dict) -> str:
    """Declared package language, cross-checked against the segment text (vi/en only)."""
    declared = package["language"].split("-")[0]
    text = " ".join(s["text"] for s in package["master_narrative"]["segments"])
    vietnamese = bool(_VI_MARKS.search(unicodedata.normalize("NFD", text)))
    if declared == "vi" and not vietnamese:
        raise ShortNarrationError(["LANGUAGE package declares vi but narration has no Vietnamese letters"])
    if declared == "en" and vietnamese:
        raise ShortNarrationError(["LANGUAGE package declares en but narration contains Vietnamese letters"])
    if declared not in ("vi", "en"):
        raise ShortNarrationError([f"LANGUAGE {declared!r} has no verified offline narration provider"])
    return declared


def canonical_beats(package: dict, name: str = "short") -> list[dict]:
    """One beat per format segment, carrying every canonical reference the segment uses."""
    ms.validate_package(package)
    view = ms.resolve_format(package, name)
    claims = {c["id"]: c for c in package["claims"]}
    entities = {e["id"]: (kind, e) for kind, rows in package["entities"].items() for e in rows}
    segments = {s["id"]: s for s in package["master_narrative"]["segments"]}
    beats = []
    for order, seg_id in enumerate(package["formats"][name]["segment_ids"], 1):
        seg = segments[seg_id]
        used = [claims[c] for c in seg["claim_ids"]]
        refs = {"characters": [], "locations": [], "objects": []}
        for e in seg.get("entity_ids", []):
            refs[entities[e][0]].append(e)
        rules = [r["id"] for r in view["continuity_rules"]
                 if set(r.get("when_claim_ids", []) + r.get("claim_ids", [])) & set(seg["claim_ids"])]
        beats.append({
            "order": order, "segment_id": seg_id, "role": seg["role"], "text": seg["text"],
            "claims": [{k: c[k] for k in ("id", "status", "supporting_source_ids", "contradicting_source_ids",
                                          "qualifier") if k in c} for c in used],
            "claim_ids": list(seg["claim_ids"]),
            "source_ids": sorted({s for c in used for s in c["supporting_source_ids"] + c.get("contradicting_source_ids", [])}),
            "cited_source_ids": list(seg.get("source_ids", [])),
            "entity_ids": refs, "event_ids": list(seg.get("event_ids", [])),
            "continuity_rule_ids": rules})
    return beats


def wav_samples(path: Path) -> tuple[int, int]:
    with wave.open(str(path), "rb") as audio:
        if (audio.getnchannels(), audio.getsampwidth()) != (1, 2):
            raise ValueError(f"{path} is not mono PCM16")
        frames = audio.getnframes()
        if not frames or len(audio.readframes(frames)) != frames * 2:
            raise ValueError(f"{path} has no or truncated PCM data")
        return frames, audio.getframerate()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_timeline(beats: list[dict], wavs: dict[str, Path], timing: dict | None = None) -> dict:
    """Place beats back to back from measured WAV sample counts; no estimated durations."""
    timing = {**TIMING_DEFAULTS, **(timing or {})}
    cursor, timed = timing["lead_in_seconds"], []
    for i, beat in enumerate(beats):
        frames, rate = wav_samples(wavs[beat["segment_id"]])
        duration = frames / rate
        if i:
            cursor += timing["gap_seconds"]
        timed.append({**beat, "audio": {"path": str(wavs[beat["segment_id"]]),
                                        "sha256": sha256(wavs[beat["segment_id"]]), "samples": frames,
                                        "sample_rate": rate, "duration_seconds": duration},
                      "start_seconds": round(cursor, 6), "end_seconds": round(cursor + duration, 6)})
        cursor += duration
    total = cursor + timing["tail_seconds"]
    return {"timing_policy": timing, "speech_seconds": sum(b["audio"]["duration_seconds"] for b in timed),
            "total_seconds": round(total, 6), "beats": timed}


def subtitle_segments(timed: dict) -> list[dict]:
    """Sentence cues inside each measured beat window; times split by character share (not word alignment)."""
    cues = []
    for beat in timed["beats"]:
        sentences = [s for s in _SENTENCE.split(beat["text"]) if s.strip()]
        start, span = beat["start_seconds"], beat["end_seconds"] - beat["start_seconds"]
        weights = [len(s) for s in sentences]
        for sentence, weight in zip(sentences, weights):
            end = start + span * weight / sum(weights)
            cues.append({"segment_id": beat["segment_id"], "text": sentence, "start": round(start, 3), "end": round(end, 3)})
            start = end
        cues[-1]["end"] = round(beat["end_seconds"], 3)
    return cues


def write_concatenated_wav(timed: dict, output: Path) -> float:
    """One narration track (lead-in, beats, gaps, tail) at the beats' common sample rate."""
    rates = {b["audio"]["sample_rate"] for b in timed["beats"]}
    if len(rates) != 1:
        raise ValueError(f"beats use different sample rates: {sorted(rates)}")
    rate = rates.pop()
    frames = bytearray()
    for beat in timed["beats"]:
        frames += b"\x00\x00" * (int(round(beat["start_seconds"] * rate)) - len(frames) // 2)
        with wave.open(beat["audio"]["path"], "rb") as audio:
            frames += audio.readframes(audio.getnframes())
    frames += b"\x00\x00" * (int(round(timed["total_seconds"] * rate)) - len(frames) // 2)
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(bytes(frames))
    return len(frames) // 2 / rate


_SRT_CUE = re.compile(r"(\d+)\r?\n(\d\d):(\d\d):(\d\d),(\d{3}) --> (\d\d):(\d\d):(\d\d),(\d{3})\r?\n(.*?)(?:\r?\n\r?\n|\s*$)", re.S)


def parse_srt(text: str) -> list[dict]:
    seconds = lambda h, m, s, ms_: int(h) * 3600 + int(m) * 60 + int(s) + int(ms_) / 1000
    return [{"start": seconds(*m.group(2, 3, 4, 5)), "end": seconds(*m.group(6, 7, 8, 9)), "text": m.group(10).strip()}
            for m in _SRT_CUE.finditer(text)]


def quality_gates(package: dict, timed: dict, srt_text: str, name: str = "short",
                  track: Path | None = None) -> dict:
    """Automatic gates; returns {gate: {"pass": bool, ...}} and never approves facts or publication."""
    plan = package["formats"][name]
    segments = {s["id"]: s for s in package["master_narrative"]["segments"]}
    claims = {c["id"]: c for c in package["claims"]}
    beats = timed["beats"]
    ids = [b["segment_id"] for b in beats]
    gates = {}
    gates["segments_complete"] = {"pass": ids == plan["segment_ids"],
                                  "missing": [s for s in plan["segment_ids"] if s not in ids],
                                  "duplicated": sorted({s for s in ids if ids.count(s) > 1}),
                                  "unexpected": [s for s in ids if s not in plan["segment_ids"]]}
    changed = [b["segment_id"] for b in beats if b["segment_id"] in segments and b["text"] != segments[b["segment_id"]]["text"]]
    gates["text_verbatim"] = {"pass": not changed, "changed": changed}
    expected_claims = ms.format_claims(package, plan)
    used = {c for b in beats for c in b["claim_ids"]}
    claim_drift = [b["segment_id"] for b in beats if b["segment_id"] in segments
                   and b["claim_ids"] != segments[b["segment_id"]]["claim_ids"]]
    expected_sources = {s for c in expected_claims for s in claims[c]["supporting_source_ids"] + claims[c].get("contradicting_source_ids", [])}
    used_sources = {s for b in beats for s in b["source_ids"]}
    gates["no_new_claims_or_sources"] = {"pass": used == expected_claims and not claim_drift and used_sources == expected_sources,
                                         "extra_claims": sorted(used - expected_claims),
                                         "missing_claims": sorted(expected_claims - used),
                                         "segments_with_changed_claims": claim_drift,
                                         "extra_sources": sorted(used_sources - expected_sources)}
    altered = [c["id"] for b in beats for c in b["claims"]
               if c["id"] not in claims or c["status"] != claims[c["id"]]["status"]
               or c.get("qualifier") != claims[c["id"]].get("qualifier")]
    try:
        rule_problems = ms._rule_problems(package, used, "timed short")
    except KeyError as exc:
        rule_problems = [f"unresolved claim {exc}"]
    gates["qualifiers_and_continuity"] = {"pass": not altered and not rule_problems, "altered_claims": altered,
                                          "violations": rule_problems,
                                          "pass_covers": "automatic checks only",
                                          "human_review_rules": {r: "pending_human_review" for r in sorted(
                                              {r for b in beats for r in b["continuity_rule_ids"]
                                               if next(x for x in package["continuity_rules"] if x["id"] == r)["check"] == "human_review"})}}
    audio_problems = []
    for b in beats:
        try:
            frames, rate = wav_samples(Path(b["audio"]["path"]))
            if frames != b["audio"]["samples"] or rate != b["audio"]["sample_rate"]:
                audio_problems.append(f"{b['segment_id']}: manifest samples differ from file")
            if abs(b["end_seconds"] - b["start_seconds"] - frames / rate) > 1e-5:
                audio_problems.append(f"{b['segment_id']}: window differs from measured audio")
        except (OSError, ValueError, EOFError, wave.Error) as exc:
            audio_problems.append(f"{b['segment_id']}: {exc}")
    order = all(a["end_seconds"] <= b["start_seconds"] for a, b in zip(beats, beats[1:]))
    if track is not None:
        frames, rate = wav_samples(track)
        if abs(frames / rate - timed["total_seconds"]) > 1 / rate + 1e-6:
            audio_problems.append("concatenated track length differs from timeline total")
    gates["audio_measured"] = {"pass": not audio_problems and order, "problems": audio_problems, "ordered": order}
    cues = parse_srt(srt_text)
    srt_problems = []
    for b in beats:
        inside = [c for c in cues if b["start_seconds"] - 0.002 <= c["start"] and c["end"] <= b["end_seconds"] + 0.002]
        if " ".join(" ".join(c["text"].split()) for c in inside) != " ".join(b["text"].split()):
            srt_problems.append(f"{b['segment_id']}: subtitle text differs from narration")
    if any(c["end"] <= c["start"] for c in cues) or any(a["end"] > b["start"] + 0.001 for a, b in zip(cues, cues[1:])):
        srt_problems.append("cues overlap or have non-positive duration")
    if " ".join(c["text"] for c in cues).split() != " ".join(b["text"] for b in beats).split():
        srt_problems.append("subtitle text is not exactly the narration text in order")
    gates["subtitles_aligned"] = {"pass": not srt_problems, "cues": len(cues), "problems": srt_problems}
    low, high = plan["target_seconds"]["min"], plan["target_seconds"]["max"]
    total = timed["total_seconds"]
    gate = {"pass": low <= total <= high, "total_seconds": round(total, 3),
            "speech_seconds": round(timed["speech_seconds"], 3), "target": [low, high]}
    if total > high:
        gate["over_by_seconds"] = round(total - high, 3)
    if total < low:
        gate["under_by_seconds"] = round(low - total, 3)
    gate["longest_segments"] = [{"segment_id": b["segment_id"], "seconds": round(b["audio"]["duration_seconds"], 3)}
                                for b in sorted(beats, key=lambda b: -b["audio"]["duration_seconds"])[:3]]
    gates["duration_target"] = gate
    return gates
