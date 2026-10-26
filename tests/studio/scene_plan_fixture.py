"""Entirely synthetic complete fiction for P3.4 scene planning; never a private pilot or STORY 053."""
import copy

STORY = ("# [SYNTHETIC TEST] The Knocking on Floor Four\n\n"
         "Lena sat alone in her old room on the fourth floor. Moonlight lay across the floor, and the door to the corridor was shut.\n\n"
         "Just after midnight, three slow knocks sounded on her door.\n\n"
         "\"Who is there?\" Lena asked.\n\n"
         "Nobody answered. The silence after the knocks felt heavier than the sound itself.\n\n"
         "Lena crossed the room, held her breath and reached for the handle. She opened the door.\n\n"
         "The corridor was empty. Only the middle ceiling lamp was burning, and it buzzed and flickered over the faded carpet.\n\n"
         "Across the hall, Owen stepped out of the apartment opposite hers, his shoulders hunched.\n\n"
         "\"You heard it too?\" Owen whispered.\n\n"
         "Lena nodded. Neither of them had heard anyone on the stairs.\n\n"
         "Then Lena noticed a tall, dark shape standing in the opening at the far end of the corridor. It had no face that she could see.\n\n"
         "The shape did not move. Owen gripped the door frame. The lamp stuttered and went dark for a heartbeat.\n\n"
         "When the light came back, the end of the corridor was empty.\n\n"
         "Owen said the woman who once lived in the corner apartment used to knock like that, but he admitted he had never met her.\n\n"
         "Lena went back inside and locked her door. She sat facing it in the moonlight and did not sleep.\n\n"
         "Later that night, three soft knocks came again. Lena did not answer, and she never learned who had been standing in the corridor.")


def _staging(action, environment, camera, uncertainty="", reveal=False):
    return {"action": action, "environment": environment, "camera": camera, "uncertainty": uncertainty, "reveal": reveal}


