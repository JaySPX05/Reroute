"""Supplier report form: the stand-in for the SAP Build Apps mobile app.

Small suppliers open this on a phone, pick their name, say what happened, and send.
"""
import streamlit as st

from reroute import agent, db

st.set_page_config(page_title="Report a problem · ReRoute")
_theme_context = getattr(getattr(st, "context", None), "theme", None)
LIGHT_MODE = getattr(_theme_context, "type", None) == "light"
palette = {   # ReRoute colour system (dark navy, teal, cyan); light-mode value first
    "page": "#EEF2F5" if LIGHT_MODE else "#07111F",          # main background
    "elevated": "#F5F7F9" if LIGHT_MODE else "#0A1728",      # elevated background
    "panel": "#FFFFFF" if LIGHT_MODE else "#0D1B2D",         # panel background
    "panel_hover": "#F8FAFB" if LIGHT_MODE else "#102238",
    "panel_soft": "#EDF3F5" if LIGHT_MODE else "#12253A",    # strong panel surface
    "text": "#102435" if LIGHT_MODE else "#F1F6FA",          # primary text
    "muted": "#536877" if LIGHT_MODE else "#9EAFBE",         # secondary text
    "faint": "#81919C" if LIGHT_MODE else "#6E8295",         # muted text
    "accent": "#078AAA" if LIGHT_MODE else "#2AC7E8",        # cyan highlight
    "on_accent": "#FFFFFF" if LIGHT_MODE else "#07111F",
    "teal": "#087D73" if LIGHT_MODE else "#13B8A6",          # primary teal
    "teal_hover": "#066B63" if LIGHT_MODE else "#19CBB7",
    "teal_surface": "#EDF3F5" if LIGHT_MODE else "#063F3B",  # dark teal surface
    "border": "#D7E0E5" if LIGHT_MODE else "#203247",
    "border_subtle": "#E7ECEF" if LIGHT_MODE else "#172A3E",
    "danger": "#C43D3D" if LIGHT_MODE else "#F06565",        # critical
    "warning": "#A46608" if LIGHT_MODE else "#F0B44A",
    "success": "#168558" if LIGHT_MODE else "#35CF8D",
    "input": "#F8FAFB" if LIGHT_MODE else "#091625",
    "map_bg": "#E7ECEC" if LIGHT_MODE else "#091827",
    "sidebar": "#F5F7F9" if LIGHT_MODE else "#0A1728",
    "sidebar_text": "#536877" if LIGHT_MODE else "#9EAFBE",
    "card": "#FFFFFF" if LIGHT_MODE else "#0D1B2D",
}
st.markdown(
    f"""<style>
:root {{
    --rr-page: var(--st-background-color, {palette["page"]});
    --rr-panel: var(--st-secondary-background-color, {palette["panel"]});
    --rr-panel-soft: {palette["panel_soft"]};
    --rr-panel-hover: {palette["panel_hover"]};
    --rr-elevated: {palette["elevated"]};
    --rr-input: {palette["input"]};
    --rr-map-bg: {palette["map_bg"]};
    --rr-border-subtle: {palette["border_subtle"]};
    --rr-text: var(--st-text-color, {palette["text"]});
    --rr-muted: {palette["muted"]};
    --rr-faint: {palette["faint"]};
    --rr-accent: {palette["accent"]};
    --rr-button-bg: {palette["teal"]};
    --rr-button-text: {palette["on_accent"]};
    --rr-teal: {palette["teal"]};
    --rr-teal-hover: {palette["teal_hover"]};
    --rr-teal-surface: {palette["teal_surface"]};
    --rr-border: var(--st-border-color, {palette["border"]});
    --rr-danger: var(--st-red-color, {palette["danger"]});
    --rr-warning: var(--st-yellow-color, {palette["warning"]});
    --rr-success: var(--st-green-color, {palette["success"]});
    --rr-sidebar: var(--st-secondary-background-color, {palette["sidebar"]});
    --rr-sidebar-text: var(--st-text-color, {palette["sidebar_text"]});
    --rr-card: var(--st-secondary-background-color, {palette["card"]});
}}
.stApp, [data-testid="stAppViewContainer"] {{
    background-color: var(--rr-page);
    background-image:
        radial-gradient(ellipse at 52% -14%, color-mix(in srgb, var(--rr-accent) 12%, transparent), transparent 48%),
        linear-gradient(135deg, color-mix(in srgb, var(--rr-teal) 4%, transparent), transparent 55%);
    color: var(--rr-text);
    font-family: "Avenir Next", "Bahnschrift", "Segoe UI", sans-serif;
}}
[data-testid="stMainBlockContainer"], .main .block-container {{
    max-width: 1680px;
    padding: 4.25rem clamp(.85rem, 1.8vw, 1.8rem) 2.5rem;   /* clear of the Streamlit top bar, which takes clicks */
}}
[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stMainBlockContainer"] > div {{ animation: rr-arrive .42s ease-out both; }}
@keyframes rr-arrive {{ from {{ opacity: 0; transform: translateY(5px); }} to {{ opacity: 1; transform: translateY(0); }} }}
h1, h2, h3, h4 {{
    color: var(--rr-text);
    font-family: "Bahnschrift", "Avenir Next", "Segoe UI", sans-serif;
    letter-spacing: -.035em;
}}
h1 {{ font-size: clamp(1.7rem, 2.7vw, 2.35rem); font-weight: 700; }}
h2, h3 {{ font-weight: 650; }}
p, [data-testid="stCaptionContainer"], [data-testid="stWidgetLabel"] {{ color: var(--rr-muted); }}
section[data-testid="stSidebar"] {{
    background: var(--rr-sidebar);
    border-right: 1px solid var(--rr-border);
}}
section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {{ padding-top: .65rem; }}
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {{ color: var(--rr-sidebar-text); }}
section[data-testid="stSidebar"] [data-testid="stSidebarNav"]::before {{
    content: "ReRoute";
    display: block;
    margin: .45rem 1rem .85rem;
    padding: .15rem 0 .75rem;
    border-bottom: 1px solid var(--rr-border);
    font-family: "Bahnschrift", "Avenir Next", sans-serif;
    font-size: 1.45rem;
    font-weight: 750;
    letter-spacing: -.04em;
    color: var(--rr-text);
}}
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a {{
    border-radius: 5px;
    margin: .12rem .45rem;
    color: var(--rr-sidebar-text);
    transition: background-color .16s ease, border-color .16s ease;
}}
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a:hover {{
    background: color-mix(in srgb, var(--rr-accent) 12%, transparent);
}}
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] a[aria-current="page"] {{
    background: color-mix(in srgb, var(--rr-accent) 15%, transparent);
    color: var(--rr-text);
    border-left: 2px solid var(--rr-accent);
}}
[data-testid="stVerticalBlockBorderWrapper"] {{
    border: 1px solid var(--rr-border) !important;
    border-radius: 7px !important;
    background: var(--rr-panel);
    box-shadow: 0 2px 10px rgba(0, 0, 0, .09);
    transition: border-color .16s ease, box-shadow .16s ease, background-color .16s ease;
}}
[data-testid="stVerticalBlockBorderWrapper"]:hover {{
    border-color: var(--rr-accent) !important;
    box-shadow: 0 3px 12px rgba(0, 0, 0, .11);
}}
[data-testid="stMetric"] {{
    min-height: 92px;
    padding: .7rem .85rem;
    border: 1px solid var(--rr-border);
    border-left: 2px solid var(--rr-accent);
    border-radius: 5px;
    background: var(--rr-panel);
}}
[data-testid="stMetricLabel"] {{
    color: var(--rr-muted);
    font-size: .68rem;
    font-weight: 700;
    letter-spacing: .08em;
    text-transform: uppercase;
}}
[data-testid="stMetricValue"] {{ color: var(--rr-text); font-weight: 720; }}
[data-testid="stMetricDelta"] {{ font-size: .75rem; }}
.rr-workflow {{
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr) auto minmax(0, 1fr) auto minmax(0, 1fr);
    align-items: stretch;
    gap: .45rem;
    margin: .45rem 0 1rem;
}}
.rr-flow-step {{
    min-width: 0;
    padding: .62rem .72rem;
    border: 1px solid var(--rr-border);
    border-left: 3px solid var(--rr-border);
    border-radius: 4px;
    background: var(--rr-panel);
    transition: border-color .16s ease, background-color .16s ease;
}}
@media (hover: hover) {{
    .rr-flow-step:hover {{
        border-color: var(--rr-accent);
        background: color-mix(in srgb, var(--rr-panel) 94%, var(--rr-accent));
    }}
}}
.rr-flow-step.is-done {{ border-left-color: var(--rr-success); }}
.rr-flow-step.is-current {{ border-left-color: var(--rr-accent); }}
.rr-flow-heading {{ display: flex; align-items: center; gap: .45rem; color: var(--rr-text); }}
.rr-flow-number {{ color: var(--rr-muted); font-size: .65rem; font-weight: 750; letter-spacing: .07em; }}
.rr-flow-heading strong {{ font-size: .82rem; }}
.rr-flow-state {{ display: block; margin: .28rem 0 0 1.8rem; color: var(--rr-muted); font-size: .72rem; line-height: 1.3; }}
.rr-flow-arrow {{ align-self: center; color: var(--rr-accent); font-size: 1.1rem; font-weight: 700; }}
.rr-operational-strip {{
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    margin: .45rem 0 .8rem;
    border: 1px solid var(--rr-border);
    border-radius: 4px;
}}
.rr-operational-item {{ min-width: 0; padding: .68rem .82rem; }}
.rr-operational-item + .rr-operational-item {{ border-left: 1px solid var(--rr-border); }}
.rr-operational-label {{ color: var(--rr-muted); font-size: .68rem; font-weight: 700; letter-spacing: .07em; text-transform: uppercase; }}
.rr-operational-value {{ margin-top: .18rem; color: var(--rr-text); font-size: 1.2rem; font-weight: 750; line-height: 1.2; }}
.rr-operational-note {{ margin-top: .2rem; color: var(--rr-muted); font-size: .72rem; line-height: 1.25; }}
.rr-section-kicker {{ margin: .15rem 0 .12rem; color: var(--rr-accent); font-size: .66rem; font-weight: 750; letter-spacing: .11em; text-transform: uppercase; }}
.rr-form-step {{ margin: .55rem 0 .35rem; padding-top: .45rem; border-top: 1px solid var(--rr-border); color: var(--rr-accent); font-size: .68rem; font-weight: 750; letter-spacing: .1em; }}
@media (max-width: 760px) {{
    .rr-workflow {{ grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }}
    .rr-flow-arrow {{ display: none; }}
    .rr-operational-strip {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .rr-operational-item:nth-child(3) {{ border-left: 0; border-top: 1px solid var(--rr-border); }}
    .rr-operational-item:nth-child(4) {{ border-top: 1px solid var(--rr-border); }}
}}
[data-testid="stDataFrame"], [data-testid="stTable"], [data-testid="stVegaLiteChart"],
[data-testid="stMap"], [data-testid="stGraphVizChart"] {{
    border: 1px solid var(--rr-border);
    border-radius: 5px;
    overflow: hidden;
    background: var(--rr-panel);
}}
[data-testid="stAlert"] {{
    border-radius: 4px;
    border: 1px solid var(--rr-border);
    background: var(--rr-panel-soft);
}}
[data-testid="stTabs"] {{ border-bottom: 1px solid var(--rr-border); }}
[data-testid="stTabs"] button {{
    color: var(--rr-muted);
    font-size: .82rem;
    font-weight: 650;
}}
[data-testid="stTabs"] button {{
    border-radius: 3px 3px 0 0;
    transition: color .14s ease, background-color .14s ease, border-color .14s ease;
}}
[data-testid="stTabs"] button:hover {{
    color: var(--rr-text);
    background: color-mix(in srgb, var(--rr-panel-soft) 82%, var(--rr-accent));
}}
[data-testid="stTabs"] button[aria-selected="true"] {{
    color: var(--rr-accent);
    background: color-mix(in srgb, var(--rr-panel-soft) 90%, var(--rr-accent));
    border-bottom-color: var(--rr-accent);
}}
[data-testid="stButton"] button, [data-testid="stDownloadButton"] button {{
    color: var(--rr-text);
    background: var(--rr-panel-soft);
    border: 1px solid var(--rr-border);
    border-radius: 4px;
    font-weight: 700;
    transition: background-color .14s ease, color .14s ease, border-color .14s ease;
}}
[data-testid="stButton"] button[kind="primary"],
[data-testid="stFormSubmitButton"],
[data-testid="stFormSubmitButton"] button {{
    background: var(--rr-teal) !important;
    border-color: var(--rr-teal) !important;
    color: var(--rr-button-text) !important;
    -webkit-text-fill-color: var(--rr-button-text) !important;
}}
[data-testid="stButton"] button[kind="primary"]:hover,
[data-testid="stFormSubmitButton"]:hover,
[data-testid="stFormSubmitButton"] button:hover {{
    background: var(--rr-teal-hover) !important;
    border-color: var(--rr-teal-hover) !important;
    color: var(--rr-button-text) !important;
    -webkit-text-fill-color: var(--rr-button-text) !important;
}}
[data-testid="stButton"] button[kind="primary"]:active,
[data-testid="stFormSubmitButton"]:active,
[data-testid="stFormSubmitButton"] button:active {{
    background: var(--rr-teal-hover) !important;
    border-color: var(--rr-teal-hover) !important;
    color: var(--rr-button-text) !important;
    -webkit-text-fill-color: var(--rr-button-text) !important;
}}
[data-testid="stButton"] button[kind="primary"]:focus-visible,
[data-testid="stFormSubmitButton"]:focus-visible,
[data-testid="stFormSubmitButton"] button:focus-visible {{
    outline: 2px solid var(--rr-accent) !important;
    outline-offset: 2px;
}}
[data-testid="stButton"] button[kind="primary"]:disabled,
[data-testid="stFormSubmitButton"]:disabled,
[data-testid="stFormSubmitButton"] button:disabled {{
    background: var(--rr-faint) !important;
    border-color: var(--rr-faint) !important;
    color: var(--rr-button-text) !important;
    -webkit-text-fill-color: var(--rr-button-text) !important;
    opacity: 1 !important;
    cursor: not-allowed;
}}
[data-testid="stButton"] button:not([kind="primary"]):hover,
[data-testid="stDownloadButton"] button:hover {{
    color: var(--rr-text);
    background: color-mix(in srgb, var(--rr-panel-soft) 86%, var(--rr-accent));
    border-color: var(--rr-accent);
}}
[data-testid="stButton"] button:disabled,
[data-testid="stDownloadButton"] button:disabled {{
    color: var(--rr-muted);
    -webkit-text-fill-color: var(--rr-muted);
    background: var(--rr-panel-soft);
    border-color: var(--rr-border);
    opacity: 1;
    cursor: not-allowed;
}}
[data-testid="stDataFrame"] tbody tr:hover,
[data-testid="stTable"] tbody tr:hover {{
    background-color: color-mix(in srgb, var(--rr-panel-soft) 84%, var(--rr-accent));
}}
[data-testid="stSelectbox"] [role="combobox"],
[data-testid="stMultiSelect"] [role="combobox"],
[data-testid="stCheckbox"] label,
[data-testid="stRadio"] label {{
    transition: background-color .14s ease, border-color .14s ease, color .14s ease;
}}
@media (hover: hover) {{
    [data-testid="stSelectbox"] [role="combobox"]:hover,
    [data-testid="stMultiSelect"] [role="combobox"]:hover,
    [data-testid="stCheckbox"] label:hover,
    [data-testid="stRadio"] label:hover {{
        border-color: var(--rr-accent);
        color: var(--rr-text);
    }}
}}
[data-testid="stExpander"] details {{
    border: 1px solid var(--rr-border);
    border-radius: 5px;
    background: var(--rr-panel);
}}
[data-testid="stTextInput"] input, [data-testid="stNumberInput"] input,
[data-testid="stTextArea"] textarea, [data-testid="stSelectbox"] [role="combobox"] {{
    color: var(--rr-text);
    background: var(--rr-input);
    border-color: var(--rr-border);
    border-radius: 4px;
}}
[data-testid="stSidebar"] input, [data-testid="stSidebar"] textarea {{
    color: var(--rr-text);
    background: var(--rr-panel-soft);
}}
[data-testid="stTextInput"] input, [data-testid="stNumberInput"] input,
[data-testid="stTextArea"] textarea, [data-testid="stChatInput"] textarea,
[data-testid="stSelectbox"] [role="combobox"] {{
    color: var(--rr-text) !important;
    -webkit-text-fill-color: var(--rr-text);
    background: var(--rr-input) !important;
    border-color: var(--rr-border) !important;
}}
input::placeholder, textarea::placeholder {{
    color: var(--rr-muted) !important;
    opacity: 1;
}}
[data-baseweb="popover"], [data-baseweb="menu"], [role="listbox"],
[role="option"], [role="tooltip"], [data-baseweb="tooltip"] {{
    color: var(--rr-text) !important;
    background-color: var(--rr-panel-soft) !important;
    border-color: var(--rr-border) !important;
}}
[role="option"]:hover, [role="option"][aria-selected="true"] {{
    color: var(--rr-text) !important;
    background-color: var(--rr-panel) !important;
}}
[data-testid="stTooltipContent"] {{
    color: var(--rr-text) !important;
    background: var(--rr-panel-soft) !important;
    border: 1px solid var(--rr-border);
}}
.vega-tooltip {{
    color: var(--rr-text) !important;
    background: var(--rr-panel-soft) !important;
    border: 1px solid var(--rr-border) !important;
}}
.vega-tooltip table, .vega-tooltip th, .vega-tooltip td {{
    color: var(--rr-text) !important;
    background: var(--rr-panel-soft) !important;
}}
[data-testid="stCheckbox"] label, [data-testid="stRadio"] label {{
    color: var(--rr-text);
}}
a {{ color: var(--rr-accent); }}
[data-testid="stMarkdownContainer"] {{ color: var(--rr-text); }}
[data-testid="stMarkdownContainer"] p, [data-testid="stCaptionContainer"] {{
    color: var(--rr-muted);
}}
[data-testid="stMarkdownContainer"] code, [data-testid="stCode"] {{
    color: var(--rr-text);
    background: var(--rr-panel-soft);
}}
[data-testid="stAlert"] [data-testid="stMarkdownContainer"],
[data-testid="stAlert"] p {{
    color: var(--rr-text);
}}
[data-testid="stDataFrame"], [data-testid="stTable"] {{
    color: var(--rr-text);
    color-scheme: inherit;
}}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] {{
    color: var(--rr-sidebar-text);
}}
[data-testid="stSidebarCollapsedControl"] button {{
    border: 1px solid var(--rr-border);
    border-radius: 4px;
    background: var(--rr-panel);
}}
hr {{ border-color: var(--rr-border); }}
:focus-visible {{ outline: 2px solid var(--rr-accent) !important; outline-offset: 2px; }}
@media (max-width: 800px) {{
    [data-testid="stMainBlockContainer"], .main .block-container {{ padding: 3.75rem .7rem 1.5rem; }}
    [data-testid="stMetric"] {{ min-height: 78px; padding: .55rem; }}
}}
@media (prefers-reduced-motion: reduce) {{
    *, *::before, *::after {{ animation-duration: .01ms !important; transition-duration: .01ms !important; }}
}}
</style>""",
    unsafe_allow_html=True,
)

