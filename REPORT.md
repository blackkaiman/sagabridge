# SAGABridge — Technical Report

### Invoice Digitalization and Integration with SAGA

**University POLITEHNICA of Bucharest**
**Faculty of Entrepreneurship, Business Engineering and Management**
Master programme: *Management of Digital Enterprises*

**Author:** Ing. David-Adrian Băbțan
**Scientific advisor:** Conf. dr. ing. Silviu Răileanu
*Bucharest, May 2026*

---

## 1. Abstract

SAGABridge is a desktop/web application that automates the digitalization of invoices and prepares them for direct integration into the **SAGA** Romanian accounting software. The user uploads a PDF (digital or scanned), and the application produces a SAGA-compatible XML file enriched with an external verification of the supplier company and a heuristic risk indicator.

The novelty of the work lies not in any single technique, but in the **hybrid composition** of three layers: (i) deterministic local parsing of digital PDFs, (ii) Large-Language-Model-based extraction with vision fallback for scanned documents, and (iii) external verification against public registries and the open web — with heuristic risk scoring. The result is an end-to-end pipeline that converts an unstructured PDF into a structured, validated, externally-cross-checked XML in under five seconds per document.

---

## 2. Problem statement and motivation

Romanian SMEs receive invoices in dozens of layouts, frequently as scanned PDFs. Manual data entry into SAGA is slow, error-prone, and creates a bottleneck at month-end closing. Existing OCR products tend to be either layout-dependent (templates-per-supplier, brittle), or layout-agnostic but require costly enterprise licenses.

A more recent option — using a multimodal LLM (OpenAI GPT-4 Vision class) — is robust to layout variation, but raises three concerns: (i) cost and latency on large invoice batches, (ii) hallucinations on partially-readable fields, and (iii) absence of a check against the supplier's actual identity. SAGABridge addresses all three: a **digital-first** path that uses the LLM only when local extraction fails, **strict JSON-schema constraints** in the prompt, and **post-extraction verification** against public registries.

---

## 3. Architecture overview

```
PDF input
   │
   ▼
[PyMuPDF text extraction] ──── sufficient text? ───► [OpenAI text → JSON]
   │                                                         │
   │ (insufficient / scanned)                                │
   ▼                                                         ▼
[PDF → PNG render]                                  [Pydantic validation]
   │                                                         │
   ▼                                                         │
[OpenAI Vision → JSON] ─────────────────────────────────────┘
                                                             │
                                                             ▼
                          ┌──────────────────────┐
                          │ Supplier extraction  │
                          └──────────┬───────────┘
                                     │
            ┌────────────────────────┼────────────────────────┐
            ▼                        ▼                        ▼
     [verify_company()]   [search_company_mentions()]  [analyze_company_risk()]
     OpenAPI.ro / ANAF /     Google Custom Search       heuristic 0–100 score
     ListaFirme.ro
            │                        │                        │
            └────────────────────────┼────────────────────────┘
                                     ▼
                       [XML serialization (ElementTree)]
                                     │
                                     ▼
                         [SAGA-compatible XML download]
```

### 3.1 Why a hybrid pipeline

A pure-OCR approach (Tesseract, Google Vision plain OCR) is layout-blind: it returns a stream of text without semantic labels. A pure-LLM approach is expensive on every page. The hybrid approach uses local PyMuPDF for digital PDFs (free, instant), and routes only scanned PDFs to OpenAI Vision. The decision is made at runtime by `is_text_sufficient(text)`, which checks both length (≥ 200 characters) and the presence of at least one invoice-specific keyword (`factura`, `invoice`, `total`, `tva`, `cui`, `vat`, `iban`, `furnizor`, etc.).

### 3.2 Why JSON-mode extraction

The prompt to OpenAI explicitly enforces a JSON schema with `response_format={"type":"json_object"}`. The schema mirrors the Pydantic models in `src/schema.py`, which means the LLM output and the application's runtime types are the same artifact, validated by the same source of truth. This eliminates an entire class of integration bugs.

### 3.3 Why deterministic XML

The XML generation is **not** done by the LLM. Once a Pydantic-validated `InvoiceData` object is in memory, the XML is built by a small ElementTree-based generator (`src/xml_generator.py`). This guarantees that the XML is byte-for-byte reproducible from the same JSON, which is important for auditability in an accounting context.

---

## 4. Technology choices and rationale

