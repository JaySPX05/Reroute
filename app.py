"""ReRoute planner dashboard.  Run:  streamlit run app.py"""
import json
from html import escape
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

import pydeck as pdk

from reroute import agent, config, db, explain, impact, llm, logistics, planner, signals

st.set_page_config(page_title="ReRoute", layout="wide")
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
[data-testid="stMetricLabel"], [data-testid="stMetricLabel"] * {{
    white-space: normal !important;   /* wrap long labels instead of cutting them off with "..." */
    overflow: visible !important;
    text-overflow: clip !important;
}}
[data-testid="stMetricValue"] {{ color: var(--rr-text); font-weight: 720; font-size: clamp(1.3rem, 1.9vw, 2.1rem); line-height: 1.2; }}
[data-testid="stMetricValue"] * {{
    white-space: normal !important;   /* "Rs 31.46 lakh", "No late orders": wrap instead of "Rs 31.46 la..." */
    overflow: visible !important;
    text-overflow: clip !important;
}}
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
.st-key-rr_intel_card .rr-operational-strip {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
.st-key-rr_intel_card .rr-operational-item:nth-child(3) {{ border-left: 0; }}
.st-key-rr_intel_card .rr-operational-item:nth-child(n+3) {{ border-top: 1px solid var(--rr-border); }}
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
[data-testid="stMap"], [data-testid="stDeckGlJsonChart"] {{ background: var(--rr-map-bg); }}
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

def page_footer(lines):
    """The page's status details, shown at the bottom of the page."""
    st.divider()
    for line in lines:
        st.caption(line)



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
top_nav("app")
STATUS = (f"Database: {'SAP HANA Cloud' if db.backend() == 'hana' else 'SQLite (local)'}",
          f"Language model: {llm.status()}",
          f"Data as of {T['meta'].set_index('key').loc['as_of', 'value']}")

# ------------------------------------------------------------------ page frame: header, then three boxes
# left = signal controls + analysis, centre = map, right = live network information; workflow and tabs below
header_area = st.container()
disruption_col, map_col, intel_col = st.columns([2.4, 6, 2.4], gap="medium")
left_card = disruption_col.container(border=True, key="rr_left_card")
intel_card = intel_col.container(border=True, key="rr_intel_card")

# ------------------------------------------------------------------ signal controls (left box)
with left_card:
    mode = st.radio("Signal", ["Demo scenario", "Paste news or IMD alert", "Supplier reports"])
    run = False
    glance = False
    if mode == "Demo scenario":
        pick = st.selectbox("Scenario", list(DEMO))
        st.write(f"_{TEXT[DEMO[pick]]['text']}_")
        if st.button("Analyse", type="primary"):
            s = TEXT[DEMO[pick]]
            st.session_state.result = agent.analyze_text(s["text"], T, source=s["source"])
            st.session_state.pop("approved_plan_name", None)
            run = True
    elif mode == "Paste news or IMD alert":
        text = st.text_area("Text", height=140, placeholder="Paste a news line or weather alert")
        if st.button("Analyse", type="primary", disabled=not text.strip()):
            st.session_state.result = agent.analyze_text(text, T)
            st.session_state.pop("approved_plan_name", None)
            run = True
    else:
        reports = db.supplier_reports()          # resolved reports are hidden but kept in the database
        if reports.empty:
            st.info("No open supplier reports. Open the Supplier report page to send one.")
        else:
            # newest first (HANA returns rows in no fixed order); the newest is preselected
            reports = reports.sort_values("created_at", ascending=False).reset_index(drop=True)
            names = T["suppliers"].set_index("supplier_id")["name"]
            glance = st.radio("View", ["One report", "All at a glance"], horizontal=True) == "All at a glance"

        if not reports.empty and not glance:
            def label(i: int) -> str:
                r = reports.iloc[i]
                when = str(r["created_at"])[:16].replace("T", " ")
                return f"{names.get(r['supplier_id'], r['supplier_id'])} · {r['issue_type']} · {r['days_down']} days · {when}"

            i = st.selectbox(f"Report to analyse ({len(reports)} received, newest first)",
                                     range(len(reports)), format_func=label)
            chosen = reports.iloc[i].to_dict()
            if chosen.get("note"):
                st.caption(f"Note: {chosen['note']}")
            if st.button("Analyse", type="primary"):
                st.session_state.result = agent.analyze_report(
                    {k: chosen[k] for k in ["supplier_id", "issue_type", "days_down", "note"]}, T, save=False)
                st.session_state.pop("approved_plan_name", None)
                run = True
            if st.button("Mark as resolved",
                                 help="Hide this report from the dashboard once it's dealt with. It stays in the database."):
                db.clear_supplier_report(chosen)
                st.toast(f"Marked as resolved: {label(i)}")
                st.rerun()
if run:
    st.session_state.chat = []


# ------------------------------------------------------------------ map helper
def network_map(down: pd.DataFrame | None = None):
    sup = T["suppliers"].copy()
    days = dict(zip(down["supplier_id"], down["via"])) if down is not None and len(down) else {}
    red, amber, grey, blue = palette["danger"], palette["warning"], palette["faint"], palette["teal"]  # plant: teal
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
    red, amber, grey, blue = palette["danger"], palette["warning"], palette["faint"], palette["teal"]  # plant: teal
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
        on_watch = isinstance(result.get("impact"), dict) and result["impact"].get("summary", {}).get("on_watch")
        if isinstance(relevant, bool):
            stages[0] = ("Disruption", "done",
                         "Yellow alert: on watch" if relevant and on_watch else
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
            detail = (f"{late_count} late order{'' if late_count == 1 else 's'}" if late_count else "No late orders")
            stages[1] = ("Impacted Orders", "done", detail)

        plans = result.get("plans")
        plans_available = isinstance(plans, (list, tuple))
        if plans_available and pos_risk == 0:            # nothing at risk: plans exist but change nothing
            stages[2] = ("Recovery Plan", "done", "No plan required")
        elif plans_available and plans:
            stages[2] = ("Recovery Plan", "done", f"{len(plans)} plans generated")
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
        elif plans_available and pos_risk == 0:
            stages[3] = ("Approval", "done", "Not required")
        elif plans_available and plans:
            stages[3] = ("Approval", "current", "Awaiting planner approval")

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


def _rgb(hex_color: str) -> list:
    return [int(hex_color[i:i + 2], 16) for i in (1, 3, 5)]


PLANT_COLOR = _rgb(palette["teal"])                                       # teal
ROUTE_COLORS = {"original": _rgb(palette["danger"]), "switch": _rgb(palette["accent"]),   # critical, cyan
                "expedite": [142, 68, 173]}
APPROVED_COLOR = _rgb(palette["success"])


def _hex(rgb) -> str:
    return "#%02x%02x%02x" % tuple(rgb)


def _curve(lon1, lat1, lon2, lat2, bend=0.18, n=24) -> list:
    """A gently bowed path from one point to another, so a new route never sits on top of a straight original one."""
    mx, my = (lon1 + lon2) / 2, (lat1 + lat2) / 2
    dx, dy = lon2 - lon1, lat2 - lat1
    cx, cy = mx - dy * bend, my + dx * bend          # control point, pushed sideways from the midpoint
    out = []
    for i in range(n + 1):
        t = i / n
        out.append([(1 - t) ** 2 * lon1 + 2 * (1 - t) * t * cx + t ** 2 * lon2,
                    (1 - t) ** 2 * lat1 + 2 * (1 - t) * t * cy + t ** 2 * lat2])
    return out


def map_legend(routes: pd.DataFrame, approved: bool):
    """The map key in the side panel: dot colours for places, line styles for the routes actually on the map.
    Colours are the ones route_map draws with."""
    def dot(color, label):
        return (f'<div class="rr-legend-row"><span class="rr-legend-dot" style="background:{color}"></span>'
                f'<span>{label}</span></div>')

    def line(color, label, curved):
        path = "M2 10 Q13 0 24 10" if curved else "M2 6 L24 6"
        return (f'<div class="rr-legend-row"><svg width="26" height="12" style="flex:0 0 26px">'
                f'<path d="{path}" stroke="{color}" stroke-width="3" fill="none"/></svg><span>{label}</span></div>')

    p = logistics.plant(T)
    items = [dot(_hex(PLANT_COLOR), f"Plant · {p['name']}"), dot(palette["danger"], "Supplier hit directly"),
             dot(palette["warning"], "Down through a supplier it depends on"), dot(palette["faint"], "Unaffected supplier")]
    kinds = set(routes["kind"]) if len(routes) else set()
    if "original" in kinds:
        items.append(line(_hex(ROUTE_COLORS["original"]), "Original route (disrupted)", False))
    if approved and kinds & {"switch", "expedite"}:
        items.append(line(_hex(APPROVED_COLOR), "Approved plan route", True))
    else:
        if "switch" in kinds:
            items.append(line(_hex(ROUTE_COLORS["switch"]), "New supplier route", True))
        if "expedite" in kinds:
            items.append(line(_hex(ROUTE_COLORS["expedite"]), "Express shipment, same supplier", True))
    st.markdown('<div class="rr-map-legend"><div class="rr-map-legend-title">MAP KEY</div>'
                + "".join(items) + "</div>", unsafe_allow_html=True)


def route_map(down: pd.DataFrame, routes: pd.DataFrame, approved: bool):
    """Flat 2D map: suppliers and plant as dots, disrupted original routes as straight red lines,
    the plan's routes as curves so they stay visible next to the originals. Its key is map_legend."""
    sup = T["suppliers"].copy()
    status = dict(zip(down["supplier_id"], down["via"])) if len(down) else {}
    sup["color"] = sup["supplier_id"].map(lambda s: _rgb(palette["faint"]) if s not in status else
                                          _rgb(palette["danger"]) if status[s] == "hit directly" else _rgb(palette["warning"]))
    sup["n"] = sup.groupby("city").cumcount()            # same small spread as network_map, so lines meet the dots
    sup["lat"] = sup["lat"] + sup["n"] * 0.04
    sup["label"] = sup["name"] + " (" + sup["city"] + ")" + sup["supplier_id"].map(
        lambda s: "" if s not in status else f": {status[s]}")
    sup = sup.assign(_hit=sup["supplier_id"].isin(status)).sort_values("_hit")   # affected suppliers drawn on top
    p = logistics.plant(T)
    plant_df = pd.DataFrame([{**p, "label": f"Our plant: {p['name']}"}])
    # sizes in metres but capped in screen pixels, so dots don't grow over the map when you zoom in
    # (pydeck turns string props such as radius_units="pixels" into expressions, so units can't be set that way)
    layers = [pdk.Layer("ScatterplotLayer", sup, get_position=["lon", "lat"], get_fill_color="color",
                        get_radius=9000, radius_min_pixels=5, radius_max_pixels=9, stroked=True,
                        get_line_color=[255, 255, 255], get_line_width=0, line_width_min_pixels=1, pickable=True),
              pdk.Layer("ScatterplotLayer", plant_df, get_position=["lon", "lat"], get_fill_color=PLANT_COLOR,
                        get_radius=14000, radius_min_pixels=8, radius_max_pixels=12, stroked=True,
                        get_line_color=[255, 255, 255], get_line_width=0, line_width_min_pixels=1.5, pickable=True)]
    pts = [(p["lat"], p["lon"])]
    if len(routes):
        r = routes.copy()
        pos = sup.set_index("supplier_id")
        r["from_lat"] = r["supplier_id"].map(pos["lat"])
        r["from_lon"] = r["supplier_id"].map(pos["lon"])
        r["color"] = r["kind"].map(lambda k: APPROVED_COLOR if approved and k != "original" else ROUTE_COLORS[k])
        pts += list(zip(r["from_lat"], r["from_lon"]))
        layers.append(pdk.Layer("LineLayer", r[r["kind"] == "original"], get_source_position=["from_lon", "from_lat"],
                                get_target_position=["to_lon", "to_lat"], get_color="color", get_width=4, pickable=True))
        # the plan's routes as curves, drawn as short straight segments; express shipments bow the other way,
        # so they never hide a new-supplier route from the same place
        segs = []
        for a in r[r["kind"] != "original"].itertuples():
            pts_c = _curve(a.from_lon, a.from_lat, a.to_lon, a.to_lat, bend=0.18 if a.kind == "switch" else -0.18)
            segs += [{"from_lon": p0[0], "from_lat": p0[1], "to_lon": p1[0], "to_lat": p1[1],
                      "color": a.color, "label": a.label} for p0, p1 in zip(pts_c, pts_c[1:])]
        if segs:
            layers.append(pdk.Layer("LineLayer", pd.DataFrame(segs), get_source_position=["from_lon", "from_lat"],
                                    get_target_position=["to_lon", "to_lat"], get_color="color",
                                    get_width=5 if approved else 4, pickable=True))
    lats, lons = [a for a, _ in pts], [b for _, b in pts]
    span = max(max(lats) - min(lats), max(lons) - min(lons), 0.3 if len(routes) else 1.0)
    zoom = 8.2 if span < 0.6 else 6.5 if span < 2 else 5.5 if span < 5 else 4.6 if span < 10 else 3.8
    view = pdk.ViewState(latitude=(max(lats) + min(lats)) / 2, longitude=(max(lons) + min(lons)) / 2, zoom=zoom,
                         pitch=0, bearing=0)
    st.pydeck_chart(pdk.Deck(layers=layers, initial_view_state=view, map_provider="carto",
                             map_style="light" if LIGHT_MODE else "dark", tooltip={"text": "{label}"}))


def plan_route_summary(plan: dict) -> str:
    """One line on what the plan does with each order: which go to a new supplier, which ship express, which stay."""
    a = plan["actions"]
    if a.empty:
        return "No purchase order changes."

    def n_pos(k):
        return f"{k} PO{'' if k == 1 else 's'}"
    parts = [f"switches {n_pos(len(g))} to {sup}" for sup, g in a[a["action"] == "switch"].groupby("to_supplier")]
    parts += [f"expedites {n_pos(len(g))} with {sup}" for sup, g in a[a["action"] == "expedite"].groupby("from_supplier")]
    stay = int((a["action"] == "wait").sum())
    if stay:
        parts.append(f"keeps {n_pos(stay)} as they are")
    t = plan["totals"]
    return (f"**{plan['name']}** {', '.join(parts)} · {explain.inr(t['extra_cost'])} · "
            f"order-days avoided: {explain.delay_avoided_text(t)}")


def same_routes_note(plans: list) -> str:
    """When every plan draws the same lines, say so, and say what does differ."""
    keys = []
    for p in plans:
        a = p["actions"]
        keys.append(frozenset() if a.empty else frozenset(
            (x.action, x.to_supplier if x.action == "switch" else x.from_supplier)
            for x in a[a["action"] != "wait"].itertuples()))
    if len(plans) < 2 or len(set(keys)) > 1 or not keys[0]:
        return ""
    counts = ", ".join(f"{p['name']} {p['totals']['pos_changed']}" for p in plans)
    why = ("No other supplier can deliver sooner, so every plan ships express from the same supplier. "
           if all(act == "expedite" for act, _ in keys[0]) else "")
    return (f"All three plans use the same routes for this event. {why}"
            f"They differ in how many orders take them (POs changed: {counts}).")


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
    reports = db.supplier_reports()
    n_cleared = len(db.supplier_reports(include_cleared=True)) - len(reports)
    note = (f"{n_cleared} resolved report{'s' if n_cleared != 1 else ''} hidden; still stored in the database."
            if n_cleared else "")
    if collapsed:
        with st.expander(f"Received supplier reports ({len(reports)})", expanded=False):
            _reports_table(reports)
            if note:
                st.caption(note)
    else:
        st.subheader("Received Supplier Reports")
        _reports_table(reports)
        if note:
            st.caption(note)


def _reports_table(reports: pd.DataFrame):
    if reports.empty:
        st.info("No open supplier reports.")
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


@st.cache_data(ttl=300, show_spinner="Analysing every supplier report...")
def analyse_all_reports(rows: tuple, _tables) -> list:
    """Trace and plan each report on its own (no written explanation, so no AI call per report)."""
    out = []
    for created_at, supplier_id, issue, days, note in rows:
        ev = signals.match_suppliers(signals.event_from_report(
            {"supplier_id": supplier_id, "issue_type": issue, "days_down": days, "note": note}, _tables), _tables)
        imp = impact.trace(ev, _tables)
        plans = planner.build_plans(imp, _tables)
        rec = next((p for p in plans if p.get("recommended")), plans[0] if plans else None)
        sos = imp["sales_orders"]
        out.append({"created_at": created_at, "supplier_id": supplier_id, "issue": issue, "days": days,
                    "summary": imp["summary"], "plan": rec["name"] if rec else "", "totals": rec["totals"] if rec else {},
                    "down": imp["down"][["supplier_id", "via"]].to_dict("records") if len(imp["down"]) else [],
                    "late_orders": sos[["sales_order_id", "priority"]].to_dict("records") if len(sos) else []})
    return out


def show_reports_at_a_glance(reports: pd.DataFrame):
    st.title("Supplier reports at a glance")
    st.caption("Supply Chain Resilience")
    if reports.empty:
        st.info("No supplier reports received yet.")
        return
    rows = tuple((str(r.created_at), r.supplier_id, r.issue_type, r.days_down, r.note or "")
                 for r in reports.itertuples())
    results = analyse_all_reports(rows, T)
    names = T["suppliers"].set_index("supplier_id")["name"]

    # totals count each supplier and customer order once, even if several reports hit it
    down, late = {}, {}
    for r in results:
        for d in r["down"]:
            if down.get(d["supplier_id"]) != "hit directly":
                down[d["supplier_id"]] = d["via"]
        for o in r["late_orders"]:
            late[o["sales_order_id"]] = o["priority"]
    c = st.columns(4)
    c[0].metric("Reports received", len(results))
    c[1].metric("Suppliers down", len(down))
    c[2].metric("Customer orders at risk", len(late))
    c[3].metric("High-priority orders at risk", sum(p == "High" for p in late.values()))

    table = []
    for r in results:
        s, t = r["summary"], r["totals"]
        status = ("High-priority at risk" if s.get("high_priority_late") else
                  "Customer orders late" if s.get("sales_orders_late") else "Covered by stock")
        table.append({
            "Received": r["created_at"][:16].replace("T", " "),
            "Supplier": names.get(r["supplier_id"], r["supplier_id"]),
            "Issue": f"{r['issue']}, {r['days']} days",
            "Status": status,
            "Suppliers down": s.get("suppliers_down", 0),
            "POs at risk": s.get("pos_at_risk", 0),
            "Customer orders late": s.get("sales_orders_late", 0),
            "High-priority late": s.get("high_priority_late", 0),
            "Recommended plan: extra cost": explain.inr(t.get("extra_cost", 0)),
            "Order-days avoided": explain.delay_avoided_text({"delay_avoided_days": 0, "late_days_before": 0, **t}),
            "High-priority kept on time": explain.high_priority_text({"high_priority_protected": 0, "high_priority_affected": 0, **t}),
        })
    st.dataframe(pd.DataFrame(table), hide_index=True, width="stretch")
    st.caption("Each report is analysed on its own, newest first. To see a report's three plans and approve one, "
               "switch the view on the left to **One report** and pick it.")
    network_map(pd.DataFrame([{"supplier_id": k, "via": v} for k, v in down.items()]))


# ------------------------------------------------------------------ main
if glance:
    with map_col:
        show_reports_at_a_glance(reports)
    with intel_card:
        show_map_legend()
    page_footer(STATUS)
    st.stop()

res = st.session_state.get("result")
if not res:
    with header_area:
        st.title("ReRoute ")
        st.caption("Supply Chain Resilience")
        st.caption("Select a signal on the left to assess its effect on the supplier network.")
    with left_card:
        st.divider()
        st.markdown('<div class="rr-section-kicker">ACTIVE EVENT</div>', unsafe_allow_html=True)
        st.markdown("#### Disruption intelligence")
        st.info("No analysis is selected. Choose a demo signal, paste an alert, or select a supplier report above.")
    with map_col:
        network_map()
    with intel_card:
        st.markdown('<div class="rr-section-kicker">LIVE INTELLIGENCE</div>', unsafe_allow_html=True)
        st.markdown("#### Network command")
        st.caption("Supplier and plant locations across the current network.")
        show_map_legend()
    show_workflow_progress()
    show_received_supplier_reports()
    page_footer(STATUS)
    st.stop()

ev, imp, plans, s = res["event"], res["impact"], res["plans"], res["impact"]["summary"]
title = f"{ev.event_type.title()}" + (f" · {ev.location}" if ev.location else "") + (f" · {ev.state}" if ev.scope == "state" else "")
tm = res["timings_ms"]
plan_ms = tm["total"] - tm["explain"]   # detection (if any) + tracing + planning; the explanation is separate
starts = (f" from {pd.Timestamp(s['starts_on']):%d %b}" if getattr(ev, "starts_in_days", 0) else "")
with header_area:
    st.markdown("OPERATIONS")
    st.title(title if ev.relevant else "No disruption detected")
    st.caption("Kaveri EV Motors · Supply Chain Resilience")
    st.caption(f"{ev.text}  \nDetected by: {ev.method} · expected {ev.duration_days} days{starts} · severity {ev.severity}/5 · "
               f"{plan_ms:.0f} ms to a ranked plan · {tm['total']:.0f} ms total · explanation by "
               f"{'Generative AI Hub' if res.get('explain_method') == 'llm' else 'template'} "
               f"in {tm['explain'] / 1000:.1f} s")
workflow_progress_slot = st.empty()
show_workflow_progress(res, workflow_progress_slot)
show_received_supplier_reports(collapsed=True)

if ev.relevant and s.get("on_watch"):
    st.info(explain.watch_text(imp))
    with left_card:
        st.divider()
        st.markdown('<div class="rr-section-kicker">ACTIVE EVENT</div>', unsafe_allow_html=True)
        st.markdown("#### Disruption profile")
        st.markdown(f"**IMD yellow alert · {ev.event_type.title()}**  \n{ev.location or ev.state or 'Network-wide'}")
        st.caption(f"Severity {ev.severity}/5 · {ev.duration_days} days{starts}")
        st.markdown("#### Signal")
        st.write(ev.text)
    with map_col:
        network_map(pd.DataFrame([{"supplier_id": m["supplier_id"], "via": "on watch"} for m in ev.matched]))
    with intel_card:
        st.markdown('<div class="rr-section-kicker">LIVE INTELLIGENCE</div>', unsafe_allow_html=True)
        st.markdown("#### Network command")
        st.caption("Amber: suppliers on watch. Nothing is replanned for a yellow alert.")
        show_map_legend()
    page_footer(STATUS)
    st.stop()

if not ev.relevant or not ev.matched:
    st.info("This signal doesn't touch any supplier in our network, so there is nothing to replan.")
    with left_card:
        st.divider()
        st.markdown('<div class="rr-section-kicker">ACTIVE EVENT</div>', unsafe_allow_html=True)
        st.markdown("#### Disruption profile")
        kind = ev.event_type.title() if ev.relevant and ev.event_type not in ("", "none") else "Not a disruption"
        st.markdown(f"**{kind}**  \n{ev.location or ev.state or 'Network-wide'}")
        st.caption(f"Severity {ev.severity}/5 · expected duration {ev.duration_days} days")
        st.markdown("#### Signal")
        st.write(ev.text)
        st.caption(f"Detected by {ev.method} · {plan_ms:.0f} ms to classify")
    with map_col:
        network_map()
    with intel_card:
        st.markdown('<div class="rr-section-kicker">LIVE INTELLIGENCE</div>', unsafe_allow_html=True)
        st.markdown("#### Network command")
        st.caption("No suppliers in the current network match this signal.")
        show_map_legend()
    page_footer(STATUS)
    st.stop()

with left_card:
    st.divider()
    st.markdown('<div class="rr-section-kicker">ACTIVE EVENT</div>', unsafe_allow_html=True)
    st.markdown("#### Disruption profile")
    st.markdown(f"**{ev.event_type.title()}**  \n{ev.location or ev.state or 'Network-wide'}")
    st.caption(f"Severity {ev.severity}/5 · expected duration {ev.duration_days} days{starts}")
    st.markdown("#### Signal")
    st.write(ev.text)
    st.caption(f"Detected by {ev.method} · {plan_ms:.0f} ms to a ranked plan")
with map_col:
    with st.container(border=True):
        st.markdown("#### Supply network")
        route_area = st.container()     # filled at the end of the page, so an approval on this run shows at once
with intel_card:
    st.markdown("##### NETWORK COMMAND  /  LIVE EXPOSURE")
    show_operational_strip(s)
    st.markdown('<div class="rr-section-kicker">LIVE INTELLIGENCE</div>', unsafe_allow_html=True)
    st.markdown("#### Network command")
    st.caption("Supplier impact and the routes of the plan picked above the map.")
    legend_area = st.container()

tab_impact, tab_risk, tab_plan, tab_ask, tab_done = st.tabs(
    ["Impact", "Customer Order Risk Analysis", "Recovery plans", "Ask ReRoute", "Approved actions"])

with tab_plan:
    if s["pos_at_risk"] == 0:
        st.success("Safety stock and lead times cover this event. No purchase order needs to change.")
    else:
        st.info(res["explanation"] + f"\n\n_Written by: {'Generative AI Hub' if res['explain_method'] == 'llm' else 'offline template'}_")

        note = explain.same_plans_note(plans)
        if note:
            st.caption(note)
        for p in plans:
            t = p["totals"]

            with st.container(border=p.get("recommended", False)):
                if p.get("recommended"):
                    st.success("⭐ RECOMMENDED PLAN")

                st.subheader(p["name"])

                c1, c2, c3, c4 = st.columns(4)

                c1.metric("Extra cost", explain.inr(t["extra_cost"]))
                c2.metric("Order-days of delay avoided", explain.delay_avoided_text(t))
                c3.metric("High-priority orders on time", explain.high_priority_text(t))
                c4.metric("Purchase orders changed", t["pos_changed"])

                b = logistics.cost_breakdown(T, imp, p)
                st.caption(f"Includes **{explain.inr(b['extra_freight'])}** extra freight for farther suppliers "
                           f"(estimate: Rs {config.FREIGHT_RS_PER_KM:.0f} per road km, one truck per PO)")
                with st.expander("Cost breakdown", expanded=p["name"] == st.session_state.get("approved_plan_name")):
                    st.dataframe(logistics.breakdown_table(b, explain.inr), hide_index=True, width="stretch")

                if not t["pos_changed"]:
                    st.caption("Nothing to approve: this plan keeps every purchase order as it is.")
                elif st.button(
                    f"Approve {p['name']}",
                    key=f"approve-{p['name']}",
                    type="primary" if p.get("recommended") else "secondary"
                ):
                    n = agent.approve(res, p["name"])
                    st.session_state.approved_plan_name = p["name"]
                    st.session_state.approved_plan_result_ref = res
                    show_workflow_progress(res, workflow_progress_slot)
                    changes = f"{n} PO change{'' if n == 1 else 's'} queued and supplier messages drafted. "
                    if t.get("cost_if_wait", 0) > 0:   # tariff: the extra cost includes duty paid either way
                        money = (f"Saves {explain.inr(t['cost_avoided'])} of the {explain.inr(t['cost_if_wait'])} "
                                 f"extra duty, after {explain.inr(b['extra_freight'])} extra freight. ")
                    else:
                        money = (f"Total extra cost {explain.inr(b['total'])}, including "
                                 f"{explain.inr(b['extra_freight'])} extra freight. ")
                    st.success("Approved. " + changes + money +
                               "The map above now shows the new routes; Approved actions has the breakdown.")

        for p in plans:
            acts = p["actions"]
            with st.expander(f"{p['name']}: what changes"):
                if acts.empty or (acts["action"] == "wait").all():
                    st.write("No purchase order changes; customer orders absorb the delay.")
                else:
                    st.dataframe(acts[acts["action"] != "wait"][["po_id", "so_priority", "material", "qty", "from_supplier",
                                                                  "action", "to_supplier", "delay_before", "delay_after",
                                                                  "extra_cost"]], hide_index=True, width="stretch")
                limits = acts[acts["capacity_note"] != ""] if "capacity_note" in acts else acts.iloc[0:0]
                if len(limits):
                    st.markdown("**Capacity limits** (spare capacity is shared, so plans never promise the same parts twice)")
                    for r in limits.itertuples():
                        st.caption(f"PO {r.po_id}: {r.capacity_note}")

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
    approved_name = st.session_state.get("approved_plan_name")
    approved_plan = next((p for p in plans if p["name"] == approved_name), None)
    if approved_plan is not None:
        st.subheader(f"Approved plan: {approved_name}")
        st.dataframe(logistics.breakdown_table(logistics.cost_breakdown(T, imp, approved_plan), explain.inr),
                     hide_index=True, width="stretch")
        lines = logistics.plan_lines(T, imp, approved_plan)
        changed = lines[lines["action"] != "wait"] if len(lines) else lines
        if len(changed):
            st.caption("Per purchase order (freight is an estimate: one truck per PO, road km = straight-line x "
                       f"{config.ROAD_FACTOR}, Rs {config.FREIGHT_RS_PER_KM:.0f} per extra km)")
            money = ["price_difference", "new_supplier_checks", "extra_freight", "expedite_fee", "planner_extra_cost"]
            view = changed.assign(**{c: changed[c].map(explain.inr) for c in money})
            st.dataframe(view[["po_id", "action", "from_supplier", "to_supplier", "qty", "km_before", "km_after",
                               *money]].rename(columns={
                "po_id": "PO", "action": "Action", "from_supplier": "From", "to_supplier": "To", "qty": "Qty",
                "km_before": "Road km before", "km_after": "Road km after", "price_difference": "Price difference",
                "new_supplier_checks": "New-supplier checks", "extra_freight": "Extra freight",
                "expedite_fee": "Expedite fee", "planner_extra_cost": "Extra cost"}),
                hide_index=True, width="stretch")
        st.divider()
        st.subheader("All approved changes")
    done = db.read_rows("plan_actions")
    if done.empty:
        st.write("Nothing approved yet.")
    else:
        st.dataframe(done.iloc[::-1], hide_index=True, width="stretch")
    sandbox = config.DATA_DIR / "s4_sandbox_pos.csv"
    if sandbox.exists():
        st.subheader("Purchase orders pulled from the SAP S/4HANA sandbox")
        st.dataframe(pd.read_csv(sandbox), hide_index=True, width="stretch")

# ------------------------------------------------------------------ route map in the panel at the top
# Drawn last, after the tabs, so a plan approved on this run is already shown as approved.
names = [p["name"] for p in plans]
approved_name = st.session_state.get("approved_plan_name")
with route_area:
    if s["pos_at_risk"] == 0 or not names:
        r, is_approved = pd.DataFrame(), False
        route_map(imp["down"], r, is_approved)
        st.caption("No purchase order is late, so no route changes.")
    else:
        default = approved_name if approved_name in names else next(
            (p["name"] for p in plans if p.get("recommended")), names[0])
        pick = st.radio("Show the routes for", names, index=names.index(default), horizontal=True,
                        format_func=lambda n: f"{n} (approved)" if n == approved_name else n)
        chosen_plan = next(p for p in plans if p["name"] == pick)
        is_approved = pick == approved_name
        st.markdown(plan_route_summary(chosen_plan))
        r = logistics.routes(T, imp, chosen_plan)
        route_map(imp["down"], r, is_approved)
        note = same_routes_note(plans)
        if note:
            st.info(note)
        st.caption("Routes are drawn directly between supplier and plant, not along actual roads. "
                   "Hover over a dot or route for details.")
        if len(r):
            with st.expander("Route details"):
                st.dataframe(r.assign(
                    Route=r["label"],
                    Type=r["kind"].map({"original": "Original (disrupted)", "switch": "New supplier",
                                        "expedite": "Express shipment, same supplier"}),
                    **{"Road km (est.)": r["km"]})[["Type", "Route", "Road km (est.)"]],
                    hide_index=True, width="stretch")
with legend_area:
    map_legend(r, is_approved)

page_footer(STATUS)
