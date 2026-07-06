from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from app.schemas.vcp_schema import VCPMilestone
from app.store.postgres_json_store import PostgresJsonStore


class VCPStore:
    """
    VCP milestone store, backed by Postgres (PostgresJsonStore).

    `path` is kept as the store's identity key (it was the JSON file path
    before this moved to Postgres) so every caller that already shares the
    same DEFAULT_STORE_PATH constant continues to read/write the same
    underlying document.
    """

    def __init__(
        self,
        path: str = "data/processed/synthetic_vcp_milestones_seed.json",
    ):
        self.path = Path(path)
        self._store = PostgresJsonStore("vcp_milestones")
        self._cache: Optional[List[VCPMilestone]] = None

    def exists(self) -> bool:
        return self._store.get(str(self.path)) is not None

    def load_all(self) -> List[VCPMilestone]:
        """Fetches the full milestones document once per instance and reuses it.

        Every callback (load_for_company/load_confirmed_for_company/company_ids/
        is_confirmed) goes through this, and callers like the portfolio route
        reuse one VCPStore instance across an entire company loop — caching here
        turns what used to be one Postgres round trip per call into one per
        instance (each round trip to Azure Postgres costs real network latency,
        so this matters a lot on hot paths iterating many companies).
        """
        if self._cache is not None:
            return self._cache

        doc = self._store.get(str(self.path))
        if not doc:
            self._cache = []
        else:
            self._cache = [VCPMilestone.from_dict(item) for item in doc.get("milestones", [])]

        return self._cache

    def load_for_company(self, company_id: str) -> List[VCPMilestone]:
        return [
            milestone
            for milestone in self.load_all()
            if milestone.company_id == company_id
        ]

    def load_confirmed_for_company(self, company_id: str) -> List[VCPMilestone]:
        return [
            milestone
            for milestone in self.load_for_company(company_id)
            if milestone.confirmed
        ]

    def is_confirmed(self, company_id: str) -> bool:
        milestones = self.load_for_company(company_id)

        if not milestones:
            return False

        return all(milestone.confirmed for milestone in milestones)

    def company_ids(self) -> List[str]:
        return sorted({milestone.company_id for milestone in self.load_all()})

    def summary(self) -> Dict:
        milestones = self.load_all()
        confirmed = [m for m in milestones if m.confirmed]
        by_company: Dict[str, int] = {}

        for milestone in milestones:
            by_company[milestone.company_id] = (
                by_company.get(milestone.company_id, 0) + 1
            )

        return {
            "path": str(self.path),
            "exists": self.exists(),
            "total_milestones": len(milestones),
            "confirmed_milestones": len(confirmed),
            "company_count": len(by_company),
            "milestones_by_company": by_company,
        }

    def save_all(
        self,
        milestones: List[VCPMilestone],
        output_path: Optional[str] = None,
    ) -> str:
        key = str(Path(output_path)) if output_path else str(self.path)
        self._store.put(key, {"milestones": [m.to_dict() for m in milestones]})
        if key == str(self.path):
            self._cache = None

        return key