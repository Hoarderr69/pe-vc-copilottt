"""
Portfolio memo store — the board-ready markdown memo, backed by Postgres
(PostgresJsonStore). One document for the whole portfolio, keyed by the
former flat-file path so it slots into the same "app_documents" table as
every other store.
"""

from __future__ import annotations

from typing import Optional

from app.store.postgres_json_store import PostgresJsonStore

_DOC_ID = "data/processed/portfolio_memo.md"

_store = PostgresJsonStore("portfolio_memo")


def load_portfolio_memo() -> Optional[str]:
    doc = _store.get(_DOC_ID)
    return doc.get("markdown") if doc else None


def save_portfolio_memo(markdown: str) -> None:
    _store.put(_DOC_ID, {"markdown": markdown})
