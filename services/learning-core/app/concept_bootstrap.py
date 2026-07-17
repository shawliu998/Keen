"""Create the smallest honest concept state from an indexed course document.

This module intentionally does not infer mastery from document ingestion.  It
only creates a BKT prior with zero attempts; learner evidence and mastery
events remain the responsibility of assessment/review flows.
"""

from __future__ import annotations

import json
import sqlite3
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from .mastery import BktParameters

INITIAL_MASTERY_PROBABILITY = 0.2
INITIAL_MASTERY_ALGORITHM = "bkt"
INITIAL_MASTERY_ALGORITHM_VERSION = "keen-bkt-prior-v1"
_CONCEPT_ID_NAMESPACE = uuid.UUID("541d4f38-920d-467b-b9b3-8dbb5af943a1")
_MAX_CONCEPT_NAME_LENGTH = 160


class ConceptBootstrapError(RuntimeError):
    """A recoverable prerequisite for bootstrap is not satisfied."""


class CourseNotFoundError(ConceptBootstrapError):
    def __init__(self) -> None:
        super().__init__("course was not found")


class IndexedDocumentRequiredError(ConceptBootstrapError):
    def __init__(self) -> None:
        super().__init__(
            "an indexed document linked to this course is required; finish indexing and retry"
        )


class CourseDocumentUnavailableError(ConceptBootstrapError):
    def __init__(self) -> None:
        super().__init__("document is not available in this course")


class IncompleteConceptMasteryStateError(ConceptBootstrapError):
    def __init__(self) -> None:
        super().__init__(
            "concept mastery state is incomplete and has learning history; repair the local data before retrying"
        )


@dataclass(frozen=True, slots=True)
class ConceptBootstrapResult:
    """The persisted concept and mastery state after a bootstrap attempt."""

    course_id: str
    document_id: str
    concept_id: str
    concept_name: str
    mastery_probability: float
    mastery_attempts: int
    concept_created: bool
    mastery_initialized: bool
    mastery_initialization_algorithm: str | None
    mastery_initialization_algorithm_version: str | None


@dataclass(frozen=True, slots=True)
class _BootstrapSource:
    document_id: str
    display_name: str
    extension: str
    first_section_path: str | None


class ConceptBootstrapRepository:
    """Transactional persistence for deterministic indexed-document bootstrap."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def bootstrap(self, *, course_id: str, document_id: str) -> ConceptBootstrapResult:
        """Create or return the one deterministic concept for this source title.

        A write lock makes the unique ``(course_id, name)`` constraint a safe
        idempotency boundary across multiple sidecar requests.  It is also
        intentionally narrow: bootstrap neither creates evidence nor alters an
        existing mastery row.  A missing, history-free mastery row is repaired
        as a zero-evidence prior; a missing row with history is rejected.
        """

        try:
            self.connection.execute("BEGIN IMMEDIATE")
            if not self._course_exists(course_id):
                raise CourseNotFoundError
            source = self._indexed_course_document(course_id, document_id)
            if source is None:
                if self._document_is_linked_to_course(course_id, document_id):
                    raise IndexedDocumentRequiredError
                raise CourseDocumentUnavailableError

            concept_name = _concept_name(source)
            concept = self._concept(course_id, concept_name)
            concept_created = False
            if concept is None:
                concept_id = _concept_id(course_id, concept_name)
                parameters = BktParameters()
                concept_created = (
                    self.connection.execute(
                        """
                INSERT OR IGNORE INTO concepts
                    (id, course_id, name, bkt_slip, bkt_guess, bkt_transit)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                        (
                            concept_id,
                            course_id,
                            concept_name,
                            parameters.slip,
                            parameters.guess,
                            parameters.transit,
                        ),
                    ).rowcount
                    == 1
                )
                concept = self._concept(course_id, concept_name)
                if concept is None:  # pragma: no cover - guarded by the insert above
                    raise RuntimeError("concept bootstrap did not persist")

            concept_id = str(concept["id"])
            mastery = self._mastery(concept_id)
            mastery_initialized = False
            if mastery is None:
                if self._has_mastery_history(concept_id):
                    raise IncompleteConceptMasteryStateError
                now = datetime.now(UTC).isoformat()
                self.connection.execute(
                    """
                    INSERT INTO mastery (concept_id, probability, attempts, updated_at)
                    VALUES (?, ?, 0, ?)
                    """,
                    (concept_id, INITIAL_MASTERY_PROBABILITY, now),
                )
                mastery_initialized = True
                mastery = self._mastery(concept_id)
                if mastery is None:  # pragma: no cover - guarded by the insert above
                    raise RuntimeError("initial mastery did not persist")
            self.connection.commit()
            return _result(
                course_id=course_id,
                document_id=document_id,
                concept=concept,
                mastery=mastery,
                concept_created=concept_created,
                mastery_initialized=mastery_initialized,
            )
        except Exception:
            if self.connection.in_transaction:
                self.connection.rollback()
            raise

    def _course_exists(self, course_id: str) -> bool:
        return (
            self.connection.execute(
                "SELECT 1 FROM courses WHERE id = ?", (course_id,)
            ).fetchone()
            is not None
        )

    def _indexed_course_document(
        self, course_id: str, document_id: str
    ) -> _BootstrapSource | None:
        row = self.connection.execute(
            """
            SELECT d.id, d.name, d.extension,
                   (
                       SELECT dc.section_path
                       FROM document_chunks dc
                       WHERE dc.document_id = d.id
                       ORDER BY dc.ordinal, dc.id
                       LIMIT 1
                   ) AS first_section_path
            FROM documents d
            JOIN course_documents cd ON cd.document_id = d.id
            WHERE cd.course_id = ? AND d.id = ? AND d.status = 'indexed'
            """,
            (course_id, document_id),
        ).fetchone()
        if row is None:
            return None
        return _BootstrapSource(
            document_id=str(row["id"]),
            display_name=str(row["name"]),
            extension=str(row["extension"]),
            first_section_path=(
                str(row["first_section_path"])
                if row["first_section_path"] is not None
                else None
            ),
        )

    def _document_is_linked_to_course(self, course_id: str, document_id: str) -> bool:
        return (
            self.connection.execute(
                """
                SELECT 1 FROM course_documents
                WHERE course_id = ? AND document_id = ?
                """,
                (course_id, document_id),
            ).fetchone()
            is not None
        )

    def _concept(self, course_id: str, name: str) -> sqlite3.Row | None:
        return self.connection.execute(
            """
            SELECT id, name FROM concepts
            WHERE course_id = ? AND name = ?
            """,
            (course_id, name),
        ).fetchone()

    def _mastery(self, concept_id: str) -> sqlite3.Row | None:
        return self.connection.execute(
            """
            SELECT probability, attempts FROM mastery
            WHERE concept_id = ?
            """,
            (concept_id,),
        ).fetchone()

    def _has_mastery_history(self, concept_id: str) -> bool:
        return (
            self.connection.execute(
                """
                SELECT 1
                WHERE EXISTS (
                    SELECT 1 FROM mastery_events WHERE concept_id = ?
                ) OR EXISTS (
                    SELECT 1 FROM mastery_evidence WHERE concept_id = ?
                )
                """,
                (concept_id, concept_id),
            ).fetchone()
            is not None
        )


