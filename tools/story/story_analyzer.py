"""Story text -> structured analysis (characters, locations, props, timed beats).

Narration text is always produced by deterministic segmentation of the source, so
the video reproduces the story exactly. Labels (who does what, where, to what) come
from a closed-vocabulary rule pass (Vietnamese/English) and, when a local Ollama
model is reachable, from that model constrained to the same enums. Anything the
model returns outside the vocabulary is dropped and the rule label is kept.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from tools.base_tool import (
    BaseTool, Determinism, ExecutionMode, ResourceProfile, ToolResult,
    ToolRuntime, ToolStability, ToolStatus, ToolTier,
)
from tools.story import lexicon as L

DEFAULT_OLLAMA = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen2.5:7b-instruct"
VI_MARKS = set(L.VI_MARKS)
_ALT = lambda words: "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))  # noqa: E731
ABBREVIATIONS = ("Mr.", "Mrs.", "Ms.", "Dr.", "St.", "Jr.", "Sr.", "TP.", "Th.")


# ---------------------------------------------------------------------------
# Loading and segmentation (deterministic; defines the narration text)
# ---------------------------------------------------------------------------

def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


def load_story(path: str | Path) -> dict:
    raw = Path(path).read_text(encoding="utf-8")
    lines = raw.strip().splitlines()
    title = None
    if lines and lines[0].lstrip().startswith("#"):
        title = _clean(lines[0].lstrip("#"))
        lines = lines[1:]
    paragraphs = [_clean(p) for p in re.split(r"\n\s*\n", "\n".join(lines)) if _clean(p)]
    if not paragraphs:
        raise ValueError(f"Story file has no text: {path}")
    body = " ".join(paragraphs)
    return {"title": title or Path(path).stem, "paragraphs": paragraphs, "language": detect_language(body),
            "source_path": str(Path(path).resolve()),
            "source_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest()}


def detect_language(text: str) -> str:
    letters = [c for c in text.lower() if c.isalpha()]
    marked = sum(c in VI_MARKS for c in letters)
    return "vi" if letters and marked / len(letters) > 0.03 else "en"


def split_sentences(paragraph: str) -> list[str]:
    """Split after . ! ? … (plus an optional closing quote) outside quoted speech.

    A closing quote followed by a lowercase word ("Are you open?" she asked) stays
    one sentence, and so does a quotation containing several sentences.
    """
    out, buf, inside, i = [], "", False, 0
    n = len(paragraph)
    while i < n:
        ch = paragraph[i]
        buf += ch
        if ch == '"':
            inside = not inside
        elif ch in "“«":
            inside = True
        elif ch in "”»":
            inside = False
        if ch in ".!?…" or (ch in '"”»)' and len(buf) > 1 and buf[-2] in ".!?…"):
            j = i + 1
            if j < n and paragraph[j] in '"”»)' and ch in ".!?…":
                i += 1
                continue  # let the closing quote join the buffer first
            if not inside and j < n and paragraph[j].isspace():
                k = j
                while k < n and paragraph[k].isspace():
                    k += 1
                nxt = paragraph[k] if k < n else ""
                if (nxt and (nxt.isupper() or nxt.isdigit() or nxt in '"“«')
                        and not buf.rstrip().endswith(ABBREVIATIONS)):
                    out.append(buf.strip())
                    buf, i = "", k
                    continue
        i += 1
    if buf.strip():
        out.append(buf.strip())
    return out


def _split_long(sentence: str, max_chars: int) -> list[str]:
    if len(sentence) <= max_chars:
        return [sentence]
    commas = [m.end() for m in re.finditer(r",\s", sentence)]
    if not commas:
        return [sentence]
    mid = len(sentence) / 2
    cut = min(commas, key=lambda c: abs(c - mid))
    return _split_long(sentence[:cut].rstrip(), max_chars) + _split_long(sentence[cut:].lstrip(), max_chars)


def segment_story(story: dict, max_chars: int = 130) -> list[dict]:
    segments = []
    for p_index, paragraph in enumerate(story["paragraphs"]):
        for sentence in split_sentences(paragraph):
            for piece in _split_long(sentence, max_chars):
                segments.append({"id": f"b{len(segments) + 1:02d}", "paragraph": p_index, "text": piece})
    if " ".join(s["text"] for s in segments) != " ".join(story["paragraphs"]):
        raise ValueError("Segmentation does not reproduce the source text")
    return segments


# ---------------------------------------------------------------------------
# Phrase matching
# ---------------------------------------------------------------------------

def _phrase_re(phrase: str) -> re.Pattern:
    return re.compile(r"(?<![\w])" + re.escape(phrase) + r"(?![\w])", re.IGNORECASE)


class PhraseTable:
    """Longest-first, non-overlapping phrase matcher over a {label: [phrases]} table."""

    def __init__(self, table: dict[str, list[str]]):
        pairs = [(p, label) for label, phrases in table.items() for p in phrases]
        pairs.sort(key=lambda x: -len(x[0]))
        self.pairs = [(p, label, _phrase_re(p)) for p, label in pairs]

    def find(self, text: str) -> list[tuple[int, int, str, str]]:
        taken: list[tuple[int, int]] = []
        hits = []
        for phrase, label, rx in self.pairs:
            for m in rx.finditer(text):
                if any(m.start() < b and a < m.end() for a, b in taken):
                    continue
                taken.append((m.start(), m.end()))
                hits.append((m.start(), m.end(), label, m.group(0)))
        return sorted(hits)


def _slug(text: str) -> str:
    base = unicodedata.normalize("NFKD", text.replace("\u0111", "d").replace("\u0110", "D"))
    base = "".join(c for c in base if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-") or "x"


def _mask_quotes(text: str) -> str:
    """Replace quoted dialogue by spaces (same length) so offsets stay valid."""
    out, inside = [], False
    for ch in text:
        if ch in L.QUOTE_CHARS:
            inside = (not inside) if ch == '"' else ch in '“«'
            out.append(" ")
        else:
            out.append(" " if inside else ch)
    return "".join(out)


def _quotes(text: str) -> list[str]:
    return [q.strip() for q in re.findall(r'["“«]([^"”»]+)["”»]', text)]


# ---------------------------------------------------------------------------
# Rule analysis
# ---------------------------------------------------------------------------

class RuleAnalyzer:
    def __init__(self, language: str):
        self.lang = language
        self.actions = PhraseTable(L.ACTION_WORDS[language])
        self.locations = PhraseTable(L.LOCATION_WORDS[language])
        self.props = PhraseTable(L.PROP_WORDS[language])
        self.features = PhraseTable(L.FEATURE_WORDS[language])
        self.nouns = PhraseTable({k: [k] for k in L.PERSON_NOUNS[language]})
        self.pronouns = PhraseTable({k: [k] for k in L.PRONOUNS[language]})
        self.colors = PhraseTable({v: [k] for k, v in L.COLORS[language].items()})
        self.night = PhraseTable({"night": L.NIGHT_WORDS[language], "day": L.DAY_WORDS[language]})
        self.rain = PhraseTable({"rain": L.RAIN_WORDS[language], "stop": L.RAIN_STOP_WORDS[language]})
        self.jumps = PhraseTable({"jump": L.TIME_JUMP_WORDS[language]})
        self.negated = PhraseTable({"neg": L.NEGATED_SUBJECTS[language]})
        self.indefinite = PhraseTable({"someone": L.INDEFINITE_SUBJECTS[language]})

    # -- characters --------------------------------------------------------
    def find_names(self, segments: list[dict]) -> list[str]:
        text = " ".join(s["text"] for s in segments)
        masked = _mask_quotes(text)
        # Words the text itself writes in lowercase are common words, not names.
        lowered_words = {w for w in re.findall(r"\w+", masked) if w.islower()}
        stop = L.NAME_STOPWORDS[self.lang]
        counts: dict[str, int] = {}
        mid: set[str] = set()
        verbs_after: set[str] = set()
        for sentence in (s for seg in segments for s in [_mask_quotes(seg["text"])]):
            tokens = [(m.start(), m.group(0)) for m in re.finditer(r"\w+", sentence)]
            for i, (pos, tok) in enumerate(tokens):
                if not tok[0].isupper() or tok.lower() in stop or tok.isdigit():
                    continue
                prev = tokens[i - 1][1].lower() if i else ""
                if prev in L.NAME_BLOCKERS[self.lang]:
                    continue  # weekday or place name, not a person
                counts[tok] = counts.get(tok, 0) + 1
                before = sentence[:pos].rstrip()
                if before and before[-1] not in ".!?:…":
                    mid.add(tok)
                rest = sentence[pos + len(tok):]
                if any(start <= 1 for start, _, _, _ in self.actions.find(rest.lstrip()[:30])):
                    verbs_after.add(tok)
        names = []
        for tok, n in counts.items():
            if tok in mid or ((n >= 2 or tok in verbs_after) and tok.lower() not in lowered_words):
                names.append(tok)
        return names

    def analyze(self, story: dict, segments: list[dict]) -> dict:
        lang = self.lang
        chars: dict[str, dict] = {}
        order: list[str] = []

        def add_char(cid, name, gender="unknown", age="adult", narrator=False, aliases=()):
            if cid not in chars:
                chars[cid] = {"id": cid, "name": name, "aliases": sorted(set(aliases) | {name.lower()}),
                              "gender": gender, "age": age, "is_narrator": narrator, "color": None, "mentions": 0}
                order.append(cid)
            return chars[cid]

        for name in self.find_names(segments):
            add_char(_slug(name), name)
        name_table = PhraseTable({cid: [c["name"]] for cid, c in chars.items()})

        props: dict[str, dict] = {}
        locations: dict[str, dict] = {}
        beats = []
        last_subject = None
        last_prop = None
        last_speaker = None
        time_of_day = None
        weather = None
        location = None

        def resolve_pronoun(gender, exclude=None):
            if gender == "narrator":
                return add_char("narrator", L.NARRATOR_NAME[lang], narrator=True)["id"]
            pool = [c for c in reversed(recent) if c != exclude]
            for cid in pool:
                if chars[cid]["gender"] == gender:
                    return cid
            for cid in pool:  # learn gender from the first matching pronoun
                if chars[cid]["gender"] == "unknown" and gender in ("male", "female"):
                    chars[cid]["gender"] = gender
                    return cid
            return pool[0] if pool and gender == "unknown" else None

        recent: list[str] = []

        def touch(cid):
            if cid in recent:
                recent.remove(cid)
            recent.append(cid)
            chars[cid]["mentions"] += 1

        for seg in segments:
            text = seg["text"]
            masked = _mask_quotes(text)
            low = masked.lower()
            beat_chars: list[str] = []
            beat_actions: list[dict] = []
            # Scene context.
            for _, _, label, _ in self.night.find(low):
                time_of_day = label
            for _, _, label, _ in self.rain.find(low):
                weather = None if label == "stop" else "rain"
            jump = bool(self.jumps.find(low))
            if jump and weather == "rain" and not self.rain.find(low):
                weather = None
            loc_hits = self.locations.find(low)
            if loc_hits:
                kind = loc_hits[-1][2]
                location = kind
                loc = locations.setdefault(kind, {"id": kind, "kind": kind, "name": loc_hits[-1][3],
                                                  "variant": None})
                if any(h[3] in L.BUS_STOP_PHRASES for h in loc_hits):
                    loc["variant"] = "bus_stop"
            # Props mentioned outside quotes.
            for start, end, kind, phrase in self.props.find(low):
                prop = props.setdefault(kind, {"id": kind, "kind": kind, "name": phrase, "color": None,
                                               "vehicle": kind in L.VEHICLE_KINDS})
                window = low[end:end + 14] if lang == "vi" else low[max(0, start - 16):start]
                for _, _, hexcolor, _ in self.colors.find(window):
                    prop["color"] = prop["color"] or hexcolor
                if kind not in L.VEHICLE_KINDS:
                    last_prop = kind
            # Unnamed person nouns introduce characters.
            for start, end, noun, phrase in self.nouns.find(low):
                gender, age = L.PERSON_NOUNS[lang][noun]
                canonical = noun if lang == "vi" else noun.split()[-1]
                cid = _slug(canonical)
                existing = next((c for c in chars.values() if canonical in c["aliases"]), None)
                c = existing or add_char(cid, canonical, gender, age, aliases=(noun, canonical))
                if c["gender"] == "unknown":
                    c["gender"] = gender
                if age != "adult":
                    c["age"] = age
                clause = low[start:start + 40]
                if re.search(f"({_ALT(L.CLOTHING_WORDS)})", clause):
                    for _, _, hexcolor, _ in self.colors.find(clause):
                        c["color"] = c["color"] or hexcolor
            noun_table = PhraseTable({cid: c["aliases"] for cid, c in chars.items() if not c["is_narrator"]})
            # Clauses: subject + verbs.
            spans = self._clauses(masked)
            explicit_subject_in_first = False
            # A subject-less opening clause ("Back home, <name> put ...") belongs to the
            # sentence's first explicit subject, not to the previous sentence.
            sentence_subject = None
            for a, b in spans:
                sentence_subject = self._clause_subject(masked[a:b], noun_table, resolve_pronoun, peek=True)
                if sentence_subject:
                    break
            seen_subject = False
            for ci, (a, b) in enumerate(spans):
                clause = masked[a:b]
                cl = clause.lower()
                if not cl.strip():
                    continue
                if self.negated.find(cl.strip()[:12]):
                    continue
                acts = self.actions.find(cl)
                first_verb = acts[0][0] if acts else len(cl)
                indefinite = any(h[0] < first_verb for h in self.indefinite.find(cl))
                subject = self._clause_subject(clause, noun_table, resolve_pronoun)
                if subject:
                    if ci == 0:
                        explicit_subject_in_first = True
                    seen_subject = True
                    last_subject = subject
                elif not seen_subject and sentence_subject:
                    last_subject = sentence_subject
                for start, end, cid, _ in noun_table.find(cl):
                    if cid not in beat_chars:
                        beat_chars.append(cid)
                vehicle = next((p for p in props.values() if p["vehicle"] and _phrase_re(p["name"]).search(cl)), None)
                for start, end, action, phrase in acts:
                    actor = None if indefinite else last_subject
                    if action in ("vehicle_arrive", "disappear"):
                        actor = None
                    if action in ("idle", "pick_up", "hold", "put_down", "give", "talk", "walk", "sit") and not actor:
                        continue
                    after = cl[end:]
                    target = self._target(after, chars, noun_table, actor, resolve_pronoun, last_prop,
                                          prefer_character=action in ("give", "approach", "wave"))
                    if target is None and action in ("disappear", "reveal", "pick_up", "put_down", "hold"):
                        target = self._target(cl, chars, noun_table, actor, resolve_pronoun, last_prop,
                                              props_only=True)
                    if action in ("board", "vehicle_arrive") and vehicle:
                        target = {"type": "prop", "id": vehicle["id"]}
                    feats = [h[2] for h in self.features.find(cl)]
                    after_feats = [h[2] for h in self.features.find(after)]
                    obj = None
                    if action == "give":  # "gave him the box": recipient is the target, the prop the object
                        obj = self._target(after, chars, noun_table, actor, resolve_pronoun, last_prop,
                                           props_only=True)
                    beat_actions.append({"character_id": actor, "action": action, "phrase": phrase,
                                         "target": target, "object": obj, "features": after_feats or feats,
                                         "offset": a + start})
                    if actor:
                        touch(actor)
                        if actor not in beat_chars:
                            beat_chars.append(actor)
                    if target and target["type"] == "prop" and target["id"] in props:
                        if not props[target["id"]]["vehicle"]:
                            last_prop = target["id"]
            # Dialogue.
            quotes = _quotes(text)
            speaker = None
            if quotes:
                talk = next((x for x in beat_actions if x["action"] == "talk" and x["character_id"]), None)
                only_quote = not masked.strip(" .,:;!?…")
                if talk:
                    speaker = talk["character_id"]
                elif explicit_subject_in_first or only_quote:
                    speaker = last_subject if not only_quote else (last_speaker or last_subject)
                    if speaker:
                        beat_actions.append({"character_id": speaker, "action": "talk", "phrase": "",
                                             "target": None, "features": []})
                if speaker:
                    last_speaker = speaker
            for x in beat_actions:
                if x["character_id"] and x["character_id"] not in beat_chars:
                    beat_chars.append(x["character_id"])
            beat_features = [h[2] for h in self.features.find(low)]
            beats.append({**seg, "location_id": location, "features": beat_features, "time_of_day": time_of_day or "day",
                          "weather": weather, "time_jump": jump, "characters": beat_chars,
                          "actions": beat_actions, "dialogue": {"speaker_id": speaker, "text": " ".join(quotes)}
                          if quotes else None})
        # Backfill the opening beats that precede the first named location.
        first = next((b["location_id"] for b in beats if b["location_id"]), None)
        if first is None:
            first = "room"
            locations["room"] = {"id": "room", "kind": "room", "name": "room", "variant": None}
        for b in beats:
            if b["location_id"] is None:
                b["location_id"] = first
            else:
                break
        first_tod = next((b["time_of_day"] for b in beats if b["time_of_day"]), "day")
        for b in beats:
            b["time_of_day"] = b["time_of_day"] or first_tod
        used_chars = {c for b in beats for c in b["characters"]}
        characters = [chars[c] for c in order if c in used_chars]
        for i, c in enumerate(characters):
            if c["gender"] == "unknown":
                c["gender"] = "female" if i % 2 else "male"
        return {"version": "1.0", "title": story["title"], "language": lang,
                "source_path": story["source_path"], "source_sha256": story["source_sha256"],
                "characters": characters, "locations": list(locations.values()),
                "props": list(props.values()), "beats": beats}

    def _clauses(self, masked: str) -> list[tuple[int, int]]:
        cuts = {0, len(masked)}
        for sep in L.CLAUSE_SPLIT[self.lang]:
            for m in re.finditer(re.escape(sep), masked, re.IGNORECASE):
                cuts.add(m.start())
        for m in re.finditer(r"[:;]", masked):
            cuts.add(m.start())
        edges = sorted(cuts)
        return [(a, b) for a, b in zip(edges, edges[1:])]

    def _clause_subject(self, clause, noun_table, resolve_pronoun, peek=False):
        body = re.sub(rf"^[\s,;:.]*(?:{_ALT(L.LEADING_CONJUNCTIONS)})?\s*", "", clause, flags=re.I)
        head = body.lower()[:28]
        head = re.sub(rf"^(?:{_ALT(L.ARTICLES)})\s+", "", head)
        hits = noun_table.find(head)
        if hits and hits[0][0] <= 6:
            return hits[0][2]
        pro = self.pronouns.find(head)
        if pro and pro[0][0] == 0:
            gender = L.PRONOUNS[self.lang][pro[0][2]]
            if peek:  # pronouns are resolved in order, never while peeking ahead
                return None
            return resolve_pronoun(gender)
        return None

    def _target(self, after, chars, noun_table, actor, resolve_pronoun, last_prop,
                prefer_character=False, props_only=False):
        best = None
        hits = []
        if props_only:
            found = self.props.find(after)
            return {"type": "prop", "id": found[0][2]} if found else None
        hits += [(s, {"type": "prop", "id": k}) for s, _, k, _ in self.props.find(after)]
        hits += [(s, {"type": "character", "id": c}) for s, _, c, _ in noun_table.find(after) if c != actor]
        hits += [(s, {"type": "feature", "id": f}) for s, _, f, _ in self.features.find(after)]
        for s, _, p, _ in self.pronouns.find(after):
            if s == 0 and after[:1].strip():
                continue
            gender = L.PRONOUNS[self.lang][p]
            if p in L.IT_PRONOUNS:
                if last_prop:
                    hits.append((s, {"type": "prop", "id": last_prop}))
                continue
            if gender in ("male", "female"):
                cid = resolve_pronoun(gender, exclude=actor)
                if cid and cid != actor:
                    hits.append((s, {"type": "character", "id": cid}))
        it = re.search(rf"(?<!\w)({_ALT(L.IT_PRONOUNS)})(?!\w)", after)
        if it and last_prop:
            hits.append((it.start(), {"type": "prop", "id": last_prop}))
        if prefer_character and any(h[1]["type"] == "character" for h in hits):
            hits = [h for h in hits if h[1]["type"] == "character"]
        if hits:
            best = min(hits, key=lambda h: h[0])[1]
        return best


# ---------------------------------------------------------------------------
# Optional local LLM labelling (Ollama), constrained to the closed vocabulary
# ---------------------------------------------------------------------------

LLM_SCHEMA = {
    "type": "object",
    "required": ["characters", "segments"],
    "properties": {
        "characters": {"type": "array", "items": {
            "type": "object", "required": ["name", "gender", "age"],
            "properties": {"name": {"type": "string"}, "gender": {"type": "string", "enum": ["male", "female", "unknown"]},
                           "age": {"type": "string", "enum": ["child", "adult", "elder"]},
                           "clothing_color": {"type": "string"}}}},
        "segments": {"type": "array", "items": {
            "type": "object", "required": ["id", "location", "actions"],
            "properties": {
                "id": {"type": "string"},
                "location": {"type": "string", "enum": L.LOCATION_KINDS},
                "time_of_day": {"type": "string", "enum": ["day", "night"]},
                "rain": {"type": "boolean"},
                "actions": {"type": "array", "items": {
                    "type": "object", "required": ["actor", "action"],
                    "properties": {"actor": {"type": "string"}, "action": {"type": "string", "enum": L.ACTIONS},
                                   "target": {"type": "string"}}}}}}},
    },
}


def _llm_prompt(story: dict, segments: list[dict]) -> str:
    lines = "\n".join(f'{s["id"]}: {s["text"]}' for s in segments)
    return (
        "You label a short story for a 2D cartoon animation. Read the numbered sentences and return JSON.\n"
        "Rules:\n"
        "- characters: every person who physically appears (not people only mentioned in dialogue). Use the "
        "name exactly as written in the story (or the short noun phrase used, e.g. 'the girl', 'the old man').\n"
        f"- location for each sentence: one of {L.LOCATION_KINDS} (where the sentence happens; keep the previous "
        "one if unchanged).\n"
        f"- actions: visible physical actions in that sentence, in order, each from {L.ACTIONS}. "
        "actor is a character name from your list. Use 'vehicle_arrive' with actor 'none' for an arriving bus/car. "
        "Use 'reveal' when an object is discovered somewhere (actor = who sees it, or 'none'). "
        "Use 'talk' when a character speaks. Do not invent actions that are not in the sentence.\n"
        f"- target: optional object, person or place feature ({L.FEATURES}) the action is aimed at, as written.\n"
        f"Language of the story: {story['language']}. Title: {story['title']}.\n\n{lines}\n"
    )


def ollama_available(endpoint: str = DEFAULT_OLLAMA, model: str = DEFAULT_MODEL, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(f"{endpoint}/api/tags", timeout=timeout) as resp:
            tags = json.loads(resp.read().decode("utf-8"))
        return any(m.get("name") == model or m.get("model") == model for m in tags.get("models", []))
    except (urllib.error.URLError, OSError, ValueError):
        return False


def call_ollama(prompt: str, endpoint: str, model: str, timeout: float = 600) -> dict:
    payload = {"model": model, "stream": False, "format": LLM_SCHEMA,
               "options": {"temperature": 0, "seed": 7, "num_ctx": 8192},
               "messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request(f"{endpoint}/api/chat", data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return json.loads(body["message"]["content"])


def merge_llm(analysis: dict, llm: dict, language: str) -> tuple[dict, dict]:
    """Merge LLM labels into the rule analysis (rules stay primary). Returns (analysis, report).

    Measured on the test stories, a 7B local model invented exits, swapped actors and
    dropped events when its labels replaced the rule labels. So the model only:
    enriches character gender/age, and fills beats where rules found no action, and
    only with actors named or referred to in that beat. Agreement is reported.
    """
    report = {"accepted_actions": 0, "rejected_actions": 0, "ungrounded_actions": 0, "new_characters": 0,
              "segments_filled": 0, "rule_actions": 0, "rule_actions_confirmed": 0}
    chars = {c["id"]: c for c in analysis["characters"]}

    def match_char(name: str):
        key = name.strip().lower()
        key = re.sub(rf"^({_ALT(L.ARTICLES)})\s+", "", key)
        if not key or key in ("none", "null", "narrator?"):
            return None
        for c in chars.values():
            if key == c["name"].lower() or key in c["aliases"] or c["name"].lower() in key.split():
                return c["id"]
        for c in chars.values():
            if any(a in key for a in c["aliases"] if len(a) > 2):
                return c["id"]
        return None

    for item in llm.get("characters", []):
        name = (item.get("name") or "").strip()
        cid = match_char(name)
        if cid is None and name and len(name) < 40 and any(
                _phrase_re(re.sub(rf"^({_ALT(L.ARTICLES)})\s+", "", name.lower())).search(b["text"].lower())
                for b in analysis["beats"]):
            nouns = L.PERSON_NOUNS[language]
            canonical = re.sub(rf"^({_ALT(L.ARTICLES)})\s+", "", name.lower())
            gender, age = nouns.get(canonical, (item.get("gender", "unknown"), item.get("age", "adult")))
            cid = _slug(canonical)
            chars[cid] = {"id": cid, "name": canonical, "aliases": [canonical], "gender": gender, "age": age,
                          "is_narrator": False, "color": None, "mentions": 0}
            report["new_characters"] += 1
        if cid:
            c = chars[cid]
            if item.get("gender") in ("male", "female") and c["gender"] != item["gender"] and c["mentions"] < 2:
                c["gender"] = item["gender"]
            if item.get("age") in ("child", "elder"):
                c["age"] = item["age"]
    props = {p["id"]: p for p in analysis["props"]}
    features = set(L.FEATURES)
    by_id = {s.get("id"): s for s in llm.get("segments", [])}
    for beat in analysis["beats"]:
        seg = by_id.get(beat["id"])
        if not seg:
            continue
        rule_pairs = {(a["character_id"], a["action"]) for a in beat["actions"]}
        actions = []
        for act in seg.get("actions", []):
            action = act.get("action")
            actor = match_char(act.get("actor", ""))
            if action not in L.ACTIONS or (actor is None and action not in ("vehicle_arrive", "reveal")):
                report["rejected_actions"] += 1
                continue
            target = None
            raw = (act.get("target") or "").strip().lower()
            if raw:
                tid = match_char(raw)
                if tid and tid != actor:
                    target = {"type": "character", "id": tid}
                else:
                    for pid, p in props.items():
                        if p["name"] in raw or pid in raw:
                            target = {"type": "prop", "id": pid}
                            break
                    if target is None:
                        for f in features:
                            if f in raw:
                                target = {"type": "feature", "id": f}
                                break
            actions.append({"character_id": actor, "action": action, "phrase": "llm", "target": target,
                            "features": [target["id"]] if target and target["type"] == "feature" else []})
        llm_pairs = {(a["character_id"], a["action"]) for a in actions}
        report["rule_actions"] += len(rule_pairs)
        report["rule_actions_confirmed"] += len(rule_pairs & llm_pairs)
        if beat["actions"] or not actions:
            continue
        # Fill only: the actor must be named, or referred to, in this very beat.
        text = beat["text"].lower()
        mentioned = set(beat["characters"]) | {cid for cid, c in chars.items()
                                                if any(_phrase_re(a).search(text) for a in c["aliases"])}
        grounded = [a for a in actions if a["character_id"] is None or a["character_id"] in mentioned]
        report["ungrounded_actions"] += len(actions) - len(grounded)
        if grounded:
            beat["actions"] = grounded
            beat["characters"] = sorted({a["character_id"] for a in grounded if a["character_id"]} |
                                        set(beat["characters"]), key=list(chars).index)
            report["accepted_actions"] += len(grounded)
            report["segments_filled"] += 1
    used = {c for b in analysis["beats"] for c in b["characters"]}
    analysis["characters"] = [c for c in chars.values() if c["id"] in used]
    return analysis, report


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_analysis(analysis: dict, story: dict) -> None:
    beats = analysis["beats"]
    if not beats:
        raise ValueError("Analysis has no beats")
    if " ".join(b["text"] for b in beats) != " ".join(story["paragraphs"]):
        raise ValueError("Beats do not reproduce the source text exactly")
    chars = {c["id"] for c in analysis["characters"]}
    props = {p["id"] for p in analysis["props"]}
    locs = {loc["id"] for loc in analysis["locations"]}
    for b in beats:
        if b["location_id"] not in locs:
            raise ValueError(f"{b['id']}: unknown location {b['location_id']}")
        for a in b["actions"]:
            if a["action"] not in L.ACTIONS:
                raise ValueError(f"{b['id']}: unsupported action {a['action']}")
            if a["character_id"] is not None and a["character_id"] not in chars:
                raise ValueError(f"{b['id']}: unknown character {a['character_id']}")
            t = a.get("target")
            if t and ((t["type"] == "prop" and t["id"] not in props) or
                      (t["type"] == "character" and t["id"] not in chars) or
                      (t["type"] == "feature" and t["id"] not in L.FEATURES)):
                raise ValueError(f"{b['id']}: unknown target {t}")


def analyze_story(path: str | Path, backend: str = "auto", endpoint: str = DEFAULT_OLLAMA,
                  model: str = DEFAULT_MODEL, llm_raw_path: str | Path | None = None) -> dict:
    story = load_story(path)
    segments = segment_story(story)
    analysis = RuleAnalyzer(story["language"]).analyze(story, segments)
    info = {"backend": "rules", "requested": backend}
    if backend in ("auto", "ollama"):
        if ollama_available(endpoint, model):
            started = time.monotonic()
            raw = call_ollama(_llm_prompt(story, segments), endpoint, model)
            if llm_raw_path:
                Path(llm_raw_path).write_text(json.dumps(raw, ensure_ascii=False, indent=1), encoding="utf-8")
            analysis, report = merge_llm(analysis, raw, story["language"])
            info = {"backend": "ollama+rules", "requested": backend, "model": model, "endpoint": endpoint,
                    "seconds": round(time.monotonic() - started, 1), "merge": report}
        elif backend == "ollama":
            raise RuntimeError(f"Ollama model {model} not reachable at {endpoint}; use --analyzer rules")
        else:
            info["note"] = f"Ollama model {model} not reachable; rule analysis only"
    analysis["analyzer"] = info
    validate_analysis(analysis, story)
    return analysis


class StoryAnalyzer(BaseTool):
    name = "story_analyzer"
    version = "0.1.0"
    tier = ToolTier.CORE
    capability = "story_analysis"
    provider = "openmontage"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL
    dependencies = []
    install_instructions = "Optional: Ollama with a local model (default qwen2.5:7b-instruct) for LLM labels."
    agent_skills = []
    capabilities = ["story_segmentation", "character_extraction", "action_extraction"]
    supports = {"languages": ["vi", "en"], "backends": ["rules", "ollama"], "offline": True}
    best_for = ["Short narrated stories with a few characters, rooms and handheld props"]
    not_good_for = ["Long novels", "Abstract or non-physical narration", "Languages other than vi/en"]
    resource_profile = ResourceProfile(cpu_cores=1, ram_mb=256, vram_mb=0, disk_mb=1)
    input_schema = {
        "type": "object", "required": ["story_path"],
        "properties": {"story_path": {"type": "string"},
                       "backend": {"type": "string", "enum": ["auto", "rules", "ollama"], "default": "auto"},
                       "endpoint": {"type": "string", "default": DEFAULT_OLLAMA},
                       "model": {"type": "string", "default": DEFAULT_MODEL},
                       "output_path": {"type": "string"}, "llm_raw_path": {"type": "string"}},
    }
    side_effects = ["Writes story_analysis JSON (and raw LLM output) when paths are given"]
    user_visible_verification = ["Review characters, locations and per-beat actions before rendering"]

    def get_status(self) -> ToolStatus:
        return ToolStatus.AVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        start = time.monotonic()
        try:
            analysis = analyze_story(inputs["story_path"], inputs.get("backend", "auto"),
                                     inputs.get("endpoint", DEFAULT_OLLAMA), inputs.get("model", DEFAULT_MODEL),
                                     inputs.get("llm_raw_path"))
        except (KeyError, ValueError, OSError, RuntimeError, urllib.error.URLError) as exc:
            return ToolResult(success=False, error=f"Story analysis failed: {exc}")
        artifacts = []
        if inputs.get("output_path"):
            out = Path(inputs["output_path"])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(analysis, ensure_ascii=False, indent=1), encoding="utf-8")
            artifacts.append(str(out))
        return ToolResult(success=True, data={"story_analysis": analysis}, artifacts=artifacts, cost_usd=0,
                          duration_seconds=round(time.monotonic() - start, 2))
