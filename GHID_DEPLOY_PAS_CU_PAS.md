# Ghid de deployment SAGABridge pe VPS Hostinger

### Anexă tehnică la lucrarea de disertație

**Universitatea POLITEHNICA din București · Facultatea FAIMA**
Master: *Management of Digital Enterprises*

**Autor:** Ing. David-Adrian Băbțan
**Conducător științific:** Conf. dr. ing. Silviu Răileanu
*București, mai 2026*

---

## Despre acest document

Acest ghid documentează procedura completă prin care aplicația **SAGABridge** a fost dezvoltată local pe un Mac și apoi publicată pe domeniul `https://app.sagabridge.live` printr-un VPS Hostinger. Este scris ca o anexă reproductibilă: orice cititor cu cunoștințe medii de linie de comandă poate parcurge pașii într-o singură sesiune de ~90 de minute și obține un sistem live, identic cu cel demonstrat la apărare.

Procedura acoperă patru categorii mari de operațiuni:

1. **Achiziția și inițializarea VPS-ului** — alegerea planului, conectarea SSH, securizarea inițială.
2. **Instalarea stack-ului local-only** — Tesseract OCR, Ollama LLM, nginx, certbot.
3. **Deployment-ul aplicației** — clonarea repository-ului GitHub, mediul virtual Python, configurarea variabilelor de mediu.
4. **Punerea aplicației public-facing** — systemd service, reverse proxy nginx, DNS la Hostinger, SSL prin Let's Encrypt.

La final aplicația este accesibilă HTTPS pe un subdomeniu propriu, integrabilă în pagina principală WordPress prin iframe, și pregătită pentru demo live în fața comisiei.

---

## Prerechizite

Înainte de a începe ai nevoie de:

- Un cont **Hostinger** activ care deține domeniul folosit (în cazul nostru `sagabridge.live`).
- Un cont **GitHub** unde se găsește codul sursă al aplicației.
- Un **terminal SSH** (Terminal.app pe macOS, sau PowerShell / Windows Terminal pe Windows).
- O conexiune internet stabilă (pașii implică download-uri de ~3 GB).
- Un **password manager** (Bitwarden, 1Password, KeePass) pentru a genera și stoca parole sigure — nu folosi parole tastate manual.

Timp estimat: 90 minute, dintre care ~20 minute așteptare la download-uri (modelul Ollama de 2 GB).

Cost lunar al infrastructurii rezultate: **~8 EUR/lună** (VPS) plus costul anual al domeniului (~10 EUR/an).

---

## Etapa 1 — Achiziție VPS

În panoul Hostinger, mergi la **VPS Hosting** și alege planul **KVM 2**:

| Plan      | RAM  | vCPU | Disk    | Preț      | Note                                              |
|-----------|------|------|---------|-----------|---------------------------------------------------|
| KVM 1     | 4 GB | 1    | 50 GB   | ~5 EUR    | Posibil dar tight pentru Llama 3.2 3B             |
| **KVM 2** | **8 GB** | **2** | **100 GB** | **~7 EUR** | **Recomandat** — confortabil pentru tot stack-ul |
| KVM 4     | 16 GB | 4    | 200 GB  | ~10 EUR   | Overkill pentru disertație                        |

Setări la checkout:

- **Operating System**: Ubuntu 24.04 LTS (sau 22.04 LTS dacă 24 nu apare în listă).
- **Data center location**: Frankfurt — cea mai mică latență din România (~25 ms).
- **Hostname**: `sagabridge`.
- **Root password**: lasă Hostinger să o genereze automat, apoi o salvezi în password manager. **NU folosi parole cu cuvinte din dicționar.**

După plată primești email-ul de confirmare cu IP-ul VPS-ului tău (în cazul nostru `187.124.162.26`).

> **Observație despre performanță**: VPS-urile partajate folosesc inferență CPU-only, fără GPU. Llama 3.2 3B pe CPU dă latențe de aproximativ 30–50 secunde per factură, comparativ cu 5–10 secunde pe Apple Silicon. Este o limitare cunoscută, acceptabilă pentru un demo academic. Dacă viteza devine o problemă în producție, se poate migra la `llama3.2:1b` (mai mic, mai rapid, ușor mai imprecis), sau la modelele Qwen 2.5 din aceeași familie.

