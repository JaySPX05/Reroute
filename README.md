# ReRoute — AI replanning for supply disruptions

SAP Ideathon 2026 prototype, theme: Resilient Supply Chains.
A supplier report or news alert comes in; ReRoute finds the suppliers it hits (including Tier-2),
traces the late purchase and customer orders, simulates recovery options, explains three ranked
plans, and records the planner's approval.

## Run it in 5 minutes (no accounts needed)

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python data/generate_data.py          # synthetic supplier network, dated from today
python -c "from reroute import db; db.init_db()"
streamlit run app.py                  # planner dashboard + Supplier report page
```

Optional:

```bash
uvicorn api:app --reload              # REST API, docs at http://127.0.0.1:8000/docs
python scripts/evaluate.py            # numbers for slide 6, written to results/
pytest -q                             # 8 quick tests
```

## Full System Showcase (live multi-agent demo)

Open the **Live showcase** page in the app's sidebar, pick a disruption and press **Start live simulation**.
Six agents (Sentinel, Impact, Sourcing, Policy, Execution, Audit) pass messages live on screen:

- **Disruptions:** Chennai port closure, Li-ion cell tariff spike, Tamil Nadu transport strike, or all three chained.
- **Autonomy within limits:** the Policy agent lets agents act alone on small changes; high-priority orders,
  extra cost above Rs 1 lakh, or moving more than Rs 50 lakh of business wait in the approval queue.
- **Human approval:** approve or reject each escalation with a reason, or approve all.
- **Audit log:** every message and decision is stored in a hash-chained log (SAP HANA Cloud when connected);
  "Verify audit trail" detects any edited record.
- **SAP integration:** HANA Cloud data and logs, Generative AI Hub explanations, S/4HANA Purchase Order
  requests prepared by the Execution agent.

Limits are set in `.env` with `AUTO_COST_LIMIT_INR` and `BIG_SWITCH_LIMIT_INR`.

## Connect SAP services

1. `pip install -r requirements-sap.txt`
2. Copy `.env.example` to `.env` and fill in the keys (see the build guide, Day 1 morning).
3. `python -m reroute.s4_sandbox` pulls sample POs from the S/4HANA sandbox.
4. Set `REROUTE_DB=hana`, run `python -c "from reroute import db; db.init_db()"` to load SAP HANA Cloud.

With the AI Core keys set, detection and explanations use Generative AI Hub; without them, or if a
call fails, ReRoute falls back to keyword rules and templates so the demo never breaks.

## Layout

| Path | Stage | What it does |
| --- | --- | --- |
| `data/generate_data.py` | Data | Synthetic suppliers (Tier 1-2), materials, BOM, sales and purchase orders |
| `reroute/signals.py` | Detect | Classifies text (LLM or rules), matches suppliers by name, city radius or state |
| `reroute/impact.py` | Trace | Spreads downtime up the tiers, finds late POs and customer orders |
| `reroute/planner.py` | Simulate | Wait / expedite / switch options, shared spare capacity, three weighted plans |
| `reroute/explain.py` | Explain | Grounded LLM summaries and Q&A, offline templates |
| `reroute/agent.py` | Orchestrate | Runs the stages, records approvals and supplier messages |
| `reroute/network.py` | Agents | Six-agent message network, autonomy policy, approval queue, hash-chained audit log |
| `pages/2_Live_showcase.py` | Showcase | Live agent graph, message feed, approval queue, audit view, SAP status |
| `reroute/db.py` | Data access | SQLite or SAP HANA Cloud with the same code |
| `reroute/llm.py` | AI | Generative AI Hub wrapper with safe fallback |
| `reroute/s4_sandbox.py` | Integration | Pulls purchase orders from the S/4HANA Cloud sandbox API |
| `app.py`, `pages/` | UI | Planner dashboard and supplier report form (Streamlit) |
| `api.py` | API | `/reports`, `/analyze`, `/suppliers`, `/health` (FastAPI) |
| `scripts/evaluate.py` | Results | Detection accuracy and replanning outcomes |

All data is synthetic. SAP IBP and Joule Studio are represented by `planner.py` and the agent/chat;
see the build guide for how they map to the production design.
