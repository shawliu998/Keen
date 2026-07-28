from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Sequence
from typing import Any, Protocol


class LocalWriteSession(Protocol):
    """Minimum transaction capability exposed to a Level 2 tool."""

    @property
    def active(self) -> bool: ...


class SQLiteToolResult:
    """Cursor facade that does not expose SQLite connection controls."""

    __slots__ = ("__cursor",)

    def __init__(self, cursor: sqlite3.Cursor) -> None:
        self.__cursor = cursor

    @property
    def rowcount(self) -> int:
        return self.__cursor.rowcount

    def fetchone(self) -> sqlite3.Row | tuple[Any, ...] | None:
        return self.__cursor.fetchone()

    def fetchall(self) -> list[sqlite3.Row] | list[tuple[Any, ...]]:
        return self.__cursor.fetchall()

    def __iter__(self) -> Iterator[sqlite3.Row | tuple[Any, ...]]:
        return iter(self.__cursor)


class SQLiteToolSession:
    """Narrow SQLite capability for trusted study-task repository operations.

    The transaction coordinator retains the real connection. Tools receive only
    this session, which cannot end or reshape the transaction and can access only
    the ``study_tasks`` table through the SELECT/UPDATE statements currently used
    by ``TaskRepository.get`` and ``TaskRepository.complete`` and by task Undo.
    """

    __slots__ = ("__connection", "__owner_token")

    def __init__(self, connection: sqlite3.Connection, owner_token: object) -> None:
        self.__connection = connection
        self.__owner_token = owner_token

    @property
    def active(self) -> bool:
        return self.__connection.in_transaction

    @property
    def in_transaction(self) -> bool:
        """Compatibility surface required by repository ``commit=False`` guards."""

        return self.active

    def execute(
        self,
        sql: str,
        parameters: Sequence[object] = (),
    ) -> SQLiteToolResult:
        if not self.active:
            raise RuntimeError("agent tool transaction is not active")
        if not isinstance(sql, str) or not sql.strip():
            raise PermissionError("agent tool SQL must be non-empty text")
        denied = False

        def authorize(
            action: int,
            first_argument: str | None,
            second_argument: str | None,
            database_name: str | None,
            trigger_name: str | None,
        ) -> int:
            del second_argument, trigger_name
            nonlocal denied
            if action == sqlite3.SQLITE_SELECT:
                return sqlite3.SQLITE_OK
            if (
                action in {sqlite3.SQLITE_READ, sqlite3.SQLITE_UPDATE}
                and first_argument == "study_tasks"
                and database_name == "main"
            ):
                return sqlite3.SQLITE_OK
            denied = True
            return sqlite3.SQLITE_DENY

        self.__connection.set_authorizer(authorize)
        try:
            cursor = self.__connection.execute(sql, parameters)
        except sqlite3.DatabaseError as error:
            if denied:
                raise PermissionError(
                    "agent tool SQL attempted an unauthorized database operation"
                ) from error
            raise
        finally:
            self.__connection.set_authorizer(None)
        return SQLiteToolResult(cursor)

    def commit(self) -> None:
        raise PermissionError("agent tools cannot commit their transaction")

    def rollback(self) -> None:
        raise PermissionError("agent tools cannot rollback their transaction")

    def _belongs_to(self, connection: sqlite3.Connection, owner_token: object) -> bool:
        """Coordinator-only identity check; it never returns the real connection."""

        return self.__connection is connection and self.__owner_token is owner_token