ROOM = "Old fourth-floor room at night."
HALL = "Fourth-floor corridor; one buzzing ceiling lamp."
UNKNOWN = "Never show who or what knocks."
SHAPE = "Keep the shape faceless and unexplained; never identify it."
EVENTS = [  # id, label, location, participants, objects, segments, facts
    ("EVT_ALONE", "Lena sits alone in her room", "LOC_ROOM", ["CHR_LENA"], ["OBJ_ROOM_DOOR"], "SEG_0002", []),
    ("EVT_KNOCKS", "Three slow knocks; nobody answers", "LOC_ROOM", ["CHR_LENA"], ["OBJ_ROOM_DOOR"], "SEG_0003..SEG_0005", ["FACT_KNOCKS"]),
    ("EVT_OPEN", "Lena opens her door", "LOC_ROOM", ["CHR_LENA"], ["OBJ_ROOM_DOOR"], "SEG_0006", []),
    ("EVT_EMPTY_HALL", "The corridor is empty under a flickering lamp", "LOC_HALL", ["CHR_LENA"], ["OBJ_LAMP"], "SEG_0007", []),
    ("EVT_OWEN", "Owen steps out; he heard it too", "LOC_HALL", ["CHR_LENA", "CHR_OWEN"], [], "SEG_0008..SEG_0010", []),
    ("EVT_SHAPE", "A faceless shape stands at the far end", "LOC_HALL", ["CHR_LENA", "CHR_SHAPE"], [], "SEG_0011", []),
    ("EVT_DARK", "The lamp goes dark; the shape is gone", "LOC_HALL", ["CHR_LENA", "CHR_OWEN", "CHR_SHAPE"], ["OBJ_LAMP"], "SEG_0012..SEG_0013", []),
    ("EVT_CLAIM", "Owen repeats an unverified story about a former tenant", "LOC_HALL", ["CHR_OWEN", "CHR_LENA"], [], "SEG_0014", ["FACT_OWEN_CLAIM"]),
    ("EVT_RETURN", "Lena locks herself in and waits", "LOC_ROOM", ["CHR_LENA"], ["OBJ_ROOM_DOOR"], "SEG_0015", []),
    ("EVT_KNOCKS_AGAIN", "Soft knocks return; the knocker stays unknown", "LOC_ROOM", ["CHR_LENA"], ["OBJ_ROOM_DOOR"], "SEG_0016", []),
]
LONG = [  # chapter id/title, then beats: id, segments, events, characters, location, objects, sounds, silence, staging
    ("CH_L1", "Midnight", [
        ("BEAT_L01", "SEG_0002", ["EVT_ALONE"], ["CHR_LENA"], "LOC_ROOM", ["OBJ_ROOM_DOOR"], [], 1.5,
         _staging("Lena sits still in the dark room.", ROOM, "Slow establishing view of the room.")),
        ("BEAT_L02", "SEG_0003", ["EVT_KNOCKS"], ["CHR_LENA"], "LOC_ROOM", ["OBJ_ROOM_DOOR"], ["SND_KNOCKS"], 2,
         _staging("Lena freezes at the knocks.", ROOM, "Hold on Lena and the shut door.", UNKNOWN)),
        ("BEAT_L03", "SEG_0004", ["EVT_KNOCKS"], ["CHR_LENA"], "LOC_ROOM", ["OBJ_ROOM_DOOR"], [], 1,
         _staging("Lena calls toward the door.", ROOM, "Medium shot.", UNKNOWN)),
        ("BEAT_L04", "SEG_0005", ["EVT_KNOCKS"], ["CHR_LENA"], "LOC_ROOM", ["OBJ_ROOM_DOOR"], ["SND_SILENCE"], 2.5,
         _staging("No answer; Lena listens.", ROOM, "Hold the silence.", UNKNOWN))]),
    ("CH_L2", "The Corridor", [
        ("BEAT_L05", "SEG_0006", ["EVT_OPEN"], ["CHR_LENA"], "LOC_ROOM", ["OBJ_ROOM_DOOR"], [], 1,
         _staging("Lena crosses the room, reaches for the handle and opens the door.", ROOM, "Follow her to the door.")),
        ("BEAT_L06", "SEG_0007", ["EVT_EMPTY_HALL"], ["CHR_LENA"], "LOC_HALL", ["OBJ_LAMP"], ["SND_LAMP_BUZZ"], 2,
         _staging("Lena looks along the empty corridor.", HALL, "Wide view of the corridor.")),
        ("BEAT_L07", "SEG_0008", ["EVT_OWEN"], ["CHR_LENA", "CHR_OWEN"], "LOC_HALL", [], [], 1,
         _staging("Owen steps out of the apartment opposite.", HALL, "Two-shot.")),
        ("BEAT_L08", "SEG_0009..SEG_0010", ["EVT_OWEN"], ["CHR_LENA", "CHR_OWEN"], "LOC_HALL", [], [], 1.5,
         _staging("Owen whispers; Lena nods.", HALL, "Two-shot, tighter."))]),
    ("CH_L3", "The Shape", [
        ("BEAT_L09", "SEG_0011", ["EVT_SHAPE"], ["CHR_LENA", "CHR_SHAPE"], "LOC_HALL", [], [], 3,
         _staging("Lena notices the shape at the far end.", HALL, "Slow push toward the far opening.", SHAPE, True)),
        ("BEAT_L10", "SEG_0012", ["EVT_DARK"], ["CHR_LENA", "CHR_OWEN", "CHR_SHAPE"], "LOC_HALL", ["OBJ_LAMP"], ["SND_LAMP_BUZZ"], 1.5,
         _staging("Owen grips the door frame; the lamp stutters and goes dark.", HALL, "Hold wide.", SHAPE)),
        ("BEAT_L11", "SEG_0013", ["EVT_DARK"], ["CHR_LENA", "CHR_OWEN"], "LOC_HALL", ["OBJ_LAMP"], [], 2.5,
         _staging("The light returns; the end of the corridor is empty.", HALL, "Same framing as before the dark.", SHAPE))]),
    ("CH_L4", "Before Dawn", [
        ("BEAT_L12", "SEG_0014", ["EVT_CLAIM"], ["CHR_OWEN", "CHR_LENA"], "LOC_HALL", [], [], 1.5,
         _staging("Owen repeats what he heard about a former tenant.", HALL, "Medium on Owen.",
                  "A character claim only; do not depict the former tenant.")),
        ("BEAT_L13", "SEG_0015", ["EVT_RETURN"], ["CHR_LENA"], "LOC_ROOM", ["OBJ_ROOM_DOOR"], [], 2,
         _staging("Lena locks her door and sits facing it.", ROOM, "Static, low-key.")),
        ("BEAT_L14", "SEG_0016", ["EVT_KNOCKS_AGAIN"], ["CHR_LENA"], "LOC_ROOM", ["OBJ_ROOM_DOOR"], ["SND_SOFT_KNOCKS"], 3,
         _staging("Lena does not move or answer.", ROOM, "Hold until black.", UNKNOWN))]),
]
SHORT = [
    ("CH_S1", "The Knock", [
        ("BEAT_S01", "SEG_0003", ["EVT_KNOCKS"], ["CHR_LENA"], "LOC_ROOM", ["OBJ_ROOM_DOOR"], ["SND_KNOCKS"], 2,
         _staging("Lena freezes at the knocks.", ROOM, "Vertical medium on Lena and the door.", UNKNOWN)),
        ("BEAT_S02", "SEG_0005", ["EVT_KNOCKS"], ["CHR_LENA"], "LOC_ROOM", ["OBJ_ROOM_DOOR"], ["SND_SILENCE"], 2.5,
         _staging("Lena listens.", ROOM, "Hold the silence.", UNKNOWN)),
        ("BEAT_S03", "SEG_0006", ["EVT_OPEN"], ["CHR_LENA"], "LOC_ROOM", ["OBJ_ROOM_DOOR"], [], 1.5,
         _staging("Lena reaches for the handle and opens the door.", ROOM, "Follow her to the door."))]),
    ("CH_S2", "The Shape", [
        ("BEAT_S04", "SEG_0007", ["EVT_EMPTY_HALL"], ["CHR_LENA"], "LOC_HALL", ["OBJ_LAMP"], ["SND_LAMP_BUZZ"], 2,
         _staging("Lena looks along the empty corridor.", HALL, "Vertical corridor depth.")),
        ("BEAT_S05", "SEG_0011", ["EVT_SHAPE"], ["CHR_LENA", "CHR_SHAPE"], "LOC_HALL", [], [], 3,
         _staging("Lena notices the shape.", HALL, "Slow push toward the far opening.", SHAPE, True)),
        ("BEAT_S06", "SEG_0012..SEG_0013", ["EVT_DARK"], ["CHR_LENA", "CHR_OWEN", "CHR_SHAPE"], "LOC_HALL", ["OBJ_LAMP"],
         ["SND_LAMP_BUZZ"], 2.5, _staging("The lamp goes dark; then the end is empty.", HALL, "Hold.", SHAPE))]),
    ("CH_S3", "Again", [
        ("BEAT_S07", "SEG_0016", ["EVT_KNOCKS_AGAIN"], ["CHR_LENA"], "LOC_ROOM", ["OBJ_ROOM_DOOR"], ["SND_SOFT_KNOCKS"], 3,
         _staging("Lena does not answer.", ROOM, "Hold until black.", UNKNOWN))]),
]


