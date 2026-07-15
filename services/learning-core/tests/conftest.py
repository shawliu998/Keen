from __future__ import annotations

from collections.abc import Sequence

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings

TOKEN = "0123456789abcdef0123456789abcdef"


@pytest.fixture
def client(tmp_path):
    settings = Settings(
        session_token=TOKEN,
        database_path=tmp_path / "test.sqlite3",
        seed_demo=True,
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def auth_headers():
    return {"Authorization": f"Bearer {TOKEN}"}


def _minimal_text_pdf(pages: Sequence[str]) -> bytes:
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"",  # Filled after page object identifiers are known.
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    page_ids: list[int] = []
    for page_text in pages:
        page_id = len(objects) + 1
        content_id = page_id + 1
        page_ids.append(page_id)
        escaped = page_text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT\n/F1 14 Tf\n72 720 Td\n({escaped}) Tj\nET".encode("latin-1")
        objects.extend(
            [
                (
                    f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                    f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>"
                ).encode("ascii"),
                b"<< /Length "
                + str(len(stream)).encode("ascii")
                + b" >>\nstream\n"
                + stream
                + b"\nendstream",
            ]
        )
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("ascii")

    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_id, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{object_id} 0 obj\n".encode("ascii"))
        output.extend(body)
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(output)


@pytest.fixture
def pdf_bytes():
    return _minimal_text_pdf(
        [
            "Photosynthesis captures sunlight energy in chloroplasts.",
            "Mitochondria release stored energy through cellular respiration.",
        ]
    )


@pytest.fixture
def blank_pdf_bytes():
    return _minimal_text_pdf([""])
