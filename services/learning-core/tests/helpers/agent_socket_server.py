from __future__ import annotations

import argparse
import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import uvicorn

from app.__main__ import (
    ReadyAnnouncingServer,
    SidecarLifecycleEvents,
    bind_loopback_listener,
    resolve_session_token,
)
from app.agent.provider import ContentDelta, ProviderAction, ProviderRequest
from app.main import create_app
from app.settings import Settings


class BlockingSocketTestProvider:
    """Test-only provider that leaves a durable partial run for crash recovery."""

    name = "socket-test"
    model = "blocking-provider"
    version = "socket-restart-v1"

    async def stream(self, request: ProviderRequest) -> AsyncIterator[ProviderAction]:
        del request
        yield ContentDelta(text="partial-before-process-crash")
        await asyncio.Event().wait()

    async def aclose(self) -> None:
        return None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    token = resolve_session_token(None, read_from_stdin=True)
    settings = Settings(session_token=token, database_path=args.database)
    events = SidecarLifecycleEvents()
    with bind_loopback_listener(0) as listener:
        port = int(listener.getsockname()[1])
        events.announce_port(port)
        config = uvicorn.Config(
            create_app(
                settings,
                startup_phase_reporter=events.announce_phase,
                agent_provider_factory=BlockingSocketTestProvider,
            ),
            host="127.0.0.1",
            port=port,
            log_config=None,
            access_log=False,
        )
        ReadyAnnouncingServer(config, events).run(sockets=[listener])


if __name__ == "__main__":
    main()
