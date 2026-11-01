# Live showcase runs

Run on: SQLite (local)   Date: 2026-11-01   Run by: Kavana

How: `streamlit run app.py`, open **Live showcase**, pick a disruption, press **Start live simulation**.
Fill in each cell from what the screen shows. Leave a cell blank rather than guess.

| Disruption | Agent messages | Done by agents alone | Sent to human | Seconds for the whole run | Notes |
|---|---|---|---|---|---|
| Chennai port closure | 14 | 0 | 3 | | All 3 approved. Extra cost Rs 7.96 lakh. 7 POs left as they are. Audit trail: chain intact. |
| Li-ion cell tariff spike | 42 | 5 | 9 | | 14 switches to Pune Battery Systems (5 by agents alone, 9 approved by a human). Extra cost committed Rs 41.00 lakh (switch costs only). Run RUN-5A4E22. |
| Tamil Nadu transport strike | 10 | 1 | 1 | | 11 suppliers down, 31 POs late, 2 customer orders late. 2 expedites: 1 auto-approved by agents (PO 4500000007), 1 approved by a human (PO 4500000013, feeds a high-priority order). Extra cost Rs 2.56 lakh. 29 POs left as they are. |
| Chained (all three, plus the cricket headline) | 66 | 6 | 12 | | All 12 approved. Extra cost Rs 49.45 lakh (7.96 + 41.00 + about 0.49). Strike skipped PO 4500000013, already moved by the port closure. Cricket headline ignored by Sentinel. Run RUN-525372. |

Project handbook says the chained run gives 42 messages, 6 done alone, 12 sent to a human.
Our run: 66 messages, 6 done alone, 12 sent to a human. The handbook's 42 is out of date; use 66.

## After the run

- Approved one escalated action and checked it appears in the audit log: yes (port run, all 3 approved)
- Pressed "Verify audit trail" and it said the chain is intact: yes (port run)
- Sentinel ignored the cricket headline: yes (chained run, messages 143 to 144)
- Anything that looked wrong: the diagram labels say "HANA", but the sidebar shows "Database: SQLite (local)". The message numbers continue across runs, so click Reset before each run. The sidebar says "Language model: not configured (offline templates)", so these runs used offline explanations, not Generative AI Hub. The handbook's 42 messages for the chained run is out of date (we measured 66).