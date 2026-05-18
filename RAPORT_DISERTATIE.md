# SAGABridge — Raport de prezentare

### Digitalizarea facturilor și integrarea cu SAGA

**Universitatea POLITEHNICA din București**
**Facultatea de Antreprenoriat, Ingineria și Managementul Afacerilor**
Master *Management of Digital Enterprises*

**Autor:** Ing. David-Adrian Băbțan
**Conducător științific:** Conf. dr. ing. Silviu Răileanu
*București, mai 2026*

---

> Acest document este versiunea de prezentare a proiectului — scris pentru a fi citit fluent, fără cunoștințe tehnice avansate. Pentru detalii de implementare există documentul tehnic separat (`REPORT.md`).

---

## 1. Despre ce e vorba, în două propoziții

SAGABridge este o aplicație care preia o factură PDF și produce, în câteva secunde, un fișier XML curat, gata să fie importat în programul de contabilitate SAGA. Pe drum, aplicația verifică automat dacă firma furnizoare și firma client există cu adevărat în registrele oficiale ale României, și dacă nu cumva există probleme publice asociate cu ele.

Cu alte cuvinte: înlocuiește introducerea manuală a datelor, care durează minute pentru fiecare factură și e plină de greșeli, cu un proces automat care durează 6–15 secunde și se verifică singur.

## 2. De ce ar avea cineva nevoie de asta

Orice firmă din România primește facturi în zeci de formate diferite: unele PDF-uri sunt generate de programe moderne și conțin text selectabil, altele sunt scanate din imprimantă, multe au layout-uri unice de la un furnizor la altul. La sfârșit de lună, contabilul se așază în fața monitorului și introduce manual, factură cu factură, datele în SAGA. Procesul are trei probleme cunoscute:

- Este **lent**. O factură simplă durează 2–3 minute. Un IMM cu 200 facturi/lună pierde 6–10 ore de muncă administrativă pe lună, doar pe input.
- Este **predispus la erori**. CUI greșit, sumă inversată, dată confuză — toate apar zilnic.
- Nu există **niciun nivel de verificare**. Dacă pe factură scrie *"S.C. Furnizor Inventat S.R.L., CUI RO12345678"*, contabilul îl introduce ca atare. Dacă firma nu există, acel cost ajunge până la urmă în declarația de TVA și se descoperă mult mai târziu.

SAGABridge atacă toate trei problemele simultan: extrage datele automat, le validează strict înainte de export și le compară cu surse oficiale.

## 3. Cum funcționează, pe scurt

Imaginează-ți o linie de asamblare cu cinci stații:

1. **Stația de citire.** Aplicația încearcă mai întâi să citească textul direct din PDF, folosind o bibliotecă rapidă numită PyMuPDF. Pentru facturile digitale, asta merge instant și gratis.

2. **Stația de fallback.** Dacă PDF-ul este o scanare (text neselectabil), aplicația randează paginile ca imagini și le trimite spre **OpenAI Vision** — modelul vede imaginea, "citește" factura ca un om și extrage datele.

3. **Stația de structurare.** Indiferent dacă a fost text sau imagine, modelul OpenAI returnează un JSON strict, cu câmpuri standardizate: număr factură, dată, furnizor, client, articole, totale, TVA. Schema este impusă explicit în prompt — modelul nu are voie să inventeze.

4. **Stația de verificare externă.** Aici e diferențiatorul față de aplicațiile clasice. Aplicația ia datele firmei furnizoare *și* ale firmei client și le caută online — în registrul ANAF, listafirme.ro, termene.ro, Registrul Comerțului. Apoi face același lucru pentru articolele de presă. Dacă găsește mențiuni cu *insolvență*, *faliment*, *anchetă*, *datorii*, le marchează.

5. **Stația de raport și export.** Toate informațiile (datele facturii + verificările + scorul de risc) sunt împachetate într-un XML formatat, gata pentru SAGA. Utilizatorul îl descarcă cu un click.

## 4. Ce face nou față de ce există

Există deja produse de OCR pentru facturi (DocBee, Klippa, Rossum etc.). Ce aduce nou SAGABridge:

- **Hibridul rapid + AI.** Pentru facturile digitale folosim extragere locală gratuită (PyMuPDF). Doar pentru cele scanate plătim Vision. Așa scade costul cu 60–80% comparativ cu un sistem care trimite tot la AI.

- **Verificarea identității.** Niciun produs comercial accesibil pentru IMM nu face cross-check automat al CUI-ului între factură și ANAF. SAGABridge îl face implicit, gratuit (sau cu cost neglijabil), pentru ambele firme de pe factură.

- **Indicator de risc inteligibil.** Scor 0–100 împărțit în niveluri **Low / Medium / High**, cu listă explicită de motive ("CUI nu se potrivește", "compania apare în articol despre datorii", etc.). Nu e un AI black-box — fiecare punct adăugat are o regulă clară în spate.