---

## Etapa 2 — Prima conectare SSH

Din Terminal pe Mac:

```bash
ssh root@187.124.162.26
```

La prima conectare apare un avertisment despre autenticitatea cheii — confirmă cu `yes`. Apoi introduci parola root (cea generată de Hostinger).

Dacă totul merge bine, vezi banner-ul Ubuntu cu informații despre sistem:

```
Welcome to Ubuntu 24.04.4 LTS (GNU/Linux 6.8.0-111-generic x86_64)
System load: 0.08
Memory usage: 6%
IPv4 address for eth0: 187.124.162.26
*** System restart required ***
```

Mesajul "System restart required" semnalează că există o actualizare de kernel în așteptare. O vom aplica după ce instalăm toate pachetele necesare, ca să facem un singur reboot la final.

---

## Etapa 3 — Schimbarea parolei root + actualizare sistem

**Primul pas obligatoriu**: schimbă parola root cu una proprie, generată de password manager:

```bash
passwd
```

Comanda îți cere parola curentă o singură dată, apoi parola nouă de două ori. Recomandare: parolă de 20+ caractere, random, fără cuvinte uzuale.

Apoi rulează actualizarea completă a sistemului și instalează pachetele necesare în acest ghid:

```bash
apt update && apt upgrade -y

apt install -y curl wget git nano htop ufw build-essential \
    python3 python3-pip python3-venv \
    tesseract-ocr tesseract-ocr-ron tesseract-ocr-eng \
    nginx certbot python3-certbot-nginx
```

Procesul durează 3–5 minute. La final, verifică versiunile cheie:

```bash
python3 --version       # Python 3.12.x
tesseract --version     # tesseract 5.x.x cu pachete pentru română (ron) și engleză (eng)
nginx -v                # nginx version: nginx/1.x
```

Apoi rebootează ca să se aplice kernel update-ul:

```bash
reboot
```

Aștepți ~30 de secunde și reconectezi:

```bash
ssh root@187.124.162.26
```

Mesajul "System restart required" trebuie să fi dispărut.

---

## Etapa 4 — Securizare server: utilizator dedicat, firewall, swap

Aplicația **nu trebuie să ruleze ca root** — ar fi o vulnerabilitate de securitate. Cream un utilizator dedicat cu drepturi limitate:

```bash
adduser sagabridge
```

Sistemul te ghidează: pui o parolă, apeși Enter la restul câmpurilor (nume complet, telefon, etc. sunt opționale). La final confirmă cu `Y`.

Adaugă utilizatorul în grupul `sudo` ca să poată rula comenzi privilegiate când este necesar:

```bash
usermod -aG sudo sagabridge
```

Configurează firewall-ul UFW astfel încât doar SSH-ul și nginx-ul (porturile 22, 80, 443) să fie accesibile din afară:

```bash
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable
```

Verifică:

```bash
ufw status
```

Output-ul trebuie să afișeze `Status: active` și regulile pentru OpenSSH / Nginx Full.

În final adaugă un swap file de 4 GB ca rezervă de memorie. Acest pas este important pentru că Ollama, când încarcă modelul Llama 3.2 3B în RAM, poate atinge temporar limita celor 8 GB disponibile pe planul KVM 2. Swap-ul previne crash-urile prin OOM (out-of-memory):

