"""ReRoute planner dashboard.  Run:  streamlit run app.py"""
import json
from html import escape
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from reroute import agent, config, db, explain, llm

st.set_page_config(page_title="ReRoute", layout="wide", initial_sidebar_state="collapsed")
_theme_context = getattr(getattr(st, "context", None), "theme", None)
LIGHT_MODE = getattr(_theme_context, "type", None) == "light"
palette = {
    "page": "#E7EFEE" if LIGHT_MODE else "#061820",
    "panel": "#FFFFFF" if LIGHT_MODE else "#0B2C36",
    "panel_soft": "#F0F7F5" if LIGHT_MODE else "#103743",
    "text": "#0B2932" if LIGHT_MODE else "#E8F4F6",
    "muted": "#547078" if LIGHT_MODE else "#B0C7CE",
    "accent": "#007E8A" if LIGHT_MODE else "#00D9E8",
    "on_accent": "#FFFFFF" if LIGHT_MODE else "#03262B",
    "teal": "#087F73" if LIGHT_MODE else "#20C6B7",
    "border": "rgba(0, 126, 138, .30)" if LIGHT_MODE else "rgba(0, 217, 232, .28)",
    "danger": "#C13F55" if LIGHT_MODE else "#FF5C70",
    "warning": "#8A5600" if LIGHT_MODE else "#F4B942",
    "success": "#187A5B" if LIGHT_MODE else "#32D296",
    "sidebar": "#E0ECEA" if LIGHT_MODE else "#041319",
    "sidebar_text": "#18363D" if LIGHT_MODE else "#C5D8DC",
    "card": "#FFFFFF" if LIGHT_MODE else "#0B2831",
}
st.markdown(
    f"""<style>
:root {{
    --rr-page: var(--st-background-color, {palette["page"]});
    --rr-panel: var(--st-secondary-background-color, {palette["panel"]});
    --rr-panel-soft: color-mix(in srgb, var(--rr-panel) 76%, var(--rr-page));
    --rr-text: var(--st-text-color, {palette["text"]});
    --rr-muted: color-mix(in srgb, var(--rr-text) 68%, var(--rr-panel));
    --rr-accent: color-mix(in srgb, var(--rr-text) 58%, #00D9E8 42%);
    --rr-button-bg: #006B75;
    --rr-button-text: #FFFFFF;
    --rr-teal: #20C6B7;
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
    padding: 1.05rem clamp(.85rem, 1.8vw, 1.8rem) 2.5rem;
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
[data-testid="stMap"] canvas {{ filter: saturate(1.12) contrast(1.06) drop-shadow(0 0 2px rgba(231, 248, 250, .48)); }}
.rr-map-legend {{
    display: flex;
    flex-direction: column;
    gap: .62rem;
    margin-top: .25rem;
    padding: .75rem .65rem;
    border: 1px solid var(--rr-border);
    border-radius: 5px;
    background: var(--rr-panel-soft);
}}
.rr-map-legend-title {{
    margin-bottom: .12rem;
    color: var(--rr-accent);
    font-size: .66rem;
    font-weight: 750;
    letter-spacing: .11em;
}}
.rr-legend-row {{
    display: flex;
    align-items: center;
    gap: .5rem;
    color: var(--rr-text);
    font-size: .75rem;
    line-height: 1.25;
}}
.rr-legend-dot {{
    flex: 0 0 .68rem;
    width: .68rem;
    height: .68rem;
    border: 1.5px solid var(--rr-text);
    border-radius: 50%;
    box-shadow: 0 0 0 1px color-mix(in srgb, var(--rr-accent) 24%, transparent);
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
    background: #006B75 !important;
    border-color: #006B75 !important;
    color: #FFFFFF !important;
    -webkit-text-fill-color: #FFFFFF !important;
}}
[data-testid="stButton"] button[kind="primary"]:hover,
[data-testid="stFormSubmitButton"]:hover,
[data-testid="stFormSubmitButton"] button:hover {{
    background: #005761 !important;
    border-color: #005761 !important;
    color: #FFFFFF !important;
    -webkit-text-fill-color: #FFFFFF !important;
}}
[data-testid="stButton"] button[kind="primary"]:active,
[data-testid="stFormSubmitButton"]:active,
[data-testid="stFormSubmitButton"] button:active {{
    background: #004B53 !important;
    border-color: #004B53 !important;
    color: #FFFFFF !important;
    -webkit-text-fill-color: #FFFFFF !important;
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
    background: #526F73 !important;
    border-color: #526F73 !important;
    color: #FFFFFF !important;
    -webkit-text-fill-color: #FFFFFF !important;
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
    background: var(--rr-panel-soft);
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
    background: var(--rr-panel-soft) !important;
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
    [data-testid="stMainBlockContainer"], .main .block-container {{ padding: .8rem .7rem 1.5rem; }}
    [data-testid="stMetric"] {{ min-height: 78px; padding: .55rem; }}
}}
@media (prefers-reduced-motion: reduce) {{
    *, *::before, *::after {{ animation-duration: .01ms !important; transition-duration: .01ms !important; }}
}}
</style>""",
    unsafe_allow_html=True,
)

