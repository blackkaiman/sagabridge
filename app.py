# app.py
"""
SAGABridge - Invoice Digitalization and Integration with SAGA

Streamlit interface, refactored for an editorial / academic visual register.
Inspired by Impeccable's anti-slop guidance: tinted neutrals, considered
typography (Fraunces + Geist), no glass cards, no neon glows, no purple
gradients. The page reads like a finely typeset document that happens to
be interactive.
"""

from __future__ import annotations

import base64
import io
import json
import time
import traceback
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import streamlit as st

from src.config import (
    AUTHOR_LINKS,
    AUTHOR_NAME,
    DEFENSE_DATE,
    DEFENSE_LOCATION,
    FACULTY,
    FAIMA_LOGO_PATH,
    MASTER_PROGRAM,
    MAX_PAGES,
    OLLAMA_MODEL,
    OUTPUTS_DIR,
    PROJECT_NAME,
    PROJECT_TAGLINE,
    SCIENTIFIC_LEADER_LINKS,
    SCIENTIFIC_LEADER_NAME,
    UNIVERSITY,
    UPB_LOGO_PATH,
    UPLOADS_DIR,
)
from src.company_news_search import (
    CompanyNewsSearchResult,
    search_company_mentions,
)
from src.company_risk_analyzer import analyze_company_risk
from src.company_verifier import (
    compare_invoice_supplier_with_verified_data,
    verify_company,
)
from src.local_extractor import (
    check_local_stack,
    extract_invoice_from_images,
    extract_invoice_from_text,
)
from src.pdf_processor import (
    convert_pdf_to_images,
    extract_text_from_pdf,
    is_text_sufficient,
)
from src.schema import CompanyVerification
from src.utils import ensure_directory, get_timestamped_filename, save_uploaded_file
from src.validators import (
    InvoiceValidationError,
    XMLValidationError,
    validate_invoice_data,
    validate_xml,
)
from src.xml_generator import generate_invoice_xml


# =============================================================================
# Page configuration
# =============================================================================
st.set_page_config(
    page_title=f"{PROJECT_NAME} — UPB FAIMA",
    page_icon="📑",
    layout="centered",
    initial_sidebar_state="collapsed",
)


# =============================================================================
# Helpers
# =============================================================================
def _img_to_base64(path: Path) -> str:
    if not path.exists():
        return ""
    return base64.b64encode(path.read_bytes()).decode("utf-8")


UPB_B64 = _img_to_base64(UPB_LOGO_PATH)
FAIMA_B64 = _img_to_base64(FAIMA_LOGO_PATH)


# =============================================================================
# Stylesheet — editorial / academic register
# =============================================================================
STYLESHEET = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght,SOFT@9..144,400,50;9..144,500,50;9..144,600,50;9..144,700,50&family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500&display=swap');

:root {
    --ink:        #1B1714;
    --ink-soft:   #4D4538;
    --ink-quiet:  #807766;
    --ink-faint:  #B5AB99;
    --paper:      #FAF7F0;
    --paper-deep: #F2EDE0;
    --paper-warm: #EFE9D7;
    --rule:       #DDD6C2;
    --rule-soft:  #E8E2D2;
    --surface:    #FFFFFF;
    --accent:     #7A1820;   /* UPB heritage red */
    --accent-soft:#9E2A33;
    --accent-wash:#F4E8E5;
    --ok:         #2C5F3B;
    --ok-wash:    #E5EDE2;
    --warn:       #8C5A1B;
    --warn-wash:  #F4ECDC;
}

/* Global background — warm cream paper */
.stApp {
    background: var(--paper);
    color: var(--ink);
    font-family: 'Geist', -apple-system, BlinkMacSystemFont, sans-serif !important;
    font-feature-settings: 'ss01', 'cv11';
}
[data-testid="stMain"] { background: transparent !important; }

/* Container width — editorial reading width */
.block-container {
    padding-top: 2.5rem !important;
    padding-bottom: 4rem !important;
    max-width: 1080px !important;
}

/* Hide Streamlit chrome */
#MainMenu, footer { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent !important; height: 0 !important; }
[data-testid="stSidebarCollapsedControl"] { display: none !important; }
section[data-testid="stSidebar"] { display: none !important; }

/* ---------- TITLE PAGE ---------- */
.titlepage {
    border-top: 1px solid var(--rule);
    border-bottom: 1px solid var(--rule);
    padding: 2rem 0 2.4rem;
    margin-bottom: 3rem;
    display: grid;
    grid-template-columns: 90px 1fr 90px;
    grid-gap: 2.5rem;
    align-items: center;
}
.titlepage .crest { display:flex; align-items:center; justify-content:center; }
.titlepage .crest img { width: 90px; height: auto; }
.titlepage .core { text-align: center; }

.titlepage .institution {
    font-family: 'Geist', sans-serif;
    font-size: 0.72rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--ink-quiet);
    font-weight: 500;
    margin-bottom: 0.3rem;
}
.titlepage .faculty {
    font-family: 'Geist', sans-serif;
    font-size: 0.84rem;
    color: var(--ink-soft);
    line-height: 1.55;
    margin-bottom: 0.2rem;
}
.titlepage .programme {
    font-family: 'Fraunces', serif;
    font-style: italic;
    font-size: 0.92rem;
    color: var(--ink-soft);
    margin-bottom: 1.4rem;
}
.titlepage h1.project-name {
    font-family: 'Fraunces', serif;
    font-weight: 600;
    font-size: clamp(2.6rem, 5vw, 3.8rem);
    line-height: 1;
    letter-spacing: -0.02em;
    color: var(--ink);
    margin: 0 0 0.5rem 0;
    font-variation-settings: "opsz" 144, "SOFT" 30;
}
.titlepage .project-tagline {
    font-family: 'Fraunces', serif;
    font-style: italic;
    font-size: 1.1rem;
    color: var(--ink-soft);
    font-weight: 400;
    max-width: 36ch;
    margin: 0 auto;
    line-height: 1.4;
}

/* ---------- BIBLIO STRIP ---------- */
.biblio {
    display: grid;
    grid-template-columns: 1fr auto 1fr auto 1fr;
    gap: 1.5rem;
    align-items: start;
    margin-bottom: 3rem;
    font-size: 0.84rem;
    line-height: 1.55;
}
.biblio .col { color: var(--ink-soft); }
.biblio .label {
    font-family: 'Geist', sans-serif;
    font-size: 0.66rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--ink-quiet);
    font-weight: 500;
    margin-bottom: 0.3rem;
}
.biblio .name {
    font-family: 'Fraunces', serif;
    font-weight: 500;
    color: var(--ink);
    font-size: 0.96rem;
    margin-bottom: 0.25rem;
    font-variation-settings: "opsz" 24;
}
.biblio a {
    color: var(--accent);
    text-decoration: none;
    border-bottom: 1px solid transparent;
    transition: border-color 120ms ease;
}
.biblio a:hover { border-bottom-color: var(--accent); }
.biblio .sep {
    width: 1px; background: var(--rule); align-self: stretch;
}