```bash
fallocate -l 4G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

Confirmă:

```bash
free -h
```

Linia `Swap:` trebuie să afișeze `4.0G`.

---

## Etapa 5 — Instalarea Ollama și descărcarea modelului

Ollama oferă un installer one-line care configurează automat și un systemd service:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Procesul durează 1–2 minute. La final, Ollama rulează în background pe `localhost:11434`. Verifică:

```bash
systemctl status ollama
```

Status-ul trebuie să fie `active (running)`. Apasă `Q` pentru a ieși din afișarea status-ului.

Acum descarci modelul AI propriu-zis:

```bash
ollama pull llama3.2:3b
```

Aceasta este descărcarea cea mai mare (aproximativ 2 GB), durează 5–15 minute în funcție de viteza conexiunii VPS-ului. La final apare mesajul `success`.

Testează că modelul răspunde:

```bash
ollama run llama3.2:3b "Spune doar 'merge' daca primesti acest mesaj."
```

Modelul îți răspunde după 30–60 de secunde (CPU-only inference). Apasă `Ctrl+D` pentru a ieși.

---

## Etapa 6 — Pregătirea repository-ului GitHub

Pe Mac, navighează în folderul proiectului și inițializează un repository Git:

```bash
cd "/Users/david-adrianbabtan/Desktop/Disertație/Disertație/invoice-ai-extractor"
git init -b main
git config user.name "David-Adrian Babtan"
git config user.email "davidbabtan1@gmail.com"
```

**Pas critic înainte de orice commit**: asigură-te că fișierele sensibile sunt în `.gitignore`. Conținutul corect al `.gitignore`:

```gitignore
# Variabile de mediu (CONȚIN CHEI - NU SE COMITĂ!)
.env
.env.local
.env.*.local
.env.save
.env.bak
.env.backup
.env.swp
.env~

# Mediu virtual
venv/
.venv/
env/

# Python
__pycache__/
*.py[cod]
*.so
*.egg-info/

# Pytest
.pytest_cache/
.coverage

