"""Design tokens + global theme for the NiceGUI UI.

Single source of truth for the visual language described in ``STYLEGUIDE.md``:
one blue accent, hairline borders, flat surfaces, tabular numerals, and small
uppercase muted captions. Components reference the token *constants* and the
semantic CSS classes defined here rather than hardcoding hex values or ad-hoc
Tailwind greys — so a rebrand is a one-file change.

Call :func:`apply_theme` once per page (the shared scaffold does this) to set
NiceGUI's Quasar palette and inject the global stylesheet.
"""

from __future__ import annotations

from nicegui import ui

# --- Color tokens (mirror STYLEGUIDE.md §2) -------------------------------
ACCENT = "#2563eb"  # primary accent; selected states; primary buttons
ACCENT_SOFT = "#eff4ff"  # tint for hover/selected fills
INK = "#0f172a"  # primary text, headings
MUTED = "#64748b"  # secondary text, labels, captions
HAIRLINE = "#e9edf3"  # all borders, dividers, table rules
SURFACE = "#ffffff"  # cards, sidebar, metrics
CANVAS = "#fbfcfe"  # app background, table header fill
BODY = "#334155"  # body copy, one step above MUTED
NEGATIVE = "#dc2626"  # destructive actions / errors
POSITIVE = "#16a34a"  # success
WARNING = "#d97706"  # warning

# Shared font stack (STYLEGUIDE.md §3). Inter is not bundled — falls back to
# the system UI font, so there is no network dependency on a public deploy.
FONT_STACK = (
    "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, "
    "Helvetica, Arial, sans-serif"
)

# --- Semantic class names (used by components in place of raw Tailwind) ---
# Section caption: small, uppercase, letter-spaced, muted (STYLEGUIDE.md §3).
SECTION_LABEL = "fdp-section-label"
# Page title: 1.55rem / weight-650 / tight tracking, INK.
PAGE_TITLE = "fdp-page-title"
# Muted helper/meta copy under a title.
HELP_TEXT = "fdp-help"
# Slim flat card with hairline border + 10px radius.
CARD = "fdp-card"


_GLOBAL_CSS = f"""
:root {{
  --fdp-accent: {ACCENT};
  --fdp-accent-soft: {ACCENT_SOFT};
  --fdp-ink: {INK};
  --fdp-muted: {MUTED};
  --fdp-hairline: {HAIRLINE};
  --fdp-surface: {SURFACE};
  --fdp-canvas: {CANVAS};
  --fdp-body: {BODY};
}}

html, body, .q-page-container, .nicegui-content {{
  background: {CANVAS};
  font-family: {FONT_STACK};
  color: {BODY};
}}

/* Headings (STYLEGUIDE.md §3): weight 650, tight tracking, INK. */
.{PAGE_TITLE} {{
  font-size: 1.55rem;
  font-weight: 650;
  letter-spacing: -0.02em;
  color: {INK};
  line-height: 1.2;
}}

/* Section label: uppercase muted caption that frames content. */
.{SECTION_LABEL} {{
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: {MUTED};
}}

.{HELP_TEXT} {{
  font-size: 0.8rem;
  color: {MUTED};
}}

/* Slim card: flat surface, hairline border, 10px radius, no shadow. */
.{CARD} {{
  background: {SURFACE};
  border: 1px solid {HAIRLINE};
  border-radius: 10px;
  box-shadow: none !important;
}}
.{CARD} > .q-card__section,
.{CARD}.q-card {{
  box-shadow: none !important;
}}

/* App header: flat white, hairline bottom rule. */
.fdp-header {{
  background: {SURFACE} !important;
  color: {INK} !important;
  border-bottom: 1px solid {HAIRLINE};
  box-shadow: none !important;
}}

/* Nav drawer: surface bg, hairline right rule. */
.fdp-drawer {{
  background: {SURFACE} !important;
  border-right: 1px solid {HAIRLINE};
}}

/* Nav links: quiet by default, accent-soft tint + accent text when active. */
.fdp-nav-link {{
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.5rem 0.6rem;
  border-radius: 8px;
  text-decoration: none;
  color: {MUTED};
  font-size: 0.82rem;
  font-weight: 500;
  transition: background 0.12s ease, color 0.12s ease;
}}
.fdp-nav-link:hover {{
  background: {ACCENT_SOFT};
  color: {INK};
}}
.fdp-nav-link.fdp-nav-active {{
  background: {ACCENT_SOFT};
  color: {ACCENT};
}}
.fdp-nav-link.fdp-nav-active .q-icon {{
  color: {ACCENT};
}}

/* Cards everywhere: kill Quasar's default shadow, use hairline + 10px. */
.q-card {{
  box-shadow: none !important;
  border-radius: 10px;
}}

/* Tables (STYLEGUIDE.md §5): airy, hairline-ruled, 8px clipped corners,
   uppercase muted header on CANVAS fill, tabular body numerals. */
.q-table__container {{
  border: 1px solid {HAIRLINE};
  border-radius: 8px;
  box-shadow: none !important;
  overflow: hidden;
}}
.q-table thead th {{
  background: {CANVAS};
  color: {MUTED};
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  border-bottom: 1px solid {HAIRLINE};
}}
.q-table tbody td {{
  color: {BODY};
  font-size: 0.84rem;
  border-bottom: 1px solid {HAIRLINE};
  font-variant-numeric: tabular-nums;
}}
.q-table tbody tr:last-child td {{
  border-bottom: none;
}}

/* Inputs / selects: 8px radius, hairline borders, 0.86rem text. */
.q-field--outlined .q-field__control {{
  border-radius: 8px;
}}
.q-field__native, .q-field__input {{
  font-size: 0.86rem;
  color: {INK};
}}
.q-field__label {{
  font-size: 0.78rem;
  font-weight: 600;
  color: {MUTED};
}}

/* Buttons: 8px radius, no uppercase shout, slim. */
.q-btn {{
  border-radius: 8px;
}}

/* Expansions: hairline framed, flat. */
.q-expansion-item {{
  border: 1px solid {HAIRLINE};
  border-radius: 10px;
  background: {SURFACE};
}}
.q-expansion-item .q-item {{
  border-radius: 10px;
}}

/* Toggle (segmented) selected state uses the accent. */
.q-btn-toggle {{
  border: 1px solid {HAIRLINE};
  border-radius: 8px;
  box-shadow: none !important;
}}

/* Separators are a single hairline rule. */
.q-separator {{
  background: {HAIRLINE};
}}
"""


def apply_theme() -> None:
    """Set the Quasar palette and inject the global stylesheet.

    Idempotent within a page render. NiceGUI dedupes identical ``add_head_html``
    blocks per client, so calling this from every page's scaffold is safe.
    """

    ui.colors(
        primary=ACCENT,
        secondary=MUTED,
        accent=ACCENT,
        positive=POSITIVE,
        negative=NEGATIVE,
        warning=WARNING,
        dark=INK,
    )
    ui.add_head_html(f"<style>{_GLOBAL_CSS}</style>")