SIGNALS = json.loads((config.DATA_DIR / "sample_signals.json").read_text(encoding="utf-8"))
DEMO = {
    "Hosur flood (news)": "N01",
    "Pune magnet plant fire (Tier-2, news)": "N03",
    "Tamil Nadu transport strike (news)": "N04",
    "IMD red alert for Chennai": "N02",
    "Cricket score (not a disruption)": "N06",
}
TEXT = {s["id"]: s for s in SIGNALS}


@st.cache_resource
def ensure_db():
    if db.backend() == "sqlite" and not Path(config.SQLITE_PATH).exists():
        db.init_db()
    db.ensure_runtime_tables()   # adds or upgrades the approval and audit tables
    return True


@st.cache_data(ttl=300)
def tables():
    return db.load_tables()


ensure_db()
T = tables()

# ------------------------------------------------------------------ sidebar
mode = st.sidebar.radio("Signal", ["Demo scenario", "Paste news or IMD alert", "Latest supplier report"])
run = False
if mode == "Demo scenario":
    pick = st.sidebar.selectbox("Scenario", list(DEMO))
    st.sidebar.write(f"_{TEXT[DEMO[pick]]['text']}_")
    if st.sidebar.button("Analyse", type="primary"):
        s = TEXT[DEMO[pick]]
        st.session_state.result = agent.analyze_text(s["text"], T, source=s["source"])
        st.session_state.pop("approved_plan_name", None)
        run = True
elif mode == "Paste news or IMD alert":
    text = st.sidebar.text_area("Text", height=140, placeholder="Paste a news line or weather alert")
    if st.sidebar.button("Analyse", type="primary", disabled=not text.strip()):
        st.session_state.result = agent.analyze_text(text, T)
        st.session_state.pop("approved_plan_name", None)
        run = True
else:
    reports = db.read_rows("supplier_reports")
    if reports.empty:
        st.sidebar.info("No supplier reports yet. Open the Supplier report page to send one.")
    else:
        # HANA returns rows in no fixed order, so sort by time before taking the newest
        last = reports.sort_values("created_at").iloc[-1].to_dict()
        name = T["suppliers"].set_index("supplier_id").loc[last["supplier_id"], "name"]
        st.sidebar.write(f"**{name}**: {last['issue_type']}, {last['days_down']} days. {last['note']}")
        if st.sidebar.button("Analyse", type="primary"):
            st.session_state.result = agent.analyze_report(
                {k: last[k] for k in ["supplier_id", "issue_type", "days_down", "note"]}, T, save=False)
            st.session_state.pop("approved_plan_name", None)
            run = True
if run:
    st.session_state.chat = []

