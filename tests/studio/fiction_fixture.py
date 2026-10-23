"""Fictional fixture story and Story Bible draft for P2.2 tests; not a real production."""

import copy

STORY = ("# Đèn báo trong xưởng\r\n\r\n"
         "Tôi trực tại xưởng sửa đồng hồ trên đồi.\r\n\r\n"
         "Đúng 1 giờ 13 phút, bảng điều khiển phát ra tiếng tách.\r\n\r\n"
         "Tách.\r\n\r\nTách.\r\n\r\n"
         "Kỹ thuật viên nói: “Kho dụng cụ đã khóa từ chiều.”\r\n\r\n"
         "Theo lời Minh, người giữ kho đã tắt đèn lúc 1:13.\r\n\r\n"
         "Nhãn kho A. \\\r\n\r\n\r\n"
         "Sáng hôm sau tôi kiểm tra kho dụng cụ.\r\n\r\n"
         "**1:13 đèn vẫn sáng.**\r\n\r\n\r\n\r\n"
         "đây là câu chuyện tôi muốn kể")

STAGING = {"action": "Narrator pauses at a workbench and watches the panel.", "environment": "Unlit workshop.",
           "camera": "Slow push-in on the control panel.", "uncertainty": "Nobody is visible.", "reveal": False}

DRAFT = {
    "package_id": "FIC_TEST_FIXTURE",
    "title": "[TEST FIXTURE] Đèn báo trong xưởng",
    "authored_by": "test fixture",
    "basis": "Hand-written test data for automated checks.",
    "semantic_basis": "Fixture draft; every assignment cites the fixture story.",
    "coverage_missing": ["Fixture: the clicks' origin is intentionally unexplained."],
    "characters": [
        {"id": "CHR_NARRATOR", "name": "Narrator (workshop attendant)", "aliases": ["tôi"],
         "description": "First-person narrator.", "identity_status": "narrated", "on_screen_policy": "shown",
         "evidence": ["Tôi trực tại xưởng sửa đồng hồ trên đồi."]},
        {"id": "CHR_TECHNICIAN", "name": "Technician", "aliases": ["kỹ thuật viên"], "description": "Workshop technician.",
         "identity_status": "narrated", "evidence": ["Kỹ thuật viên nói:"]},
        {"id": "CHR_MINH", "name": "Minh", "aliases": ["Minh"], "description": "Gives an account of the keeper.",
         "identity_status": "narrated", "evidence": ["Theo lời Minh"]},
        {"id": "CHR_KEEPER", "name": "The keeper", "aliases": ["người giữ kho"], "description": "Known only by account.",
         "identity_status": "reported", "on_screen_policy": "not_shown_pending_review",
         "evidence": ["người giữ kho đã tắt đèn"]},
    ],
    "locations": [
        {"id": "LOC_HALL", "name": "Workshop hall", "description": "The narrator's workplace.",
         "environment": {"source_details": ["hilltop"], "proposed_staging": "Narrow workbench, one control panel."},
         "evidence": ["xưởng sửa đồng hồ trên đồi"]},
        {"id": "LOC_STORE", "name": "Tool store", "description": "Reportedly locked store.",
         "environment": {"source_details": [], "proposed_staging": "Dusty, dark."},
         "evidence": [{"segment_id": "SEG_0006", "quote": "Kho dụng cụ"}, {"segment_id": "SEG_0009", "quote": "kho dụng cụ"}]},
    ],
    "objects": [
        {"id": "OBJ_PANEL", "name": "Control panel", "description": "Where the clicks are heard.", "persistent": True,
         "location_id": "LOC_HALL", "evidence": ["tiếng tách"]},
    ],
    "facts": [
        {"id": "FACT_KNOCK", "statement": "Clicks are heard at 1:13.", "kind": "narrated_event", "reported_by": None,
         "revealed_at": "SEG_0003", "conflicts_with": [], "evidence": ["SEG_0003..SEG_0005"]},
        {"id": "FACT_MINH_ACCOUNT", "statement": "Minh says the keeper switched the lamp off at 1:13.", "kind": "character_claim",
         "reported_by": "CHR_MINH", "revealed_at": "SEG_0007", "conflicts_with": ["FACT_WRITING"],
         "evidence": ["SEG_0007"]},
        {"id": "FACT_WRITING", "statement": "Writing says the lamp was still lit at 1:13.",
         "kind": "later_revelation", "reported_by": "CHR_NARRATOR", "revealed_at": "SEG_0010",
         "conflicts_with": ["FACT_MINH_ACCOUNT"], "evidence": ["SEG_0010"]},
    ],
    "events": [
        {"id": "EVT_KNOCK", "label": "Clicks at 1:13", "story_phase": "present", "certainty": "depicted",
         "participant_ids": ["CHR_NARRATOR"], "location_id": "LOC_HALL", "object_ids": ["OBJ_PANEL"],
         "fact_ids": ["FACT_KNOCK"], "time_markers": ["1 giờ 13 phút"], "segments": ["SEG_0002..SEG_0005"]},
        {"id": "EVT_TECHNICIAN", "label": "Technician says the store is locked", "story_phase": "present",
         "certainty": "depicted", "participant_ids": ["CHR_TECHNICIAN", "CHR_NARRATOR"], "location_id": "LOC_HALL",
         "object_ids": [], "fact_ids": [], "time_markers": [], "segments": ["SEG_0006"]},
        {"id": "EVT_ACCOUNT", "label": "Minh's account", "story_phase": "backstory", "certainty": "reported",
         "participant_ids": ["CHR_MINH", "CHR_KEEPER"], "location_id": "LOC_STORE", "object_ids": [],
         "fact_ids": ["FACT_MINH_ACCOUNT"], "time_markers": ["1:13"], "segments": ["SEG_0007"]},
        {"id": "EVT_CHECK", "label": "Narrator checks tool store and finds the writing", "story_phase": "present",
         "certainty": "depicted", "participant_ids": ["CHR_NARRATOR"], "location_id": "LOC_STORE",
         "object_ids": [], "fact_ids": ["FACT_WRITING"], "time_markers": ["Sáng hôm sau"],
         "segments": ["SEG_0008..SEG_0010"]},
    ],
    "dialogue": [
        {"id": "DLG_TECHNICIAN", "channel": "speech", "text": "“Kho dụng cụ đã khóa từ chiều.”",
         "speaker_id": "CHR_TECHNICIAN", "speaker_label": "Technician", "attribution_status": "proposed",
         "attribution_basis": "Preceded by 'Kỹ thuật viên nói:'.", "evidence": ["“Kho dụng cụ đã khóa từ chiều.”"]},
        {"id": "DLG_WRITING", "channel": "writing", "text": "**1:13 đèn vẫn sáng.**", "speaker_id": None,
         "speaker_label": "Unknown writer", "attribution_status": "unresolved", "evidence": ["SEG_0010"]},
    ],
    "sound_cues": [
        {"id": "SND_KNOCK", "label": "Two clicks", "kind": "diegetic", "event_ids": ["EVT_KNOCK"],
         "proposed_treatment": "Metallic clicks, then silence.", "evidence": ["SEG_0004", "SEG_0005"]},
    ],
    "motifs": [
        {"id": "MOT_113", "label": "1:13", "kind": "time", "related_ids": ["EVT_KNOCK", "FACT_WRITING"],
         "evidence": ["1 giờ 13 phút", {"segment_id": "SEG_0007", "quote": "1:13"},
                      {"segment_id": "SEG_0010", "quote": "1:13"}]},
    ],
    "ambiguities": [
        {"id": "AMB_WRITER", "question": "Who wrote '1:13 đèn vẫn sáng.'?", "status": "unresolved",
         "related_ids": ["DLG_WRITING", "FACT_WRITING"], "production_guidance": "Do not show the writer.",
         "evidence": ["SEG_0010"]},
    ],
    "continuity_rules": [
        {"id": "CONT_WORKSHOP", "rule": "Tool store is next to the narrator's workshop hall.",
         "related_ids": ["LOC_HALL", "LOC_STORE"], "evidence": ["xưởng sửa đồng hồ", "Nhãn kho A."]},
    ],
    "stickman_production": {
        "style": "stickman_horror_2d", "primary_output": "character_animation_in_horror_environments",
        "forbidden_primary_treatments": ["documentary_motion_graphics", "text_slideshow", "stock_footage_montage",
                                         "static_image_zoom", "infographic_replacement"],
        "characters": [{"character_id": "CHR_NARRATOR", "silhouette": "Plain adult stickman.",
                        "persistent_props": [], "consistency_rules": ["Same proportions in every shot."],
                        "basis": "production_proposal"}],
        "uncertainty_policy": "Never show what the story leaves unseen.", "status": "preliminary_not_rendered",
    },
    "formats": {
        "short": {
            "intent": "Fixture short.", "depends_on_changes": [], "excluded_segments": [],
            "chapters": [{"id": "CH_S1", "title": "Đèn báo", "beats": [
                {"id": "BEAT_S1", "narration": {"mode": "verbatim", "spans": ["SEG_0002..SEG_0006"]},
                 "event_ids": ["EVT_KNOCK", "EVT_TECHNICIAN"], "character_ids": ["CHR_NARRATOR", "CHR_TECHNICIAN"],
                 "location_id": "LOC_HALL", "object_ids": ["OBJ_PANEL"], "sound_cue_ids": ["SND_KNOCK"],
                 "silence_after_seconds": 2, "staging": STAGING},
                {"id": "BEAT_S2", "narration": {"mode": "authored_proposal", "text": "Và ai đó viết rằng đèn vẫn sáng lúc một giờ mười ba.",
                                                "sources": ["SEG_0010"], "note": "Bridging line for the fixture."},
                 "event_ids": ["EVT_CHECK"], "character_ids": ["CHR_NARRATOR"], "location_id": "LOC_STORE",
                 "object_ids": [], "sound_cue_ids": [], "silence_after_seconds": 1, "staging": STAGING},
            ]}],
        },
        "long": {
            "intent": "Fixture long.", "depends_on_changes": ["CHG_0001", "CHG_0002"],
            "excluded_segments": [{"segment_id": "SEG_0011", "reason": "Proposed removal of the author's note.",
                                   "change_id": "CHG_0002"}],
            "chapters": [{"id": "CH_L1", "title": "Đêm", "beats": [
                {"id": "BEAT_L1", "narration": {"mode": "verbatim", "spans": ["SEG_0002..SEG_0007"]},
                 "event_ids": ["EVT_KNOCK", "EVT_TECHNICIAN", "EVT_ACCOUNT"],
                 "character_ids": ["CHR_NARRATOR", "CHR_TECHNICIAN", "CHR_MINH"], "location_id": "LOC_HALL",
                 "object_ids": ["OBJ_PANEL"], "sound_cue_ids": ["SND_KNOCK"], "silence_after_seconds": 2,
                 "staging": STAGING},
                {"id": "BEAT_L2", "narration": {"mode": "verbatim", "spans": [
                    {"segment_id": "SEG_0008", "quote": "Nhãn kho A."}, "SEG_0009..SEG_0010"]},
                 "event_ids": ["EVT_CHECK"], "character_ids": ["CHR_NARRATOR"], "location_id": "LOC_STORE",
                 "object_ids": [], "sound_cue_ids": [], "silence_after_seconds": 0, "staging": STAGING},
            ]}],
        },
    },
}


def draft(**overrides):
    data = copy.deepcopy(DRAFT)
    data.update(overrides)
    return data
