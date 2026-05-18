# Deploy SAGABridge pe Hostinger VPS

Ghid pas-cu-pas pentru hostarea aplicației SAGABridge pe un VPS Hostinger, cu domeniul `sagabridge.live`. Setup-ul include Ollama + Tesseract + Streamlit + nginx + SSL Let's Encrypt.

**Timp estimat:** 60-90 minute (din care ~20 min așteptare la download-ul modelului Ollama).

**Cost lunar:** ~7–10 EUR (Hostinger VPS KVM 2) + domeniul deja plătit.

---

## 1. Cumpărarea planului VPS

Mergi la https://www.hostinger.com/vps-hosting și alege:

| Plan | RAM | CPU | Disk | Preț | Verdict |
|------|-----|-----|------|------|---------|
| KVM 1 | 4 GB | 1 vCPU | 50 GB | ~5 EUR/lună | Merge, dar tight pentru llama3.2:3b |
| **KVM 2** | **8 GB** | **2 vCPU** | **100 GB** | **~7 EUR/lună** | **Recomandat — confortabil pentru 3B + nginx + WordPress dacă vrei** |
| KVM 4 | 16 GB | 4 vCPU | 200 GB | ~10 EUR/lună | Overkill pentru disertație |

La checkout:
- **OS template**: Ubuntu 24.04 LTS (sau 22.04 LTS dacă 24 nu apare)
- **Data center**: Frankfurt (cel mai apropiat de România, ~25 ms latență)
- **Hostname**: `sagabridge` (apare în prompt)
- **Root password**: setezi una puternică, **o notezi** într-un password manager

După plată primești email cu **IP-ul VPS-ului** (ex: `89.117.123.45`) și credențialele.

> **NOTĂ CPU vs GPU:** VPS-ul rulează CPU-only inference, fără accelerare GPU. Llama 3.2 3B pe CPU dă ~30-50 secunde per factură (față de 5-10 s pe Apple Silicon). Dacă vrei mai rapid, schimbi modelul la `llama3.2:1b` (~10-15 s pe CPU dar puțin mai imprecis).

---

## 2. Conectare SSH la VPS

Pe Mac, deschide Terminal:

```bash
ssh root@IP_VPS_TĂU
```

La prima conectare îți cere "Are you sure you want to continue? yes". Apoi parola root.

---

## 3. Setup inițial (10 minute)

Rulează în ordine, ca **root**:

```bash
# Update sistem
apt update && apt upgrade -y

# Pachete de bază
apt install -y curl wget git nano htop ufw build-essential \
    python3 python3-pip python3-venv \
    tesseract-ocr tesseract-ocr-ron tesseract-ocr-eng \
    nginx certbot python3-certbot-nginx

# Creează utilizator nesigur pentru aplicație (best practice)
adduser sagabridge   # pune-i parolă
usermod -aG sudo sagabridge

# Firewall — permite SSH + HTTP + HTTPS
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable

# Swap de 4GB (safety net dacă RAM se duce aproape de limită)
fallocate -l 4G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

Apoi `exit` și **logați-vă ca utilizatorul nou**:

```bash
ssh sagabridge@IP_VPS_TĂU
```

---

## 4. Instalează Ollama

```bash
# One-line installer oficial
curl -fsSL https://ollama.com/install.sh | sh

# Verifică
ollama --version
```

Ollama se instalează automat ca systemd service și pornește pe `localhost:11434`. Verifică:

```bash
systemctl status ollama
```

Pull modelul (durează 3-10 min, ~2 GB):

```bash
ollama pull llama3.2:3b
```

Test:

```bash
ollama run llama3.2:3b "Salut, spune-mi 'merge' daca poti raspunde."
```

Dacă răspunde, Ollama e gata.

---

## 5. Clonează proiectul

Mai întâi împinge codul pe GitHub (dacă nu l-ai făcut). Pe laptopul tău:

```bash
cd "/Users/david-adrianbabtan/Desktop/Disertație/Disertație/invoice-ai-extractor"
git init
git add .
git commit -m "SAGABridge initial commit"
git branch -M main
git remote add origin https://github.com/USERNAME/sagabridge.git
git push -u origin main
```

> **IMPORTANT:** `.env` e deja în `.gitignore` deci NU se urcă pe GitHub. Vei seta variabilele direct pe VPS.

Pe VPS, ca utilizatorul `sagabridge`:

```bash
cd ~
git clone https://github.com/USERNAME/sagabridge.git
cd sagabridge

# Mediu virtual + deps
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# .env minimal
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

# Director pentru date runtime
mkdir -p data/uploads data/outputs
```

Test rapid că merge:

```bash
streamlit run app.py --server.port 8501 --server.address 127.0.0.1
```

Lasă-l să pornească, vezi dacă afișează "Uvicorn server started". Apasă Ctrl+C ca să oprești — îl punem ca service permanent în pasul următor.

---

## 6. Streamlit ca systemd service

Ca **root** (`sudo su` sau direct prin ssh root):

```bash
nano /etc/systemd/system/sagabridge.service
```

Pune conținutul:

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

Salvează (Ctrl+O, Enter, Ctrl+X). Pornește:

```bash
touch /var/log/sagabridge.log
chown sagabridge:sagabridge /var/log/sagabridge.log

