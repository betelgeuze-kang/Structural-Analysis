from __future__ import annotations


_FONT_IMPORT = (
    "@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600;700"
    "&family=Space+Grotesk:wght@500;700&display=swap');"
)


def build_signal_desk_dark_css() -> str:
    return f"""
{_FONT_IMPORT}
body.signal-desk-dark {{
  --bg:#08121d;
  --panel:#111c29;
  --panel-soft:#152435;
  --panel-strong:#0d1824;
  --panel-2:#1a2a3d;
  --ink:#ecf2f6;
  --text:#ecf2f6;
  --muted:#96a8bb;
  --line:#2b3d50;
  --border:#2b3d50;
  --accent:#4fb7ad;
  --accent-2:#f4b56b;
  --brand:#4fb7ad;
  --brand-soft:rgba(79,183,173,.12);
  --ok:#63c7a1;
  --success:#63c7a1;
  --warn:#e6a95d;
  --bad:#ef7d73;
  --danger:#ef7d73;
  color-scheme:dark;
  margin:0;
  color:var(--ink);
  font-family:'IBM Plex Sans KR','Pretendard','Noto Sans KR',sans-serif;
  background:
    radial-gradient(circle at top left, rgba(244,181,107,.12), transparent 24%),
    radial-gradient(circle at 84% 16%, rgba(79,183,173,.16), transparent 22%),
    linear-gradient(180deg, #07111c 0%, #0d1824 42%, #111e2b 100%);
  position:relative;
}}
body.signal-desk-dark::before {{
  content:'';
  position:fixed;
  inset:0;
  pointer-events:none;
  opacity:.24;
  background-image:
    linear-gradient(rgba(255,255,255,.035) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,.035) 1px, transparent 1px);
  background-size:28px 28px;
  mask-image:radial-gradient(circle at center, black 25%, transparent 85%);
}}
body.signal-desk-dark a {{
  color:inherit;
}}
body.signal-desk-dark .route-context-banner {{
  border:1px solid rgba(79,183,173,.24);
  background:linear-gradient(135deg,rgba(17,28,41,.96) 0%,rgba(21,36,53,.96) 100%);
  box-shadow:0 18px 36px rgba(0,0,0,.22);
  backdrop-filter:blur(14px);
}}
body.signal-desk-dark .route-context-banner__meta span,
body.signal-desk-dark .chip,
body.signal-desk-dark .pill {{
  border:1px solid rgba(79,183,173,.18);
  background:rgba(79,183,173,.08);
}}
body.signal-desk-dark .route-context-banner__return {{
  background:linear-gradient(135deg,var(--accent) 0%,var(--accent-2) 100%);
  color:#0b1218;
}}
body.signal-desk-dark .card,
body.signal-desk-dark .panel,
body.signal-desk-dark .hero-side,
body.signal-desk-dark .summary-card {{
  background:linear-gradient(180deg,#111c29 0%,#152435 100%);
  border:1px solid var(--line);
  box-shadow:0 18px 40px rgba(0,0,0,.24);
}}
body.signal-desk-dark .hero-main {{
  background:linear-gradient(135deg,#0f2533 0%,#10394b 40%,#1d6d73 72%,#4fb7ad 100%);
  box-shadow:0 24px 60px rgba(7,17,28,.28);
}}
body.signal-desk-dark .hero-main h1,
body.signal-desk-dark .route-context-banner__title,
body.signal-desk-dark .hero-side h2 {{
  font-family:'Space Grotesk','IBM Plex Sans KR',sans-serif;
  letter-spacing:-.04em;
}}
body.signal-desk-dark .toolbar select,
body.signal-desk-dark .toolbar a {{
  background:rgba(21,36,53,.92);
  border:1px solid var(--line);
}}
"""


