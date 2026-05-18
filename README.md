# SAGABridge

### Invoice Digitalization and Integration with SAGA

**University POLITEHNICA of Bucharest**
**Faculty of Entrepreneurship, Business Engineering and Management**
Master programme: *Management of Digital Enterprises*

**Scientific leader:** Conf. dr. ing. Silviu Răileanu
([UPB Profile](https://aii.pub.ro/cadre-didactice/membrii-titulari/raileanu-silviu/1490/) ·
[LinkedIn](https://ro.linkedin.com/in/silviu-raileanu-b8b46699) ·
[ResearchGate](https://www.researchgate.net/profile/Silviu-Raileanu))

**Author:** Ing. David-Adrian Băbțan
([LinkedIn](https://www.linkedin.com/in/david-adrian-b-b22aa5205/))

*Bucharest, May 2026*

---

## Project goal

SAGABridge automates the digitalization of invoices and prepares them for direct integration into the **SAGA** accounting software. The user uploads a PDF (digital or scanned), the application extracts the relevant fields with a hybrid local-text + AI pipeline, validates the data against a strict schema, and exports a SAGA-compatible XML file.

The contribution of the dissertation lies in the *hybrid architecture*: deterministic local parsing for digital PDFs, OpenAI Vision fallback for scanned ones, and a validated, reproducible XML output for downstream accounting integration.

## Architecture

```
PDF input
   |
   v
[PyMuPDF text extraction] ----> sufficient text? ----> [OpenAI text -> JSON]
   |                                                          |
   | (insufficient / scanned)                                 v
   v                                                    [Pydantic validation]
[PDF -> PNG pages]                                            |
   |                                                          v
   v                                                    [XML generation]
[OpenAI Vision -> JSON] -------------------------------------/
                                                              |
                                                              v
                                                      [SAGA-ready XML]
```

The hybrid approach is preferable to plain OCR because invoices have widely varying layouts, the AI model can interpret semantic fields (CUI, IBAN, VAT), local extraction is cheaper when it works, and Vision is invoked only when needed.

## Project structure

```
invoice-ai-extractor/
|-- app.py                      # Streamlit interface
|-- requirements.txt            # Python dependencies
|-- .env.example                # Environment variables template
|-- README.md                   # Documentation
|-- assets/
|   |-- logo_upb.png            # University logo
|   `-- logo_faima.png          # Faculty logo
|-- data/
|   |-- uploads/                # Uploaded PDFs
|   `-- outputs/                # Generated XMLs
|-- src/
|   |-- __init__.py
|   |-- config.py               # Configuration & academic metadata
|   |-- pdf_processor.py        # Local PDF processing
|   |-- openai_extractor.py     # AI extraction (text + Vision)
|   |-- schema.py               # Pydantic data models
|   |-- xml_generator.py        # XML serialization
|   |-- validators.py           # Data & XML validation
|   `-- utils.py                # Utility functions
`-- tests/
    `-- test_xml_generator.py   # Unit tests
```

## Installation

1. Open a terminal in the project root:

```bash
cd invoice-ai-extractor
```

2. Create and activate a virtual environment (Python 3.10+):

```bash
python3 -m venv venv
# macOS / Linux
source venv/bin/activate
# Windows
venv\Scripts\activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Configure the OpenAI API key:

```bash
cp .env.example .env
```

Edit `.env` and replace the placeholder with your real key from <https://platform.openai.com/api-keys>.

5. Place the institutional logos in `assets/`:
- `assets/logo_upb.png` — University POLITEHNICA of Bucharest
- `assets/logo_faima.png` — Faculty FAIMA

If a logo is missing, the app shows a textual placeholder instead.

6. Run the application:

```bash
streamlit run app.py
```

The interface opens automatically at <http://localhost:8501>.

## Usage flow

1. The user uploads an invoice PDF.
2. Local text extraction is attempted first.
3. If the text is sufficient, it is sent to OpenAI as plain text.
4. Otherwise, the PDF pages are rendered to PNG and sent to OpenAI Vision.
5. The model returns strict JSON matching the schema enforced by the prompt.
6. The JSON is validated locally with Pydantic.
7. The validated data is serialized into formatted XML.
8. The user views the result in three tabs (Text, JSON, XML) and downloads the XML for SAGA import.

## Testing

```bash
pytest tests/
```

## Company Verification

The application can verify the supplier company against external public registries before the XML is finalized. Supported, configurable providers:

- **OpenAPI.ro** — commercial REST endpoint for Romanian company data (CIF, address, status, VAT, CAEN, financials).
- **ANAF** — public web service `PlatitorTvaRest/api/v8/ws/tva` of the Romanian National Tax Agency. Free, optionally protected with a token for higher rate limits.
- **ListaFirme.ro** — commercial alternative.

The active provider is selected with `COMPANY_API_PROVIDER` and the credentials are loaded from `.env`. If verification is disabled, not configured, or fails, the pipeline continues and emits a clearly labeled status (`disabled`, `not_configured`, `not_found`, `insufficient_data`, `error`) — invoice extraction is never blocked.

The verification result is rendered in a dedicated **Company verification** tab and included in the final XML under `<CompanyVerification>`.

## Online Mentions Search

The application searches publicly available articles, press releases, and notices about the supplier. Two backends are supported, switchable via `SEARCH_PROVIDER` in `.env`:

- **`openai` (default, recommended)** — uses the same OpenAI key as the extraction step, calling the Responses API with the `web_search_preview` tool. The model performs the search internally and returns structured citations. No additional credentials are needed.
- **`google_cse`** — the classic Google Custom Search JSON API. Requires `GOOGLE_SEARCH_API_KEY` (a simple API key from Google Cloud Console) and `GOOGLE_SEARCH_ENGINE_ID` (a CX identifier from https://programmablesearchengine.google.com). Useful as a fallback or for environments that cannot call OpenAI.

Either way, the search is **read-only and snippet-based**: only the title, URL, snippet, source domain, and (where present) the published date are kept. The application does not download or scrape article bodies. The model is explicitly instructed not to fabricate results — if no genuine mentions are found, the result list is empty.

## Heuristic Risk Score

A simple additive score combines:

- verification status (unverified company → +30),
- company status (inactive / radiat / suspendat → +50),
- mismatch with the invoice (tax ID +40, name +20),
- negative keywords in mention titles/snippets (+10 per article).

Buckets: 0–30 = `low`, 31–65 = `medium`, 66–100 = `high`. The score is shown alongside the risk level and a human-readable list of warnings.

## Important Disclaimer

The risk score is a **heuristic academic indicator**, not a legal, financial, or fiscal decision tool. It is meant to surface potentially risky suppliers for human review, not to substitute for due diligence.

## Hosting (post-defense)

The application can be deployed to a public domain. Recommended options:

- **Streamlit Community Cloud** — free, native support, built-in custom domain configuration. Set the OpenAI key as a secret, never commit it.
- **Render / Railway / Fly.io** — container-based hosting with custom domain.
- **Self-hosted VPS** — Docker + nginx reverse proxy + Let's Encrypt.

For any public deployment: the API key must live in environment variables on the server, the app must have authentication or rate limiting, and the OpenAI dashboard must have a hard monthly spending cap configured.

## License

Academic project — University POLITEHNICA of Bucharest, FAIMA, 2026.