- **Design academic, nu SaaS-template.** Interfața e gândită deliberat ca un document tipografiat (Fraunces + Geist, accent vișiniu UPB, layout editorial), nu ca un dashboard cu glow neon. Asta e o decizie de design conștientă, documentată ca atare în lucrare.

## 5. Tehnologii folosite

| Componentă | Tehnologie | De ce |
|------------|------------|-------|
| Interfață | Streamlit | Single-file Python, nu necesită toolchain JS, ideal pentru demo academic |
| Citire PDF locală | PyMuPDF | Cea mai rapidă bibliotecă Python pentru text și randare imagini |
| Extragere AI | OpenAI `gpt-4.1-mini` | Multimodal (text + imagine), JSON strict, latență mică, cost redus |
| Validare date | Pydantic v2 | Schema explicită, mesaje de eroare clare, type-safe |
| Verificare firme | OpenAI `web_search_preview` (default) + ANAF / listafirme.ro / openapi.ro | OpenAI ca fallback robust care funcționează de oriunde; ANAF pentru cazuri locale |
| Generare XML | `xml.etree.ElementTree` standard library | Determinist, fără dependențe terțe, audit-friendly |
| Secrete | python-dotenv + `.env` (gitignored) | 12-factor app, nicio cheie nu ajunge în cod |

## 6. Un demo cu un caz real

Am încărcat în testare o factură fictivă în care figura ca furnizor *"Dedeman SRL, CUI RO2371796"*. Real CUI-ul Dedeman este 2816464. Cifra fictivă era introdusă intenționat ca să forțez un mismatch.

Iată ce a făcut aplicația, pas cu pas:

1. A citit textul facturii cu PyMuPDF (factura era digitală, deci nu a fost nevoie de Vision).
2. A trimis textul la GPT-4.1-mini, care a returnat datele structurate în 1.2 secunde.
3. A trimis numele și CUI-ul furnizorului la OpenAI web search. Modelul a căutat pe listafirme.ro și a găsit Dedeman SRL cu CUI-ul corect 2816464.
4. A comparat: nume = potrivire ✓, CUI = NU se potrivește ✗.
5. A căutat articole online despre Dedeman. A găsit 4 articole reale, dintre care două conțineau cuvintele cheie *anchetă* și *datorii*.
6. A calculat scorul de risc: +40 pentru CUI mismatch, +10 pentru fiecare articol cu cuvinte negative = **scor 60, nivel medium**.
7. A generat XML-ul, inclusiv blocul `<SupplierVerification>` cu toate detaliile, și l-a oferit pentru descărcare.

Tot procesul a durat 14 secunde. Un contabil ar fi introdus aceeași factură în 2-3 minute, fără să prindă mismatch-ul de CUI.

## 7. Limitări actuale

Onestitatea academică e importantă, deci enumăr și ce încă nu poate face aplicația:

- **Nu procesează loturi mari**. Acum acceptă o factură pe rând. Pentru un volum mare s-ar adăuga un mod batch (planificat ca extensie viitoare).
- **Cost OpenAI**. La rulare cu Vision + verificare + search, o factură costă aproximativ **2–4 cenți**. Pentru 1000 facturi/lună înseamnă 30 EUR. Acceptabil pentru IMM, costisitor pentru cazuri foarte mari.
- **ANAF e instabil**. WAF-ul ANAF blochează cereri din rețele non-rezidentiale (cloud-uri, sandbox-uri). Am implementat un fallback automat la OpenAI, deci utilizatorul nu rămâne fără verificare, dar rezultatul oficial e mai puțin "pur".
- **Scorul de risc este orientativ**. Are scop academic, nu juridic. Asta e scris explicit în interfață și în XML.

## 8. Ce poate fi îmbunătățit ulterior

- **Mod batch** cu progress bar pe folder de PDF-uri.
- **Conexiune directă la SAGA** prin API-ul lor de import (când vom avea acces la el).
- **Detecție de duplicate** — recunoașterea facturilor deja procesate.
- **Auto-import contabil** — odată ce firma a fost verificată ok timp de 6 luni, sări peste pasul de verificare.
- **Interfață multi-limbă** — momentan UI-ul e bilingv (RO + EN); poate fi extins la DE/HU pentru clienți externi.

## 9. Pe scurt, cu ce rămâne profesorul

- O aplicație **funcțională end-to-end**, demonstrabilă local, documentată tehnic și narativ.
- **Două inovații clare**: arhitectura hibridă text-local-întâi-AI-după și verificarea identității prin web search AI.
- **Decizii de design conștiente** (UI editorial, anti-pattern-uri evitate, prompt strict JSON, graceful degradation pe fiecare API extern).
- **Bază pentru extensii viitoare** — codul e modular, fiecare etapă în propriul fișier `src/`, schimbarea unui provider nu afectează restul pipeline-ului.

---

*Pentru documentația tehnică completă (arhitectură detaliată, decizii de design, motivație tehnologică, securitate, deploy), vezi `REPORT.md`. Pentru ghidul de publicare pe site WordPress, vezi `GHID_WORDPRESS.md`.*

*București, mai 2026*