st.sidebar.divider()
st.sidebar.caption(f"Database: {'SAP HANA Cloud' if db.backend() == 'hana' else 'SQLite (local)'}")
st.sidebar.caption(f"Language model: {llm.status()}")
st.sidebar.caption(f"Data as of {T['meta'].set_index('key').loc['as_of', 'value']}")

# ------------------------------------------------------------------ map helper
def network_map(down: pd.DataFrame | None = None):
    sup = T["suppliers"].copy()
    days = dict(zip(down["supplier_id"], down["via"])) if down is not None and len(down) else {}
    red, amber, grey, blue = "#FF5C70", "#F4B942", "#91A7B0", "#45B7FF"
    sup["color"] = sup["supplier_id"].map(lambda s: grey if s not in days else red if days[s] == "hit directly" else amber)
    sup["size"] = sup["supplier_id"].map(lambda s: 9000 if s in days else 5000)
    city = T["cities"].set_index("city")
    plant = pd.DataFrame([{"lat": city.loc["Bidadi", "lat"], "lon": city.loc["Bidadi", "lon"], "color": blue, "size": 12000}])
    # spread suppliers in the same city a little so every dot is visible
    sup["n"] = sup.groupby("city").cumcount()
    sup["lat"] = sup["lat"] + sup["n"] * 0.04
    pts = pd.concat([sup[["lat", "lon", "color", "size"]], plant])
    with st.container(border=True):
        st.markdown("#### Supply network")
        st.map(pts, latitude="lat", longitude="lon", color="color", size="size")


def show_map_legend():
    red, amber, grey, blue = "#FF5C70", "#F4B942", "#91A7B0", "#45B7FF"
    with st.container(border=True):
        st.markdown(
            f"""<div class="rr-map-legend">
                <div class="rr-map-legend-title">MAP KEY</div>
                <div class="rr-legend-row"><span class="rr-legend-dot" style="background:{blue}"></span><span>Plant · Bidadi</span></div>
                <div class="rr-legend-row"><span class="rr-legend-dot" style="background:{red}"></span><span>Directly affected</span></div>
                <div class="rr-legend-row"><span class="rr-legend-dot" style="background:{amber}"></span><span>Indirectly affected</span></div>
                <div class="rr-legend-row"><span class="rr-legend-dot" style="background:{grey}"></span><span>Unaffected supplier</span></div>
            </div>""",
            unsafe_allow_html=True,
        )


