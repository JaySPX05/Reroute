# Live showcase runs

Run on: SQLite (local)  
Date: 2026-11-01  
Run by: Kavana

How: `streamlit run app.py`, open **Live showcase**, pick a disruption, press **Start live simulation**. Values below are transcribed from the recorded run; run duration was not recorded.

| Disruption | Agent messages | Done by agents alone | Sent to human | Seconds for the whole run | Notes |
|---|---:|---:|---:|---|---|
| Chennai port closure | 14 | 0 | 3 | | All 3 approved. Extra cost Rs 7.96 lakh. 7 POs left as they are. Audit trail: chain intact. |
| Li-ion cell tariff spike | 42 | 5 | 9 | | 14 switches to Pune Battery Systems (5 by agents alone, 9 approved by a human). Extra cost committed Rs 41.00 lakh (switch costs only). Run RUN-5A4E22. |
| Tamil Nadu transport strike | 10 | 1 | 1 | | 11 suppliers down, 31 POs late, 2 customer orders late. 2 expedites: 1 auto-approved by agents (PO 4500000007), 1 approved by a human (PO 4500000013, feeds a high-priority order). Extra cost Rs 2.56 lakh. 29 POs left as they are. |
| Chained (all three, plus the cricket headline) | 66 | 6 | 12 | | All 12 approved. Extra cost Rs 49.45 lakh (7.96 + 41.00 + about 0.49). Strike skipped PO 4500000013, already moved by the port closure. Cricket headline ignored by Sentinel. Run RUN-525372. |

"Agent messages" counts every message after all escalations were approved, so it includes the approval messages.
Before any approval, the agents send 8 (port), 24 (tariff), 8 (strike) and 42 (chained) messages. So the chained run is
42 agent messages, or 66 including the 12 human approvals; the handbook's 42 counts the first, not an error.
(Checked 2026-11-01 by rerunning the same four scenarios headless with `network.Network(T, persist=False, use_llm=False)`
and approving every escalation: counts, autonomous actions, escalations and extra costs match the table.)

## After the run

- Approved one escalated action and checked it appears in the audit log: yes (port run, all 3 approved).
- Pressed "Verify audit trail" and it said the chain is intact: yes (port run).
- Sentinel ignored the cricket headline: yes (chained run, messages 143 to 144).
- Anything that looked wrong: the diagram labels say "HANA", but the sidebar shows "Database: SQLite (local)". The message numbers continue across runs, so click Reset before each run. The sidebar says "Language model: not configured (offline templates)", so these runs used offline explanations, not Generative AI Hub.
