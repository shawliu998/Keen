"""Keen-owned review scheduler contract backed by the pinned py-fsrs package.

Review scheduling is intentionally independent of concept mastery. This module
does not read or update mastery evidence, BKT state, assessments, or tasks.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from importlib.metadata import version
from math import isfinite
from types import MappingProxyType
from typing import Mapping, Protocol

from fsrs import Card as FSRSCard
from fsrs import Rating as FSRSRating
from fsrs import Scheduler as FSRSScheduler
from fsrs import State as FSRSState

UPSTREAM_FSRS_VERSION = "6.3.1"
SCHEDULER_VERSION = f"fsrs-{UPSTREAM_FSRS_VERSION}-keen-v1"
DESIRED_RETENTION = 0.9
MAXIMUM_INTERVAL_DAYS = 36_500
_SCHEDULER_NAME = "fsrs"
_MAX_SQLITE_INTEGER = (1 << 63) - 1
_MAX_STABILITY = 1_000_000_000.0


class Rating(str, Enum):
    AGAIN = "again"
    HARD = "hard"
    GOOD = "good"
    EASY = "easy"


class ReviewState(str, Enum):
    NEW = "new"
    LEARNING = "learning"
    REVIEW = "review"
    RELEARNING = "relearning"


def _utc(value: datetime, *, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware UTC")
    if value.utcoffset().total_seconds() != 0:
        raise ValueError(f"{field} must be UTC")
    return value.astimezone(UTC)


def _integer(value: object, *, field: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field} must be an integer")
    if not minimum <= value <= _MAX_SQLITE_INTEGER:
        raise ValueError(f"{field} must be between {minimum} and {_MAX_SQLITE_INTEGER}")
    return value


def _number(value: object, *, field: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field} must be a number")
    result = float(value)
    if not isfinite(result) or not minimum <= result <= maximum:
        raise ValueError(f"{field} must be between {minimum} and {maximum}")
    return result


def _datetime_from_record(value: object, *, field: str) -> datetime:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be an ISO 8601 string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field} must be a valid ISO 8601 datetime") from error
    return _utc(parsed, field=field)


@dataclass(frozen=True, slots=True)
class Schedule:
    """Validated scheduling state compatible with migration 015 columns."""

    difficulty: float
    stability: float
    due_at: datetime
    last_reviewed_at: datetime | None
    repetitions: int
    lapses: int
    state: ReviewState
    scheduler_state: Mapping[str, int | None]
    scheduler: str = _SCHEDULER_NAME
    scheduler_version: str = SCHEDULER_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "difficulty",
            _number(
                self.difficulty,
                field="difficulty",
                minimum=1.0,
                maximum=10.0,
            ),
        )
        object.__setattr__(
            self,
            "stability",
            _number(
                self.stability,
                field="stability",
                minimum=0.0,
                maximum=_MAX_STABILITY,
            ),
        )
        object.__setattr__(self, "due_at", _utc(self.due_at, field="due_at"))
        if self.last_reviewed_at is not None:
            object.__setattr__(
                self,
                "last_reviewed_at",
                _utc(self.last_reviewed_at, field="last_reviewed_at"),
            )
        object.__setattr__(
            self, "repetitions", _integer(self.repetitions, field="repetitions")
        )
        object.__setattr__(self, "lapses", _integer(self.lapses, field="lapses"))
        if not isinstance(self.state, ReviewState):
            raise TypeError("state must be a ReviewState")
        if self.scheduler != _SCHEDULER_NAME:
            raise ValueError("scheduler must be fsrs")
        if self.scheduler_version != SCHEDULER_VERSION:
            raise ValueError("scheduler_version is not supported")
        if not isinstance(self.scheduler_state, Mapping):
            raise TypeError("scheduler_state must be a mapping")

        card_id = _integer(
            self.scheduler_state.get("card_id"),
            field="scheduler_state.card_id",
            minimum=1,
        )
        step_value = self.scheduler_state.get("step")
        step = (
            None
            if step_value is None
            else _integer(step_value, field="scheduler_state.step")
        )
        if set(self.scheduler_state) != {"card_id", "step"}:
            raise ValueError("scheduler_state must contain only card_id and step")
        object.__setattr__(
            self,
            "scheduler_state",
            MappingProxyType({"card_id": card_id, "step": step}),
        )

        if self.state is ReviewState.NEW:
            if (
                self.last_reviewed_at is not None
                or self.repetitions != 0
                or self.lapses != 0
                or self.stability != 0.0
                or step != 0
            ):
                raise ValueError("new review state is internally inconsistent")
        else:
            if self.last_reviewed_at is None or self.repetitions == 0:
                raise ValueError("reviewed state requires review history")
            if self.stability <= 0.0:
                raise ValueError("reviewed state requires positive stability")
            if self.due_at < self.last_reviewed_at:
                raise ValueError("due_at cannot precede last_reviewed_at")

        if self.state is ReviewState.REVIEW and step is not None:
            raise ValueError("review state cannot have a learning step")
        if (
            self.state in {ReviewState.LEARNING, ReviewState.RELEARNING}
            and step is None
        ):
            raise ValueError("learning state requires a learning step")

    def to_record(self) -> dict[str, object]:
        """Return migration-015-compatible persistence fields."""

        return {
            "difficulty": self.difficulty,
            "stability": self.stability,
            "due_at": self.due_at.isoformat(),
            "last_reviewed_at": (
                self.last_reviewed_at.isoformat()
                if self.last_reviewed_at is not None
                else None
            ),
            "repetitions": self.repetitions,
            "lapses": self.lapses,
            "state": self.state.value,
            "scheduler": self.scheduler,
            "scheduler_version": self.scheduler_version,
            "scheduler_state": dict(self.scheduler_state),
        }

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> Schedule:
        """Restore and validate migration-015-compatible persistence fields."""

        try:
            state = ReviewState(record["state"])
            due_at = _datetime_from_record(record["due_at"], field="due_at")
            last_value = record["last_reviewed_at"]
            last_reviewed_at = (
                None
                if last_value is None
                else _datetime_from_record(last_value, field="last_reviewed_at")
            )
            raw_scheduler_state = record["scheduler_state"]
            if not isinstance(raw_scheduler_state, Mapping):
                raise TypeError("scheduler_state must be a mapping")
            scheduler_state = dict(raw_scheduler_state)
            scheduler = record["scheduler"]
            scheduler_version = record["scheduler_version"]
            if not isinstance(scheduler, str) or not isinstance(scheduler_version, str):
                raise TypeError("scheduler metadata must be strings")
            return cls(
                difficulty=_number(
                    record["difficulty"],
                    field="difficulty",
                    minimum=1.0,
                    maximum=10.0,
                ),
                stability=_number(
                    record["stability"],
                    field="stability",
                    minimum=0.0,
                    maximum=_MAX_STABILITY,
                ),
                due_at=due_at,
                last_reviewed_at=last_reviewed_at,
                repetitions=_integer(record["repetitions"], field="repetitions"),
                lapses=_integer(record["lapses"], field="lapses"),
                state=state,
                scheduler_state=scheduler_state,
                scheduler=scheduler,
                scheduler_version=scheduler_version,
            )
        except KeyError as error:
            raise ValueError(f"missing schedule field: {error.args[0]}") from error


class ReviewScheduler(Protocol):
    """Boundary for deterministic review scheduling implementations."""

    def new_schedule(self, *, card_id: int, now: datetime) -> Schedule: ...

    def review(
        self, *, current: Schedule, rating: Rating, reviewed_at: datetime
    ) -> Schedule: ...


_TO_FSRS_RATING = {
    Rating.AGAIN: FSRSRating.Again,
    Rating.HARD: FSRSRating.Hard,
    Rating.GOOD: FSRSRating.Good,
    Rating.EASY: FSRSRating.Easy,
}
_TO_FSRS_STATE = {
    ReviewState.LEARNING: FSRSState.Learning,
    ReviewState.REVIEW: FSRSState.Review,
    ReviewState.RELEARNING: FSRSState.Relearning,
}
_FROM_FSRS_STATE = {
    FSRSState.Learning: ReviewState.LEARNING,
    FSRSState.Review: ReviewState.REVIEW,
    FSRSState.Relearning: ReviewState.RELEARNING,
}


class FSRSReviewScheduler:
    """Adapter for the exact pinned py-fsrs release with fuzzing disabled."""

    def __init__(self) -> None:
        installed_version = version("fsrs")
        if installed_version != UPSTREAM_FSRS_VERSION:
            raise RuntimeError(
                "unsupported fsrs package version: "
                f"expected {UPSTREAM_FSRS_VERSION}, found {installed_version}"
            )
        self._scheduler = FSRSScheduler(
            desired_retention=DESIRED_RETENTION,
            maximum_interval=MAXIMUM_INTERVAL_DAYS,
            enable_fuzzing=False,
        )

    def new_schedule(self, *, card_id: int, now: datetime) -> Schedule:
        timestamp = _utc(now, field="now")
        return Schedule(
            difficulty=5.0,
            stability=0.0,
            due_at=timestamp,
            last_reviewed_at=None,
            repetitions=0,
            lapses=0,
            state=ReviewState.NEW,
            scheduler_state={
                "card_id": _integer(card_id, field="card_id", minimum=1),
                "step": 0,
            },
        )

    def review(
        self, *, current: Schedule, rating: Rating, reviewed_at: datetime
    ) -> Schedule:
        if not isinstance(current, Schedule):
            raise TypeError("current must be a Schedule")
        if not isinstance(rating, Rating):
            raise TypeError("rating must be a Rating")
        timestamp = _utc(reviewed_at, field="reviewed_at")
        if (
            current.last_reviewed_at is not None
            and timestamp < current.last_reviewed_at
        ):
            raise ValueError("reviewed_at cannot precede the previous review")

        reviewed_card, _ = self._scheduler.review_card(
            self._to_fsrs_card(current),
            _TO_FSRS_RATING[rating],
            review_datetime=timestamp,
        )
        if reviewed_card.difficulty is None or reviewed_card.stability is None:
            raise RuntimeError("fsrs returned an incomplete reviewed card")
        return Schedule(
            difficulty=reviewed_card.difficulty,
            stability=reviewed_card.stability,
            due_at=reviewed_card.due,
            last_reviewed_at=reviewed_card.last_review,
            repetitions=current.repetitions + 1,
            lapses=current.lapses
            + int(current.state is ReviewState.REVIEW and rating is Rating.AGAIN),
            state=_FROM_FSRS_STATE[reviewed_card.state],
            scheduler_state={
                "card_id": reviewed_card.card_id,
                "step": reviewed_card.step,
            },
        )

    @staticmethod
    def _to_fsrs_card(schedule: Schedule) -> FSRSCard:
        if schedule.state is ReviewState.NEW:
            state = FSRSState.Learning
            difficulty = None
            stability = None
        else:
            state = _TO_FSRS_STATE[schedule.state]
            difficulty = schedule.difficulty
            stability = schedule.stability
        card_id = schedule.scheduler_state["card_id"]
        step = schedule.scheduler_state["step"]
        assert card_id is not None
        return FSRSCard(
            card_id=card_id,
            state=state,
            step=step,
            stability=stability,
            difficulty=difficulty,
            due=schedule.due_at,
            last_review=schedule.last_reviewed_at,
        )


__all__ = [
    "FSRSReviewScheduler",
    "Rating",
    "ReviewScheduler",
    "ReviewState",
    "Schedule",
]
