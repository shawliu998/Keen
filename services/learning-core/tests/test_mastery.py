from __future__ import annotations

import pytest

from app.database import Database
from app.mastery import BktParameters, update_bkt
from app.repository import LearningRepository


def test_bkt_update_is_deterministic():
    parameters = BktParameters(slip=0.1, guess=0.2, transit=0.1)

    assert update_bkt(0.42, correct=True, parameters=parameters) == 0.788664
    assert update_bkt(0.42, correct=False, parameters=parameters) == 0.174704
    assert update_bkt(0.42, correct=True, parameters=parameters) == update_bkt(
        0.42, correct=True, parameters=parameters
    )


def test_bkt_rejects_invalid_probabilities():
    with pytest.raises(ValueError):
        update_bkt(-0.01, correct=True)
    with pytest.raises(ValueError):
        BktParameters(slip=1.1)


def test_repository_records_mastery_event(tmp_path):
    database = Database(tmp_path / "mastery.sqlite3")
    database.migrate()
    database.seed_demo()

    with database.connection() as connection:
        repository = LearningRepository(connection)
        result = repository.record_attempt("concept-chain-rule", correct=True)
        event = connection.execute(
            "SELECT * FROM mastery_events WHERE concept_id = ?",
            ("concept-chain-rule",),
        ).fetchone()

    assert result is not None
    assert result["probability_before"] == 0.42
    assert result["probability_after"] == 0.788664
    assert result["attempts"] == 3
    assert event["probability_after"] == 0.788664
