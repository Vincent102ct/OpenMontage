"""Story Intake: turn a saved Studio story request into reviewable, source-linked drafts.

Input is only a project ID. The saved request and original story are validated
through ProductionStore and never modified. Derivation is deterministic: exact
paragraph segments, rule-based candidates (reusing the M1 story analyzer's closed
vocabulary) and proposed editorial removals. No model, network, TTS, media or
pipeline checkpoint is used or written. Outputs are written once, atomically,
under artifacts/story_intake/v1/ and stay pending human review.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path

from studio.models import ProductionRequest, safe_project_id
from studio.store import ATX_HEADING, REQUEST_FILE, ProductionStore
from tools.story import lexicon as L
from tools.story import story_analyzer as SA

INTAKE_VERSION = "1.0"
OUTPUT_DIR = "artifacts/story_intake/v1"
FILES = {
    "report": "story_intake_report.json",
    "segments": "story_segments.json",
    "inventory": "story_inventory.json",
    "proposal": "working_text_proposal.md",
    "changes": "working_text_changes.json",
}
NEWLINE = re.compile(r"\r\n|\n|\r")
BLOCK = re.compile(r"[^\r\n]*\S[^\r\n]*(?:(?:\r\n|\n|\r)[^\r\n]*\S[^\r\n]*)*")
QUOTE = re.compile(r"“[^”\r\n]*”|\"[^\"\r\n]*\"")
EMPHASIS = re.compile(r"\*\*([^*\r\n]+)\*\*")
STRAY_BACKSLASH = re.compile(r"[ \t]*(?<!\\)\\(?=[ \t]*(?:\r\n|\n|\r)[ \t]*(?:\r\n|\n|\r)|[ \t]*$)")
YEAR = re.compile(r"(?<!\d)(1[5-9]\d\d|20\d\d)(?!\d)")
NUMBER = re.compile(r"(?<![\d:.,])\d{3,4}(?![\d:])")

# Role references the M1 lexicon lacks; candidates only, never merged into one person.
ROLE_REFERENCES = {
    "vi": ["bà chủ", "chủ nhà", "chủ trọ", "chủ cũ", "người mẹ", "mẹ", "con gái", "bé gái", "con bé",
           "đứa trẻ", "đứa nhỏ", "cảnh sát", "hàng xóm", "thợ", "người thuê", "bà ta", "anh ta", "cô ta",
           "ông ta"],
    "en": ["landlord", "landlady", "owner", "mother", "father", "daughter", "son", "police", "neighbor",
           "neighbour", "tenant"],
}
REPORTING = {
    "vi": re.compile(r"(?<!\w)(kể|kể rằng|theo lời|nói rằng|mới biết|nghe nói|chưa từng kể)(?!\w)", re.I),
    "en": re.compile(r"\b(told|said that|according to|learned|heard that|never told)\b", re.I),
}
META_NOTE = {
    "vi": (re.compile(r"(?<!\w)(câu chuyện|truyện)(?!\w)", re.I), re.compile(r"(?<!\w)(tôi|mình|em|đây)(?!\w)", re.I)),
    "en": (re.compile(r"\bstor(y|ies)\b", re.I), re.compile(r"\b(i|my|this)\b", re.I)),
}
VI_HOURS = {"một": 1, "hai": 2, "ba": 3, "bốn": 4, "năm": 5, "sáu": 6, "bảy": 7, "tám": 8, "chín": 9,
            "mười": 10, "mười một": 11, "mười hai": 12}
TIME_PATTERNS = [
    re.compile(r"(?<![\d:])(\d{1,2}):(\d{2})(?!\d)"),
    re.compile(r"(?<!\w)(\d{1,2}|" + "|".join(sorted(VI_HOURS, key=len, reverse=True))
               + r")\s+giờ(?:\s+(\d{1,2})(?:\s+phút)?)?(?!\w)", re.I),
]
HOUR_BEFORE = re.compile(r"(?<!\w)(lúc|khoảng|đến|gần|đúng|tới|từ|chừng)\s+$", re.I)
HOUR_AFTER = re.compile(r"\s*(sáng|chiều|tối|đêm|trưa|rưỡi|kém|\d)", re.I)
STOPWORDS = {
    "vi": set("tôi là có không một và rồi thì đã đang được của cho với này đó ấy nó cũng vẫn như vậy lại ra "
              "vào lên xuống đi khi mà nhưng chỉ còn từ trong ngoài trên dưới về đến những các cái chiếc "
              "người anh bà cô chú con em ông nói hỏi lần sau trước gì ai đâu thấy nghe biết".split()),
    "en": set("the a an and or but of to in on at for with was were is are be been i he she it they we you "
              "my his her their that this then there had have not no".split()),
}


class IntakeError(ValueError):
    """Intake refusal with a stable code for API mapping; nothing is written when raised."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(data: dict) -> bytes:
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _project_dir(store: ProductionStore, project_id: str) -> Path:
    try:
        safe_project_id(project_id)
        return store._project(project_id)
    except ValueError as exc:
        raise IntakeError("invalid_project_id", str(exc)) from exc


