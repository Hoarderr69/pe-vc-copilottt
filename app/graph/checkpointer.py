"""
LangGraph checkpointer backed by Azure Database for PostgreSQL.

Every graph in app/graph/ compiles with this checkpointer so runs survive
across HTTP requests (interrupt/resume for HITL, crash recovery mid-report).
Requires DATABASE_URL, e.g.:

    postgresql://user:password@host:5432/dbname?sslmode=require
"""

from __future__ import annotations

import os
from typing import List, Optional

from langgraph.checkpoint.postgres import PostgresSaver

REQUIRED_VARS: List[str] = ["DATABASE_URL"]

_checkpointer: Optional[PostgresSaver] = None


def missing_vars() -> List[str]:
    return [v for v in REQUIRED_VARS if not os.getenv(v)]


def is_configured() -> bool:
    return not missing_vars()


def get_checkpointer() -> PostgresSaver:
    """Return the process-wide PostgresSaver, opening the connection and
    running .setup() on first call. Raises with a clear message if
    DATABASE_URL is not set.
    """
    global _checkpointer

    if _checkpointer is not None:
        return _checkpointer

    missing = missing_vars()
    if missing:
        raise RuntimeError(
            "LangGraph Postgres checkpointer is not configured. Set: "
            + ", ".join(missing)
        )

    # Imported lazily so the rest of the app runs without psycopg configured.
    from psycopg import Connection
    from psycopg.rows import dict_row

    conn = Connection.connect(
        os.environ["DATABASE_URL"],
        autocommit=True,
        prepare_threshold=0,
        row_factory=dict_row,
    )
    checkpointer = PostgresSaver(conn)
    checkpointer.setup()

    _checkpointer = checkpointer
    return _checkpointer