| Layer | Technology | Why |
|-------|------------|-----|
| GUI | Streamlit | Single-file Python UI, instant deploy, no JS toolchain. Sufficient for an academic demo. |
| Local PDF parsing | PyMuPDF (`fitz`) | Fastest reliable Python library for both text extraction and page rendering to PNG. |
| AI extraction | OpenAI `gpt-4.1-mini` | Multimodal (text + image), strict JSON mode, low latency. Selected via `OPENAI_MODEL` so the user can swap to `gpt-4o-mini`, `gpt-4o`, etc. without code change. |
| Validation | Pydantic v2 | Single source of truth for both schema and runtime types; produces clear error messages. |
| XML | `xml.etree.ElementTree` + `minidom` pretty-print | No third-party dependency; fully deterministic; auditable. |
| Company verification | `requests` against ANAF/OpenAPI.ro/ListaFirme.ro | Read-only, public-or-licensed APIs; no scraping. |
| Online mentions | Google Custom Search JSON API | First-party, license-clean alternative to scraping; respects publishers' robots policies. |
| Secrets | `python-dotenv` + `.env` (gitignored) | 12-factor-app compliance; no secret in source code. |

---

## 5. Pipeline stages in detail

### 5.1 Local text extraction

`src/pdf_processor.py :: extract_text_from_pdf(pdf_path)` opens the PDF with PyMuPDF and concatenates `page.get_text("text")` from each page. The function raises typed exceptions on missing/corrupt files; the upstream caller (`app.py`) catches them and surfaces them to the user without crashing.

### 5.2 Sufficiency check

`is_text_sufficient(text)` returns `True` only when **both** the length threshold is met AND at least one invoice-specific keyword is found. The keyword list is bilingual (Romanian + English) so foreign suppliers are still recognized. The thresholds (`MIN_TEXT_LENGTH`, `INVOICE_KEYWORDS`) are tunable via `.env`.

### 5.3 PDF → PNG fallback

`convert_pdf_to_images(pdf_path, output_dir, max_pages=3, dpi=200)` renders the first 3 pages at 200 DPI as PNG. The cap on pages is a deliberate cost-control: most invoices fit in 1–2 pages, and Vision tokens scale with image area.

### 5.4 LLM extraction

`src/openai_extractor.py` exposes two entry points:

- `extract_invoice_from_text(raw_text)` — sends a single chat completion with a system prompt that describes the role and a user prompt that contains the schema and the raw text.
- `extract_invoice_from_images(image_paths)` — encodes each PNG to base64 and embeds it in a multimodal user message with the same schema description.

The system prompt explicitly forbids hallucination ("Extragi DOAR informatii prezente efectiv in factura — nu inventezi si nu deduci date care nu sunt scrise"). `temperature=0` is enforced for reproducibility. The response is parsed with `parse_json_safe()` (a defensive helper that strips Markdown fences and locates the JSON braces, in case the model accidentally adds explanation).

### 5.5 Validation

`validate_invoice_data(data)` instantiates `InvoiceData` from the parsed dict. Pydantic produces `ValidationError` for type mismatches; these are caught and re-raised as `InvoiceValidationError` with a human-readable message.

### 5.6 Company verification

`src/company_verifier.py :: verify_company(name, tax_id)` dispatches to one of three providers, selected by `COMPANY_API_PROVIDER`:

- **OpenAPI.ro** — `GET /v1/companies/{cif}` with `x-api-key` (or Bearer, switchable). Returns canonical name, address, VAT status, CAEN, registration number.
- **ANAF** — `POST` to `webservicesp.anaf.ro/PlatitorTvaRest/api/v8/ws/tva` with payload `[{"cui": int, "data": "YYYY-MM-DD"}]`. The optional `ANAF_API_TOKEN` is sent as Bearer for higher rate limits.
- **ListaFirme.ro** — `GET /info-firma.asp?cui=...&key=...`.

All three return structured `CompanyVerification` instances with a uniform `status` field. **Failure is never raised** — if the API key is missing, the network is down, or the provider returns 404/500, the function returns a result with `status="not_configured" / "error" / "not_found"`. The pipeline continues and the user sees a clearly labeled status in the UI.

`compare_invoice_supplier_with_verified_data()` performs three loose comparisons:

- **name match** — alphanumeric-only, case-folded, with substring tolerance to absorb suffixes like "SRL" / "S.R.L." that may be written differently.
- **tax_id match** — exact after RO-prefix stripping and whitespace removal.
- **address match** — token-overlap >= 1/3 of the smaller token set, to tolerate "Str./Strada", "nr./număr", missing diacritics.

### 5.7 Online mentions

`src/company_news_search.py :: search_company_mentions()` dispatches to one of two backends, switchable via `SEARCH_PROVIDER`:

#### 5.7.a OpenAI web_search_preview (default)

