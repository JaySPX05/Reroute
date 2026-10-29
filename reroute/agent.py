"""The agent: runs Detect -> Trace -> Simulate -> Explain, and records approved plans.

In production this orchestration would be a Joule Studio agent calling the same steps as tools.
"""
import time

from . import db, explain, impact, planner, signals


def load():
    return db.load_tables()


def run(event, tables) -> dict:
    t0 = time.perf_counter()
    event = signals.match_suppliers(event, tables)
    t1 = time.perf_counter()
    imp = impact.trace(event, tables)
    t2 = time.perf_counter()
    plans = planner.build_plans(imp, tables)
    t3 = time.perf_counter()
    text, method = explain.explain_plans(imp, plans)
    t4 = time.perf_counter()
    return {"event": event, "impact": imp, "plans": plans, "explanation": text, "explain_method": method,
            "timings_ms": {"match": round((t1 - t0) * 1000, 1), "trace": round((t2 - t1) * 1000, 1),
                           "simulate": round((t3 - t2) * 1000, 1), "explain": round((t4 - t3) * 1000, 1),
                           "total": round((t4 - t0) * 1000, 1)}}


def analyze_text(text: str, tables, source: str = "news", use_llm: bool = True) -> dict:
    t0 = time.perf_counter()
    event = signals.classify_text(text, tables, source=source, use_llm=use_llm)
    detect_ms = round((time.perf_counter() - t0) * 1000, 1)
    out = run(event, tables)
    out["timings_ms"]["detect"] = detect_ms
    out["timings_ms"]["total"] = round(out["timings_ms"]["total"] + detect_ms, 1)
    return out


def analyze_report(report: dict, tables, save: bool = True) -> dict:
    """report = {supplier_id, issue_type, days_down, note}"""
    if save:
        db.insert_row("supplier_reports", {"report_id": f"R{int(time.time())}", "created_at": db.now(), **report})
    return run(signals.event_from_report(report, tables), tables)


def approve(result: dict, plan_name: str) -> int:
    """Record the approved plan's PO changes and draft the supplier messages.

    The S/4HANA sandbox is read-only, so changes are stored with status 'Pending S/4HANA update'.
    With a real system this is where you would PATCH the purchase order through
    API_PURCHASEORDER_PROCESS_SRV.
    """
    plan = next(p for p in result["plans"] if p["name"] == plan_name)
    n = 0
    for a in plan["actions"].itertuples():
        if a.action == "wait":
            continue
        if a.action == "switch":
            details = f"Move {a.qty} x {a.material} from {a.from_supplier} to {a.to_supplier}"
            msg = (f"Dear {a.to_supplier} team, please confirm you can supply {a.qty} x {a.material} "
                   f"for PO {a.po_id} within your standard lead time. Thank you.")
        else:
            details = f"Expedite {a.qty} x {a.material} with {a.from_supplier} after restart"
            msg = (f"Dear {a.from_supplier} team, once you restart please prioritise PO {a.po_id} "
                   f"({a.qty} x {a.material}) and ship express. We will cover the freight difference.")
        db.insert_row("plan_actions", {
            "action_id": f"A{int(time.time() * 1000) % 10**9}{n}", "created_at": db.now(),
            "event_id": result["event"].event_id, "plan_name": plan_name, "action_type": a.action,
            "po_id": a.po_id, "details": details, "supplier_message": msg, "status": "Pending S/4HANA update"})
        n += 1
    return n
