"""
Minimal JSONB-backed document store against Azure Database for PostgreSQL.

One physical table (`app_documents`) holds every logical store's documents,
partitioned by `collection` (e.g. "vcp_milestones", "deals", "hitl_queue").
Existing file-backed stores (VCPStore, DealStore, CompanyMeta, ReportStore,
hitl_queue.py, hitl_decisions.py) can swap their read/write internals for a
PostgresJsonStore instance without changing their public method signatures.
"""

from __future__ import annotations

import os
import threading
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from psycopg_pool import ConnectionPool

TABLE_NAME = "app_documents"

# One pool per distinct DATABASE_URL, shared by every PostgresJsonStore instance
# (routes construct a fresh store object per call, e.g. `DealStore()` per request)
# so repeated get()/put()/list() calls reuse warm connections instead of paying a
# fresh TCP+TLS handshake to Azure Postgres on every single call.
_pools: Dict[str, "ConnectionPool"] = {}
_pools_lock = threading.Lock()


def _get_pool(database_url: str) -> "ConnectionPool":
    pool = _pools.get(database_url)
    if pool is not None:
        return pool

    with _pools_lock:
        pool = _pools.get(database_url)
        if pool is None:
            from psycopg.rows import dict_row
            from psycopg_pool import ConnectionPool

            pool = ConnectionPool(
                database_url,
                min_size=1,
                max_size=10,
                kwargs={"row_factory": dict_row},
                open=True,
            )
            _pools[database_url] = pool

        return pool


def close_all_pools() -> None:
    """Close every pooled connection. Call on app shutdown."""
    with _pools_lock:
        for pool in _pools.values():
            pool.close()
        _pools.clear()


def _strip_null_bytes(value: Any) -> Any:
    """Postgres text (and therefore JSONB) rejects the \\u0000 codepoint outright.
    Source documents (PDF/OCR extraction) occasionally carry stray null bytes, so
    strip them recursively rather than let every writer path guard against it."""
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, dict):
        return {k: _strip_null_bytes(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_strip_null_bytes(v) for v in value]
    return value

_SCHEMA_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    collection TEXT NOT NULL,
    id TEXT NOT NULL,
    doc JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (collection, id)
)
"""


class PostgresJsonStore:
    """get(id) / put(id, doc) / list() against one collection in one JSONB table."""

    def __init__(self, collection: str, database_url: Optional[str] = None):
        self.collection = collection
        self._database_url = database_url

    def _connect(self):
        database_url = self._database_url or os.environ.get("DATABASE_URL")
        if not database_url:
            raise RuntimeError(
                "PostgresJsonStore requires DATABASE_URL to be set "
                f"(collection={self.collection!r})."
            )

        return _get_pool(database_url).connection()

    def ensure_table(self) -> None:
        with self._connect() as conn:
            conn.execute(_SCHEMA_SQL)

    def get(self, id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT doc FROM {TABLE_NAME} WHERE collection = %s AND id = %s",
                (self.collection, id),
            ).fetchone()

        return row["doc"] if row else None

    def put(self, id: str, doc: Dict[str, Any]) -> None:
        from psycopg.types.json import Jsonb

        with self._connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {TABLE_NAME} (collection, id, doc, updated_at)
                VALUES (%s, %s, %s, now())
                ON CONFLICT (collection, id)
                DO UPDATE SET doc = EXCLUDED.doc, updated_at = EXCLUDED.updated_at
                """,
                (self.collection, id, Jsonb(_strip_null_bytes(doc))),
            )
            conn.commit()

    def list(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT doc FROM {TABLE_NAME} WHERE collection = %s ORDER BY id",
                (self.collection,),
            ).fetchall()

        return [row["doc"] for row in rows]

    def list_ids(self) -> List[str]:
        """Existence checks (e.g. 'does this report have a PDF') don't need the
        full doc — a plain `get()` per id in a loop is N round trips each pulling
        a potentially large JSONB blob just to test for None. This is one round
        trip fetching only ids."""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT id FROM {TABLE_NAME} WHERE collection = %s",
                (self.collection,),
            ).fetchall()

        return [row["id"] for row in rows]

    def delete(self, id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                f"DELETE FROM {TABLE_NAME} WHERE collection = %s AND id = %s",
                (self.collection, id),
            )
            conn.commit()
