"""Master Story Package: one researched canon feeding both Short and Long formats.

A package (``schemas/story/master_story_package.schema.json``) holds sources,
claims with an epistemic status, a timeline, characters/locations/objects,
continuity rules, the master narrative (segments) and the Short/Long format
plans. A format plan only selects master segments by ID, so every format sees
the same claims, statuses, entities and events; it cannot restate them.

Validation is offline and deterministic. It checks structure and the reference
graph; it does not certify that a claim is true or that narration wording keeps
a qualifier (those stay human review items, listed in the report).

    python -m lib.master_story validate <package.json>
    python -m lib.master_story resolve <package.json> short|long [-o out.json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import jsonschema
from referencing import Registry, Resource

SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schemas" / "story"
STATUSES = ("DOCUMENTED_FACT", "REPORTED_ACCOUNT", "LATER_INTERPRETATION", "HYPOTHESIS", "LEGEND", "UNKNOWN")
ENTITY_PREFIX = {"characters": "CHR_", "locations": "LOC_", "objects": "OBJ_"}
FORMAT_SHAPE = {"short": "9:16", "long": "16:9"}


class MasterStoryError(ValueError):
    """Raised with every problem found, one per line."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("\n".join(problems))


def _schema(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def _validator(name: str) -> jsonschema.protocols.Validator:
    plan = _schema("format_plan.schema.json")
    registry = Registry().with_resource(plan["$id"], Resource.from_contents(plan))
    schema = _schema(name)
    return jsonschema.Draft202012Validator(schema, registry=registry)


def _schema_problems(name: str, data: dict) -> list[str]:
    errors = sorted(_validator(name).iter_errors(data), key=lambda e: list(e.absolute_path))
    return [f"SCHEMA {'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}" for e in errors]


def _date_key(value: str) -> tuple:
    """Sortable key for YYYY[-MM[-DD[THH:MM]]]; missing parts sort first."""
    parts = [int(x) for x in re.split(r"[-T:]", value)]
    return tuple(parts + [0] * (5 - len(parts)))


def _index(package: dict) -> dict:
    entities = {e["id"]: (kind, e) for kind, rows in package["entities"].items() for e in rows}
    return {"sources": {s["id"]: s for s in package["sources"]},
            "claims": {c["id"]: c for c in package["claims"]},
            "events": {e["id"]: e for e in package["timeline"]},
            "entities": entities,
            "segments": {s["id"]: s for s in package["master_narrative"]["segments"]},
            "rules": {r["id"]: r for r in package["continuity_rules"]}}


def _duplicates(package: dict) -> list[str]:
    seen, problems = {}, []
    groups = [("sources", package["sources"]), ("claims", package["claims"]), ("timeline", package["timeline"]),
              ("continuity_rules", package["continuity_rules"]),
              ("segments", package["master_narrative"]["segments"])]
    groups += [(f"entities.{kind}", rows) for kind, rows in package["entities"].items()]
    for where, rows in groups:
        for row in rows:
            if row["id"] in seen:
                problems.append(f"DUPLICATE_ID {row['id']} in {where} (first in {seen[row['id']]})")
            seen.setdefault(row["id"], where)
    return problems


def _graph_problems(package: dict, idx: dict) -> list[str]:
    p = []
    sources, claims, events, entities = idx["sources"], idx["claims"], idx["events"], idx["entities"]
    for claim in package["claims"]:
        support = claim["supporting_source_ids"]
        refs = support + claim.get("contradicting_source_ids", [])
        p += [f"UNRESOLVED_SOURCE {claim['id']} -> {s}" for s in refs if s not in sources]
        if claim["status"] != "UNKNOWN" and not support:
            p.append(f"UNSUPPORTED_CLAIM {claim['id']} is {claim['status']} without supporting sources")
        event = claim.get("event_id")
        if event is not None and (event not in events or claim["id"] not in events[event]["claim_ids"]):
            p.append(f"CLAIM_EVENT_MISMATCH {claim['id']} -> {event}")
    previous = None
    for event in package["timeline"]:
        p += [f"UNRESOLVED_CLAIM {event['id']} -> {c}" for c in event["claim_ids"] if c not in claims]
        p += [f"UNRESOLVED_ENTITY {event['id']} -> {e}" for e in event.get("entity_ids", []) if e not in entities]
        for c in event["claim_ids"]:
            if c in claims and claims[c].get("event_id") not in (None, event["id"]):
                p.append(f"CLAIM_EVENT_MISMATCH {c} is linked to {claims[c]['event_id']}, listed in {event['id']}")
        start = _date_key(event["date_start"])
        if (event["precision"] == "range") != ("date_end" in event):
            p.append(f"EVENT_RANGE {event['id']}: precision 'range' requires date_end and only then")
        if "date_end" in event and _date_key(event["date_end"]) < start:
            p.append(f"EVENT_RANGE {event['id']}: date_end before date_start")
        if previous is not None and start < previous[1]:
            p.append(f"TIMELINE_ORDER {event['id']} starts before {previous[0]}")
        previous = (event["id"], start)
    for kind, rows in package["entities"].items():
        for entity in rows:
            if not entity["id"].startswith(ENTITY_PREFIX[kind]):
                p.append(f"ENTITY_PREFIX {entity['id']} in {kind} must start with {ENTITY_PREFIX[kind]}")
            p += [f"UNRESOLVED_CLAIM {entity['id']} -> {c}" for c in entity["claim_ids"] if c not in claims]
    for rule in package["continuity_rules"]:
        for field in ("when_claim_ids", "require_claim_ids", "claim_ids"):
            p += [f"UNRESOLVED_CLAIM {rule['id']}.{field} -> {c}" for c in rule.get(field, []) if c not in claims]
        p += [f"UNRESOLVED_ENTITY {rule['id']} -> {e}" for e in rule.get("entity_ids", []) if e not in entities]
        if rule["check"] == "requires_claims" and not (rule.get("when_claim_ids") and rule.get("require_claim_ids")):
            p.append(f"RULE_INCOMPLETE {rule['id']}: requires_claims needs when_claim_ids and require_claim_ids")
    for seg in package["master_narrative"]["segments"]:
        ids = set(seg["claim_ids"])
        if not ids and not seg.get("nonfactual"):
            p.append(f"UNGROUNDED_SEGMENT {seg['id']} has no claim_ids (mark nonfactual if intended)")
        p += [f"UNRESOLVED_CLAIM {seg['id']} -> {c}" for c in ids if c not in claims]
        for e in seg.get("entity_ids", []):
            if e not in entities:
                p.append(f"UNRESOLVED_ENTITY {seg['id']} -> {e}")
            elif not ids & set(entities[e][1]["claim_ids"]):
                p.append(f"UNGROUNDED_ENTITY {seg['id']} -> {e}: no shared claim")
        for e in seg.get("event_ids", []):
            if e not in events:
                p.append(f"UNRESOLVED_EVENT {seg['id']} -> {e}")
            elif not ids & set(events[e]["claim_ids"]):
                p.append(f"UNGROUNDED_EVENT {seg['id']} -> {e}: no shared claim")
        cited = {s for c in ids if c in claims
                 for s in claims[c]["supporting_source_ids"] + claims[c].get("contradicting_source_ids", [])}
        for s in seg.get("source_ids", []):
            if s not in sources:
                p.append(f"UNRESOLVED_SOURCE {seg['id']} -> {s}")
            elif s not in cited:
                p.append(f"UNGROUNDED_SOURCE {seg['id']} -> {s}: not cited by the segment's claims")
    return p


def _rule_problems(package: dict, claim_ids: set[str], where: str) -> list[str]:
    problems = []
    for rule in package["continuity_rules"]:
        when = set(rule.get("when_claim_ids", []))
        if rule["check"] != "requires_claims" or not claim_ids & when:
            continue
        missing = sorted(set(rule.get("require_claim_ids", [])) - claim_ids)
        if missing:
            problems.append(f"CONTINUITY {rule['id']} in {where}: uses {sorted(claim_ids & when)} without {missing}")
    return problems


def format_claims(package: dict, plan: dict) -> set[str]:
    segments = {s["id"]: s for s in package["master_narrative"]["segments"]}
    return {c for sid in plan["segment_ids"] if sid in segments for c in segments[sid]["claim_ids"]}


def _format_problems(package: dict, plan: dict, name: str) -> list[str]:
    p = [f"{x} (format {name})" for x in _schema_problems("format_plan.schema.json", plan)]
    if p:
        return p
    if plan["format"] != name:
        p.append(f"FORMAT_KIND {name}: plan declares format {plan['format']!r}")
    if plan["aspect_ratio"] != FORMAT_SHAPE[name]:
        p.append(f"FORMAT_SHAPE {name}: aspect ratio must be {FORMAT_SHAPE[name]}")
    if (plan["package_id"], plan["package_version"]) != (package["package_id"], package["package_version"]):
        p.append(f"PACKAGE_MISMATCH {name}: {plan['package_id']}@{plan['package_version']} is not "
                 f"{package['package_id']}@{package['package_version']}")
    order = [s["id"] for s in package["master_narrative"]["segments"]]
    unknown = [s for s in plan["segment_ids"] if s not in order]
    p += [f"UNRESOLVED_SEGMENT {name} -> {s}" for s in unknown]
    positions = [order.index(s) for s in plan["segment_ids"] if s in order]
    if positions != sorted(positions):
        p.append(f"SEGMENT_ORDER {name}: segments must follow master narrative order")
    low, high = plan["target_seconds"]["min"], plan["target_seconds"]["max"]
    if low > high:
        p.append(f"TARGET_RANGE {name}: min greater than max")
    p += _rule_problems(package, format_claims(package, plan), f"format {name}")
    return p


def duration_warnings(package: dict) -> list[str]:
    """Estimated durations are advisory: real duration depends on the voice and is gated on
    measured audio (lib/master_story_short.py). M2.2 measured Korva 30-45 % above V2 estimates."""
    warnings = []
    order = {s["id"]: s for s in package["master_narrative"]["segments"]}
    for name in ("short", "long"):
        plan = package["formats"][name]
        estimate = sum(order[s]["estimated_seconds"] for s in plan["segment_ids"] if s in order)
        low, high = plan["target_seconds"]["min"], plan["target_seconds"]["max"]
        if not low <= estimate <= high:
            warnings.append(f"DURATION_ESTIMATE {name}: estimated {estimate:.1f}s outside {low}-{high}s "
                            "(advisory; measure real audio)")
    return warnings


def validate_package(package: dict) -> dict:
    """Validate a package and both embedded formats; return a summary or raise MasterStoryError."""
    problems = _schema_problems("master_story_package.schema.json", package)
    if problems:
        raise MasterStoryError(problems)
    idx = _index(package)
    problems = _duplicates(package) + _graph_problems(package, idx)
    used = {c for s in package["master_narrative"]["segments"] for c in s["claim_ids"]}
    problems += _rule_problems(package, used, "master narrative segments")
    for name in ("short", "long"):
        problems += _format_problems(package, package["formats"][name], name)
    if not problems:
        short, long = (format_claims(package, package["formats"][n]) for n in ("short", "long"))
        extra = sorted(short - long)
        if extra:
            problems.append(f"SHORT_NOT_IN_LONG claims {extra} appear in Short but not in Long")
    if problems:
        raise MasterStoryError(problems)
    counts = {status: 0 for status in STATUSES}
    for claim in package["claims"]:
        counts[claim["status"]] += 1
    return {"package": f"{package['package_id']}@{package['package_version']}",
            "sources": len(package["sources"]), "claims": len(package["claims"]), "claim_status": counts,
            "events": len(package["timeline"]),
            "entities": {k: len(v) for k, v in package["entities"].items()},
            "segments": len(package["master_narrative"]["segments"]),
            "formats": {n: {"segments": len(package["formats"][n]["segment_ids"]),
                            "estimated_seconds": round(resolve_format(package, n)["estimated_seconds"], 1)}
                        for n in ("short", "long")},
            "human_review_rules": [r["id"] for r in package["continuity_rules"] if r["check"] == "human_review"],
            "warnings": duration_warnings(package)}


def validate_external_format(package: dict, plan: dict) -> None:
    """Validate a separately stored Short/Long plan against an already valid package."""
    name = plan.get("format") if plan.get("format") in FORMAT_SHAPE else "short"
    problems = _format_problems(package, plan, name)
    if problems:
        raise MasterStoryError(problems)


def resolve_format(package: dict, name: str, plan: dict | None = None) -> dict:
    """Shared, read-only view of one format: segment text plus the canonical records it uses."""
    plan = plan or package["formats"][name]
    idx = _index(package)
    segments = [idx["segments"][s] for s in plan["segment_ids"]]
    claim_ids = [c for c in idx["claims"] if any(c in s["claim_ids"] for s in segments)]
    claims = [idx["claims"][c] for c in claim_ids]
    source_ids = sorted({s for c in claims for s in c["supporting_source_ids"] + c.get("contradicting_source_ids", [])})
    entity_ids = sorted({e for s in segments for e in s.get("entity_ids", [])})
    event_ids = [e for e in idx["events"] if set(idx["events"][e]["claim_ids"]) & set(claim_ids)]
    return {"package_id": package["package_id"], "package_version": package["package_version"],
            "format": name, "aspect_ratio": plan["aspect_ratio"], "language": package["language"],
            "estimated_seconds": sum(s["estimated_seconds"] for s in segments),
            "segments": [{"id": s["id"], "text": s["text"], "claim_ids": s["claim_ids"]} for s in segments],
            "claims": claims,
            "sources": [idx["sources"][s] for s in source_ids],
            "entities": [{"kind": idx["entities"][e][0], **idx["entities"][e][1]} for e in entity_ids],
            "events": [idx["events"][e] for e in event_ids],
            "continuity_rules": [r for r in package["continuity_rules"]
                                 if set(r.get("when_claim_ids", []) + r.get("claim_ids", [])) & set(claim_ids)]}


def load(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("validate")
    check.add_argument("package", type=Path)
    view = sub.add_parser("resolve")
    view.add_argument("package", type=Path)
    view.add_argument("format", choices=["short", "long"])
    view.add_argument("-o", "--output", type=Path)
    args = parser.parse_args(argv)
    package = load(args.package)
    try:
        summary = validate_package(package)
    except MasterStoryError as exc:
        print(f"INVALID {args.package}", file=sys.stderr)
        for problem in exc.problems:
            print("  " + problem, file=sys.stderr)
        return 1
    if args.command == "validate":
        print(json.dumps({"status": "valid", **summary}, ensure_ascii=False, indent=1))
        return 0
    text = json.dumps(resolve_format(package, args.format), ensure_ascii=False, indent=1)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