def show_workflow_progress(result: dict | None = None, slot=None):
    """Render workflow status only from the current analysis result and its approval state."""
    stages = [
        ("Disruption", "neutral", "Ready"),
        ("Impacted Orders", "neutral", "Ready"),
        ("Recovery Plan", "neutral", "Ready"),
        ("Approval", "neutral", "Ready"),
    ]

    if result:
        stages = [
            ("Disruption", "neutral", "Status unavailable"),
            ("Impacted Orders", "neutral", "Status unavailable"),
            ("Recovery Plan", "neutral", "Status unavailable"),
            ("Approval", "neutral", "Status unavailable"),
        ]
        event = result.get("event")
        relevant = getattr(event, "relevant", None) if event is not None else None
        if isinstance(relevant, bool):
            stages[0] = ("Disruption", "done",
                         "Disruption detected" if relevant else "No disruption detected")
        elif event is not None:
            stages[0] = ("Disruption", "done", "Signal analyzed")

        impact = result.get("impact")
        summary = impact.get("summary") if isinstance(impact, dict) else None
        late_count = None
        pos_risk = None
        if isinstance(summary, dict):
            try:
                late_count = int(summary["sales_orders_late"])
            except (KeyError, TypeError, ValueError):
                pass
            try:
                pos_risk = int(summary["pos_at_risk"])
            except (KeyError, TypeError, ValueError):
                pass
        if late_count is not None:
            detail = f"{late_count} late orders" if late_count else "No late orders"
            stages[1] = ("Impacted Orders", "done", detail)

        plans = result.get("plans")
        plans_available = isinstance(plans, (list, tuple))
        if plans_available and plans:
            stages[2] = ("Recovery Plan", "done", f"{len(plans)} plans generated")
        elif plans_available and pos_risk == 0:
            stages[2] = ("Recovery Plan", "done", "No plan required")
        elif plans_available:
            stages[2] = ("Recovery Plan", "neutral", "No plans reported")

        approved_name = st.session_state.get("approved_plan_name")
        approved_result = st.session_state.get("approved_plan_result_ref")
        approved_current_plan = (
            approved_result is result
            and approved_name
            and plans_available
            and any(plan.get("name") == approved_name for plan in plans)
        )
        if approved_current_plan:
            stages[3] = ("Approval", "done", "Plan approved")
        elif approved_name and approved_result is None:
            stages[3] = ("Approval", "neutral", "Status unavailable")
        elif plans_available and plans:
            stages[3] = ("Approval", "current", "Awaiting planner approval")
        elif plans_available and pos_risk == 0:
            stages[3] = ("Approval", "done", "Not required")

    parts = ['<div class="rr-workflow" role="list" aria-label="Disruption to approval workflow">']
    for index, (label, state, detail) in enumerate(stages, start=1):
        state_class = {"done": "is-done", "current": "is-current", "neutral": "is-neutral"}[state]
        parts.append(
            f'<div class="rr-flow-step {state_class}" role="listitem">'
            f'<div class="rr-flow-heading"><span class="rr-flow-number">{index:02d}</span>'
            f'<strong>{escape(label)}</strong></div>'
            f'<span class="rr-flow-state">{escape(detail)}</span></div>'
        )
        if index < len(stages):
            parts.append('<span class="rr-flow-arrow" aria-hidden="true">→</span>')
    parts.append("</div>")
    target = slot if slot is not None else st
    target.markdown("".join(parts), unsafe_allow_html=True)


def show_operational_strip(summary: dict):
    """Present the existing exposure values as one compact operational readout."""
    values = [
        ("Suppliers down", summary["suppliers_down"], f"{summary['tier2_plus_down']} Tier-2 or deeper"),
        ("Purchase orders at risk", summary["pos_at_risk"], explain.inr(summary["po_value_at_risk"])),
        ("Customer orders late", summary["sales_orders_late"], f"{summary['high_priority_late']} high-priority"),
        ("Order-days late if we wait", summary["baseline_late_days"], ""),
    ]
    parts = ['<div class="rr-operational-strip" aria-label="Current network exposure">']
    for label, value, note in values:
        parts.append(
            '<div class="rr-operational-item">'
            f'<div class="rr-operational-label">{escape(str(label))}</div>'
            f'<div class="rr-operational-value">{escape(str(value))}</div>'
            f'<div class="rr-operational-note">{escape(str(note))}</div></div>'
        )
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def customer_order_risk(result: dict) -> pd.DataFrame:
    """Combine actual order deadlines with the simulation's current customer-level delay."""
    orders = T["sales_orders"].copy()
    required = {"sales_order_id", "due_date", "priority"}
    if orders.empty or not required.issubset(orders.columns):
        return pd.DataFrame()

    orders["deadline"] = pd.to_datetime(orders["due_date"], errors="coerce")
    orders = orders.dropna(subset=["deadline"]).copy()
    if orders.empty:
        return pd.DataFrame()

    baseline = result["impact"].get("sales_orders", pd.DataFrame())
    delay_by_order = (dict(zip(baseline["sales_order_id"], baseline["late_days"]))
                      if {"sales_order_id", "late_days"}.issubset(baseline.columns) else {})
    approved_name = st.session_state.get("approved_plan_name")
    approved_plan = next((p for p in result["plans"] if p["name"] == approved_name), None)
    if approved_plan is not None:
        actions = approved_plan.get("actions", pd.DataFrame())
        if {"sales_order_id", "so_late_after"}.issubset(actions.columns):
            delay_by_order.update(actions.groupby("sales_order_id")["so_late_after"].max().to_dict())

    orders["delay_days"] = orders["sales_order_id"].map(delay_by_order).fillna(0).astype(int)
    orders["predicted_date"] = orders["deadline"] + pd.to_timedelta(orders["delay_days"], unit="D")
    # Risk bands use simulated customer delay after plant stock cover.
    orders["risk"] = orders["delay_days"].map(
        lambda days: "On Track" if days == 0 else "At Risk" if days <= 3 else "Critical")
    orders["order_label"] = (orders["sales_order_id"].astype(str) + " ("
                             + orders["priority"].fillna("Unknown").astype(str) + ")")
    return orders


