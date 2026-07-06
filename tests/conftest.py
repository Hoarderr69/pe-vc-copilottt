from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv

load_dotenv()

_COMPANY_META_COLLECTION = "company_meta"


@pytest.fixture(autouse=True, scope="session")
def _cleanup_company_meta_rows():
    """tests/test_sector_refactor.py writes to the shared Postgres-backed
    company_meta collection using tmp_path-derived keys (for isolation from real
    company rows). Those keys are unique per test run and nothing else deletes
    them, so the collection grows by a couple of rows every run. Snapshot the
    ids present before the session and delete anything new afterward.
    """
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        yield
        return

    import psycopg

    def _ids() -> set[str]:
        with psycopg.connect(database_url) as conn:
            rows = conn.execute(
                "SELECT id FROM app_documents WHERE collection = %s",
                (_COMPANY_META_COLLECTION,),
            ).fetchall()
        return {row[0] for row in rows}

    before = _ids()
    yield
    new_ids = _ids() - before
    print("DEBUG before", before, "after", _ids(), "new_ids", new_ids)
    if new_ids:
        with psycopg.connect(database_url) as conn:
            conn.cursor().executemany(
                "DELETE FROM app_documents WHERE collection = %s AND id = %s",
                [(_COMPANY_META_COLLECTION, id_) for id_ in new_ids],
            )
            conn.commit()
