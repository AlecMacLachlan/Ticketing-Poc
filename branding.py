"""
Oak View Group brand styling for the POC.

Colors and fonts are pulled from oakviewgroup.com's own stylesheet: black
background, white text, and a blue accent family (dark navy + mid blue +
light blue — confirmed against a screenshot of the live site; there is no
gold in OVG's actual palette). Oswald is used for headings. The logo file
in assets/ was downloaded from OVG's public site. This is being applied
because OVG is the entity this POC is being built for/presented to — not
for redistribution.

ASSUMPTION: Proxima Nova (OVG's actual body font) is a commercial font we
don't have a license to bundle, so body text uses a free system/Google Font
stack instead. Only Oswald (headings) is pulled in, since it's free.
"""

from pathlib import Path

OVG_BLACK = "#000000"
OVG_NEAR_BLACK = "#121216"
OVG_WHITE = "#FFFFFF"
OVG_NAVY = "#1D3B61"
OVG_BLUE = "#4484CC"
OVG_BLUE_LIGHT = "#59A4FF"

LOGO_PATH = Path(__file__).parent / "assets" / "ovg_logo.png"

BRAND_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Oswald:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}}
h1, h2, h3, h4, .stMetric [data-testid="stMetricValue"] {{
    font-family: 'Oswald', sans-serif !important;
    letter-spacing: 0.01em;
}}

[data-testid="stAppViewContainer"] {{
    background-color: {OVG_NEAR_BLACK};
    color: {OVG_WHITE};
}}
[data-testid="stHeader"] {{
    background-color: {OVG_NEAR_BLACK};
}}
[data-testid="stSidebar"] {{
    background-color: {OVG_BLACK};
    border-right: 1px solid #2a2a2e;
}}

h1, h2, h3, h4, p, label, span, .stMarkdown, .stCaption {{
    color: {OVG_WHITE} !important;
}}

/* Blue accents on interactive/primary elements. Selectors target
   button[kind=...] directly (not ".stButton > button[...]") because a
   button with a tooltip (help=...) gets wrapped in stTooltipHoverTarget
   instead of stButton, which the more specific selector missed. */
button[kind="primary"], .stDownloadButton > button {{
    background-color: {OVG_BLUE} !important;
    color: {OVG_WHITE} !important;
    border: none !important;
    font-weight: 600;
}}
button[kind="primary"]:hover, .stDownloadButton > button:hover {{
    background-color: {OVG_BLUE_LIGHT} !important;
    color: {OVG_BLACK} !important;
}}
button[kind="secondary"] {{
    background-color: transparent !important;
    color: {OVG_WHITE} !important;
    border: 1px solid {OVG_BLUE_LIGHT} !important;
}}
button[kind="secondary"]:hover {{
    background-color: {OVG_BLUE}22 !important;
    border-color: {OVG_BLUE_LIGHT} !important;
}}

[data-testid="stMetricValue"] {{
    color: {OVG_BLUE_LIGHT} !important;
}}

[data-testid="stSliderTickBarMin"], [data-testid="stSliderTickBarMax"] {{
    color: {OVG_WHITE} !important;
}}
[data-testid="stThumbValue"], [data-testid="stSliderThumbValue"] {{
    color: {OVG_BLUE_LIGHT} !important;
}}

hr {{
    border-color: #2a2a2e !important;
}}

.ovg-header {{
    display: flex;
    align-items: center;
    gap: 1rem;
    border-bottom: 2px solid {OVG_BLUE};
    padding-bottom: 0.75rem;
    margin-bottom: 1rem;
}}
.ovg-header img {{
    height: 40px;
}}
.ovg-header .ovg-tagline {{
    color: {OVG_BLUE_LIGHT};
    font-family: 'Oswald', sans-serif;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    font-size: 0.85rem;
}}
</style>
"""


def inject_brand_css(st) -> None:
    st.markdown(BRAND_CSS, unsafe_allow_html=True)


def render_header(st, subtitle: str) -> None:
    import base64

    logo_b64 = base64.b64encode(LOGO_PATH.read_bytes()).decode()
    st.markdown(
        f"""
        <div class="ovg-header">
            <img src="data:image/png;base64,{logo_b64}" />
            <div>
                <div class="ovg-tagline">Live Event Ticketing — Proof of Concept</div>
                <div style="color:{OVG_WHITE}; font-size:0.9rem;">{subtitle}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
