from __future__ import annotations

import time


def _upload(client, headers, course_id: str, content: bytes):
    return client.post(
        "/v1/documents/import",
        headers=headers,
        data={"course_id": course_id},
        files={"file": ("shared.txt", content, "text/plain")},
    )


def _wait_completed(client, headers, job_id: str) -> dict:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        job = client.get(f"/v1/index-jobs/{job_id}", headers=headers).json()
        if job["status"] in {"completed", "failed", "cancelled", "interrupted"}:
            return job
        time.sleep(0.02)
    raise AssertionError("index job did not finish")


def test_same_hash_two_course_links_share_index_and_unlink_never_deletes_document(
    client, auth_headers
):
    content = b"One source supports searchable thermodynamics notes in two courses."
    course_a = "course-calculus"
    course_b = "course-physics"

    first = _upload(client, auth_headers, course_a, content)
    assert first.status_code == 202
    assert first.json()["duplicate"] is False
    assert first.json()["linked"] is True
    assert (
        _wait_completed(client, auth_headers, first.json()["job"]["id"])["status"]
        == "completed"
    )

    second = _upload(client, auth_headers, course_b, content)
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert second.json()["linked"] is True
    assert second.json()["document"]["id"] == first.json()["document"]["id"]
    assert second.json()["document"]["courseIds"] == [course_a, course_b]
    assert second.json()["job"]["id"] == first.json()["job"]["id"]

    document_id = first.json()["document"]["id"]
    with client.app.state.database.connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1
        assert (
            connection.execute("SELECT COUNT(*) FROM document_versions").fetchone()[0]
            == 1
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM document_index_jobs").fetchone()[0]
            == 1
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM course_documents").fetchone()[0]
            == 2
        )
        storage_path = connection.execute(
            "SELECT storage_path FROM document_versions WHERE document_id = ?",
            (document_id,),
        ).fetchone()["storage_path"]
    stored = client.app.state.settings.document_data_path / storage_path
    assert stored.read_bytes() == content
    stored_files = [
        path
        for path in client.app.state.settings.document_data_path.rglob("*")
        if path.is_file()
        and not any(
            part.startswith(".")
            for part in path.relative_to(
                client.app.state.settings.document_data_path
            ).parts
        )
    ]
    assert stored_files == [stored]

    for course_id in (course_a, course_b):
        listing = client.get(
            "/v1/documents", headers=auth_headers, params={"courseId": course_id}
        ).json()["documents"]
        assert [document["id"] for document in listing] == [document_id]
        results = client.post(
            "/v1/search",
            headers=auth_headers,
            json={"query": "thermodynamics", "courseId": course_id},
        ).json()["results"]
        assert [result["documentId"] for result in results] == [document_id]

    assert (
        client.delete(
            f"/v1/documents/{document_id}/courses/{course_a}", headers=auth_headers
        ).status_code
        == 204
    )
    assert (
        client.post(
            "/v1/search",
            headers=auth_headers,
            json={"query": "thermodynamics", "courseId": course_a},
        ).json()["results"]
        == []
    )
    assert client.post(
        "/v1/search",
        headers=auth_headers,
        json={"query": "thermodynamics", "courseId": course_b},
    ).json()["results"]

    assert (
        client.delete(
            f"/v1/documents/{document_id}/courses/{course_b}", headers=auth_headers
        ).status_code
        == 204
    )
    documents = client.get("/v1/documents", headers=auth_headers).json()["documents"]
    assert len(documents) == 1
    assert documents[0]["id"] == document_id
    assert documents[0]["courseIds"] == []
    assert client.post(
        "/v1/search",
        headers=auth_headers,
        json={"query": "thermodynamics"},
    ).json()["results"]
