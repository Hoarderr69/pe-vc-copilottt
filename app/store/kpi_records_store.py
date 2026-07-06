"""
KPI records store — normalized per-company financial records, backed by Postgres
(PostgresJsonStore). Mirrors app.store.vcp_store.VCPStore: every caller (routes,
graph nodes, analytics) already shares the ``kpi_records_path(company_id)``
convention from app.workflows.vcp_confirmation as the document's identity key,
whether they pass it as an absolute or repo-relative path string.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from app.store.postgres_json_store import PostgresJsonStore

PROJECT_ROOT = Path(__file__).resolve().parents[2]

_store = PostgresJsonStore("kpi_records")


def _normalize_key(path: str) -> str:
    """Collapse an absolute path back to its repo-relative form so a caller
    passing PROJECT_ROOT / "data/processed/x.json" and a caller passing the
    bare relative string land on the same Postgres document."""
    p = Path(path)
    if p.is_absolute():
        try:
            p = p.relative_to(PROJECT_ROOT)
        except ValueError:
            pass
    return p.as_posix()


def load_kpi_records(path: str) -> List[Dict[str, Any]]:
    doc = _store.get(_normalize_key(path))
    if not doc:
        return []
    return doc.get("records", [])


def save_kpi_records(path: str, records: List[Dict[str, Any]]) -> None:
    _store.put(_normalize_key(path), {"records": records})
