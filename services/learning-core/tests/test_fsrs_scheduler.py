from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.review import FSRSReviewScheduler, Rating, ReviewState, Schedule


NOW = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)


@pytest.fixture
def scheduler() -> FSRSReviewScheduler:
    return FSRSReviewScheduler()


@pytest.mark.parametrize(
    ("rating", "expected_state"),
    [
        (Rating.AGAIN, ReviewState.LEARNING),
        (Rating.HARD, ReviewState.LEARNING),
        (Rating.GOOD, ReviewState.LEARNING),
        (Rating.EASY, ReviewState.REVIEW),
    ],
)
def test_all_ratings_schedule_a_new_item_deterministically(
    scheduler: FSRSReviewScheduler,
    rating: Rating,
    expected_state: ReviewState,
) -> None:
    initial = scheduler.new_schedule(card_id=42, now=NOW)

    first = scheduler.review(current=initial, rating=rating, reviewed_at=NOW)
    second = scheduler.review(current=initial, rating=rating, reviewed_at=NOW)

    assert first == second
    assert first.state is expected_state
    assert first.due_at > NOW
    assert first.last_reviewed_at == NOW
    assert first.repetitions == 1
    assert first.lapses == 0
    assert first.scheduler_state["card_id"] == 42


def test_rating_intervals_are_ordered_and_fuzzing_is_disabled(
    scheduler: FSRSReviewScheduler,
) -> None:
    initial = scheduler.new_schedule(card_id=7, now=NOW)

    scheduled = {
        rating: scheduler.review(current=initial, rating=rating, reviewed_at=NOW)
        for rating in Rating
    }

    assert scheduled[Rating.AGAIN].due_at == NOW + timedelta(minutes=1)
    assert scheduled[Rating.HARD].due_at == NOW + timedelta(minutes=5, seconds=30)
    assert scheduled[Rating.GOOD].due_at == NOW + timedelta(minutes=10)
    assert scheduled[Rating.EASY].due_at == NOW + timedelta(days=8)


def test_repeated_reviews_advance_state_and_count_review_lapses(
    scheduler: FSRSReviewScheduler,
) -> None:
    schedule = scheduler.new_schedule(card_id=9, now=NOW)
    schedule = scheduler.review(current=schedule, rating=Rating.GOOD, reviewed_at=NOW)
    schedule = scheduler.review(
        current=schedule,
        rating=Rating.GOOD,
        reviewed_at=NOW + timedelta(minutes=10),
    )

    assert schedule.state is ReviewState.REVIEW
    assert schedule.repetitions == 2
    assert schedule.lapses == 0

    schedule = scheduler.review(
        current=schedule,
        rating=Rating.AGAIN,
        reviewed_at=schedule.due_at,
    )

    assert schedule.state is ReviewState.RELEARNING
    assert schedule.repetitions == 3
    assert schedule.lapses == 1


def test_schedule_persistence_mapping_round_trips(
    scheduler: FSRSReviewScheduler,
) -> None:
    schedule = scheduler.review(
        current=scheduler.new_schedule(card_id=123, now=NOW),
        rating=Rating.EASY,
        reviewed_at=NOW,
    )

    record = schedule.to_record()

    assert record == {
        "difficulty": schedule.difficulty,
        "stability": schedule.stability,
        "due_at": schedule.due_at.isoformat(),
        "last_reviewed_at": NOW.isoformat(),
        "repetitions": 1,
        "lapses": 0,
        "state": "review",
        "scheduler": "fsrs",
        "scheduler_version": "fsrs-6.3.1-keen-v1",
        "scheduler_state": {"card_id": 123, "step": None},
    }
    assert Schedule.from_record(record) == schedule


def test_persisted_schedule_resumes_identically_after_restart(
    scheduler: FSRSReviewScheduler,
) -> None:
    first = scheduler.review(
        current=scheduler.new_schedule(card_id=124, now=NOW),
        rating=Rating.GOOD,
        reviewed_at=NOW,
    )
    restored = Schedule.from_record(first.to_record())
    reviewed_at = NOW + timedelta(minutes=10)

    uninterrupted = scheduler.review(
        current=first,
        rating=Rating.EASY,
        reviewed_at=reviewed_at,
    )
    after_restart = FSRSReviewScheduler().review(
        current=restored,
        rating=Rating.EASY,
        reviewed_at=reviewed_at,
    )

    assert after_restart == uninterrupted


def test_scheduler_version_cannot_hide_custom_parameters() -> None:
    with pytest.raises(TypeError, match="unexpected keyword argument"):
        FSRSReviewScheduler(desired_retention=0.8)  # type: ignore[call-arg]
    with pytest.raises(TypeError, match="unexpected keyword argument"):
        FSRSReviewScheduler(maximum_interval=30)  # type: ignore[call-arg]


def test_naive_datetimes_are_rejected(
    scheduler: FSRSReviewScheduler,
) -> None:
    naive = datetime(2026, 7, 16, 8, 0)

    with pytest.raises(ValueError, match="timezone-aware UTC"):
        scheduler.new_schedule(card_id=1, now=naive)

    initial = scheduler.new_schedule(card_id=1, now=NOW)
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        scheduler.review(current=initial, rating=Rating.GOOD, reviewed_at=naive)


def test_invalid_or_unbounded_inputs_are_rejected(
    scheduler: FSRSReviewScheduler,
) -> None:
    for invalid_card_id in (0, -1):
        with pytest.raises(ValueError, match="card_id"):
            scheduler.new_schedule(card_id=invalid_card_id, now=NOW)
    with pytest.raises(TypeError, match="rating"):
        scheduler.review(
            current=scheduler.new_schedule(card_id=1, now=NOW),
            rating="good",  # type: ignore[arg-type]
            reviewed_at=NOW,
        )


def test_schedule_rejects_non_finite_state() -> None:
    record = FSRSReviewScheduler().new_schedule(card_id=1, now=NOW).to_record()
    record["stability"] = float("nan")

    with pytest.raises(ValueError, match="stability"):
        Schedule.from_record(record)
