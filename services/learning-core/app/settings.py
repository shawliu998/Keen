from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    session_token: str
    database_path: Path
    seed_demo: bool = False
    document_data_path: Path | None = None
    max_document_bytes: int = 25 * 1024 * 1024

    def __post_init__(self) -> None:
        if len(self.session_token) < 32:
            raise ValueError("session token must be at least 32 characters")
        if "\r" in self.session_token or "\n" in self.session_token:
            raise ValueError("session token must not contain line breaks")
        database_path = Path(self.database_path).expanduser()
        document_data_path = (
            Path(self.document_data_path).expanduser()
            if self.document_data_path is not None
            else database_path.parent / "documents"
        )
        if self.max_document_bytes <= 0:
            raise ValueError("max document bytes must be greater than zero")
        object.__setattr__(self, "database_path", database_path)
        object.__setattr__(self, "document_data_path", document_data_path)
