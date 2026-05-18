# src/schema.py
"""
Definitii Pydantic pentru schema de date a unei facturi.

Aceste modele sunt folosite pentru:
    - validarea raspunsului JSON returnat de OpenAI;
    - normalizarea tipurilor (string, numeric);
    - garantarea ca toate campurile sunt prezente (chiar daca null) inainte
      de generarea XML-ului;
    - serializarea informatiilor de verificare a firmei (provenite din
      API-uri externe) ca parte a InvoiceData.

Toate campurile sunt optionale (Optional / None) pentru a permite
extragerea partiala atunci cand factura nu contine toate informatiile.
"""

from __future__ import annotations

import re
from typing import Annotated, Any, Dict, List, Optional

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


# =============================================================================
# Coercion validators — defensive parsing of LLM output
# =============================================================================
# Modelele locale (Llama 3.2 3B etc.) returneaza ocazional tipuri "ciudate"
# pentru campurile care lipsesc de pe factura: lista goala, dict gol,
# numar in loc de string, sau invers. Aceste helper-e converteaza orice
# input intr-un Optional[str] sau Optional[float] curat, ca Pydantic sa
# nu mai cada pe ValidationError.

def _to_opt_str(v: Any) -> Optional[str]:
    """Coerce arbitrary LLM output into Optional[str]."""
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        return s if s else None
    if isinstance(v, bool):
        # bool e subclasa de int in Python — evitam sa-l convertim la "True"/"False"
        return None
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        # Lista de candidati — luam string-urile non-goale si le concatenam.
        cleaned = [s for s in (_to_opt_str(x) for x in v) if s]
        if not cleaned:
            return None
        if len(cleaned) == 1:
            return cleaned[0]
        return " | ".join(cleaned)
    if isinstance(v, dict):
        # Dict cu o singura valoare scalara — luam prima valoare nenula.
        for val in v.values():
            s = _to_opt_str(val)
            if s:
                return s
        return None
    return str(v) if v else None


def _to_opt_float(v: Any) -> Optional[float]:
    """Coerce arbitrary LLM output into Optional[float]."""
    if v is None or v == "" or v == [] or v == {}:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        # Elimina simboluri monetare, spatii non-numerice etc.
        s = re.sub(r"[^\d.,\-]", "", s)
        if not s:
            return None
        # Format european: "1.234,56" -> "1234.56"
        if "," in s and "." in s:
            # ambele prezente: presupunem . = mii, , = zecimale
            if s.rfind(",") > s.rfind("."):
                s = s.replace(".", "").replace(",", ".")
            else:
                # dot e zecimal, virgula e mii
                s = s.replace(",", "")
        elif "," in s:
            # doar virgula: daca apare un singur "," urmat de 1-2 cifre
            # la sfarsit, e zecimal.
            parts = s.split(",")
            if len(parts) == 2 and 1 <= len(parts[1]) <= 2:
                s = s.replace(",", ".")
            else:
                s = s.replace(",", "")
        try:
            return float(s)
        except ValueError:
            return None
    if isinstance(v, list):
        for x in v:
            f = _to_opt_float(x)
            if f is not None:
                return f
        return None
    return None


# Tipuri reutilizabile, plug-and-play in field-uri:
OptStr = Annotated[Optional[str], BeforeValidator(_to_opt_str)]
OptFloat = Annotated[Optional[float], BeforeValidator(_to_opt_float)]


# =============================================================================
# Schema de baza a facturii
# =============================================================================
class Supplier(BaseModel):
    """Date despre furnizor (emitentul facturii)."""

    model_config = ConfigDict(extra="ignore")

    name: OptStr = Field(default=None, description="Denumirea furnizorului")
    tax_id: OptStr = Field(default=None, description="CUI / VAT ID")
    registration_number: OptStr = Field(
        default=None, description="Numar Registrul Comertului (J.../F...)"
    )
    address: OptStr = Field(default=None, description="Adresa completa")
    iban: OptStr = Field(default=None, description="Cont IBAN")
    bank: OptStr = Field(default=None, description="Denumirea bancii")


class Customer(BaseModel):
    """Date despre client (destinatarul facturii)."""

    model_config = ConfigDict(extra="ignore")

    name: OptStr = Field(default=None, description="Denumirea clientului")
    tax_id: OptStr = Field(default=None, description="CUI / VAT ID client")
    registration_number: OptStr = Field(
        default=None, description="Numar Registrul Comertului client"
    )
    address: OptStr = Field(default=None, description="Adresa client")


class InvoiceItem(BaseModel):
    """O linie de produs / serviciu din factura."""

    model_config = ConfigDict(extra="ignore")

    description: OptStr = Field(default=None, description="Denumirea produsului/serviciului")
    quantity: OptFloat = Field(default=None, description="Cantitate")
    unit_price: OptFloat = Field(default=None, description="Pret unitar net")
    vat_rate: OptFloat = Field(default=None, description="Cota TVA (%)")
    net_amount: OptFloat = Field(default=None, description="Valoare neta")
    vat_amount: OptFloat = Field(default=None, description="Valoare TVA")
    gross_amount: OptFloat = Field(default=None, description="Valoare bruta")