# Date runtime - facturi reale și XML-uri generate
data/uploads/*
data/outputs/*
!data/uploads/.gitkeep
!data/outputs/.gitkeep

# Streamlit
.streamlit/secrets.toml

# IDE și OS
.vscode/
.idea/
.DS_Store
```

> **Lecția învățată în practică**: editorul `nano` creează automat fișiere de backup cu sufixul `.save` în timpul editării. Dacă editezi `.env` cu nano și salvezi parțial, apare un `.env.save` care va fi capturat de `git add .` chiar dacă `.env` e ignorat. Soluția: include explicit `.env.save` (și variantele) în `.gitignore`.

Stage și commit:

```bash
git add .
git status --short   # verifică manual că NU apare .env în listă
git commit -m "Initial commit — SAGABridge local-only invoice digitalization"
```

Creează repository-ul pe GitHub din browser: https://github.com/new

- **Repository name**: `sagabridge`
- **Visibility**: `Private` (recomandat — codul disertației poate conține referințe sensibile)
- **NU bifa** "Initialize with README" — avem deja conținut local

Adaugă remote-ul și push:

```bash
git remote add origin https://github.com/blackkaiman/sagabridge.git
git push -u origin main
```

GitHub îți cere autentificare. Folosește un **Personal Access Token** (parolele clasice nu mai sunt acceptate pentru git push):

1. Mergi la https://github.com/settings/tokens/new
2. Note: `sagabridge deploy`
3. Expiration: 90 days
4. Scopes: bifează `repo` (full control of private repositories)
5. Generate → copiază tokenul (începe cu `ghp_...`) — apare o singură dată

La prompt-ul Git pentru password, lipești tokenul. La username pui contul tău GitHub.

Verifică pe browser că repo-ul s-a urcat: https://github.com/blackkaiman/sagabridge. **NU trebuie să apară** fișierele `.env`, `.env.save`, `venv/`, `data/uploads/`, `data/outputs/`.

---

## Etapa 7 — Clonarea codului pe VPS

Pe VPS, ieși din root și conectează-te ca utilizatorul `sagabridge`:

```bash
exit                                    # ieșire din sesiunea root
ssh sagabridge@187.124.162.26          # logare cu parola noului user
```

Clonează repository-ul:

```bash
cd ~
git clone https://github.com/blackkaiman/sagabridge.git
cd sagabridge
```

Git îți cere autentificare. Folosește același token GitHub generat anterior (sau generează unul nou specific pentru VPS).

---

## Etapa 8 — Configurarea mediului Python și a variabilelor de mediu

Creează mediul virtual Python și instalează dependențele:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Procesul durează 2–3 minute. La final vezi `Successfully installed streamlit-... pymupdf-... ollama-...`.

Creează fișierul `.env` direct pe server (este în `.gitignore`, deci nu se urcă pe GitHub):

```bash
cat > .env << 'EOF'
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3.2:3b
TESSERACT_LANG=ron+eng
MAX_PAGES=3
MIN_TEXT_LENGTH=200
ENABLE_COMPANY_VERIFICATION=true
COMPANY_API_PROVIDER=anaf
ENABLE_ONLINE_MENTIONS=true
SEARCH_PROVIDER=duckduckgo
MAX_ONLINE_MENTIONS=5
EOF
```

Creează directoarele de runtime:

```bash
mkdir -p data/uploads data/outputs
```

Test rapid că aplicația pornește:

```bash
streamlit run app.py --server.port 8501 --server.address 127.0.0.1
```

În câteva secunde apare:

```
Uvicorn server started on 127.0.0.1:8501
You can now view your Streamlit app in your browser.
URL: http://127.0.0.1:8501
```

Apasă `Ctrl+C` pentru a opri. Aplicația funcționează — în pasul următor o transformăm într-un service systemd care pornește automat la boot.

---

## Etapa 9 — Streamlit ca systemd service

Streamlit-ul trebuie să ruleze 24/7 în background, cu restart automat în caz de crash și pornire automată după reboot. Pentru asta îl rulăm ca **systemd unit**.

Creează fișierul de configurare al service-ului (necesită sudo):

```bash
sudo nano /etc/systemd/system/sagabridge.service
```

Lipește conținutul:

```ini
[Unit]
Description=SAGABridge Streamlit App
After=network.target ollama.service
Requires=ollama.service

[Service]
Type=simple
User=sagabridge
WorkingDirectory=/home/sagabridge/sagabridge
Environment="PATH=/home/sagabridge/sagabridge/venv/bin"
ExecStart=/home/sagabridge/sagabridge/venv/bin/streamlit run app.py \
    --server.port 8501 \
    --server.address 127.0.0.1 \
    --server.headless true \
    --server.enableCORS false \
    --server.enableXsrfProtection false
Restart=on-failure
RestartSec=5
StandardOutput=append:/var/log/sagabridge.log
StandardError=append:/var/log/sagabridge.log

[Install]
WantedBy=multi-user.target
```

Salvează cu `Ctrl+O`, `Enter`, apoi `Ctrl+X`.

Pregătește fișierul de log și pornește service-ul:

```bash
sudo touch /var/log/sagabridge.log
sudo chown sagabridge:sagabridge /var/log/sagabridge.log

sudo systemctl daemon-reload
sudo systemctl enable sagabridge        # pornire automată la boot
sudo systemctl start sagabridge
sudo systemctl status sagabridge
```

Verifică status-ul: trebuie să apară `active (running)` în verde. Apasă `Q` pentru a ieși.

Testează că aplicația răspunde local:

```bash
curl -I http://127.0.0.1:8501
```

Răspunsul trebuie să fie `HTTP/1.1 200 OK`.

> **Notă conceptuală**: secțiunea `[Unit]` declară explicit `Requires=ollama.service`. Asta înseamnă că systemd nu va porni `sagabridge` decât după ce Ollama e activ. Dacă Ollama crash-uiește, systemd oprește și `sagabridge`. Această dependență de ordin garantează coerența pipeline-ului.

---

## Etapa 10 — Nginx ca reverse proxy

Streamlit ascultă doar pe `127.0.0.1:8501`, deci nu este accesibil din afara serverului. Pentru a-l expune public, configurăm nginx ca proxy invers pe portul 80/443.

Creează configurația de site:

```bash
sudo nano /etc/nginx/sites-available/sagabridge
```

Conținut:

```nginx
server {
    listen 80;
    server_name app.sagabridge.live;

    client_max_body_size 20M;

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket - obligatoriu pentru Streamlit
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # Timeouts ample pentru apelurile Ollama
        proxy_read_timeout 180s;
        proxy_connect_timeout 180s;
        proxy_send_timeout 180s;
    }

    location /_stcore/health {
        proxy_pass http://127.0.0.1:8501/_stcore/health;
    }
}
```

> **Detaliu critic**: Streamlit folosește WebSocket pentru update-uri în timp real (progress bar, hot reload, etc.). Header-ele `Upgrade` și `Connection: upgrade` sunt **obligatorii** — fără ele aplicația încarcă pagina inițială dar nu mai răspunde la interacțiuni.

Activează site-ul și reîncarcă nginx:

```bash
sudo ln -s /etc/nginx/sites-available/sagabridge /etc/nginx/sites-enabled/
sudo nginx -t                    # validare sintaxă
sudo systemctl reload nginx
```

Dacă `nginx -t` afișează `syntax is ok` + `test is successful`, configurarea este corectă.

---

## Etapa 11 — Configurarea DNS în Hostinger

În panoul Hostinger:

1. **Domains** → click pe `sagabridge.live`
2. **DNS / Name Servers** (sau "DNS Zone Editor", denumirea variază)
3. **Add new record**:

| Field      | Value                       |
|------------|-----------------------------|
| Type       | `A`                         |
| Name       | `app` (doar atât, nu `app.sagabridge.live`) |
| Points to  | `187.124.162.26`            |
| TTL        | `3600` (sau Default)        |

4. Save

> **De ce subdomain și nu subpath**: am ales `app.sagabridge.live` în loc de `sagabridge.live/app/` din două motive: (1) certificatele SSL Let's Encrypt sunt emise per host, deci un subdomeniu propriu permite SSL distinct fără să afecteze WordPress-ul de pe domeniul principal; (2) Streamlit nu se descurcă elegant cu subpaths — multe asset-uri se referă absolut la `/`, ceea ce ar necesita rewrite-uri complicate în nginx. Subdomeniul rezolvă ambele probleme.

Așteaptă 5–15 minute ca DNS-ul să se propage. Verifică de pe Mac:

```bash
dig app.sagabridge.live +short
```

Dacă răspunde cu `187.124.162.26`, DNS-ul este propagat și putem continua. Dacă răspunde gol, mai aștepți câteva minute.

---

## Etapa 12 — SSL prin Let's Encrypt

După ce DNS-ul a propagat, obținerea certificatului SSL este automată prin `certbot`:

```bash
sudo certbot --nginx -d app.sagabridge.live
```

Răspunzi la prompt-uri:

- **Email** pentru notificări de expirare: `davidbabtan1@gmail.com`
- **Termeni de serviciu**: `Y`
- **Newsletter EFF**: `N` (opțional)
- **Redirect HTTP → HTTPS**: alege opțiunea `2` (recomandată)

Certbot:

1. Validează domeniul automat printr-un challenge HTTP
2. Generează un certificat SSL valid 90 zile
3. Modifică configurația nginx pentru a servi HTTPS pe portul 443
4. Adaugă un cron job care reînnoiește certificatul automat la 60 zile

La final apare mesajul:

```
Congratulations! You have successfully enabled HTTPS on https://app.sagabridge.live
```

---

## Etapa 13 — Test final

Deschide în browser:

**https://app.sagabridge.live**

Aplicația SAGABridge se încarcă cu:

- Header-ul tipografiat cu numele lucrării
- Pagina de titlu academică
- Banda bibliografică (autor, conducător, dată)
- Secțiunea §1 cu dropzone-ul pentru PDF
- Lacăt verde în bara browser-ului (SSL activ)

Încarcă o factură PDF de test pentru a confirma că pipeline-ul rulează end-to-end:

1. Click pe dropzone, selectează un PDF de factură
2. Click pe **Analyze invoice**
3. Pipeline visualizer-ul afișează cele 4 stații (Read → Extract → Verify → Package)
4. După 20–40 de secunde apare rezultatul: tab-urile XML / Structured data / Source text / Company verification
5. Tab-ul **Company verification** afișează verificarea ambelor firme cu scor de risc

Dacă toate cele 5 puncte sunt validate, aplicația este complet funcțională în producție.

---

## Mentenanță și operațiuni post-deploy

### Update cod după modificări locale

Când modifici codul pe laptop:

```bash
# Pe Mac
git add .
git commit -m "descrierea modificării"
git push

# Pe VPS
ssh sagabridge@187.124.162.26
cd ~/sagabridge
git pull
source venv/bin/activate
pip install -r requirements.txt    # doar dacă ai schimbat requirements
sudo systemctl restart sagabridge
```

### Comenzi de monitorizare

```bash
sudo systemctl status ollama sagabridge nginx    # status servicii
tail -f /var/log/sagabridge.log                  # log live
sudo journalctl -u sagabridge -n 100             # ultimele 100 linii din log
htop                                              # CPU și RAM în timp real
free -h                                           # disponibilitate memorie + swap
df -h                                             # spațiu disk
```

### Restart aplicații

```bash
sudo systemctl restart sagabridge      # doar Streamlit
sudo systemctl restart ollama          # doar Ollama
sudo systemctl restart nginx           # doar nginx
```

### Oprire temporară

```bash
sudo systemctl stop sagabridge         # oprește aplicația, păstrează nginx + Ollama
```

---

## Troubleshooting

### Aplicația arată "502 Bad Gateway" în browser

**Cauza**: Streamlit nu rulează sau nginx nu îl poate atinge.

**Diagnostic**:
```bash
sudo systemctl status sagabridge
tail -50 /var/log/sagabridge.log
```

**Remediere**: dacă service-ul e dead, `sudo systemctl restart sagabridge`. Dacă crash-uiește repetat, citește ultimele 50 de linii din log pentru a identifica eroarea.

### Aplicația răspunde dar "Pipeline error: Could not reach Ollama"

**Cauza**: Ollama s-a oprit sau modelul nu este pulled.

**Diagnostic**:
```bash
sudo systemctl status ollama
ollama list                  # verifică dacă llama3.2:3b apare
curl http://localhost:11434/api/tags
```

**Remediere**:
```bash
sudo systemctl restart ollama
# Dacă modelul lipsește din list:
ollama pull llama3.2:3b
```

### Lentoare excesivă (peste 60 secunde per factură)

**Cauza**: CPU-only inference este lent pentru modele 3B. Acceptabil în limitele a 30–50 secunde, dar dacă depășește mult, treci la un model mai mic.

**Remediere**:
```bash
ollama pull llama3.2:1b
nano ~/sagabridge/.env
# modifică linia OLLAMA_MODEL=llama3.2:1b
sudo systemctl restart sagabridge
```

### SSL nu se reînnoiește automat

Certbot pune deja un cron, dar poți testa manual:

```bash
sudo certbot renew --dry-run
```

Dacă reușește dry-run-ul, reînnoirea reală va merge automat la timpul potrivit.

### Discul VPS-ului se umple

Cele mai mari surse de spațiu:
- `/var/log/sagabridge.log` — poate crește în timp
- `~/sagabridge/data/uploads/` — facturile încărcate
- `~/sagabridge/data/outputs/` — XML-urile generate și imaginile OCR

Curățare:

```bash
sudo truncate -s 0 /var/log/sagabridge.log    # golește log-ul (păstrează fișierul)
find ~/sagabridge/data/uploads/ -type f -mtime +30 -delete    # șterge fișiere mai vechi de 30 zile
find ~/sagabridge/data/outputs/ -type f -mtime +30 -delete
```

---

## Recomandări de securitate (post-deploy)

După ce sistemul este în producție, recomandăm trei măsuri suplimentare:

### Dezactivează login-ul SSH ca root

```bash
sudo nano /etc/ssh/sshd_config
```

Modifică (sau adaugă) linia:

```
PermitRootLogin no
```

Reîncarcă sshd:

```bash
sudo systemctl restart sshd
```

De acum încolo vei intra doar ca `sagabridge` și vei folosi `sudo` pentru comenzi privilegiate.

### Instalează fail2ban

Blochează automat IP-urile care încearcă multe parole greșite la SSH:

```bash
sudo apt install -y fail2ban
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

### Setup autentificare SSH cu cheie (preferată parolei)

Pe Mac:

```bash
ssh-keygen -t ed25519 -C "davidbabtan1@gmail.com"
ssh-copy-id sagabridge@187.124.162.26
```

Acum poți edita `/etc/ssh/sshd_config` pe VPS și dezactiva complet autentificarea cu parolă:

```
PasswordAuthentication no
```

Apoi `sudo systemctl restart sshd`.

> **Atenție**: înainte de a dezactiva parolele, testează că poți intra cu cheia. Altfel rămâi blocat afară din server și trebuie să folosești consola Hostinger pentru a recupera accesul.

---

## Integrarea în WordPress (sagabridge.live)

Având aplicația live pe `app.sagabridge.live`, ultimul pas este integrarea într-o pagină WordPress pe domeniul principal `sagabridge.live`.

În panoul WordPress, creează o pagină nouă (de ex. `/demo`) și adaugă un block **Custom HTML** cu:

```html
<div style="position: relative; width: 100%; height: 1400px;
            border: 1px solid #DDD6C2; border-radius: 8px;
            overflow: hidden; background: #FAF7F0;">
  <iframe
    src="https://app.sagabridge.live/?embed=true"
    style="width: 100%; height: 100%; border: none;"
    allow="clipboard-write; downloads"
    sandbox="allow-scripts allow-same-origin allow-forms allow-downloads allow-popups">
  </iframe>
</div>
<p style="font-size: 0.85rem; color: #666; margin-top: 0.8rem;
          font-style: italic; text-align: center;">
  Aplicația rulează live pe app.sagabridge.live.
  <a href="https://app.sagabridge.live" target="_blank">Deschide pe ecran complet ↗</a>
</p>
```

Publică pagina. Vizitatorii pot folosi aplicația direct din WordPress, fără să schimbe domeniul.

---

## Cost lunar estimat

| Component | Preț |
|-----------|------|
| Hostinger VPS KVM 2 (8 GB RAM, 2 vCPU) | ~7 EUR/lună |
| Domeniu sagabridge.live (renewal anual) | ~10 EUR/an = ~0.8 EUR/lună |
| SSL Let's Encrypt | 0 (gratuit, renewal automat) |
| API-uri externe (ANAF, VIES, DuckDuckGo) | 0 (toate gratuite) |
| LLM (Ollama local) | 0 (rulează pe VPS, fără cost per cerere) |
| **Total** | **~8 EUR/lună** |

---

## Concluzie

Procedura descrisă aici transformă aplicația SAGABridge din proiect local dezvoltat pe Mac într-un serviciu accesibil public la `https://app.sagabridge.live`, complet funcțional, cu certificat SSL valid și protejat de firewall. Stack-ul rezultat este **100% open-source**, fără dependențe de servicii cloud comerciale, fără chei API plătite, și fără date sensibile care părăsesc infrastructura controlată de utilizator.

Pentru comisia de disertație, această configurație ilustrează trei principii arhitecturale importante:

1. **Suveranitate digitală** — toate componentele (Tesseract, Ollama, ANAF, VIES, DuckDuckGo, nginx, Let's Encrypt) sunt fie open-source rulate local, fie API-uri publice oficiale gratuite. Nu există un singur furnizor cloud comercial pe care depinde funcționarea.

2. **Reproductibilitate** — orice cercetător sau IMM poate reproduce setup-ul în 90 de minute urmând acest ghid, fără cunoștințe avansate de DevOps.

3. **Cost zero per procesare** — odată plătit VPS-ul fix de ~7 EUR/lună, fiecare factură procesată costă efectiv 0 RON. Comparativ cu o soluție bazată pe OpenAI API (~2–4 cenți / factură), pragul de rentabilitate este atins la ~200 facturi / lună.

---

*Acest ghid completează documentația tehnică din `REPORT.md` și raportul human-readable din `RAPORT_DISERTATIE.md`. Pentru detalii despre algoritmii din pipeline, vezi `raport_algoritmi.html`.*

**SAGABridge · București, mai 2026**
