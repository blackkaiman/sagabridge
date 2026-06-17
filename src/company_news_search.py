# src/company_news_search.py
"""
Online mentions search — fully local, no cloud APIs.

Default backend: **DuckDuckGo HTML search** via the `duckduckgo-search`
package. No API key, no rate-limited paid plan, no data leaves to a
proprietary cloud beyond the standard web request.

Optional fallback: Google Custom Search JSON API (commented examples
preserved in code for academic comparison, but disabled by default).

Result shape is identical to before: a :class:`CompanyNewsSearchResult`
wrapping a list of :class:`OnlineMention`, each tagged with a
``mention_type`` from {website, registry, social, news, other}.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict

from .config import (
    ENABLE_ONLINE_MENTIONS,
    MAX_ONLINE_MENTIONS,
    SEARCH_PROVIDER,
)
from .schema import OnlineMention


class CompanyNewsSearchResult(BaseModel):
    """Wrapper around the list of mentions, with a status code."""

    model_config = ConfigDict(extra="ignore")

    searched: bool = False
    status: str = "not_attempted"
    query: Optional[str] = None
    mentions: List[OnlineMention] = []
    error: Optional[str] = None
    provider: Optional[str] = None


# =============================================================================
# Domain classification — turn a hostname into a mention_type
# =============================================================================
REGISTRY_DOMAINS = (
    "anaf.ro", "listafirme.ro", "termene.ro", "openapi.ro",
    "bizoo.ro", "registrulcomertului.ro", "onrc.ro",
    "handelsregister.de", "bundesanzeiger.de", "northdata.de",
    "insee.fr", "pappers.fr", "societe.com", "infogreffe.fr",
    "registroimprese.it", "ufficiocamerale.it",
    "find-and-update.company-information.service.gov.uk",
    "companieshouse.gov.uk", "kvk.nl", "einforma.com",
    "ec.europa.eu",  # VIES
)

SOCIAL_DOMAINS = (
    "linkedin.com", "facebook.com", "twitter.com", "x.com",
    "instagram.com", "github.com", "youtube.com", "tiktok.com",
)

# =============================================================================
# Adult content blocklist
# =============================================================================
# Aceste rezultate NU TREBUIE sa apara intr-un raport de verificare a firmei.
# Filtram pe doua niveluri:
#   1. safesearch="strict" la DuckDuckGo (filtreaza la sursa)
#   2. blocklist explicit de domenii + cuvinte-cheie in titlu/snippet
ADULT_DOMAINS = (
    # Mainstream porn tube sites
    "pornhub.com", "xvideos.com", "xhamster.com", "xnxx.com",
    "redtube.com", "youporn.com", "tube8.com", "spankbang.com",
    "brazzers.com", "naughtyamerica.com", "porno.com",
    # Cam / live
    "chaturbate.com", "stripchat.com", "livejasmin.com", "bongacams.com",
    "cam4.com", "myfreecams.com",
    # Escort / adult classifieds (RO + intl)
    "escortguide.ro", "publi24.ro/escorte", "anunturi-escorte",
    "escortdirectory", "eros.com", "adultsearch.com",
    "skokka.com", "escortforum",
    # OnlyFans-style + adult social
    "onlyfans.com", "fansly.com", "manyvids.com", "clips4sale.com",
)

# =============================================================================
# Junk / generic-service domain blocklist
# =============================================================================
# Domenii care apar des in rezultatele de search dar nu reprezinta niciodata
# o referinta legitima despre o firma — pagini de login, landing-uri SaaS
# generice, motoare de cautare, redirect-uri etc. Le scoatem complet.
JUNK_DOMAINS = (
    # Microsoft / Outlook login & generic landings
    "outlook.com", "outlook.office365.com", "outlook.live.com",
    "office.com", "office365.com", "microsoft.com", "microsoftonline.com",
    "login.microsoftonline.com", "login.live.com",
    # Google generic
    "google.com", "accounts.google.com", "support.google.com",
    "policies.google.com",
    # Apple generic
    "apple.com/legal", "support.apple.com",
    # Search engines themselves
    "duckduckgo.com", "bing.com", "yahoo.com", "yandex.com",
    # Other generic redirects / spam
    "translate.google.com", "webcache.googleusercontent.com",
)


ADULT_KEYWORDS = (
    "porn", "porno", "xxx", "sex video", "sex anime", "escort", "escorte",
    "naked", "nude", "milf", "anal", "fetish", "bdsm",
    "camgirl", "camsex", "webcam sex", "matrimoniale sex",
    "adult dating", "adult content",
)


def _probe_company_domain(clean_name: str) -> List[OnlineMention]:
    """
    Probe direct HTTP HEAD pe domenii probabile ale firmei.

    DDG si alte search engines pot rata complet site-ul oficial al unei firme
    mici (mai ales pentru SEO-uri slabe sau crawl recent). Pentru a nu pierde
    "website-ul propriu", incercam direct cateva patterns clasice:

        {slug}.ro, www.{slug}.ro, {slug}.com

    Daca raspunde HTTP < 400, e un domeniu activ — il declaram ca website
    al firmei. Total ~1-2 secunde pentru 3 incercari paralele (HEAD requests).
    """
    import requests
    from concurrent.futures import ThreadPoolExecutor

    if not clean_name:
        return []

    slug = re.sub(r"[^a-z0-9]", "", clean_name.lower())
    if len(slug) < 3:
        return []

    candidates = (
        f"https://www.{slug}.ro",
        f"https://{slug}.ro",
        f"https://www.{slug}.com",
    )

    def _check(url: str) -> Optional[OnlineMention]:
        try:
            r = requests.head(
                url, timeout=2.5, allow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 SAGABridge/1.0"},
            )
            if r.status_code < 400:
                final = r.url
                domain = _extract_domain(final)
                return OnlineMention(
                    title=f"{clean_name} — official website",
                    url=final,
                    snippet=f"Official domain probed and reachable ({domain}).",
                    source=domain,
                    published_date=None,
                    mention_type="website",
                )
        except Exception:  # noqa: BLE001
            return None
        return None

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(_check, candidates))

    seen: set = set()
    found: List[OnlineMention] = []
    for r in results:
        if r and r.url and r.url not in seen:
            seen.add(r.url)
            found.append(r)
            break  # primul match e suficient
    return found


def _is_junk_domain(domain: Optional[str]) -> bool:
    """True for generic SaaS landing pages, login screens, search engines."""
    if not domain:
        return False
    d = domain.lower()
    for junk in JUNK_DOMAINS:
        if d == junk or d.endswith("." + junk):
            return True
    return False


def _is_relevant_to_company(
    title: Optional[str],
    snippet: Optional[str],
    company_name: Optional[str],
    tax_id: Optional[str],
    domain: Optional[str],
) -> bool:
    """
    Verifica daca rezultatul are vreo relatie reala cu firma.

    Regula: titlul SAU snippet-ul TREBUIE sa contina:
      - numele firmei (slug-uit, intregul sau o portiune semnificativa), SAU
      - CUI-ul firmei (exact, ca text), SAU
      - sa fie pe un domeniu de tip 'website' care contine slug-ul firmei
        (cazul site-ului propriu — nu mai cerem mentiune in text).

    Asta elimina rezultate gen "LinkedIn post unde URL-ul contine accidental
    secventa numerica a CUI-ului in slug" sau pagini Outlook generic.
    """
    text = " ".join(t for t in (title or "", snippet or "") if t).lower()

    # Variant 1: tax_id apare explicit in text (nu doar in URL).
    if tax_id:
        tid_clean = re.sub(r"\D", "", tax_id)
        if tid_clean and len(tid_clean) >= 5 and tid_clean in re.sub(r"\D", "", text):
            return True

    # Variant 2: site-ul propriu (slug numefirmá in domain) — accept fara
    # cerere de mentiune in text. Normalizam slug-ul firmei FARA forma
    # juridica (srl/sa/pfa) ca sa potrivim "empower-srl.ro" pentru
    # "EM POWER S.R.L."
    if company_name and domain:
        # Strip forma juridica inainte de slug
        clean = re.sub(
            r"\s*(S\.?\s*R\.?\s*L\.?|S\.?\s*A\.?|PFA|II|IA|S\.?\s*C\.?|SNC|SCS)\s*\.?\s*$",
            "", company_name, flags=re.IGNORECASE,
        )
        name_slug = re.sub(r"[^a-z0-9]", "", clean.lower())
        d = re.sub(r"[^a-z0-9.]", "", domain.lower())  # normalizam si domain-ul
        parts = d.split(".")
        if len(parts) >= 2 and name_slug and len(name_slug) >= 4:
            registrable = parts[-2]
            if name_slug in registrable or registrable in name_slug:
                return True

    # Variant 3: numele firmei apare in text.
    if company_name:
        # Folosim cuvintele "informative" din nume (≥2 caractere, fara
        # cuvinte goale "srl"/"sa"/"pfa"/"sc"). Acceptam 2 caractere ca sa
        # prindem "EM" din "EM POWER" sau "IT" din nume cu acronime scurte.
        STOP = {"srl", "sa", "sc", "pfa", "ii", "ia", "snc", "scs", "the", "ltd",
                "gmbh", "ag", "spa", "bv", "sas", "sarl", "kft",
                "and", "for", "with", "from"}
        words = [w for w in re.findall(r"[a-zăâîșțA-ZĂÂÎȘȚ]{2,}", company_name)
                 if w.lower() not in STOP]
        if not words:
            return False  # numele e doar forma juridica, nu putem valida
        text_norm = re.sub(r"\s+", " ", text)
        # WORD-BOUNDARY match — "full" NU se potriveste cu "fulltime", iar
        # "out" NU cu "without". Threshold scalat pe lungime:
        #   1 cuvant  -> trebuie sa apara
        #   2 cuvinte -> ambele
        #   3+        -> >=75%
        hits = sum(
            1 for w in words
            if re.search(rf"\b{re.escape(w.lower())}\b", text_norm)
        )
        if len(words) == 1:
            threshold = 1
        elif len(words) == 2:
            threshold = 2
        else:
            threshold = max(2, (len(words) * 3) // 4)
        return hits >= threshold

    return False


def _is_adult_result(domain: Optional[str], title: Optional[str],
                     snippet: Optional[str]) -> bool:
    """
    Return True if the result looks like adult content and should be
    filtered out of the company-verification report.

    Decision rule:
      - domain matches (or contains as part) an entry in ADULT_DOMAINS, OR
      - title or snippet contains an entry from ADULT_KEYWORDS as a
        word-boundary match.
    """
    if domain:
        d = domain.lower()
        for blocked in ADULT_DOMAINS:
            if blocked in d:
                return True
    text = " ".join(t for t in (title or "", snippet or "") if t).lower()
    if not text:
        return False
    for kw in ADULT_KEYWORDS:
        # Word-boundary check ca sa nu confunde "sex" cu "Essex".
        if re.search(rf"\b{re.escape(kw)}\b", text):
            return True
    return False


def _extract_domain(url: Optional[str]) -> Optional[str]:
    """Best-effort extraction of the host part from a URL."""
    if not url:
        return None
    try:
        host = urlparse(url).hostname or ""
        return host[4:] if host.startswith("www.") else host or None
    except Exception:  # noqa: BLE001
        return None


def _classify(domain: Optional[str], company_name: Optional[str]) -> str:
    """
    Decide which `mention_type` a result belongs to based on its domain
    (and, as a tiebreaker, whether the domain matches the company name).
    """
    if not domain:
        return "news"

    d = domain.lower()
    if any(d == reg or d.endswith("." + reg) for reg in REGISTRY_DOMAINS):
        return "registry"
    if any(d == soc or d.endswith("." + soc) for soc in SOCIAL_DOMAINS):
        return "social"

    # Heuristic: if the domain contains the company-name slug, it's likely
    # the company's own site.
    if company_name:
        slug = re.sub(r"[^a-z0-9]", "", company_name.lower())
        # Pull the registrable part of the host (foo.example.com -> example)
        parts = d.split(".")
        if len(parts) >= 2 and slug and slug in parts[-2]:
            return "website"

    return "news"


# =============================================================================
# Backend: DuckDuckGo (default, no API key)
# =============================================================================
def _search_via_duckduckgo(
    company_name: Optional[str],
    tax_id: Optional[str],
) -> CompanyNewsSearchResult:
    """
    Free, key-less search via DuckDuckGo HTML endpoint.

    DuckDuckGo doesn't return structured publication dates, but it returns
    title / URL / snippet (the snippet is what they call "body"). We
    classify each result by its domain into website / registry / social /
    news, then return at most MAX_ONLINE_MENTIONS items.
    """
    # The dependency is imported lazily so the rest of the app still runs
    # if `duckduckgo-search` is not installed yet.
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        return CompanyNewsSearchResult(
            status="not_configured", provider="duckduckgo",
            error="The `duckduckgo-search` package is not installed. "
                  "Run `pip install duckduckgo-search`.",
        )

    parts: List[str] = []
    name = (company_name or "").strip()
    tid = (tax_id or "").strip()

    # Curatam sufixul juridic ca DDG sa gaseasca rezultate concrete:
    # "FULL OUT MEDIA S.R.L." -> "FULL OUT MEDIA"
    # "BABTAN DAVID-ADRIAN PFA" -> "BABTAN DAVID-ADRIAN"
    clean_name = re.sub(
        r"\s*(S\.?\s*R\.?\s*L\.?|S\.?\s*A\.?|PFA|II|IA|S\.?\s*C\.?|SNC|SCS)\s*\.?\s*$",
        "", name, flags=re.IGNORECASE,
    ).strip()

    # Si CUI-ul fara prefixul RO (DDG match mai flexibil pe numeric).
    tid_clean = re.sub(r"^RO\s*", "", tid, flags=re.IGNORECASE).strip()

    if clean_name:
        # Quotat pentru a forta matchul pe fraza intreaga
        parts.append(f'"{clean_name}"')
    if tid_clean:
        # Neguillemetat — DDG matchuieste flexibil
        parts.append(tid_clean)

    # Query mai natural decat OR-clause + presa-keywords. Returneaza orice
    # gen de rezultate (website, registru, presa) — filtrarea/clasificarea
    # se face downstream.
    query = " ".join(parts).strip()
    if not query:
        return CompanyNewsSearchResult(
            status="insufficient_data", provider="duckduckgo",
        )

    n = int(MAX_ONLINE_MENTIONS or 5)
    # We request a few extra results so we can prioritize/filter.
    fetch_n = min(n * 3, 20)

    try:
        with DDGS() as ddgs:
            # safesearch="strict" filtreaza la sursa rezultatele adult.
            # Cerem si mai multe rezultate (fetch_n*2) ca sa avem din ce
            # filtra suplimentar dupa blocklist-ul nostru explicit.
            raw_results = list(
                ddgs.text(
                    query,
                    region="ro-ro",
                    safesearch="strict",
                    max_results=fetch_n * 2,
                )
            )
    except Exception as exc:  # noqa: BLE001
        return CompanyNewsSearchResult(
            status="error", provider="duckduckgo", query=query,
            error=f"DuckDuckGo search failed: {exc}",
        )

    if not raw_results:
        return CompanyNewsSearchResult(
            searched=True, status="no_results", provider="duckduckgo",
            query=query, mentions=[],
        )

    # Build OnlineMention list and classify each by domain.
    seen_urls: set = set()
    classified: List[OnlineMention] = []
    skipped_adult = 0
    skipped_junk = 0
    skipped_irrelevant = 0
    for r in raw_results:
        url = (r.get("href") or r.get("url") or "").strip() or None
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)

        title = (r.get("title") or "").strip() or None
        snippet = (r.get("body") or r.get("snippet") or "").strip() or None
        domain = _extract_domain(url)

        # Filtru 1 - anti-adult.
        if _is_adult_result(domain, title, snippet):
            skipped_adult += 1
            continue

        # Filtru 2 - junk domains (Outlook login, Microsoft generic, etc).
        if _is_junk_domain(domain):
            skipped_junk += 1
            continue

        # Filtru 3 - relevance: rezultatul trebuie sa mentioneze firma sau
        # CUI-ul in titlu/snippet, sau sa fie pe site-ul propriu. Asta
        # elimina rezultate "false positive" gen LinkedIn post unde URL-ul
        # contine accidental secventa numerica a CUI-ului.
        if not _is_relevant_to_company(title, snippet, name, tid, domain):
            skipped_irrelevant += 1
            continue

        mtype = _classify(domain, name)
        classified.append(OnlineMention(
            title=title,
            url=url,
            snippet=snippet,
            source=domain,
            published_date=None,  # DDG doesn't expose publish dates
            mention_type=mtype,
        ))

    # Probe direct pentru site-ul oficial daca DDG nu a returnat unul.
    # Folosim numele curat (fara SRL/SA/PFA) ca slug pentru domeniu.
    has_website = any(m.mention_type == "website" for m in classified)
    if not has_website and clean_name:
        probed = _probe_company_domain(clean_name)
        for m in probed:
            if m.url and m.url not in seen_urls:
                seen_urls.add(m.url)
                classified.append(m)

    # Prioritize: website first, then registry, social, news.
    type_order = {"website": 0, "registry": 1, "social": 2, "news": 3, "other": 4}
    classified.sort(key=lambda m: type_order.get(m.mention_type or "news", 5))
    mentions = classified[:n]

    return CompanyNewsSearchResult(
        searched=True, status="ok", provider="duckduckgo",
        query=query, mentions=mentions,
    )


# =============================================================================
# Public entry point
# =============================================================================
def search_company_mentions(
    company_name: Optional[str],
    tax_id: Optional[str],
) -> CompanyNewsSearchResult:
    """
    Dispatch to the configured search backend.

    The default backend is "duckduckgo" — fully local, no API key.
    Returns a :class:`CompanyNewsSearchResult` regardless of outcome.
    """
    if not ENABLE_ONLINE_MENTIONS:
        return CompanyNewsSearchResult(status="disabled")

    if not company_name and not tax_id:
        return CompanyNewsSearchResult(status="insufficient_data")

    provider = (SEARCH_PROVIDER or "duckduckgo").strip().lower()

    # All supported providers route here. Only "duckduckgo" remains as an
    # active backend in the local-only configuration.
    if provider in ("duckduckgo", "ddg", "local"):
        return _search_via_duckduckgo(company_name, tax_id)

    # Unknown / disabled provider — fall back to DuckDuckGo.
    return _search_via_duckduckgo(company_name, tax_id)