def show_received_supplier_reports(collapsed: bool = False):
    """Show persisted supplier reports without depending on this browser session.

    collapsed=True puts the table in a closed expander, so it doesn't push analysis results down the page.
    """
    reports = db.read_rows("supplier_reports")
    if collapsed:
        with st.expander(f"Received supplier reports ({len(reports)})", expanded=False):
            _reports_table(reports)
    else:
        st.subheader("Received Supplier Reports")
        _reports_table(reports)


def _reports_table(reports: pd.DataFrame):
    if reports.empty:
        st.info("No supplier reports received yet.")
        return

    supplier_names = T["suppliers"][["supplier_id", "name"]].rename(columns={"name": "Supplier name"})
    view = reports.merge(supplier_names, on="supplier_id", how="left")
    view["_submitted_at"] = pd.to_datetime(view["created_at"], errors="coerce")
    view = view.sort_values("_submitted_at", ascending=False, na_position="last")
    view = view.rename(columns={
        "issue_type": "Reported issue",
        "days_down": "Expected disruption duration (days)",
        "created_at": "Submission timestamp",
    })
    st.dataframe(
        view[[
            "Supplier name",
            "Reported issue",
            "Expected disruption duration (days)",
            "Submission timestamp",
        ]],
        hide_index=True,
        width="stretch",
    )

# ------------------------------------------------------------------ main
res = st.session_state.get("result")
if not res:
    st.markdown("OPERATIONS  /  SOUTH INDIA NETWORK")
    st.title("ReRoute Control Tower")
    st.caption("Kaveri EV Motors · Supply Chain Resilience")
    st.caption("Select a signal in the sidebar to assess its effect on the supplier network.")
    show_workflow_progress()
    disruption_col, map_col, intel_col = st.columns([2.2, 6, 2.2], gap="medium")
    with disruption_col:
        with st.container(border=True):
            st.markdown('<div class="rr-section-kicker">ACTIVE EVENT</div>', unsafe_allow_html=True)
            st.markdown("#### Disruption intelligence")
            st.info("No analysis is selected. Choose a demo signal, paste an alert, or select a supplier report in the sidebar.")
    with map_col:
        network_map()
    with intel_col:
        with st.container(border=True):
            st.markdown('<div class="rr-section-kicker">LIVE INTELLIGENCE</div>', unsafe_allow_html=True)
            st.markdown("#### Network command")
            st.caption("Supplier and plant locations across the current network.")
            show_map_legend()
    show_received_supplier_reports()
    st.stop()

ev, imp, plans, s = res["event"], res["impact"], res["plans"], res["impact"]["summary"]
title = f"{ev.event_type.title()}" + (f" · {ev.location}" if ev.location else "") + (f" · {ev.state}" if ev.scope == "state" else "")
st.markdown("OPERATIONS  /  SOUTH INDIA NETWORK")
st.title(title if ev.relevant else "No disruption detected")
st.caption("Kaveri EV Motors · Supply Chain Resilience")
st.caption(f"{ev.text}  \nDetected by: {ev.method} · expected {ev.duration_days} days · severity {ev.severity}/5 · "
           f"{res['timings_ms']['total']:.0f} ms from signal to plan")
workflow_progress_slot = st.empty()
show_workflow_progress(res, workflow_progress_slot)
show_received_supplier_reports(collapsed=True)