def _plan(chapters, intent):
    return {"intent": intent, "depends_on_changes": [], "excluded_segments": [],
            "chapters": [{"id": cid, "title": title, "beats": [
                {"id": b, "narration": {"mode": "verbatim", "spans": [seg]}, "event_ids": ev, "character_ids": ch,
                 "location_id": loc, "object_ids": obj, "sound_cue_ids": snd, "silence_after_seconds": sil, "staging": st}
                for b, seg, ev, ch, loc, obj, snd, sil, st in beats]} for cid, title, beats in chapters]}


def draft():
    person = "Named person; appearance unspecified."
    data = {
        "package_id": "FIC_SCENE_PLAN_FIXTURE", "title": "[SYNTHETIC TEST] The Knocking on Floor Four",
        "authored_by": "test fixture", "basis": "Isolated synthetic P3.4 complete-story fixture.",
        "semantic_basis": "Exact synthetic source evidence only.", "coverage_missing": [],
        "characters": [
            {"id": "CHR_LENA", "name": "Lena", "aliases": [], "description": person, "identity_status": "narrated",
             "on_screen_policy": "shown", "evidence": ["Lena sat alone"]},
            {"id": "CHR_OWEN", "name": "Owen", "aliases": [], "description": person, "identity_status": "narrated",
             "on_screen_policy": "shown", "evidence": ["Owen stepped out"]},
            {"id": "CHR_SHAPE", "name": "The shape", "aliases": [], "description": "A tall, dark, faceless shape; identity unknown.",
             "identity_status": "ambiguous", "on_screen_policy": "partial", "evidence": ["a tall, dark shape"]},
            {"id": "CHR_TENANT", "name": "Former tenant", "aliases": [], "description": "Mentioned only in a claim; never seen.",
             "identity_status": "reported", "on_screen_policy": "not_shown_pending_review",
             "evidence": ["the woman who once lived in the corner apartment"]}],
        "locations": [{"id": i, "name": n, "description": n,
                       "environment": {"source_details": [n], "proposed_staging": "Creative proposal requires review."},
                       "evidence": [e]} for i, n, e in [("LOC_ROOM", "Lena's old room", "her old room on the fourth floor"),
                                                          ("LOC_HALL", "Fourth-floor corridor", "The corridor was empty.")]],
        "objects": [{"id": "OBJ_ROOM_DOOR", "name": "Lena's door", "description": "The door between Lena's room and the corridor.",
                     "persistent": True, "location_id": "LOC_ROOM", "evidence": ["the door to the corridor was shut"]},
                    {"id": "OBJ_LAMP", "name": "Middle ceiling lamp", "description": "The only lamp burning in the corridor.",
                     "persistent": True, "location_id": "LOC_HALL", "evidence": ["the middle ceiling lamp"]}],
        "facts": [{"id": "FACT_KNOCKS", "statement": "Three slow knocks sounded on Lena's door and nobody answered.",
                   "kind": "narrated_event", "reported_by": None, "revealed_at": "SEG_0003", "conflicts_with": [],
                   "evidence": ["three slow knocks sounded on her door", "Nobody answered."]},
                  {"id": "FACT_OWEN_CLAIM", "statement": "Owen says a former tenant used to knock like that; he never met her.",
                   "kind": "character_claim", "reported_by": "CHR_OWEN", "revealed_at": "SEG_0014", "conflicts_with": [],
                   "evidence": ["SEG_0014"]}],
        "events": [{"id": i, "label": label, "story_phase": "present", "certainty": "depicted", "participant_ids": who,
                    "location_id": loc, "object_ids": obj, "fact_ids": facts, "time_markers": [], "segments": [seg]}
                   for i, label, loc, who, obj, seg, facts in EVENTS],
        "dialogue": [{"id": "DLG_WHO", "channel": "speech", "text": "\"Who is there?\"", "speaker_id": "CHR_LENA",
                      "speaker_label": "Lena", "attribution_status": "proposed", "attribution_basis": "Lena asked",
                      "evidence": ["\"Who is there?\""]},
                     {"id": "DLG_HEARD", "channel": "speech", "text": "\"You heard it too?\"", "speaker_id": "CHR_OWEN",
                      "speaker_label": "Owen", "attribution_status": "proposed", "attribution_basis": "Owen whispered",
                      "evidence": ["\"You heard it too?\""]}],
        "sound_cues": [
            {"id": "SND_KNOCKS", "label": "Three slow knocks", "kind": "diegetic", "event_ids": ["EVT_KNOCKS"],
             "proposed_treatment": "Three slow, dry knocks on wood; no visible source.", "evidence": ["three slow knocks"]},
            {"id": "SND_SILENCE", "label": "Heavy silence", "kind": "silence", "event_ids": ["EVT_KNOCKS"],
             "proposed_treatment": "Drop room tone almost to nothing.", "evidence": ["The silence after the knocks"]},
            {"id": "SND_LAMP_BUZZ", "label": "Buzzing lamp", "kind": "electronic", "event_ids": ["EVT_EMPTY_HALL", "EVT_DARK"],
             "proposed_treatment": "Thin electrical buzz that stutters with the flicker.", "evidence": ["it buzzed and flickered"]},
            {"id": "SND_SOFT_KNOCKS", "label": "Three soft knocks", "kind": "diegetic", "event_ids": ["EVT_KNOCKS_AGAIN"],
             "proposed_treatment": "Quieter repeat of the first knocks.", "evidence": ["three soft knocks came again"]}],
        "motifs": [{"id": "MOT_THREE_KNOCKS", "label": "Three knocks", "kind": "sound",
                    "related_ids": ["SND_KNOCKS", "SND_SOFT_KNOCKS"], "evidence": ["three slow knocks", "three soft knocks"]}],
        "ambiguities": [
            {"id": "AMB_KNOCKER", "question": "Who or what knocked on Lena's door?", "status": "unresolved",
             "related_ids": ["EVT_KNOCKS", "EVT_KNOCKS_AGAIN", "SND_KNOCKS", "SND_SOFT_KNOCKS"],
             "production_guidance": "Never show or name the knocker.",
             "evidence": ["she never learned who had been standing in the corridor"]},
            {"id": "AMB_SHAPE", "question": "What was the shape at the end of the corridor?", "status": "unresolved",
             "related_ids": ["CHR_SHAPE", "EVT_SHAPE", "FACT_OWEN_CLAIM", "CHR_TENANT"],
             "production_guidance": "Faceless, partial and unexplained; never link it to the former tenant.",
             "evidence": ["It had no face that she could see."]}],
        "continuity_rules": [
            {"id": "CONT_SHAPE_FACELESS", "rule": "The shape never shows a face.", "related_ids": ["CHR_SHAPE"],
             "evidence": ["It had no face that she could see."]},
            {"id": "CONT_DOOR_LOCKED", "rule": "After Lena returns, her door stays locked.", "related_ids": ["OBJ_ROOM_DOOR"],
             "evidence": ["locked her door"]}],
        "stickman_production": {"style": "stickman_horror_2d", "primary_output": "character_animation_in_horror_environments",
            "forbidden_primary_treatments": ["documentary_motion_graphics", "text_slideshow", "stock_footage_montage",
                                             "static_image_zoom", "infographic_replacement"],
            "characters": [], "uncertainty_policy": "Never depict or explain the unknown knocker or shape.",
            "status": "preliminary_not_rendered"},
        "formats": {"short": _plan(SHORT, "Synthetic vertical Short: knocks, the shape, the unresolved return."),
                    "long": _plan(LONG, "Synthetic complete Long: every paragraph in source order.")},
    }
    return copy.deepcopy(data)


