# src/local_extractor.py
"""
Local invoice extraction — replaces the OpenAI-based extractor with a
fully on-device pipeline:

    1. PyMuPDF (already used)         — text extraction from digital PDFs
    2. Tesseract OCR (`pytesseract`)  — text extraction from scanned PDFs
    3. Ollama (local LLM)             — structuring raw text into JSON

No data leaves the user's machine. This is the privacy-first / GDPR
friendly pathway for the dissertation.

Prerequisites (one-time setup on macOS):
    brew install tesseract tesseract-lang ollama
    ollama pull llama3.2:3b     # ~2 GB, one-time download
    ollama serve                # starts background server on port 11434
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import ollama
import pytesseract
from PIL import Image

from .config import OLLAMA_HOST, OLLAMA_MODEL, TESSERACT_LANG
from .utils import parse_json_safe


# =============================================================================
# Constants
# =============================================================================

# Schema impusa modelului local. Aceeasi structura ca la varianta OpenAI,
# pentru ca restul pipeline-ului (validare Pydantic, generare XML) sa nu
# se schimbe deloc.
# =============================================================================
# JSON Schema impusa de Ollama la tokenizer level (mecanism structured output)
# =============================================================================
# Toate campurile numerice sunt declarate ca "string" — modelul NU POATE FIZIC
# sa returneze "29.5" cand factura zice "29.500". E mai puternic decat orice
# instructiune in prompt.

def _opt_str() -> dict:
    return {"type": ["string", "null"]}

_INVOICE_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "invoice_number": _opt_str(),
        "invoice_date": _opt_str(),
        "due_date": _opt_str(),
        "currency": _opt_str(),
        "supplier": {
            "type": "object",
            "properties": {
                "name": _opt_str(),
                "tax_id": _opt_str(),
                "registration_number": _opt_str(),
                "address": _opt_str(),
                "iban": _opt_str(),
                "bank": _opt_str(),
            },
        },
        "customer": {
            "type": "object",
            "properties": {
                "name": _opt_str(),
                "tax_id": _opt_str(),
                "registration_number": _opt_str(),
                "address": _opt_str(),
            },
        },
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "description": _opt_str(),
                    # ATENTIE: numerice ca STRING — schema forteaza asta.
                    "quantity": _opt_str(),
                    "unit_price": _opt_str(),
                    "vat_rate": _opt_str(),
                    "net_amount": _opt_str(),
                    "vat_amount": _opt_str(),
                    "gross_amount": _opt_str(),
                },
            },
        },
        "totals": {
            "type": "object",
            "properties": {
                # Si totalurile la fel — string in JSON, parsate ulterior.
                "subtotal": _opt_str(),
                "vat_total": _opt_str(),
                "grand_total": _opt_str(),
            },
        },
    },
    "required": ["supplier", "customer", "items", "totals"],
}


JSON_SCHEMA_DESCRIPTION = """\
Return STRICTLY a JSON object with EXACTLY this structure. Use null where
the field is missing or illegible. Do NOT invent data.

CRITICAL — NUMERIC FIELDS MUST BE RETURNED AS STRINGS:
All numeric fields (quantity, unit_price, vat_rate, net_amount, vat_amount,
gross_amount, subtotal, vat_total, grand_total) must be returned as STRINGS
that preserve the EXACT formatting from the invoice text (including dots,
commas, and spaces). DO NOT pre-convert numbers to JSON numbers — a downstream
parser handles the Romanian-vs-English format detection.

ROMANIAN NUMBER FORMAT (essential context):
  - Decimal separator: COMMA  ","   ("29,50" means 29.50)
  - Thousand separator: DOT  "."   or SPACE  " "
  - Examples of literal invoice text:
      "29,50"       =  29.50          (decimal, twenty-nine point fifty)
      "29.500"      =  29,500         (thousand, twenty-nine thousand five hundred)
      "29.500,75"   =  29,500.75
      "1.500.000"   =  1,500,000      (one million five hundred thousand)
      "1 500 000"   =  1,500,000      (same value, space separator)

When you see a number like "29.500" in a Romanian invoice context, it is
ALMOST ALWAYS twenty-nine thousand five hundred, NOT twenty-nine point five.
Copy the number AS A STRING exactly as written; do not normalize it.

