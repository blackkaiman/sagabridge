# src/company_risk_analyzer.py
"""
Heuristic risk analyzer for an invoice supplier.

NOTE: This is a heuristic academic risk indicator, not a legal or
financial decision tool.

The score is built additively from four signals:
    1. external verification status     (unverified company => +30)
    2. legal status of the company      (inactive/radiat/suspendat => +50)
    3. cross-check against the invoice  (tax_id mismatch +40, name mismatch +20)
    4. negative keywords in online news (+10 per article that contains
       any term from a curated Romanian/English negative-vocabulary list)

The final score is capped at 100 and bucketed:
    0-30  -> low
    31-65 -> medium
    66-100 -> high
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .company_news_search import CompanyNewsSearchResult
from .schema import CompanyRiskAnalysis, CompanyVerification


# -----------------------------------------------------------------------------
# Vocabularul de risc
# -----------------------------------------------------------------------------
NEGATIVE_TERMS = (
    "insolvență", "insolventa", "insolvent",
    "faliment",
    "dosar penal", "dosar",
    "anchetă", "ancheta",
    "fraudă", "frauda",
    "proces", "procese",
    "executare silită", "executare silita", "executare",
    "datorii", "datorie",
    # English equivalents commonly found in Romanian press articles
    "bankruptcy", "fraud", "lawsuit", "investigation",
)

INACTIVE_STATUS_TERMS = (
    "inactiv", "inactive",
    "radiat", "radiata", "radiată",
    "suspendat", "suspendata", "suspendată",
    "dizolvat", "dizolvata", "dizolvată",
    "lichidare", "in lichidare",
    "faliment",
)

# Praguri pentru bucketizarea scorului in low/medium/high.
LOW_THRESHOLD = 30
MEDIUM_THRESHOLD = 65


def _detect_inactive(company_status: Optional[str]) -> bool:
    """Detect any term that suggests the company is no longer active."""
    if not company_status:
        return False
    s = company_status.lower()
    return any(term in s for term in INACTIVE_STATUS_TERMS)


def _scan_negative_mentions(news_result: Optional[CompanyNewsSearchResult]) -> List[str]:
    """
    Inspect the title/snippet of each mention for negative keywords.

    Returns a list of human-readable warning strings (one per article that
    contains at least one keyword). Does NOT exceed +10 per article.
    """
    warnings: List[str] = []
    if not news_result or not news_result.searched:
        return warnings

    for mention in news_result.mentions or []:
        text = " ".join(
            t for t in (mention.title or "", mention.snippet or "") if t
        ).lower()
        for term in NEGATIVE_TERMS:
            if term in text:
                warnings.append(
                    f"Negative keyword '{term}' in: "
                    f"{mention.title or '(untitled)'} "
                    f"[{mention.source or 'unknown source'}]"
                )
                break  # one penalty per article

    return warnings


def analyze_company_risk(
    verification_result: Optional[CompanyVerification],
    comparison_result: Optional[Dict[str, Any]],
    news_result: Optional[CompanyNewsSearchResult],
) -> CompanyRiskAnalysis:
    """
    Compute a 0-100 heuristic risk score and bucketize into low/medium/high.

    All inputs may be ``None`` — missing inputs are treated as
    "not performed" (no additional penalty beyond +30 for non-verification).
    """
    score: int = 0
    warnings: List[str] = []

    # ---- 1) Verification status ----
    if verification_result is None or not verification_result.verified:
        v_status = (verification_result.status if verification_result else "missing")
        if v_status in ("not_configured", "disabled", "insufficient_data"):
            warnings.append(
                f"Company verification was not performed (status: {v_status})."
            )
        else:
            score += 30
            warnings.append(
                f"Company could not be verified (status: {v_status})."
            )

    # ---- 2) Legal status of the company (only if we have data) ----
    if verification_result and verification_result.verified:
        if _detect_inactive(verification_result.company_status):
            score += 50
            warnings.append(
                f"Company status indicates inactivity / liquidation: "
                f"'{verification_result.company_status}'."
            )

    # ---- 3) Cross-check vs. invoice ----
    if comparison_result:
        if comparison_result.get("tax_id_match") is False:
            score += 40
            warnings.append(
                "Tax ID on the invoice does NOT match the official record."
            )
        if comparison_result.get("name_match") is False:
            score += 20
            warnings.append(
                "Supplier name on the invoice does NOT match the official record."
            )
        # Address mismatch is informative only (no penalty), to avoid
        # punishing minor format variations.
        if comparison_result.get("address_match") is False:
            warnings.append(
                "Supplier address on the invoice differs from the official record."
            )

    # ---- 4) Negative news mentions ----
    neg_warnings = _scan_negative_mentions(news_result)
    score += 10 * len(neg_warnings)
    warnings.extend(neg_warnings)

    # ---- Cap & bucketize ----
    score = max(0, min(score, 100))
    if score <= LOW_THRESHOLD:
        level = "low"
    elif score <= MEDIUM_THRESHOLD:
        level = "medium"
    else:
        level = "high"

    return CompanyRiskAnalysis(
        risk_score=score,
        risk_level=level,
        warnings=warnings,
    )
