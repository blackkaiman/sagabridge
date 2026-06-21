<?php
/**
 * SAGABridge Landing — single-page WordPress theme.
 *
 * Master's dissertation companion site for the SAGABridge invoice
 * digitalization project. The full Streamlit application is hosted at
 * app.sagabridge.live; this WordPress theme is the public landing page
 * at sagabridge.live.
 */
?>
<!DOCTYPE html>
<html <?php language_attributes(); ?>>
<head>
    <meta charset="<?php bloginfo('charset'); ?>">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="SAGABridge — Open-source, privacy-first pipeline that turns PDF invoices into SAGA-ready XML in under 30 seconds, running entirely on-device. Master's dissertation project at University POLITEHNICA of Bucharest, FAIMA.">
    <meta name="author" content="Ing. David-Adrian Babtan">
    <meta property="og:title" content="SAGABridge — Invoice Digitalization & SAGA Integration">
    <meta property="og:description" content="Open-source, privacy-first invoice digitalization. 100% on-device AI. Live demo at app.sagabridge.live">
    <meta property="og:type" content="website">
    <meta property="og:url" content="https://sagabridge.live">
    <title>SAGABridge — Invoice Digitalization &amp; SAGA Integration</title>
    <?php wp_head(); ?>
</head>
<body <?php body_class(); ?>>

<!-- =================== ACADEMIC HEADER =================== -->
<div class="academic-bar">
    <div class="container">
        <div class="crest">
            <img src="<?php echo get_template_directory_uri(); ?>/logo_upb.png"
                 alt="University POLITEHNICA of Bucharest">
        </div>
        <div class="acad-text">
            <strong>University POLITEHNICA of Bucharest</strong>
            Faculty of Entrepreneurship, Business Engineering and Management
            <div class="programme">Management of Digital Enterprises</div>
        </div>
        <div class="crest">
            <img src="<?php echo get_template_directory_uri(); ?>/logo_faima.png"
                 alt="Faculty FAIMA">
        </div>
    </div>
</div>

<!-- =================== HERO =================== -->
<header class="hero">
    <div class="container">
        <div class="eyebrow">Master&rsquo;s dissertation · May 2026</div>
        <h1>SAGABridge</h1>
        <p class="tagline">Invoice Digitalization and Integration with SAGA</p>
        <p class="lead">
            An open-source, privacy-first pipeline that turns PDF invoices into
            SAGA-ready XML in under 30 seconds &mdash; while running entirely on
            your own machine. Hybrid local extraction, cross-checked against
            ANAF and VIES, scored for risk, and packaged for direct accounting
            import.
        </p>
        <a class="cta" href="https://app.sagabridge.live">Try the live demo &nbsp;&rarr;</a>
        <a class="cta-secondary" href="#about">Read more &nbsp;&darr;</a>
    </div>
</header>

<!-- =================== §1 ABOUT =================== -->
<section id="about" class="editorial">
    <div class="container">
        <h2><span class="section-num">§1</span>What it does</h2>
        <p class="lede">
            Every small-business accountant spends 6&ndash;10 hours a month
            keying invoice data into accounting software. That work is slow,
            error-prone, and lacks any verification step &mdash; if the
            supplier on the invoice doesn&rsquo;t actually exist, the cost
            still hits the books and the discrepancy surfaces months later.
        </p>
        <p>
            <strong>SAGABridge automates that entire flow.</strong> Upload an
            invoice PDF and the application extracts every field, verifies
            both supplier and customer against the Romanian ANAF registry and
            the EU VIES database, computes a heuristic risk score, and
            produces an XML compatible with SAGA&rsquo;s import format.
        </p>
        <p>
            What separates this project from commercial OCR products is the
            architectural choice to run <strong>nothing on the cloud</strong>.
            Local LLM via Ollama, local OCR via Tesseract, verifications via
            public registries. No OpenAI, no Google, no commercial APIs in
            the production pipeline. The invoice never leaves the user&rsquo;s
            machine.
        </p>

        <div class="highlight-box">
            For a Romanian SME processing 200 invoices/month, the manual flow
            takes 6&ndash;10 hours. SAGABridge handles the same volume in
            under 2 hours of unattended runtime, with full verification of
            every counterparty included.
        </div>
    </div>
</section>

