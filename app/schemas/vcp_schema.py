from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional


@dataclass
class VCPMilestone:
    """
    A confirmed value creation commitment extracted from the IC memo / VCP.

    This is the ground-truth object used by the monitoring graph.
    """

    company_id: str
    company_name: str
    initiative: str
    metric: str
    target_value: Any
    target_date: Optional[str]

    category: str = "financial"
    owner_role: Optional[str] = None
    baseline_value: Any = None
    confidence: float = 0.0
    source_document: Optional[str] = None
    source_text: Optional[str] = None
    confirmed: bool = True
    version: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "VCPMilestone":
        allowed = {
            "company_id",
            "company_name",
            "initiative",
            "metric",
            "target_value",
            "target_date",
            "category",
            "owner_role",
            "baseline_value",
            "confidence",
            "source_document",
            "source_text",
            "confirmed",
            "version",
            "metadata",
        }

        clean_payload = {k: v for k, v in payload.items() if k in allowed}

        if "confirmed" not in clean_payload:
            clean_payload["confirmed"] = True

        if "version" not in clean_payload:
            clean_payload["version"] = 1

        if "metadata" not in clean_payload or clean_payload["metadata"] is None:
            clean_payload["metadata"] = {}

        return cls(**clean_payload)