/* ---------- SECTION HEADERS ---------- */
.section {
    margin: 3rem 0 2rem;
}
.section-num {
    font-family: 'Fraunces', serif;
    font-size: 0.92rem;
    color: var(--accent);
    font-weight: 500;
    margin-right: 0.6rem;
    font-feature-settings: 'lnum';
}
.section h2 {
    font-family: 'Fraunces', serif;
    font-weight: 600;
    font-size: 1.65rem;
    color: var(--ink) !important;
    margin: 0 0 0.4rem 0 !important;
    letter-spacing: -0.01em;
    line-height: 1.15;
    font-variation-settings: "opsz" 60;
}
.section .lede {
    font-family: 'Geist', sans-serif;
    color: var(--ink-soft);
    font-size: 0.96rem;
    line-height: 1.6;
    max-width: 62ch;
    margin: 0 0 1.5rem 0;
}

/* Hairline */
.rule { border: none; border-top: 1px solid var(--rule); margin: 0 0 1.5rem; }

/* ---------- FILE UPLOADER ---------- */
[data-testid="stFileUploader"] {
    margin-top: 0.5rem;
}
[data-testid="stFileUploaderDropzone"] {
    background: var(--surface) !important;
    border: 1px dashed var(--rule) !important;
    border-radius: 6px !important;
    padding: 1.6rem !important;
    transition: border-color 150ms ease, background 150ms ease;
}
[data-testid="stFileUploaderDropzone"]:hover {
    border-color: var(--accent) !important;
    background: var(--accent-wash) !important;
}
[data-testid="stFileUploaderDropzoneInstructions"] * {
    font-family: 'Geist', sans-serif !important;
    color: var(--ink-soft) !important;
    font-size: 0.92rem !important;
}
[data-testid="stFileUploaderDropzone"] button {
    background: transparent !important;
    border: 1px solid var(--ink-quiet) !important;
    color: var(--ink) !important;
    font-family: 'Geist', sans-serif !important;
    font-weight: 500 !important;
    font-size: 0.85rem !important;
    border-radius: 4px !important;
    padding: 0.4rem 1rem !important;
    box-shadow: none !important;
}
[data-testid="stFileUploaderDropzone"] button:hover {
    border-color: var(--ink) !important;
    background: var(--paper-warm) !important;
}

/* Uploaded file row */
[data-testid="stFileUploaderFile"] {
    background: var(--paper-deep) !important;
    border-radius: 4px !important;
    padding: 0.5rem 0.7rem !important;
}

/* ---------- BUTTONS ---------- */
.stButton > button, .stDownloadButton > button {
    font-family: 'Geist', sans-serif !important;
    font-weight: 500 !important;
    font-size: 0.92rem !important;
    border-radius: 4px !important;
    padding: 0.55rem 1.2rem !important;
    border: 1px solid var(--ink) !important;
    background: var(--ink) !important;
    color: var(--paper) !important;
    box-shadow: none !important;
    transition: background 150ms ease, transform 150ms ease;
    letter-spacing: 0.005em;
}
.stButton > button:hover, .stDownloadButton > button:hover {
    background: var(--accent) !important;
    border-color: var(--accent) !important;
    transform: none;
}
.stButton > button:disabled,
.stButton > button[disabled] {
    background: transparent !important;
    color: var(--ink-quiet) !important;
    border-color: var(--rule) !important;
}

/* Primary buttons accent */
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {
    background: var(--accent) !important;
    border-color: var(--accent) !important;
    color: var(--paper) !important;
}
.stButton > button[kind="primary"]:hover, .stDownloadButton > button[kind="primary"]:hover {
    background: var(--accent-soft) !important;
    border-color: var(--accent-soft) !important;
}

/* ---------- TABS ---------- */
.stTabs [data-baseweb="tab-list"] {
    background: transparent !important;
    border-bottom: 1px solid var(--rule) !important;
    gap: 0 !important;
    padding: 0 !important;
    margin-bottom: 1.4rem !important;
}
.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    border: none !important;
    border-bottom: 2px solid transparent !important;
    border-radius: 0 !important;
    padding: 0.7rem 1.2rem !important;
    color: var(--ink-quiet) !important;
    font-family: 'Geist', sans-serif !important;
    font-weight: 500 !important;
    font-size: 0.88rem !important;
    margin-right: 0.4rem !important;
    letter-spacing: 0.005em;
}
.stTabs [data-baseweb="tab"]:hover {
    color: var(--ink) !important;
}
.stTabs [aria-selected="true"] {
    color: var(--ink) !important;
    border-bottom: 2px solid var(--accent) !important;
    box-shadow: none !important;
    background: transparent !important;
}

/* ---------- CODE BLOCKS ---------- */
.stCode, [data-testid="stCodeBlock"] {
    background: var(--paper-deep) !important;
    border: 1px solid var(--rule-soft) !important;
    border-radius: 6px !important;
    padding: 0.4rem !important;
}
.stCode pre, [data-testid="stCodeBlock"] pre {
    background: transparent !important;
    font-family: 'Geist Mono', 'IBM Plex Mono', monospace !important;
    font-size: 0.82rem !important;
    color: var(--ink) !important;
    line-height: 1.6 !important;
}
code { font-family: 'Geist Mono', monospace !important; }

/* ---------- TEXT AREA ---------- */
[data-baseweb="textarea"] textarea {
    background: var(--paper-deep) !important;
    color: var(--ink) !important;
    border: 1px solid var(--rule-soft) !important;
    border-radius: 6px !important;
    font-family: 'Geist Mono', monospace !important;
    font-size: 0.82rem !important;
    line-height: 1.6;
}

/* ---------- ALERTS ---------- */
[data-testid="stAlert"] {
    border-radius: 6px !important;
    border-left-width: 3px !important;
    background: var(--paper-deep) !important;
    color: var(--ink) !important;
    font-family: 'Geist', sans-serif !important;
    font-size: 0.9rem !important;
    box-shadow: none !important;
}
[data-testid="stAlert"][data-baseweb="notification"][kind="success"] {
    background: var(--ok-wash) !important;
    border-left-color: var(--ok) !important;
    color: var(--ink) !important;
}
[data-testid="stAlert"] svg { color: inherit !important; }

/* ---------- PROGRESS BAR ---------- */
.stProgress > div > div { background: var(--rule-soft) !important; height: 4px !important; }
.stProgress > div > div > div { background: var(--accent) !important; box-shadow: none !important; }
.stProgress p { color: var(--ink-quiet) !important; font-size: 0.82rem !important; font-family: 'Geist', sans-serif !important; }

/* ---------- KEY-VALUE LINES ---------- */
.kv {
    display: grid;
    grid-template-columns: 11rem 1fr;
    gap: 0.4rem 1.2rem;
    padding: 0.45rem 0;
    border-bottom: 1px solid var(--rule-soft);
    font-size: 0.92rem;
    line-height: 1.5;
}
.kv:last-child { border-bottom: none; }
.kv .k {
    font-family: 'Geist', sans-serif;
    color: var(--ink-quiet);
    font-size: 0.82rem;
    letter-spacing: 0.04em;
}
.kv .v {
    font-family: 'Fraunces', serif;
    color: var(--ink);
    font-size: 0.98rem;
    font-variation-settings: "opsz" 24;
}
.kv .v.num { font-feature-settings: 'tnum', 'lnum'; }
.kv .v.accent { color: var(--accent); font-weight: 600; }
.kv .v.muted { color: var(--ink-quiet); font-style: italic; }

