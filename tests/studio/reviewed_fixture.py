"""Synthetic review helpers; never load a private project or story."""

from studio.fiction import build_fiction_package
from studio.intake import prepare_story_intake
from studio.models import NewProduction
from studio.review import _context, record_decision, targets
from tests.studio.fiction_fixture import STORY, draft


def prepare(store, project_id="fx", override=None):
    store.create(NewProduction(project_id=project_id, input_mode="story", content=STORY, formats=["short", "long"]))
    prepare_story_intake(store, project_id)
    build_fiction_package(store, project_id, override or draft())


def complete(store, project_id="fx", skip=()):
    for target_id, target in targets(_context(store, project_id)).items():
        if target_id not in skip:
            record_decision(store, project_id, {"target_id": target_id,
                "decision": "preserve_ambiguity" if target["kind"] == "question" else "accept"})