def visual_choices(view):
    """Explicit synthetic visual review; casting is a test proposal, not a story fact."""
    choices = copy.deepcopy(view["manifest"]["choices"])
    for row in choices["characters"].values():
        row["reviewed"] = True
    choices["characters"]["CHR_SHAPE"].update(representation="silhouette", asset={"id": "tall_hooded", "revision": 1})
    choices["locations"]["LOC_ROOM"].update(environment={"id": "old_apartment_room", "revision": 1},
                                            lighting={"id": "cold_moonlight", "revision": 1}, reviewed=True)
    choices["locations"]["LOC_HALL"].update(environment={"id": "dark_apartment_corridor", "revision": 1},
                                            lighting={"id": "flickering_interior", "revision": 1}, flicker_lamp="lamp_mid",
                                            presence={"character_id": "CHR_SHAPE", "anchor": "corridor_end"}, reviewed=True)
    choices["props"]["OBJ_ROOM_DOOR"].update(asset={"id": "interior_door", "revision": 1}, anchor="doors.room_door.handle",
                                             reviewed=True)
    choices["props"]["OBJ_LAMP"].update(asset={"id": "ceiling_lamp", "revision": 1}, anchor="lamps.lamp_mid.bulb", reviewed=True)
    choices["continuity_reviewed"] = True
    return choices


