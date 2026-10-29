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
    lines = ['digraph G {', 'rankdir=TB; bgcolor="transparent"; nodesep=0.5; ranksep=0.32;',
             'node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=16, margin="0.12,0.06", '
             'color="#8a94a6", fillcolor="#eef1f6", fontcolor="#1a2233"];',
             'edge [color="#8a94a6", arrowsize=0.8];']
    for key, (name, role) in network.AGENTS.items():
        fill = "#ffb627" if key == recipient else "#7fc4ff" if key == sender else (
            "#e7e2ff" if key == "planner" else "#eef1f6")
        pen = 2.5 if key in (sender, recipient) else 1
        lines.append(f'{key} [label=<<b>{name}</b><br/><font point-size="12">{role}</font>>, '
                     f'fillcolor="{fill}", penwidth={pen}];')
    for a, b in EDGES:
        hot = (a, b) == (sender, recipient)
        lines.append(f'{a} -> {b} [color="{"#d62828" if hot else "#8a94a6"}", penwidth={3 if hot else 1}];')
    if active and (sender, recipient) not in EDGES:
        lines.append(f'{sender} -> {recipient} [color="#d62828", penwidth=3, style=dashed];')
    lines.append('{rank=same; policy; planner;}')
    lines.append("}")
    return "\n".join(lines)


def show_graph(slot, active=None):
    try:
        slot.graphviz_chart(graph_dot(active), width="stretch")
    except TypeError:  # older Streamlit
        slot.graphviz_chart(graph_dot(active), use_container_width=True)


def feed_frame(msgs) -> pd.DataFrame:
    return pd.DataFrame([{"#": m.seq,
                          "route": f"{network.AGENTS[m.sender][0]} → {network.AGENTS[m.recipient][0]}",
                          "summary": m.summary} for m in reversed(msgs)])


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

# ------------------------------------------------------------------ sidebar
st.sidebar.title("Live showcase")
scenario = st.sidebar.selectbox("Disruption", list(SCENARIOS))
speed = st.sidebar.slider("Seconds per agent message", 0.0, 2.0, 0.7, 0.1)
start = st.sidebar.button("Start live simulation", type="primary")
if st.sidebar.button("Reset"):
    for k in ["net", "feed", "last"]:
        st.session_state.pop(k, None)
    st.rerun()
st.sidebar.divider()
st.sidebar.caption("Autonomy limits (Policy agent)")
st.sidebar.write(f"- High-priority customer orders always go to a human\n"
                 f"- Extra cost above {explain.inr(config.AUTO_COST_LIMIT_INR)} goes to a human\n"
                 f"- Moving more than {explain.inr(config.BIG_SWITCH_LIMIT_INR)} of business goes to a human")
st.sidebar.divider()
st.sidebar.caption(f"Database: {'SAP HANA Cloud' if db.backend() == 'hana' else 'SQLite (local)'}")
st.sidebar.caption(f"Language model: {llm.status()}")

# ------------------------------------------------------------------ layout
st.title("ReRoute agent network")
st.caption("Signals in, decisions out: every message between agents is shown live and written to the audit log.")
banner = st.empty()
kpi_slots = [c.empty() for c in st.columns(5)]
left, right = st.columns([4, 8])
with left:
    st.subheader("Agents")
    graph_slot = st.empty()
with right:
    st.subheader("Live message feed")
    feed_slot = st.empty()

# ------------------------------------------------------------------ live run
if start:
    net = network.Network(T)
    st.session_state.net, st.session_state.feed, st.session_state.last = net, [], None
    for key in SCENARIOS[scenario]:
        label, source, text = STEPS[key]
        banner.info(f"**{label}:** {text}")
        net.inject(text, source, label)
        for m in net.run():
            st.session_state.feed.append(m)
            st.session_state.last = (m.sender, m.recipient)
            show_graph(graph_slot, st.session_state.last)
            show_feed(feed_slot, st.session_state.feed)
            show_kpis(net, kpi_slots)
            if speed:
                time.sleep(speed)
    st.session_state.last = None

net = st.session_state.get("net")
if not net:
    banner.info("Pick a disruption in the sidebar and press **Start live simulation**.")
    show_graph(graph_slot)
    st.stop()

show_graph(graph_slot, st.session_state.get("last"))
show_feed(feed_slot, st.session_state.feed)
show_kpis(net, kpi_slots)
banner.success(f"Run {net.run_id}: the network is quiet. "
               + (f"{len(net.pending)} actions are waiting for your decision below." if net.pending
                  else "Nothing is waiting for you."))


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
                st.caption(f"Why it needs you: {a['rule']}. Extra cost {explain.inr(a['extra_cost'])}, "
                           f"{explain.inr(a['net_cost'])} versus doing nothing. Delay {a['delay_before']} → {a['delay_after']} days.")
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
                                            "cost avoided": explain.inr(p["totals"]["cost_avoided"]),
                                            "order-days avoided": f"{p['totals']['delay_avoided_days']} of {p['totals']['late_days_before']}",
                                            "high-priority on time": f"{p['totals']['high_priority_protected']} of {p['totals']['high_priority_affected']}"}
                                           for p in stt["plans"]]), hide_index=True, width="stretch")
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
    rows = db.read_rows("audit_log")
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
