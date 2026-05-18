# src/xml_generator.py
"""
Generator XML pentru facturile extrase.

Modulul construieste un document XML conform structurii cerute in
specificatia proiectului:

<Invoice>
  <InvoiceNumber/>
  <InvoiceDate/>
  ...
  <Supplier>...</Supplier>
  <Customer>...</Customer>
  <Items>
    <Item>...</Item>
  </Items>
  <Totals>...</Totals>
</Invoice>

Generarea este DETERMINISTA si LOCALA (fara apel AI), pentru a oferi
un comportament reproductibil si auditabil. Caracterele speciale
(<, >, &) sunt escapate automat de `xml.etree.ElementTree`.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any, Optional, Union
from xml.dom import minidom

from .schema import (
    CompanyRiskAnalysis,
    CompanyVerification,
    Customer,
    InvoiceData,
    InvoiceItem,
    OnlineMention,
    Supplier,
    Totals,
)


def safe_text(value: Any) -> str:
    """
    Converteste o valoare oarecare intr-un string sigur pentru XML.

    Reguli:
        - None -> "" (string gol);
        - numere (int / float) -> reprezentare zecimala normala;
        - alte tipuri -> str(value).

    Args:
        value: valoarea de convertit.

    Returns:
        Stringul corespunzator, gata de inserat in tag XML.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        # Evitam ca bool sa fie tratat ca int.
        return "true" if value else "false"
    if isinstance(value, float):
        # Eliminam zerourile finale inutile, dar pastram precizia.
        formatted = f"{value:.4f}".rstrip("0").rstrip(".")
        return formatted if formatted else "0"
    return str(value)


def _add_child(parent: ET.Element, tag: str, value: Any) -> ET.Element:
    """Helper pentru a adauga un copil cu text in mod uniform."""
    el = ET.SubElement(parent, tag)
    el.text = safe_text(value)
    return el


def _build_supplier(parent: ET.Element, supplier: Supplier) -> None:
    """Adauga blocul <Supplier> sub elementul parinte."""
    node = ET.SubElement(parent, "Supplier")
    _add_child(node, "Name", supplier.name)
    _add_child(node, "TaxID", supplier.tax_id)
    _add_child(node, "RegistrationNumber", supplier.registration_number)
    _add_child(node, "Address", supplier.address)
    _add_child(node, "IBAN", supplier.iban)
    _add_child(node, "Bank", supplier.bank)


def _build_customer(parent: ET.Element, customer: Customer) -> None:
    """Adauga blocul <Customer> sub elementul parinte."""
    node = ET.SubElement(parent, "Customer")
    _add_child(node, "Name", customer.name)
    _add_child(node, "TaxID", customer.tax_id)
    _add_child(node, "RegistrationNumber", customer.registration_number)
    _add_child(node, "Address", customer.address)


def _build_item(parent: ET.Element, item: InvoiceItem) -> None:
    """Adauga un singur <Item> sub <Items>."""
    node = ET.SubElement(parent, "Item")
    _add_child(node, "Description", item.description)
    _add_child(node, "Quantity", item.quantity)
    _add_child(node, "UnitPrice", item.unit_price)
    _add_child(node, "VATRate", item.vat_rate)
    _add_child(node, "NetAmount", item.net_amount)
    _add_child(node, "VATAmount", item.vat_amount)
    _add_child(node, "GrossAmount", item.gross_amount)


def _build_totals(parent: ET.Element, totals: Totals) -> None:
    """Adauga blocul <Totals> sub elementul parinte."""
    node = ET.SubElement(parent, "Totals")
    _add_child(node, "Subtotal", totals.subtotal)
    _add_child(node, "VATTotal", totals.vat_total)
    _add_child(node, "GrandTotal", totals.grand_total)


def _build_online_mentions(
    parent: ET.Element,
    mentions: list,
) -> None:
    """Adauga blocul <OnlineMentions> cu fiecare <Mention>."""
    node = ET.SubElement(parent, "OnlineMentions")
    if not mentions:
        return
    for m in mentions:
        if not isinstance(m, OnlineMention):
            try:
                m = OnlineMention.model_validate(m)
            except Exception:  # noqa: BLE001
                continue
        item = ET.SubElement(node, "Mention")
        _add_child(item, "Title", m.title)
        _add_child(item, "URL", m.url)
        _add_child(item, "Snippet", m.snippet)
        _add_child(item, "Source", m.source)
        _add_child(item, "PublishedDate", m.published_date)