def shot_id(view, fmt, beat, kind="narrative"):
    return next(s["shot_id"] for s in view["package"]["formats"][fmt]["shots"]
                if s["source"]["beat_id"] == beat and s["kind"] == kind)


def requested_actions(view):
    """Synthetic reviewer maps reviewed staging to actions the canon describes; some are unsupported."""
    choices = copy.deepcopy(view["manifest"]["choices"])
    shots = {f: choices["formats"][f]["shots"] for f in ("short", "long")}
    shots["long"][shot_id(view, "long", "BEAT_L05")]["props"]["OBJ_ROOM_DOOR"] = "open_door"
    shots["short"][shot_id(view, "short", "BEAT_S03")]["props"]["OBJ_ROOM_DOOR"] = "open_door"
    shots["long"][shot_id(view, "long", "BEAT_L10")]["cast"]["CHR_OWEN"]["performance"] = "grasp_object"
    return choices


def resolved_choices(view):
    """Supported or explicitly editorial alternatives; no beat, narration or canonical fact is removed."""
    choices = copy.deepcopy(view["manifest"]["choices"])
    long, short = choices["formats"]["long"], choices["formats"]["short"]
    edits = [("long", "BEAT_L05", "OBJ_ROOM_DOOR", "reach_then_opened_across_cut"),
             ("short", "BEAT_S03", "OBJ_ROOM_DOOR", "reach_then_opened_across_cut"),
             ("long", "BEAT_L13", "OBJ_ROOM_DOOR", "door_closed_across_cut"),
             ("short", "BEAT_S07", "OBJ_ROOM_DOOR", "door_closed_across_cut")]
    for fmt, beat, obj, value in edits:
        row = choices["formats"][fmt]["shots"][shot_id(view, fmt, beat)]
        row["props"][obj], row["editorial_acknowledged"] = value, True
    long["shots"][shot_id(view, "long", "BEAT_L10")]["cast"]["CHR_OWEN"]["performance"] = "startled_reaction"
    for beat, line in (("BEAT_L03", "DLG_WHO"), ("BEAT_L08", "DLG_HEARD")):
        row = long["shots"][shot_id(view, "long", beat)]
        row["dialogue"][line], row["editorial_acknowledged"] = "voice_over_narration", True
    # Lena crosses the room into the next chapter without a cut in time or place.
    long["scenes"][next(s["scene_id"] for s in view["package"]["formats"]["long"]["scenes"]
                        if "BEAT_L05" in s["beat_ids"])]["transition"] = "continuous"
    for plan in (long, short):
        for scene in plan["scenes"].values():
            scene["reviewed"] = True
    choices["coverage_reviewed"] = choices["continuity_reviewed"] = True
    return choices


