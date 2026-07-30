"""Immutable built-in procedures for the closed intervention action set."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum


class LearningInterventionIntent(StrEnum):
    EXPLAIN_DIFFERENTLY = "explain_differently"
    SHOW_SOURCE_EXAMPLE = "show_source_example"
    TEST_ME_INSTEAD = "test_me_instead"


@dataclass(frozen=True, slots=True)
class LearningInterventionPlaybook:
    slug: str
    version: int
    instruction: str
    definition_hash: str


def _playbook(slug: str, instruction: str) -> LearningInterventionPlaybook:
    definition = {
        "slug": slug,
        "version": 1,
        "instruction": instruction,
        "allowedTool": "search_course_knowledge",
        "artifactKind": "source_grounded_misconception_repair",
        "fallback": "source_review",
    }
    encoded = json.dumps(
        definition, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return LearningInterventionPlaybook(
        slug=slug,
        version=1,
        instruction=instruction,
        definition_hash=hashlib.sha256(encoded).hexdigest(),
    )


_PLAYBOOKS = {
    LearningInterventionIntent.EXPLAIN_DIFFERENTLY: _playbook(
        "source-grounded-rephrase",
        (
            "Explain the current idea using a meaningfully different formulation. "
            "Use only the frozen source excerpts, do not score the learner, do not "
            "claim mastery, and return the strict intervention artifact JSON."
        ),
    ),
    LearningInterventionIntent.SHOW_SOURCE_EXAMPLE: _playbook(
        "source-grounded-example",
        (
            "Use one concrete example supported by the frozen source excerpts. "
            "Use only issued source handles, do not score the learner, do not claim "
            "mastery, and return the strict intervention artifact JSON."
        ),
    ),
}
_PROGRESSIVE_HINT = _playbook(
    "progressive-hint",
    (
        "Give one source-grounded scaffold that helps the learner make the next "
        "step without scoring the learner or claiming mastery. Use only the "
        "frozen source excerpts and return the strict intervention artifact JSON."
    ),
)


def playbook_for_intent(
    intent: LearningInterventionIntent,
) -> LearningInterventionPlaybook:
    if intent is LearningInterventionIntent.TEST_ME_INSTEAD:
        raise ValueError("test me instead uses deterministic Practice, not a Playbook")
    return _PLAYBOOKS[intent]


def select_playbook(
    intent: LearningInterventionIntent,
    *,
    diagnostic_self_report_score: float | None,
    has_predecessor: bool,
) -> LearningInterventionPlaybook:
    """Select one fixed procedure from authoritative, frozen host signals."""

    if intent is LearningInterventionIntent.TEST_ME_INSTEAD:
        raise ValueError("test me instead uses deterministic Practice, not a Playbook")
    if (
        intent is LearningInterventionIntent.EXPLAIN_DIFFERENTLY
        and not has_predecessor
        and diagnostic_self_report_score == 0.0
    ):
        return _PROGRESSIVE_HINT
    return _PLAYBOOKS[intent]


__all__ = [
    "LearningInterventionIntent",
    "LearningInterventionPlaybook",
    "playbook_for_intent",
    "select_playbook",
]