if not ev.relevant or not ev.matched:
    st.info("This signal doesn't touch any supplier in our network, so there is nothing to replan.")
    disruption_col, map_col, intel_col = st.columns([2.2, 6, 2.2], gap="medium")
    with disruption_col:
        with st.container(border=True):
            st.markdown('<div class="rr-section-kicker">ACTIVE EVENT</div>', unsafe_allow_html=True)
            st.markdown("#### Disruption profile")
            st.markdown(f"**{ev.event_type.title()}**  \n{ev.location or ev.state or 'Network-wide'}")
            st.caption(f"Severity {ev.severity}/5 · expected duration {ev.duration_days} days")
            st.markdown("#### Signal")
            st.write(ev.text)
            st.caption(f"Detected by {ev.method} · {res['timings_ms']['total']:.0f} ms to classify")
    with map_col:
        network_map()
    with intel_col:
        with st.container(border=True):
            st.markdown('<div class="rr-section-kicker">LIVE INTELLIGENCE</div>', unsafe_allow_html=True)
            st.markdown("#### Network command")
            st.caption("No suppliers in the current network match this signal.")
            show_map_legend()
    st.stop()

with st.container(border=True):
    st.markdown("##### NETWORK COMMAND  /  LIVE EXPOSURE")
    show_operational_strip(s)
    disruption_col, map_col, intel_col = st.columns([2.2, 6, 2.2], gap="medium")
    with disruption_col:
        st.markdown('<div class="rr-section-kicker">ACTIVE EVENT</div>', unsafe_allow_html=True)
        st.markdown("#### Disruption profile")
        st.markdown(f"**{ev.event_type.title()}**  \n{ev.location or ev.state or 'Network-wide'}")
        st.caption(f"Severity {ev.severity}/5 · expected duration {ev.duration_days} days")
        st.markdown("#### Signal")
        st.write(ev.text)
        st.caption(f"Detected by {ev.method} · {res['timings_ms']['total']:.0f} ms to plan")
    with map_col:
        network_map(imp["down"])
    with intel_col:
        st.markdown('<div class="rr-section-kicker">LIVE INTELLIGENCE</div>', unsafe_allow_html=True)
        st.markdown("#### Network command")
        st.caption("Current supplier impact is reflected on the map and in the exposure strip.")
        show_map_legend()

tab_impact, tab_risk, tab_plan, tab_map, tab_ask, tab_done = st.tabs(
    ["Impact", "Customer Order Risk Analysis", "Recovery plans", "Map", "Ask ReRoute", "Approved actions"])

with tab_plan:
    if s["pos_at_risk"] == 0:
        st.success("Safety stock and lead times cover this event. No purchase order needs to change.")
    else:
        st.info(res["explanation"] + f"\n\n_Written by: {'Generative AI Hub' if res['explain_method'] == 'llm' else 'offline template'}_")

        for p in plans:
            t = p["totals"]

            with st.container(border=p.get("recommended", False)):
                if p.get("recommended"):
                    st.success("⭐ RECOMMENDED PLAN")

                st.subheader(p["name"])

                c1, c2, c3, c4 = st.columns(4)

                c1.metric("Extra cost", explain.inr(t["extra_cost"]))
                c2.metric(
                    "Order-days of delay avoided",
                    f"{t['delay_avoided_days']} of {t['late_days_before']}"
                )
                c3.metric(
                    "High-priority orders on time",
                    f"{t['high_priority_protected']} of {t['high_priority_affected']}"
                )
                c4.metric("Purchase orders changed", t["pos_changed"])

                if st.button(
                    f"Approve {p['name']}",
                    key=f"approve-{p['name']}",
                    type="primary" if p.get("recommended") else "secondary"
                ):
                    n = agent.approve(res, p["name"])
                    st.session_state.approved_plan_name = p["name"]
                    st.session_state.approved_plan_result_ref = res
                    show_workflow_progress(res, workflow_progress_slot)
                    st.success(
                        f"Approved. {n} PO changes queued and supplier messages drafted."
                    )

        for p in plans:
            acts = p["actions"]
            with st.expander(f"{p['name']}: what changes"):
                if acts.empty or (acts["action"] == "wait").all():
                    st.write("No purchase order changes; customer orders absorb the delay.")
                else:
                    st.dataframe(acts[acts["action"] != "wait"][["po_id", "so_priority", "material", "qty", "from_supplier",
                                                                  "action", "to_supplier", "delay_before", "delay_after",
                                                                  "extra_cost"]], hide_index=True, width="stretch")

