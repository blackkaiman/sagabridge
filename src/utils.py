# src/utils.py
"""
Modul cu functii utilitare folosite in intreaga aplicatie.

Functiile sunt mici, fara stare, si expun operatii repetitive
precum: crearea directoarelor, salvarea fisierelor incarcate,
generarea de nume cu timestamp, curatarea raspunsurilor JSON
care contin markdown si codarea imaginilor in base64.
"""

from __future__ import annotations

import base64
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Union


def ensure_directory(path: Union[str, Path]) -> Path:
    """
    Creeaza un director (recursiv) daca nu exista.

    Args:
        path: calea (string sau Path) catre directorul dorit.

    Returns:
        Obiect Path catre directorul existent / nou creat.
    """
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_uploaded_file(uploaded_file, target_dir: Union[str, Path]) -> Path:
    """
    Salveaza un fisier incarcat prin Streamlit pe disc.

    Args:
        uploaded_file: obiectul UploadedFile returnat de st.file_uploader.
        target_dir: directorul tinta unde se salveaza fisierul.

    Returns:
        Path-ul absolut al fisierului salvat.
    """
    target_dir = ensure_directory(target_dir)

    # Generam un nume unic pentru a evita coliziunea cu fisiere anterioare.
    safe_name = get_timestamped_filename(uploaded_file.name)
    output_path = target_dir / safe_name

    # Citim continutul fisierului incarcat si il scriem pe disc in mod binar.
    with open(output_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    return output_path


def get_timestamped_filename(original_name: str) -> str:
    """
    Genereaza un nume de fisier unic prin prefixarea cu timestamp.

    Exemplu: "factura.pdf" -> "20260504_153012_factura.pdf"

    Args:
        original_name: numele original al fisierului.

    Returns:
        Numele nou, prefixat cu data si ora curenta.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Curatam numele original de caractere problematice pentru sistemul de fisiere.
    clean_name = re.sub(r"[^A-Za-z0-9._-]", "_", original_name)
    return f"{timestamp}_{clean_name}"


def clean_json_response(raw_response: str) -> str:
    """
    Curata un raspuns text care ar trebui sa fie JSON, dar care poate contine
    blocuri Markdown (```json ... ```) sau text adiacent.

    Modelele LLM, chiar daca primesc instructiuni stricte, pot include
    accidental delimitatori de cod sau texte scurte. Aceasta functie elimina
    aceste artefacte si returneaza doar continutul JSON.

    Args:
        raw_response: textul brut returnat de model.

    Returns:
        Stringul JSON curatat, gata pentru `json.loads`.
    """
    if not raw_response:
        return "{}"

    text = raw_response.strip()

    # Eliminam delimitatorii Markdown ```json sau ``` daca exista.
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()

    # Daca textul incepe cu un cuvant si urmeaza un { (sau [), pastram doar
    # portiunea de la primul caracter JSON valid pana la ultimul corespondent.
    first_obj = text.find("{")
    first_arr = text.find("[")
    candidates = [i for i in (first_obj, first_arr) if i != -1]
    if candidates:
        start = min(candidates)
        # Cautam ultimul caracter inchidere corespunzator pentru a fi siguri.
        end_obj = text.rfind("}")
        end_arr = text.rfind("]")
        end = max(end_obj, end_arr)
        if end > start:
            text = text[start:end + 1]

    return text.strip() or "{}"


def parse_json_safe(raw_response: str) -> dict:
    """
    Wrapper care combina `clean_json_response` cu `json.loads`,
    capturand erorile de parsare si returnand un dict gol in caz de esec.

    Args:
        raw_response: textul brut returnat de model.

    Returns:
        Dictionar Python rezultat din parsare, sau {} daca parsarea esueaza.
    """
    cleaned = clean_json_response(raw_response)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {}


def encode_image_to_base64(image_path: Union[str, Path]) -> str:
    """
    Codeaza o imagine de pe disc in format base64 (UTF-8 string).

    Aceasta functie este necesara pentru a transmite imagini catre OpenAI
    Vision API, care asteapta payload-uri base64 in mesajele multimodale.

    Args:
        image_path: calea catre fisierul imagine (PNG, JPG, etc.).

    Returns:
        String base64 reprezentand imaginea.
    """
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")
