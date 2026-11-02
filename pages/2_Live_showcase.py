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


# ------------------------------------------------------------------ sidebar
status_when_drawn = st.session_state.sim_status   # the Start/Stop buttons below are enabled from this
scenario = st.sidebar.selectbox("Disruption", list(SCENARIOS))
speed = st.sidebar.slider("Seconds per agent message", 0.0, 2.0, 0.7, 0.1)
start = st.sidebar.button("Start Simulation", type="primary",
                          disabled=st.session_state.sim_status == "Running")
stop = st.sidebar.button("Stop Simulation", disabled=st.session_state.sim_status != "Running")
if st.session_state.sim_status == "Stopped":
    st.sidebar.caption("Starting again creates a new run; the stopped run will not resume.")
if st.sidebar.button("Reset"):
    for state_key in ["net", "feed", "last", *SIM_STATE_DEFAULTS]:
        st.session_state.pop(state_key, None)
    st.rerun()
st.sidebar.divider()
st.sidebar.caption("Autonomy limits (Policy agent)")
st.sidebar.write(f"- High-priority customer orders always go to a human\n"
                 f"- Extra cost above {explain.inr(config.AUTO_COST_LIMIT_INR)} goes to a human\n"
                 f"- Moving more than {explain.inr(config.BIG_SWITCH_LIMIT_INR)} of business goes to a human")
st.sidebar.divider()
st.sidebar.caption(f"Database: {'SAP HANA Cloud' if db.backend() == 'hana' else 'SQLite (local)'}")
st.sidebar.caption(f"Language model: {llm.status()}")

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
st.title("ReRoute agent network")
st.caption("Kaveri EV Motors · Supply Chain Resilience")
st.caption("Signals in, decisions out: every message between agents is shown live and written to the audit log.")
banner = st.empty()
with st.container(border=True):
    st.markdown("#### Simulation Summary")
    performance_slots = [c.empty() for c in st.columns(4, gap="small", border=True)]
    st.divider()
    st.markdown("#### Agent Metrics")
    kpi_slots = [c.empty() for c in st.columns(5, gap="small", border=True)]
left, right = st.columns([4, 8])
with left:
    st.subheader("Agents")
    graph_slot = st.empty()
with right:
    st.subheader("Live message feed")
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
