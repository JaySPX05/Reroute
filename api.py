"""ReRoute REST API.  Run:  uvicorn api:app --reload   then open http://127.0.0.1:8000/docs

An SAP Build Apps form (or any mobile app) can POST supplier reports to /reports.
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from reroute import agent, db, llm

app = FastAPI(title="ReRoute API", version="0.1")
_tables = None


def T():
    global _tables
    if _tables is None:
        _tables = db.load_tables()
    return _tables


class Report(BaseModel):
    supplier_id: str = Field(examples=["S01"])
    issue_type: str = Field(examples=["flood"])
    days_down: int = Field(ge=1, le=60, examples=[5])
    note: str = ""


class Signal(BaseModel):
    text: str = Field(examples=["Heavy rain floods SIPCOT industrial estate in Hosur; units halted for 4-5 days."])
    source: str = "news"


def summarize(res: dict) -> dict:
    ev = res["event"]
    rec = next(p for p in res["plans"] if p.get("recommended"))
    acts = rec["actions"]
    return {
        "event": {k: v for k, v in ev.to_dict().items() if k != "text"},
        "impact": res["impact"]["summary"],
        "recommended_plan": {"name": rec["name"], "totals": rec["totals"],
                             "changes": acts[acts["action"] != "wait"].to_dict("records") if len(acts) else []},
        "other_plans": [{"name": p["name"], "totals": p["totals"]} for p in res["plans"] if not p.get("recommended")],
        "explanation": res["explanation"],
        "timings_ms": res["timings_ms"],
    }


@app.get("/health")
def health():
    return {"status": "ok", "database": db.backend(), "llm": llm.status()}


@app.get("/suppliers")
def suppliers():
    return T()["suppliers"][["supplier_id", "name", "tier", "city", "state"]].to_dict("records")


@app.post("/reports")
def report(r: Report):
    if r.supplier_id not in set(T()["suppliers"]["supplier_id"]):
        raise HTTPException(404, f"Unknown supplier {r.supplier_id}")
    return summarize(agent.analyze_report(r.model_dump(), T(), save=True))


@app.post("/analyze")
def analyze(s: Signal):
    return summarize(agent.analyze_text(s.text, T(), source=s.source))
