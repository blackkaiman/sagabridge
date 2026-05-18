# Ghid: publicare SAGABridge pe un site WordPress

Acest ghid îți arată două lucruri:
1. **Cum să hostezi aplicația** ca să fie accesibilă online prin URL.
2. **Cum să o integrezi într-o pagină WordPress** ca vizitatorii să poată folosi aplicația direct din site-ul tău, plus să vadă și raportul de prezentare.

Estimare timp: **30–60 de minute** dacă urmărești pașii.

---

## Partea 1 — Hosting-ul aplicației Streamlit

Aplicația ta este un program Python care rulează pe un server. Ca să fie accesibilă prin internet, trebuie să o pui pe un serviciu de hosting. Cea mai simplă variantă pentru disertație este **Streamlit Community Cloud** — gratuit, special creat pentru aplicații Streamlit, suportă custom domain și gestionează automat secretele.

### Pasul 1.1 — Pune codul pe GitHub

Streamlit Cloud încarcă aplicația direct dintr-un repo GitHub.

1. Creează cont pe https://github.com (dacă nu ai deja).
2. Creează un repo nou, public sau privat — recomand **privat** dacă proiectul include `.env`.
3. Pe laptopul tău, în terminal:

```bash
cd "/Users/david-adrianbabtan/Desktop/Disertație/Disertație/invoice-ai-extractor"
git init
git add .
git commit -m "Initial commit — SAGABridge MVP"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/sagabridge.git
git push -u origin main
```

> **Foarte important**: am adăugat deja `.env` în `.gitignore`, deci cheile tale OpenAI NU vor ajunge pe GitHub. Verifică totuși după primul push că `.env` nu apare pe pagina repo-ului.

### Pasul 1.2 — Conectează la Streamlit Cloud

1. Mergi la https://streamlit.io/cloud și loghează-te cu contul GitHub.
2. Click **"Create app"** → **"Deploy a public app from GitHub"**.
3. Selectează:
   - **Repository**: `YOUR_USERNAME/sagabridge`
   - **Branch**: `main`
   - **Main file path**: `app.py`
4. Click **"Advanced settings"** → secțiunea **Secrets**. Aici copiezi conținutul fișierului tău `.env` în formatul TOML pe care îl așteaptă Streamlit:

```toml
OPENAI_API_KEY = "sk-proj-..."
OPENAI_MODEL = "gpt-4.1-mini"
COMPANY_API_PROVIDER = "openai"
ENABLE_COMPANY_VERIFICATION = "true"
ENABLE_ONLINE_MENTIONS = "true"
SEARCH_PROVIDER = "openai"
MAX_PAGES = "3"
MAX_ONLINE_MENTIONS = "5"
```

5. Click **"Deploy"**. Aplicația va apărea în 1–3 minute la o adresă de forma `https://sagabridge.streamlit.app` (sau un subdomeniu pe care îl alegi tu).

### Pasul 1.3 — (Opțional) Custom domain

Dacă ai deja un domeniu propriu (de exemplu `sagabridge.ro`):

1. În Streamlit Cloud → setările aplicației → **Custom subdomain**.
2. Adaugă domeniul tău și copiază valoarea CNAME pe care ți-o dă.
3. La registrarul tău de domeniu (RoTLD, Namecheap, GoDaddy) adaugă un record CNAME care pointează `app.sagabridge.ro` (sau ce alegi) către valoarea de la Streamlit.

Propagarea DNS durează 15–60 minute.

---

## Partea 2 — Integrarea în site-ul WordPress

Acum ai aplicația live la un URL public. Trebuie să o aduci pe site-ul tău WordPress.

Sunt două abordări — **alege-o pe cea care se potrivește scopului**:

### Abordarea A — Pagină dedicată cu aplicația embedded (recomandată)

Vizitatorii pot folosi aplicația direct, fără să părăsească site-ul tău.