The default backend uses **OpenAI's Responses API with the `web_search_preview` tool**. A single `client.responses.create()` call issues an instruction in which the model is asked to search the web for press articles, news, official notices, and legal cases mentioning the supplier — with explicit attention to risk signals (`insolvență`, `faliment`, `executare`, `datorii`, `anchetă`). The model returns a strict JSON object with up to `MAX_ONLINE_MENTIONS` results, each containing `title`, `url`, `snippet`, `source`, and `published_date`. The instruction explicitly forbids fabrication: if no genuine mentions are found, the model is told to return `{"results": []}`.

The implementation also reads any URL annotations attached to the response (the model exposes citations via `response.output[*].content[*].annotations` of type `url_citation`) and uses them to backfill missing source domains or augment the result set when the JSON list is short. Results are deduplicated by URL.

This backend has three operational advantages over a classic search-engine API:

1. **Single-credential**: the same `OPENAI_API_KEY` already used for invoice extraction is sufficient. There is no separate Google Cloud project, no billing setup, no Programmable Search Engine to maintain.
2. **Better Romanian-press recall**: the model is more flexible at synthesizing relevant articles across diverse Romanian news domains than a CSE keyword query.
3. **Risk-aware prompting**: by naming the categories of interest in the prompt, the model surfaces articles with risk signals first — the heuristic risk analyzer then weights them appropriately.

The trade-off is latency (~5–8 seconds vs. ~300 ms for CSE) and per-call cost (a few cents per search vs. free up to 100/day for CSE). For an academic dissertation tool, the latency is acceptable; for a production deployment with high invoice volume, the CSE backend can be re-enabled by setting `SEARCH_PROVIDER=google_cse`.

#### 5.7.b Google Custom Search JSON API (fallback)

The fallback backend issues a single GET to `googleapis.com/customsearch/v1` with a quoted-name + quoted-CUI OR-clause and bilingual press keywords (`știri OR articole OR presă OR news`). The response is reduced to at most `MAX_ONLINE_MENTIONS=5` results, each retaining only `title`, `link`, `snippet`, `displayLink`, and a best-effort `published_date` extracted from `pagemap.metatags`. **No article bodies are fetched** in either backend.

#### 5.7.c Why the design pivoted from CSE to OpenAI search

During development, the Google Custom Search backend was implemented first. Configuring it in production turned out to be brittle even for a developer with full Google Cloud access: in addition to the API key, the project requires Custom Search API enablement, a billing account, a linked billing account on the project, an API key with Custom Search in its `Restrict key` allowlist, a separate Programmable Search Engine instance with its own CX, and — empirically — sometimes a service-side propagation delay measured in tens of minutes. Several of these failure modes return error messages that are misleading at the first reading (`API_KEY_SERVICE_BLOCKED` vs. `This project does not have the access to Custom Search JSON API`), making field debugging slow.

Pivoting to OpenAI's first-party web search tool removes all of these moving parts and keeps the application's external-credential surface to a single key — a substantial reduction in deployment friction for an academic project. Both backends are kept in the codebase for comparative discussion and to demonstrate the cost of each operational profile.

### 5.8 Risk analysis

`src/company_risk_analyzer.py :: analyze_company_risk()` builds a 0–100 score additively:

| Signal | Penalty | Rationale |
|--------|---------|-----------|
| Company not verified | +30 | The supplier is unconfirmed against the registry |
| Company inactive / radiat / suspendat | +50 | Strong indicator the invoice cannot be legitimate |
| Tax ID mismatch | +40 | Likely identity manipulation |
| Name mismatch | +20 | Could be a clerical error or impersonation |
| Negative keyword in news article | +10 each | Press mention of insolvency/bankruptcy/lawsuit |

The negative keyword list (`NEGATIVE_TERMS`) is bilingual: `insolvență`, `faliment`, `dosar`, `anchetă`, `fraudă`, `proces`, `executare silită`, `datorii`, `bankruptcy`, `fraud`, `lawsuit`, `investigation`. The score is capped at 100 and bucketed: 0–30 `low`, 31–65 `medium`, 66–100 `high`.

> **Disclaimer (also embedded in code):** *This is a heuristic academic risk indicator, not a legal or financial decision tool.* It surfaces suppliers worth a human second look — it does not replace due diligence.

### 5.9 XML generation

`src/xml_generator.py :: generate_invoice_xml(invoice_data)` produces an XML conformant to the schema in the project specification, plus a `<CompanyVerification>` block under `<Invoice>` containing the verification fields, the risk score, the warnings, and the online mentions. ElementTree handles XML escaping (`<`, `>`, `&`, quotes) automatically. `minidom.toprettyxml()` is then used for human-readable indentation.

---

## 6. UI design — three iterations

