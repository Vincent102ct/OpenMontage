"""Deterministic editorial materialization. No interpretation or production tools."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import jsonschema

from lib.fiction_story import (COLLECTIONS, FictionStoryError, SYLLABLES_PER_SECOND,
                               syllables, validate_package)

SCHEMA = Path(__file__).resolve().parents[1] / "schemas/story/reviewed_fiction_package.schema.json"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def working_copy(source: str, accepted: list[dict]) -> tuple[str, list[dict]]:
    """Lossless mapping; removals have zero-width reviewed spans. Offsets are Unicode characters."""
    mapping, pieces, cursor, position = [], [], 0, 0
    for change in sorted(accepted, key=lambda c: c["source_span"]["char_start"]):
        start, end = (change["source_span"][k] for k in ("char_start", "char_end"))
        if (change["operation"] != "remove" or not cursor <= start < end <= len(source)
                or source[start:end] != change["removed_text"]):
            raise ValueError("Invalid or overlapping approved edit: " + change["id"])
        if start > cursor:
            text = source[cursor:start]
            mapping.append({"source_start": cursor, "source_end": start, "working_start": position,
                            "working_end": position + len(text), "operation": "retain", "change_id": None})
            pieces.append(text)
            position += len(text)
        mapping.append({"source_start": start, "source_end": end, "working_start": position,
                        "working_end": position, "operation": "remove", "change_id": change["id"]})
        cursor = end
    if cursor < len(source):
        text = source[cursor:]
        mapping.append({"source_start": cursor, "source_end": len(source), "working_start": position,
                        "working_end": position + len(text), "operation": "retain", "change_id": None})
        pieces.append(text)
    return "".join(pieces), mapping


def mapped_spans(mapping: list[dict], start: int, end: int) -> list[dict]:
    out = []
    for chunk in mapping:
        left, right = max(start, chunk["source_start"]), min(end, chunk["source_end"])
        if chunk["operation"] == "retain" and left < right:
            out.append({"source_start": left, "source_end": right,
                        "char_start": chunk["working_start"] + left - chunk["source_start"],
                        "char_end": chunk["working_start"] + right - chunk["source_start"]})
    return out


def materialize_content(draft: dict, source: str, changes: list[dict],
                        dispositions: list[dict], version: str) -> dict:
    """Only explicit accepts survive; answers remain human interpretations, never inferred facts."""
    decisions = {d["target_id"]: d for d in dispositions}
    blockers = []
    for d in dispositions:
        allowed = ("answer", "preserve_ambiguity") if d["kind"] == "question" else ("accept", "reject")
        if d["decision"] not in allowed:
            blockers.append(f"DECISION {d['target_id']}: {d['decision']} requires explicit review.")
    accepted = [c for c in changes if decisions[c["id"]]["decision"] == "accept"]
    working, mapping = working_copy(source, accepted)
    canon = copy.deepcopy(draft)
    canon.update(package_version=version, status="reviewed", review_status="decisions_materialized")
    for name in COLLECTIONS:
        if name == "ambiguities":
            for item in canon[name]:
                choice = decisions[item["id"]]["decision"]
                item["status"] = {"preserve_ambiguity": "intentionally_unresolved",
                                  "answer": "human_answer_recorded"}.get(choice, "unresolved")
        else:
            canon[name] = [item for item in canon[name] if decisions[item["id"]]["decision"] == "accept"]
    # Never renumber surviving event identities; presentation order remains the source order.
    for i, event in enumerate(canon["events"], 1):
        event["narrative_order"] = i
    canon["formats"] = {k: p for k, p in canon["formats"].items()
                        if decisions[p["id"]]["decision"] == "accept"}
    segs = {s["id"]: s for s in canon["segments"]}
    for name in COLLECTIONS:
        for item in canon[name]:
            for evidence in item["evidence"]:
                seg = segs[evidence["segment_id"]]
                start = seg["char_start"] + evidence["char_start"]
                if not mapped_spans(mapping, start, seg["char_start"] + evidence["char_end"]):
                    blockers.append(f"REMOVED_EVIDENCE {item['id']}: its supporting text was removed.")
    interpreted_refs = {ref for q in canon["ambiguities"]
                        if decisions[q["id"]]["decision"] in ("answer", "preserve_ambiguity")
                        for ref in q["related_ids"]}
    for dialogue in canon["dialogue"]:
        if dialogue["attribution_status"] == "unresolved" and dialogue["id"] not in interpreted_refs:
            blockers.append(f"UNREVIEWED_ATTRIBUTION {dialogue['id']}: explicitly review a linked ambiguity.")
    for fmt, plan in canon["formats"].items():
        plan["status"] = "reviewed"
        for exclusion in plan["excluded_segments"]:
            cid = exclusion.get("change_id")
            if not cid or decisions.get(cid, {}).get("decision") != "accept":
                blockers.append(f"UNAPPROVED_EXCLUSION {fmt}: {exclusion['segment_id']} needs an accepted edit.")
        total, silence = 0, 0.0
        for chapter in plan["chapters"]:
            for beat in chapter["beats"]:
                narration = beat["narration"]
                groups = []
                for span in narration["sources"]:
                    seg = segs[span["segment_id"]]
                    start, end = (seg["char_start"] + span[k] for k in ("char_start", "char_end"))
                    mapped = mapped_spans(mapping, start, end)
                    if not mapped:
                        blockers.append(f"REMOVED_NARRATION {beat['id']}: source span no longer exists.")
                    groups.append(mapped)
                narration["working_spans"] = groups
                if narration["mode"] == "verbatim":
                    narration["text"] = "\n".join("".join(working[s["char_start"]:s["char_end"]] for s in group)
                                                   for group in groups if group)
                elif any(sum(s["source_end"] - s["source_start"] for s in group)
                         != span["char_end"] - span["char_start"]
                         for group, span in zip(groups, narration["sources"])):
                    blockers.append(f"AUTHORED_SOURCE_CHANGED {beat['id']}: revise the proposal explicitly.")
                total += syllables(narration["text"])
                silence += beat["silence_after_seconds"]
        plan["duration"].update(syllables=total, planned_silence_seconds=round(silence, 2),
                                estimated_seconds=round(total / SYLLABLES_PER_SECOND + silence, 1))
    result = {"schema_version": "1.0", "artifact": "reviewed_fiction_package", "version": version,
              "approval_scope": "preproduction_story_only", "production_started": False, "publishing_enabled": False,
              "source_sha256": sha(source), "working_text": working, "working_text_sha256": sha(working),
              "source_mapping": mapping, "dispositions": dispositions, "canonical_story": canon,
              "blockers": blockers}
    result["blockers"] = list(dict.fromkeys(blockers + validate_reviewed_package(result, source, changes)))
    return result


def validate_reviewed_package(package: dict, source: str, changes: list[dict]) -> list[str]:
    """Reuse v1 reference/evidence/format validation, plus exact approved text and coverage checks."""
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    errors = [f"SCHEMA {e.json_path}: {e.message}" for e in jsonschema.Draft202012Validator(schema).iter_errors(package)]
    if errors:
        return errors
    canon, working, mapping = package["canonical_story"], package["working_text"], package["source_mapping"]
    choices = {d["target_id"]: d for d in package["dispositions"]}
    try:
        if (canon["status"] != "reviewed" or canon["review_status"] != "decisions_materialized"
                or canon["package_version"] != package["version"]):
            errors.append("REVIEWED_STATE canonical content must describe this immutable reviewed version.")
        expected, expected_map = working_copy(source, [c for c in changes
                                                      if choices[c["id"]]["decision"] == "accept"])
        if (working, mapping, package["source_sha256"], package["working_text_sha256"]) != (
                expected, expected_map, sha(source), sha(working)):
            errors.append("SOURCE_MAPPING reviewed text differs from the approved edits.")
        shadow = copy.deepcopy(canon)
        shadow.update(status="draft", review_status="pending_human_review")
        for item in shadow["ambiguities"]:
            item["status"] = "unresolved"
        segs = {s["id"]: s for s in shadow["segments"]}
        long_ranges, short_ranges = [], []
        sound_ids = {s["id"] for s in canon["sound_cues"]}
        format_sounds = {}
        for fmt, plan in shadow["formats"].items():
            if plan["status"] != "reviewed":
                errors.append(f"REVIEWED_STATE {fmt}")
            format_sounds[fmt] = set()
            plan["status"] = "draft"
            total = 0
            for ch in plan["chapters"]:
                for beat in ch["beats"]:
                    format_sounds[fmt].update(beat["sound_cue_ids"])
                    for sound_id in beat["sound_cue_ids"]:
                        if sound_id not in sound_ids:
                            errors.append(f"BAD_REFERENCE {beat['id']} -> {sound_id}")
                    nar = beat["narration"]
                    parts, groups = [], []
                    for span in nar["sources"]:
                        seg = segs[span["segment_id"]]
                        parts.append(seg["text"][span["char_start"]:span["char_end"]])
                        groups.append(mapped_spans(mapping, seg["char_start"] + span["char_start"],
                                                   seg["char_start"] + span["char_end"]))
                    if nar.pop("working_spans", None) != groups:
                        errors.append(f"NARRATION_MAPPING {beat['id']}")
                    if nar["mode"] == "verbatim":
                        text = "\n".join("".join(working[s["char_start"]:s["char_end"]] for s in group)
                                         for group in groups if group)
                        if nar["text"] != text:
                            errors.append(f"REVIEWED_VERBATIM {beat['id']}")
                        if fmt == "long":
                            long_ranges += [(s["char_start"], s["char_end"]) for g in groups for s in g]
                        nar["text"] = "\n".join(parts)
                    if fmt == "short":
                        short_ranges += [(s["char_start"], s["char_end"]) for g in groups for s in g]
                    total += syllables(nar["text"])
            duration = plan["duration"]
            duration.update(syllables=total, estimated_seconds=round(
                total / SYLLABLES_PER_SECOND + duration["planned_silence_seconds"], 1))
        try:
            validate_package(shadow, source_text=source, changes=changes)
        except FictionStoryError as exc:
            errors.extend(exc.problems)
        if format_sounds.get("short", set()) - format_sounds.get("long", set()):
            errors.append("FORMAT_CONSISTENCY Short sound cues must also appear in Long.")
        if any(not working[i].isspace() and not any(a <= i < b for a, b in long_ranges)
               for left, right in short_ranges for i in range(left, right)):
            errors.append("FORMAT_CONSISTENCY Short sources must be covered by the reviewed Long.")
        # v1 checks segment IDs; v2 also checks every non-whitespace character in the retained Long body.
        for seg in canon["segments"]:
            if seg["kind"] == "heading":
                continue
            for span in mapped_spans(mapping, seg["char_start"], seg["char_end"]):
                if any(not working[i].isspace() and not any(a <= i < b for a, b in long_ranges)
                       for i in range(span["char_start"], span["char_end"])):
                    errors.append(f"LONG_WORKING_COVERAGE {seg['id']}: approved story text is missing.")
                    break
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(f"REVIEWED_STRUCTURE {exc}")
    return errors
