"""Deterministic visual proposals over verified fiction canon; never edit story content."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import jsonschema

from tools.character import horror_assets as assets

SCHEMA = Path(__file__).resolve().parents[1] / "schemas/story/story_visual_bible.schema.json"
STYLE = "cinematic_2d_cartoon_supernatural_horror"
POLICY = "Preserve canonical uncertainty; never invent a figure or reveal an unseen identity."


class VisualBibleError(ValueError):
    def __init__(self, code, message, blockers=None):
        super().__init__(message)
        self.code, self.blockers = code, blockers or []


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def library_ref():
    try:
        manifest = assets.manifest()
    except ValueError as exc:
        raise VisualBibleError("visual_invalid", "Asset library integrity failed; no revision was substituted.") from exc
    return {"id": assets.LIBRARY_ID, "version": assets.LIBRARY_VERSION, "sha256": fingerprint(manifest)}


def pin(kind, ref):
    if ref is None:
        return None
    fields(ref, {"id", "revision"}, "Asset reference")
    if type(ref["revision"]) is not int or ref["revision"] < 1:
        raise VisualBibleError("invalid_binding", "Asset revision must be a positive integer.")
    try:
        asset = assets.get(kind, ref["id"], ref["revision"])
    except (ValueError, TypeError) as exc:
        raise VisualBibleError("invalid_binding", str(exc)) from exc
    return {"kind": kind, "id": asset["id"], "revision": asset["revision"], "sha256": assets.content_hash(asset)}


def fields(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise VisualBibleError("invalid_binding", f"{label}: expected exactly {sorted(keys)}.")


def default_choices(canon):
    """Unique suggestions are proposals only, never facts or automatically approved designs."""
    available = iter(sorted(assets.CHARACTERS))
    characters = {}
    for c in canon["characters"]:
        unseen = c.get("on_screen_policy") in {"not_shown_pending_review", "partial"} or c["identity_status"] == "ambiguous"
        name = None if unseen else next(available, None)
        characters[c["id"]] = {"representation": "unseen" if unseen else "character",
                               "asset": {"id": name, "revision": 1} if name else None, "reviewed": False}
    return {"characters": characters,
            "locations": {c["id"]: {"environment": None, "lighting": None, "flicker_lamp": None,
                                      "presence": None, "reviewed": False} for c in canon["locations"]},
            "props": {c["id"]: {"asset": None, "location_id": c.get("location_id"), "anchor": None,
                                  "reviewed": False} for c in canon["objects"]},
            "continuity_reviewed": False}


def prop_anchors(env, prop_id):
    """Only actual renderer-supported prop/anchor combinations, in world coordinates."""
    if prop_id not in assets.get("environment", env["id"], env["revision"])["props"]:
        return {}
    f = env["features"]
    if prop_id == "interior_door":
        return {f"doors.{d['id']}.handle": d["handle"] for d in f["doors"]}
    if prop_id == "sash_window":
        return {f"windows.{w['id']}.centre": [w["rect"]["x"] + w["rect"]["w"] / 2,
                                               w["rect"]["y"] + w["rect"]["h"] / 2] for w in f["windows"]}
    return {f"lamps.{l['id']}.bulb": [l["x"], l["y"]] for l in f["lamps"]
            if (prop_id == "ceiling_lamp") == (l["kind"] == "ceiling")}


def catalog():
    assets.check_library()
    return {"library": library_ref(), "assets": assets.manifest()["assets"],
            "environments": {key: {"anchors": assets.environment(key)["features"],
                                     "prop_anchors": {p: prop_anchors(assets.environment(key), p)
                                                      for p in assets.PROPS}} for key in assets.ENVIRONMENTS},
            "limitations": ["Bent-knee/stylized walking", "No independently animated fingers",
                            "Limited viewing angles", "Synthetic Foley", "Flat ghost silhouettes",
                            "Vector lighting; no full-body cast shadows", "Subjective audio review pending"]}


def compile_bible(project_id, version, canon, canonical_ref, choices):
    fields(choices, {"characters", "locations", "props", "continuity_reviewed"}, "Visual choices")
    for collection, source in (("characters", "characters"), ("locations", "locations"), ("props", "objects")):
        fields(choices[collection], {r["id"] for r in canon[source]}, collection)
    if type(choices["continuity_reviewed"]) is not bool:
        raise VisualBibleError("invalid_binding", "Continuity review must be boolean.")
    blockers, characters, locations, props = [], [], [], []
    used = set()

    def review(row, label):
        if type(row["reviewed"]) is not bool:
            raise VisualBibleError("invalid_binding", "Review acknowledgement must be boolean.")
        if not row["reviewed"]:
            blockers.append(f"UNREVIEWED {label}: review this creative proposal explicitly.")

    def provenance(collection, item):
        return {"canonical_ref": f"{collection}.{item['id']}", "description": item["description"],
                "evidence": copy.deepcopy(item["evidence"]),
                "design_basis": "creative_proposal_not_canonical_fact"}

    for c in canon["characters"]:
        row = choices["characters"][c["id"]]
        fields(row, {"representation", "asset", "reviewed"}, c["id"])
        mode = row["representation"]
        if not isinstance(mode, str) or mode not in {"character", "silhouette", "unseen"}:
            raise VisualBibleError("invalid_binding", "Unknown character representation.")
        restricted = c.get("on_screen_policy") in {"not_shown_pending_review", "partial"} or c["identity_status"] == "ambiguous"
        if mode == "unseen":
            if not restricted:
                blockers.append(f"UNBOUND {c['id']}: required character cannot be hidden.")
            if row["asset"] is not None:
                raise VisualBibleError("invalid_binding", "Unseen characters must not carry visual assets.")
            ref = appearance = None
        else:
            if restricted and not (mode == "silhouette" and c.get("on_screen_policy") == "partial"):
                blockers.append(f"UNCERTAINTY {c['id']}: canon does not authorize revealing this identity.")
            ref = pin("silhouette" if mode == "silhouette" else "character", row["asset"])
            if ref is None:
                blockers.append(f"MISSING_ASSET {c['id']}: no compatible identity is assigned.")
            elif (ref["kind"], ref["id"]) in used:
                blockers.append(f"CONFLICTING_IDENTITY {c['id']}: one identity cannot play unrelated roles.")
            if ref:
                used.add((ref["kind"], ref["id"]))
            appearance = (assets.character_look(ref["id"], ref["revision"]) if ref and mode == "character"
                          else assets.get("silhouette", ref["id"], ref["revision"]) if ref else None)
        review(row, c["id"])
        characters.append({"canonical_id": c["id"], "label": c["name"], "representation": mode,
                           "asset": ref, "appearance": appearance, "reviewed": row["reviewed"],
                           "provenance": provenance("characters", c)})

    for c in canon["locations"]:
        row = choices["locations"][c["id"]]
        fields(row, {"environment", "lighting", "flicker_lamp", "presence", "reviewed"}, c["id"])
        if row["flicker_lamp"] is not None and not isinstance(row["flicker_lamp"], str):
            raise VisualBibleError("invalid_binding", "Flicker lamp must be a lamp identifier or null.")
        env_ref, light_ref = pin("environment", row["environment"]), pin("lighting", row["lighting"])
        env, geometry = None, None
        if env_ref is None or light_ref is None:
            blockers.append(f"UNBOUND {c['id']}: select an environment and compatible lighting.")
        if env_ref:
            env = assets.environment(env_ref["id"], env_ref["revision"])
        presence = row["presence"]
        if presence is not None:
            fields(presence, {"character_id", "anchor"}, "Presence")
            if not all(isinstance(v, str) for v in presence.values()):
                raise VisualBibleError("invalid_binding", "Presence requires canonical character and anchor identifiers.")
            figure = next((a for a in characters if a["canonical_id"] == presence["character_id"]), None)
            if not figure or figure["representation"] != "silhouette" or not figure["asset"]:
                raise VisualBibleError("invalid_binding", "Presence requires a canonical, explicitly bound partial silhouette.")
            allowed = {e["location_id"] for e in canon["events"] if presence["character_id"] in e["participant_ids"]}
            if c["id"] not in allowed:
                blockers.append(f"CANONICAL_PRESENCE_LOCATION {c['id']}: presence is not located here in the reviewed canon.")
        if env and light_ref:
            try:
                if row["flicker_lamp"] is not None and (light_ref["id"] != "flickering_interior" or
                        row["flicker_lamp"] not in [l["id"] for l in env["features"]["lamps"]]):
                    raise ValueError("Flicker lamp is incompatible with this lighting/environment.")
                # Reuse P3.2A's environment-derived geometry, including its fail-closed feature checks.
                geometry = assets.lighting_geometry(env, light_ref["id"], flicker_lamp=row["flicker_lamp"],
                    presence=(presence["anchor"], figure["asset"]["id"]) if presence else None)
            except (ValueError, TypeError) as exc:
                blockers.append(f"INCOMPATIBLE_LIGHTING_OR_ANCHOR {c['id']}: {exc}")
        review(row, c["id"])
        locations.append({"canonical_id": c["id"], "label": c["name"], "environment": env_ref,
                          "lighting": light_ref, "atmosphere": "tense_apartment", "geometry": geometry,
                          "anchors": env["features"] if env else None, "presence": copy.deepcopy(presence),
                          "reviewed": row["reviewed"], "provenance": provenance("locations", c)})

    for c in canon["objects"]:
        row = choices["props"][c["id"]]
        fields(row, {"asset", "location_id", "anchor", "reviewed"}, c["id"])
        if (row["location_id"] is not None and not isinstance(row["location_id"], str)) or (row["anchor"] is not None and not isinstance(row["anchor"], str)):
            raise VisualBibleError("invalid_binding", "Prop location and anchor must be identifiers.")
        ref = pin("prop", row["asset"])
        loc = next((l for l in locations if l["canonical_id"] == row["location_id"]), None)
        point = None
        if c.get("location_id") and row["location_id"] != c["location_id"]:
            blockers.append(f"CANONICAL_LOCATION {c['id']}: prop location must match the reviewed story.")
        used_locations = {e["location_id"] for e in canon["events"] if c["id"] in e["object_ids"]}
        if used_locations - {row["location_id"]}:
            blockers.append(f"PROP_CONTINUITY {c['id']}: bind its canonical event location; moving/multi-location props need additional supported states.")
        if ref and loc and loc["environment"]:
            env = assets.environment(loc["environment"]["id"], loc["environment"]["revision"])
            point = prop_anchors(env, ref["id"]).get(row["anchor"]) if isinstance(row["anchor"], str) else None
        if point is None:
            blockers.append(f"MISSING_PROP_OR_ANCHOR {c['id']}: select a supported prop and interaction anchor.")
        review(row, c["id"])
        props.append({"canonical_id": c["id"], "label": c["name"], "asset": ref,
                      "location_id": row["location_id"], "anchor": row["anchor"], "point": point,
                      "persistent": c["persistent"], "reviewed": row["reviewed"],
                      "provenance": provenance("objects", c)})
    if not choices["continuity_reviewed"]:
        blockers.append("UNREVIEWED_CONTINUITY: review shared Short/Long identity and canonical ambiguity constraints.")
    identities = {r["canonical_id"]: fingerprint({"asset": r["asset"], "appearance": r["appearance"],
                                                "representation": r["representation"]}) for r in characters}
    environments = {r["canonical_id"]: fingerprint({k: r[k] for k in ("environment", "lighting", "geometry", "anchors")})
                    for r in locations}
    result = {"schema_version": "1.0", "artifact": "story_visual_bible", "project_id": project_id,
              "version": version, "canonical_input": copy.deepcopy(canonical_ref), "library": library_ref(),
              "style": STYLE, "characters": characters, "locations": locations, "props": props,
              "continuity": {"canonical_rules": copy.deepcopy(canon["continuity_rules"]),
                             "canonical_ambiguities": copy.deepcopy(canon["ambiguities"]), "uncertainty_policy": POLICY,
                             "identity_rule": "same_identity_costume_and_environment_across_all_shots_short_and_long",
                             "reviewed": choices["continuity_reviewed"]},
              "formats": {fmt: {"characters": copy.deepcopy(identities), "locations": copy.deepcopy(environments)}
                          for fmt in ("short", "long")},
              "unresolved_visual_decisions": list(blockers), "blockers": list(blockers),
              "review_status": "pending_explicit_visual_approval", "approval_scope": "scene_planning_only",
              "production_started": False, "publishing_enabled": False}
    jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8"))).validate(result)
    return result
