"""ReRoute planner dashboard.  Run:  streamlit run app.py"""
import json
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from reroute import agent, config, db, explain, llm

st.set_page_config(page_title="ReRoute", layout="wide")
st.markdown(
    """<style>
    [data-testid="stSidebarNav"]::before {
        content: "TechTitans\\A ReRoute | Supply Chain Resilience Platform";
        display: block;
        white-space: pre-line;
        margin: 0.5rem 1rem 0.75rem;
        padding-bottom: 0.75rem;
        border-bottom: 1px solid var(--secondary-background-color);
        font-size: 1.15rem;
        line-height: 1.55;
        color: var(--text-color);
    }
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
        last = reports.iloc[-1].to_dict()
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


# ------------------------------------------------------------------ main
res = st.session_state.get("result")
if not res:
    st.title("ReRoute")
    st.caption("Kaveri EV Motors · Supply Chain Resilience")
    st.write("Pick a scenario or paste a news item in the sidebar, then press **Analyse**. "
             "Suppliers report problems on the **Supplier report** page.")
    network_map()
    st.stop()

ev, imp, plans, s = res["event"], res["impact"], res["plans"], res["impact"]["summary"]
title = f"{ev.event_type.title()}" + (f" · {ev.location}" if ev.location else "") + (f" · {ev.state}" if ev.scope == "state" else "")
st.title(title if ev.relevant else "No disruption detected")
st.caption("Kaveri EV Motors · Supply Chain Resilience")
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
        risk_colors = ["#2e8b57", "#e6a23c", "#d64545"]
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
            fontSize=27, fontWeight="bold", color="#243247", dy=-8).encode(text="label:N")
        center_label = alt.Chart(pd.DataFrame({"label": ["Total orders"]})).mark_text(
            fontSize=12, color="#596579", dy=17).encode(text="label:N")
        st.markdown("#### Order Risk Summary")
        st.altair_chart((donut + center_total + center_label).properties(height=300), width="stretch")

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
                domain=["On Track", "At Risk", "Critical"], range=["#2e8b57", "#e6a23c", "#d64545"])),
            tooltip=tooltip,
        )
        date_points = chart_orders.melt(
            id_vars=["order_label", "sales_order_id", "priority", "risk", "delay_days", "deadline_label", "predicted_label"],
            value_vars=["deadline", "predicted_date"], var_name="date_type", value_name="date")
        date_points["date_type"] = date_points["date_type"].map(
            {"deadline": "Required deadline", "predicted_date": "Predicted delivery"})
        points = alt.Chart(date_points).mark_point(filled=True, size=85, stroke="#ffffff", strokeWidth=1.5).encode(
            y=alt.Y("order_label:N", sort=sort_orders, title="Customer order (priority)"),
            x=alt.X("date:T", title="Delivery date", axis=alt.Axis(format="%b %d")),
            color=alt.Color("date_type:N", title="Date", legend=alt.Legend(orient="bottom"), scale=alt.Scale(
                domain=["Required deadline", "Predicted delivery"], range=["#3569a8", "#d64545"])),
            shape=alt.Shape("date_type:N", title="Milestone", legend=alt.Legend(orient="bottom"), scale=alt.Scale(
                domain=["Required deadline", "Predicted delivery"], range=["diamond", "circle"])),
            tooltip=tooltip,
        )
        st.altair_chart((delay_lines + points).properties(
            height=max(320, min(760, 25 * len(chart_orders)))), width="stretch")

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
