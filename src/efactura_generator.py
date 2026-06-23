# src/efactura_generator.py
"""
Generator XML in format e-Factura (RO e-Factura / ANAF).

Spre deosebire de `xml_generator.py` (care produce o schema proprie,
orientata pe import contabil generic), acest modul produce un document
conform standardului european **EN 16931**, in sintaxa **UBL 2.1**,
cu profilul de customizare romanesc **RO_CIUS** cerut de ANAF pentru
sistemul national RO e-Factura.

Structura (simplificata) a documentului UBL generat:

    <Invoice xmlns=... xmlns:cac=... xmlns:cbc=...>
      <cbc:CustomizationID>...CIUS-RO...</cbc:CustomizationID>
      <cbc:ID/>                         numarul facturii (BT-1)
      <cbc:IssueDate/>                  data emiterii, ISO (BT-2)
      <cbc:InvoiceTypeCode>380</...>    factura comerciala (BT-3)
      <cbc:DocumentCurrencyCode/>       moneda (BT-5)
      <cac:AccountingSupplierParty/>    prestator (BG-4)
      <cac:AccountingCustomerParty/>    beneficiar (BG-7)
      <cac:TaxTotal/>                   total TVA (BG-22 / BG-23)
      <cac:LegalMonetaryTotal/>         totaluri document (BG-22)
      <cac:InvoiceLine/>*               liniile facturii (BG-25)
    </Invoice>

IMPORTANT (limitari oneste):
    Documentul respecta STRUCTURA UBL/EN16931, dar trecerea efectiva a
    validarii ANAF depinde de completitudinea datelor extrase din PDF
    (CUI cu prefix de tara, cod judet, cota TVA, unitate de masura etc.).
    Acolo unde o informatie obligatorie lipseste din factura sursa, se
    foloseste o valoare implicita rezonabila (ex. moneda RON, unitate
    "C62"/bucata, cota standard) — care poate necesita corectie manuala.
"""

from __future__ import annotations

import datetime as _dt
import re
import unicodedata
import xml.etree.ElementTree as ET
from typing import Optional, Union
from xml.dom import minidom

from .schema import InvoiceData

# ---------------------------------------------------------------------------
# Namespace-uri UBL 2.1
# ---------------------------------------------------------------------------
_UBL = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
_CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
_CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"

ET.register_namespace("", _UBL)
ET.register_namespace("cac", _CAC)
ET.register_namespace("cbc", _CBC)

# Profilul de customizare RO_CIUS cerut de ANAF.
_CUSTOMIZATION_ID = (
    "urn:cen.eu:en16931:2017#compliant#urn:efactura.mfinante.ro:CIUS-RO:1.0.1"
)
_DEFAULT_CURRENCY = "RON"
_DEFAULT_UNIT = "C62"  # cod UN/ECE pentru "bucata"
_STANDARD_VAT = 21.0   # cota standard RO (21% din 1 aug 2025), doar ca fallback


def _cbc(tag: str) -> str:
    return f"{{{_CBC}}}{tag}"


def _cac(tag: str) -> str:
    return f"{{{_CAC}}}{tag}"


# ---------------------------------------------------------------------------
# Helperi de normalizare
# ---------------------------------------------------------------------------
def _iso_date(value: Optional[str]) -> str:
    """
    Converteste o data in format ISO (YYYY-MM-DD), cum cere e-Factura.

    Accepta formate uzuale romanesti: "15.01.2026", "15/01/2026",
    "2026-01-15". Daca nu poate parsa, intoarce data curenta (ca sa nu
    lase campul obligatoriu gol).
    """
    if value:
        s = value.strip()
        for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%y"):
            try:
                return _dt.datetime.strptime(s, fmt).date().isoformat()
            except ValueError:
                continue
        # ultima incercare: extrage 3 grupuri numerice
        m = re.match(r"\s*(\d{1,4})\D(\d{1,2})\D(\d{1,4})", s)
        if m:
            a, b, c = m.groups()
            try:
                if len(a) == 4:  # YYYY-MM-DD
                    return _dt.date(int(a), int(b), int(c)).isoformat()
                return _dt.date(int(c), int(b), int(a)).isoformat()  # DD-MM-YYYY
            except ValueError:
                pass
    return _dt.date.today().isoformat()


