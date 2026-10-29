"""Supplier report form: the stand-in for the SAP Build Apps mobile app.

Small suppliers open this on a phone, pick their name, say what happened, and send.
"""
import streamlit as st

from reroute import agent, db

st.set_page_config(page_title="Report a problem · ReRoute")
st.title("Report a problem")
st.write("Tell Kaveri EV Motors early if something will slow your deliveries. It takes under a minute.")

T = db.load_tables()
sup = T["suppliers"].sort_values("name")
labels = {f"{r.name} ({r.city})": r.supplier_id for r in sup.itertuples()}

with st.form("report"):
    who = st.selectbox("Your company", list(labels))
    issue = st.selectbox("What happened?", ["flood", "strike", "fire", "power", "transport", "equipment"],
                         format_func=lambda x: {"flood": "Flood or heavy rain", "strike": "Strike or bandh",
                                                "fire": "Fire or accident", "power": "Power cut",
                                                "transport": "Transport or road problem",
                                                "equipment": "Machine breakdown"}[x])
    days = st.number_input("How many days will production stop?", min_value=1, max_value=60, value=3)
    note = st.text_input("Anything else? (optional)")
    sent = st.form_submit_button("Send report", type="primary")

if sent:
    report = {"supplier_id": labels[who], "issue_type": issue, "days_down": int(days), "note": note}
    st.session_state.result = agent.analyze_report(report, T, save=True)
    st.session_state.chat = []
    st.success("Thank you. Your buyer's planning team has been alerted.")
    st.caption("Planner view: open the main ReRoute page to see the recovery plans for this report.")