/* ---------- META ROW (run summary) ---------- */
.runmeta {
    display: flex;
    flex-wrap: wrap;
    gap: 0 2rem;
    padding: 0.8rem 0;
    border-top: 1px solid var(--rule);
    border-bottom: 1px solid var(--rule);
    margin: 1rem 0 1.6rem 0;
    font-size: 0.84rem;
}
.runmeta .item {
    display: flex; flex-direction: column; gap: 2px; padding: 0.2rem 0;
}
.runmeta .label {
    font-family: 'Geist', sans-serif;
    font-size: 0.66rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--ink-quiet);
    font-weight: 500;
}
.runmeta .value {
    font-family: 'Fraunces', serif;
    font-size: 1rem;
    color: var(--ink);
    font-feature-settings: 'tnum', 'lnum';
}
.runmeta .value.accent { color: var(--accent); }

/* ---------- IDLE STATES ---------- */
.idle-block {
    padding: 2.5rem 0;
    text-align: center;
    color: var(--ink-quiet);
    font-family: 'Fraunces', serif;
    font-style: italic;
    font-size: 1rem;
    border-top: 1px solid var(--rule-soft);
    border-bottom: 1px solid var(--rule-soft);
}

/* ---------- COLOPHON / FOOTER ---------- */
.colophon {
    margin-top: 4rem;
    padding-top: 1.4rem;
    border-top: 1px solid var(--rule);
    font-family: 'Geist', sans-serif;
    font-size: 0.78rem;
    color: var(--ink-quiet);
    line-height: 1.7;
    text-align: left;
    letter-spacing: 0.005em;
}
.colophon strong { color: var(--ink-soft); font-weight: 600; }
.colophon a { color: var(--accent); text-decoration: none; }
.colophon a:hover { text-decoration: underline; }
.colophon .place {
    font-family: 'Fraunces', serif;
    font-style: italic;
    font-size: 0.88rem;
    margin-top: 0.4rem;
    color: var(--ink-soft);
}

/* ---------- ANIMATIONS — quiet, editorial, never decorative ---------- */
@keyframes fadeUp {
    from { opacity: 0; transform: translateY(6px); }
    to   { opacity: 1; transform: translateY(0); }
}
@keyframes fadeIn {
    from { opacity: 0; }
    to   { opacity: 1; }
}

/* Initial reveal — short, calm, no stagger overload */
.titlepage   { animation: fadeUp 420ms cubic-bezier(0.2, 0.6, 0.2, 1) both; }
.biblio      { animation: fadeUp 420ms cubic-bezier(0.2, 0.6, 0.2, 1) 60ms both; }

/* Sections that appear later (after Analyze) animate too */
.section     { animation: fadeUp 380ms cubic-bezier(0.2, 0.6, 0.2, 1) both; }
.runmeta     { animation: fadeUp 380ms cubic-bezier(0.2, 0.6, 0.2, 1) both; }

/* Tab content cross-fade */
.stTabs [role="tabpanel"] { animation: fadeIn 220ms ease both; }

/* Hover refinement only — no continuous animations */
.section-num { transition: color 200ms ease; }
.section h2:hover .section-num { color: var(--accent-soft); }

[data-testid="stFileUploaderDropzone"] {
    transition: border-color 200ms ease, background 200ms ease;
}

.stButton > button, .stDownloadButton > button {
    transition: background 180ms ease, color 180ms ease,
                border-color 180ms ease, box-shadow 180ms ease !important;
}

/* Honor reduced-motion preference */
@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
        animation-duration: 0.01ms !important;
        transition-duration: 0.01ms !important;
    }
}

/* ---------- PIPELINE VISUALIZER (loading state) ---------- */
@keyframes pulseDot {
    0%, 100% { box-shadow: 0 0 0 0 rgba(122, 24, 32, 0.45); }
    50%      { box-shadow: 0 0 0 6px rgba(122, 24, 32, 0); }
}
@keyframes fillSlide {
    from { transform: scaleX(0); }
    to   { transform: scaleX(1); }
}

.pipeline-viz {
    margin: 1rem 0 2rem 0;
    padding: 1.4rem 1.6rem 1.6rem 1.6rem;
    background: var(--paper-deep);
    border: 1px solid var(--rule-soft);
    border-radius: 8px;
    animation: fadeIn 280ms ease both;
}

/* The horizontal track + accent fill */
.pl-track {
    position: relative;
    height: 2px;
    background: var(--rule);
    margin: 0 1rem 1.4rem 1rem;
    border-radius: 1px;
    overflow: hidden;
}
.pl-fill {
    position: absolute; inset: 0;
    background: var(--accent);
    transform-origin: left center;
    transform: scaleX(0);
    transition: width 600ms cubic-bezier(0.2, 0.6, 0.2, 1);
}
/* Width is set inline; this keeps the fill animated when width changes */
.pl-track .pl-fill { transform: none; transition: width 600ms cubic-bezier(0.2, 0.6, 0.2, 1); }

/* The four stations */
.pl-stations {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 0.6rem;
}
.pl-station {
    text-align: center;
    padding: 0.4rem 0.4rem 0.2rem 0.4rem;
    transition: opacity 260ms ease;
}
.pl-station.pl-pending { opacity: 0.45; }
.pl-station.pl-active  { opacity: 1; }
.pl-station.pl-done    { opacity: 0.85; }

.pl-dot {
    width: 28px; height: 28px;
    margin: 0 auto 0.5rem auto;
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-family: 'Geist', sans-serif;
    font-weight: 600;
    font-size: 0.78rem;
    line-height: 1;
    transition: background 260ms ease, color 260ms ease,
                border-color 260ms ease, transform 260ms ease;
}
.pl-pending .pl-dot {
    border: 1.5px solid var(--rule);
    background: var(--paper);
    color: transparent;
}
.pl-active .pl-dot {
    border: 1.5px solid var(--accent);
    background: var(--paper);
    color: var(--accent);
    animation: pulseDot 1.6s ease-in-out infinite;
}
.pl-done .pl-dot {
    border: 1.5px solid var(--accent);
    background: var(--accent);
    color: var(--paper);
    transform: scale(0.92);
}

.pl-num {
    font-family: 'Geist', sans-serif;
    font-size: 0.62rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--ink-quiet);
    font-feature-settings: 'lnum';
    margin-bottom: 0.15rem;
}
.pl-label {
    font-family: 'Fraunces', serif;
    font-weight: 600;
    font-size: 1rem;
    color: var(--ink);
    line-height: 1.1;
    font-variation-settings: "opsz" 24;
    margin-bottom: 0.15rem;
}
.pl-active .pl-label { color: var(--accent); }
.pl-pending .pl-label { color: var(--ink-quiet); font-weight: 500; }

.pl-hint {
    font-family: 'Geist', sans-serif;
    font-size: 0.74rem;
    color: var(--ink-quiet);
    line-height: 1.35;
}

.pl-message {
    margin-top: 1.2rem;
    padding-top: 0.8rem;
    border-top: 1px solid var(--rule-soft);
    text-align: center;
    font-family: 'Fraunces', serif;
    font-style: italic;
    font-size: 0.92rem;
    color: var(--ink-soft);
    font-variation-settings: "opsz" 14;
}

/* On narrow screens, stack the stations 2x2 */
@media (max-width: 680px) {
    .pl-stations { grid-template-columns: 1fr 1fr; gap: 1rem 0.5rem; }
}

