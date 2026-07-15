from __future__ import annotations


def test_health_requires_session_token(client, auth_headers):
    missing = client.get("/health")
    invalid = client.get(
        "/health",
        headers={"Authorization": "Bearer ffffffffffffffffffffffffffffffff"},
    )
    valid = client.get("/health", headers=auth_headers)

    assert missing.status_code == 401
    assert missing.headers["www-authenticate"] == "Bearer"
    assert invalid.status_code == 401
    assert valid.status_code == 200
    assert valid.json() == {
        "status": "ok",
        "service": "keen-learning-core",
        "version": "0.1.0",
    }


def test_demo_state_is_seeded(client, auth_headers):
    response = client.get("/v1/demo-state", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body["courses"]) == 2
    assert len(body["tasks"]) == 2
    assert len(body["mastery"]) == 3