1. Loghează-te în panoul de administrare WordPress (`tudomeniu.ro/wp-admin`).
2. **Pages → Add New**. Pune titlu: `SAGABridge — Demo`.
3. În editor (Gutenberg / blocks), apasă **+** ca să adaugi un bloc nou și caută **"Custom HTML"**. Adaugă-l.
4. Lipește în el codul de mai jos, înlocuind URL-ul cu cel real al aplicației tale Streamlit:

```html
<div style="position: relative; width: 100%; height: 1200px; border: 1px solid #DDD6C2; border-radius: 8px; overflow: hidden;">
  <iframe
    src="https://sagabridge.streamlit.app/?embed=true"
    style="width: 100%; height: 100%; border: none;"
    allow="clipboard-write; downloads"
    sandbox="allow-scripts allow-same-origin allow-forms allow-downloads allow-popups">
  </iframe>
</div>
<p style="font-size: 0.85rem; color: #666; margin-top: 0.6rem; font-style: italic;">
  Aplicația rulează live. Pentru a o deschide la dimensiune completă,
  <a href="https://sagabridge.streamlit.app" target="_blank">click aici</a>.
</p>
```

> Parametrul `?embed=true` din URL spune Streamlit să ascundă header-ul propriu, ca aplicația să se integreze curat în pagina ta.

5. **Publish** pagina. Vizitatorii o pot folosi direct.

### Abordarea B — Pagină de prezentare cu link spre aplicație

Mai sobră, mai potrivită dacă vrei o pagină tip *"Despre proiect"* cu detalii și un buton care duce la aplicație.

1. **Pages → Add New** cu titlu `SAGABridge`.
2. Copiază conținutul din `RAPORT_DISERTATIE.md` (raportul human-readable) în editorul Gutenberg. WordPress acceptă Markdown direct dacă ai pluginul **Markdown Editor**, sau îl convertești manual la blocks (Heading + Paragraph + List).
3. Adaugă jos un buton (block-ul **Buttons**) cu textul *"Folosește aplicația"* care leagă spre `https://sagabridge.streamlit.app`.

### Abordarea C — Combinația lor (recomandată pentru disertație)

Pentru o prezentare completă în fața comisiei și a colegilor:

- Pagina principală: prezentare + butoane spre demo, raport, repo GitHub
- Sub-pagină `/demo`: aplicația embedded (Abordarea A)
- Sub-pagină `/raport`: textul raportului (Abordarea B)
- Sub-pagină `/cod`: link spre repo GitHub + secțiune scurtă cu arhitectura

---

## Partea 3 — Conversia raportului în pagină WordPress

Ai două fișiere `.md` în proiect: `RAPORT_DISERTATIE.md` (versiunea umană) și `REPORT.md` (versiunea tehnică). Cum le pui pe WordPress:

### Varianta rapidă — copy/paste manual

1. Deschide `.md`-ul în orice editor (TextEdit, VS Code).
2. Copiază secțiunile pe rând în WordPress, folosind block-urile **Heading** (pentru `##`), **Paragraph** (pentru text), **List** (pentru `-`), **Code** (pentru cod).
3. La tabele, folosește block-ul **Table**.

Durată: 30 minute pentru raportul scurt.

### Varianta automată — pandoc + import HTML

Dacă vrei să fie identic cu cel din proiect:

1. Instalează pandoc: `brew install pandoc` (Mac) sau `sudo apt install pandoc` (Linux).
2. Convertește `.md` în HTML:

```bash
cd "/Users/david-adrianbabtan/Desktop/Disertație/Disertație/invoice-ai-extractor"
pandoc RAPORT_DISERTATIE.md -o raport.html --standalone
```

3. În WordPress, creează pagina nouă, schimbă editorul pe **Code Editor** (cele 3 puncte sus → Code Editor) și lipește conținutul `raport.html`. Schimbă înapoi pe **Visual Editor**.

### Varianta foarte fidelă — PDF embedded

Dacă vrei ca raportul să fie afișat exact ca în PDF (cu tot formatting-ul):

1. Convertește în PDF: `pandoc RAPORT_DISERTATIE.md -o raport.pdf` (necesită LaTeX instalat).
2. În WordPress: **Media → Add New** → urcă PDF-ul.
3. În pagina ta, embed PDF-ul cu plugin-ul **PDF Embedder** (gratuit din pluginurile WordPress) sau cu un block iframe simplu.