/* ---------- PARTY HEADINGS (supplier vs customer) ---------- */
.party-heading {
    margin: 1.4rem 0 0.8rem 0;
    animation: fadeUp 500ms cubic-bezier(0.2, 0.6, 0.2, 1) both;
}
.party-eyebrow {
    font-family: 'Geist', sans-serif;
    font-size: 0.66rem;
    letter-spacing: 0.22em;
    text-transform: uppercase;
    color: var(--ink-quiet);
    font-weight: 500;
}
.party-heading h3 {
    font-family: 'Fraunces', serif !important;
    font-weight: 600 !important;
    font-size: 1.5rem !important;
    color: var(--ink) !important;
    margin: 0.2rem 0 0 0 !important;
    line-height: 1.15 !important;
    font-variation-settings: "opsz" 60;
    letter-spacing: -0.01em;
}
.party-heading .role {
    font-family: 'Fraunces', serif;
    font-style: italic;
    font-weight: 400;
    font-size: 1rem;
    color: var(--ink-quiet);
    margin-left: 0.4rem;
    font-variation-settings: "opsz" 14;
}
.party-name {
    font-family: 'Fraunces', serif;
    font-size: 1rem;
    color: var(--ink-soft);
    margin-top: 0.2rem;
    font-variation-settings: "opsz" 14;
}
.party-divider {
    border: none;
    border-top: 1px solid var(--rule);
    margin: 3rem 0 0.5rem 0;
}

/* ---------- VERIFICATION / RISK BANDS ---------- */
.risk-band {
    display: flex; align-items: baseline; justify-content: space-between;
    padding: 1rem 1.2rem;
    border-radius: 6px;
    margin: 1rem 0 1.4rem;
    border-left: 3px solid var(--rule);
    background: var(--paper-deep);
}
.risk-band.low    { background: var(--ok-wash);  border-left-color: var(--ok); }
.risk-band.medium { background: var(--warn-wash);border-left-color: var(--warn); }
.risk-band.high   { background: var(--accent-wash); border-left-color: var(--accent); }
.risk-band .lhs { display: flex; flex-direction: column; gap: 0.2rem; }
.risk-band .rhs { text-align: right; }
.risk-band .label-mini {
    font-size: 0.66rem; letter-spacing: 0.18em; text-transform: uppercase;
    color: var(--ink-quiet); font-weight: 500;
}
.risk-band .level {
    font-family: 'Fraunces', serif; font-weight: 600; font-size: 1.4rem;
    text-transform: capitalize;
    font-variation-settings: "opsz" 36;
}
.risk-band .level.low { color: var(--ok); }
.risk-band .level.medium { color: var(--warn); }
.risk-band .level.high { color: var(--accent); }
.risk-band .score {
    font-family: 'Fraunces', serif; font-weight: 700; font-size: 2.4rem;
    line-height: 1; color: var(--ink);
    font-feature-settings: 'tnum', 'lnum';
    font-variation-settings: "opsz" 96;
}
.risk-band .score-suffix {
    font-family: 'Geist', sans-serif; font-size: 0.9rem;
    color: var(--ink-quiet); margin-left: 0.2rem;
}

/* warnings list */
.warnings {
    list-style: none; padding: 0; margin: 0 0 1.4rem 0;
}
.warnings li {
    font-family: 'Geist', sans-serif; font-size: 0.88rem;
    color: var(--ink-soft); line-height: 1.55;
    padding: 0.45rem 0 0.45rem 1.2rem;
    border-bottom: 1px solid var(--rule-soft);
    position: relative;
}
.warnings li::before {
    content: "—"; position: absolute; left: 0; color: var(--ink-quiet);
}

/* mention card - editorial citation block */
.mention {
    padding: 1rem 0;
    border-bottom: 1px solid var(--rule-soft);
}
.mention:last-child { border-bottom: none; }
.mention .src-row {
    font-family: 'Geist', sans-serif; font-size: 0.74rem;
    letter-spacing: 0.1em; text-transform: uppercase;
    color: var(--ink-quiet); margin-bottom: 0.3rem;
}
.mention .src-row .domain { color: var(--accent); font-weight: 500; }
.mention .src-row .date { color: var(--ink-faint); margin-left: 0.6rem; }
.mention h4 {
    font-family: 'Fraunces', serif !important; font-weight: 600 !important;
    font-size: 1.05rem !important; margin: 0 0 0.3rem 0 !important;
    color: var(--ink) !important; line-height: 1.3 !important;
    font-variation-settings: "opsz" 24;
}
.mention h4 a {
    color: var(--ink); text-decoration: none;
    border-bottom: 1px solid var(--rule);
}
.mention h4 a:hover {
    color: var(--accent); border-bottom-color: var(--accent);
}
.mention .snippet {
    font-family: 'Fraunces', serif; font-style: italic;
    font-size: 0.92rem; color: var(--ink-soft);
    line-height: 1.55; margin: 0;
    font-variation-settings: "opsz" 14;
}

/* mention-type badge (website / registry / social / news) */
.mtype {
    display: inline-block;
    font-family: 'Geist', sans-serif;
    font-size: 0.62rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    font-weight: 600;
    padding: 0.12rem 0.45rem;
    border-radius: 2px;
    margin-right: 0.6rem;
    border: 1px solid var(--rule);
    color: var(--ink-quiet);
    vertical-align: middle;
}
.mtype-website  { color: var(--accent); border-color: var(--accent); background: var(--accent-wash); }
.mtype-registry { color: var(--ink); border-color: var(--ink-soft); background: var(--paper-warm); }
.mtype-social   { color: var(--ink-soft); border-color: var(--ink-quiet); background: var(--paper-deep); }
.mtype-news     { color: var(--ink-quiet); }
.mtype-other    { color: var(--ink-faint); }

/* match indicator inline pill */
.match-pill {
    display: inline-block;
    font-family: 'Geist', sans-serif;
    font-size: 0.7rem; font-weight: 500;
    padding: 0.15rem 0.5rem;
    border-radius: 3px;
    letter-spacing: 0.04em;
    margin-left: 0.5rem;
    border: 1px solid var(--rule);
}
.match-pill.match  { color: var(--ok); border-color: var(--ok); background: var(--ok-wash); }
.match-pill.mismatch { color: var(--accent); border-color: var(--accent); background: var(--accent-wash); }
.match-pill.unknown { color: var(--ink-quiet); }

