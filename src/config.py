# src/config.py
"""
Modul de configurare a aplicatiei.

Acest modul este responsabil cu:
    - incarcarea variabilelor de mediu din fisierul .env;
    - expunerea constantelor de configurare catre celelalte module;
    - validarea prezentei cheii API OpenAI.

Conform principiului "12-factor app", toate datele sensibile (chei API)
sunt tinute in fisierul .env, NU in cod, pentru a evita expunerea
accidentala in repository-uri publice.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Incarcare variabile din fisierul .env aflat in radacina proiectului
# Se cauta automat fisierul .env in directorul curent si parinti.
load_dotenv()

# -----------------------------------------------------------------------------
# Constante pentru directoare
# -----------------------------------------------------------------------------
# Calea absoluta catre radacina proiectului (folosita pentru a construi
# caile celorlalte directoare in mod independent de directorul curent).
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

# Directorul unde sunt salvate temporar fisierele PDF incarcate.
UPLOADS_DIR: Path = PROJECT_ROOT / "data" / "uploads"

# Directorul unde sunt salvate fisierele de iesire (XML, JSON, imagini).
OUTPUTS_DIR: Path = PROJECT_ROOT / "data" / "outputs"

# Directorul cu resurse statice (logo-uri institutionale).
ASSETS_DIR: Path = PROJECT_ROOT / "assets"

# Calea catre logo-ul Universitatii POLITEHNICA Bucuresti.
UPB_LOGO_PATH: Path = ASSETS_DIR / "logo_upb.png"

# Calea catre logo-ul Facultatii FAIMA (Antreprenoriat, Ingineria si
# Managementul Afacerilor).
FAIMA_LOGO_PATH: Path = ASSETS_DIR / "logo_faima.png"

# -----------------------------------------------------------------------------
# Identitate proiect / date academice
# -----------------------------------------------------------------------------
PROJECT_NAME: str = "SAGABridge"
PROJECT_TAGLINE: str = "Invoice Digitalization and Integration with SAGA"

UNIVERSITY: str = "University POLITEHNICA of Bucharest"
FACULTY: str = (
    "Faculty of Entrepreneurship, Business Engineering and Management"
)
MASTER_PROGRAM: str = "Management of Digital Enterprises"

SCIENTIFIC_LEADER_NAME: str = "Conf. dr. ing. Silviu Răileanu"
SCIENTIFIC_LEADER_LINKS: dict = {
    "UPB Profile": "https://aii.pub.ro/cadre-didactice/membrii-titulari/raileanu-silviu/1490/",
    "LinkedIn": "https://ro.linkedin.com/in/silviu-raileanu-b8b46699",
    "ResearchGate": "https://www.researchgate.net/profile/Silviu-Raileanu",
}

AUTHOR_NAME: str = "Ing. David-Adrian Băbțan"
AUTHOR_LINKS: dict = {
    "LinkedIn": "https://www.linkedin.com/in/david-adrian-b-b22aa5205/",
}

DEFENSE_LOCATION: str = "Bucharest"
DEFENSE_DATE: str = "May 2026"

# -----------------------------------------------------------------------------
# Configurare AI local (Ollama + Tesseract)
# -----------------------------------------------------------------------------
# Pentru disertatie folosim un stack 100% local: Ollama pentru LLM si
# Tesseract pentru OCR. Datele facturilor nu parasesc niciodata masina.

# Host-ul serverului Ollama. Default este 11434 (port standard ollama).
OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434").strip()

# Modelul Ollama default (folosit cand utilizatorul nu alege explicit din UI).
# Recomandari:
#   "qwen2.5:3b"     - ~2GB, excelent la structured output, ~25s pe CPU (DEFAULT)
#   "qwen2.5:1.5b"   - ~1GB, mai rapid (~15s), poate rata campuri pe layout-uri complexe
#   "llama3.1:8b"    - ~5GB, mai precis dar mult mai lent pe CPU
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen2.5:3b").strip()

# Limbile folosite de Tesseract. "ron" = romana, "eng" = engleza.
# Necesita instalarea pachetelor: `brew install tesseract tesseract-lang`.
TESSERACT_LANG: str = os.getenv("TESSERACT_LANG", "ron+eng").strip()

# -----------------------------------------------------------------------------
# Parametri de procesare
# -----------------------------------------------------------------------------
# Numarul maxim de pagini PDF procesate pentru a limita consumul API.
MAX_PAGES: int = int(os.getenv("MAX_PAGES", "3"))

# Lungimea minima de text (caractere) pentru a considera ca extragerea locala
# a fost suficienta. Daca textul este mai scurt, se foloseste OpenAI Vision.
MIN_TEXT_LENGTH: int = int(os.getenv("MIN_TEXT_LENGTH", "200"))

# Cuvinte-cheie care indica prezenta unei facturi reale in textul extras.
INVOICE_KEYWORDS: tuple = (
    "factura", "factură", "invoice", "total", "tva", "vat",
    "cui", "subtotal", "iban", "furnizor", "supplier", "client",
    "customer",
)

# -----------------------------------------------------------------------------
# Verificare firma prin API extern (extensia disertatiei)
# -----------------------------------------------------------------------------
# Provider activ pentru verificarea firmei. Valori suportate:
#   "anaf"        -> ANAF public web service (PlatitorTvaRest, gratuit)
#   "vies"        -> VIES (Comisia Europeana, gratuit, validare VAT)
#   "openapi"     -> OpenAPI.ro (commercial, necesita cheie)
#   "listafirme"  -> ListaFirme.ro (commercial, necesita cheie)
COMPANY_API_PROVIDER: str = os.getenv("COMPANY_API_PROVIDER", "anaf").strip()

# Cheia API pentru provider-ul comercial (OpenAPI.ro / ListaFirme.ro).
# Ramane goala daca se foloseste ANAF (care nu necesita autentificare).
COMPANY_API_KEY: str = os.getenv("COMPANY_API_KEY", "").strip()

# URL-ul de baza al provider-ului. Unele plan-uri au domenii proprii.
COMPANY_API_BASE_URL: str = os.getenv("COMPANY_API_BASE_URL", "").strip()

# Token optional pentru ANAF (rate limit mai mare la API protejat).
ANAF_API_TOKEN: str = os.getenv("ANAF_API_TOKEN", "").strip()

# Comutator global pentru pasul de verificare firma.
ENABLE_COMPANY_VERIFICATION: bool = (
    os.getenv("ENABLE_COMPANY_VERIFICATION", "true").strip().lower() == "true"
)

# -----------------------------------------------------------------------------
# Cautare mentiuni online despre firma
# -----------------------------------------------------------------------------
# Provider activ pentru cautare online:
#   "duckduckgo" (default) - free, no key, search via DuckDuckGo HTML
SEARCH_PROVIDER: str = os.getenv("SEARCH_PROVIDER", "duckduckgo").strip()

# Pastrate doar pentru compatibilitate retroactiva, NU sunt folosite default.
GOOGLE_SEARCH_API_KEY: str = os.getenv("GOOGLE_SEARCH_API_KEY", "").strip()
GOOGLE_SEARCH_ENGINE_ID: str = os.getenv("GOOGLE_SEARCH_ENGINE_ID", "").strip()

# Comutator global pentru cautare online.
ENABLE_ONLINE_MENTIONS: bool = (
    os.getenv("ENABLE_ONLINE_MENTIONS", "true").strip().lower() == "true"
)

# Numar maxim de articole/mentiuni returnate (Google CSE permite max. 10).
MAX_ONLINE_MENTIONS: int = int(os.getenv("MAX_ONLINE_MENTIONS", "5"))


def validate_local_stack() -> None:
    """
    Placeholder pentru validari de mediu local. Validarea reala se face
    in `src/local_extractor.py :: check_local_stack()` care vorbeste direct
    cu Tesseract si Ollama. Aplicatia porneste chiar daca acestea lipsesc
    si afiseaza ghidul de instalare in interfata.
    """
    return None
