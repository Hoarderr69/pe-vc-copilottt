"""
VCP Extraction Agent — the first true AI agent in the pipeline.

Reads an IC memo (unstructured prose) and extracts every forward-looking value
creation commitment as a typed, Pydantic-validated milestone, with a confidence
score and the exact source sentence. This replaces the hand-seeded milestone
JSON: the agent produces candidates, a human confirms them (HITL), and only then
do they become ground truth in the VCPStore.

Two execution modes:
  - "azure_openai": live GPT-4o structured-output call (requires Azure config).
  - "offline_heuristic": deterministic rule-based extraction over the synthetic
    memo phrasing, so the pipeline, schema, mapping and eval are runnable without
    credentials. Clearly labelled in the output so it is never mistaken for the LLM.

Why an LLM here (and not Python): IC memos are prose with arbitrary phrasing.
Rules break on any wording change. This is exactly where language understanding
earns its place — unlike the deterministic drift/IRR math, which stays in Python.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from app.llm import azure_openai
from app.schemas.vcp_schema import VCPMilestone

# Canonical metric keys the downstream drift node understands. The agent is asked
# to map each commitment onto one of these where possible, else "other".
KNOWN_METRICS = {
    "annual_revenue",
    "ebitda_margin",
    "net_debt_to_ebitda",
    "sga_ratio",
    "cro_hired",
    "reporting_cadence_upgrade_complete",
}

Category = Literal["financial", "operational", "organizational", "commercial"]
ValueUnit = Literal["currency", "ratio", "multiple", "boolean", "count", "none"]


class ExtractedMilestone(BaseModel):
    """One forward-looking commitment found in the memo."""

    initiative: str = Field(description="Short name for the commitment, e.g. 'Revenue growth plan'.")
    description: str = Field(description="One sentence describing what is committed.")
    metric: str = Field(description="Canonical metric key if it maps to one, else 'other'.")
    category: Category
    baseline_value: Optional[float] = Field(default=None, description="Starting value at close, normalized (% as decimal).")
    target_value: Optional[float] = Field(default=None, description="Target value, normalized: % as decimal (24%->0.24), currency as full number, multiple as the number (1.2x->1.2), boolean as 1.")
    value_unit: ValueUnit = "none"
    target_horizon_months: Optional[int] = Field(default=None, description="Months from deal close if expressed relatively ('Month 24'->24, 'within 90 days'->3).")
    explicit_target_date: Optional[str] = Field(default=None, description="ISO date if an explicit calendar date is stated, else null.")
    owner_role: Optional[str] = None
    confidence: float = Field(description="0..1 extraction confidence. Use <0.7 when the commitment is vague or its target/date is unstated.")
    source_text: str = Field(description="The exact sentence from the memo this was extracted from.")
    ambiguity_note: Optional[str] = Field(default=None, description="If confidence<0.7, why (e.g. 'no completion date given').")


class VCPExtraction(BaseModel):
    milestones: List[ExtractedMilestone]


class ExtractionResult(BaseModel):
    company_id: str
    company_name: str
    extraction_mode: str
    model: Optional[str] = None
    milestones: List[ExtractedMilestone]
    usage: Optional[dict] = None
    source_document: Optional[str] = None
    document_loader: Optional[str] = None


SYSTEM_PROMPT = """You are a private-equity investment analyst. You read Investment \
Committee (IC) memos and extract every forward-looking value-creation commitment \
the sponsor is making about the company after deal close.

Extract ONLY commitments/targets (things the company will achieve or do), not \
descriptions of the current state or generic context. For each commitment:

- Map `metric` to one of these canonical keys when it clearly fits, else "other":
  annual_revenue, ebitda_margin, net_debt_to_ebitda, sga_ratio, cro_hired,
  reporting_cadence_upgrade_complete.
- Normalize `target_value`/`baseline_value`: percentages as decimals (24% -> 0.24),
  currency as the full number (£35,800,000 -> 35800000), multiples as the number
  (1.2x -> 1.2), a 'do this' commitment as boolean 1. Set `value_unit` accordingly.
- For timing, set `target_horizon_months` when stated relative to close ("by Month 24"
  -> 24, "within 90 days of close" -> 3). Use `explicit_target_date` only for calendar dates.
