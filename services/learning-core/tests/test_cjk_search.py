from __future__ import annotations

import sqlite3
from hashlib import sha256
from pathlib import Path

import pytest

from app.database import Database
from app.lexical_retrieval import detect_query_script, search_lexical


NOW = "2026-07-16T00:00:00+00:00"


@pytest.fixture
def lexical_database(tmp_path) -> Database:
    database = Database(tmp_path / "cjk-search.sqlite3")
    database.migrate()
    with database.connection() as connection:
        _insert_fixture_corpus(connection)
    return database


def test_python_sqlite_runtimes_support_fts5_trigram_tokenizer():
    # Verified in the repository's supported runtimes: Python 3.11 uses SQLite
    # 3.53.1 and the project Python 3.14 venv uses SQLite 3.53.3.
    assert sqlite3.sqlite_version_info >= (3, 34, 0)
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute(
            "CREATE VIRTUAL TABLE trigram_probe USING fts5(text, tokenize='trigram')"
        )
        connection.execute("INSERT INTO trigram_probe(text) VALUES (?)", ("光合作用",))
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM trigram_probe WHERE trigram_probe MATCH ?",
                ("光合作用",),
            ).fetchone()[0]
            == 1
        )
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("query", "expected_chunk"),
    [
        ("傅里叶变换为什么能表示信号", "chunk-fourier"),
        ("牛顿第二定律", "chunk-newton"),
        ("eigenvector direction", "chunk-eigenvector"),
        ("matrix 特征向量 direction", "chunk-eigenvector"),
        ("gradient 梯度 descent", "chunk-gradient-descent"),
        ("叶绿体如何进行光合作用", "chunk-photosynthesis"),
        ("cellular respiration energy", "chunk-respiration"),
        ("线粒体 ATP", "chunk-respiration"),
        ("牛顿第二定律的加速度", "chunk-newton"),
        ("日本近代化与明治维新", "chunk-meiji"),
        ("怎样求解二次方程", "chunk-quadratic"),
    ],
)
def test_latin_cjk_and_mixed_queries_rank_relevant_chunk_first(
    lexical_database, query, expected_chunk
):
    with lexical_database.connection() as connection:
        results = search_lexical(connection, query, course_id=None, limit=5)

    assert results
    assert results[0]["chunk_id"] == expected_chunk
    assert len({result["chunk_id"] for result in results}) == len(results)


def test_mixed_query_uses_rrf_deduplication(lexical_database):
    with lexical_database.connection() as connection:
        mixed = search_lexical(connection, "线粒体 ATP", course_id=None, limit=10)
        latin_only = search_lexical(connection, "ATP", course_id=None, limit=10)

    assert mixed[0]["chunk_id"] == "chunk-respiration"
    assert mixed[0]["score"] > latin_only[0]["score"]
    assert [item["chunk_id"] for item in mixed].count("chunk-respiration") == 1


def test_course_filter_uses_many_to_many_membership(lexical_database):
    with lexical_database.connection() as connection:
        science = search_lexical(
            connection, "光合作用", course_id="course-science", limit=5
        )
        language = search_lexical(
            connection, "光合作用", course_id="course-language", limit=5
        )
        missing = search_lexical(
            connection, "光合作用", course_id="course-missing", limit=5
        )

    assert science[0]["chunk_id"] == "chunk-photosynthesis"
    assert {item["document_id"] for item in science} == {"doc-biology"}
    assert language[0]["chunk_id"] == "chunk-language"
    assert {item["document_id"] for item in language} == {"doc-language"}
    assert missing == []


def test_fts_values_are_parameterized_and_script_detection_is_explicit(
    lexical_database,
):
    assert detect_query_script("photosynthesis") == "latin"
    assert detect_query_script("光合作用") == "cjk"
    assert detect_query_script("ATP 在线粒体") == "mixed"
    with pytest.raises(ValueError, match="letter or number"):
        detect_query_script("' -- **")

    with lexical_database.connection() as connection:
        results = search_lexical(
            connection,
            '光合作用" OR document_chunks_cjk_fts:*',
            course_id=None,
            limit=10,
        )
        table_still_exists = connection.execute(
            """
            SELECT 1 FROM sqlite_master
            WHERE type = 'table' AND name = 'document_chunks_cjk_fts'
            """
        ).fetchone()

    assert {item["chunk_id"] for item in results} & {
        "chunk-photosynthesis",
        "chunk-language",
    }
    assert table_still_exists is not None


def test_migration_005_rebuilds_existing_chunks_and_triggers_stay_in_sync(
    tmp_path,
):
    database = Database(tmp_path / "cjk-rebuild.sqlite3")
    _apply_migrations_before_005(database)
    with database.connection() as connection:
        _insert_courses(connection)
        _insert_document(
            connection,
            document_id="doc-before-005",
            name="before.txt",
            course_ids=("course-science",),
            chunks=(("chunk-before-005", "叶绿体负责进行光合作用。"),),
        )

    assert database.migrate() == list(range(5, 18))
    with database.connection() as connection:
        rebuilt = search_lexical(connection, "叶绿体光合作用", course_id=None, limit=5)
        connection.execute(
            "UPDATE document_chunks SET content = ? WHERE id = ?",
            ("量子纠缠体现非经典关联。", "chunk-before-005"),
        )
        connection.commit()
        old_results = search_lexical(
            connection, "叶绿体光合作用", course_id=None, limit=5
        )
        updated = search_lexical(connection, "量子纠缠关联", course_id=None, limit=5)
        connection.execute(
            "DELETE FROM document_chunks WHERE id = ?", ("chunk-before-005",)
        )
        connection.commit()
        deleted = search_lexical(connection, "量子纠缠关联", course_id=None, limit=5)

    assert rebuilt[0]["chunk_id"] == "chunk-before-005"
    assert old_results == []
    assert updated[0]["chunk_id"] == "chunk-before-005"
    assert deleted == []


