from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    session_token: str
    database_path: Path
    seed_demo: bool = False

    def __post_init__(self) -> None:
        if len(self.session_token) < 32:
            raise ValueError("session token must be at least 32 characters")
        object.__setattr__(self, "database_path", Path(self.database_path).expanduser())
