from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Literal

from .provider_endpoints import ProviderKind, validate_provider_endpoint


@dataclass(frozen=True, slots=True)
class LocalEmbeddingSettings:
    """Complete, non-secret configuration for one loopback embedding model."""

    provider: Literal["ollama", "openai-compatible"]
    base_url: str
    model: str
    version: str
    dimensions: int
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 60.0
    write_timeout_seconds: float = 15.0
    pool_timeout_seconds: float = 5.0

    def __post_init__(self) -> None:
        if not self.model.strip() or not self.version.strip():
            raise ValueError("embedding model and version must not be empty")
        if len(self.model) > 256 or len(self.version) > 256:
            raise ValueError(
                "embedding model and version must be at most 256 characters"
            )
        if any(
            ord(character) < 32 or ord(character) == 127
            for value in (self.model, self.version)
            for character in value
        ):
            raise ValueError(
                "embedding model and version must not contain control characters"
            )
        if not 1 <= self.dimensions <= 8_192:
            raise ValueError("embedding dimensions must be between 1 and 8192")
        for name in (
            "connect_timeout_seconds",
            "read_timeout_seconds",
            "write_timeout_seconds",
            "pool_timeout_seconds",
        ):
            value = getattr(self, name)
            if not isfinite(value) or value <= 0:
                raise ValueError(
                    "embedding provider timeouts must be finite and greater than zero"
                )
        validate_provider_endpoint(ProviderKind(self.provider), self.base_url)


@dataclass(frozen=True, slots=True)
class LocalChatSettings:
    """Complete, non-secret configuration for one loopback chat model."""

    provider: Literal["ollama", "openai-compatible"]
    base_url: str
    model: str
    version: str
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 120.0
    write_timeout_seconds: float = 15.0
    pool_timeout_seconds: float = 5.0
    total_timeout_seconds: float = 180.0

    def __post_init__(self) -> None:
        if not self.model.strip() or not self.version.strip():
            raise ValueError("chat model and version must not be empty")
        if len(self.model) > 256 or len(self.version) > 256:
            raise ValueError("chat model and version must be at most 256 characters")
        if any(
            ord(character) < 32 or ord(character) == 127
            for value in (self.model, self.version)
            for character in value
        ):
            raise ValueError(
                "chat model and version must not contain control characters"
            )
        for name in (
            "connect_timeout_seconds",
            "read_timeout_seconds",
            "write_timeout_seconds",
            "pool_timeout_seconds",
            "total_timeout_seconds",
        ):
            value = getattr(self, name)
            if not isfinite(value) or value <= 0:
                raise ValueError(
                    "chat provider timeouts must be finite and greater than zero"
                )
        validate_provider_endpoint(ProviderKind(self.provider), self.base_url)


@dataclass(frozen=True, slots=True)
class Settings:
    session_token: str
    database_path: Path
    seed_demo: bool = False
    document_data_path: Path | None = None
    max_document_bytes: int = 25 * 1024 * 1024
    max_pdf_pages: int = 2_000
    max_extracted_characters: int = 12 * 1024 * 1024
    max_document_chunks: int = 12_000
    pdf_max_rss_bytes: int = 512 * 1024 * 1024
    pdf_no_progress_timeout_seconds: float = 15.0
    pdf_total_timeout_seconds: float = 180.0
    local_embedding: LocalEmbeddingSettings | None = None
    local_chat: LocalChatSettings | None = None

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
        integer_limits = {
            "max PDF pages": self.max_pdf_pages,
            "max extracted characters": self.max_extracted_characters,
            "max document chunks": self.max_document_chunks,
            "PDF max RSS bytes": self.pdf_max_rss_bytes,
        }
        for label, value in integer_limits.items():
            if value <= 0:
                raise ValueError(f"{label} must be greater than zero")
        if self.pdf_no_progress_timeout_seconds <= 0:
            raise ValueError("PDF no-progress timeout must be greater than zero")
        if self.pdf_total_timeout_seconds <= 0:
            raise ValueError("PDF total timeout must be greater than zero")
        if self.pdf_no_progress_timeout_seconds > self.pdf_total_timeout_seconds:
            raise ValueError("PDF no-progress timeout must not exceed total timeout")
        object.__setattr__(self, "database_path", database_path)
        object.__setattr__(self, "document_data_path", document_data_path)