def _insert_fixture_corpus(connection: sqlite3.Connection) -> None:
    _insert_courses(connection)
    _insert_document(
        connection,
        document_id="doc-biology",
        name="biology.txt",
        course_ids=("course-science",),
        chunks=(
            (
                "chunk-photosynthesis",
                "植物在叶绿体中完成光合作用，把光能转化并合成有机物。",
            ),
            (
                "chunk-respiration",
                "Cellular respiration 在线粒体中释放 energy，并产生 ATP。",
            ),
        ),
    )
    _insert_document(
        connection,
        document_id="doc-physics",
        name="physics.txt",
        course_ids=("course-science",),
        chunks=(("chunk-newton", "牛顿第二定律把物体受力、质量和加速度联系起来。"),),
    )
    _insert_document(
        connection,
        document_id="doc-signals",
        name="signals.txt",
        course_ids=("course-science",),
        chunks=(
            (
                "chunk-fourier",
                "周期波形可分解成不同频率的正弦与余弦分量，傅里叶变换由此给出频域表示。",
            ),
        ),
    )
    _insert_document(
        connection,
        document_id="doc-linear-algebra",
        name="linear-algebra.txt",
        course_ids=("course-science",),
        chunks=(
            (
                "chunk-eigenvector",
                "An eigenvector preserves its direction after a matrix transformation；"
                "它就是矩阵所对应的特征向量。",
            ),
        ),
    )
    _insert_document(
        connection,
        document_id="doc-optimization",
        name="optimization.txt",
        course_ids=("course-science",),
        chunks=(
            (
                "chunk-gradient-descent",
                "Gradient descent 沿负梯度方向逐步更新参数，从而降低目标函数。",
            ),
        ),
    )
    _insert_document(
        connection,
        document_id="doc-history",
        name="history.txt",
        course_ids=("course-history",),
        chunks=(("chunk-meiji", "明治维新推动日本制度改革与工业近代化。"),),
    )
    _insert_document(
        connection,
        document_id="doc-math",
        name="math.txt",
        course_ids=("course-science",),
        chunks=(("chunk-quadratic", "二次方程可以使用配方法或求根公式求解。"),),
    )
    _insert_document(
        connection,
        document_id="doc-language",
        name="language.txt",
        course_ids=("course-language",),
        chunks=(("chunk-language", "本课只分析“光合作用”这个词的汉语构词方式。"),),
    )


def _insert_courses(connection: sqlite3.Connection) -> None:
    connection.executemany(
        """
        INSERT INTO courses(id, title, description, created_at)
        VALUES (?, ?, '', ?)
        """,
        [
            ("course-science", "Science", NOW),
            ("course-history", "History", NOW),
            ("course-language", "Language", NOW),
        ],
    )
    connection.commit()


def _insert_document(
    connection: sqlite3.Connection,
    *,
    document_id: str,
    name: str,
    course_ids: tuple[str, ...],
    chunks: tuple[tuple[str, str], ...],
) -> None:
    version_id = f"version-{document_id}"
    combined = "\n".join(content for _chunk_id, content in chunks)
    content_hash = sha256(combined.encode()).hexdigest()
    connection.execute(
        """
        INSERT INTO documents(
            id, course_id, name, mime_type, extension, status,
            page_count, chunk_count, error, created_at, updated_at
        ) VALUES (?, ?, ?, 'text/plain', '.txt', 'indexed', 1, ?, NULL, ?, ?)
        """,
        (document_id, course_ids[0], name, len(chunks), NOW, NOW),
    )
    connection.execute(
        """
        INSERT INTO document_versions(
            id, document_id, version_number, content_hash, storage_path,
            size_bytes, parser_version, page_count, created_at
        ) VALUES (?, ?, 1, ?, ?, ?, 'test-parser/1', 1, ?)
        """,
        (
            version_id,
            document_id,
            content_hash,
            f"fixture/{content_hash}.txt",
            len(combined.encode()),
            NOW,
        ),
    )
    connection.executemany(
        """
        INSERT INTO course_documents(course_id, document_id, added_at)
        VALUES (?, ?, ?)
        """,
        [(course_id, document_id, NOW) for course_id in course_ids],
    )
    for ordinal, (chunk_id, content) in enumerate(chunks):
        connection.execute(
            """
            INSERT INTO document_chunks(
                id, document_id, version_id, ordinal, page_number,
                section_path, content, content_hash, text_location,
                parser_version, embedding_version, created_at
            ) VALUES (?, ?, ?, ?, 1, '[]', ?, ?, ?, 'test-parser/1', NULL, ?)
            """,
            (
                chunk_id,
                document_id,
                version_id,
                ordinal,
                content,
                sha256(content.encode()).hexdigest(),
                f'{{"unit":{ordinal},"start":0,"end":{len(content)}}}',
                NOW,
            ),
        )
    connection.commit()


def _apply_migrations_before_005(database: Database) -> None:
    migrations = Path(__file__).resolve().parent.parent / "migrations"
    with database.connection() as connection:
        for version in (1, 2, 3, 4):
            migration = next(migrations.glob(f"{version:03d}_*.sql"))
            connection.executescript(migration.read_text(encoding="utf-8"))
        connection.execute(
            """
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.executemany(
            "INSERT INTO schema_migrations(version) VALUES (?)",
            [(1,), (2,), (3,), (4,)],
        )
        connection.commit()
