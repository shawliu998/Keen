# Slice 4 packaged non-empty Session restart review

Date: 2026-07-27

## Decision requested

Does this evidence satisfy Slice 4's remaining packaged persistence/restart
gate for the authoritative Session state?

Return one of:

- `ACCEPT`: the packaged service restart gate is closed;
- `CORRECT`: name one concrete missing observation or invariant;
- `REJECT`: identify a product or persistence contradiction.

This package does **not** claim a packaged WebView screenshot, Developer ID
signature, notarization, provider run, or pixel parity. If a native UI
observation remains independently required, keep that as a separate visual
verification item rather than rejecting the persistence result below.

## Product boundary

The verification used the newly built sidecar inside the production-named
`Keen.app`. It did not add a route, coordinator, audit script, provider call,
fixture-only Session, or second state store.

One isolated temporary profile received:

1. a minimal canonical stored Markdown source linked to the existing demo
   course (the only direct fixture);
2. a real focused-learning request through
   `POST /v1/focused-study-requests`;
3. a real pending opening Diagnostic through
   `POST /v1/study-sessions/{id}/diagnostic`;
4. a full packaged-sidecar process stop and restart against the same SQLite
   database;
5. authoritative Session, Diagnostic and History reads;
6. an exact replay of the original focused-learning request.

The temporary profile was removed after the command. No user profile or saved
learning data was touched.

## Fresh package result

Command:

```text
scripts/package-macos.sh
```

Observed:

- migrations `001–032` were frozen into the sidecar;
- `hdiutil verify` reported the DMG checksum valid;
- the mounted app and sidecar passed strict signature validation;
- `smoke-bundled-sidecar.sh` passed READY, job/cancellation, CJK, many-to-many,
  sqlite-vec, PDF geometry/content, token and cleanup checks;
- `smoke-bundled-review-restart.py` passed token rotation, Review due read,
  FSRS rating, restart recovery, exact replay and single-attempt persistence;
- the final standalone `Keen.app` repeated both sidecar and Review-restart
  smokes successfully.

Artifact:

```text
apps/desktop/src-tauri/target/release/bundle/dmg/Keen_0.1.0_aarch64.dmg
34264522 bytes
SHA-256 14fd4446b071dbdda0d760f90af762fb32e695c88ea239d92bd8e6a934fcd38d
```

This is an ad-hoc local verification artifact, not a notarized release.

## Non-empty Session restart result

The Session and its pending checkpoint were created only through the public
domain APIs. The source fixture used a real file in the sidecar's canonical
content-addressed storage layout so startup reconciliation exercised the same
storage invariant as a normal import.

```json
{
  "result": "PASS",
  "course_id": "course-calculus",
  "task_id": "focused-task-cfd03df7-285a-5baf-afdf-cc3418894545",
  "session_id": "focused-session-cb97f140-b548-5a9d-a7e0-3875a9128755",
  "plan_id": "focused-plan-962c7e1d-afad-5c77-a5c3-891e85475fc7",
  "checkpoint_id": "diagnostic:aca3aa89-7911-52db-962d-752cf4bb8a9f",
  "restored_status": "diagnosing",
  "restored_revision": 2,
  "diagnostic_state": "pending",
  "history_contains_session": true,
  "focused_request_replay": "replayed",
  "old_token_rejected": true,
  "duplicate_provider_or_lineage_writes": 0
}
```

Counts immediately before process stop:

```json
{
  "study_tasks": 3,
  "study_sessions": 1,
  "study_plan_versions": 1,
  "study_units": 2,
  "study_checkpoints": 1,
  "agent_runs": 0,
  "agent_events": 0,
  "learning_intervention_outcomes": 0
}
```

Counts after recovery reads and the exact request replay were identical.
Therefore restart/replay created no duplicate Task, Session, plan, Unit,
checkpoint, Agent run, Agent event, provider work, or intervention lineage.

## Invariants proved

- the same Session identity and plan identity survive a packaged process
  restart;
- the persisted `revision = 2` and `diagnosing` state survive;
- the same pending Diagnostic checkpoint survives;
- History independently finds the same Session;
- the original creation command reconciles as `replayed`;
- a token from the prior sidecar generation is rejected;
- restart and replay do not create duplicate learning or Agent records;
- recovery remains usable with no configured model provider.

## Codex technical assessment

The packaged persistence/restart gate is satisfied at the service and durable
state boundary. A packaged WebView capture would verify presentation of that
state, not a different persistence invariant, and should remain a separate
bounded UI check if still required.
