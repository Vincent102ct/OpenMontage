"""Fiction Story Package: an author-provided story as reviewable canon for Short and Long drafts.

Separate from the historical Master Story Package (``lib/master_story.py``), which
needs sources, verification statuses and dated timelines that fiction does not
have. Provenance here is the author's original text and its SHA-256. Every
semantic item cites exact source spans; facts distinguish narrated events,
character claims, later revelations and ambiguity; events use relative order.

``resolve_draft`` turns a human- or agent-authored draft (quotes instead of
offsets) into a package. ``validate_package`` checks structure, the reference
graph, evidence spans, anti-fabrication rules and format consistency. It does
not decide whether an interpretation is right; that stays a human review item.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import jsonschema

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "story" / "fiction_story_package.schema.json"
SYLLABLES_PER_SECOND = 4.35
DURATION_BASIS = ("Estimate only: syllables / 4.35 per second (STORY 053 measured V2 Piper Vietnamese narration, "
                  "1857 syllables over 426.55 s) plus planned silences. Real duration requires TTS measurement.")
SHORT_TARGET = {"min": 45, "max": 60}
FORMAT_SHAPE = {"short": ("FMT_SHORT", "9:16"), "long": ("FMT_LONG", "16:9")}
REQUIRED_FORBIDDEN = {"documentary_motion_graphics", "text_slideshow", "stock_footage_montage", "static_image_zoom",
                      "infographic_replacement"}
COLLECTIONS = {"characters": "CHR_", "locations": "LOC_", "objects": "OBJ_", "facts": "FACT_", "events": "EVT_",
               "dialogue": "DLG_", "sound_cues": "SND_", "motifs": "MOT_", "ambiguities": "AMB_",
               "continuity_rules": "CONT_"}
REVIEWABLE = list(COLLECTIONS)
FABRICATION = [
    (re.compile(r"(?<!\d)(1[5-9]\d\d|20\d\d)(?!\d)"), "calendar year"),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}\b"), "calendar date"),
    (re.compile(r"https?://|www\.", re.I), "URL"),
    (re.compile(r"\b(doi|isbn)\b", re.I), "citation identifier"),
]
# Exact source copies are checked against the source instead; authored text is always scanned.
SOURCE_TEXT_KEYS = {"quote"}


class FictionStoryError(ValueError):
    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems[:12]) + (f" (+{len(problems) - 12} more)" if len(problems) > 12 else ""))
        self.problems = problems


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def syllables(text: str) -> int:
    return len(re.findall(r"\w+", text))


# ---------------------------------------------------------------------------
# Draft resolution (quotes -> exact spans)
# ---------------------------------------------------------------------------

class _Resolver:
    def __init__(self, segments: list[dict]):
        self.segments = segments
        self.by_id = {s["id"]: s for s in segments}
        self.order = {s["id"]: i for i, s in enumerate(segments)}
        self.problems: list[str] = []

    def _span(self, seg: dict, quote: str, occurrence: int, where: str) -> dict | None:
        start = -1
        for _ in range(occurrence):
            start = seg["text"].find(quote, start + 1)
            if start < 0:
                self.problems.append(f"QUOTE_NOT_FOUND {where}: {quote!r} not in {seg['id']}")
                return None
        return {"segment_id": seg["id"], "char_start": start, "char_end": start + len(quote), "quote": quote}

    def evidence(self, item, where: str) -> list[dict]:
        """Accept 'quote', 'SEG_0001', 'SEG_0001..SEG_0009' or {segment_id, quote?, occurrence?}."""
        if isinstance(item, str) and re.fullmatch(r"SEG_\d{4}(\.\.SEG_\d{4})?", item):
            first, _, last = item.partition("..")
            last = last or first
            if first not in self.order or last not in self.order or self.order[first] > self.order[last]:
                self.problems.append(f"BAD_SEGMENT_RANGE {where}: {item}")
                return []
            return [{"segment_id": s["id"], "char_start": 0, "char_end": len(s["text"]), "quote": s["text"]}
                    for s in self.segments[self.order[first]:self.order[last] + 1]]
        if isinstance(item, str):
            hits = [s for s in self.segments if item in s["text"]]
            total = sum(s["text"].count(item) for s in hits)
            if total != 1:
                self.problems.append(f"QUOTE_{'NOT_FOUND' if not total else 'AMBIGUOUS'} {where}: {item!r} "
                                     f"occurs {total} times; give segment_id")
                return []
            span = self._span(hits[0], item, 1, where)
            return [span] if span else []
        if isinstance(item, dict) and item.get("segment_id") in self.by_id:
            seg = self.by_id[item["segment_id"]]
            span = self._span(seg, item.get("quote") or seg["text"], int(item.get("occurrence", 1)), where)
            return [span] if span else []
        self.problems.append(f"BAD_EVIDENCE {where}: {item!r}")
        return []

    def many(self, items, where: str) -> list[dict]:
        out = []
        for item in items or []:
            out.extend(self.evidence(item, where))
        return out


def resolve_draft(draft: dict, *, segments: list[dict], language: str, provenance: dict,
                  intake_dialogue: list[dict] | None = None) -> dict:
    """Build a package from a draft; segments are the verified intake segments."""
    r = _Resolver(segments)
    pkg: dict = {
        "schema_version": "1.0", "package_kind": "fiction", "package_id": draft.get("package_id"),
        "package_version": "v1", "title": draft.get("title"), "language": language, "style": "stickman_horror_2d",
        "status": "draft", "review_status": "pending_human_review", "approved": False,
        "provenance": provenance,
        "authorship": {"kind": "user_authored_fiction", "author": "production_requester",
                       "statement": "Original fiction provided by the production requester; the only source."},
        "segments": [{k: s[k] for k in ("id", "kind", "char_start", "char_end", "sha256", "text")} for s in segments],
    }
    for name in COLLECTIONS:
        items = []
        for raw in draft.get(name, []):
            item = {k: v for k, v in raw.items() if k not in ("evidence", "segments")}
            item["evidence"] = r.many(list(raw.get("segments", [])) + list(raw.get("evidence", [])),
                                      f"{name}.{raw.get('id')}")
            items.append(item)
        pkg[name] = items
    for i, event in enumerate(pkg["events"], 1):
        event.setdefault("narrative_order", i)
    pkg["stickman_production"] = draft.get("stickman_production")
    pkg["formats"] = {}
    for fmt, (fid, shape) in FORMAT_SHAPE.items():
        plan = draft.get("formats", {}).get(fmt, {})
        chapters, total_syll, silence = [], 0, 0.0
        for ch in plan.get("chapters", []):
            beats = []
            for raw in ch.get("beats", []):
                beat = {k: v for k, v in raw.items() if k != "narration"}
                nar = raw.get("narration", {})
                where = f"formats.{fmt}.{raw.get('id')}"
                if nar.get("mode") == "verbatim":
                    spans = r.many(nar.get("spans"), where)
                    text = "\n".join(s["quote"] for s in spans)
                else:
                    spans = r.many(nar.get("sources"), where)
                    text = nar.get("text", "")
                beat["narration"] = {"mode": nar.get("mode"), "text": text,
                                     "sources": [{k: s[k] for k in ("segment_id", "char_start", "char_end")}
                                                 for s in spans]}
                if nar.get("note"):
                    beat["narration"]["note"] = nar["note"]
                beat.setdefault("silence_after_seconds", 0)
                total_syll += syllables(text)
                silence += float(beat["silence_after_seconds"])
                beats.append(beat)
            chapters.append({"id": ch.get("id"), "title": ch.get("title"), "beats": beats})
        pkg["formats"][fmt] = {
            "id": fid, "format": fmt, "aspect_ratio": shape, **({"intent": plan["intent"]} if plan.get("intent") else {}),
            "target_seconds": dict(SHORT_TARGET) if fmt == "short" else None,
            "duration": {"status": "estimate_pending_tts_measurement", "basis": DURATION_BASIS,
                         "syllables": total_syll, "planned_silence_seconds": round(silence, 2),
                         "estimated_seconds": round(total_syll / SYLLABLES_PER_SECOND + silence, 1)},
            "status": "draft", "approved": False,
            "depends_on_changes": plan.get("depends_on_changes", []),
            "excluded_segments": plan.get("excluded_segments", []), "chapters": chapters,
        }
    pkg["coverage"] = {"semantic_basis": draft.get("semantic_basis", ""), "complete": False,
                       "missing": list(draft.get("coverage_missing", [])) + automatic_gaps(pkg, intake_dialogue)}
    if r.problems:
        raise FictionStoryError(r.problems)
    return pkg


def automatic_gaps(pkg: dict, intake_dialogue: list[dict] | None) -> list[str]:
    """Coverage gaps computed from the package itself, so incompleteness is never hidden."""
    gaps = []
    linked = {e["segment_id"] for ev in pkg["events"] for e in ev["evidence"]}
    unlinked = [s["id"] for s in pkg["segments"] if s["kind"] != "heading" and s["id"] not in linked]
    if unlinked:
        gaps.append(f"{len(unlinked)} segments are not linked to any event: {', '.join(unlinked[:12])}"
                    + (" …" if len(unlinked) > 12 else ""))
    seg_start = {s["id"]: s["char_start"] for s in pkg["segments"]}
    covered = {(seg_start[e["segment_id"]] + e["char_start"]) for d in pkg["dialogue"] for e in d["evidence"]}
    covered |= {(seg_start[e["segment_id"]] + e["char_start"]) for c in pkg["sound_cues"] for e in c["evidence"]}
    missing = [d for d in intake_dialogue or [] if d["char_start"] not in covered]
    if missing:
        gaps.append(f"{len(missing)} quoted lines from intake have no dialogue or sound entry: "
                    + ", ".join(d["segment_id"] for d in missing[:12]))
    unresolved = [d["id"] for d in pkg["dialogue"] if d["attribution_status"] == "unresolved"]
    if unresolved:
        gaps.append(f"{len(unresolved)} dialogue/message lines have no resolved speaker or sender: "
                    + ", ".join(unresolved))
    if pkg["ambiguities"]:
        gaps.append(f"{len(pkg['ambiguities'])} interpretation questions are unresolved by design")
    return gaps


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validator():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())


def _strings(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            if k in SOURCE_TEXT_KEYS or k == "segments":
                continue
            yield from _strings(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _strings(v, f"{path}[{i}]")
    elif isinstance(node, str):
        yield path, node


def validate_package(pkg: dict, *, source_text: str | None = None, changes: list[dict] | None = None) -> dict:
    """Return a summary with warnings, or raise FictionStoryError listing every problem."""
    problems = [f"SCHEMA {'/'.join(map(str, e.path)) or '<root>'}: {e.message}"
                for e in sorted(_validator().iter_errors(pkg), key=lambda e: list(map(str, e.path)))]
    if problems:
        raise FictionStoryError(problems)
    warnings: list[str] = []
    segs = {s["id"]: s for s in pkg["segments"]}
    order = {s["id"]: i for i, s in enumerate(pkg["segments"])}
    body = [s for s in pkg["segments"] if s["kind"] != "heading"]
    for s in pkg["segments"]:
        if _sha(s["text"]) != s["sha256"]:
            problems.append(f"SEGMENT_HASH {s['id']}")
        if source_text is not None and source_text[s["char_start"]:s["char_end"]] != s["text"]:
            problems.append(f"SEGMENT_SPAN {s['id']} does not match the source text")
    if source_text is not None and _sha(source_text) != pkg["provenance"]["source"]["sha256"]:
        problems.append("SOURCE_HASH provenance does not match the source text")

    ids: dict[str, str] = {}
    for name, prefix in COLLECTIONS.items():
        for item in pkg[name]:
            if not item["id"].startswith(prefix):
                problems.append(f"ID_PREFIX {item['id']} in {name}")
            if item["id"] in ids:
                problems.append(f"DUPLICATE_ID {item['id']}")
            ids[item["id"]] = name
            for e in item["evidence"]:
                seg = segs.get(e["segment_id"])
                if not seg or seg["text"][e["char_start"]:e["char_end"]] != e["quote"]:
                    problems.append(f"EVIDENCE {item['id']}: quote does not match {e['segment_id']}")

    def need(ref_ids, kinds, where):
        for ref in ref_ids:
            if ids.get(ref) not in kinds:
                problems.append(f"BAD_REFERENCE {where} -> {ref}")

    corpus = "\n".join(s["text"] for s in pkg["segments"]).lower()
    for c in pkg["characters"]:
        for alias in c["aliases"]:
            if alias.lower() not in corpus:
                problems.append(f"ALIAS_NOT_IN_SOURCE {c['id']}: {alias!r}")
    for loc in pkg["locations"]:
        if "parent_id" in loc:
            need([loc["parent_id"]], {"locations"}, loc["id"])
    for o in pkg["objects"]:
        need([o[k] for k in ("owner_id",) if k in o], {"characters"}, o["id"])
        need([o[k] for k in ("location_id",) if k in o], {"locations"}, o["id"])
    facts = {f["id"]: f for f in pkg["facts"]}
    for f in pkg["facts"]:
        if f["kind"] in ("character_claim", "later_revelation") and not f["reported_by"]:
            problems.append(f"CLAIM_WITHOUT_REPORTER {f['id']}")
        if f["reported_by"]:
            need([f["reported_by"]], {"characters"}, f["id"])
        need(f["conflicts_with"], {"facts"}, f["id"])
        if f["revealed_at"] not in segs:
            problems.append(f"BAD_REVEAL_SEGMENT {f['id']}")
        for other in f["conflicts_with"]:
            o = facts.get(other)
            if o and f["id"] not in o["conflicts_with"]:
                problems.append(f"ASYMMETRIC_CONFLICT {f['id']} -> {other}")
            if (o and f["kind"] == "later_revelation" and o["kind"] == "character_claim"
                    and order.get(f["revealed_at"], -1) <= order.get(o["revealed_at"], -1)):
                problems.append(f"REVELATION_BEFORE_CLAIM {f['id']} must be revealed after {other}")
    ambiguous_refs = {r for a in pkg["ambiguities"] for r in a["related_ids"]}
    for f in pkg["facts"]:
        if f["kind"] == "ambiguous" and f["id"] not in ambiguous_refs:
            problems.append(f"AMBIGUOUS_FACT_WITHOUT_QUESTION {f['id']}")
    last_first = -1
    for ev in sorted(pkg["events"], key=lambda e: e["narrative_order"]):
        need(ev["participant_ids"], {"characters"}, ev["id"])
        need([ev["location_id"]], {"locations"}, ev["id"])
        need(ev["object_ids"], {"objects"}, ev["id"])
        need(ev["fact_ids"], {"facts"}, ev["id"])
        first = min(order[e["segment_id"]] for e in ev["evidence"])
        if first < last_first:
            problems.append(f"EVENT_ORDER {ev['id']} starts before the previous event in the narration")
        last_first = first
        for marker in ev["time_markers"]:
            if marker.lower() not in corpus:
                problems.append(f"TIME_MARKER_NOT_IN_SOURCE {ev['id']}: {marker!r}")
    orders = sorted(e["narrative_order"] for e in pkg["events"])
    if orders != list(range(1, len(orders) + 1)):
        problems.append("EVENT_ORDER narrative_order must be 1..n without gaps")
    for d in pkg["dialogue"]:
        if d["text"] != d["evidence"][0]["quote"]:
            problems.append(f"DIALOGUE_NOT_VERBATIM {d['id']}")
        if d["speaker_id"]:
            need([d["speaker_id"]], {"characters"}, d["id"])
        expected = "proposed" if d["speaker_id"] else ("not_applicable" if d["channel"] == "sound_effect"
                                                       else "unresolved")
        if d["attribution_status"] != expected:
            problems.append(f"ATTRIBUTION_STATUS {d['id']} should be {expected}")
    for name in ("sound_cues",):
        for c in pkg[name]:
            need(c["event_ids"], {"events"}, c["id"])
    for m in pkg["motifs"]:
        need(m["related_ids"], set(COLLECTIONS), m["id"])
    for a in pkg["ambiguities"]:
        need(a["related_ids"], set(COLLECTIONS), a["id"])
    for c in pkg["continuity_rules"]:
        need(c["related_ids"], set(COLLECTIONS), c["id"])

    sp = pkg["stickman_production"]
    if not REQUIRED_FORBIDDEN <= set(sp["forbidden_primary_treatments"]):
        problems.append("STICKMAN forbidden_primary_treatments must list every non-primary treatment")
    for c in sp["characters"]:
        need([c["character_id"]], {"characters"}, "stickman_production")
        need(c["persistent_props"], {"objects"}, f"stickman_production.{c['character_id']}")

    for path, value in _strings(pkg):
        if path.startswith(".provenance") or path.endswith(".duration.basis"):
            continue  # Generated metadata, not authored story content.
        for pattern, label in FABRICATION:
            for m in pattern.finditer(value):
                if m.group(0).lower() not in corpus:
                    problems.append(f"FABRICATION {label} {m.group(0)!r} at {path} is not in the source")

    change_segments = {c["id"]: set(c.get("segment_ids", [])) for c in changes or []}
    formats = pkg["formats"]
    seen_beats: set[str] = set()
    for fmt, (fid, shape) in FORMAT_SHAPE.items():
        plan = formats[fmt]
        if (plan["id"], plan["format"], plan["aspect_ratio"]) != (fid, fmt, shape):
            problems.append(f"FORMAT_SHAPE {fmt}")
        if fmt == "short" and plan["target_seconds"] != SHORT_TARGET:
            problems.append("FORMAT short target_seconds must be 45-60")
        if fmt == "long" and plan["target_seconds"] is not None:
            problems.append("FORMAT long duration is unknown until TTS measurement; target_seconds must be null")
        need_changes = set()
        covered: list[str] = []
        syll, silence = 0, 0.0
        for ch in plan["chapters"]:
            for beat in ch["beats"]:
                where = f"{fmt}.{beat['id']}"
                if beat["id"] in seen_beats:
                    problems.append(f"DUPLICATE_BEAT {beat['id']}")
                seen_beats.add(beat["id"])
                need(beat["event_ids"], {"events"}, where)
                need(beat["character_ids"], {"characters"}, where)
                need([beat["location_id"]], {"locations"}, where)
                need(beat["object_ids"], {"objects"}, where)
                need(beat["sound_cue_ids"], {"sound_cues"}, where)
                nar = beat["narration"]
                parts = []
                for span in nar["sources"]:
                    seg = segs.get(span["segment_id"])
                    if not seg or not 0 <= span["char_start"] < span["char_end"] <= len(seg["text"]):
                        problems.append(f"BAD_SPAN {where}")
                        continue
                    parts.append(seg["text"][span["char_start"]:span["char_end"]])
                    for cid, seg_ids in change_segments.items():
                        if span["segment_id"] in seg_ids:
                            need_changes.add(cid)
                    if nar["mode"] == "verbatim":
                        covered.append(span["segment_id"])
                if nar["mode"] == "verbatim" and nar["text"] != "\n".join(parts):
                    problems.append(f"VERBATIM_MISMATCH {where}: narration text is not the exact source span")
                if nar["mode"] == "authored_proposal" and nar["text"] in "\n".join(parts):
                    warnings.append(f"{where}: authored narration repeats source text; mark it verbatim instead")
                syll += syllables(nar["text"])
                silence += beat["silence_after_seconds"]
        for ex in plan["excluded_segments"]:
            if ex["segment_id"] not in segs:
                problems.append(f"BAD_EXCLUSION {fmt} {ex['segment_id']}")
            if "change_id" in ex:
                if ex["change_id"] not in change_segments and changes is not None:
                    problems.append(f"BAD_EXCLUSION_CHANGE {fmt} {ex['change_id']}")
                need_changes.add(ex["change_id"])
        missing_deps = need_changes - set(plan["depends_on_changes"])
        if missing_deps and changes is not None:
            problems.append(f"FORMAT {fmt} uses segments touched by proposed edits {sorted(missing_deps)}; "
                            "list them in depends_on_changes")
        positions = [order[s] for s in covered]
        if positions != sorted(positions):
            problems.append(f"FORMAT {fmt} verbatim narration is out of source order")
        d = plan["duration"]
        if d["syllables"] != syll or abs(d["planned_silence_seconds"] - silence) > 0.01 or abs(
                d["estimated_seconds"] - round(syll / SYLLABLES_PER_SECOND + silence, 1)) > 0.05:
            problems.append(f"FORMAT {fmt} duration estimate does not match its narration")
        if fmt == "long":
            excluded = {e["segment_id"] for e in plan["excluded_segments"]}
            gaps = [s["id"] for s in body if s["id"] not in set(covered) | excluded]
            if gaps:
                problems.append(f"LONG_COVERAGE {len(gaps)} story segments missing: {', '.join(gaps[:10])}")
        elif not SHORT_TARGET["min"] <= d["estimated_seconds"] <= SHORT_TARGET["max"]:
            warnings.append(f"short estimate {d['estimated_seconds']} s is outside 45-60 s")

    def plan_ids(plan, key):
        return {i for ch in plan["chapters"] for b in ch["beats"] for i in (b[key] if isinstance(b[key], list)
                                                                              else [b[key]])}
    for key in ("character_ids", "event_ids", "object_ids", "location_id"):
        extra = plan_ids(formats["short"], key) - plan_ids(formats["long"], key)
        if extra:
            problems.append(f"FORMAT_CONSISTENCY short uses {key} absent from long: {sorted(extra)}")
    if problems:
        raise FictionStoryError(problems)
    counts = {name: len(pkg[name]) for name in COLLECTIONS}
    counts.update({f"{fmt}_beats": sum(len(ch["beats"]) for ch in formats[fmt]["chapters"]) for fmt in formats})
    return {"status": "valid", "counts": counts, "warnings": warnings,
            "estimated_seconds": {fmt: formats[fmt]["duration"]["estimated_seconds"] for fmt in formats}}