<!-- =================== §2 FEATURES =================== -->
<section class="editorial">
    <div class="container">
        <h2><span class="section-num">§2</span>What&rsquo;s inside</h2>
        <p class="lede">
            Six pipeline stages, each chosen deliberately to balance speed,
            accuracy, and privacy. Every component is open-source.
        </p>

        <div class="features-grid">
            <div class="feature">
                <span class="feature-num">01</span>
                <h3>Hybrid extraction</h3>
                <p>
                    PyMuPDF first for digital PDFs &mdash; instant and free.
                    Tesseract OCR fallback for scanned documents. Local LLM
                    (Qwen 2.5) for semantic structuring of the resulting text.
                </p>
            </div>
            <div class="feature">
                <span class="feature-num">02</span>
                <h3>Dual-party verification</h3>
                <p>
                    Both supplier and customer cross-checked in parallel
                    against ANAF (for RO companies) and VIES (for any EU VAT
                    number). Auto-fallback between providers.
                </p>
            </div>
            <div class="feature">
                <span class="feature-num">03</span>
                <h3>Online presence audit</h3>
                <p>
                    DuckDuckGo search plus direct domain probing finds the
                    company&rsquo;s official website, registry pages, social
                    profiles, and press mentions &mdash; classified into four
                    badges.
                </p>
            </div>
            <div class="feature">
                <span class="feature-num">04</span>
                <h3>Heuristic risk score</h3>
                <p>
                    0&ndash;100 additive score from verification status,
                    tax-ID mismatch, company status, and negative news
                    keywords. Bucketed into low/medium/high with explicit
                    warnings.
                </p>
            </div>
            <div class="feature">
                <span class="feature-num">05</span>
                <h3>SAGA-ready XML</h3>
                <p>
                    Deterministic ElementTree-based serialization. Includes
                    the full verification dossier for both parties as an
                    audit trail embedded in the document.
                </p>
            </div>
            <div class="feature">
                <span class="feature-num">06</span>
                <h3>100% on-device AI</h3>
                <p>
                    Stack: Ollama with Qwen 2.5 3B, Tesseract OCR, ANAF/VIES
                    APIs, DuckDuckGo. Zero cloud LLM. Zero data leaving the
                    user&rsquo;s server. GDPR by architecture, not by promise.
                </p>
            </div>
        </div>
    </div>
</section>

<!-- =================== §3 TECH STACK =================== -->
<section class="editorial">
    <div class="container">
        <h2><span class="section-num">§3</span>Technology stack</h2>
        <p class="lede">
            Twelve components, all open-source, composed into a single
            pipeline. Each addresses a specific concern from the original
            problem statement.
        </p>

        <ul class="stack-list">
            <li>Streamlit &mdash; UI</li>
            <li>Python 3.12 &mdash; runtime</li>
            <li>Ollama &mdash; local LLM server</li>
            <li>Qwen 2.5 3B &mdash; structured extraction</li>
            <li>Tesseract OCR &mdash; scanned PDF fallback</li>
            <li>PyMuPDF &mdash; digital PDF parsing</li>
            <li>Pydantic v2 &mdash; schema validation</li>
            <li>ElementTree &mdash; deterministic XML</li>
            <li>ANAF API &mdash; RO company registry</li>
            <li>VIES &mdash; EU VAT validation</li>
            <li>DuckDuckGo &mdash; online mentions</li>
            <li>nginx + Let&rsquo;s Encrypt &mdash; reverse proxy + SSL</li>
        </ul>
    </div>
</section>

<!-- =================== §4 LIVE DEMO =================== -->
<section class="cta-section">
    <div class="container">
        <h2><span class="section-num">§4</span>Try it live</h2>
        <p class="lede" style="margin-left: auto; margin-right: auto;">
            The full application is hosted at the URL below. Drop an invoice
            PDF, watch the four-stage pipeline run, and download a
            SAGA-compatible XML with both parties verified.
        </p>
        <a class="big-cta" href="https://app.sagabridge.live">Open the application &nbsp;&rarr;</a>
        <div>
            <span class="url-display">https://app.sagabridge.live</span>
        </div>
    </div>
</section>

<!-- =================== §5 CREDITS =================== -->
<section class="editorial">
    <div class="container">
        <h2><span class="section-num">§5</span>Credits</h2>

        <div class="credits-grid">
            <div class="credit-block">
                <span class="label-mini">Author</span>
                <div class="name">Ing. David-Adrian B&abreve;b&tcedil;an</div>
                <div class="links">
                    <a href="https://www.linkedin.com/in/david-adrian-b-b22aa5205/" target="_blank" rel="noopener">LinkedIn</a>
                </div>
            </div>

            <div class="credit-block">
                <span class="label-mini">Scientific advisor</span>
                <div class="name">Conf. dr. ing. Silviu R&abreve;ileanu</div>
                <div class="links">
                    <a href="https://aii.pub.ro/cadre-didactice/membrii-titulari/raileanu-silviu/1490/" target="_blank" rel="noopener">UPB Profile</a>
                    <a href="https://ro.linkedin.com/in/silviu-raileanu-b8b46699" target="_blank" rel="noopener">LinkedIn</a>
                    <a href="https://www.researchgate.net/profile/Silviu-Raileanu" target="_blank" rel="noopener">ResearchGate</a>
                </div>
            </div>

            <div class="credit-block">
                <span class="label-mini">Place &amp; date</span>
                <div class="name">Bucharest</div>
                <div class="links">May 2026</div>
            </div>

            <div class="credit-block">
                <span class="label-mini">Programme</span>
                <div class="name">Management of Digital Enterprises</div>
                <div class="links">Faculty FAIMA &middot; UPB</div>
            </div>
        </div>
    </div>
</section>

<!-- =================== FOOTER =================== -->
<footer class="site-footer">
    <div class="container">
        <div>
            <strong>SAGABridge</strong> &mdash; Invoice Digitalization and Integration with SAGA
        </div>
        <div>
            University POLITEHNICA of Bucharest &middot; Faculty of Entrepreneurship, Business Engineering and Management
        </div>
        <div class="place">Bucharest, May 2026</div>
        <div class="footnote">
            Open-source, privacy-first invoice digitalization.
            &copy; <?php echo date('Y'); ?> David-Adrian B&abreve;b&tcedil;an.
            Academic project under the supervision of Conf. dr. ing. Silviu R&abreve;ileanu.
        </div>
    </div>
</footer>

<?php wp_footer(); ?>
</body>
</html>