/* responsiveness: collapse 3-col biblio strip */
@media (max-width: 760px) {
    .biblio { grid-template-columns: 1fr; gap: 1rem; }
    .biblio .sep { display: none; }
    .titlepage { grid-template-columns: 1fr; gap: 1.2rem; }
    .titlepage .crest img { width: 64px; }
    .kv { grid-template-columns: 1fr; }
}
</style>
"""


# =============================================================================
# Render helpers
# =============================================================================
def render_titlepage() -> None:
    """Editorial title page: institution above, project below, two crests sides."""
    upb = (f'<img src="data:image/png;base64,{UPB_B64}" alt="UPB" />'
           if UPB_B64 else "")
    faima = (f'<img src="data:image/png;base64,{FAIMA_B64}" alt="FAIMA" />'
             if FAIMA_B64 else "")

    st.markdown(
        f"""
        <div class="titlepage">
            <div class="crest">{upb}</div>
            <div class="core">
                <div class="institution">{UNIVERSITY}</div>
                <div class="faculty">{FACULTY}</div>
                <div class="programme">{MASTER_PROGRAM}</div>
                <h1 class="project-name">{PROJECT_NAME}</h1>
                <div class="project-tagline">{PROJECT_TAGLINE}</div>
            </div>
            <div class="crest">{faima}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_biblio_strip() -> None:
    """Bibliographic strip with author, advisor, place & date."""
    leader_links = " · ".join(
        f'<a href="{u}" target="_blank">{n}</a>'
        for n, u in SCIENTIFIC_LEADER_LINKS.items()
    )
    author_links = " · ".join(
        f'<a href="{u}" target="_blank">{n}</a>'
        for n, u in AUTHOR_LINKS.items()
    )

    st.markdown(
        f"""
        <div class="biblio">
            <div class="col">
                <div class="label">Author</div>
                <div class="name">{AUTHOR_NAME}</div>
                <div>{author_links}</div>
            </div>
            <div class="sep"></div>
            <div class="col">
                <div class="label">Scientific advisor</div>
                <div class="name">{SCIENTIFIC_LEADER_NAME}</div>
                <div>{leader_links}</div>
            </div>
            <div class="sep"></div>
            <div class="col">
                <div class="label">Place &amp; date</div>
                <div class="name">{DEFENSE_LOCATION}</div>
                <div>{DEFENSE_DATE}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_section_head(num: str, title: str, lede: str) -> None:
    """A numbered section header, like a printed paper."""
    st.markdown(
        f"""
        <div class="section">
            <h2><span class="section-num">{num}</span>{title}</h2>
            <div class="lede">{lede}</div>
        </div>
        <hr class="rule" />
        """,
        unsafe_allow_html=True,
    )


def render_kv(rows: list[tuple[str, str, str]]) -> None:
    """
    rows: list of (label, value, modifier_class)
    modifier_class is one of '', 'accent', 'muted', 'num'
    """
    parts = ['<div>']
    for label, value, mod in rows:
        cls = "v"
        if mod:
            cls += f" {mod}"
        parts.append(
            f'<div class="kv"><div class="k">{label}</div>'
            f'<div class="{cls}">{value}</div></div>'
        )
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def render_runmeta(items: list[tuple[str, str, bool]]) -> None:
    """A single horizontal strip with run-level metadata."""
    parts = ['<div class="runmeta">']
    for label, value, is_accent in items:
        cls = "value accent" if is_accent else "value"
        parts.append(
            f'<div class="item"><span class="label">{label}</span>'
            f'<span class="{cls}">{value}</span></div>'
        )
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


PIPELINE_STAGES = (
    ("01", "Read",     "Parsing the PDF"),
    ("02", "Extract",  "Structuring the data"),
    ("03", "Verify",   "Cross-checking both parties"),
    ("04", "Package",  "Building the XML"),
)


def render_pipeline_visualizer(active_idx: int, message: str = "") -> str:
    """
    Build HTML for the pipeline visualizer.

    active_idx semantics:
        -1  = nothing yet (idle, all pending)
         0  = reading
         1  = extracting
         2  = verifying
         3  = packaging
         4  = all stages complete (every station green check)

    The fill bar reflects how many stations are at least active. Active
    stations carry a subtle pulse; completed ones a filled disc with check.
    """
    n = len(PIPELINE_STAGES)
    if active_idx < 0:
        progress_pct = 0
    else:
        progress_pct = max(8, min(100, (active_idx + 0.5) / n * 100))

    stations_html_parts = []
    for i, (num, label, hint) in enumerate(PIPELINE_STAGES):
        if i < active_idx:
            state = "done"
            mark = "✓"
        elif i == active_idx:
            state = "active"
            mark = "●"
        else:
            state = "pending"
            mark = ""

        stations_html_parts.append(
            f'<div class="pl-station pl-{state}">'
            f'  <div class="pl-dot">{mark}</div>'
            f'  <div class="pl-num">{num}</div>'
            f'  <div class="pl-label">{label}</div>'
            f'  <div class="pl-hint">{hint}</div>'
            f"</div>"
        )

    msg_html = (
        f'<div class="pl-message">{message}</div>' if message else ""
    )

    return (
        '<div class="pipeline-viz">'
        '<div class="pl-track">'
        f'<div class="pl-fill" style="width: {progress_pct}%"></div>'
        "</div>"
        '<div class="pl-stations">'
        + "".join(stations_html_parts)
        + "</div>"
        + msg_html
        + "</div>"
    )


def _match_pill(value) -> str:
    """Render a small inline pill indicating match / mismatch / unknown."""
    if value is True:
        return '<span class="match-pill match">match</span>'
    if value is False:
        return '<span class="match-pill mismatch">mismatch</span>'
    return '<span class="match-pill unknown">n/a</span>'


def render_company_verification(
    verification: CompanyVerification,
    comparison: dict,
    risk,
    news_result: CompanyNewsSearchResult,
) -> None:
    """
    Render the Company Verification tab — typeset in the editorial register
    of the rest of the page (no glass cards, hairlines, Fraunces+Geist).
    """
    # ---- 1) Status block at the top ----
    status = verification.status
    if verification.verified:
        st.success(
            f"Company verified by **{verification.source or 'external API'}**."
        )
    elif status == "not_configured":
        st.warning(
            "Company verification API is not configured. "
            "Set COMPANY_API_PROVIDER and COMPANY_API_KEY in `.env` to enable."
        )
    elif status == "disabled":
        st.info("Company verification is disabled (ENABLE_COMPANY_VERIFICATION=false).")
    elif status == "insufficient_data":
        st.warning(
            "The invoice does not contain enough data to verify the supplier "
            "(need at least a tax_id or a company name)."
        )
    elif status == "not_found":
        st.warning(
            f"Company not found in {verification.source or 'the registry'}. "
            "The supplier might be unregistered, foreign, or the tax ID is wrong."
        )
    elif status == "error":
        st.error(
            f"Verification error: {verification.error or 'unknown'}. "
            "The pipeline continued without external verification."
        )
    else:
        st.info(f"Verification status: {status}.")

    # ---- 2) Risk band ----
    if risk is not None:
        level = (risk.risk_level or "low").lower()
        st.markdown(
            f"""
            <div class="risk-band {level}">
                <div class="lhs">
                    <span class="label-mini">Risk level</span>
                    <span class="level {level}">{risk.risk_level}</span>
                </div>
                <div class="rhs">
                    <span class="label-mini">Heuristic score</span><br>
                    <span class="score">{risk.risk_score}</span>
                    <span class="score-suffix">/ 100</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ---- 3) Official record vs. invoice ----
    if verification.verified:
        st.markdown(
            """
            <div class="section" style="margin-top: 1.6rem;">
                <h2 style="font-size:1.2rem; margin: 0 0 0.4rem 0;">
                    <span class="section-num">·</span>Official record
                </h2>
            </div>
            <hr class="rule" />
            """,
            unsafe_allow_html=True,
        )

        rows: list[tuple[str, str, str]] = [
            ("Source", verification.source or "—", ""),
            ("Official name", (verification.official_name or "—") +
                _match_pill(comparison.get("name_match")), ""),
            ("Tax ID / CIF", (verification.tax_id or "—") +
                _match_pill(comparison.get("tax_id_match")), ""),
            ("Reg. number", verification.registration_number or "—", ""),
            ("Address", (verification.address or "—") +
                _match_pill(comparison.get("address_match")), ""),
            ("VAT status", verification.vat_status or "—", ""),
            ("Company status", verification.company_status or "—", ""),
            ("CAEN code", verification.caen_code or "—", ""),
        ]
        # We re-use the kv layout but allow HTML in values (because of pills).
        parts = []
        for label, value, _ in rows:
            parts.append(
                f'<div class="kv"><div class="k">{label}</div>'
                f'<div class="v">{value}</div></div>'
            )
        st.markdown("".join(parts), unsafe_allow_html=True)

        # Raw API response (collapsed by default for transparency)
        if verification.raw_response:
            with st.expander("Show raw API response (debug)"):
                st.json(verification.raw_response)

    # ---- 4) Warnings ----
    if risk is not None and risk.warnings:
        st.markdown(
            '<div class="section" style="margin-top:1.8rem;">'
            '<h2 style="font-size:1.2rem; margin: 0 0 0.4rem 0;">'
            '<span class="section-num">·</span>Warnings</h2></div>'
            '<hr class="rule" />',
            unsafe_allow_html=True,
        )
        items = "".join(f"<li>{w}</li>" for w in risk.warnings)
        st.markdown(f'<ul class="warnings">{items}</ul>', unsafe_allow_html=True)

    # ---- 5) Online mentions ----
    st.markdown(
        '<div class="section" style="margin-top:1.8rem;">'
        '<h2 style="font-size:1.2rem; margin: 0 0 0.4rem 0;">'
        '<span class="section-num">·</span>Online mentions</h2></div>'
        '<hr class="rule" />',
        unsafe_allow_html=True,
    )

    if news_result.status == "disabled":
        st.info("Online presence search is disabled.")
    elif news_result.status == "not_configured":
        st.warning(
            "Search backend is not configured. "
            "Set OPENAI_API_KEY (or GOOGLE_SEARCH_API_KEY for the CSE backend) in `.env`."
        )
    elif news_result.status == "insufficient_data":
        st.info("Not enough data to construct a meaningful query.")
    elif news_result.status == "error":
        st.error(f"Search unavailable: {news_result.error or 'unknown error'}.")
    elif news_result.status == "no_results" or not news_result.mentions:
        st.info("No public mentions were found.")
    else:
        # Sortam mentiunile pentru a aseza site-ul oficial mai sus, apoi
        # registrele, retelele sociale si in final presa. In acelasi timp
        # pastram ordinea relativa a categoriilor.
        type_order = {
            "website": 0, "registry": 1, "social": 2, "news": 3, "other": 4,
        }
        sorted_mentions = sorted(
            news_result.mentions,
            key=lambda m: type_order.get(m.mention_type or "news", 5),
        )
        # Bifam ce categorii avem ca sa scriem un mic rezumat sus.
        kinds_present = sorted({(m.mention_type or "news") for m in sorted_mentions})
        kind_labels = {
            "website": "official website",
            "registry": "registry",
            "social": "social",
            "news": "news",
            "other": "other",
        }
        summary = ", ".join(kind_labels.get(k, k) for k in
                            sorted(kinds_present, key=lambda k: type_order.get(k, 5)))
        st.caption(
            f"{len(sorted_mentions)} result(s) — covering: {summary}"
        )
        parts = []
        for m in sorted_mentions:
            title = m.title or "(untitled)"
            url = m.url or "#"
            domain = m.source or "—"
            date = f' · {m.published_date[:10]}' if m.published_date else ""
            snippet = m.snippet or ""
            mtype = (m.mention_type or "news").lower()
            badge_label = kind_labels.get(mtype, mtype)
            parts.append(
                f"""
                <div class="mention">
                    <div class="src-row">
                        <span class="mtype mtype-{mtype}">{badge_label}</span>
                        <span class="domain">{domain}</span>
                        <span class="date">{date}</span>
                    </div>
                    <h4><a href="{url}" target="_blank" rel="noopener">{title}</a></h4>
                    <p class="snippet">{snippet}</p>
                </div>
                """
            )
        st.markdown("".join(parts), unsafe_allow_html=True)


