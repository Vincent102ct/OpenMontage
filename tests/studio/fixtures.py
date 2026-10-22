"""Fictional packages for input tests only; never copy STORY 053 claims."""

import hashlib
import json
from pathlib import Path


def fixture_catalog(repo: Path) -> Path:
    package_id = "STORY_999"
    package = {
        "schema_version": "1.0", "package_id": package_id, "package_version": "v1",
        "title": "[TEST FIXTURE] Cánh cửa trong mưa", "language": "vi",
        "case": {"name": "Fictional input fixture", "place": "Test workspace", "year": 2026},
        "sources": [{"id": "SRC_TEST", "title": "Fictional test fixture", "reference": "Test data only",
                     "source_type": "test_fixture", "reliability": "anecdotal",
                     "verification": {"status": "not_checked", "checked_on": "2026-01-01", "method": "fixture"}}],
        "claims": [{"id": "CLM_TEST", "text": "Fictional fixture, not a historical claim.",
                    "status": "UNKNOWN", "supporting_source_ids": []}],
        "timeline": [], "entities": {"characters": [], "locations": [], "objects": []},
        "continuity_rules": [],
        "master_narrative": {"segments": [{"id": "SEG_TEST", "role": "fixture",
                              "text": "Đây là dữ liệu thử nghiệm, không phải câu chuyện có thật.",
                              "claim_ids": ["CLM_TEST"], "estimated_seconds": 50}]},
        "formats": {name: {"format": name, "package_id": package_id, "package_version": "v1",
                           "aspect_ratio": shape, "target_seconds": {"min": 45, "max": 60},
                           "segment_ids": ["SEG_TEST"]} for name, shape in [("short", "9:16"), ("long", "16:9")]},
    }
    path = repo / "examples/master-story/test-fixture/master_story.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
    catalog = repo / "studio/approved_packages.json"
    catalog.parent.mkdir(parents=True)
    catalog.write_text(json.dumps({"schema_version": "1.0", "packages": [{
        "id": "test-canonical", "title": package["title"],
        "path": "examples/master-story/test-fixture/master_story.json",
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "approved_by": "Test fixture reviewer (not production approval)",
        "approved_at": "2026-01-01T00:00:00Z",
    }]}, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