# ------------------------------------------------------------------ top navigation
# The three pages sit in a horizontal bar at the top instead of the sidebar list
# (.streamlit/config.toml turns the sidebar page list off). Same block in all three pages.
def top_nav(active: str):
    st.markdown("""<style>
.rr-brand {{ font-family: "Bahnschrift", "Avenir Next", "Segoe UI", sans-serif; font-size: 1.4rem;
            font-weight: 750; letter-spacing: -.04em; color: var(--rr-text); white-space: nowrap; }}
.rr-brand span {{ color: var(--rr-accent); }}
.st-key-rr_topnav .rr-brand {{ line-height: 1; transform: translateY(-.4rem); }}   /* level with the page links */
.st-key-rr_topnav {{ border-bottom: 1px solid var(--rr-border); padding-bottom: .35rem; margin-bottom: .6rem; }}
.st-key-rr_topnav [data-testid="stPageLink"] {{ display: flex; justify-content: center; }}
.st-key-rr_topnav [class*="st-key-rr_nav_"] {{ align-items: center; }}
.st-key-rr_topnav [data-testid="stPageLink"] a {{ justify-content: center; border-radius: 6px; }}
.st-key-rr_topnav [data-testid="stPageLink"] a:hover {{ background: color-mix(in srgb, var(--rr-accent) 12%, transparent); }}
.st-key-rr_nav_active [data-testid="stPageLink"] a {{
    background: color-mix(in srgb, var(--rr-accent) 15%, transparent);
    border-bottom: 2px solid var(--rr-accent); border-radius: 6px 6px 0 0; }}
.st-key-rr_nav_active [data-testid="stPageLink"] a p {{ color: var(--rr-text); font-weight: 650; }}
</style>""".format(), unsafe_allow_html=True)
    links = [("app", "app.py", "app", ":material/hub:"),
             ("report", "pages/1_Supplier_report.py", "Supplier report", ":material/report:"),
             ("showcase", "pages/2_Live_showcase.py", "Live showcase", ":material/auto_awesome:"),
             ("about", "pages/3_About.py", "About", ":material/info:")]
    with st.container(key="rr_topnav"):
        # logo on the left; the page links in the middle
        cols = st.columns([2.2, 1.5, 1.5, 1.5, 1.5, 1.6], vertical_alignment="center")
        cols[0].markdown('<div class="rr-brand">Re<span>Route</span></div>', unsafe_allow_html=True)
        for col, (name, page, label, icon) in zip(cols[1:5], links):
            with col.container(key="rr_nav_active" if name == active else f"rr_nav_{name}"):
                st.page_link(page, label=label, icon=icon)