The user interface went through three deliberate redesigns, each documented as part of the dissertation work:

### 6.1 First iteration — minimal Streamlit defaults

A header with both logos, a sidebar with menu items, three columns. Functional but visually unremarkable.

### 6.2 Second iteration — futuristic dashboard mockup

Inspired by a SaaS-style mockup the author commissioned: dark navy background, neon-cyan accents, glassmorphic cards with `backdrop-filter`, gradient buttons, glowing pipeline steps, a decorative `Dashboard / Upload / History / Analytics` sidebar menu, a notification bell with a `3` badge, an invented user avatar.

### 6.3 Third iteration — editorial / academic register

Following the **Impeccable** design skill (Paul Bakaus, Apache 2.0), the dashboard look was reconsidered as a checklist of AI-generated-UI anti-patterns. The redesign replaced:

- **Inter-everywhere** with a typographic pairing: **Fraunces** (variable serif with `opsz` and `SOFT` axes) for headings and numerical values, **Geist** for body, **Geist Mono** for code.
- **Pure black/navy** with **tinted warm neutrals**: `#FAF7F0` paper, `#1B1714` warm ink, `#7A1820` heritage red borrowed from the actual UPB and FAIMA crests.
- **Glass cards nested in cards** with **hairline 1px borders** and whitespace.
- **Gradient buttons with glow shadows** with **solid-ink buttons** that hover to wine-red.
- **Decorative dashboard menu** with a centered single-column editorial layout (max-width 1080px), section numbering (§1, §2), and a bibliographic title page.
- **Emoji + neon dots** with **typographic discipline**: small-caps labels, italic ledes capped at 62 ch, tabular-numerals on amounts.

This third version reads as a typeset academic document that happens to be interactive — appropriate for the dissertation context.

### 6.4 Risk band typography

The risk band uses **Fraunces 96 opsz** for the score (large display weight), **Fraunces 36 opsz** for the level label, and the same warm-cream palette: `low` is forest green on a green wash, `medium` is warm tan on a beige wash, `high` is wine red on a faint accent wash. No saturated red is used — this is consistent with the editorial register and avoids the alarmist "danger zone" look.

---

## 7. Security and operational considerations

### 7.1 Secrets management

All credentials are loaded from `.env` (which is `.gitignore`d) via `python-dotenv`. The application **never** writes secrets to disk, never logs them, and never displays them in the UI. The `.env.example` file contains placeholders only.

For deployed instances, the recommended practice is to set the variables via the platform's secret manager (Streamlit Cloud Secrets, Render Environment Variables, etc.) rather than uploading a `.env` file.

### 7.2 Graceful degradation

External APIs are unreliable by definition. The pipeline is engineered so that **no external failure blocks the invoice extraction**. Verification, mentions search, and risk scoring are each isolated; if any of them fails, its result is set to `status="error"` (or similar) and the rest of the pipeline continues. The XML always includes a `<CompanyVerification>` block, even when its content is `<Status>not_available</Status>`.

### 7.3 Rate-limit and budget control

OpenAI usage is bounded via `MAX_PAGES=3` (page cap on Vision calls). For a hosted instance, the recommendation in `README.md` is to also set a hard monthly cap in the OpenAI dashboard (Settings → Limits → Monthly Budget). Google CSE has 100 free queries per day per key; `MAX_ONLINE_MENTIONS` caps the result count, not the rate, so for a public deployment the implementation should add a per-IP rate limiter.

### 7.4 Hosting options

The application is a stateless Streamlit app. Recommended deployment paths, in order of effort:

1. **Streamlit Community Cloud** — free, custom domain via CNAME, secrets managed in the platform.
2. **Render / Railway / Fly.io** — container-based, ~5 USD/month, custom domain, HTTPS automatic.
3. **Self-hosted VPS** — Hetzner / DigitalOcean, Docker + nginx + Let's Encrypt, full control.

### 7.5 Public-deployment hardening (recommended additions)

Before exposing the app to a public domain, three additions are recommended:

- A simple password gate at the application entrance (`.env`-stored password, checked at session start).
- A per-IP rate limit (e.g., 5 invoices per hour per IP) to prevent abuse.
- A hard OpenAI monthly budget cap.

These are out of scope for the academic demo but are documented in the README.

---

## 8. Project layout

