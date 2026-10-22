"""Canonical timed narration + authored shot directions -> unresolved visual plan.

Creative choices live in the brief, not story-specific Python rules. This module
validates references/timing and compiles a deterministic contract for a future
asset resolver. It never calls TTS, acquires media, approves facts or renders.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path

import jsonschema

from lib import master_story as ms
from lib import master_story_short as mss

SCHEMAS = Path(__file__).resolve().parents[1] / "schemas/story"
PENDING = "pending_human_review"
SOURCE_PRIORITY = ["authentic_historical_evidence", "public_domain_institutional",
                   "wikimedia_commons_verified_license", "freely_licensed_media",
                   "local_media_library", "ai_reconstruction_future_fallback"]
TIMING = {"internal_cuts": "character_distributed_subtitle_estimates", "word_alignment_verified": False,
          "lead_in": "hold_first_scene", "inter_segment_gaps": "hold_preceding_scene", "tail": "hold_last_scene"}
CANON_FIELDS = ("claims", "sources", "entities", "events", "continuity_rules")
TOLERANCE = 0.000002  # M2.2 rounds measured windows to six decimal places.


class VisualScenePlanError(ValueError):
    """Invalid input/plan, with an actionable invariant rather than a silent fallback."""


def _require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise VisualScenePlanError(f"{code}: {message}")


def content_hash(data: dict) -> str:
    """Canonical JSON content fingerprint (not the source file's whitespace)."""
    try:
        encoded = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise VisualScenePlanError(f"JSON: {exc}") from exc
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _schema(data: dict, name: str = "visual_scene_plan.schema.json", definition: str | None = None) -> None:
    schema = json.loads((SCHEMAS / name).read_text(encoding="utf-8"))
    if definition:
        schema = {"$schema": schema["$schema"], "$defs": schema["$defs"], "$ref": f"#/$defs/{definition}"}
    try:
        jsonschema.Draft202012Validator(schema).validate(data)
    except jsonschema.ValidationError as exc:
        raise VisualScenePlanError(f"SCHEMA {'/'.join(map(str, exc.absolute_path))}: {exc.message}") from exc


def _rules(package: dict, claim_ids: list[str]) -> list[str]:
    return [r["id"] for r in package["continuity_rules"]
            if set(r.get("when_claim_ids", []) + r.get("claim_ids", [])) & set(claim_ids)]


def _context(package: dict) -> dict:
    view = ms.resolve_format(package, "short")
    return copy.deepcopy({key: view[key] for key in CANON_FIELDS})


def _inputs(package: dict, timed: dict, brief: dict) -> dict:
    return {"package_content_sha256": content_hash(package), "timed_manifest_content_sha256": content_hash(timed),
            "brief_content_sha256": content_hash(brief),
            "narration_track": copy.deepcopy(timed["narration_track"]), "subtitles": copy.deepcopy(timed["subtitles"])}


def validate_timed_manifest(package: dict, timed: dict) -> None:
    """Pure M2.2 contract checks; on-disk PCM/hash verification is a separate step."""
    ms.validate_package(package)
    content_hash(timed)  # Reject NaN/infinity, including nested values, before arithmetic.
    _schema(timed, "timed_format_manifest.schema.json")
    _require(timed["format"] == "short" and timed["aspect_ratio"] == "9:16", "FORMAT", "Long planning is not implemented in M2.3")
    for key in ("package_id", "package_version", "language"):
        _require(timed[key] == package[key], "PACKAGE", f"manifest changed {key}")
    expected = mss.canonical_beats(package)
    _require(len(expected) == len(timed["beats"]), "SEGMENTS", "manifest does not match the selected format")
    policy = timed["timing_policy"]
    cursor, speech = policy["lead_in_seconds"], 0.0
    rates = set()
    for canonical, beat in zip(expected, timed["beats"]):
        for key, value in canonical.items():
            _require(beat[key] == value, "CANON", f"{canonical['segment_id']} changed {key}")
        if beat["order"] > 1:
            cursor += policy["gap_seconds"]
        audio = beat["audio"]
        seconds = audio["samples"] / audio["sample_rate"]
        rates.add(audio["sample_rate"])
        _require(abs(audio["duration_seconds"] - seconds) <= TOLERANCE, "MEASUREMENT", f"{beat['segment_id']} sample duration drift")
        _require(abs(beat["start_seconds"] - cursor) <= TOLERANCE and
                 abs(beat["end_seconds"] - (cursor + seconds)) <= TOLERANCE,
                 "TIMELINE", f"{beat['segment_id']} differs from samples/pause policy")
        cursor += seconds
        speech += seconds
    _require(len(rates) == 1, "MEASUREMENT", "mixed sample rates")
    _require(abs(speech - timed["speech_seconds"]) <= TOLERANCE and
             abs(cursor + policy["tail_seconds"] - timed["total_seconds"]) <= TOLERANCE,
             "TIMELINE", "speech/total differs from measured timeline")
    target = package["formats"]["short"]["target_seconds"]
    _require(target["min"] <= timed["total_seconds"] <= target["max"], "DURATION", "measured Short is outside its approved target")


def _cue_map(timed: dict, srt_text: str) -> dict[str, list[dict]]:
    # read_text() normalizes Windows CRLF. Accept the two newline encodings of
    # the exact same text, never altered timings/text under an old file hash.
    normalized = srt_text.replace("\r\n", "\n")
    hashes = {hashlib.sha256(value.encode("utf-8")).hexdigest()
              for value in (srt_text, normalized, normalized.replace("\n", "\r\n"))}
    _require(timed["subtitles"]["sha256"] in hashes, "SUBTITLES_HASH", "cue content differs from declared SRT")
    cues = mss.parse_srt(srt_text)
    _require(bool(cues), "SUBTITLES", "no valid cues")
    _require(all(c["end"] > c["start"] for c in cues) and
             all(a["end"] <= b["start"] for a, b in zip(cues, cues[1:])), "SUBTITLES", "cues overlap or are not positive")
    mapping, consumed = {}, []
    for beat in timed["beats"]:
        inside = [(i, c) for i, c in enumerate(cues, 1)
                  if beat["start_seconds"] - .002 <= c["start"] and c["end"] <= beat["end_seconds"] + .002]
        _require(bool(inside), "SUBTITLES", f"{beat['segment_id']} has no cues")
        _require(abs(inside[0][1]["start"] - beat["start_seconds"]) <= .002 and
                 abs(inside[-1][1]["end"] - beat["end_seconds"]) <= .002 and
                 all(abs(a[1]["end"] - b[1]["start"]) <= .002 for a, b in zip(inside, inside[1:])),
                 "SUBTITLES", f"{beat['segment_id']} cue coverage drift")
        cursor, mapped = 0, []
        for number, cue in inside:
            position = beat["text"].find(cue["text"], cursor)
            _require(position >= cursor and not beat["text"][cursor:position].strip(),
                     "SUBTITLES", f"{beat['segment_id']} cue text is not verbatim")
            mapped.append({**cue, "number": number, "char_start": position})
            cursor = position + len(cue["text"])
            consumed.append(number)
        _require(not beat["text"][cursor:].strip(), "SUBTITLES", f"{beat['segment_id']} has uncaptioned narration")
        mapped[0]["char_start"] = 0
        mapping[beat["segment_id"]] = mapped
    _require(consumed == list(range(1, len(cues)+1)), "SUBTITLES", "unused, reordered or multiply assigned cues")
    return mapping


def verify_timed_files(package: dict, timed: dict, media_root: Path) -> tuple[str, dict]:
    """Read existing audio/SRT only; reuse M2.2 gates and verify every declared hash."""
    validate_timed_manifest(package, timed)
    resolved = copy.deepcopy(timed)
    def path(value):
        p = Path(value)
        return p if p.is_absolute() else media_root / p
    files = [timed["narration_track"], timed["subtitles"]] + [b["audio"] for b in timed["beats"]]
    for file in files:
        _require(mss.sha256(path(file["path"])) == file["sha256"], "FILE_HASH", f"changed input {file['path']}")
    for beat in resolved["beats"]:
        beat["audio"]["path"] = str(path(beat["audio"]["path"]))
    srt = path(timed["subtitles"]["path"]).read_text(encoding="utf-8")
    gates = mss.quality_gates(package, resolved, srt, track=path(timed["narration_track"]["path"]))
    _require(all(g["pass"] for g in gates.values()), "INPUT_GATE", str([k for k, g in gates.items() if not g["pass"]]))
    _cue_map(timed, srt)
    return srt, {"file_hashes_verified": len(files), "wav_files_measured": len(timed["beats"])+1, "M2.2_gates": gates}


def _validate_brief(package: dict, timed: dict, brief: dict, cue_map: dict) -> None:
    _schema(brief, definition="brief")
    for key in ("package_id", "package_version", "format"):
        _require(brief[key] == timed[key], "BRIEF", f"wrong {key}")
    beats = {b["segment_id"]: b for b in timed["beats"]}
    entities = {e["id"]: e for group in package["entities"].values() for e in group}
    events = {e["id"]: e for e in package["timeline"]}
    ids, alternative_ids, coverage, used = set(), set(), [], {sid: set() for sid in beats}
    for d in brief["directions"]:
        _require(d["id"] not in ids, "SCENE_ID", f"duplicate {d['id']}")
        ids.add(d["id"])
        sid = d["segment_id"]
        _require(sid in beats, "SEGMENT_REF", sid)
        beat = beats[sid]
        start, end = d["cue_start"], d["cue_end"]
        _require(1 <= start <= end <= len(cue_map[sid]), "CUE_RANGE", d["id"])
        coverage.extend((sid, number) for number in range(start, end+1))
        _require(set(d["claim_ids"]) <= set(beat["claim_ids"]), "CLAIM_REF", d["id"])
        used[sid].update(d["claim_ids"])
        element_ids = [e["entity_id"] for e in d["required_elements"]]
        allowed = {e for group in beat["entity_ids"].values() for e in group}
        _require(len(element_ids) == len(set(element_ids)) and set(element_ids) <= allowed, "ENTITY_REF", d["id"])
        for eid in element_ids:
            _require(bool(set(entities[eid]["claim_ids"]) & set(d["claim_ids"])), "ENTITY_GROUNDING", f"{d['id']} -> {eid}")
        _require(set(d["event_ids"]) <= set(beat["event_ids"]), "EVENT_REF", d["id"])
        for eid in d["event_ids"]:
            _require(bool(set(events[eid]["claim_ids"]) & set(d["claim_ids"])), "EVENT_GROUNDING", f"{d['id']} -> {eid}")
        roles = {o["role"] for o in d["on_screen_text"]}
        if d["representation"] == "contextual_material":
            _require("context_label" in roles, "CONTEXT_LABEL", d["id"])
        visual_pause = d["shot"]["type"] == "visual_pause"
        if visual_pause:
            # Production-only flat field, never an unlabelled historical depiction.
            _require(d["representation"] == "illustration" and not d["required_elements"] and
                     not d["on_screen_text"] and "presentation" in d and
                     not d["presentation"]["text_blocks"] and
                     all(r["media_type"] == "typography" and
                         r.get("production", {}).get("kind") == "local_graphic"
                         for r in d["asset_requests"]), "VISUAL_PAUSE", d["id"])
        if d["representation"] in ("illustration", "reconstruction") and not visual_pause:
            _require("evidence_label" in roles, "EVIDENCE_LABEL", d["id"])
        for request in d["asset_requests"]:
            if request["preferred_category"] == "ai_reconstruction_future_fallback":
                _require(d["representation"] == "reconstruction", "RECONSTRUCTION", d["id"])
            production = request.get("production", {})
            kind = production.get("kind", _production_kind(request, d["representation"]))
            if kind == "local_graphic":
                _require(request["media_type"] in ("diagram", "typography") and d["representation"] == "illustration",
                         "LOCAL_GRAPHIC", d["id"] + " must not present designed graphics as authentic evidence")
                _require(production.get("recipe_status", "not_implemented") == "not_implemented", "LOCAL_RECIPE", d["id"])
            if kind == "reconstruction":
                _require(d["representation"] == "reconstruction" and production.get("separate_approval_required", True),
                         "RECONSTRUCTION", d["id"])
            if kind == "external_media":
                _require(request["media_type"] not in ("diagram", "typography"), "EXTERNAL_MEDIA", d["id"])
            local_alternatives = {a["id"] for a in request.get("alternatives", [])}
            for alternative in request.get("alternatives", []):
                _require(alternative["id"] not in alternative_ids, "ALTERNATIVE_ID", alternative["id"])
                alternative_ids.add(alternative["id"])
                if alternative["kind"] == "reconstruction":
                    _require(alternative["representation"] == "reconstruction" and
                             alternative["preferred_category"] == "ai_reconstruction_future_fallback", "RECONSTRUCTION", alternative["id"])
                else:
                    _require(alternative["representation"] in ("authentic_evidence", "contextual_material") and
                             alternative["preferred_category"] != "ai_reconstruction_future_fallback", "ALTERNATIVE_TYPE", alternative["id"])
            if production.get("role") == "conditional_fallback":
                _require(kind == "local_graphic" and production.get("fallback_for") in local_alternatives,
                         "FALLBACK_REF", d["id"])
            else:
                _require("fallback_for" not in production, "FALLBACK_REF", d["id"])
    expected = [(sid, number) for sid in beats for number in range(1, len(cue_map[sid])+1)]
    _require(coverage == expected, "CUE_COVERAGE", "directions omit, duplicate or reorder canonical narration")
    for sid, claims in used.items():
        _require(claims == set(beats[sid]["claim_ids"]), "CLAIM_COVERAGE", sid)


def _production_kind(request: dict, representation: str) -> str:
    if representation == "reconstruction":
        return "reconstruction"
    return "local_graphic" if request["media_type"] in ("diagram", "typography") else "external_media"


def _inside(inner: dict, outer: dict) -> bool:
    return (outer["x"] <= inner["x"] and outer["y"] <= inner["y"] and
            inner["x"] + inner["width"] <= outer["x"] + outer["width"] and
            inner["y"] + inner["height"] <= outer["y"] + outer["height"])


def _overlap(a: dict, b: dict) -> bool:
    return (a["x"] < b["x"] + b["width"] and b["x"] < a["x"] + a["width"] and
            a["y"] < b["y"] + b["height"] and b["y"] < a["y"] + a["height"])


def _validate_presentation(scene: dict) -> None:
    """Geometry/timing check only: actual font fit and human reading stay separate."""
    if "presentation" not in scene:
        return
    p = scene["presentation"]
    canvas = {"x": 0, "y": 0, **p["canvas"]}
    safe, subtitles = p["safe_area"], p["subtitle_reserved"]
    def luminance(color):
        rgb = [int(color[i:i+2], 16)/255 for i in (1, 3, 5)]
        linear = [v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in rgb]
        return sum(v*w for v, w in zip(linear, (.2126, .7152, .0722)))
    colors = sorted([luminance(p["text_color"]), luminance(p["background_color"])])
    _require((colors[1]+.05)/(colors[0]+.05) >= 4.5, "TEXT_CONTRAST", scene["id"])
    _require(_inside(safe, canvas) and _inside(subtitles, canvas) and not _overlap(safe, subtitles),
             "SAFE_AREA", scene["id"])
    blocks = p["text_blocks"]
    indices = [b["overlay_index"] for b in blocks]
    _require(sorted(indices) == list(range(len(scene["on_screen_text"]))), "TEXT_INDEX", scene["id"])
    duration = scene["end_seconds"] - scene["start_seconds"]
    for block in blocks:
        _require(0 <= block["start_offset"] < block["end_offset"] <= duration + TOLERANCE,
                 "TEXT_TIMING", scene["id"])
        _require(_inside(block["box"], safe) and not _overlap(block["box"], subtitles), "TEXT_BOX", scene["id"])
        _require(block["font_size_px"] <= block["line_height_px"] and
                 block["line_height_px"] * block["max_lines"] <= block["box"]["height"], "TEXT_LINES", scene["id"])
    for i, a in enumerate(blocks):
        for b in blocks[i+1:]:
            simultaneous = max(a["start_offset"], b["start_offset"]) < min(a["end_offset"], b["end_offset"]) - TOLERANCE
            _require(not simultaneous or not _overlap(a["box"], b["box"]), "TEXT_COLLISION", scene["id"])
            both_questions = all(scene["on_screen_text"][v["overlay_index"]]["role"] == "question" for v in (a, b))
            _require(not (both_questions and simultaneous), "PROGRESSIVE_QUESTIONS", scene["id"])


def _compile(package: dict, timed: dict, brief: dict, cue_map: dict) -> dict:
    beats = {b["segment_id"]: b for b in timed["beats"]}
    claims = {c["id"]: c for c in package["claims"]}
    scenes = []
    for d in brief["directions"]:
        beat, cues = beats[d["segment_id"]], cue_map[d["segment_id"]]
        first, last = d["cue_start"]-1, d["cue_end"]-1
        char_start = cues[first]["char_start"]
        char_end = cues[last+1]["char_start"] if last+1 < len(cues) else len(beat["text"])
        start = beat["start_seconds"] if first == 0 else cues[first]["start"]
        end = beat["end_seconds"] if last+1 == len(cues) else cues[last]["end"]
        source_ids = sorted({s for cid in d["claim_ids"] for s in claims[cid]["supporting_source_ids"] + claims[cid].get("contradicting_source_ids", [])})
        entity_ids = [e["entity_id"] for e in d["required_elements"]]
        flags = {"assets_unresolved", "editorial_review_pending", *d["risk_flags"]}
        if first or last+1 < len(cues):
            flags.add("internal_cut_timing_estimated")
        if d["representation"] != "authentic_evidence":
            flags.add(d["representation"] + "_not_documentary_evidence")
        if any(claims[c]["status"] == "UNKNOWN" for c in d["claim_ids"]):
            flags.add("unknown_claim_not_a_proven_action")
        assets = [{**copy.deepcopy(r), "requirement_id": f"REQ_{d['id']}_{i:02d}", "scene_id": d["id"],
                   "representation": d["representation"], "entity_ids": list(entity_ids), "evidence_source_ids": list(source_ids),
                   "status": "unresolved", "resolved_asset": None, "review_status": PENDING}
                  for i, r in enumerate(d["asset_requests"], 1)]
        scenes.append({"id": d["id"], "format": timed["format"], "segment_id": d["segment_id"],
            "start_seconds": start, "end_seconds": end,
            "narration": {"char_start": char_start, "char_end": char_end, "text": beat["text"][char_start:char_end],
                "subtitle_cue_numbers": [c["number"] for c in cues[first:last+1]], "start_seconds": start, "end_seconds": end,
                "timing_basis": "measured_segment_character_distributed_cues_not_word_alignment"},
            "claim_ids": list(d["claim_ids"]), "source_ids": source_ids, "entity_ids": entity_ids,
            "event_ids": list(d["event_ids"]), "continuity_rule_ids": _rules(package, d["claim_ids"]),
            "purpose": d["purpose"], "representation": d["representation"],
            "historical_evidence": copy.deepcopy([claims[c] for c in d["claim_ids"]]),
            "required_elements": copy.deepcopy(d["required_elements"]), "shot": copy.deepcopy(d["shot"]),
            "asset_requirements": assets, "on_screen_text": copy.deepcopy(d["on_screen_text"]),
            "risk_flags": sorted(flags), "review_status": PENDING})
        if "presentation" in d:
            scenes[-1]["presentation"] = copy.deepcopy(d["presentation"])
    scenes[0]["start_seconds"] = 0.0
    for i, scene in enumerate(scenes):
        scene["end_seconds"] = scenes[i+1]["start_seconds"] if i+1 < len(scenes) else timed["total_seconds"]
        _validate_presentation(scene)
    context = _context(package)
    return {"schema_version": "1.0", "package_id": timed["package_id"], "package_version": timed["package_version"],
            "language": timed["language"], "format": timed["format"], "aspect_ratio": timed["aspect_ratio"], "total_seconds": timed["total_seconds"],
            "inputs": _inputs(package, timed, brief), "timing": copy.deepcopy(TIMING), "source_priority": list(SOURCE_PRIORITY),
            "canon": context, "scenes": scenes, "approvals": {**timed["approvals"], "visual_plan": PENDING},
            "continuity_review": {r["id"]: PENDING for r in context["continuity_rules"] if r["check"] == "human_review"}}


def build_plan(package: dict, timed: dict, brief: dict, srt_text: str) -> dict:
    validate_timed_manifest(package, timed)
    cue_map = _cue_map(timed, srt_text)
    _validate_brief(package, timed, brief, cue_map)
    return _compile(package, timed, brief, cue_map)


def validate_plan(plan: dict, package: dict, timed: dict, brief: dict, srt_text: str) -> dict:
    """Validate stored plans as well as newly built ones; never mark human approval."""
    content_hash(plan)
    _schema(plan)
    validate_timed_manifest(package, timed)
    cue_map = _cue_map(timed, srt_text)
    _validate_brief(package, timed, brief, cue_map)
    _require(plan["inputs"] == _inputs(package, timed, brief), "INPUT_BINDING", "package/manifest/brief fingerprints changed")
    _require(plan["canon"] == _context(package), "CANON", "claim/source/entity/event/rule records changed")
    scenes = plan["scenes"]
    _require(len({s["id"] for s in scenes}) == len(scenes), "SCENE_ID", "duplicate ID")
    _require(plan["format"] == timed["format"] and plan["aspect_ratio"] == timed["aspect_ratio"] and
             plan["total_seconds"] == timed["total_seconds"], "FORMAT", "output changed format or duration")
    cursor = 0.0
    beats = {b["segment_id"]: b for b in timed["beats"]}
    for s in scenes:
        _require(math.isfinite(s["end_seconds"]) and s["start_seconds"] == cursor and
                 s["end_seconds"] > cursor and s["end_seconds"] <= timed["total_seconds"],
                 "COVERAGE", f"{s['id']} has a gap, overlap or out-of-range time")
        cursor = s["end_seconds"]
        _require(s["segment_id"] in beats, "SEGMENT_REF", s["id"])
        beat, n = beats[s["segment_id"]], s["narration"]
        _require(0 <= n["char_start"] < n["char_end"] <= len(beat["text"]) and
                 n["text"] == beat["text"][n["char_start"]:n["char_end"]], "NARRATION", s["id"])
        _require(s["start_seconds"] <= n["start_seconds"] < n["end_seconds"] <= s["end_seconds"], "NARRATION_TIME", s["id"])
    _require(cursor == timed["total_seconds"], "COVERAGE", "missing narration tail")
    # The authored brief is the approved editorial input, not an invitation for
    # downstream clients to silently reword a shot, switch evidence type or refs.
    _require(plan == _compile(package, timed, brief, cue_map), "PLAN_DRIFT", "scene span, references, assets or editorial direction differs from inputs")
    assets = [a for s in scenes for a in s["asset_requirements"]]
    return {"status": "technical_pass", "pass_covers": "contract, references, measured coverage; not factual/editorial/publication approval",
            "scenes": len(scenes), "segments": list(beats), "total_seconds": timed["total_seconds"],
            "coverage": {"start_seconds": 0, "end_seconds": cursor, "gaps": [], "overlaps": []},
            "claims": len(plan["canon"]["claims"]), "sources": len(plan["canon"]["sources"]),
            "unresolved_asset_requirements": len(assets), "media_ready": False,
            "production_breakdown": asset_breakdown(plan)["counts"],
            "continuity_review": copy.deepcopy(plan["continuity_review"]), "approvals": copy.deepcopy(plan["approvals"]),
            "word_alignment_verified": False,
            "warnings": ["Interior cuts follow character-distributed SRT estimates, not word-aligned evidence.",
                         "All assets unresolved; source IDs support claims, not licenses or possession of media.",
                         "Free-text historical accuracy and visual intent require human review."]}


def asset_breakdown(plan: dict) -> dict:
    """Classify existing requests, not resolved assets or implemented rendering recipes.

Legacy requests retain their scene JSON unchanged; kind is inferred only for
this export. Conditional fallbacks are a subset of local graphics, not an extra
set of assets to fabricate. Alternatives require a later separate decision.
"""
    groups = {key: [] for key in ("external_media", "local_graphics", "conditional_fallbacks", "reconstruction_requests")}
    for scene in plan["scenes"]:
        for request in scene["asset_requirements"]:
            production = request.get("production", {})
            kind = production.get("kind", _production_kind(request, scene["representation"]))
            row = {"id": request["requirement_id"], "scene_id": scene["id"], "scope": "current_storyboard",
                   "status": request["status"], "representation": request["representation"],
                   "recipe_status": production.get("recipe_status", "not_implemented" if kind == "local_graphic" else "not_applicable")}
            key = {"external_media": "external_media", "local_graphic": "local_graphics", "reconstruction": "reconstruction_requests"}[kind]
            groups[key].append(row)
            if production.get("role") == "conditional_fallback":
                groups["conditional_fallbacks"].append({**row, "fallback_for": production["fallback_for"]})
            for alternative in request.get("alternatives", []):
                key = "reconstruction_requests" if alternative["kind"] == "reconstruction" else "external_media"
                groups[key].append({"id": alternative["id"], "scene_id": scene["id"], "scope": "conditional_alternative",
                                    "status": alternative["status"], "representation": alternative["representation"],
                                    "activation_condition": alternative["activation_condition"], "separate_approval_required": True})
    return {"counts": {k: len(v) for k, v in groups.items()}, **groups,
            "all_assets_unresolved": True, "supported_local_rendering_recipes": 0,
            "asset_license_approval": PENDING, "note": "Conditional fallbacks are included in local_graphics; classification is not resolution."}


def storyboard_markdown(plan: dict) -> str:
    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", " ")
    lines = ["# Canonical visual storyboard — " + plan["package_id"], "",
             f"{plan['format']} / {plan['aspect_ratio']} / {plan['total_seconds']:.6f} s — pending_human_review", "",
             "Internal cuts are character-distributed subtitle estimates; lead/gaps/tail hold adjacent scenes.",
             "All asset requirements are unresolved, including proposed historical evidence. No media has been acquired.", "",
             "| Shot / segment | Time (s) | Exact narration span | Visual / framing / motion | Why this visual | Asset intent / overlay |",
             "|---|---|---|---|---|---|"]
    for s in plan["scenes"]:
        shot = s["shot"]
        visual = f"{shot['type']}: {shot['subject']}; {shot['framing']}; {shot['camera_motion']}; {shot['visual_action']}"
        assets = "; ".join(a["media_type"] + " / " + a["preferred_category"] + " / " +
                           a.get("production", {}).get("role", "primary") + " / unresolved" for a in s["asset_requirements"])
        overlay = "; ".join(o["role"] + ": " + o["text"] for o in s["on_screen_text"])
        lines.append("| " + " | ".join(map(cell, [s["id"]+" / "+s["segment_id"],
            f"{s['start_seconds']:.6f}–{s['end_seconds']:.6f}", s["narration"]["text"], visual,
            s["purpose"], s["representation"]+"; "+assets+"; "+overlay])) + " |")
    breakdown = asset_breakdown(plan)
    lines += ["", "## Media versus local graphics", "", json.dumps(breakdown["counts"], ensure_ascii=False),
              "Local graphics are design specifications only: no supported rendering recipe or usable asset is claimed.", ""]
    for s in plan["scenes"]:
        for a in s["asset_requirements"]:
            for alt in a.get("alternatives", []):
                lines.append(f"- {s['id']} / {alt['id']}: {alt['description']}; conditional, unresolved; {alt['activation_condition']}")
    lines += ["", "## Vertical text choreography (specification, not rendered readability)", ""]
    for s in plan["scenes"]:
        if "presentation" not in s:
            continue
        p = s["presentation"]
        lines.append(f"### {s['id']} — {p['composition_key']}")
        lines.append(f"1080×1920; safe area {p['safe_area']}; subtitle reservation {p['subtitle_reserved']}. Timing is editorial, not word alignment.")
        for b in p["text_blocks"]:
            text = s["on_screen_text"][b["overlay_index"]]["text"]
            lines.append(f"- +{b['start_offset']:.3f}–{b['end_offset']:.3f} s: {cell(text)}; "
                         f"font {b['font_size_px']} px, <= {b['max_lines']} lines, box {b['box']}.")
        lines.append("")
    lines += ["", "## Continuity / accuracy review", ""]
    for rule in plan["canon"]["continuity_rules"]:
        lines.append(f"- {rule['id']} ({plan['continuity_review'].get(rule['id'], 'automatic format constraint')}): {rule['description']}")
    lines += ["", "## Shot risks and canonical references", ""]
    for s in plan["scenes"]:
        lines.append(f"- {s['id']}: claims {', '.join(s['claim_ids'])}; sources {', '.join(s['source_ids'])}; "
                     f"risks {', '.join(s['risk_flags'])}; {s['review_status']}.")
    return "\n".join(lines) + "\n"