def prepare(store, project_id="fx", approve_story=True, approve_visual=True):
    """Explicit synthetic P2.3 story approval, then P3.3 visual preparation, review and approval."""
    from studio.visual_bible import approve_visual_bible, prepare_visual_bible
    from tests.studio.visual_bible_fixture import prepare_story
    story = prepare_story(store, project_id, approve=approve_story, authored=draft(), source=STORY)
    if not approve_story:
        return story
    initial = prepare_visual_bible(store, project_id, {})
    view = prepare_visual_bible(store, project_id, {
        "base_version": initial["version"], "package_sha256": initial["package_sha256"],
        "manifest_sha256": initial["manifest_sha256"], "choices": visual_choices(initial)})
    assert not view["package"]["blockers"], view["package"]["blockers"]
    if approve_visual:
        view = approve_visual_bible(store, project_id, view["version"], view["package_sha256"], view["manifest_sha256"])
    return view


def synthetic_measurements(view, fmt, seconds=2.0):
    """Contract-only values; no WAV, TTS, audio hash or real measurement is claimed."""
    from lib.story_scene_plan import measurement_contract
    from lib.story_visual_bible import fingerprint
    contract = measurement_contract(view["package"], fmt, approved=view)
    result = {"artifact": "scene_plan_measurements", "schema_version": "1.0", "plan": contract["plan"], "format": fmt,
              "units": [{**u, "duration_seconds": seconds, "audio_sha256": None, "sample_rate_hz": None}
                        for u in contract["units"]],
              "provenance": {"kind": "synthetic_test", "producer": "P3.4 isolated unit test; not audio",
                             "recorded_at": "2026-10-26T00:00:00Z"}}
    result["manifest_sha256"] = fingerprint(result)
    return result