top_nav("report")

st.markdown("SUPPLIER PORTAL  /  INCIDENT INTAKE")
T = db.load_tables()
sup = T["suppliers"].sort_values("name")
labels = {f"{r.name} ({r.city})": r.supplier_id for r in sup.itertuples()}

_, form_col, _ = st.columns([1, 3, 1], gap="large")
with form_col:
    st.title("Supplier disruption report")
    st.caption("Send an early signal to Kaveri EV Motors planning so your delivery impact can be assessed.")
    with st.container(border=True):
        with st.form("report"):
            supplier_label, supplier_field = st.columns([1, 2], gap="large")
            with supplier_label:
                st.markdown('<div class="rr-form-step">01  /  SUPPLIER INFORMATION</div>', unsafe_allow_html=True)
                st.caption("Identify the affected supplier.")
            with supplier_field:
                who = st.selectbox("Your company", list(labels))

            st.divider()
            detail_label, detail_fields = st.columns([1, 2], gap="large")
            with detail_label:
                st.markdown('<div class="rr-form-step">02  /  DISRUPTION DETAILS</div>', unsafe_allow_html=True)
                st.caption("Describe the operational interruption.")
            with detail_fields:
                issue_col, days_col = st.columns(2, gap="small")
                with issue_col:
                    issue = st.selectbox("What happened?", ["flood", "strike", "fire", "power", "transport", "equipment"],
                                         format_func=lambda x: {"flood": "Flood or heavy rain", "strike": "Strike or bandh",
                                                                "fire": "Fire or accident", "power": "Power cut",
                                                                "transport": "Transport or road problem",
                                                                "equipment": "Machine breakdown"}[x])
                with days_col:
                    days = st.number_input("Expected disruption (days)", min_value=1, max_value=60, value=3)
                note = st.text_input("Additional information (optional)")

            st.divider()
            footer_note, submit_col = st.columns([3, 1], vertical_alignment="center")
            with footer_note:
                st.caption("Your report is sent to the planning team for assessment.")
            with submit_col:
                sent = st.form_submit_button("Send Report", type="primary", width="stretch")

if sent:
    report = {"supplier_id": labels[who], "issue_type": issue, "days_down": int(days), "note": note}
    st.session_state.result = agent.analyze_report(report, T, save=True)
    st.session_state.chat = []
    st.success("Thank you. Your buyer's planning team has been alerted.")
    st.caption("Planner view: open the main ReRoute page to see the recovery plans for this report.")
