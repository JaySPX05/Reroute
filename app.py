"""ReRoute planner dashboard.  Run:  streamlit run app.py"""
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from reroute import agent, config, db, explain, llm

st.set_page_config(page_title="ReRoute", layout="wide")

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
st.sidebar.title("ReRoute")
st.sidebar.caption("AI replanning for supply disruptions")
mode = st.sidebar.radio("Signal", ["Demo scenario", "Paste news or IMD alert", "Latest supplier report"])
run = False
if mode == "Demo scenario":
    pick = st.sidebar.selectbox("Scenario", list(DEMO))
    st.sidebar.write(f"_{TEXT[DEMO[pick]]['text']}_")
    if st.sidebar.button("Analyse", type="primary"):
        s = TEXT[DEMO[pick]]
        st.session_state.result = agent.analyze_text(s["text"], T, source=s["source"])
        run = True
elif mode == "Paste news or IMD alert":
    text = st.sidebar.text_area("Text", height=140, placeholder="Paste a news line or weather alert")
    if st.sidebar.button("Analyse", type="primary", disabled=not text.strip()):
        st.session_state.result = agent.analyze_text(text, T)
        run = True
else:
    reports = db.read_rows("supplier_reports")
    if reports.empty:
        st.sidebar.info("No supplier reports yet. Open the Supplier report page to send one.")
    else:
        last = reports.iloc[-1].to_dict()
        name = T["suppliers"].set_index("supplier_id").loc[last["supplier_id"], "name"]
        st.sidebar.write(f"**{name}**: {last['issue_type']}, {last['days_down']} days. {last['note']}")
        if st.sidebar.button("Analyse", type="primary"):
            st.session_state.result = agent.analyze_report(
                {k: last[k] for k in ["supplier_id", "issue_type", "days_down", "note"]}, T, save=False)
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
    red, amber, grey, blue = "#d62828", "#f4a100", "#8a94a6", "#1f6feb"
    sup["color"] = sup["supplier_id"].map(lambda s: grey if s not in days else red if days[s] == "hit directly" else amber)
    sup["size"] = sup["supplier_id"].map(lambda s: 9000 if s in days else 5000)
    city = T["cities"].set_index("city")
    plant = pd.DataFrame([{"lat": city.loc["Bidadi", "lat"], "lon": city.loc["Bidadi", "lon"], "color": blue, "size": 12000}])
    # spread suppliers in the same city a little so every dot is visible
    sup["n"] = sup.groupby("city").cumcount()
    sup["lat"] = sup["lat"] + sup["n"] * 0.04
    pts = pd.concat([sup[["lat", "lon", "color", "size"]], plant])
    st.map(pts, latitude="lat", longitude="lon", color="color", size="size")
    st.caption("Blue: our plant (Bidadi). Red: hit directly. Amber: down through a supplier it depends on. Grey: unaffected.")


# ------------------------------------------------------------------ main
res = st.session_state.get("result")
if not res:
    st.title("ReRoute")
    st.write("Pick a scenario or paste a news item in the sidebar, then press **Analyse**. "
             "Suppliers report problems on the **Supplier report** page.")
    network_map()
    st.stop()

ev, imp, plans, s = res["event"], res["impact"], res["plans"], res["impact"]["summary"]
title = f"{ev.event_type.title()}" + (f" · {ev.location}" if ev.location else "") + (f" · {ev.state}" if ev.scope == "state" else "")
st.title(title if ev.relevant else "No disruption detected")
st.caption(f"{ev.text}  \nDetected by: {ev.method} · expected {ev.duration_days} days · severity {ev.severity}/5 · "
           f"{res['timings_ms']['total']:.0f} ms from signal to plan")

if not ev.relevant or not ev.matched:
    st.info("This signal doesn't touch any supplier in our network, so there is nothing to replan.")
    network_map()
    st.stop()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Suppliers down", s["suppliers_down"], f"{s['tier2_plus_down']} Tier-2 or deeper", delta_color="off")
c2.metric("Purchase orders at risk", s["pos_at_risk"], explain.inr(s["po_value_at_risk"]), delta_color="off")
c3.metric("Customer orders late", s["sales_orders_late"], f"{s['high_priority_late']} high-priority", delta_color="off")
c4.metric("Order-days late if we wait", s["baseline_late_days"])

tab_plan, tab_impact, tab_map, tab_ask, tab_done = st.tabs(
    ["Recovery plans", "Impact", "Map", "Ask ReRoute", "Approved actions"])

with tab_plan:
    if s["pos_at_risk"] == 0:
        st.success("Safety stock and lead times cover this event. No purchase order needs to change.")
    else:
        st.info(res["explanation"] + f"\n\n_Written by: {'Generative AI Hub' if res['explain_method'] == 'llm' else 'offline template'}_")
        cols = st.columns(len(plans))
        for col, p in zip(cols, plans):
            t = p["totals"]
            with col:
                st.subheader(p["name"] + (" ✓" if p.get("recommended") else ""))
                if p.get("recommended"):
                    st.caption("Recommended")
                st.metric("Extra cost", explain.inr(t["extra_cost"]))
                st.metric("Order-days of delay avoided", f"{t['delay_avoided_days']} of {t['late_days_before']}")
                st.metric("High-priority orders on time", f"{t['high_priority_protected']} of {t['high_priority_affected']}")
                st.metric("Purchase orders changed", t["pos_changed"])
                if st.button(f"Approve {p['name']}", key=f"approve-{p['name']}", type="primary" if p.get("recommended") else "secondary"):
                    n = agent.approve(res, p["name"])
                    st.success(f"Approved. {n} PO changes queued and supplier messages drafted.")
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