---

## Partea 4 — Securitate înainte să publici

Aplicația ta va fi accesibilă publicului. Înainte să dai linkul cuiva:

1. **Verifică `.gitignore`** — să fii sigur că `.env` NU e pe GitHub.
2. **Setează un buget de cap** la OpenAI: https://platform.openai.com/account/billing/limits → Hard limit la $10/lună. Dacă cineva îți abuzează aplicația, costul e plafonat.
3. **Adaugă rate-limit la nivel de aplicație** (opțional). În `app.py` poți pune o limită de tip "max 3 facturi / IP / oră" — îți pot adăuga eu codul dacă vrei.
4. **Anti-bot pe formularul de upload** — recomand Cloudflare Turnstile (gratuit). Se setează în câteva minute.
5. **Consideră o parolă simplă pe pagina cu aplicația** — un block "Password Protected Page" în WordPress, cu o parolă pe care o spui doar comisiei. Așa eviți să rulezi tone de verificări de la public random.

---

## Partea 5 — Ce arată comisia când urmărește live

Recomand să ai pregătite, înainte de apărare, **trei link-uri scurte** într-un slide:

- `tudomeniu.ro/sagabridge` — pagina principală cu rezumat
- `tudomeniu.ro/sagabridge/demo` — demo embedded, click și încărci o factură
- `tudomeniu.ro/sagabridge/cod` — link către GitHub + REPORT.md

Poți face demo live în fața comisiei: încarci o factură reală anonimizată, ei văd cum se populează tab-urile, vezi XML-ul, descarci. Tot demo-ul durează 30–60 de secunde.

---

## Probleme comune și soluții

**"Aplicația în iframe nu se vede / e tăiată"** — Streamlit Cloud setează implicit X-Frame-Options care blochează iframe-uri pe alt domeniu. Adaugă în `.streamlit/config.toml`:

```toml
[server]
enableCORS = false
enableXsrfProtection = false
```

și redeploy. **Atenție**: asta scade securitatea aplicației — folosește numai pentru demo.

**"Aplicația pornește lent prima dată / dă timeout"** — Streamlit Cloud free pune aplicația în "sleep" după inactivitate. Prima încărcare după sleep durează 30–60 secunde. Soluție: upgrade la Streamlit teams (~25 USD/lună) sau folosește Render.com / Railway în loc.

**"WordPress refuză iframe-ul / dă eroare de securitate"** — unele teme au sanitizers stricte. Folosește plugin-ul **HTML Snippets** sau **iFrame** ca să-l incluzi într-un mod care ocolește sanitizer-ul.

**"Cheia OpenAI a fost expusă într-un commit anterior pe GitHub"** — revoc-o imediat la https://platform.openai.com/api-keys, generează una nouă și pune-o doar în Streamlit Cloud Secrets. Apoi rulează:

```bash
git filter-repo --invert-paths --path .env --force
git push --force
```

Asta șterge `.env` din întreg istoricul Git-ului.

---

## Estimare cost lunar pentru hosting public

- Streamlit Cloud free → 0 RON, dar cu limită de 1 GB RAM și sleep după inactivitate
- Streamlit Teams → ~25 USD/lună, fără limite
- Render.com hobby → ~7 USD/lună, fără sleep, custom domain inclus
- Domeniu propriu (.ro) → ~10 EUR/an la RoTLD direct, ~5 EUR/an în primul an la .com prin GoDaddy
- OpenAI usage → ~30 USD/lună la 1000 facturi
- WordPress hosting → 5–15 EUR/lună (Bluehost, SiteGround, Hostinger)

**Total minim pentru un demo public funcțional, prima lună**: ~30–40 EUR.

---

*Pentru întrebări tehnice mai detaliate, vezi `REPORT.md`. Pentru explicația în limbaj uman a proiectului în sine, vezi `RAPORT_DISERTATIE.md`.*

*Succes la apărare!*