def _concept_id(course_id: str, concept_name: str) -> str:
    return "concept-bootstrap-" + str(
        uuid.uuid5(
            _CONCEPT_ID_NAMESPACE, f"{course_id}\N{UNIT SEPARATOR}{concept_name}"
        )
    )


def _concept_name(source: _BootstrapSource) -> str:
    section = _first_safe_section(source.first_section_path)
    if section is not None:
        return section
    display_name = _safe_display_name(source.display_name, source.extension)
    if display_name is not None:
        return display_name
    return "Indexed document " + _short_document_suffix(source.document_id)


def _first_safe_section(raw_section_path: str | None) -> str | None:
    if raw_section_path is None:
        return None
    try:
        decoded = json.loads(raw_section_path)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(decoded, list):
        return None
    for entry in decoded:
        if isinstance(entry, str):
            safe = _safe_label(entry)
            if safe is not None:
                return safe
    return None


def _safe_display_name(name: str, extension: str) -> str | None:
    if "/" in name or "\\" in name:
        return None
    candidate = name
    if extension and candidate.casefold().endswith(extension.casefold()):
        candidate = candidate[: -len(extension)]
    return _safe_label(candidate)


def _safe_label(value: str) -> str | None:
    normalized = unicodedata.normalize("NFKC", value)
    compact = " ".join(normalized.split())
    if not compact or len(compact) > _MAX_CONCEPT_NAME_LENGTH:
        return None
    if "/" in compact or "\\" in compact:
        return None
    if any(unicodedata.category(character).startswith("C") for character in compact):
        return None
    return compact


def _short_document_suffix(document_id: str) -> str:
    normalized = "".join(
        character for character in document_id if character.isalnum()
    ).lower()
    return (normalized or "source")[:12]


def _result(
    *,
    course_id: str,
    document_id: str,
    concept: sqlite3.Row,
    mastery: sqlite3.Row,
    concept_created: bool,
    mastery_initialized: bool,
) -> ConceptBootstrapResult:
    return ConceptBootstrapResult(
        course_id=course_id,
        document_id=document_id,
        concept_id=str(concept["id"]),
        concept_name=str(concept["name"]),
        mastery_probability=float(mastery["probability"]),
        mastery_attempts=int(mastery["attempts"]),
        concept_created=concept_created,
        mastery_initialized=mastery_initialized,
        mastery_initialization_algorithm=(
            INITIAL_MASTERY_ALGORITHM if mastery_initialized else None
        ),
        mastery_initialization_algorithm_version=(
            INITIAL_MASTERY_ALGORITHM_VERSION if mastery_initialized else None
        ),
    )
