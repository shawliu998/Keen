"""Trusted Agent profile for a source-linked, unapplied Plan Proposal."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from ..agent.profile import AgentExecutionLimits, ConnectionFactory
from ..agent.registry import ToolRegistry
from ..agent.tools.learning import FrozenSearchCourseKnowledgeTool
from ..database import Database
from .plan_proposal import (
    PlanProposalContext,
    revalidate_plan_proposal_context,
)
from .plan_proposal_types import StudyPlanProposalProviderArtifact

PLAN_PROPOSAL_PROFILE_ID = "learning.plan-proposal.source-grounded.v1"
_PROFILE_DEFINITION = {
    "id": PLAN_PROPOSAL_PROFILE_ID,
    "allowedTools": ["search_course_knowledge"],
    "permissionCeiling": 1,
    "maximumProviderActions": 4,
    "maximumToolCalls": 2,
    "maximumContentBytes": 20_000,
    "outputFormat": "json_object",
    "outputArtifactKind": "study_plan_proposal",
    "appliesPlan": False,
}
PLAN_PROPOSAL_PROFILE_HASH = hashlib.sha256(
    json.dumps(
        _PROFILE_DEFINITION,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()


@dataclass(frozen=True, slots=True)
class StudyPlanProposalRunProfile:
    database: Database
    context: PlanProposalContext
    id: str = PLAN_PROPOSAL_PROFILE_ID
    definition_hash: str = PLAN_PROPOSAL_PROFILE_HASH
    limits: AgentExecutionLimits = field(
        default_factory=lambda: AgentExecutionLimits(
            maximum_provider_actions=4,
            maximum_tool_calls=2,
            maximum_content_bytes=20_000,
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
            raise ValueError("plan proposal profile course scope changed")
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
        proposal = _provider_artifact(content)
        if proposal.operation.before_unit_id != self.context.target_unit.id:
            raise ValueError("proposal changed the trusted target unit")
        sources_by_handle = {
            source.source_handle: source for source in self.context.sources
        }
        try:
            selected = tuple(
                sources_by_handle[handle]
                for handle in proposal.operation.selected_source_handles
            )
        except KeyError as error:
            raise ValueError("proposal selected an unissued source handle") from error
        with self.database.connection() as connection:
            revalidate_plan_proposal_context(connection, self.context)

        canonical = proposal.model_dump(mode="json", by_alias=True)
        artifact_id = (
            "plan-proposal-artifact-"
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
        return {
            "kind": "study_plan_proposal_artifact",
            "schemaVersion": 1,
            "artifactId": artifact_id,
            "profileId": self.id,
            "profileDefinitionHash": self.definition_hash,
            "baseSessionRevision": self.context.session_revision,
            "basePlanId": self.context.plan_id,
            "basePlanVersion": self.context.plan_version,
            "summary": proposal.summary,
            "reason": proposal.reason,
            "currentPlan": {
                "units": [
                    {
                        "id": unit.id,
                        "ordinal": unit.ordinal,
                        "title": unit.title,
                        "objective": unit.objective,
                        "estimatedMinutes": unit.estimated_minutes,
                        "status": unit.status,
                    }
                    for unit in self.context.units
                ]
            },
            "operation": proposal.operation.model_dump(mode="json", by_alias=True),
            "sources": [
                source.model_dump(mode="json", by_alias=True) for source in selected
            ],
            "decision": {
                "status": "unapplied",
                "applyAvailable": False,
            },
        }


def _provider_artifact(content: str) -> StudyPlanProposalProviderArtifact:
    if not content or len(content.encode("utf-8")) > 20_000:
        raise ValueError("plan proposal provider output is empty or too large")
    try:
        value = json.loads(content)
    except json.JSONDecodeError as error:
        raise ValueError("plan proposal provider output is not strict JSON") from error
    return StudyPlanProposalProviderArtifact.model_validate(value)


__all__ = [
    "PLAN_PROPOSAL_PROFILE_HASH",
    "PLAN_PROPOSAL_PROFILE_ID",
    "StudyPlanProposalRunProfile",
]