ROMANIAN INVOICE FIELD LABELS (CRITICAL — map these labels to JSON fields):

  Label on invoice                          -> JSON field
  ─────────────────────────────────────────────────────────
  "Vânzător:" / "Furnizor:" / "Emitent:"   -> supplier
  "Cumpărător:" / "Client:" / "Beneficiar:" -> customer
  "CIF:" / "CUI:" / "Cod Fiscal:"           -> tax_id (e.g., "43964751" or "RO37082832")
  "Nr. ord. reg. com." / "RegCom" / "J.../F.../C..."  -> registration_number
  "Adresă:" / "Adresa:" / "Sediu:"          -> address
  "IBAN:" / "Cont:" / "Cont bancar:"        -> iban
  "Banca:" / "Bancă:"                       -> bank
  "Seria și numărul" / "Nr. factură" / "Factura"      -> invoice_number
  "Data facturii" / "Data emiterii"         -> invoice_date
  "Termen de plată" / "Data scadenței"      -> due_date
  "U.M." / "buc" / "kg" / "ore"             -> (part of items)
  "Cantitate" / "Cant."                     -> items[].quantity
  "Preț unitar" / "Pret unitar"             -> items[].unit_price
  "Valoare" / "Valoare Totală"              -> items[].net_amount or gross_amount
  "TVA"                                     -> items[].vat_amount or totals.vat_total
  "Total"                                   -> totals.grand_total

CRITICAL: The CIF / CUI is ALWAYS a string of digits (sometimes prefixed with
"RO"). When you see "CIF: 43964751" or "CUI: RO37082832", extract that number
as the tax_id. Do NOT skip this field — it is the most important identifier
for the company.

