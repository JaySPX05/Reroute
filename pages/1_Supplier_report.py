"""Supplier report form: the stand-in for the SAP Build Apps mobile app.

Small suppliers open this on a phone, pick their name, say what happened, and send.
"""
import streamlit as st

from reroute import agent, db

st.set_page_config(page_title="Report a problem · ReRoute")
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
st.title("Report a problem")
st.write("Tell Kaveri EV Motors early if something will slow your deliveries. It takes under a minute.")

T = db.load_tables()
sup = T["suppliers"].sort_values("name")
labels = {f"{r.name} ({r.city})": r.supplier_id for r in sup.itertuples()}

with st.container(border=True):
    with st.form("report"):
        who = st.selectbox("Your company", list(labels))
        issue = st.selectbox("What happened?", ["flood", "strike", "fire", "power", "transport", "equipment"],
                             format_func=lambda x: {"flood": "Flood or heavy rain", "strike": "Strike or bandh",
                                                    "fire": "Fire or accident", "power": "Power cut",
                                                    "transport": "Transport or road problem",
                                                    "equipment": "Machine breakdown"}[x])
        days = st.number_input("How many days will production stop?", min_value=1, max_value=60, value=3)
        note = st.text_input("Anything else? (optional)")
        sent = st.form_submit_button("Send report", type="primary", width="stretch")

if sent:
    report = {"supplier_id": labels[who], "issue_type": issue, "days_down": int(days), "note": note}
    st.session_state.result = agent.analyze_report(report, T, save=True)
    st.session_state.chat = []
    st.success("Thank you. Your buyer's planning team has been alerted.")
    st.caption("Planner view: open the main ReRoute page to see the recovery plans for this report.")