def _classify_invalid(project: Path) -> IntakeError:
    """Tell a tampered story file apart from an invalid request for a clearer message."""
    try:
        request = ProductionRequest.model_validate_json((project / REQUEST_FILE).read_bytes())
        if request.input_mode == "story" and (project / request.input_file).read_bytes() != request.content.encode():
            return IntakeError("source_mismatch", "input/story.md does not match the recorded content and SHA-256; "
                               "nothing was created.")
    except (ValueError, OSError):
        pass
    return IntakeError("invalid_request", "Saved request or input failed validation; nothing was created.")


def load_story_request(store: ProductionStore, project_id: str) -> dict:
    """Validate the saved P1 request and return the exact bytes intake will use."""
    project = _project_dir(store, project_id)
    try:
        request = store.detail(project_id)["request"]
        request_bytes = (project / REQUEST_FILE).read_bytes()
        source_path = project / request["input_file"]
        source = source_path.read_bytes() if request["input_mode"] == "story" else b""
    except FileNotFoundError as exc:
        if not (project / REQUEST_FILE).is_file():
            raise IntakeError("not_found", "Saved Studio production not found.") from exc
        raise IntakeError("source_mismatch", "The saved story input is missing; nothing was created.") from exc
    except (ValueError, OSError) as exc:
        raise _classify_invalid(project) from exc
    if request["input_mode"] != "story":
        what = {"topic": "Topic requests need research first", "canonical": "Canonical package requests use the "
                "Master Story Package path"}[request["input_mode"]]
        raise IntakeError("unsupported_input_mode", f"Story Intake supports Full story requests only at this stage. "
                          f"{what}; that is a later milestone. Nothing was created.")
    # Re-validate the bytes actually used, so a change after store.detail() cannot slip through.
    try:
        reread = ProductionRequest.model_validate_json(request_bytes)
    except ValueError as exc:
        raise IntakeError("invalid_request", "Saved request changed during intake; nothing was created.") from exc
    if reread.model_dump(mode="json") != request:
        raise IntakeError("invalid_request", "Saved request changed during intake; nothing was created.")
    if _sha(source) != request["content_sha256"] or source != request["content"].encode("utf-8"):
        raise IntakeError("source_mismatch", "input/story.md does not match the recorded content and SHA-256; "
                          "nothing was created.")
    if (request["style"], request["review_mode"], request["publishing_enabled"], request["status"]) != (
            "stickman_horror_2d", "human_required", False, "production_not_started"):
        raise IntakeError("invalid_request", "Request is not a pending Stickman Horror human-review request.")
    return {"project": project, "request": request, "request_sha256": _sha(request_bytes), "source": source}


# ---------------------------------------------------------------------------
# Derivation (pure functions of the source text)
# ---------------------------------------------------------------------------

