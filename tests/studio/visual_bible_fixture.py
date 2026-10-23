"""Entirely synthetic two-person/two-location fiction, never a private pilot."""
import copy

from studio.fiction import build_fiction_package
from studio.intake import prepare_story_intake
from studio.models import NewProduction
from studio.review import _context, record_decision, targets
from studio.reviewed import approve_reviewed_story, materialize_reviewed_story

STORY = ("# TEST FIXTURE — Hai tiếng gõ\n\n"
         "An đứng trong căn phòng cũ, bên cánh cửa đã đóng.\n\n"
         "Bình đợi ở hành lang, dưới chiếc đèn trần.\n\n"
         "Hai tiếng gõ vang lên. Không ai biết tiếng gõ đến từ đâu.\n\n"
         "An nhìn Bình nhưng cả hai vẫn đứng yên.")
STAGING = {"action": "The two people hold still.", "environment": "Room and adjoining corridor.",
           "camera": "Restrained framing.", "uncertainty": "Do not show the unknown source of the knocks.", "reveal": False}


def draft():
    data = {"package_id": "FIC_VISUAL_FIXTURE", "title": "[SYNTHETIC TEST] Hai tiếng gõ", "authored_by": "test fixture",
            "basis": "Isolated synthetic visual-review integration fixture.", "semantic_basis": "Exact synthetic source evidence only.",
            "coverage_missing": [],
            "characters": [{"id": i, "name": n, "aliases": [], "description": "Named person; appearance unspecified.",
                            "identity_status": "narrated", "on_screen_policy": "shown", "evidence": [e]}
                           for i, n, e in [("CHR_AN", "An", "An đứng"), ("CHR_BINH", "Bình", "Bình đợi")]],
            "locations": [{"id": i, "name": n, "description": n,
                           "environment": {"source_details": [n], "proposed_staging": "Creative proposal requires review."},
                           "evidence": [e]} for i, n, e in [("LOC_ROOM", "Căn phòng cũ", "căn phòng cũ"),
                                                              ("LOC_HALL", "Hành lang", "hành lang")]],
            "objects": [{"id": i, "name": n, "description": n, "persistent": True, "location_id": l, "evidence": [e]}
                        for i, n, l, e in [("OBJ_DOOR", "Closed door", "LOC_ROOM", "cánh cửa đã đóng"),
                                           ("OBJ_LAMP", "Ceiling lamp", "LOC_HALL", "chiếc đèn trần")]],
            "facts": [], "dialogue": [], "motifs": [],
            "events": [{"id": "EVT_WAIT", "label": "An waits by the door", "story_phase": "present", "certainty": "depicted",
                        "participant_ids": ["CHR_AN"], "location_id": "LOC_ROOM", "object_ids": ["OBJ_DOOR"],
                        "fact_ids": [], "time_markers": [], "segments": ["SEG_0002"]},
                       {"id": "EVT_KNOCK", "label": "Knocks are heard; source unknown", "story_phase": "present", "certainty": "depicted",
                        "participant_ids": ["CHR_AN", "CHR_BINH"], "location_id": "LOC_HALL", "object_ids": ["OBJ_LAMP"],
                        "fact_ids": [], "time_markers": [], "segments": ["SEG_0003..SEG_0005"]}],
            "sound_cues": [{"id": "SND_KNOCK", "label": "Two knocks", "kind": "diegetic", "event_ids": ["EVT_KNOCK"],
                            "proposed_treatment": "Quiet knocks, no invented source.", "evidence": ["Hai tiếng gõ vang lên."]}],
            "ambiguities": [{"id": "AMB_SOURCE", "question": "Where do the knocks come from?", "status": "unresolved",
                             "related_ids": ["EVT_KNOCK"], "production_guidance": "Do not invent or show a figure.",
                             "evidence": ["Không ai biết tiếng gõ đến từ đâu."]}],
            "continuity_rules": [{"id": "CONT_DOOR", "rule": "The door remains closed.", "related_ids": ["OBJ_DOOR"],
                                  "evidence": ["cánh cửa đã đóng"]}],
            "stickman_production": {"style": "stickman_horror_2d", "primary_output": "character_animation_in_horror_environments",
                "forbidden_primary_treatments": ["documentary_motion_graphics", "text_slideshow", "stock_footage_montage", "static_image_zoom", "infographic_replacement"],
                "characters": [], "uncertainty_policy": "Do not depict the unknown source.", "status": "preliminary_not_rendered"},
            "formats": {}}
    for fmt, prefix in [("short", "S"), ("long", "L")]:
        beats = [{"id": f"BEAT_{prefix}1", "narration": {"mode": "verbatim", "spans": ["SEG_0002"]},
                  "event_ids": ["EVT_WAIT"], "character_ids": ["CHR_AN"], "location_id": "LOC_ROOM",
                  "object_ids": ["OBJ_DOOR"], "sound_cue_ids": [], "silence_after_seconds": 1, "staging": STAGING},
                 {"id": f"BEAT_{prefix}2", "narration": {"mode": "verbatim", "spans": ["SEG_0003..SEG_0005"]},
                  "event_ids": ["EVT_KNOCK"], "character_ids": ["CHR_AN", "CHR_BINH"], "location_id": "LOC_HALL",
                  "object_ids": ["OBJ_LAMP"], "sound_cue_ids": ["SND_KNOCK"], "silence_after_seconds": 1, "staging": STAGING}]
        data["formats"][fmt] = {"intent": "Synthetic identity consistency proof.", "depends_on_changes": [], "excluded_segments": [],
                                "chapters": [{"id": f"CH_{prefix}1", "title": "Waiting", "beats": beats}]}
    return copy.deepcopy(data)


def prepare_story(store, project_id="fx", approve=True, authored=None, source=STORY):
    store.create(NewProduction(project_id=project_id, input_mode="story", content=source, formats=["short", "long"]))
    prepare_story_intake(store, project_id)
    build_fiction_package(store, project_id, authored or draft())
    for tid, target in targets(_context(store, project_id)).items():
        record_decision(store, project_id, {"target_id": tid,
                        "decision": "preserve_ambiguity" if target["kind"] == "question" else "accept"})
    view = materialize_reviewed_story(store, project_id)
    assert not view["package"]["blockers"], view["package"]["blockers"]
    return (approve_reviewed_story(store, project_id, view["version"], view["package_sha256"], view["manifest_sha256"])
            if approve else view)


def bound_choices(view):
    choices = copy.deepcopy(view["manifest"]["choices"])
    for row in choices["characters"].values():
        row["reviewed"] = True
    for cid, env, lighting in [("LOC_ROOM", "old_apartment_room", "cold_moonlight"),
                               ("LOC_HALL", "dark_apartment_corridor", "dim_corridor")]:
        choices["locations"][cid].update(environment={"id": env, "revision": 1}, lighting={"id": lighting, "revision": 1}, reviewed=True)
    choices["props"]["OBJ_DOOR"].update(asset={"id": "interior_door", "revision": 1}, anchor="doors.room_door.handle", reviewed=True)
    choices["props"]["OBJ_LAMP"].update(asset={"id": "ceiling_lamp", "revision": 1}, anchor="lamps.lamp_mid.bulb", reviewed=True)
    choices["continuity_reviewed"] = True
    return choices
