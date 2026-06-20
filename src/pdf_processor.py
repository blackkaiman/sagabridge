# src/pdf_processor.py
"""
Modul de procesare a fisierelor PDF.

Responsabilitati:
    - extragere text din PDF-uri digitale folosind PyMuPDF (fitz);
    - evaluarea suficientei textului extras (decizie locala vs. AI Vision);
    - conversia paginilor PDF in imagini PNG pentru analiza vizuala.

Aceasta etapa este "primul nivel" al pipeline-ului hibrid: incercam
sa extragem date direct din PDF (rapid, fara cost API). Doar daca
extragerea esueaza, escaladam catre OpenAI Vision.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Union

import fitz  # PyMuPDF

from .config import INVOICE_KEYWORDS, MAX_PAGES, MIN_TEXT_LENGTH
from .utils import ensure_directory


def extract_text_from_pdf(pdf_path: Union[str, Path]) -> str:
    """
    Extrage textul din toate paginile unui PDF folosind PyMuPDF.

    Args:
        pdf_path: calea catre fisierul PDF.

    Returns:
        Textul concatenat din toate paginile (string). Daca PDF-ul nu poate
        fi deschis, se returneaza un string gol si se loggeaza eroarea.

    Raises:
        FileNotFoundError: daca fisierul PDF nu exista.
        RuntimeError: daca PDF-ul este corupt sau nu poate fi parsat.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"Fisierul PDF nu exista: {pdf_path}")

    try:
        # `fitz.open` deschide PDF-ul; folosim un context manager pentru a
        # ne asigura ca resursele sunt eliberate corect.
        text_chunks: List[str] = []
        with fitz.open(pdf_path) as doc:
            for page_index, page in enumerate(doc):
                # `get_text("text")` returneaza textul "plain" al paginii.
                page_text = page.get_text("text") or ""
                text_chunks.append(page_text)

        return "\n".join(text_chunks).strip()

    except Exception as exc:
        raise RuntimeError(
            f"Eroare la extragerea textului din PDF: {exc}"
        ) from exc


def is_text_sufficient(text: str) -> bool:
    """
    Determina daca textul extras dintr-un PDF este suficient pentru a putea
    fi analizat de modelul OpenAI fara a recurge la procesarea imaginii.

    Criterii folosite (ambele trebuie sa fie indeplinite):
        1. Lungimea textului >= MIN_TEXT_LENGTH (din .env).
        2. Textul contine cel putin un cuvant-cheie specific facturilor
           (factura, invoice, total, tva, cui, vat etc.).

    Args:
        text: textul extras din PDF.

    Returns:
        True daca textul este suficient pentru analiza; False altfel
        (in care caz pipeline-ul va escalada catre OpenAI Vision).
    """
    if not text or len(text.strip()) < MIN_TEXT_LENGTH:
        return False

    lowered = text.lower()
    return any(keyword in lowered for keyword in INVOICE_KEYWORDS)


def convert_pdf_to_images(
    pdf_path: Union[str, Path],
    output_dir: Union[str, Path],
    max_pages: int = MAX_PAGES,
    dpi: int = 150,
) -> List[Path]:
    """
    Converteste primele `max_pages` pagini ale unui PDF in imagini PNG.

    Imaginile sunt salvate in `output_dir` cu nume de forma
    `page_001.png`, `page_002.png` etc.

    Args:
        pdf_path: calea catre fisierul PDF de procesat.
        output_dir: directorul unde vor fi salvate imaginile rezultate.
        max_pages: numarul maxim de pagini de convertit (limiteaza costurile).
        dpi: rezolutia de randare. Valori mai mari -> imagini mai clare,
             dar fisiere mai mari si tokenuri Vision mai numeroase.

    Returns:
        Lista cu Path-urile catre imaginile generate.

    Raises:
        FileNotFoundError: daca PDF-ul de intrare nu exista.
        RuntimeError: daca apare o eroare la randare.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"Fisierul PDF nu exista: {pdf_path}")

    output_dir = ensure_directory(output_dir)
    image_paths: List[Path] = []

    try:
        # Calculam factorul de scalare in functie de DPI dorit.
        # PDF-ul este 72 DPI nativ, deci 200/72 ~= 2.78 mareste imaginea.
        zoom = dpi / 72
        matrix = fitz.Matrix(zoom, zoom)

        with fitz.open(pdf_path) as doc:
            num_pages = min(len(doc), max_pages)
            for page_idx in range(num_pages):
                page = doc.load_page(page_idx)
                pix = page.get_pixmap(matrix=matrix, alpha=False)

                image_filename = f"page_{page_idx + 1:03d}.png"
                image_path = output_dir / image_filename
                pix.save(str(image_path))
                image_paths.append(image_path)

        return image_paths

    except Exception as exc:
        raise RuntimeError(
            f"Eroare la conversia PDF -> imagini: {exc}"
        ) from exc
