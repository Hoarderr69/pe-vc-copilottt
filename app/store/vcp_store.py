from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from app.schemas.vcp_schema import VCPMilestone


class VCPStore:
    """
    Lightweight JSON-backed VCP store for prototype.

    In production, this becomes Postgres.
    For now, it reads/writes confirmed VCP milestones from JSON.
    """

    def __init__(
        self,
        path: str = "data/processed/synthetic_vcp_milestones_seed.json",
    ):
        self.path = Path(path)

    def exists(self) -> bool:
        return self.path.exists()

    def load_all(self) -> List[VCPMilestone]:
        if not self.path.exists():
            return []

        with open(self.path, "r", encoding="utf-8") as f:
            payload = json.load(f)

        return [VCPMilestone.from_dict(item) for item in payload]

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
        save_path = Path(output_path) if output_path else self.path
        save_path.parent.mkdir(parents=True, exist_ok=True)

        payload = [milestone.to_dict() for milestone in milestones]

        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)

        return str(save_path)