def _num(value: Optional[float]) -> str:
    """Formateaza un numar cu 2 zecimale (cerinta sume monetare UBL)."""
    if value is None:
        return "0.00"
    return f"{float(value):.2f}"


def _qty(value: Optional[float]) -> str:
    if value is None:
        return "1"
    # cantitatile pot avea zecimale (ore, kg); pastram pana la 3.
    formatted = f"{float(value):.3f}".rstrip("0").rstrip(".")
    return formatted or "0"


def _vat_company_id(tax_id: Optional[str]) -> Optional[str]:
    """
    Construieste identificatorul de TVA (BT-31): "RO" + cifrele CUI-ului.
    Intoarce None daca nu exista cifre.
    """
    if not tax_id:
        return None
    digits = re.sub(r"\D", "", tax_id)
    if not digits:
        return None
    return f"RO{digits}"


def _clean_text(value: Optional[str], fallback: str = "N/A") -> str:
    if value is None:
        return fallback
    s = str(value).strip()
    return s if s else fallback


# ISO 3166-2:RO — coduri de judet cerute de RO_CIUS pentru CountrySubentity
# (regulile BR-RO-110 / BR-RO-111: daca tara e RO, judetul e obligatoriu).
_COUNTY_CODES = {
    "alba": "RO-AB", "arad": "RO-AR", "arges": "RO-AG", "bacau": "RO-BC",
    "bihor": "RO-BH", "bistrita-nasaud": "RO-BN", "bistrita nasaud": "RO-BN",
    "botosani": "RO-BT", "braila": "RO-BR", "brasov": "RO-BV", "buzau": "RO-BZ",
    "calarasi": "RO-CL", "caras-severin": "RO-CS", "caras severin": "RO-CS",
    "cluj": "RO-CJ", "constanta": "RO-CT", "covasna": "RO-CV", "dambovita": "RO-DB",
    "dolj": "RO-DJ", "galati": "RO-GL", "giurgiu": "RO-GR", "gorj": "RO-GJ",
    "harghita": "RO-HR", "hunedoara": "RO-HD", "ialomita": "RO-IL", "iasi": "RO-IS",
    "ilfov": "RO-IF", "maramures": "RO-MM", "mehedinti": "RO-MH", "mures": "RO-MS",
    "neamt": "RO-NT", "olt": "RO-OT", "prahova": "RO-PH", "satu mare": "RO-SM",
    "salaj": "RO-SJ", "sibiu": "RO-SB", "suceava": "RO-SV", "teleorman": "RO-TR",
    "timis": "RO-TM", "tulcea": "RO-TL", "vaslui": "RO-VS", "valcea": "RO-VL",
    "vrancea": "RO-VN", "bucuresti": "RO-B",
}