- Set `confidence` honestly. Use < 0.7 when the target value or the deadline is vague,
  missing, or "to be confirmed", and explain in `ambiguity_note`.
- `source_text` must be the exact sentence the commitment came from.

Return every commitment you find, including soft or partially-specified ones."""


def _build_user_prompt(memo_text: str, company_name: str) -> str:
    return (
        f"Company: {company_name}\n\n"
        f"IC MEMO:\n\"\"\"\n{memo_text}\n\"\"\"\n\n"
        "Extract all forward-looking value-creation commitments as structured milestones."
    )


def extract_llm(memo_text: str, company_id: str, company_name: str) -> ExtractionResult:
    """Live Azure OpenAI GPT-4o structured-output extraction."""
    client = azure_openai.get_client()
    model = azure_openai.deployment_name()

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_prompt(memo_text, company_name)},
    ]

    # `.parse` returns a validated Pydantic object (structured outputs). Support
    # both the promoted and beta locations across openai SDK versions.
    parse_fn = getattr(client.chat.completions, "parse", None) or client.beta.chat.completions.parse
    completion = parse_fn(model=model, messages=messages, response_format=VCPExtraction, temperature=0)

    parsed = completion.choices[0].message.parsed
    usage = getattr(completion, "usage", None)
    return ExtractionResult(
        company_id=company_id,
        company_name=company_name,
        extraction_mode="azure_openai",
        model=model,
        milestones=parsed.milestones if parsed else [],
        usage=usage.model_dump() if usage else None,
    )


# ---------------------------------------------------------------------------
# Offline deterministic extractor (no credentials needed). Targets the synthetic
# memo phrasing. Labelled "offline_heuristic" so it is never confused with the LLM.
# ---------------------------------------------------------------------------

_NUM = r"[£$]?\s*([\d,]+(?:\.\d+)?)"


def _f(s: str) -> float:
    return float(s.replace(",", "").replace("£", "").replace("$", "").strip())


def extract_offline(memo_text: str, company_id: str, company_name: str) -> ExtractionResult:
    t = memo_text
    out: List[ExtractedMilestone] = []

    m = re.search(rf"annual revenue run-rate to approximately {_NUM}.*?run-rate of roughly {_NUM}", t, re.S)
    if m:
        out.append(ExtractedMilestone(
            initiative="Revenue growth plan", description="Grow annual revenue run-rate by Month 24.",
            metric="annual_revenue", category="financial",
            baseline_value=_f(m.group(2)), target_value=_f(m.group(1)), value_unit="currency",
            target_horizon_months=24, owner_role="Chief Revenue Officer", confidence=0.92,
            source_text=m.group(0).split(". ")[0].strip() + ".",
        ))

    m = re.search(rf"EBITDA margin improves from approximately {_NUM}%? at close to approximately {_NUM}%", t)
    if m:
        out.append(ExtractedMilestone(
            initiative="EBITDA margin expansion", description="Expand EBITDA margin by Month 24.",
            metric="ebitda_margin", category="financial",
            baseline_value=_f(m.group(1)) / 100, target_value=_f(m.group(2)) / 100, value_unit="ratio",
            target_horizon_months=24, owner_role="CFO", confidence=0.94, source_text=m.group(0).strip() + ".",
        ))

    m = re.search(rf"net debt to EBITDA to reduce from approximately {_NUM}x at close toward {_NUM}x", t)
    if m:
        out.append(ExtractedMilestone(
            initiative="Deleveraging plan", description="Reduce net debt / EBITDA by Month 24.",
            metric="net_debt_to_ebitda", category="financial",
            baseline_value=_f(m.group(1)), target_value=_f(m.group(2)), value_unit="multiple",
            target_horizon_months=24, owner_role="CFO", confidence=0.91, source_text=m.group(0).strip() + ".",
        ))

    if re.search(r"reduce SG&A intensity", t):
        src = re.search(r"The operating team should reduce SG&A intensity[^.]*\.", t)
        out.append(ExtractedMilestone(
            initiative="SG&A reduction", description="Reduce SG&A intensity toward the long-term target range.",
            metric="sga_ratio", category="operational", value_unit="none",
            target_horizon_months=12, owner_role="CFO", confidence=0.55,
            source_text=(src.group(0).strip() if src else "reduce SG&A intensity"),
            ambiguity_note="No explicit target SG&A ratio or hard deadline stated.",
        ))

    m = re.search(r"hire a Chief Revenue Officer within (\d+) days", t)
    if m:
        out.append(ExtractedMilestone(
            initiative="Chief Revenue Officer hire", description="Hire a CRO shortly after close.",
            metric="cro_hired", category="organizational", target_value=1, value_unit="boolean",
            target_horizon_months=max(1, round(int(m.group(1)) / 30)), owner_role="CEO", confidence=0.88,
            source_text=re.search(r"The company should hire a Chief Revenue Officer[^.]*\.", t).group(0).strip(),
        ))

    if re.search(r"improve monthly reporting cadence", t):
        src = re.search(r"There is also an expectation[^.]*\.", t)
        out.append(ExtractedMilestone(
            initiative="Monthly KPI reporting upgrade", description="Upgrade monthly reporting cadence / KPI pack.",
            metric="reporting_cadence_upgrade_complete", category="operational", target_value=1, value_unit="boolean",
            target_horizon_months=None, owner_role="CFO", confidence=0.62,
            source_text=(src.group(0).strip() if src else "improve monthly reporting cadence"),
            ambiguity_note="Completion date is explicitly 'still to be confirmed with management'.",
        ))

    return ExtractionResult(
        company_id=company_id, company_name=company_name,
        extraction_mode="offline_heuristic", model=None, milestones=out,
    )


def extract(memo_text: str, company_id: str, company_name: str, prefer_llm: bool = True) -> ExtractionResult:
    """Extract using GPT-4o when configured, else the offline heuristic fallback."""
    if prefer_llm and azure_openai.is_configured():
        return extract_llm(memo_text, company_id, company_name)
    return extract_offline(memo_text, company_id, company_name)


def extract_from_document(
    document_path: str,
    company_id: str,
    company_name: str,
    prefer_llm: bool = True,
) -> ExtractionResult:
    """Ingest a source document (PDF/DOCX/MD), then extract milestones.

    This is the production entrypoint: the agent's input is a document, not a string.
    Records which file and which loader (pymupdf4llm / docling / plaintext, or a
    pymupdf4llm+docling mix for scanned PDFs) produced the text.
    """
    from app.ingestion.document_loader import load_document_text

    loaded = load_document_text(document_path)
    result = extract(loaded.text, company_id, company_name, prefer_llm=prefer_llm)
    result.source_document = loaded.source_name
    result.document_loader = loaded.loader
    return result


# ---------------------------------------------------------------------------
# Mapping: extracted candidates -> VCPMilestone (unconfirmed, awaiting HITL)
# ---------------------------------------------------------------------------

def _horizon_to_date(close: date, horizon_months: int) -> str:
    """close + horizon months, snapped to end-of-month (matches the seed convention).

    e.g. close 2026-01, horizon 24 -> 2027-12-31; horizon 3 -> 2026-03-31.
    """
    total = close.year * 12 + (close.month - 1) + horizon_months
    first_of_next = date(total // 12, total % 12 + 1, 1)
    return (first_of_next - timedelta(days=1)).isoformat()


def to_vcp_milestones(
    result: ExtractionResult,
    deal_close_date: str = "2026-01-01",
) -> List[VCPMilestone]:
    close = date.fromisoformat(deal_close_date)
    milestones: List[VCPMilestone] = []

    for em in result.milestones:
        if em.explicit_target_date:
            target_date = em.explicit_target_date
        elif em.target_horizon_months is not None:
            target_date = _horizon_to_date(close, em.target_horizon_months)
        else:
            target_date = None

        milestones.append(VCPMilestone(
            company_id=result.company_id,
            company_name=result.company_name,
            initiative=em.initiative,
            metric=em.metric,
            target_value=em.target_value,
            target_date=target_date,
            category=em.category,
            owner_role=em.owner_role,
            baseline_value=em.baseline_value,
            confidence=em.confidence,
            source_document=result.source_document,
            source_text=em.source_text,
            confirmed=False,  # candidate — must pass HITL before it is ground truth
            metadata={
                "extraction_mode": result.extraction_mode,
                "model": result.model,
                "value_unit": em.value_unit,
                "target_horizon_months": em.target_horizon_months,
                "ambiguity_note": em.ambiguity_note,
                "document_loader": result.document_loader,
            },
        ))

    return milestones
