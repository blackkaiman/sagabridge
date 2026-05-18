# src/openai_extractor.py
"""
Modul de extragere inteligenta a datelor de pe factura folosind OpenAI API.

Suporta doua moduri de operare:
    1. extract_invoice_from_text(raw_text)   - pentru facturi digitale,
       cand textul a putut fi extras local din PDF.
    2. extract_invoice_from_images(image_paths) - pentru facturi scanate,
       cand este necesara analiza vizuala (OpenAI Vision).

Promptul este construit astfel incat sa impuna modelului:
    - sa returneze STRICT JSON (fara markdown / explicatii);
    - sa NU inventeze date inexistente in factura;
    - sa respecte schema cu campuri null daca lipsesc;
    - sa returneze structura exacta ceruta in specificatie.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Union

from openai import OpenAI

from .config import OPENAI_API_KEY, OPENAI_MODEL, validate_api_key
from .utils import encode_image_to_base64, parse_json_safe


# -----------------------------------------------------------------------------
# Prompt-uri reutilizabile
# -----------------------------------------------------------------------------

# Schema impusa modelului - este inclusa in fiecare prompt pentru a forta
# raspunsul intr-un format predictibil.
JSON_SCHEMA_DESCRIPTION = """\
Returneaza STRICT un obiect JSON valid, fara markdown, fara comentarii,
fara text inainte sau dupa. Foloseste exact urmatoarea structura,
folosind null cand un camp nu este prezent in factura:

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
      "quantity": "number|null",
      "unit_price": "number|null",
      "vat_rate": "number|null",
      "net_amount": "number|null",
      "vat_amount": "number|null",
      "gross_amount": "number|null"
    }
  ],
  "totals": {
    "subtotal": "number|null",
    "vat_total": "number|null",
    "grand_total": "number|null"
  }
}
"""

SYSTEM_PROMPT = (
    "Esti un asistent specializat in extragerea automata de date din facturi "
    "(romanesti si internationale). Extragi DOAR informatii prezente efectiv "
    "in factura - nu inventezi si nu deduci date care nu sunt scrise. "
    "Daca un camp lipseste sau este ilizibil, folosesti null. "
    "Numerele le returnezi ca tipuri numerice JSON (fara simboluri de moneda)."
)


def _get_client() -> OpenAI:
    """Construieste un client OpenAI, validand prezenta cheii API."""
    validate_api_key()
    return OpenAI(api_key=OPENAI_API_KEY)


def extract_invoice_from_text(raw_text: str) -> Dict[str, Any]:
    """
    Extrage datele facturii dintr-un text deja obtinut local din PDF.

    Args:
        raw_text: textul brut extras cu PyMuPDF (sau alt extractor).

    Returns:
        Dictionar Python cu structura ceruta in JSON_SCHEMA_DESCRIPTION.

    Raises:
        ValueError: daca textul de intrare este gol.
        RuntimeError: daca apare o eroare la apelul OpenAI sau la parsare.
    """
    if not raw_text or not raw_text.strip():
        raise ValueError("Textul facturii este gol; nu poate fi procesat.")

    client = _get_client()

    user_prompt = (
        "Mai jos este textul extras dintr-o factura. Extrage informatiile "
        "structurate conform schemei.\n\n"
        f"{JSON_SCHEMA_DESCRIPTION}\n\n"
        "TEXT FACTURA:\n"
        "<<<\n"
        f"{raw_text}\n"
        ">>>"
    )

    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
    except Exception as exc:  # noqa: BLE001 - vrem mesaje generice catre utilizator
        raise RuntimeError(f"Eroare la apelul OpenAI (text): {exc}") from exc

    content = response.choices[0].message.content or ""
    parsed = parse_json_safe(content)

    if not parsed:
        raise RuntimeError(
            "Raspunsul OpenAI nu a putut fi parsat ca JSON valid. "
            f"Continut brut: {content[:500]}"
        )

    return parsed


def extract_invoice_from_images(
    image_paths: List[Union[str, Path]],
) -> Dict[str, Any]:
    """
    Extrage datele facturii din una sau mai multe imagini PNG (factura scanata).

    Foloseste OpenAI Vision: imaginile sunt codate base64 si trimise ca
    parte a mesajului utilizatorului, alaturi de instructiunile schemei.

    Args:
        image_paths: lista de cai catre imaginile PNG.

    Returns:
        Dictionar Python conform schemei.

    Raises:
        ValueError: daca lista de imagini este goala.
        RuntimeError: la erori de API sau parsare.
    """
    if not image_paths:
        raise ValueError("Lista de imagini este goala; nu se poate apela Vision.")

    client = _get_client()

    # Construim continutul mesajului utilizator: text + N imagini base64.
    user_content: List[Dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                "Mai jos sunt imagini ale paginilor unei facturi. "
                "Extrage informatiile structurate conform schemei.\n\n"
                f"{JSON_SCHEMA_DESCRIPTION}"
            ),
        }
    ]

    for img_path in image_paths:
        b64 = encode_image_to_base64(img_path)
        user_content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{b64}",
                "detail": "high",
            },
        })

    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
        )
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Eroare la apelul OpenAI Vision: {exc}") from exc

    content = response.choices[0].message.content or ""
    parsed = parse_json_safe(content)

    if not parsed:
        raise RuntimeError(
            "Raspunsul OpenAI Vision nu a putut fi parsat ca JSON valid. "
            f"Continut brut: {content[:500]}"
        )

    return parsed
