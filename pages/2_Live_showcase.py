"""Full system showcase: a live disruption runs through the ReRoute agent network.

Agents detect, trace, plan, act within limits, escalate the rest to a human, and log every
message to a hash-chained audit trail in SAP HANA Cloud.
"""
import json
import time

import pandas as pd
import streamlit as st

from reroute import config, db, explain, llm, network

st.set_page_config(page_title="Live showcase · ReRoute", layout="wide")
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
    [data-testid="stMainBlockContainer"], .main .block-container {{ padding: 3.75rem .7rem 1.5rem; }}
    [data-testid="stMetric"] {{ min-height: 78px; padding: .55rem; }}
}}
@media (prefers-reduced-motion: reduce) {{
    *, *::before, *::after {{ animation-duration: .01ms !important; transition-duration: .01ms !important; }}
}}
</style>""",
    unsafe_allow_html=True,
)

STEPS = {
    "port": ("Day 1 · Port notice", "port_notice",
             "Chennai Port Authority: cyclone warning, all container terminal operations suspended for 8 days. "
             "Vessels diverted to Krishnapatnam."),
    "tariff": ("Day 2 · Tariff bulletin", "tariff_bulletin",
               "Finance ministry raises basic customs duty on imported lithium-ion cells from 10% to 35%, "
               "effective immediately."),
    "strike": ("Day 3 · News", "news",
               "Transporters announce statewide strike across Tamil Nadu from Monday for 3 days over toll hike."),
    "noise": ("Day 3 · News", "news", "India beat Australia by 6 wickets in Bengaluru T20 thriller."),
}
SCENARIOS = {
    "Chained crisis: port closure, tariff spike, strike": ["port", "tariff", "strike", "noise"],
    "Chennai port closure": ["port"],
    "Li-ion cell tariff spike": ["tariff"],
    "Tamil Nadu transport strike": ["strike"],
}
EDGES = [("signals", "sentinel"), ("sentinel", "impact"), ("impact", "sourcing"), ("sourcing", "policy"),
         ("policy", "execution"), ("policy", "planner"), ("planner", "execution"), ("execution", "audit")]


@st.cache_data(ttl=300)
def tables():
    return db.load_tables()


def graph_dot(active=None) -> str:
    sender, recipient = active if active else (None, None)
    node_fill = "#F4FCFC" if LIGHT_MODE else "#0D303B"
    node_text = palette["text"]
    node_border = palette["accent"]
    edge_color = palette["muted"]
    lines = ['digraph G {', 'rankdir=TB; bgcolor="transparent"; nodesep=0.5; ranksep=0.32;',
             f'node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=16, margin="0.12,0.06", color="{node_border}", fillcolor="{node_fill}", fontcolor="{node_text}"];',
             f'edge [color="{edge_color}", arrowsize=0.8];']
    for key, (name, role) in network.AGENTS.items():
        fill = ("#F4B942" if LIGHT_MODE else "#9E7020") if key == recipient else (
            "#20C6B7" if LIGHT_MODE else "#087D86") if key == sender else (
            ("#D9F2E7" if LIGHT_MODE else "#145241") if key == "planner" else node_fill)
        pen = 2.5 if key in (sender, recipient) else 1
        lines.append(f'{key} [label=<<b>{name}</b><br/><font point-size="12">{role}</font>>, '
                     f'fillcolor="{fill}", color="{node_border}", fontcolor="{node_text}", penwidth={pen}];')
    for a, b in EDGES:
        hot = (a, b) == (sender, recipient)
        lines.append(f'{a} -> {b} [color="{"#FF5C70" if hot and not LIGHT_MODE else "#C13F55" if hot else edge_color}", penwidth={3 if hot else 1}];')
    if active and (sender, recipient) not in EDGES:
        lines.append(f'{sender} -> {recipient} [color="{("#C13F55" if LIGHT_MODE else "#FF5C70")}", penwidth=3, style=dashed];')
    lines.append('{rank=same; policy; planner;}')
    lines.append("}")
    return "\n".join(lines)


def show_graph(slot, active=None):
    try:
        slot.graphviz_chart(graph_dot(active), width="stretch")
    except TypeError:  # older Streamlit
        slot.graphviz_chart(graph_dot(active), use_container_width=True)


def feed_frame(msgs) -> pd.DataFrame:
    # number messages from 1 within this run; the global audit-log number (m.seq) stays in the audit view below
    return pd.DataFrame([{"#": i,
                          "route": f"{network.AGENTS[m.sender][0]} → {network.AGENTS[m.recipient][0]}",
                          "summary": m.summary} for i, m in reversed(list(enumerate(msgs, start=1)))])


FEED_COLUMNS = {"#": st.column_config.NumberColumn(width="small"),
                "route": st.column_config.TextColumn(width="medium"),
                "summary": st.column_config.TextColumn(width="large")}


def show_feed(slot, msgs):
    slot.dataframe(feed_frame(msgs), hide_index=True, height=560, width="stretch", column_config=FEED_COLUMNS)


def show_kpis(net, slots):
    s = net.stats
    slots[0].metric("Agent messages", s["messages"])
    slots[1].metric("Done by agents alone", s["auto"])
    slots[2].metric("Waiting for you", len(net.pending))
    slots[3].metric("Approved / rejected", f"{s['approved']} / {s['rejected']}")
    slots[4].metric("Extra cost committed", explain.inr(s["extra_cost"]))


T = tables()

# ------------------------------------------------------------------ simulation state and controls
SIM_STATE_DEFAULTS = {
    "sim_status": "Ready",
    "sim_started_at": None,
    "sim_elapsed": 0.0,
    "sim_processing": 0.0,            # seconds the agents themselves spent, without the display delay
    "sim_scenario_keys": [],
    "sim_scenario_index": 0,
    "sim_message_iter": None,
    "sim_current_label": "",
}
for state_key, default_value in SIM_STATE_DEFAULTS.items():
    st.session_state.setdefault(state_key, default_value)


def show_simulation_metrics(net, slots):
    status = st.session_state.sim_status
    started_at = st.session_state.sim_started_at
    elapsed = (time.perf_counter() - started_at
               if status == "Running" and started_at is not None
               else st.session_state.sim_elapsed)
    all_plans = ([plan for event in net.events.values() for plan in event.get("plans", [])]
                 if net else [])
    alternatives = sum(not plan.get("recommended", False) for plan in all_plans)
    # wall-clock time includes the "seconds per agent message" pause; show the agents' own time separately
    slots[0].metric("Run time (incl. display delay)", f"{elapsed:.1f} s")
    slots[1].metric("Agent processing time", f"{st.session_state.sim_processing * 1000:.0f} ms")
    slots[2].metric("Alternative plans generated", alternatives)
    slots[3].metric("Simulation status", status)


# ------------------------------------------------------------------ sidebar and page controls
status_when_drawn = st.session_state.sim_status
scenario = st.sidebar.selectbox("Disruption", list(SCENARIOS))
speed = st.sidebar.slider("Seconds per agent message", 0.0, 2.0, 0.7, 0.1)
st.sidebar.divider()
st.sidebar.caption("Autonomy limits (Policy agent)")
st.sidebar.write(f"- High-priority customer orders always go to a human\n"
                 f"- Extra cost above {explain.inr(config.AUTO_COST_LIMIT_INR)} goes to a human\n"
                 f"- Moving more than {explain.inr(config.BIG_SWITCH_LIMIT_INR)} of business goes to a human")
st.sidebar.divider()
st.sidebar.caption(f"Database: {'SAP HANA Cloud' if db.backend() == 'hana' else 'SQLite (local)'}")
st.sidebar.caption(f"Language model: {llm.status()}")

heading_col, start_col, stop_col, reset_col = st.columns([5, 1.8, 1.2, 1], gap="small")
with heading_col:
    st.markdown("OPERATIONS CENTER  /  AGENT NETWORK")
    st.title("Live Operations Showcase")
    st.caption("Observe the existing agent workflow from disruption signal to Human Planner decision.")
start = start_col.button("Start Simulation", type="primary",
                         disabled=st.session_state.sim_status == "Running", width="stretch")
stop = stop_col.button("Stop", disabled=st.session_state.sim_status != "Running", width="stretch")
if st.session_state.sim_status == "Stopped":
    heading_col.caption("The stopped run is preserved. Starting again creates a new run.")
if reset_col.button("Reset", width="stretch"):
    for state_key in ["net", "feed", "last", *SIM_STATE_DEFAULTS]:
        st.session_state.pop(state_key, None)
    st.rerun()

if start:
    net = network.Network(T)
    st.session_state.net = net
    st.session_state.feed = []
    st.session_state.last = None
    st.session_state.sim_scenario_keys = list(SCENARIOS[scenario])
    st.session_state.sim_scenario_index = 0
    st.session_state.sim_message_iter = None
    st.session_state.sim_current_label = ""
    st.session_state.sim_started_at = time.perf_counter()
    st.session_state.sim_elapsed = 0.0
    st.session_state.sim_processing = 0.0
    st.session_state.sim_status = "Running"

if stop and st.session_state.sim_status == "Running":
    started_at = st.session_state.sim_started_at
    st.session_state.sim_elapsed = (time.perf_counter() - started_at) if started_at is not None else 0.0
    st.session_state.sim_status = "Stopped"
    st.session_state.sim_message_iter = None
    st.session_state.last = None
    stopped_net = st.session_state.get("net")
    if stopped_net:
        # drop undelivered messages, so a later approval doesn't quietly finish the stopped disruption
        stopped_net.queue.clear()

# ------------------------------------------------------------------ layout
banner = st.empty()
with st.container(border=True):
    st.markdown('<div class="rr-section-kicker">RUN PERFORMANCE</div>', unsafe_allow_html=True)
    performance_slots = [c.empty() for c in st.columns(4, gap="small", border=True)]
    st.divider()
    st.markdown('<div class="rr-section-kicker">AGENT METRICS</div>', unsafe_allow_html=True)
    kpi_slots = [c.empty() for c in st.columns(5, gap="small", border=True)]

left, right = st.columns([4, 8], gap="small")   # the message feed keeps two thirds of the width
with left:
    with st.container(border=True):
        st.markdown('<div class="rr-section-kicker">AUTOMATED WORKFLOW</div>', unsafe_allow_html=True)
        st.subheader("Agent topology")
        graph_slot = st.empty()
    with st.container(border=True):
        st.markdown('<div class="rr-section-kicker">HUMAN CHECKPOINT</div>', unsafe_allow_html=True)
        st.subheader("Human oversight")
        oversight_slot = st.empty()
with right:
    with st.container(border=True):
        st.markdown('<div class="rr-section-kicker">AGENT COMMUNICATION</div>', unsafe_allow_html=True)
        st.subheader("Live activity")
        feed_slot = st.empty()

# ------------------------------------------------------------------ advance one safe agent-message boundary per rerun
net = st.session_state.get("net")
processed_message = False
if net and st.session_state.sim_status == "Running":
    while st.session_state.sim_status == "Running":
        scenario_index = st.session_state.sim_scenario_index
        scenario_keys = st.session_state.sim_scenario_keys
        if scenario_index >= len(scenario_keys):
            started_at = st.session_state.sim_started_at
            st.session_state.sim_elapsed = (time.perf_counter() - started_at
                                             if started_at is not None else 0.0)
            st.session_state.sim_status = "Awaiting Approval"
            st.session_state.sim_message_iter = None
            st.session_state.last = None
            break

        message_iter = st.session_state.sim_message_iter
        if message_iter is None:
            step_key = scenario_keys[scenario_index]
            label, source, signal_text = STEPS[step_key]
            st.session_state.sim_current_label = label
            banner.info(f"**{label}:** {signal_text}")
            net.inject(signal_text, source, label)
            message_iter = iter(net.run())
            st.session_state.sim_message_iter = message_iter

        try:
            t0 = time.perf_counter()
            message = next(message_iter)
            st.session_state.sim_processing += time.perf_counter() - t0
        except StopIteration:
            st.session_state.sim_message_iter = None
            st.session_state.sim_scenario_index = scenario_index + 1
            continue

        st.session_state.feed.append(message)
        st.session_state.last = (message.sender, message.recipient)
        processed_message = True
        break

show_simulation_metrics(net, performance_slots)


if not net:
    banner.info("Pick a disruption in the sidebar and press **Start Simulation**.")
    show_graph(graph_slot)
    st.stop()

show_graph(graph_slot, st.session_state.get("last"))
show_feed(feed_slot, st.session_state.feed)
show_kpis(net, kpi_slots)

with oversight_slot.container():
    status = st.session_state.sim_status
    st.caption(f"Simulation status · {status}")
    st.metric("Actions awaiting decision", len(net.pending))
    # one recommended plan per disruption: a chained run has several, so list each one
    recommended = []
    for state in net.events.values():
        plan = next((p for p in state.get("plans", []) if p.get("recommended")), None)
        if plan:
            ev = state["event"]
            where = ev.location or getattr(ev, "state", "") or ""
            recommended.append((f"{ev.event_type.title()}" + (f" · {where}" if where else ""), plan))
    if recommended:
        st.markdown("**Recommended recovery plans**" if len(recommended) > 1 else "**Recommended recovery plan**")
        for label, plan in recommended:
            t = plan.get("totals", {})
            if t.get("cost_if_wait", 0) > 0:   # tariff: the duty is paid either way, so show what the plan saves
                cost = f"saves {explain.inr(t.get('cost_avoided', 0))} of {explain.inr(t['cost_if_wait'])} extra duty"
            else:
                cost = f"extra cost {explain.inr(t.get('extra_cost', 0))}"
            st.caption(f"{label}: {plan['name']} · {cost}")
    elif any(state.get("plans") for state in net.events.values()):
        st.caption("No recommended plan is identified in the current results.")
    else:
        st.caption("Recovery plans are not available yet.")
    st.caption("Use the Approval queue below to review and decide on pending actions.")


status = st.session_state.sim_status
if status == "Running":
    banner.info(f"Running: {st.session_state.sim_current_label}")
elif status == "Stopped":
    banner.warning(f"Run {net.run_id} stopped. Generated messages, plans and audit entries are preserved.")
elif status == "Awaiting Approval":
    banner.success(f"Run {net.run_id}: workflow complete; awaiting Human Planner approval. "
                   + (f"{len(net.pending)} actions are waiting for your decision below."
                      if net.pending else "No actions are waiting for approval."))
else:
    banner.info("Simulation is ready to start.")

if status == "Running":
    if speed and processed_message:
        time.sleep(speed)
    st.rerun()
elif status != status_when_drawn:
    # the run finished or was stopped after the sidebar was drawn: redraw once so Start/Stop are enabled correctly
    st.rerun()

def settle():
    """After a human decision, let Execution and Audit finish, then refresh."""
    for m in net.run():
        st.session_state.feed.append(m)
    st.rerun()


tab_q, tab_plans, tab_done, tab_audit, tab_sap = st.tabs(
    [f"Approval queue ({len(net.pending)})", "Plans and explanations", "Actions taken", "Audit log", "SAP integration"])

with tab_q:
    if not net.pending:
        st.write("Nothing is waiting for approval.")
    else:
        c1, c2 = st.columns([1, 4])
        if c1.button("Approve all", type="primary"):
            for aid in list(net.pending):
                net.decide(aid, True, "Approved in bulk")
            settle()
        c2.caption("Or decide one by one. Every decision and its reason goes into the audit log.")
        for aid, a in list(net.pending.items()):
            with st.container(border=True):
                what = (f"Switch PO {a['po_id']} to **{a['to_supplier']}**" if a["action"] == "switch"
                        else f"Expedite PO {a['po_id']} with **{a['from_supplier']}**")
                st.markdown(f"{what} · {a['qty']} × {a['material']} · customer order {a['sales_order_id']} "
                            f"({a['so_priority']} priority)")
                # versus doing nothing: after a tariff, doing nothing means paying the higher duty
                versus = ("" if abs(a["net_cost"] - a["extra_cost"]) < 1 else
                          f", saves {explain.inr(-a['net_cost'])} versus paying the higher duty" if a["net_cost"] < 0
                          else f", {explain.inr(a['net_cost'])} more than paying the higher duty")
                st.caption(f"Why it needs you: {a['rule']}. Extra cost {explain.inr(a['extra_cost'])}{versus}. "
                           f"Delay {a['delay_before']} → {a['delay_after']} days.")
                r1, r2, r3 = st.columns([4, 1, 1])
                reason = r1.text_input("Reason (optional)", key=f"reason-{aid}", label_visibility="collapsed",
                                       placeholder="Reason (optional)")
                if r2.button("Approve", key=f"ok-{aid}"):
                    net.decide(aid, True, reason)
                    settle()
                if r3.button("Reject", key=f"no-{aid}"):
                    net.decide(aid, False, reason)
                    settle()

with tab_plans:
    if not net.events:
        st.write("No disruption touched the network.")
    for eid, stt in net.events.items():
        ev = stt["event"]
        with st.expander(f"{eid} · {ev.event_type} · {ev.text[:90]}", expanded=len(net.events) == 1):
            if "explanation" in stt:
                st.info(stt["explanation"])
                st.dataframe(pd.DataFrame([{"plan": p["name"] + (" (recommended)" if p.get("recommended") else ""),
                                            "POs changed": p["totals"]["pos_changed"],
                                            "extra cost": explain.inr(p["totals"]["extra_cost"]),
                                            "cost avoided": explain.cost_avoided_text(p["totals"]),
                                            "order-days avoided": explain.delay_avoided_text(p["totals"]),
                                            "high-priority on time": explain.high_priority_text(p["totals"])}
                                           for p in stt["plans"]]), hide_index=True, width="stretch")
                note = explain.same_plans_note(stt["plans"])
                if note:
                    st.caption(note)
            if "impact" in stt:
                st.dataframe(stt["impact"]["down"], hide_index=True, width="stretch")

with tab_done:
    done = db.read_rows("plan_actions")
    done = done[done["event_id"].isin(list(net.events))] if len(done) else done
    if done.empty:
        st.write("No actions yet.")
    else:
        st.dataframe(done[["created_at", "status", "decided_by", "action_type", "po_id", "details", "policy_rule",
                           "extra_cost", "supplier_message"]].iloc[::-1], hide_index=True, width="stretch")

with tab_audit:
    rows = db.read_rows("agent_audit_log")
    c1, c2 = st.columns([1, 3])
    if c1.button("Verify audit trail"):
        v = network.verify_audit(rows)
        if v["ok"]:
            c2.success(f"Chain intact: all {v['records']} records match their hashes.")
        else:
            c2.error(f"Chain broken at record {v['broken_at']}: a stored record was changed or removed.")
    run_rows = rows[rows["run_id"] == net.run_id].sort_values("seq", ascending=False) if len(rows) else rows
    st.dataframe(run_rows[["seq", "ts", "sender", "recipient", "kind", "summary", "hash"]] if len(run_rows) else run_rows,
                 hide_index=True, width="stretch", height=360)
    if len(run_rows):
        st.download_button("Download this run's audit log (CSV)", run_rows.to_csv(index=False),
                           file_name=f"reroute_audit_{net.run_id}.csv", mime="text/csv")

with tab_sap:
    sandbox = config.DATA_DIR / "s4_sandbox_pos.csv"
    st.dataframe(pd.DataFrame([
        {"SAP service": "SAP HANA Cloud (Hackfest-DB)", "used for": "Supplier network, orders, approvals, audit log",
         "status": "live" if db.backend() == "hana" else "SQLite stand-in (set REROUTE_DB=hana)"},
        {"SAP service": "Generative AI Hub (SAP AI Core)", "used for": "Sentinel classification, Sourcing explanations",
         "status": "live" if llm.available() else "offline templates (waiting for credentials)"},
        {"SAP service": "S/4HANA Cloud Purchase Order API", "used for": "Reading POs; Execution prepares write-back requests",
         "status": "sandbox data pulled" if sandbox.exists() else "not pulled yet (python -m reroute.s4_sandbox)"},
        {"SAP service": "SAP Business Application Studio", "used for": "Development and hosting option on SAP BTP",
         "status": "available on the practice system"},
        {"SAP service": "SAP IBP / Joule Studio", "used for": "Production home of the Sourcing agent / agent runtime",
         "status": "represented by our planner and agent classes"},
    ]), hide_index=True, width="stretch")
    done = db.read_rows("plan_actions")
    done = done[done["event_id"].isin(list(net.events)) & (done["s4_request"] != "{}")] if len(done) else done
    if len(done):
        st.caption("Latest S/4HANA request prepared by the Execution agent (the sandbox is read-only, so it is not sent):")
        st.code(json.dumps(json.loads(done.iloc[-1]["s4_request"]), indent=2), language="json")