systemctl daemon-reload
systemctl enable sagabridge
systemctl start sagabridge
systemctl status sagabridge
```

Verifică logul:

```bash
tail -f /var/log/sagabridge.log
```

Ar trebui să vezi "Uvicorn server started on 127.0.0.1:8501".

---

## 7. nginx reverse proxy + SSL

Configurarea nginx pentru `app.sagabridge.live`:

```bash
nano /etc/nginx/sites-available/sagabridge
```

Conținut:

```nginx
server {
    listen 80;
    server_name app.sagabridge.live;

    client_max_body_size 20M;

    # Streamlit folosește WebSocket pentru live updates
    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support — esențial pentru Streamlit
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # Timeout-uri mari pentru cereri lungi (Ollama poate dura 30s+)
        proxy_read_timeout 120s;
        proxy_connect_timeout 120s;
        proxy_send_timeout 120s;
    }

    # Endpoint-ul de health al Streamlit
    location /_stcore/health {
        proxy_pass http://127.0.0.1:8501/_stcore/health;
    }
}
```

Activează site-ul:

```bash
ln -s /etc/nginx/sites-available/sagabridge /etc/nginx/sites-enabled/
nginx -t   # test syntax
systemctl reload nginx
```

---

## 8. DNS în Hostinger

În panoul Hostinger, mergi la **Domains → sagabridge.live → DNS / Name Servers**:

Adaugă un **A record**:

| Type | Name | Value | TTL |
|------|------|-------|-----|
| A | `app` | `IP_VPS_TĂU` | 3600 |

Salvează. **Așteaptă 5-15 minute** ca DNS-ul să se propage.

Verifică din terminal pe Mac:

```bash
dig app.sagabridge.live +short
```

Dacă răspunde cu IP-ul VPS-ului, propagarea s-a făcut.

---

## 9. SSL prin Let's Encrypt

Pe VPS:

```bash
certbot --nginx -d app.sagabridge.live
```

Răspunzi la prompts:
- Email pentru notificări de renewal
- Y la termenii de serviciu
- N (sau Y) la newsletter
- Selectează "Redirect HTTP to HTTPS" (opțiunea 2)

Certbot configurează automat nginx pentru HTTPS și pune un cron pentru renewal automat la 60 zile.

Testează:

```bash
curl -I https://app.sagabridge.live
```

Ar trebui să primești `HTTP/2 200`.

---

## 10. Pagina WordPress care embed-uiește aplicația

Pe `sagabridge.live` (WordPress-ul tău), creezi o pagină nouă `/demo` cu un block "Custom HTML":

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
<p style="font-size: 0.85rem; color: #666; margin-top: 0.8rem; font-style: italic; text-align: center;">
  Aplicația rulează live pe app.sagabridge.live.
  <a href="https://app.sagabridge.live" target="_blank">Deschide pe ecran complet ↗</a>
</p>
```

Publish. Acum cineva care intră pe `sagabridge.live/demo/` vede aplicația direct, fără să schimbe URL-ul.

---

## 11. Comenzi utile post-deploy

```bash
# Status servicii
systemctl status ollama sagabridge nginx

# Restart Streamlit (după update de cod)
sudo systemctl restart sagabridge

# Vezi log live
tail -f /var/log/sagabridge.log

# Update cod de pe GitHub
cd ~/sagabridge
git pull
source venv/bin/activate
pip install -r requirements.txt   # dacă au fost deps noi
sudo systemctl restart sagabridge

# Restart Ollama
sudo systemctl restart ollama

# Vezi consum RAM
htop
```

---

## 12. Troubleshooting

**"502 Bad Gateway" în browser:**
- Streamlit nu rulează. `systemctl status sagabridge` și `tail /var/log/sagabridge.log`

**"Ollama not reachable":**
- `systemctl status ollama` — dacă e dead, `systemctl restart ollama`
- Verifică `ollama list` — există modelul?

**Lentoare excesivă (>60s pe factură):**
- VPS-ul e CPU-only, normal pentru llama3.2:3b
- Treci la `llama3.2:1b`: `ollama pull llama3.2:1b`, apoi modifică `.env` `OLLAMA_MODEL=llama3.2:1b`, `systemctl restart sagabridge`

**"Connection refused" la HTTPS:**
- Firewall: `sudo ufw status` — trebuie să fie "Nginx Full" pe ALLOW
- DNS: `dig app.sagabridge.live` — răspunde cu IP-ul corect?

**Vrei să oprești temporar aplicația:**
```bash
sudo systemctl stop sagabridge
```

**Backup configurație:**
Toate fișierele critice:
- `/etc/systemd/system/sagabridge.service`
- `/etc/nginx/sites-available/sagabridge`
- `/home/sagabridge/sagabridge/.env`

---

## 13. Securitate adiționale (recomandat post-deploy)

```bash
# Dezactivează SSH ca root
sudo nano /etc/ssh/sshd_config
# Setează: PermitRootLogin no
sudo systemctl restart sshd

# fail2ban — blochează automat IP-uri cu multe încercări de login
sudo apt install fail2ban
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

---

## 14. Cost lunar estimat

| Component | Cost |
|-----------|------|
| Hostinger VPS KVM 2 | ~7 EUR/lună |
| Domeniu sagabridge.live | ~10 EUR/an = ~0.8 EUR/lună |
| Renewal Let's Encrypt | 0 (gratis, auto) |
| OpenAI sau alte API-uri | 0 (totul local + gratuit) |
| **Total** | **~8 EUR/lună** |

---

*Pentru întrebări tehnice mai detaliate sau extensii (CI/CD din GitHub, monitoring cu Uptime Robot, etc.), vezi README.md și REPORT.md.*
