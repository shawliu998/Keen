from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from .logging import configure_logging
from .main import create_app
from .settings import Settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Keen learning core sidecar")
    parser.add_argument("--token", required=True, help="ephemeral session Bearer token")
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--seed-demo", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not 1 <= args.port <= 65535:
        raise SystemExit("--port must be between 1 and 65535")
    configure_logging()
    settings = Settings(
        session_token=args.token,
        database_path=args.database,
        seed_demo=args.seed_demo,
    )
    uvicorn.run(create_app(settings), host="127.0.0.1", port=args.port, log_config=None)


if __name__ == "__main__":
    main()
