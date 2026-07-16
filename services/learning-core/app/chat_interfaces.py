from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class ChatModel:
    provider: Literal["ollama", "openai-compatible"]
    model: str
    version: str

    def __post_init__(self) -> None:
        if not self.model.strip() or not self.version.strip():
            raise ValueError("chat model and version must not be empty")


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Literal["system", "user", "assistant"]
    content: str

    def __post_init__(self) -> None:
        if not self.content.strip():
            raise ValueError("chat message content must not be empty")


@runtime_checkable
class ChatProvider(Protocol):
    @property
    def model(self) -> ChatModel: ...

    def stream(self, messages: Sequence[ChatMessage]) -> AsyncIterator[str]: ...

    async def aclose(self) -> None: ...