def _strip_diacritics(text: str) -> str:
    """Elimina diacriticele (ă→a, ș→s, ț→t etc.) pentru potrivire robusta."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _parse_ro_address(address: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """
    Extrage (oras, cod_judet) dintr-o adresa romaneasca in text liber.

    Returneaza codul ISO 3166-2:RO al judetului (ex. "RO-SJ") si numele
    orasului. Acopera formate uzuale: "..., Zalău, jud. Sălaj, România"
    sau "JUD. SĂLAJ, MUN. ZALĂU, STR. ...". Bucureștiul → "RO-B".
    """
    if not address:
        return None, None
    raw = address.strip()
    norm = _strip_diacritics(raw).lower()

    subentity: Optional[str] = None
    if "bucuresti" in norm or re.search(r"\bsector\s*\d", norm):
        subentity = "RO-B"
    else:
        m = re.search(r"jud(?:e[t]?(?:ul)?)?\.?\s+([a-z\- ]+)", norm)
        if m:
            cand = re.sub(r"\s+", " ", m.group(1).split(",")[0].strip())
            subentity = _COUNTY_CODES.get(cand)
            if not subentity:
                for key, code in _COUNTY_CODES.items():
                    if cand.startswith(key):
                        subentity = code
                        break
        if not subentity:
            for key, code in _COUNTY_CODES.items():
                if re.search(r"\b" + re.escape(key) + r"\b", norm):
                    subentity = code
                    break

    city: Optional[str] = None
    parts = [p.strip() for p in raw.split(",")]
    for i, p in enumerate(parts):
        if _strip_diacritics(p).lower().startswith("jud") and i > 0:
            city = parts[i - 1]
            break
    if not city:
        m2 = re.search(
            r"(?:mun\.?|municipiul|oras(?:ul)?|com\.?|comuna)\s+([^,]+)",
            raw, re.IGNORECASE,
        )
        if m2:
            city = m2.group(1).strip()
    if city:
        city = re.sub(r"^[\s\-\d]+", "", city).strip()  # scoate cod postal / "-" din fata
    if not city and subentity == "RO-B":
        city = "București"
    return (city or None, subentity)


def _derive_percent(invoice: InvoiceData, item) -> float:
    """Determina cota TVA pentru o linie: din linie, altfel din totaluri, altfel standard."""
    if item is not None and item.vat_rate is not None:
        return float(item.vat_rate)
    t = invoice.totals
    if t.vat_total and t.subtotal:
        try:
            return round(t.vat_total / t.subtotal * 100)
        except ZeroDivisionError:
            pass
    # daca nu exista TVA deloc, tratam ca 0 (neplatitor / scutit)
    if (t.vat_total in (None, 0)) and t.subtotal:
        return 0.0
    return _STANDARD_VAT


def _tax_category(percent: float):
    """
    Returneaza (cod_categorie, motiv_scutire | None) pentru un procent dat.
        percent > 0  -> "S" (cota standard)
        percent == 0 -> "O" (neplatitor de TVA / in afara sferei)
    """
    if percent and percent > 0:
        return "S", None
    return "O", "Neplătitor de TVA"


# ---------------------------------------------------------------------------
# Blocuri de constructie
# ---------------------------------------------------------------------------
def _build_address(
    parent: ET.Element,
    address: Optional[str],
    city: Optional[str],
    subentity: Optional[str],
) -> None:
    # Ordinea ceruta de schema UBL: StreetName, CityName, CountrySubentity, Country.
    node = ET.SubElement(parent, _cac("PostalAddress"))
    addr = _clean_text(address, "")
    if addr:
        ET.SubElement(node, _cbc("StreetName")).text = addr[:150]
    ET.SubElement(node, _cbc("CityName")).text = city or "N/A"
    if subentity:
        # BT-39 / BT-54 — obligatoriu cand tara e RO (BR-RO-110 / BR-RO-111).
        ET.SubElement(node, _cbc("CountrySubentity")).text = subentity
    country = ET.SubElement(node, _cac("Country"))
    ET.SubElement(country, _cbc("IdentificationCode")).text = "RO"


def _build_party(
    parent: ET.Element, tag: str, name, tax_id, reg_no, address,
    official_address: Optional[str] = None,
) -> None:
    holder = ET.SubElement(parent, _cac(tag))
    party = ET.SubElement(holder, _cac("Party"))

    pname = ET.SubElement(party, _cac("PartyName"))
    ET.SubElement(pname, _cbc("Name")).text = _clean_text(name)

    # Oras + judet: din adresa de pe factura; daca lipseste judetul,
    # incercam adresa oficiala (din verificarea ANAF) ca rezerva.
    city, subentity = _parse_ro_address(address)
    if (not subentity or not city) and official_address:
        off_city, off_sub = _parse_ro_address(official_address)
        subentity = subentity or off_sub
        city = city or off_city
    _build_address(party, address or official_address, city, subentity)

    vat_id = _vat_company_id(tax_id)
    if vat_id:
        pts = ET.SubElement(party, _cac("PartyTaxScheme"))
        ET.SubElement(pts, _cbc("CompanyID")).text = vat_id
        scheme = ET.SubElement(pts, _cac("TaxScheme"))
        ET.SubElement(scheme, _cbc("ID")).text = "VAT"

    legal = ET.SubElement(party, _cac("PartyLegalEntity"))
    ET.SubElement(legal, _cbc("RegistrationName")).text = _clean_text(name)
    company_id = _clean_text(reg_no, "") or re.sub(r"\D", "", tax_id or "")
    if company_id:
        ET.SubElement(legal, _cbc("CompanyID")).text = company_id


def _build_tax_total(parent: ET.Element, invoice: InvoiceData, currency: str) -> None:
    t = invoice.totals
    taxable = t.subtotal if t.subtotal is not None else 0.0
    tax_amount = t.vat_total if t.vat_total is not None else 0.0
    percent = _derive_percent(invoice, invoice.items[0] if invoice.items else None)
    cat_code, exemption = _tax_category(percent)

    node = ET.SubElement(parent, _cac("TaxTotal"))
    ET.SubElement(node, _cbc("TaxAmount"), {"currencyID": currency}).text = _num(tax_amount)

    sub = ET.SubElement(node, _cac("TaxSubtotal"))
    ET.SubElement(sub, _cbc("TaxableAmount"), {"currencyID": currency}).text = _num(taxable)
    ET.SubElement(sub, _cbc("TaxAmount"), {"currencyID": currency}).text = _num(tax_amount)

    cat = ET.SubElement(sub, _cac("TaxCategory"))
    ET.SubElement(cat, _cbc("ID")).text = cat_code
    ET.SubElement(cat, _cbc("Percent")).text = _num(percent if percent else 0.0)
    if exemption:
        ET.SubElement(cat, _cbc("TaxExemptionReason")).text = exemption
    scheme = ET.SubElement(cat, _cac("TaxScheme"))
    ET.SubElement(scheme, _cbc("ID")).text = "VAT"


def _build_monetary_total(parent: ET.Element, invoice: InvoiceData, currency: str) -> None:
    t = invoice.totals
    net = t.subtotal if t.subtotal is not None else 0.0
    gross = t.grand_total if t.grand_total is not None else net

    node = ET.SubElement(parent, _cac("LegalMonetaryTotal"))
    ET.SubElement(node, _cbc("LineExtensionAmount"), {"currencyID": currency}).text = _num(net)
    ET.SubElement(node, _cbc("TaxExclusiveAmount"), {"currencyID": currency}).text = _num(net)
    ET.SubElement(node, _cbc("TaxInclusiveAmount"), {"currencyID": currency}).text = _num(gross)
    ET.SubElement(node, _cbc("PayableAmount"), {"currencyID": currency}).text = _num(gross)


def _build_invoice_line(parent: ET.Element, idx: int, item, invoice, currency: str) -> None:
    net = item.net_amount
    if net is None and item.unit_price is not None and item.quantity is not None:
        net = item.unit_price * item.quantity
    if net is None:
        net = item.gross_amount if item.gross_amount is not None else 0.0

    percent = _derive_percent(invoice, item)
    cat_code, _ = _tax_category(percent)

    node = ET.SubElement(parent, _cac("InvoiceLine"))
    ET.SubElement(node, _cbc("ID")).text = str(idx)
    ET.SubElement(
        node, _cbc("InvoicedQuantity"), {"unitCode": _DEFAULT_UNIT}
    ).text = _qty(item.quantity)
    ET.SubElement(
        node, _cbc("LineExtensionAmount"), {"currencyID": currency}
    ).text = _num(net)

    it = ET.SubElement(node, _cac("Item"))
    ET.SubElement(it, _cbc("Name")).text = _clean_text(item.description, "Produs/serviciu")
    ctc = ET.SubElement(it, _cac("ClassifiedTaxCategory"))
    ET.SubElement(ctc, _cbc("ID")).text = cat_code
    ET.SubElement(ctc, _cbc("Percent")).text = _num(percent if percent else 0.0)
    scheme = ET.SubElement(ctc, _cac("TaxScheme"))
    ET.SubElement(scheme, _cbc("ID")).text = "VAT"

    price = ET.SubElement(node, _cac("Price"))
    unit_price = item.unit_price if item.unit_price is not None else net
    ET.SubElement(
        price, _cbc("PriceAmount"), {"currencyID": currency}
    ).text = _num(unit_price)


# ---------------------------------------------------------------------------
# Punct de intrare public
# ---------------------------------------------------------------------------
def generate_efactura_xml(invoice_data: Union[InvoiceData, dict]) -> str:
    """
    Genereaza factura in format e-Factura (UBL 2.1, profil RO_CIUS).

    Args:
        invoice_data: model `InvoiceData` sau dict (validat prin Pydantic).

    Returns:
        Stringul XML UBL, pretty-print, UTF-8.

    Raises:
        TypeError: daca tipul argumentului nu este suportat.
    """
    if isinstance(invoice_data, dict):
        invoice_data = InvoiceData.model_validate(invoice_data)
    elif not isinstance(invoice_data, InvoiceData):
        raise TypeError(
            "generate_efactura_xml asteapta InvoiceData sau dict. "
            f"Primit: {type(invoice_data).__name__}"
        )

    currency = (_clean_text(invoice_data.currency, "") or _DEFAULT_CURRENCY).upper()[:3]

    root = ET.Element(f"{{{_UBL}}}Invoice")

    ET.SubElement(root, _cbc("CustomizationID")).text = _CUSTOMIZATION_ID
    ET.SubElement(root, _cbc("ID")).text = _clean_text(invoice_data.invoice_number, "0")
    ET.SubElement(root, _cbc("IssueDate")).text = _iso_date(invoice_data.invoice_date)
    if invoice_data.due_date:
        due = _iso_date(invoice_data.due_date)
        ET.SubElement(root, _cbc("DueDate")).text = due
    ET.SubElement(root, _cbc("InvoiceTypeCode")).text = "380"
    ET.SubElement(root, _cbc("DocumentCurrencyCode")).text = currency

    sup_off = (
        invoice_data.supplier_verification.address
        if invoice_data.supplier_verification else None
    )
    cus_off = (
        invoice_data.customer_verification.address
        if invoice_data.customer_verification else None
    )
    _build_party(
        root, "AccountingSupplierParty",
        invoice_data.supplier.name, invoice_data.supplier.tax_id,
        invoice_data.supplier.registration_number, invoice_data.supplier.address,
        official_address=sup_off,
    )
    _build_party(
        root, "AccountingCustomerParty",
        invoice_data.customer.name, invoice_data.customer.tax_id,
        invoice_data.customer.registration_number, invoice_data.customer.address,
        official_address=cus_off,
    )

    _build_tax_total(root, invoice_data, currency)
    _build_monetary_total(root, invoice_data, currency)

    items = invoice_data.items or []
    if not items:
        # e-Factura cere cel putin o linie; cream una din totaluri.
        from .schema import InvoiceItem
        items = [InvoiceItem(
            description="Produs/serviciu",
            net_amount=invoice_data.totals.subtotal,
            gross_amount=invoice_data.totals.grand_total,
        )]
    for i, item in enumerate(items, start=1):
        _build_invoice_line(root, i, item, invoice_data, currency)

    raw = ET.tostring(root, encoding="utf-8", xml_declaration=False)
    pretty = minidom.parseString(raw).toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")
    lines = [ln for ln in pretty.splitlines() if ln.strip()]
    return "\n".join(lines) + "\n"