def _build_company_verification(
    parent: ET.Element,
    block_tag: str,
    verification: CompanyVerification | None,
    risk: CompanyRiskAnalysis | None,
    mentions: list | None,
) -> None:
    """
    Construieste un bloc <SupplierVerification> sau <CustomerVerification>
    sub elementul parinte, in functie de ``block_tag``.

    Contine toate informatiile colectate din API-uri externe + scorul de risc
    heuristic + mentiunile online. Daca lipsesc complet datele, se genereaza
    un bloc cu Status='not_available' pentru a pastra schema XML consistenta.
    """
    node = ET.SubElement(parent, block_tag)

    if verification is None:
        _add_child(node, "Verified", "false")
        _add_child(node, "Status", "not_available")
        _add_child(node, "Source", None)
        _add_child(node, "OfficialName", None)
        _add_child(node, "TaxID", None)
        _add_child(node, "RegistrationNumber", None)
        _add_child(node, "Address", None)
        _add_child(node, "VATStatus", None)
        _add_child(node, "CompanyStatus", None)
        _add_child(node, "CAENCode", None)
    else:
        _add_child(node, "Verified", verification.verified)
        _add_child(node, "Status", verification.status)
        _add_child(node, "Source", verification.source)
        _add_child(node, "OfficialName", verification.official_name)
        _add_child(node, "TaxID", verification.tax_id)
        _add_child(node, "RegistrationNumber", verification.registration_number)
        _add_child(node, "Address", verification.address)
        _add_child(node, "VATStatus", verification.vat_status)
        _add_child(node, "CompanyStatus", verification.company_status)
        _add_child(node, "CAENCode", verification.caen_code)

    # ---- Risk analysis ----
    if risk is None:
        _add_child(node, "RiskScore", None)
        _add_child(node, "RiskLevel", "not_available")
    else:
        _add_child(node, "RiskScore", risk.risk_score)
        _add_child(node, "RiskLevel", risk.risk_level)
        warnings_node = ET.SubElement(node, "Warnings")
        for w in risk.warnings or []:
            _add_child(warnings_node, "Warning", w)

    # ---- Online mentions ----
    _build_online_mentions(node, mentions or [])


def generate_invoice_xml(invoice_data: Union[InvoiceData, dict]) -> str:
    """
    Genereaza un XML formatat (pretty-print) pentru o factura validata.

    Accepta atat o instanta `InvoiceData` cat si un dictionar (caz in care
    il valideaza prin Pydantic inainte de generare).

    Args:
        invoice_data: datele facturii (model Pydantic sau dict).

    Returns:
        Stringul XML rezultat, in format UTF-8 cu indentare.

    Raises:
        TypeError: daca tipul argumentului nu este suportat.
    """
    # Acceptam si dict pentru flexibilitate; il transformam in model Pydantic.
    if isinstance(invoice_data, dict):
        invoice_data = InvoiceData.model_validate(invoice_data)
    elif not isinstance(invoice_data, InvoiceData):
        raise TypeError(
            "generate_invoice_xml asteapta InvoiceData sau dict. "
            f"Primit: {type(invoice_data).__name__}"
        )

    # Construim arborele XML.
    root = ET.Element("Invoice")
    _add_child(root, "InvoiceNumber", invoice_data.invoice_number)
    _add_child(root, "InvoiceDate", invoice_data.invoice_date)
    _add_child(root, "DueDate", invoice_data.due_date)
    _add_child(root, "Currency", invoice_data.currency)

    _build_supplier(root, invoice_data.supplier)
    _build_customer(root, invoice_data.customer)

    items_node = ET.SubElement(root, "Items")
    for item in invoice_data.items:
        _build_item(items_node, item)

    _build_totals(root, invoice_data.totals)

    # Extensia disertatiei - blocuri pentru AMBELE firme:
    # <SupplierVerification> (prestator) si <CustomerVerification> (beneficiar).
    _build_company_verification(
        root,
        "SupplierVerification",
        invoice_data.supplier_verification,
        invoice_data.supplier_risk_analysis,
        invoice_data.supplier_online_mentions or [],
    )
    _build_company_verification(
        root,
        "CustomerVerification",
        invoice_data.customer_verification,
        invoice_data.customer_risk_analysis,
        invoice_data.customer_online_mentions or [],
    )

    # Serializam in string brut, apoi formatam cu minidom pentru pretty-print.
    raw_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=False)
    pretty = minidom.parseString(raw_bytes).toprettyxml(indent="  ", encoding="utf-8")

    # `toprettyxml` returneaza bytes; il decodam si eliminam liniile goale
    # extra adaugate accidental de minidom.
    pretty_str = pretty.decode("utf-8")
    cleaned_lines = [line for line in pretty_str.splitlines() if line.strip()]
    return "\n".join(cleaned_lines) + "\n"