Schema:
{
  "invoice_number": "string|null",
  "invoice_date": "string|null",
  "due_date": "string|null",
  "currency": "string|null",
  "supplier": {
    "name": "string|null",
    "tax_id": "string|null",
    "registration_number": "string|null",
    "address": "string|null",
    "iban": "string|null",
    "bank": "string|null"
  },
  "customer": {
    "name": "string|null",
    "tax_id": "string|null",
    "registration_number": "string|null",
    "address": "string|null"
  },
  "items": [
    {
      "description": "string|null",
      "quantity": "string|null      (exact text from invoice, e.g. \\"2\\" or \\"1,5\\")",
      "unit_price": "string|null    (exact text from invoice, e.g. \\"29.500\\")",
      "vat_rate": "string|null      (exact text from invoice, e.g. \\"19\\" or \\"19%\\")",
      "net_amount": "string|null    (exact text from invoice)",
      "vat_amount": "string|null    (exact text from invoice)",
      "gross_amount": "string|null  (exact text from invoice)"
    }
  ],
  "totals": {
    "subtotal": "string|null      (exact text from invoice)",
    "vat_total": "string|null     (exact text from invoice)",
    "grand_total": "string|null   (exact text from invoice)"
  }
}
"""

SYSTEM_PROMPT = (
    "You are an expert in extracting structured data from Romanian and "
    "international invoices. Extract only information ACTUALLY present in "
    "the invoice — do NOT infer or invent. Use null for missing fields.\n\n"
    "ROMANIAN INVOICE TERMS (must recognize):\n"
    "  - 'CIF', 'CUI', 'Cod Fiscal' -> tax_id (e.g., \"43964751\", \"RO37082832\")\n"
    "  - 'Vânzător' / 'Furnizor' -> supplier\n"
    "  - 'Cumpărător' / 'Client' / 'Beneficiar' -> customer\n"
    "  - 'Nr. ord. reg. com.' / 'RegCom' -> registration_number\n"
    "  - 'IBAN' / 'Cont' -> iban\n"
    "  - 'Banca' / 'Bancă' -> bank\n"
    "  - 'Adresă' / 'Adresa' / 'Sediu' -> address\n\n"
    "ALWAYS extract tax_id when CIF / CUI / Cod Fiscal is present on the "
    "invoice. It is a numeric identifier (with optional RO prefix). Look "
    "carefully for these labels for BOTH supplier and customer sections.\n\n"
    "IMPORTANT: return ALL numeric fields (quantity, prices, amounts, "
    "totals) as STRINGS preserving the EXACT text from the invoice "
    "(including dots, commas, spaces). Do not convert numbers yourself — a "
    "downstream parser will interpret the Romanian number format. For "
    "example, if the invoice shows \"29.500\", return the STRING \"29.500\" "
    "(not the number 29.5)."
)


# =============================================================================
# Tesseract OCR
# =============================================================================
def extract_text_from_images(image_paths: List[Union[str, Path]]) -> str:
    """
    Run Tesseract OCR on one or more rendered PDF pages.

    Uses Romanian + English language packs by default. The result strings
    are concatenated with a page separator so the local LLM can reason over
    the full document.
    """
    if not image_paths:
        return ""

    page_texts: List[str] = []
    for idx, path in enumerate(image_paths, start=1):
        try:
            image = Image.open(path)
            # Tesseract reads the image and returns plain text.
            text = pytesseract.image_to_string(image, lang=TESSERACT_LANG)
        except Exception as exc:  # noqa: BLE001
            page_texts.append(f"[OCR error on page {idx}: {exc}]")
            continue
        page_texts.append(f"--- Page {idx} ---\n{text}")
    return "\n\n".join(page_texts).strip()


# =============================================================================
# Ollama (local LLM) — text structuring
# =============================================================================
def _ollama_client() -> ollama.Client:
    """Build an Ollama client pointing at the configured host."""
    return ollama.Client(host=OLLAMA_HOST)


def _run_ollama(prompt: str) -> str:
    """
    Send a prompt to the local Ollama server with strict JSON schema.

    Uses Ollama's structured output feature: passing a JSON Schema as `format`
    forces the model to produce output matching that schema at the tokenizer
    level. This is MUCH more reliable than asking via prompt — small models
    (Llama 3.2 3B) often ignore textual instructions but cannot violate the
    grammar enforced by the JSON Schema.

    Critical: ALL numeric fields are declared as "string" type. The LLM is
    physically prevented from outputting "29.5" when the invoice shows
    "29.500" — it must keep the original text. The downstream Pydantic
    OptFloat coercer then applies Romanian-aware parsing.

    Returns the raw text response. Raises RuntimeError if the local server
    is not reachable or the configured model is not installed.
    """
    client = _ollama_client()
    try:
        response = client.chat(
            model=OLLAMA_MODEL,
            format=_INVOICE_JSON_SCHEMA,  # tokenizer-level schema enforcement
            options={"temperature": 0},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
    except ollama.ResponseError as exc:
        raise RuntimeError(
            f"Ollama server error: {exc}. Make sure Ollama is running "
            f"(`ollama serve`) and the model `{OLLAMA_MODEL}` is installed "
            f"(`ollama pull {OLLAMA_MODEL}`)."
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"Could not reach Ollama at {OLLAMA_HOST}: {exc}. Run "
            f"`ollama serve` in a separate terminal to start the local LLM."
        ) from exc

    return response.get("message", {}).get("content", "") or ""


def extract_invoice_from_text(raw_text: str) -> Dict[str, Any]:
    """
    Extract invoice fields from raw text using the local Ollama model.

    Args:
        raw_text: text obtained from PyMuPDF or Tesseract OCR.

    Returns:
        Dict matching the schema in :data:`JSON_SCHEMA_DESCRIPTION`.

    Raises:
        ValueError: if the text is empty.
        RuntimeError: if Ollama is unreachable or the response is invalid.
    """
    if not raw_text or not raw_text.strip():
        raise ValueError("Invoice text is empty; cannot process.")

    user_prompt = (
        "Below is the text extracted from an invoice. Extract its fields "
        "into the JSON object described below.\n\n"
        f"{JSON_SCHEMA_DESCRIPTION}\n\n"
        "INVOICE TEXT:\n<<<\n"
        f"{raw_text}\n>>>"
    )

    raw_response = _run_ollama(user_prompt)
    parsed = parse_json_safe(raw_response)

    if not parsed:
        raise RuntimeError(
            "The local model returned a response that could not be parsed "
            f"as JSON. Raw output: {raw_response[:500]}"
        )

    return parsed


def extract_invoice_from_images(
    image_paths: List[Union[str, Path]],
) -> Dict[str, Any]:
    """
    Extract invoice fields from one or more rendered PDF page images.

    Pipeline: Tesseract OCR -> Ollama structuring. Both steps run entirely
    on the local machine.
    """
    if not image_paths:
        raise ValueError("No image paths provided for OCR.")

    raw_text = extract_text_from_images(image_paths)
    if not raw_text.strip():
        raise RuntimeError(
            "Tesseract OCR returned no text. Either the images are blank, "
            "the language pack is missing, or Tesseract is not installed. "
            "Try `brew install tesseract tesseract-lang`."
        )

    return extract_invoice_from_text(raw_text)


# =============================================================================
# Optional: a quick health check used by the UI
# =============================================================================
def check_local_stack() -> Dict[str, str]:
    """
    Verify that Tesseract and Ollama are reachable. Returns a dict with
    'tesseract' and 'ollama' status strings ("ok" or an error message),
    plus the model name in use. Useful for surfacing setup issues early.
    """
    out: Dict[str, str] = {}

    # Tesseract
    try:
        version = pytesseract.get_tesseract_version()
        out["tesseract"] = f"ok (v{version})"
    except Exception as exc:  # noqa: BLE001
        out["tesseract"] = f"not available: {exc}"

    # Ollama
    try:
        client = _ollama_client()
        models = client.list().get("models", [])
        model_names = {m.get("model", m.get("name", "")) for m in models}
        if OLLAMA_MODEL in model_names or any(
            OLLAMA_MODEL.split(":")[0] in name for name in model_names
        ):
            out["ollama"] = f"ok (model: {OLLAMA_MODEL})"
        else:
            out["ollama"] = (
                f"server up but model `{OLLAMA_MODEL}` not pulled. "
                f"Run `ollama pull {OLLAMA_MODEL}`."
            )
    except Exception as exc:  # noqa: BLE001
        out["ollama"] = (
            f"not reachable at {OLLAMA_HOST}: {exc}. "
            "Run `ollama serve` in a separate terminal."
        )

    return out
