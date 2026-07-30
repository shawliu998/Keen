"""PyInstaller entry point for the bundled Keen learning-core sidecar."""

import multiprocessing
import os
import sys
import threading
import time

SUPERVISOR_PID_ENVIRONMENT_KEY = "KEEN_SUPERVISOR_PID"


def _configured_supervisor_pid() -> int:
    raw_pid = os.environ.pop(SUPERVISOR_PID_ENVIRONMENT_KEY, None)
    if raw_pid is None:
        return os.getppid()
    try:
        supervisor_pid = int(raw_pid)
    except ValueError as error:
        raise SystemExit("invalid Keen supervisor PID") from error
    if supervisor_pid <= 1 or supervisor_pid == os.getpid():
        raise SystemExit("invalid Keen supervisor PID")
    return supervisor_pid


def _process_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _watch_supervisor(supervisor_pid: int) -> None:
    """Exit when either the Tauri supervisor or one-file bootloader disappears."""
    bootloader_pid = os.getppid()

    def watch() -> None:
        while True:
            if (
                os.getppid() != bootloader_pid
                or not _process_is_alive(bootloader_pid)
                or not _process_is_alive(supervisor_pid)
            ):
                os._exit(1)
            time.sleep(0.25)

    threading.Thread(target=watch, name="keen-supervisor-watch", daemon=True).start()


if __name__ == "__main__":
    multiprocessing.freeze_support()

    # The one-file bootloader removes its extracted entrypoint before a later
    # multiprocessing "spawn" child can import it. PDF workers only need their
    # importable app.documents target, so do not put that stale path into the
    # spawn preparation payload.
    if getattr(sys, "frozen", False):
        sys.modules["__main__"].__file__ = None

    from app.__main__ import main

    _watch_supervisor(_configured_supervisor_pid())
    main()
