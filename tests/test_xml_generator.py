# tests/test_xml_generator.py
"""
Teste unitare pentru modulul `xml_generator`.

Scopul testelor:
    - sa verifice ca XML-ul rezultat contine tagurile principale cerute
      in specificatia proiectului (InvoiceNumber, Supplier, Customer, Totals);
    - sa verifice ca XML-ul este sintactic valid (parseable);
    - sa verifice ca elementele <Item> sunt generate corect pentru fiecare
      linie de factura din input.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from src.schema import (
    Customer,
    InvoiceData,
    InvoiceItem,
    Supplier,
    Totals,
)
from src.validators import validate_xml
from src.xml_generator import generate_invoice_xml, safe_text


@pytest.fixture()
def sample_invoice() -> InvoiceData:
    """Creeaza o instanta `InvoiceData` cu valori de test."""
    return InvoiceData(
        invoice_number="FACT-2026-001",
        invoice_date="2026-05-04",
        due_date="2026-06-04",
        currency="RON",
        supplier=Supplier(
            name="Furnizor SRL",
            tax_id="RO12345678",
            registration_number="J40/123/2020",
            address="Str. Tehnologiei 1, Bucuresti",
            iban="RO49AAAA1B31007593840000",
            bank="Banca Test",
        ),
        customer=Customer(
            name="Client SA",
            tax_id="RO87654321",
            registration_number="J40/999/2019",
            address="Bd. Universitatii 5, Bucuresti",
        ),
        items=[
            InvoiceItem(
                description="Servicii de consultanta",
                quantity=2,
                unit_price=500.0,
                vat_rate=19.0,
                net_amount=1000.0,
                vat_amount=190.0,
                gross_amount=1190.0,
            ),
            InvoiceItem(
                description="Licenta software",
                quantity=1,
                unit_price=300.0,
                vat_rate=19.0,
                net_amount=300.0,
                vat_amount=57.0,
                gross_amount=357.0,
            ),
        ],
        totals=Totals(
            subtotal=1300.0,
            vat_total=247.0,
            grand_total=1547.0,
        ),
    )


def test_xml_contains_required_tags(sample_invoice: InvoiceData) -> None:
    """XML-ul trebuie sa contina tagurile principale cerute in specificatie."""
    xml_str = generate_invoice_xml(sample_invoice)

    for tag in (
        "<Invoice>",
        "<InvoiceNumber>",
        "<InvoiceDate>",
        "<DueDate>",
        "<Currency>",
        "<Supplier>",
        "<Customer>",
        "<Items>",
        "<Item>",
        "<Totals>",
        "<Subtotal>",
        "<VATTotal>",
        "<GrandTotal>",
    ):
        assert tag in xml_str, f"Tagul {tag} lipseste din XML."


def test_xml_is_well_formed(sample_invoice: InvoiceData) -> None:
    """XML-ul generat trebuie sa fie parseable."""
    xml_str = generate_invoice_xml(sample_invoice)
    assert validate_xml(xml_str) is True


def test_xml_item_count_matches_input(sample_invoice: InvoiceData) -> None:
    """Numarul de <Item> generat trebuie sa fie egal cu numarul de linii."""
    xml_str = generate_invoice_xml(sample_invoice)
    root = ET.fromstring(xml_str)
    items = root.findall("./Items/Item")
    assert len(items) == len(sample_invoice.items)


def test_xml_supplier_fields(sample_invoice: InvoiceData) -> None:
    """Campurile Supplier trebuie sa fie populate corect in XML."""
    xml_str = generate_invoice_xml(sample_invoice)
    root = ET.fromstring(xml_str)

    assert root.findtext("./Supplier/Name") == "Furnizor SRL"
    assert root.findtext("./Supplier/TaxID") == "RO12345678"
    assert root.findtext("./Supplier/IBAN") == "RO49AAAA1B31007593840000"


def test_xml_handles_empty_invoice() -> None:
    """O factura goala (toate campurile None) trebuie sa produca XML valid."""
    empty = InvoiceData()
    xml_str = generate_invoice_xml(empty)
    assert validate_xml(xml_str) is True
    root = ET.fromstring(xml_str)
    # Tagurile trebuie sa existe, chiar daca au text gol.
    assert root.find("InvoiceNumber") is not None
    assert root.find("Supplier") is not None
    assert root.find("Customer") is not None
    assert root.find("Totals") is not None


def test_safe_text_handles_various_types() -> None:
    """`safe_text` trebuie sa converteasca corect diverse tipuri."""
    assert safe_text(None) == ""
    assert safe_text("abc") == "abc"
    assert safe_text(123) == "123"
    assert safe_text(12.50) == "12.5"
    assert safe_text(0.0) == "0"
    assert safe_text(True) == "true"


def test_generate_xml_accepts_dict() -> None:
    """`generate_invoice_xml` trebuie sa accepte si un dict ca input."""
    data = {
        "invoice_number": "X-1",
        "totals": {"grand_total": 100.0},
    }
    xml_str = generate_invoice_xml(data)
    assert "<InvoiceNumber>X-1</InvoiceNumber>" in xml_str
    assert "<GrandTotal>100</GrandTotal>" in xml_str
