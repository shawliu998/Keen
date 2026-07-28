"""Trusted purpose profile and completion publisher for interventions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from ..agent.profile import AgentExecutionLimits, ConnectionFactory
from ..agent.registry import ToolRegistry
from ..agent.tools.learning import FrozenSearchCourseKnowledgeTool
from ..database import Database
from ..repositories.intervention_outcome_repository import (
    InterventionOutcomeRepository,
)
from .context import (
    WHAT_NEXT,
    WHY_NOW,
    InterventionContext,
)
from .playbooks import LearningInterventionPlaybook
from .practice_handoff import ensure_intervention_practice
from .types import LearningInterventionProviderArtifact

PROFILE_ID = "learning.intervention.source-grounded.v1"
_PROFILE_DEFINITION = {
    "id": PROFILE_ID,
    "allowedTools": ["search_course_knowledge"],
    "permissionCeiling": 1,
    "maximumProviderActions": 4,
    "maximumToolCalls": 2,
    "maximumContentBytes": 24_000,
    "outputFormat": "json_object",
    "outputArtifactKind": "source_grounded_misconception_repair",
    "fallback": "source_review",
}
PROFILE_DEFINITION_HASH = hashlib.sha256(
    json.dumps(
        _PROFILE_DEFINITION,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()


@dataclass(frozen=True, slots=True)
class LearningInterventionRunProfile:
    """One host-created profile instance bound to a frozen learning context."""

    database: Database
    context: InterventionContext
    playbook: LearningInterventionPlaybook
    predecessor_run_id: str | None = None
    predecessor_artifact_id: str | None = None
    id: str = PROFILE_ID
    definition_hash: str = PROFILE_DEFINITION_HASH
    limits: AgentExecutionLimits = field(
        default_factory=lambda: AgentExecutionLimits(
            maximum_provider_actions=4,
            maximum_tool_calls=2,
            maximum_content_bytes=24_000,
        )
    )
    output_format: Literal["json_object"] = "json_object"

    def register_tools(
        self,
        registry: ToolRegistry,
        *,
        connection_factory: ConnectionFactory,
        course_id: str,
        as_of: datetime,
    ) -> None:
        del as_of
        if course_id != self.context.course_id:
            raise ValueError("intervention profile course scope changed")
        registry.register(
            FrozenSearchCourseKnowledgeTool(
                connection_factory,
                course_id=course_id,
                sources=self.context.sources,
            )
        )

    async def publish_completion(
        self,
        *,
        run_id: str,
        content: str,
    ) -> dict[str, object]:
        """Validate provider JSON, create existing Practice, then publish."""

        artifact = _provider_artifact(content)
        sources_by_handle = {
            source.source_handle: source for source in self.context.sources
        }
        try:
            selected = tuple(
                sources_by_handle[handle] for handle in artifact.selected_source_handles
            )
        except KeyError as error:
            raise ValueError(
                "intervention artifact selected an unissued source handle"
            ) from error

        canonical = artifact.model_dump(mode="json", by_alias=True)
        artifact_id = (
            "artifact-"
            + hashlib.sha256(
                (
                    run_id
                    + "\0"
                    + json.dumps(
                        canonical,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                ).encode("utf-8")
            ).hexdigest()[:32]
        )
        linked_at = datetime.now(UTC)
        with self.database.connection() as connection:
            practice = ensure_intervention_practice(
                connection,
                context=self.context,
                idempotency_seed=run_id,
                now=linked_at,
            )
            InterventionOutcomeRepository(connection).record_exposure(
                course_id=self.context.course_id,
                session_id=self.context.session_id,
                unit_id=self.context.unit_id,
                trigger_active_recall_run_id=self.context.recall_run_id,
                intervention_run_id=run_id,
                intervention_artifact_id=artifact_id,
                practice_run_id=practice.run_id,
                playbook_slug=self.playbook.slug,
                playbook_version=self.playbook.version,
                playbook_definition_hash=self.playbook.definition_hash,
                linked_at=linked_at.isoformat(),
            )
        return {
            "kind": "learning_intervention_artifact",
            "schemaVersion": 1,
            "artifactId": artifact_id,
            "predecessor": (
                {
                    "runId": self.predecessor_run_id,
                    "artifactId": self.predecessor_artifact_id,
                }
                if self.predecessor_run_id is not None
                and self.predecessor_artifact_id is not None
                else None
            ),
            "profileId": self.id,
            "profileDefinitionHash": self.definition_hash,
            "playbookSlug": self.playbook.slug,
            "playbookVersion": self.playbook.version,
            "playbookDefinitionHash": self.playbook.definition_hash,
            "whyNow": WHY_NOW,
            "summary": artifact.summary,
            "explanationMarkdown": artifact.explanation_markdown,
            "sources": [
                source.model_dump(mode="json", by_alias=True) for source in selected
            ],
            "whatNext": {
                "label": WHAT_NEXT,
                "action": "continue_practice",
                "practiceRunId": practice.run_id,
                "practicePrompt": practice.prompt,
                "sessionRevision": practice.session_revision,
            },
        }


def _provider_artifact(content: str) -> LearningInterventionProviderArtifact:
    if not content or len(content.encode("utf-8")) > 24_000:
        raise ValueError("intervention provider output is empty or too large")
    try:
        value = json.loads(content)
    except json.JSONDecodeError as error:
        raise ValueError("intervention provider output is not strict JSON") from error
    return LearningInterventionProviderArtifact.model_validate(value)


__all__ = [
    "PROFILE_DEFINITION_HASH",
    "PROFILE_ID",
    "LearningInterventionRunProfile",
]
