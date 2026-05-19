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
    "the invoice — do NOT infer or invent. Use null for missing fields. "
    "IMPORTANT: return ALL numeric fields as STRINGS preserving the EXACT "
    "text from the invoice (including dots, commas, spaces). Do not "
    "convert numbers yourself — a downstream parser will interpret the "
    "Romanian number format. For example, if the invoice shows \"29.500\", "
    "return the STRING \"29.500\" (not the number 29.5)."
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
    Send a prompt to the local Ollama server with strict JSON formatting.

    Returns the raw text response. Raises RuntimeError if the local server
    is not reachable or the configured model is not installed.
    """
    client = _ollama_client()
    try:
        response = client.chat(
            model=OLLAMA_MODEL,
            format="json",  # constrain to valid JSON
            options={"temperature": 0},  # deterministic output
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
