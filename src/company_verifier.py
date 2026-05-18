# src/company_verifier.py
"""
Company verification module — checks supplier identity against external
public registries.

Supported providers (selectable via COMPANY_API_PROVIDER):
    - "openapi"     : OpenAPI.ro (commercial)
    - "anaf"        : Romanian National Tax Agency public web service
    - "listafirme"  : ListaFirme.ro (commercial)

The module follows a graceful-degradation policy: any failure (no API key,
network error, HTTP error, malformed JSON) returns a structured result with
status='not_configured' / 'error' / 'not_found' instead of raising — so the
invoice processing pipeline can continue regardless.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

import requests

from .config import (
    ANAF_API_TOKEN,
    COMPANY_API_BASE_URL,
    COMPANY_API_KEY,
    COMPANY_API_PROVIDER,
    ENABLE_COMPANY_VERIFICATION,
)
from .schema import CompanyVerification


# Aliasul cerut explicit in specificatia disertatiei.
CompanyVerificationResult = CompanyVerification


# =============================================================================
# Helpers
# =============================================================================
def normalize_tax_id(tax_id: Optional[str]) -> str:
    """
    Normalize a Romanian tax ID for API queries.

    Removes whitespace and the optional ``RO`` prefix (commonly used for
    VAT-registered companies). Returns the canonical numeric portion.
    """
    if not tax_id:
        return ""
    cleaned = re.sub(r"\s+", "", str(tax_id).strip())
    # Strip an optional "RO" / "ro" prefix (case-insensitive). We pass
    # re.IGNORECASE explicitly because Python 3.14 disallows inline flags
    # in the middle of an expression.
    cleaned = re.sub(r"^RO", "", cleaned, flags=re.IGNORECASE)
    return cleaned


def _safe_get(d: Dict[str, Any], *keys: str) -> Optional[Any]:
    """Return the first non-empty value among ``keys`` from ``d``."""
    for k in keys:
        v = d.get(k) if isinstance(d, dict) else None
        if v not in (None, "", []):
            return v
    return None


# =============================================================================
# Provider dispatcher
# =============================================================================
def verify_company(
    company_name: Optional[str],
    tax_id: Optional[str],
) -> CompanyVerification:
    """
    Verify a company against the configured external provider.

    Returns a populated :class:`CompanyVerification` regardless of outcome —
    the ``status`` field carries the diagnostic.
    """
    if not ENABLE_COMPANY_VERIFICATION:
        return CompanyVerification(status="disabled")

    if not tax_id and not company_name:
        return CompanyVerification(status="insufficient_data")

    provider = (COMPANY_API_PROVIDER or "").strip().lower()

    # Dispatch to the primary provider — all backends are local / official
    # public APIs. No cloud LLM is used.
    if provider == "anaf":
        primary = verify_company_anaf(company_name, tax_id)
    elif provider == "vies":
        primary = verify_company_vies(company_name, tax_id)
    elif provider == "openapi":
        primary = verify_company_openapi(company_name, tax_id)
    elif provider == "listafirme":
        primary = verify_company_listafirme(company_name, tax_id)
    else:
        primary = CompanyVerification(
            status="not_configured",
            error=f"Unknown or empty provider: '{provider}'.",
        )

    # Auto-fallback chain: if the primary provider failed (network, WAF,
    # missing credentials), try VIES for any EU VAT, then ANAF for any
    # Romanian-shaped tax_id. All fallbacks are free public APIs.
    if primary.status in ("error", "not_configured", "not_found"):
        tid = normalize_tax_id(tax_id)
        # VIES for EU prefixes (RO, DE, FR, IT, ...) when provider isn't already VIES.
        if provider != "vies" and tid and tid_starts_with_eu_prefix(tax_id):
            vies = verify_company_vies(company_name, tax_id)
            if vies.verified:
                note = (
                    f"Primary '{provider}' returned {primary.status}; "
                    f"used VIES fallback."
                )
                vies.error = (vies.error + " | " if vies.error else "") + note
                return vies
        # ANAF for plain Romanian CUI when provider wasn't already ANAF.
        if provider != "anaf" and tid.isdigit():
            anaf = verify_company_anaf(company_name, tax_id)
            if anaf.verified:
                note = (
                    f"Primary '{provider}' returned {primary.status}; "
                    f"used ANAF fallback."
                )
                anaf.error = (anaf.error + " | " if anaf.error else "") + note
                return anaf

    return primary


# =============================================================================
# Helper: detect EU VAT prefix
# =============================================================================
EU_VAT_PREFIXES = (
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL", "GR", "ES",
    "FI", "FR", "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT", "NL",
    "PL", "PT", "RO", "SE", "SI", "SK", "XI",  # XI = Northern Ireland
)


def tid_starts_with_eu_prefix(tax_id: Optional[str]) -> bool:
    """Return True if `tax_id` starts with a known EU country prefix."""
    if not tax_id:
        return False
    upper = re.sub(r"\s+", "", str(tax_id).strip()).upper()
    return upper[:2] in EU_VAT_PREFIXES


# =============================================================================
# Provider: VIES (EU VAT validation)
# =============================================================================
def verify_company_vies(
    company_name: Optional[str],
    tax_id: Optional[str],
) -> CompanyVerification:
    """
    Validate a VAT number through VIES (the EU Commission's free service).

    Returns the trader name and address when available. VIES has no
    "company status" concept — it only returns valid/invalid for the VAT
    registration. So we map ``valid=True`` to ``company_status="ACTIVE"``
    and ``valid=False`` to ``"INACTIVE"``.

    Endpoint (REST, no key, no quota for reasonable usage):
        https://ec.europa.eu/taxation_customs/vies/rest-api/check-vat-number
    """
    if not tax_id:
        return CompanyVerification(
            status="insufficient_data", source="vies",
            error="VIES requires a VAT number.",
        )

    raw = re.sub(r"\s+", "", str(tax_id).strip()).upper()
    if len(raw) < 3 or raw[:2] not in EU_VAT_PREFIXES:
        return CompanyVerification(
            status="insufficient_data", source="vies",
            error=f"'{tax_id}' is not a recognizable EU VAT number.",
        )

    country_code = raw[:2]
    vat_number = raw[2:]

    url = "https://ec.europa.eu/taxation_customs/vies/rest-api/check-vat-number"
    payload = {"countryCode": country_code, "vatNumber": vat_number}

    try:
        resp = requests.post(
            url, json=payload, timeout=15,
            headers={"Content-Type": "application/json"},
        )
    except requests.RequestException as exc:
        return CompanyVerification(
            status="error", source="vies", error=str(exc),
        )

    if resp.status_code != 200:
        return CompanyVerification(
            status="error", source="vies",
            error=f"HTTP {resp.status_code}: {resp.text[:200]}",
        )

    try:
        data = resp.json()
    except ValueError:
        return CompanyVerification(
            status="error", source="vies",
            error="Invalid JSON in VIES response.",
        )

    valid = bool(data.get("valid"))
    name = (data.get("name") or "").strip() or None
    address = (data.get("address") or "").strip() or None

    return CompanyVerification(
        verified=valid,
        status="verified" if valid else "not_found",
        source="vies",
        official_name=name,
        tax_id=f"{country_code}{vat_number}",
        registration_number=None,
        address=address,
        vat_status="active" if valid else "inactive",
        company_status="ACTIVE" if valid else "INACTIVE",
        caen_code=None,
        raw_response=data,
    )


# =============================================================================
# Provider: OpenAPI.ro
# =============================================================================
def verify_company_openapi(
    company_name: Optional[str],
    tax_id: Optional[str],
) -> CompanyVerification:
    """
    Verify via OpenAPI.ro.

    NOTE: the exact endpoint depends on the user's plan. Adjust the path
    and the auth header below to match the documentation of your account.
    Common authentication patterns: ``x-api-key`` header or Bearer token.
    """
    if not COMPANY_API_KEY:
        return CompanyVerification(
            status="not_configured",
            source="openapi",
            error="COMPANY_API_KEY missing in environment.",
        )

    cif = normalize_tax_id(tax_id)
    if not cif:
        return CompanyVerification(
            status="insufficient_data",
            source="openapi",
            error="No tax_id available; OpenAPI lookup requires a CIF.",
        )

    base = (COMPANY_API_BASE_URL or "https://api.openapi.ro").rstrip("/")
    # Example endpoint shape — adjust to your subscription:
    url = f"{base}/v1/companies/{cif}"

    headers = {
        "x-api-key": COMPANY_API_KEY,
        # Some plans require Bearer instead. Switch if your account needs it:
        # "Authorization": f"Bearer {COMPANY_API_KEY}",
        "Accept": "application/json",
        "User-Agent": "SAGABridge/1.0 (academic)",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=10)
    except requests.RequestException as exc:
        return CompanyVerification(
            status="error", source="openapi", error=str(exc),
        )

    if resp.status_code == 404:
        return CompanyVerification(
            status="not_found", source="openapi", tax_id=cif,
        )
    if resp.status_code != 200:
        return CompanyVerification(
            status="error", source="openapi",
            error=f"HTTP {resp.status_code}: {resp.text[:200]}",
        )

    try:
        data = resp.json()
    except ValueError:
        return CompanyVerification(
            status="error", source="openapi",
            error="Invalid JSON in API response.",
        )

    # Map common OpenAPI.ro field names — fall back through aliases.
    return CompanyVerification(
        verified=True,
        status="verified",
        source="openapi.ro",
        official_name=_safe_get(data, "denumire", "nume", "name"),
        tax_id=str(_safe_get(data, "cif", "cui") or cif),
        registration_number=_safe_get(
            data, "nrRegCom", "registration_number", "regCom",
        ),
        address=_safe_get(data, "adresa", "address"),
        vat_status=(
            "active"
            if _safe_get(data, "scpTVA", "plafonTVA", "vat_active")
            else "inactive"
        ),
        company_status=_safe_get(data, "stare", "status", "stare_inregistrare"),
        caen_code=_safe_get(data, "cod_CAEN", "caen", "caenCode"),
        raw_response=data if isinstance(data, dict) else None,
    )


# =============================================================================
# Provider: ANAF (Romanian National Tax Agency)
# =============================================================================
def verify_company_anaf(
    company_name: Optional[str],
    tax_id: Optional[str],
) -> CompanyVerification:
    """
    Verify via the public ANAF web service (PlatitorTvaRest).

    The public endpoint does not strictly require a token, but the spec
    allows protected variants for higher rate limits. If ``ANAF_API_TOKEN``
    is configured, it is sent as a Bearer header.
    """
    cif = normalize_tax_id(tax_id)
    if not cif:
        return CompanyVerification(
            status="insufficient_data", source="anaf",
            error="No tax_id available.",
        )

    # ANAF v9 endpoint (current as of 2025). Note the path: `/api/` prefix,
    # then `PlatitorTvaRest/v9/tva` — the `/ws/` segment from older docs is
    # NOT used in v9.
    url = "https://webservicesp.anaf.ro/api/PlatitorTvaRest/v9/tva"
    from datetime import date
    payload = [{"cui": int(cif), "data": date.today().isoformat()}]
    headers = {
        "Content-Type": "application/json; charset=UTF-8",
        "Accept": "application/json",
        "User-Agent": "SAGABridge/1.0 (academic; UPB FAIMA)",
    }
    if ANAF_API_TOKEN:
        headers["Authorization"] = f"Bearer {ANAF_API_TOKEN}"

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
    except requests.RequestException as exc:
        return CompanyVerification(
            status="error", source="anaf", error=str(exc),
        )

    if resp.status_code != 200:
        return CompanyVerification(
            status="error", source="anaf",
            error=f"HTTP {resp.status_code}: {resp.text[:200]}",
        )

    # ANAF's WAF returns HTML "Request Rejected" pages with HTTP 200 when
    # the request fingerprint looks bot-like. Detect that explicitly so the
    # error surfaced in the UI is human-readable instead of a JSON parse error.
    text_preview = resp.text.lstrip()[:50].lower()
    if text_preview.startswith("<") or "request rejected" in text_preview:
        return CompanyVerification(
            status="error", source="anaf",
            error=(
                "ANAF blocked the request (WAF / firewall). This sometimes "
                "happens for non-Romanian IP addresses or sandboxed networks. "
                "Try again from a residential Romanian connection, or switch "
                "to COMPANY_API_PROVIDER=openai for an LLM-based fallback."
            ),
        )

    try:
        data = resp.json()
    except ValueError:
        return CompanyVerification(
            status="error", source="anaf",
            error="Invalid JSON in ANAF response.",
        )

    found = data.get("found") if isinstance(data, dict) else None
    if not found:
        return CompanyVerification(
            status="not_found", source="anaf", tax_id=cif,
        )

    company = found[0]
    info = company.get("date_generale", {}) or {}
    vat_info = company.get("inregistrare_scop_Tva", {}) or {}

    return CompanyVerification(
        verified=True,
        status="verified",
        source="anaf",
        official_name=info.get("denumire"),
        tax_id=str(info.get("cui") or cif),
        registration_number=info.get("nrRegCom"),
        address=info.get("adresa"),
        vat_status=("active" if vat_info.get("scpTVA") else "inactive"),
        company_status=info.get("stare_inregistrare"),
        caen_code=info.get("cod_CAEN"),
        raw_response=company,
    )


# =============================================================================
# Provider: ListaFirme.ro
# =============================================================================
def verify_company_listafirme(
    company_name: Optional[str],
    tax_id: Optional[str],
) -> CompanyVerification:
    """Verify via ListaFirme.ro JSON API. Requires COMPANY_API_KEY."""
    if not COMPANY_API_KEY:
        return CompanyVerification(
            status="not_configured", source="listafirme",
            error="COMPANY_API_KEY missing.",
        )

    cif = normalize_tax_id(tax_id)
    if not cif:
        return CompanyVerification(
            status="insufficient_data", source="listafirme",
        )

    base = (COMPANY_API_BASE_URL or "https://www.listafirme.ro/api").rstrip("/")
    url = f"{base}/info-firma.asp"
    params = {"cui": cif, "key": COMPANY_API_KEY}

    try:
        resp = requests.get(url, params=params, timeout=10)
    except requests.RequestException as exc:
        return CompanyVerification(
            status="error", source="listafirme", error=str(exc),
        )

    if resp.status_code != 200:
        return CompanyVerification(
            status="error", source="listafirme",
            error=f"HTTP {resp.status_code}",
        )

    try:
        data = resp.json()
    except ValueError:
        return CompanyVerification(
            status="error", source="listafirme",
            error="Invalid JSON response.",
        )

    if not data or not _safe_get(data, "Nume", "name", "denumire"):
        return CompanyVerification(
            status="not_found", source="listafirme", tax_id=cif,
        )

    return CompanyVerification(
        verified=True,
        status="verified",
        source="listafirme.ro",
        official_name=_safe_get(data, "Nume", "name"),
        tax_id=str(_safe_get(data, "CIF", "cif") or cif),
        registration_number=_safe_get(data, "RegCom", "regcom"),
        address=_safe_get(data, "Adresa", "address"),
        vat_status=str(_safe_get(data, "Tva", "vat") or ""),
        company_status=_safe_get(data, "Stare", "status"),
        caen_code=_safe_get(data, "CodCAEN", "caen"),
        raw_response=data,
    )


# =============================================================================
# Comparison helpers
# =============================================================================
def _slug(text: str) -> str:
    """Lowercase + alphanumeric-only, for loose name matching."""
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def compare_invoice_supplier_with_verified_data(
    invoice_supplier: dict | object,
    verification_result: CompanyVerification,
) -> Dict[str, Any]:
    """
    Compare invoice supplier fields with the verified registry data.

    Returns a dict with name_match / tax_id_match / address_match (all
    True/False/None) and a list of human-readable warnings explaining any
    mismatch.
    """
    out: Dict[str, Any] = {
        "name_match": None,
        "tax_id_match": None,
        "address_match": None,
        "warnings": [],
    }

    if not verification_result or not verification_result.verified:
        return out

    # Accept both dict and Pydantic model for invoice_supplier.
    if hasattr(invoice_supplier, "model_dump"):
        sup = invoice_supplier.model_dump()
    elif isinstance(invoice_supplier, dict):
        sup = invoice_supplier
    else:
        sup = {}

    inv_name = (sup.get("name") or "").strip()
    inv_tax = normalize_tax_id(sup.get("tax_id") or "")
    inv_addr = (sup.get("address") or "").strip()

    # ---- name match (loose, alphanumeric-only) ----
    if inv_name and verification_result.official_name:
        a = _slug(inv_name)
        b = _slug(verification_result.official_name)
        out["name_match"] = bool(a) and (a == b or a in b or b in a)
        if not out["name_match"]:
            out["warnings"].append(
                f"Supplier name on invoice ('{inv_name}') differs from "
                f"official record ('{verification_result.official_name}')."
            )

    # ---- tax_id match (exact, after normalization) ----
    if inv_tax and verification_result.tax_id:
        v_tax = normalize_tax_id(verification_result.tax_id)
        out["tax_id_match"] = inv_tax == v_tax
        if not out["tax_id_match"]:
            out["warnings"].append(
                f"Tax ID mismatch: invoice='{inv_tax}', registry='{v_tax}'."
            )

    # ---- address match (token overlap >= 1/3) ----
    if inv_addr and verification_result.address:
        a_tokens = set(re.findall(r"\w{3,}", inv_addr.lower()))
        b_tokens = set(re.findall(r"\w{3,}", verification_result.address.lower()))
        if a_tokens and b_tokens:
            overlap = len(a_tokens & b_tokens)
            threshold = max(1, min(len(a_tokens), len(b_tokens)) // 3)
            out["address_match"] = overlap >= threshold

    return out