class _Text:
    def __init__(self, text: str):
        self.text = text
        self.byte_at = [0]
        for ch in text:
            self.byte_at.append(self.byte_at[-1] + len(ch.encode("utf-8")))
        self.line_starts = [0] + [m.end() for m in NEWLINE.finditer(text)]

    def line(self, index: int) -> int:
        lo, hi = 0, len(self.line_starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.line_starts[mid] <= index:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1

    def span(self, start: int, end: int) -> dict:
        return {"char_start": start, "char_end": end, "byte_start": self.byte_at[start],
                "byte_end": self.byte_at[end], "line": self.line(start)}


def _line_endings(text: str) -> str:
    crlf = text.count("\r\n")
    lone = text.count("\n") - crlf + text.count("\r") - crlf
    return "none" if not (crlf or lone) else "CRLF" if not lone else "LF" if not crlf and "\r" not in text else "mixed"


def _segment_kind(block: str) -> str:
    stripped = block.strip()
    if "\n" not in block and "\r" not in block and ATX_HEADING.match(block):
        return "heading"
    if EMPHASIS.fullmatch(stripped):
        return "emphasized_line"
    if stripped[:1] in "“\"" and stripped.rstrip(".!?…").endswith(("”", "\"")):
        return "dialogue_line"
    return "paragraph"


def segment_source(t: _Text) -> list[dict]:
    segments = []
    for m in BLOCK.finditer(t.text):
        block = m.group(0)
        segments.append({"id": f"SEG_{len(segments) + 1:04d}", "index": len(segments), "kind": _segment_kind(block),
                         "text": block, **t.span(m.start(), m.end()), "line_end": t.line(m.end()),
                         "sha256": _sha(block.encode("utf-8")), "proposed_change_ids": []})
    rest = t.text
    for s in reversed(segments):
        rest = rest[:s["char_start"]] + rest[s["char_end"]:]
    if rest.strip() or not segments:
        raise IntakeError("invalid_request", "Story text could not be segmented without loss.")
    return segments


def _excerpt(text: str, start: int, end: int, width: int = 40) -> str:
    return text[max(0, start - width):min(len(text), end + width)]


def propose_changes(t: _Text, segments: list[dict], language: str) -> tuple[list[dict], list[dict]]:
    """Proposed removals (never applied to the original) and observations left unchanged."""
    text, changes, observations = t.text, [], []

    def add(rule, start, end, rationale, confidence, signals):
        changes.append({"id": f"CHG_{len(changes) + 1:04d}", "rule": rule, "operation": "remove",
                        "status": "proposed", "approved": False, "confidence": confidence,
                        "rationale": rationale, "signals": signals, "source_span": t.span(start, end),
                        "removed_text": text[start:end],
                        "segment_ids": [s["id"] for s in segments if s["char_start"] < max(end, start + 1)
                                        and s["char_end"] > start]})

    for m in STRAY_BACKSLASH.finditer(text):
        add("stray_line_end_backslash", m.start(), m.end(),
            "A Markdown line-break backslash before a blank line or the end of text has no effect and would be "
            "read literally.", "high", ["backslash at end of line", "followed by a blank line or end of text"])
    body = [s for s in segments if s["kind"] != "heading"]
    if len(body) >= 2:
        last, previous = body[-1], body[-2]
        gap = text[previous["char_end"]:last["char_start"]]
        breaks = len(NEWLINE.findall(gap))
        story_ref, person_ref = META_NOTE.get(language, META_NOTE["en"])
        meta = bool(story_ref.search(last["text"]) and person_ref.search(last["text"]))
        if breaks >= 3 and meta and len(last["text"]) <= 200:
            add("trailing_meta_note", previous["char_end"], last["char_end"],
                "The final paragraph is set apart from the story and refers to the story itself; it looks like "
                "an author's note rather than narrative text.", "medium",
                [f"final paragraph after {breaks - 1} blank lines", "refers to the story and to its author"])
        elif breaks >= 3:
            observations.append({"kind": "final_paragraph_after_large_gap", **t.span(last["char_start"], last["char_end"]),
                                 "segment_id": last["id"], "status": "no_change_proposed"})
    removed = [(c["source_span"]["char_start"], c["source_span"]["char_end"]) for c in changes]
    for m in re.finditer(r"(?:[ \t]*(?:\r\n|\n|\r))+", text):
        if len(NEWLINE.findall(m.group(0))) < 3:  # Count CRLF as one break; regex repetition could split it.
            continue
        if not any(a <= m.start() < b or a < m.end() <= b for a, b in removed):
            observations.append({"kind": "multiple_blank_lines", **t.span(m.start(), m.end()),
                                 "blank_lines": len(NEWLINE.findall(m.group(0))) - 1, "status": "no_change_proposed"})
    for c in changes:
        for s in segments:
            if s["id"] in c["segment_ids"]:
                s["proposed_change_ids"].append(c["id"])
    return changes, observations


def apply_changes(text: str, changes: list[dict]) -> str:
    out = text
    for c in sorted(changes, key=lambda c: c["source_span"]["char_start"], reverse=True):
        out = out[:c["source_span"]["char_start"]] + out[c["source_span"]["char_end"]:]
    return out


def _occurrences(segments: list[dict], phrases) -> list[dict]:
    found = []
    for s in segments:
        taken: list[tuple[int, int]] = []
        for phrase in sorted(set(phrases), key=len, reverse=True):
            for m in SA._phrase_re(phrase).finditer(s["text"]):
                if any(a < m.end() and m.start() < b for a, b in taken):
                    continue  # A longer phrase already covers this text.
                taken.append((m.start(), m.end()))
                found.append({"segment_id": s["id"], "char_start": s["char_start"] + m.start(),
                              "char_end": s["char_start"] + m.end(), "text": m.group(0)})
    return sorted(found, key=lambda o: o["char_start"])


def _standalone(segments_by_id: dict, occurrences: list[dict]) -> bool:
    """True when every occurrence is a whole one-word line such as a sound effect ("Cốc.")."""
    return bool(occurrences) and all(
        re.sub(r"[\W_]+", "", segments_by_id[o["segment_id"]]["text"]).lower()
        == re.sub(r"[\W_]+", "", o["text"]).lower() for o in occurrences)


def _candidate(prefix, n, label, phrases, basis, occurrences, confidence, extra=None):
    return {"id": f"{prefix}{n:03d}", "label": label, "phrases": sorted(set(phrases)), "basis": basis,
            "status": "candidate", "confidence": confidence, "mention_count": len(occurrences),
            "segment_ids": list(dict.fromkeys(o["segment_id"] for o in occurrences)),
            "occurrences": occurrences, **(extra or {})}


def build_inventory(segments: list[dict], language: str) -> tuple[dict, dict]:
    body = [s for s in segments if s["kind"] != "heading"]
    by_id = {s["id"]: s for s in segments}
    lang = language if language in L.LOCATION_WORDS else "en"
    story = {"title": "", "paragraphs": [SA._clean(s["text"]) for s in body], "source_path": "",
             "source_sha256": ""}
    analysis = SA.RuleAnalyzer(lang).analyze(story, [{"id": s["id"], "paragraph": i, "text": SA._clean(s["text"])}
                                                     for i, s in enumerate(body)])
    excluded: list[dict] = []

    def keep(item, kind):
        if not item["occurrences"]:
            excluded.append({"kind": kind, "label": item["label"], "basis": item["basis"],
                             "reason": "No textual evidence (analyzer default)."})
            return False
        if kind != "motif" and _standalone(by_id, item["occurrences"]):
            excluded.append({"kind": kind, "label": item["label"], "basis": item["basis"],
                             "reason": "Only appears as a standalone one-word line (likely a sound); see repeated_lines.",
                             "segment_ids": item["segment_ids"]})
            return False
        return True

    characters, char_map = [], {}
    for c in analysis["characters"]:
        phrases = [c["name"], *c["aliases"]]
        item = _candidate("CHR_CAND_", len(characters) + 1, c["name"], phrases,
                          "story_analyzer.narrator" if c["is_narrator"] else "story_analyzer.rules",
                          _occurrences(body, phrases), "high" if c["is_narrator"] else "low",
                          {"is_narrator": c["is_narrator"]})
        if keep(item, "character"):
            characters.append(item)
            char_map[c["id"]] = item["id"]
    covered = {p.lower() for c in characters for p in c["phrases"]}
    for role in ROLE_REFERENCES.get(lang, []):
        if role in covered:
            continue
        occ = _occurrences(body, [role])
        occ = [o for o in occ if not any(o["char_start"] >= x["char_start"] and o["char_end"] <= x["char_end"]
                                         for c in characters for x in c["occurrences"])]
        item = _candidate("CHR_CAND_", len(characters) + 1, role, [role], "intake.role_reference", occ, "medium",
                          {"is_narrator": False})
        if occ and keep(item, "character"):
            characters.append(item)
    # A shorter role reference can sit inside a longer one; drop occurrences already covered by the longer one.
    for c in characters:
        if c["basis"] == "intake.role_reference":
            longer = [o for d in characters if d is not c and len(d["label"]) > len(c["label"]) for o in d["occurrences"]]
            c["occurrences"] = [o for o in c["occurrences"] if not any(
                o["char_start"] >= x["char_start"] and o["char_end"] <= x["char_end"] for x in longer)]
            c["mention_count"] = len(c["occurrences"])
            c["segment_ids"] = list(dict.fromkeys(o["segment_id"] for o in c["occurrences"]))
    characters = [c for c in characters if c["occurrences"]]
    for n, c in enumerate(characters, 1):
        c["id"] = f"CHR_CAND_{n:03d}"

    locations = []
    for loc in analysis["locations"]:
        phrases = L.LOCATION_WORDS[lang].get(loc["kind"], [loc["name"]])
        item = _candidate("LOC_CAND_", len(locations) + 1, loc["name"], phrases, "story_analyzer.rules",
                          _occurrences(body, phrases), "low", {"vocabulary_kind": loc["kind"]})
        if keep(item, "location"):
            locations.append(item)
    numbered: dict[str, list[dict]] = {}
    place = re.compile(r"(?<!\w)(phòng|tầng|room|floor|apartment)\s+(\d{1,4}|" + "|".join(VI_HOURS) + r")(?!\w)", re.I)
    for s in body:
        for m in place.finditer(s["text"]):
            numbered.setdefault(m.group(0).lower(), []).append(
                {"segment_id": s["id"], "char_start": s["char_start"] + m.start(),
                 "char_end": s["char_start"] + m.end(), "text": m.group(0)})
    for label, occ in numbered.items():
        locations.append(_candidate("LOC_CAND_", len(locations) + 1, label, [label], "intake.numbered_place", occ,
                                    "medium"))

    objects = []
    for prop in analysis["props"]:
        phrases = L.PROP_WORDS[lang].get(prop["kind"], [prop["name"]])
        item = _candidate("OBJ_CAND_", len(objects) + 1, prop["name"], phrases, "story_analyzer.rules",
                          _occurrences(body, phrases), "low", {"vocabulary_kind": prop["kind"]})
        if keep(item, "object"):
            objects.append(item)

    motifs = _motifs(body, lang)
    dialogue = [{"id": f"DLG_{n:03d}", "segment_id": s["id"], "char_start": s["char_start"] + m.start(),
                 "char_end": s["char_start"] + m.end(), "text": m.group(0), "speaker_candidate": None,
                 "attribution": "needs_review"}
                for n, (s, m) in enumerate(((s, m) for s in body for m in QUOTE.finditer(s["text"])), 1)]
    emphasized = [{"id": f"EMP_{n:03d}", "segment_id": s["id"], "char_start": s["char_start"] + m.start(),
                   "char_end": s["char_start"] + m.end(), "text": m.group(0), "interpretation": "needs_review"}
                  for n, (s, m) in enumerate(((s, m) for s in body for m in EMPHASIS.finditer(s["text"])), 1)]
    events = []
    for beat in analysis["beats"]:
        if not (beat["actions"] or beat["time_jump"]):
            continue
        events.append({"id": f"EVT_CAND_{len(events) + 1:03d}", "segment_id": beat["id"],
                       "action_labels": sorted({a["action"] for a in beat["actions"]}),
                       "action_phrases": sorted({a["phrase"] for a in beat["actions"] if a["phrase"]}),
                       "actor_candidates": sorted({char_map[a["character_id"]] for a in beat["actions"]
                                                   if a["character_id"] in char_map}),
                       "time_jump": beat["time_jump"], "basis": "story_analyzer.rules (closed M1 action vocabulary)",
                       "status": "candidate", "confidence": "low"})
    review = _interpretation_items(body, lang, characters, motifs, dialogue, emphasized)
    inventory = {"characters": characters, "locations": locations, "objects": objects, "motifs": motifs,
                 "dialogue": dialogue, "emphasized_text": emphasized, "narrative_event_candidates": events,
                 "human_interpretation": review, "excluded_candidates": excluded}
    return inventory, analysis


def _motifs(body: list[dict], lang: str) -> dict:
    times: dict[str, list[dict]] = {}
    for s in body:
        taken: list[tuple[int, int]] = []
        for pattern in TIME_PATTERNS:
            for m in pattern.finditer(s["text"]):
                if any(a < m.end() and m.start() < b for a, b in taken):
                    continue
                hour = m.group(1).lower()
                if not hour.isdigit() and not (HOUR_BEFORE.search(s["text"][:m.start()])
                                               or HOUR_AFTER.match(s["text"][m.end():])):
                    continue  # The hour word also means "now" in Vietnamese; spelled hours need a time context word.
                taken.append((m.start(), m.end()))
                hour = int(hour) if hour.isdigit() else VI_HOURS[hour]
                minute = f"{int(m.group(2)):02d}" if m.group(2) else "??"
                times.setdefault(f"{hour:02d}:{minute}", []).append(
                    {"segment_id": s["id"], "char_start": s["char_start"] + m.start(),
                     "char_end": s["char_start"] + m.end(), "text": m.group(0)})
    numbers: dict[str, list[dict]] = {}
    time_spans = {(o["char_start"], o["char_end"]) for occ in times.values() for o in occ}
    for s in body:
        for m in NUMBER.finditer(s["text"]):
            a = s["char_start"] + m.start()
            if any(x <= a < y for x, y in time_spans):
                continue
            numbers.setdefault(m.group(0), []).append({"segment_id": s["id"], "char_start": a,
                                                       "char_end": a + len(m.group(0)), "text": m.group(0)})
    lines: dict[str, list[dict]] = {}
    for s in body:
        key = unicodedata.normalize("NFC", s["text"].strip()).lower()
        lines.setdefault(key, []).append({"segment_id": s["id"], "char_start": s["char_start"],
                                          "char_end": s["char_end"], "text": s["text"]})
    stop = STOPWORDS.get(lang, STOPWORDS["en"])
    grams: dict[tuple, list[dict]] = {}
    for s in body:
        tokens = [(m.start(), m.end(), m.group(0).lower()) for m in re.finditer(r"\w+", s["text"])]
        for size in (2, 3):
            for i in range(len(tokens) - size + 1):
                window = tokens[i:i + size]
                words = tuple(w for _, _, w in window)
                if all(w in stop for w in words) or any(w.isdigit() for w in words):
                    continue
                grams.setdefault(words, []).append({"segment_id": s["id"], "char_start": s["char_start"] + window[0][0],
                                                    "char_end": s["char_start"] + window[-1][1],
                                                    "text": s["text"][window[0][0]:window[-1][1]]})
    frequent = {g: o for g, o in grams.items() if len(o) >= 3}
    kept = [g for g in frequent if not any(len(h) > len(g) and len(frequent[h]) == len(frequent[g])
                                           and any(h[i:i + len(g)] == g for i in range(len(h) - len(g) + 1))
                                           for h in frequent)]
    kept = sorted(kept, key=lambda g: (-len(frequent[g]), " ".join(g)))[:30]

    def group(prefix, items, extra=lambda k, o: {}):
        return [{"id": f"{prefix}{n:03d}", "key": key, "count": len(occ), "recurring": len(occ) >= 2,
                 "segment_ids": list(dict.fromkeys(o["segment_id"] for o in occ)), "occurrences": occ,
                 **extra(key, occ)} for n, (key, occ) in enumerate(items, 1)]

    return {
        "time_expressions": group("TIME_", sorted(times.items()),
                                  lambda k, o: {"variants": sorted({x["text"] for x in o})}),
        "numbers": group("NUM_", sorted(numbers.items())),
        "repeated_lines": group("LINE_", [(o[0]["text"].strip(), o) for k, o in lines.items() if len(o) >= 2]),
        "repeated_phrases": group("PHR_", [(" ".join(g), frequent[g]) for g in kept]),
        "basis": "deterministic patterns; significance is not interpreted",
    }


def _interpretation_items(body, lang, characters, motifs, dialogue, emphasized) -> list[dict]:
    items = [{"kind": "semantic_analysis_not_performed", "segment_ids": [],
              "question": "Plot structure, twists, contradictions, reveals and cause/effect were not analyzed "
                          "automatically. Read the full segment list and record the intended story canon."}]
    people = [c for c in characters if not c.get("is_narrator")]
    if len(people) >= 2:
        items.append({"kind": "coreference", "candidate_ids": [c["id"] for c in people],
                      "segment_ids": [], "question": "Which person references denote the same individual? "
                      "Candidates: " + ", ".join(c["label"] for c in people) + "."})
    for t in motifs["time_expressions"]:
        if t["recurring"]:
            items.append({"kind": "recurring_time", "motif_id": t["id"], "segment_ids": t["segment_ids"],
                          "question": f"Time {t['key']} recurs {t['count']} times ({', '.join(t['variants'])}). "
                                      "Confirm its narrative meaning and whether the accounts agree."})
    for num in motifs["numbers"]:
        if num["recurring"]:
            items.append({"kind": "recurring_number", "motif_id": num["id"], "segment_ids": num["segment_ids"],
                          "question": f"Number {num['key']} recurs {num['count']} times. Confirm what it identifies."})
    reporting = [s["id"] for s in body if REPORTING.get(lang, REPORTING["en"]).search(s["text"])]
    if reporting:
        items.append({"kind": "reported_accounts", "segment_ids": reporting,
                      "question": "These segments report what characters told or later learned. Accounts may "
                                  "conflict or be revised; confirm which statements are true within the story "
                                  "and the actual sequence of events."})
    if dialogue:
        items.append({"kind": "dialogue_attribution", "segment_ids": list(dict.fromkeys(d["segment_id"] for d in dialogue)),
                      "question": f"{len(dialogue)} quoted lines have no confirmed speaker. Attribute each line."})
    if emphasized:
        items.append({"kind": "emphasized_text", "segment_ids": [e["segment_id"] for e in emphasized],
                      "question": "Confirm what each emphasized line represents (for example a message or writing "
                                  "on a wall) and how it should appear on screen."})
    for n, item in enumerate(items, 1):
        item["id"] = f"HRI_{n:03d}"
        item["status"] = "open"
    return [{"id": i.pop("id"), **i} for i in items]


def canonical_compatibility(text: str) -> dict:
    years = sorted(set(YEAR.findall(text)))
    return {
        "target_schema": "schemas/story/master_story_package.schema.json",
        "compatible_without_fabrication": False,
        "blocking_requirements": [
            {"field": "case.year", "reason": "An integer year is required. " + (
                f"Years found in text: {', '.join(years)}; their role needs review." if years
                else "The story states no explicit year.")},
            {"field": "sources[] (reliability, verification)", "reason": "Historical source verification does not "
             "apply to user-authored fiction; filling it would invent sources."},
            {"field": "claims[].status", "reason": "Statuses such as DOCUMENTED_FACT or LEGEND describe historical "
             "evidence, not fictional canon."},
            {"field": "timeline[].date_start", "reason": "A dated chronology is required; the story uses relative "
             "time, so dates would be invented."},
        ],
        "reusable_parts": ["entities (CHR_/LOC_/OBJ_ IDs)", "continuity_rules", "master_narrative.segments",
                           "formats.short (9:16) / formats.long (16:9) segment selection"],
        "recommendation": "P2.2: add a separate fiction story package variant (own schema and validator) that "
                          "replaces case/sources/claims/timeline with authorship provenance (this intake's source "
                          "hash), in-story canon facts with fiction statuses (for example author_stated, "
                          "character_claim, ambiguous) and relative event order, while reusing entities, "
                          "continuity rules, narrative segments and format plans. The historical validator and "
                          "STORY 053 stay unchanged.",
        "historical_schema_modified": False,
    }


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _output_dir(project: Path) -> Path:
    out = project / OUTPUT_DIR
    for parent in (project / "artifacts", out.parent):
        if parent.is_symlink():
            raise IntakeError("invalid_request", "Intake output path is a symlink; nothing was written.")
    return out


def build_outputs(loaded: dict, created_at: datetime) -> dict[str, bytes]:
    request, source = loaded["request"], loaded["source"]
    text = source.decode("utf-8")
    t = _Text(text)
    segments = segment_source(t)
    body_text = " ".join(SA._clean(s["text"]) for s in segments if s["kind"] != "heading")
    language = SA.detect_language(body_text)
    changes, observations = propose_changes(t, segments, language)
    proposal = apply_changes(text, changes).encode("utf-8")
    inventory, _ = build_inventory(segments, language)
    provenance = {
        "project_id": request["project_id"],
        "production_request": {"path": REQUEST_FILE, "sha256": loaded["request_sha256"]},
        "source": {"path": request["input_file"], "sha256": request["content_sha256"], "bytes": len(source),
                   "chars": len(text), "line_endings": _line_endings(text),
                   "unicode_nfc": unicodedata.is_normalized("NFC", text)},
        "intake_version": INTAKE_VERSION, "generator": "studio.intake",
    }

    def artifact(name, body):
        return {"schema_version": "1.0", "artifact": name, "provenance": provenance, **body}

    files = {
        FILES["segments"]: _json_bytes(artifact("story_segments", {
            "segmentation": "paragraphs = runs of non-blank lines; spans index the original source text",
            "segments": segments})),
        FILES["inventory"]: _json_bytes(artifact("story_inventory", {
            "status": "preliminary", "review_status": "pending_human_review",
            "basis": "deterministic rules and tools.story.story_analyzer closed vocabulary; no model was used",
            "omitted_analyzer_fields": ["gender", "age", "color", "dialogue speaker"],
            **inventory})),
        FILES["proposal"]: proposal,
    }
    files[FILES["changes"]] = _json_bytes(artifact("working_text_changes", {
        "review_status": "pending_human_review",
        "note": "The proposal applies every proposed change for preview only. No change is approved; the original "
                "input/story.md is unchanged and remains authoritative.",
        "proposal": {"path": f"{OUTPUT_DIR}/{FILES['proposal']}", "sha256": _sha(proposal), "bytes": len(proposal)},
        "changes": [{**c, "before_excerpt": _excerpt(text, c["source_span"]["char_start"], c["source_span"]["char_end"]),
                     "after_excerpt": _excerpt(apply_changes(text, [c]), c["source_span"]["char_start"],
                                               c["source_span"]["char_start"])} for c in changes],
        "observations": observations}))
    counts = {"segments": len(segments), "characters": len(inventory["characters"]),
              "locations": len(inventory["locations"]), "objects": len(inventory["objects"]),
              "time_expressions": len(inventory["motifs"]["time_expressions"]),
              "numbers": len(inventory["motifs"]["numbers"]),
              "repeated_lines": len(inventory["motifs"]["repeated_lines"]),
              "repeated_phrases": len(inventory["motifs"]["repeated_phrases"]),
              "dialogue_lines": len(inventory["dialogue"]), "emphasized_lines": len(inventory["emphasized_text"]),
              "narrative_event_candidates": len(inventory["narrative_event_candidates"]),
              "proposed_changes": len(changes), "observations": len(observations),
              "human_interpretation_items": len(inventory["human_interpretation"]),
              "excluded_candidates": len(inventory["excluded_candidates"])}
    heading = next((s["text"] for s in segments if s["kind"] == "heading"), None)
    report = artifact("story_intake_report", {
        "status": "prepared", "created_at": created_at.isoformat().replace("+00:00", "Z"),
        "review": {"status": "pending_human_review", "required": True, "approved": False, "approved_by": None},
        "production_started": False, "publishing_enabled": False, "style": request["style"],
        "formats": request["formats"], "title": request["title"], "source_heading": heading,
        "language": language,
        "analysis_coverage": {
            "overall": "incomplete",
            "deterministic": ["exact paragraph segmentation with char/byte spans", "editorial proposals",
                              "rule-based character/location/object candidates", "time, number, repeated line "
                              "and phrase motifs", "quoted dialogue and emphasized lines (unattributed)",
                              "closed-vocabulary action labels"],
            "semantic": {"status": "not_performed", "engine": None,
                         "reason": "No local model was used. Plot, twists, contradictions, coreference and speaker "
                                   "attribution require human review."},
        },
        "counts": counts,
        "proposed_change_ids": [c["id"] for c in changes],
        "human_interpretation_ids": [i["id"] for i in inventory["human_interpretation"]],
        "canonical_compatibility": canonical_compatibility(text),
        "checkpoint_integration": {
            "checkpoint_written": False,
            "reason": "The character-animation pipeline has no intake stage; writing a research or proposal "
                      "checkpoint would claim stage work that did not happen.",
            "required": "Add an explicit intake/story stage to the pipeline manifest, or let P2.2 consume "
                        f"{OUTPUT_DIR}/ as reviewed input.",
        },
        "outputs": {name: {"path": f"{OUTPUT_DIR}/{name}", "sha256": _sha(data), "bytes": len(data)}
                    for name, data in files.items()},
    })
    files[FILES["report"]] = _json_bytes(report)
    return files


def read_story_intake(store: ProductionStore, project_id: str, loaded: dict | None = None) -> dict:
    """Return verified saved intake output; raise if missing, tampered or stale."""
    loaded = loaded or load_story_request(store, project_id)
    out = _output_dir(loaded["project"])
    report_path = out / FILES["report"]
    if not out.exists():
        raise IntakeError("not_prepared", "Story draft has not been prepared for this production.")
    if not out.is_dir() or not report_path.is_file():
        raise IntakeError("existing_output_invalid", "Saved story draft is incomplete; it was not overwritten. "
                          "Move artifacts/story_intake/v1 aside to prepare it again.")
    try:
        report = json.loads(report_path.read_bytes())
        prov = report["provenance"]
        problems = []
        if prov["production_request"]["sha256"] != loaded["request_sha256"]:
            problems.append("production request hash differs")
        if prov["source"]["sha256"] != loaded["request"]["content_sha256"]:
            problems.append("source hash differs")
        if set(report["outputs"]) != {FILES[k] for k in FILES if k != "report"}:
            problems.append("output list differs")
        for name, meta in report["outputs"].items():
            if _sha((out / name).read_bytes()) != meta["sha256"]:
                problems.append(f"{name} changed")
        if report["review"]["status"] != "pending_human_review" or report["production_started"] is not False:
            problems.append("review or production state changed")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise IntakeError("existing_output_invalid", "Saved story draft is unreadable; it was not overwritten. "
                          "Move artifacts/story_intake/v1 aside to prepare it again.") from exc
    if problems:
        raise IntakeError("existing_output_invalid", "Saved story draft failed verification (" + "; ".join(problems)
                          + "); it was not overwritten. Move artifacts/story_intake/v1 aside to prepare it again.")
    changes = json.loads((out / FILES["changes"]).read_bytes())
    inventory = json.loads((out / FILES["inventory"]).read_bytes())
    return {"report": report, "changes": changes["changes"], "observations": changes["observations"],
            "human_interpretation": inventory["human_interpretation"],
            "candidates": {k: [{"id": c["id"], "label": c["label"], "mention_count": c["mention_count"],
                                "confidence": c["confidence"]} for c in inventory[k]]
                           for k in ("characters", "locations", "objects")},
            "saved_files": [f"{OUTPUT_DIR}/{name}" for name in FILES.values()]}


def prepare_story_intake(store: ProductionStore, project_id: str, now: datetime | None = None) -> dict:
    """Run intake once. Re-runs return the verified existing output; invalid output is never overwritten."""
    loaded = load_story_request(store, project_id)
    out = _output_dir(loaded["project"])
    if out.exists():
        return {"status": "already_prepared", **read_story_intake(store, project_id, loaded)}
    files = build_outputs(loaded, now or datetime.now(timezone.utc))
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.parent / f".tmp-{uuid.uuid4().hex}"
    tmp.mkdir()
    try:
        for name, data in files.items():
            with (tmp / name).open("xb") as f:
                f.write(data)
        try:
            os.rename(tmp, out)  # Atomic publish; fails if another run published first.
        except OSError:
            if not out.exists():
                raise
            return {"status": "already_prepared", **read_story_intake(store, project_id, loaded)}
    finally:
        if tmp.exists():
            shutil.rmtree(tmp)
    return {"status": "created", **read_story_intake(store, project_id, loaded)}
