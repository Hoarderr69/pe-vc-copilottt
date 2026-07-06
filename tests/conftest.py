from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv

load_dotenv()

_CLEANUP_COLLECTIONS = ["company_meta", "kpi_records"]


@pytest.fixture(autouse=True, scope="session")
def _cleanup_test_rows():
    """tests/test_sector_refactor.py writes to the shared Postgres-backed
    company_meta and kpi_records collections using tmp_path-derived keys (for
    isolation from real company/KPI rows). Those keys are unique per test run
    and nothing else deletes them, so the collections grow by a couple of rows
    every run. Snapshot the ids present before the session and delete anything
    new afterward.
    """
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        yield
        return

    import psycopg

    def _ids(collection: str) -> set[str]:
        with psycopg.connect(database_url) as conn:
            rows = conn.execute(
                "SELECT id FROM app_documents WHERE collection = %s",
                (collection,),
            ).fetchall()
        return {row[0] for row in rows}

    before = {collection: _ids(collection) for collection in _CLEANUP_COLLECTIONS}
    yield
    with psycopg.connect(database_url) as conn:
        for collection in _CLEANUP_COLLECTIONS:
            new_ids = _ids(collection) - before[collection]
            if new_ids:
                conn.cursor().executemany(
                    "DELETE FROM app_documents WHERE collection = %s AND id = %s",
                    [(collection, id_) for id_ in new_ids],
                )
        conn.commit()