def render_colophon() -> None:
    leader_links = " · ".join(
        f'<a href="{u}" target="_blank">{n}</a>'
        for n, u in SCIENTIFIC_LEADER_LINKS.items()
    )
    author_links = " · ".join(
        f'<a href="{u}" target="_blank">{n}</a>'
        for n, u in AUTHOR_LINKS.items()
    )
    st.markdown(
        f"""
        <div class="colophon">
            <strong>{PROJECT_NAME}</strong> — {PROJECT_TAGLINE}.
            A master's dissertation project at the {FACULTY},
            {UNIVERSITY}, programme <em>{MASTER_PROGRAM}</em>.
            Written by {AUTHOR_NAME} ({author_links}) under the supervision of
            {SCIENTIFIC_LEADER_NAME} ({leader_links}).
            <div class="place">{DEFENSE_LOCATION}, {DEFENSE_DATE}.</div>
            <div style="margin-top:0.6rem; color:var(--ink-faint); font-size:0.74rem;">
                Pipeline: PyMuPDF for digital text · Tesseract OCR for scanned
                pages · Ollama {OLLAMA_MODEL} for local semantic extraction ·
                ANAF / VIES for company verification · DuckDuckGo for online
                mentions · Pydantic for validation · Python ElementTree for
                SAGA-compatible XML. <strong>100% on-device.</strong>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# =============================================================================
# Pipeline
# =============================================================================
def run_pipeline(pdf_path: Path, model: str | None = None) -> dict:
    """Run the full extraction pipeline. `model` overrides OLLAMA_MODEL."""
    raw_text = extract_text_from_pdf(pdf_path)

    if is_text_sufficient(raw_text):
        method = "text"
        data = extract_invoice_from_text(raw_text, model=model)
        image_paths: list = []
    else:
        method = "vision"
        images_subdir = OUTPUTS_DIR / f"images_{pdf_path.stem}"
        ensure_directory(images_subdir)
        image_paths = convert_pdf_to_images(
            pdf_path=pdf_path, output_dir=images_subdir, max_pages=MAX_PAGES,
        )
        data = extract_invoice_from_images(image_paths, model=model)

    return {"raw_text": raw_text, "method": method,
            "image_paths": image_paths, "data": data}


# =============================================================================
# Application
# =============================================================================
def main() -> None:
    st.markdown(STYLESHEET, unsafe_allow_html=True)

    ensure_directory(UPLOADS_DIR)
    ensure_directory(OUTPUTS_DIR)

    render_titlepage()
    render_biblio_strip()

    # ----- §1 Upload -----
    render_section_head(
        "§1",
        "Upload invoice(s)",
        "Drop a PDF or select multiple files for batch processing. "
        "Single mode includes full company verification and risk analysis. "
        "Bulk mode skips verification and generates one XML per file, "
        "packaged as a ZIP archive — faster for large batches.",
    )

    mode = st.radio(
        "Mode",
        ["Single invoice", "Bulk import"],
        horizontal=True,
        label_visibility="collapsed",
    )
    st.markdown("<div style='height:0.5rem;'></div>", unsafe_allow_html=True)

    # ── Bulk mode ───────────────────────────────────────────────────────────
    if mode == "Bulk import":
        uploaded_files = st.file_uploader(
            "Select invoice PDFs",
            type=["pdf"],
            accept_multiple_files=True,
            label_visibility="collapsed",
        )

        if not uploaded_files:
            st.markdown(
                '<div class="idle-block">Select multiple PDFs and press '
                '<em>Analyze invoices</em> to begin.</div>',
                unsafe_allow_html=True,
            )
            render_colophon()
            return

        st.caption(
            f"{len(uploaded_files)} file(s) selected — "
            f"{sum(f.size for f in uploaded_files) / 1024:.0f} KB total"
        )
        st.markdown("<div style='height:0.5rem;'></div>", unsafe_allow_html=True)

        # Invalidate cached results when the file set changes.
        _bulk_key = tuple(sorted(f.name + str(f.size) for f in uploaded_files))
        if st.session_state.get("_bulk_key") != _bulk_key:
            st.session_state["_bulk_key"] = _bulk_key
            st.session_state["_bulk_results"] = None

        analyze_bulk = st.button(
            f"Analyze {len(uploaded_files)} invoice(s)",
            type="primary",
        )

        if analyze_bulk:
            render_section_head(
                "§2",
                "Batch processing",
                f"Running {len(uploaded_files)} file(s) through the extraction pipeline.",
            )
            _prog = st.progress(0, text="Starting…")
            _status = st.empty()
            _bulk: list[dict] = []

            for _i, _uf in enumerate(uploaded_files):
                _prog.progress(
                    _i / len(uploaded_files),
                    text=f"[{_i + 1}/{len(uploaded_files)}] {_uf.name}",
                )
                _status.info(f"⏳ Extracting **{_uf.name}**…")
                _t0 = time.time()
                try:
                    _pdf_path = save_uploaded_file(_uf, UPLOADS_DIR)
                    _res = run_pipeline(_pdf_path)
                    _inv = validate_invoice_data(_res["data"])
                    _xml_str = generate_invoice_xml(_inv)
                    validate_xml(_xml_str)
                    _xml_fn = get_timestamped_filename(Path(_uf.name).stem + ".xml")
                    (OUTPUTS_DIR / _xml_fn).write_text(_xml_str, encoding="utf-8")
                    _bulk.append({
                        "name": _uf.name, "status": "ok",
                        "supplier": _inv.supplier.name or "—",
                        "customer": _inv.customer.name or "—",
                        "total": (
                            f"{_inv.totals.grand_total:,.2f} "
                            f"{_inv.currency or ''}".strip()
                            if _inv.totals.grand_total is not None else "—"
                        ),
                        "time": time.time() - _t0,
                        "xml_str": _xml_str, "xml_fn": _xml_fn, "error": None,
                    })
                except Exception as _exc:  # noqa: BLE001
                    _bulk.append({
                        "name": _uf.name, "status": "error",
                        "supplier": "—", "customer": "—", "total": "—",
                        "time": time.time() - _t0,
                        "xml_str": None, "xml_fn": None, "error": str(_exc),
                    })

            _prog.progress(1.0, text="All done!")
            _status.empty()
            st.session_state["_bulk_results"] = _bulk

        if st.session_state.get("_bulk_results"):
            _res_list: list[dict] = st.session_state["_bulk_results"]
            _ok = [r for r in _res_list if r["status"] == "ok"]
            _err = [r for r in _res_list if r["status"] == "error"]
            render_runmeta([
                ("Files", str(len(_res_list)), False),
                ("Successful", str(len(_ok)), True),
                ("Errors", str(len(_err)), bool(_err)),
                ("Total time", f"{sum(r['time'] for r in _res_list):.1f} s", False),
            ])

            # Per-file result rows
            for _r in _res_list:
                _icon = "✅" if _r["status"] == "ok" else "❌"
                _c1, _c2, _c3, _c4, _c5 = st.columns([3, 2, 2, 1, 1])
                with _c1:
                    st.markdown(f"{_icon} **{_r['name']}**")
                    if _r["error"]:
                        st.caption(f"↳ {_r['error'][:120]}")
                with _c2:
                    st.caption(_r["supplier"])
                with _c3:
                    st.caption(_r["customer"])
                with _c4:
                    st.caption(_r["total"])
                with _c5:
                    if _r["xml_str"]:
                        st.download_button(
                            "XML",
                            data=_r["xml_str"].encode("utf-8"),
                            file_name=_r["xml_fn"],
                            mime="application/xml",
                            key=f"dl_bulk_{_r['xml_fn']}",
                        )

            # ZIP archive with all successful XMLs
            if _ok:
                _zip_buf = io.BytesIO()
                with zipfile.ZipFile(_zip_buf, "w", zipfile.ZIP_DEFLATED) as _zf:
                    for _r in _ok:
                        _zf.writestr(_r["xml_fn"], _r["xml_str"])
                _zip_buf.seek(0)
                st.markdown("<div style='height:1rem;'></div>", unsafe_allow_html=True)
                st.download_button(
                    f"⬇ Download all {len(_ok)} XML file(s) as ZIP",
                    data=_zip_buf.getvalue(),
                    file_name="sagabridge_invoices.zip",
                    mime="application/zip",
                    type="primary",
                    key="dl_bulk_zip",
                )

        render_colophon()
        return

    # ── Single invoice mode ──────────────────────────────────────────────────
    uploaded_file = st.file_uploader(
        "Select an invoice PDF",
        type=["pdf"],
        label_visibility="collapsed",
    )

    analyze = False
    if uploaded_file is not None:
        st.markdown(
            f"""
            <div class="kv">
                <div class="k">File</div>
                <div class="v">{uploaded_file.name}</div>
            </div>
            <div class="kv">
                <div class="k">Size</div>
                <div class="v num">{uploaded_file.size / 1024:.1f} KB</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        # Selector model — utilizatorul alege intre viteza (1.5b) si precizie (3b).
        st.markdown("<div style='height:0.8rem;'></div>", unsafe_allow_html=True)
        accuracy = st.radio(
            label="Extraction accuracy",
            options=("Fast", "Precise"),
            index=1,  # default Precise — calitate inainte de viteza
            horizontal=True,
            help=(
                "Fast: qwen2.5:1.5b (~15s) — bun pentru facturi simple, "
                "poate rata campuri pe layout-uri complexe.\n"
                "Precise: qwen2.5:3b (~25s) — recomandat pentru demo si "
                "facturi cu mai multe firme/sectiuni."
            ),
        )
        selected_model = "qwen2.5:1.5b" if accuracy == "Fast" else "qwen2.5:3b"
        st.caption(f"Model: `{selected_model}`")

        st.markdown("<div style='height:0.8rem;'></div>", unsafe_allow_html=True)
        analyze = st.button(
            "Analyze invoice",
            type="primary",
            use_container_width=False,
        )

    if uploaded_file is None or not analyze:
        st.markdown(
            '<div class="idle-block">Upload a PDF and press '
            '<em>Analyze invoice</em> to begin.</div>',
            unsafe_allow_html=True,
        )
        render_colophon()
        return

    # ----- §2 Result -----
    render_section_head(
        "§2",
        "Result",
        "Reading the document, structuring the data, verifying both parties, "
        "packaging it for SAGA.",
    )

    start = time.time()
    pl_slot = st.empty()  # placeholder pe care il rescriem la fiecare stage
    pl_slot.markdown(
        render_pipeline_visualizer(0, "Saving uploaded file…"),
        unsafe_allow_html=True,
    )

    try:
        pdf_path = save_uploaded_file(uploaded_file, UPLOADS_DIR)
        pl_slot.markdown(
            render_pipeline_visualizer(0, f"Reading {pdf_path.name}"),
            unsafe_allow_html=True,
        )

        # Stage 0 → 1: extracting (cu model-ul ales de utilizator)
        result = run_pipeline(pdf_path, model=selected_model)
        method_label = "digital text" if result["method"] == "text" else "vision OCR"
        pl_slot.markdown(
            render_pipeline_visualizer(
                1,
                f"Structured data extracted via {method_label}.",
            ),
            unsafe_allow_html=True,
        )

        invoice = validate_invoice_data(result["data"])

        # Stage 2: verification (parallel)
        pl_slot.markdown(
            render_pipeline_visualizer(
                2, "Verifying both parties against public registries…"
            ),
            unsafe_allow_html=True,
        )

        def _audit_party(party):
            """
            Run the full verification chain for a single party.

            Optimization: verify_company (~2-3s) and search_company_mentions
            (~5-7s) are independent — they share no data dependency. We run
            them in parallel within the party, cutting the per-party time
            from sum(ver, news) to max(ver, news).
            """
            with ThreadPoolExecutor(max_workers=2) as inner_pool:
                ver_fut = inner_pool.submit(
                    verify_company, company_name=party.name, tax_id=party.tax_id,
                )
                news_fut = inner_pool.submit(
                    search_company_mentions,
                    company_name=party.name, tax_id=party.tax_id,
                )
                ver = ver_fut.result()
                news = news_fut.result()
            cmp = compare_invoice_supplier_with_verified_data(party, ver)
            risk = analyze_company_risk(ver, cmp, news)
            return ver, cmp, news, risk

        with ThreadPoolExecutor(max_workers=2) as pool:
            sup_future = pool.submit(_audit_party, invoice.supplier)
            cus_future = pool.submit(_audit_party, invoice.customer)
            sup_verification, sup_comparison, sup_news, sup_risk = sup_future.result()
            cus_verification, cus_comparison, cus_news, cus_risk = cus_future.result()

        # Atasam rezultatele in InvoiceData inainte de generarea XML.
        invoice.supplier_verification = sup_verification
        invoice.supplier_online_mentions = list(sup_news.mentions or [])
        invoice.supplier_risk_analysis = sup_risk
        invoice.customer_verification = cus_verification
        invoice.customer_online_mentions = list(cus_news.mentions or [])
        invoice.customer_risk_analysis = cus_risk

        # Pastrate ca aliasuri pentru compatibilitate cu apelurile vechi.
        verification = sup_verification
        comparison = sup_comparison
        news_result = sup_news
        risk = sup_risk

        # Stage 3: packaging
        pl_slot.markdown(
            render_pipeline_visualizer(3, "Building the XML output…"),
            unsafe_allow_html=True,
        )
        xml_str = generate_invoice_xml(invoice)
        validate_xml(xml_str)

        xml_filename = get_timestamped_filename(
            Path(uploaded_file.name).stem + ".xml"
        )
        xml_path = OUTPUTS_DIR / xml_filename
        xml_path.write_text(xml_str, encoding="utf-8")

        elapsed = time.time() - start
        # Final state — all four stations done.
        pl_slot.markdown(
            render_pipeline_visualizer(
                4, f"Complete in {elapsed:.1f}s · saved as {xml_path.name}"
            ),
            unsafe_allow_html=True,
        )

        # Compact run-level metadata strip
        method_label = "Digital text" if result["method"] == "text" else "Vision (OCR)"
        fields = sum(1 for v in invoice.supplier.model_dump().values() if v) + \
                 sum(1 for v in invoice.customer.model_dump().values() if v) + \
                 sum(1 for v in (invoice.invoice_number, invoice.invoice_date,
                                 invoice.due_date, invoice.currency) if v)

        render_runmeta([
            ("Method", method_label, False),
            ("Fields detected", str(fields), True),
            ("Items", str(len(invoice.items)), False),
            ("Time", f"{elapsed:.1f} s", False),
        ])

        # Compact summary as KV (no card around it)
        s, c, t = invoice.supplier, invoice.customer, invoice.totals
        rows: list[tuple[str, str, str]] = [
            ("Invoice number", invoice.invoice_number or "—",
             "" if invoice.invoice_number else "muted"),
            ("Invoice date", invoice.invoice_date or "—",
             "" if invoice.invoice_date else "muted"),
            ("Supplier", s.name or "—", "" if s.name else "muted"),
            ("Customer", c.name or "—", "" if c.name else "muted"),
        ]
        if t.subtotal is not None:
            rows.append(("Subtotal", f"{t.subtotal:,.2f} {invoice.currency or ''}".strip(), "num"))
        if t.vat_total is not None:
            rows.append(("VAT total", f"{t.vat_total:,.2f} {invoice.currency or ''}".strip(), "num"))
        rows.append((
            "Total",
            f"{t.grand_total:,.2f} {invoice.currency or ''}".strip()
            if t.grand_total is not None else "—",
            "accent num" if t.grand_total is not None else "muted",
        ))
        render_kv(rows)

        st.markdown("<div style='height:2rem;'></div>", unsafe_allow_html=True)

        # Tabs
        tab_xml, tab_json, tab_text, tab_verif = st.tabs(
            ["XML output", "Structured data", "Source text", "Company verification"]
        )

        with tab_verif:
            # Layout: doua sectiuni stivuite vertical, una pentru fiecare firma.
            st.markdown(
                '<div class="party-heading">'
                '<span class="party-eyebrow">Party 1 of 2</span>'
                '<h3>Supplier <span class="role">prestator</span></h3>'
                f'<div class="party-name">{invoice.supplier.name or "(name not extracted)"}</div>'
                '</div>',
                unsafe_allow_html=True,
            )
            render_company_verification(
                verification=sup_verification,
                comparison=sup_comparison,
                risk=sup_risk,
                news_result=sup_news,
            )

            st.markdown(
                '<hr class="party-divider" />'
                '<div class="party-heading">'
                '<span class="party-eyebrow">Party 2 of 2</span>'
                '<h3>Customer <span class="role">beneficiar</span></h3>'
                f'<div class="party-name">{invoice.customer.name or "(name not extracted)"}</div>'
                '</div>',
                unsafe_allow_html=True,
            )
            render_company_verification(
                verification=cus_verification,
                comparison=cus_comparison,
                risk=cus_risk,
                news_result=cus_news,
            )

        with tab_xml:
            st.code(xml_str, language="xml")
            st.download_button(
                "Download XML",
                data=xml_str.encode("utf-8"),
                file_name=xml_filename,
                mime="application/xml",
                type="primary",
            )

        with tab_json:
            json_str = json.dumps(invoice.model_dump(), ensure_ascii=False, indent=2)
            st.code(json_str, language="json")
            st.download_button(
                "Download JSON",
                data=json_str.encode("utf-8"),
                file_name=Path(xml_filename).with_suffix(".json").name,
                mime="application/json",
            )

        with tab_text:
            if result["method"] == "vision":
                st.info(
                    f"Local text extraction was insufficient. Tesseract OCR was "
                    f"used on {len(result['image_paths'])} rendered page(s)."
                )
            st.text_area(
                "Source text",
                value=result["raw_text"] or "(no local text was available)",
                height=400,
                label_visibility="collapsed",
            )

    except FileNotFoundError as exc:
        st.error(f"File not found: {exc}")
    except ValueError as exc:
        st.error(f"Configuration error: {exc}")
    except InvoiceValidationError as exc:
        st.error(f"Validation failed: {exc}")
    except XMLValidationError as exc:
        st.error(f"XML serialization error: {exc}")
    except RuntimeError as exc:
        st.error(f"Pipeline error: {exc}")
    except Exception as exc:  # noqa: BLE001
        st.error("An unexpected error occurred. Details below.")
        st.exception(exc)
        traceback.print_exc()

    finally:
        render_colophon()


if __name__ == "__main__":
    main()
