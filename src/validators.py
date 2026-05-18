# src/validators.py
"""
Validatori pentru datele extrase si pentru XML-ul generat.

Validarea este o etapa critica intre extragerea AI si generarea XML:
    - garanteaza ca structura JSON respecta schema impusa;
    - normalizeaza tipurile (string vs. numeric);
    - prinde din timp raspunsuri partiale sau invalide.

Folosim Pydantic pentru validarea datelor, si xml.etree pentru a verifica
ca XML-ul generat este sintactic corect.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any, Dict

from pydantic import ValidationError

from .schema import InvoiceData


class InvoiceValidationError(Exception):
    """Eroare specifica in validarea datelor de factura."""


class XMLValidationError(Exception):
    """Eroare specifica in validarea XML-ului generat."""


def validate_invoice_data(data: Dict[str, Any]) -> InvoiceData:
    """
    Valideaza un dictionar Python (rezultat din parsarea raspunsului OpenAI)
    folosind modelul Pydantic `InvoiceData`.

    Args:
        data: dictionarul de validat.

    Returns:
        Obiect `InvoiceData` validat si normalizat.

    Raises:
        InvoiceValidationError: daca structura nu respecta schema impusa
            (mesajul detaliaza campurile problematice).
    """
    if not isinstance(data, dict):
        raise InvoiceValidationError(
            f"Datele primite nu sunt un dictionar. Tip primit: {type(data).__name__}"
        )

    try:
        return InvoiceData.model_validate(data)
    except ValidationError as exc:
        # Reformulam erorile Pydantic intr-un mesaj prietenos pentru utilizator.
        details = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}"
            for err in exc.errors()
        )
        raise InvoiceValidationError(
            f"Datele facturii nu sunt valide. Detalii: {details}"
        ) from exc


def validate_xml(xml_string: str) -> bool:
    """
    Verifica daca un string XML este sintactic valid (well-formed).

    Args:
        xml_string: continutul XML de validat.

    Returns:
        True daca XML-ul este parseable.

    Raises:
        XMLValidationError: daca XML-ul nu poate fi parsat (ex. taguri
            nebalansate, caractere invalide).
    """
    if not xml_string or not xml_string.strip():
        raise XMLValidationError("XML-ul este gol.")

    try:
        ET.fromstring(xml_string)
        return True
    except ET.ParseError as exc:
        raise XMLValidationError(f"XML invalid: {exc}") from exc