with tab_impact:
    st.subheader("Suppliers down")
    st.dataframe(imp["down"], hide_index=True, width="stretch")
    st.subheader("Customer orders that slip if we do nothing")
    st.dataframe(imp["sales_orders"][["sales_order_id", "customer", "product", "qty", "due_date", "priority", "late_days"]],
                 hide_index=True, width="stretch")
    st.subheader("Purchase orders at risk")
    st.dataframe(imp["pos"][["po_id", "supplier", "material", "qty", "value", "due_date", "new_arrival", "delay_days",
                             "cover_days", "for_sales_order_id", "so_priority"]], hide_index=True, width="stretch")

with tab_risk:
    st.subheader("Customer Order Risk Analysis")
    risk_orders = customer_order_risk(res)
    if risk_orders.empty:
        st.info("Customer order deadlines or simulation delay data are unavailable for this run.")
    else:
        approved_name = st.session_state.get("approved_plan_name")
        if approved_name:
            st.caption(f"Predicted dates reflect the approved {approved_name} plan.")
        else:
            st.caption("Predicted dates show the current impact if no recovery plan is applied.")

        risk_counts = (risk_orders["risk"].value_counts()
                       .reindex(["On Track", "At Risk", "Critical"], fill_value=0)
                       .rename_axis("Risk").reset_index(name="Orders"))
        st.caption("Risk bands use predicted customer delay after stock cover: On Track = 0 days, At Risk = 1–3 days, Critical = 4+ days.")
        risk_counts["Legend"] = risk_counts.apply(lambda row: f"{row['Risk']} · {row['Orders']}", axis=1)
        risk_colors = [palette["success"], palette["warning"], palette["danger"]]
        donut = alt.Chart(risk_counts).mark_arc(innerRadius=68, outerRadius=108).encode(
            theta=alt.Theta("Orders:Q", stack=True),
            color=alt.Color("Legend:N", title=None, scale=alt.Scale(
                domain=risk_counts["Legend"].tolist(), range=risk_colors),
                legend=alt.Legend(orient="bottom", labelLimit=180)),
            order=alt.Order("Risk:N", sort="ascending"),
            tooltip=[alt.Tooltip("Risk:N", title="Risk"), alt.Tooltip("Orders:Q", title="Orders")],
        )
        total_orders = len(risk_orders)
        center_total = alt.Chart(pd.DataFrame({"label": [str(total_orders)]})).mark_text(
            fontSize=27, fontWeight="bold", color=palette["text"], dy=-8).encode(text="label:N")
        center_label = alt.Chart(pd.DataFrame({"label": ["Total orders"]})).mark_text(
            fontSize=12, color=palette["muted"], dy=17).encode(text="label:N")
        chart_theme = {
            "background": "transparent",
            "axis": alt.AxisConfig(labelColor=palette["muted"], titleColor=palette["text"],
                                   gridColor=palette["border"], domainColor=palette["border"],
                                   tickColor=palette["border"]),
            "legend": alt.LegendConfig(labelColor=palette["muted"], titleColor=palette["text"]),
            "view": alt.ViewConfig(stroke=palette["border"]),
        }
        st.markdown("#### Order Risk Summary")
        st.altair_chart((donut + center_total + center_label).properties(height=300).configure(**chart_theme),
                        width="stretch")

        st.markdown("#### Customer Order Deadline Timeline")
        chart_orders = risk_orders.copy()
        chart_orders["deadline_label"] = chart_orders["deadline"].dt.strftime("%b %d, %Y")
        chart_orders["predicted_label"] = chart_orders["predicted_date"].dt.strftime("%b %d, %Y")
        tooltip = [alt.Tooltip("sales_order_id:N", title="Order"),
                   alt.Tooltip("priority:N", title="Priority"),
                   alt.Tooltip("risk:N", title="Risk"),
                   alt.Tooltip("deadline_label:N", title="Required deadline"),
                   alt.Tooltip("predicted_label:N", title="Predicted delivery"),
                   alt.Tooltip("delay_days:Q", title="Predicted delay (days)")]
        sort_orders = alt.SortField("predicted_date", order="ascending")
        y_axis = alt.Y("order_label:N", sort=sort_orders, title="Customer order (priority)")
        timeline = alt.Chart(chart_orders)
        delay_lines = timeline.mark_rule(strokeWidth=3).encode(
            y=y_axis,
            x=alt.X("deadline:T", title="Delivery date", axis=alt.Axis(format="%b %d")),
            x2="predicted_date:T",
            color=alt.Color("risk:N", title="Risk", legend=alt.Legend(orient="bottom"), scale=alt.Scale(
                domain=["On Track", "At Risk", "Critical"], range=[palette["success"], palette["warning"], palette["danger"]])),
            tooltip=tooltip,
        )
        date_points = chart_orders.melt(
            id_vars=["order_label", "sales_order_id", "priority", "risk", "delay_days", "deadline_label", "predicted_label"],
            value_vars=["deadline", "predicted_date"], var_name="date_type", value_name="date")
        date_points["date_type"] = date_points["date_type"].map(
            {"deadline": "Required deadline", "predicted_date": "Predicted delivery"})
        points = alt.Chart(date_points).mark_point(filled=True, size=85, stroke=palette["panel"], strokeWidth=1.5).encode(
            y=alt.Y("order_label:N", sort=sort_orders, title="Customer order (priority)"),
            x=alt.X("date:T", title="Delivery date", axis=alt.Axis(format="%b %d")),
            color=alt.Color("date_type:N", title="Date", legend=alt.Legend(orient="bottom"), scale=alt.Scale(
                domain=["Required deadline", "Predicted delivery"], range=[palette["accent"], palette["danger"]])),
            shape=alt.Shape("date_type:N", title="Milestone", legend=alt.Legend(orient="bottom"), scale=alt.Scale(
                domain=["Required deadline", "Predicted delivery"], range=["diamond", "circle"])),
            tooltip=tooltip,
        )
        st.altair_chart((delay_lines + points).properties(
            height=max(320, min(760, 25 * len(chart_orders)))).configure(**chart_theme), width="stretch")

with tab_map:
    network_map(imp["down"])

with tab_ask:
    st.caption("Ask about this disruption, for example: Why not switch everything to Coimbatore? Which customers should we call?")
    for m in st.session_state.get("chat", []):
        st.chat_message(m["role"]).write(m["content"])
    q = st.chat_input("Ask ReRoute")
    if q:
        st.session_state.setdefault("chat", []).append({"role": "user", "content": q})
        st.chat_message("user").write(q)
        ans, _ = explain.answer(q, imp, plans, st.session_state["chat"][:-1])
        st.session_state["chat"].append({"role": "assistant", "content": ans})
        st.chat_message("assistant").write(ans)

with tab_done:
    done = db.read_rows("plan_actions")
    if done.empty:
        st.write("Nothing approved yet.")
    else:
        st.dataframe(done.iloc[::-1], hide_index=True, width="stretch")
    sandbox = config.DATA_DIR / "s4_sandbox_pos.csv"
    if sandbox.exists():
        st.subheader("Purchase orders pulled from the SAP S/4HANA sandbox")
        st.dataframe(pd.read_csv(sandbox), hide_index=True, width="stretch")