class Totals(BaseModel):
    """Totalurile facturii."""

    model_config = ConfigDict(extra="ignore")

    subtotal: OptFloat = Field(default=None, description="Subtotal (suma neta)")
    vat_total: OptFloat = Field(default=None, description="TVA total")
    grand_total: OptFloat = Field(default=None, description="Total general (cu TVA)")


# =============================================================================
# Modele pentru verificarea firmei (extensie API-uri externe)
# =============================================================================
class CompanyVerification(BaseModel):
    """
    Rezultatul verificarii firmei furnizoare prin API extern (OpenAPI.ro,
    ANAF, ListaFirme.ro).

    Acest model este folosit ATAT ca rezultat returnat de modulul de
    verificare, CAT si ca sub-document al InvoiceData (serializat in XML).
    Campul ``status`` codifica diagnosticul: 'verified', 'not_found',
    'not_configured', 'insufficient_data', 'error', 'disabled'.
    """

    model_config = ConfigDict(extra="ignore")

    verified: bool = Field(default=False, description="True daca firma a fost confirmata oficial")
    status: str = Field(default="not_attempted", description="Cod-stare al verificarii")
    source: Optional[str] = Field(default=None, description="Provider folosit (openapi, anaf, listafirme)")
    official_name: Optional[str] = Field(default=None)
    tax_id: Optional[str] = Field(default=None)
    registration_number: Optional[str] = Field(default=None)
    address: Optional[str] = Field(default=None)
    vat_status: Optional[str] = Field(default=None)
    company_status: Optional[str] = Field(default=None)
    caen_code: Optional[str] = Field(default=None)
    raw_response: Optional[Dict[str, Any]] = Field(default=None, description="JSON brut returnat de API")
    error: Optional[str] = Field(default=None)


class OnlineMention(BaseModel):
    """
    O singura referinta publica (rezultat de cautare web) despre firma.

    Tipul `mention_type` permite filtrarea / vizualizarea separata a
    site-ului oficial vs. retele sociale vs. presa. Valori uzuale:
    "website" (homepage, about, contact), "social" (LinkedIn, Facebook),
    "news" (presa, articole), "registry" (anaf.ro, listafirme.ro etc.),
    "other" (orice altceva).
    """

    model_config = ConfigDict(extra="ignore")

    title: Optional[str] = Field(default=None)
    url: Optional[str] = Field(default=None)
    snippet: Optional[str] = Field(default=None)
    source: Optional[str] = Field(default=None, description="Domeniul")
    published_date: Optional[str] = Field(default=None)
    mention_type: Optional[str] = Field(default="news")


class CompanyRiskAnalysis(BaseModel):
    """
    Indicator euristic de risc compus din statusul verificarii, comparatia
    cu factura si mentiunile online.

    NOTE: This is a heuristic academic risk indicator, not a legal or
    financial decision tool.
    """

    model_config = ConfigDict(extra="ignore")

    risk_score: int = Field(default=0, ge=0, le=100)
    risk_level: str = Field(default="low", description="low | medium | high")
    warnings: List[str] = Field(default_factory=list)


# =============================================================================
# Modelul radacina
# =============================================================================
class InvoiceData(BaseModel):
    """
    Modelul radacina al unei facturi extrase.

    Reflecta schema JSON impusa modelului OpenAI in prompt si include,
    ca extensie ulterioara, rezultatele verificarii externe a firmei
    (`company_verification`, `online_mentions`, `company_risk_analysis`).
    """

    model_config = ConfigDict(extra="ignore")

    invoice_number: OptStr = Field(default=None)
    invoice_date: OptStr = Field(default=None)
    due_date: OptStr = Field(default=None)
    currency: OptStr = Field(default=None)

    supplier: Supplier = Field(default_factory=Supplier)
    customer: Customer = Field(default_factory=Customer)
    items: List[InvoiceItem] = Field(default_factory=list)
    totals: Totals = Field(default_factory=Totals)

    # ---- Extensia de verificare: supplier (prestator) ----
    supplier_verification: Optional[CompanyVerification] = Field(default=None)
    supplier_online_mentions: Optional[List[OnlineMention]] = Field(default_factory=list)
    supplier_risk_analysis: Optional[CompanyRiskAnalysis] = Field(default=None)

    # ---- Extensia de verificare: customer (beneficiar) ----
    customer_verification: Optional[CompanyVerification] = Field(default=None)
    customer_online_mentions: Optional[List[OnlineMention]] = Field(default_factory=list)
    customer_risk_analysis: Optional[CompanyRiskAnalysis] = Field(default=None)