```
invoice-ai-extractor/
├── app.py                         Streamlit GUI (editorial register)
├── requirements.txt               Pinned dependencies
├── .env.example                   Environment variables template
├── .env                           ← NOT committed, contains real keys
├── .gitignore                     Excludes .env, venv, data/, etc.
├── README.md                      User-facing documentation
├── REPORT.md                      ← This document, dissertation-grade report
├── .streamlit/
│   └── config.toml                Light/warm theme defaults
├── assets/
│   ├── logo_upb.png               University crest
│   └── logo_faima.png             Faculty crest
├── data/
│   ├── uploads/                   Runtime PDF uploads (gitignored)
│   └── outputs/                   Generated XML/JSON (gitignored)
├── src/
│   ├── __init__.py
│   ├── config.py                  Env vars + academic metadata
│   ├── pdf_processor.py           PyMuPDF text + image extraction
│   ├── openai_extractor.py        OpenAI text + Vision wrapper
│   ├── schema.py                  Pydantic models incl. CompanyVerification
│   ├── xml_generator.py           Deterministic ElementTree XML builder
│   ├── validators.py              Pydantic + XML validation
│   ├── utils.py                   Helpers (base64, json clean, etc.)
│   ├── company_verifier.py        ← External registry verification
│   ├── company_news_search.py     ← Google CSE wrapper
│   └── company_risk_analyzer.py   ← Heuristic risk scoring
└── tests/
    ├── __init__.py
    └── test_xml_generator.py
```

---

## 9. Limitations and future work

### 9.1 Known limitations

- The OpenAPI.ro endpoint shape used in `verify_company_openapi()` is a placeholder approximation. Real-world deployment requires aligning the URL and authentication style with the user's actual subscription tier.
- The address comparison is intentionally loose; it can produce false positives on suppliers that share a street name with a different city.
- The risk score is monotonic-additive — it does not weight the recency of news mentions.
- VIES (EU intra-community VAT validation) is documented as a future provider but not yet implemented.
- The application does not currently persist runs; each session is fresh.

### 9.2 Roadmap

- **Batch mode** — accept a folder of PDFs, produce a ZIP of XMLs and a CSV summary.
- **Confidence calibration** — derive a real confidence score from the model's logprobs (currently the UI shows a placeholder 96%/89%).
- **Direct SAGA import** — instead of generating XML for manual import, post the data directly via SAGA's import API (when the user has access).
- **Anti-bot layer** — Cloudflare Turnstile or hCaptcha at the upload step for public deployments.
- **Auditable run log** — append an SQLite row per run (not the PDF itself), capturing checksum, timing, model version, verification status, risk level — enabling reproducibility studies.

---

## 10. Reproducibility checklist

- Python 3.10+
- Dependencies pinned via `>=` in `requirements.txt` (see `pip freeze` for an exact bill of materials).
- All randomness suppressed: `temperature=0` on every OpenAI call.
- XML generation deterministic by construction (ElementTree, no LLM).
- All secret-bearing inputs declared in `.env.example`.
- All external API failures handled non-fatally.
- Unit tests in `tests/test_xml_generator.py` cover the seven main paths of the XML builder, including the empty-invoice edge case.

To reproduce:

```bash
git clone <repo>
cd invoice-ai-extractor
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then edit .env with your real keys
streamlit run app.py
```

---

## 11. Disclosure regarding credentials shared during development

During development, sample Google Cloud service account metadata was shared in the working session (account email, unique ID, key fingerprint). This metadata is **not a secret**: the unique ID and the fingerprint are public-grade identifiers, and the actual private key (the JSON key file content) was never disclosed. Nevertheless, the affected service account was rotated as a precaution, and the application has since been re-keyed with a **simple Custom Search API key** — which is the correct credential type for this use case (service accounts authenticate workloads against IAM-protected APIs; Custom Search uses an API-key model).

---

## 12. References and licensing

- **Anthropic Claude Agent SDK** — used during development as the AI pair-programming environment.
- **Impeccable** by Paul Bakaus, Apache 2.0 — design skill that informed the third UI iteration. https://github.com/pbakaus/impeccable
- **OpenAI API** — `gpt-4.1-mini` for text and Vision extraction. https://platform.openai.com
- **PyMuPDF** — AGPL or commercial. https://pymupdf.readthedocs.io
- **Pydantic v2** — MIT. https://docs.pydantic.dev
- **Streamlit** — Apache 2.0. https://streamlit.io
- **ANAF web service** — `webservicesp.anaf.ro/PlatitorTvaRest`. Public, no token required.
- **Google Programmable Search Engine** — https://programmablesearchengine.google.com
- **OpenAPI.ro / ListaFirme.ro** — commercial Romanian company-data APIs.

The project itself is an academic deliverable of the master programme *Management of Digital Enterprises* at the Faculty FAIMA, University POLITEHNICA of Bucharest. Source code is internal to the dissertation; the design references and dependencies retain their respective licenses.

---

*Bucharest, May 2026*
