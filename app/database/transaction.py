from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from sqlite3 import Connection
from typing import Any, Callable, TypeVar, cast

from app.database.connection import get_connection


_active_connection: ContextVar[Connection | None] = ContextVar(
    "active_database_connection",
    default=None,
)

Result = TypeVar("Result")


@contextmanager
def transaction(*, write: bool = True) -> Iterator[Connection]:
    """Own one database transaction, reusing an existing boundary.

    Services own write transactions. Nested service calls reuse the active
    connection and leave commit or rollback responsibility to the outermost
    business operation.
    """
    active = _active_connection.get()
    if active is not None:
        yield active
        return

    connection = get_connection()
    token = _active_connection.set(connection)

    try:
        _begin(connection, write=write)
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        _active_connection.reset(token)
        connection.close()


@contextmanager
def connection_scope() -> Iterator[Connection]:
    """Give repositories the current connection without transaction ownership."""
    active = _active_connection.get()
    if active is not None:
        yield active
        return

    # Backward-compatible repository use outside a service operation.
    with transaction(write=False) as connection:
        yield connection


def transactional(
    function: Callable[..., Result],
) -> Callable[..., Result]:
    """Mark a service method as one atomic business operation."""

    @wraps(function)
    def wrapped(*args: Any, **kwargs: Any) -> Result:
        with transaction(write=True):
            return function(*args, **kwargs)

    return cast(Callable[..., Result], wrapped)


def _begin(connection: Connection, *, write: bool) -> None:
    """Apply adapter-specific transaction start behavior internally."""
    connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