def build_signal_desk_light_css() -> str:
    return f"""
{_FONT_IMPORT}
body.signal-desk-light {{
  --bg:#f4efe7;
  --surface-light:#fffaf2;
  --surface-light-soft:#f7efe3;
  --surface-light-strong:#fffdf8;
  --panel:#fffaf2;
  --panel-soft:rgba(255,250,242,.82);
  --panel-strong:rgba(247,239,227,.92);
  --panel-2:#fff6ea;
  --ink:#1c2430;
  --text:#1c2430;
  --muted:#5c6678;
  --line:#d8cfbf;
  --border:#d8cfbf;
  --accent:#0f6a73;
  --accent-2:#4fb7ad;
  --accent-warm:#f4b56b;
  --accent-warm-ink:#8f4a19;
  --brand:#0f6a73;
  --brand-soft:rgba(15,106,115,.08);
  --ok:#2f7d5a;
  --success:#2f7d5a;
  --warn:#96580e;
  --bad:#a1492e;
  --danger:#a1492e;
  --font-display:'Space Grotesk','IBM Plex Sans KR','Pretendard',sans-serif;
  --font-ui:'IBM Plex Sans KR','Pretendard','Noto Sans KR',sans-serif;
  --type-h1-size:44px;
  --type-h1-weight:700;
  --type-h1-line-height:1.02;
  --type-h1-tracking:-.04em;
  --type-h2-size:28px;
  --type-h2-weight:700;
  --type-h2-line-height:1.08;
  --type-h2-tracking:-.03em;
  --type-h3-size:18px;
  --type-h3-weight:700;
  --type-h3-line-height:1.2;
  --type-h3-tracking:-.02em;
  --type-body-size:14px;
  --type-body-line-height:1.6;
  --type-body-tracking:-.01em;
  --type-body-sm-size:12px;
  --type-body-sm-line-height:1.55;
  --type-label-size:11px;
  --type-label-line-height:1.1;
  --type-label-tracking:.12em;
  --type-metric-size:28px;
  --type-metric-line-height:1.05;
  --type-metric-tracking:-.03em;
  --radius-sm:10px;
  --radius-md:16px;
  --radius-lg:24px;
  --radius-xl:28px;
  --radius-pill:999px;
  --space-xs:4px;
  --space-sm:8px;
  --space-md:12px;
  --space-lg:16px;
  --space-xl:24px;
  --space-xxl:32px;
  --shadow-panel:0 16px 32px rgba(28,36,48,.06);
  --shadow-card:0 14px 28px rgba(28,36,48,.08);
  --shadow-hero:0 24px 60px rgba(18,56,71,.18);
  --review-hero-bg:linear-gradient(135deg,#123847 0%,#0f6a73 56%,#2c8f8e 100%);
  --review-panel-bg:linear-gradient(180deg,#fffdf8 0%,#f7efe3 100%);
  --review-panel-quiet-bg:linear-gradient(180deg,rgba(255,253,248,.96) 0%,rgba(247,239,227,.94) 100%);
  --review-meta-bg:#f7efe3;
  --review-meta-ink:#5c6678;
  --review-pill-bg:rgba(15,106,115,.08);
  --review-pill-border:rgba(15,106,115,.12);
  --review-pill-ink:#0f6a73;
  --review-pill-warm-bg:rgba(244,181,107,.18);
  --review-pill-warm-border:rgba(143,74,25,.14);
  --review-pill-warm-ink:#8f4a19;
  --review-divider:rgba(216,207,191,.92);
  color-scheme:light;
  margin:0;
  color:var(--ink);
  font-family:var(--font-ui);
  background:
    radial-gradient(circle at top left, rgba(15,106,115,.06), transparent 26%),
    radial-gradient(circle at 86% 12%, rgba(244,181,107,.12), transparent 20%),
    linear-gradient(180deg, #f6f1e8 0%, #f2ece2 46%, #ece4d8 100%);
  position:relative;
}}
body.signal-desk-light::before {{
  content:'';
  position:fixed;
  inset:0;
  pointer-events:none;
  opacity:.18;
  background-image:
    linear-gradient(rgba(15,36,48,.045) 1px, transparent 1px),
    linear-gradient(90deg, rgba(15,36,48,.045) 1px, transparent 1px);
  background-size:28px 28px;
  mask-image:radial-gradient(circle at center, black 25%, transparent 85%);
}}
body.signal-desk-light a {{
  color:inherit;
  text-decoration:none;
}}
body.signal-desk-light .route-context-banner {{
  border:1px solid rgba(15,106,115,.24);
  background:linear-gradient(135deg,rgba(255,250,242,.96) 0%,rgba(229,243,244,.96) 100%);
  border-radius:var(--radius-xl);
  box-shadow:var(--shadow-card);
  backdrop-filter:blur(14px);
}}
body.signal-desk-light .route-context-banner__eyebrow,
body.signal-desk-light .card-label,
body.signal-desk-light .section-kicker,
body.signal-desk-light .hero-kicker,
body.signal-desk-light .expert-eyebrow,
body.signal-desk-light .sheet-kicker,
body.signal-desk-light .review-label-caps {{
  font-size:var(--type-label-size);
  font-weight:700;
  line-height:var(--type-label-line-height);
  letter-spacing:var(--type-label-tracking);
  text-transform:uppercase;
}}
body.signal-desk-light .route-context-banner__meta span,
body.signal-desk-light .chip,
body.signal-desk-light .pill,
body.signal-desk-light .link-pill,
body.signal-desk-light .expert-pill,
body.signal-desk-light .expert-link-pill,
body.signal-desk-light .expert-nav-link {{
  border:1px solid rgba(15,106,115,.12);
  background:rgba(15,106,115,.08);
  color:var(--review-pill-ink);
  border-radius:var(--radius-pill);
  min-height:34px;
  padding:0 12px;
  font-family:var(--font-ui);
  font-size:var(--type-body-sm-size);
  font-weight:700;
  line-height:var(--type-body-sm-line-height);
  letter-spacing:var(--type-body-tracking);
}}
body.signal-desk-light .route-context-banner__return {{
  background:linear-gradient(135deg,#123847 0%,#0f6a73 56%,#2c8f8e 100%);
  color:#f4fbfc;
  border-radius:var(--radius-pill);
  min-height:36px;
  padding:0 14px;
  font-weight:700;
}}
body.signal-desk-light .card,
body.signal-desk-light .panel,
body.signal-desk-light .hero-side,
body.signal-desk-light .summary-card,
body.signal-desk-light .expert-hero-side,
body.signal-desk-light .expert-panel {{
  background:var(--review-panel-bg);
  border:1px solid var(--line);
  border-radius:var(--radius-lg);
  box-shadow:var(--shadow-panel);
}}
body.signal-desk-light .hero-main,
body.signal-desk-light .expert-hero-main {{
  background:var(--review-hero-bg);
  border-radius:var(--radius-xl);
  box-shadow:var(--shadow-hero);
}}
body.signal-desk-light .hero-main h1,
body.signal-desk-light .expert-hero-main h1,
body.signal-desk-light .route-context-banner__title,
body.signal-desk-light .hero-side .big {{
  font-family:var(--font-display);
  letter-spacing:var(--type-h1-tracking);
}}
body.signal-desk-light .panel h2,
body.signal-desk-light .hero-side h2,
body.signal-desk-light .expert-hero-side h2,
body.signal-desk-light .sheet-title,
body.signal-desk-light .card-value,
body.signal-desk-light .metric-value {{
  font-family:var(--font-display);
}}
body.signal-desk-light .panel h2,
body.signal-desk-light .hero-side h2,
body.signal-desk-light .expert-hero-side h2,
body.signal-desk-light .sheet-title {{
  font-size:var(--type-h2-size);
  font-weight:var(--type-h2-weight);
  line-height:var(--type-h2-line-height);
  letter-spacing:var(--type-h2-tracking);
}}
body.signal-desk-light .card-value,
body.signal-desk-light .metric-value {{
  font-size:var(--type-metric-size);
  font-weight:700;
  line-height:var(--type-metric-line-height);
  letter-spacing:var(--type-metric-tracking);
}}
body.signal-desk-light .panel p,
body.signal-desk-light .hero-side p,
body.signal-desk-light .expert-hero-side p,
body.signal-desk-light .card-note,
body.signal-desk-light .sheet-copy,
body.signal-desk-light .sheet-note-panel p,
body.signal-desk-light .sheet-note-panel li {{
  font-size:var(--type-body-size);
  line-height:var(--type-body-line-height);
  letter-spacing:var(--type-body-tracking);
}}
"""
