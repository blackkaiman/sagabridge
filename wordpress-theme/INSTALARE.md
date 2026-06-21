# SAGABridge Landing — Tema WordPress

Tema single-page pentru `sagabridge.live`, companion al aplicației de la `app.sagabridge.live`.

## Conținut arhivă

```
sagabridge/
├── style.css       (metadata WP + tot CSS-ul)
├── index.php       (pagina propriu-zisă)
└── functions.php   (setup minimal)
```

## Instalare (3 pași)

1. **Comprimă** folderul `sagabridge/` într-o arhivă `.zip`:
   ```bash
   cd /Users/david-adrianbabtan/Desktop/Master/Disertație/Disertație/invoice-ai-extractor/wordpress-theme
   zip -r sagabridge-theme.zip sagabridge/
   ```
   (Sau folosește interfața grafică pe Mac: right-click pe folder → Compress)

2. **Loghează-te în WordPress admin** (`sagabridge.live/wp-admin`).

3. **Aspect → Teme → Adaugă temă nouă → Încarcă temă** → selectează `sagabridge-theme.zip` → **Instalează acum** → **Activează**.

Gata. Vizitezi `https://sagabridge.live` și vezi noua pagină.

## Personalizare ulterioară

Toate textele sunt direct în `index.php`. Pentru modificări mici:

1. Editezi `index.php` local
2. Re-zip → re-upload (sau editezi prin **Aspect → Editor de teme** direct în WordPress)

Pentru modificări de design: ajustezi CSS-ul în `style.css`. Sunt variabile CSS în top pentru paleta de culori (`--accent`, `--paper`, etc.) ca să poți schimba toate culorile dintr-un singur loc.

## Note tehnice

- **Single-page** — nu folosește loop-ul WordPress clasic, e o pagină statică tipărită direct
- **Compatibilă cu plugin-uri** — `wp_head()` și `wp_footer()` sunt apelate, deci pluginuri de SEO/cache/analytics merg normal
- **Fonts** — Fraunces și Geist de pe Google Fonts (CDN), fără hosting local
- **Imagini** — zero. Tot designul e tipografic, ca să fie rapid și fără dependențe externe.
- **Responsive** — testat pe mobile, tablet, desktop

## Dacă nu vrei să folosești ca temă

**Alternativă mai simplă:** copiezi conținutul din `index.php` (de la `<!-- ACADEMIC HEADER -->` până la `</footer>`) plus `<style>...</style>` cu CSS-ul din `style.css`, și-l pui într-un block **Custom HTML** într-o pagină WordPress nouă numită "Home". Apoi setezi pagina ca front-page din **Setări → Citire**.

Funcționează cu orice temă WordPress activă.
