"""Run:  pytest -q   (uses SQLite and the offline rules, no accounts needed)"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["REROUTE_DB"] = "sqlite"
os.environ["REROUTE_LLM"] = "off"
os.environ["REROUTE_SQLITE_PATH"] = str(ROOT / "test.db")

from reroute import agent, db, signals  # noqa: E402

db.init_db()
T = db.load_tables()


def test_news_is_classified_and_matched():
    ev = signals.match_suppliers(signals.classify_text(
        "Heavy rain floods SIPCOT industrial estate in Hosur; units halted for 4-5 days.", T), T)
    assert ev.event_type == "flood" and ev.duration_days == 5
    assert {"S01", "S06", "S12", "S20"} == {m["supplier_id"] for m in ev.matched}


def test_irrelevant_news_does_nothing():
    res = agent.analyze_text("Sensex closes 300 points higher.", T)
    assert not res["event"].relevant and res["impact"]["summary"]["pos_at_risk"] == 0


def test_tier2_downtime_reaches_tier1():
    res = agent.analyze_report({"supplier_id": "S22", "issue_type": "fire", "days_down": 10, "note": ""}, T, save=False)
    down = set(res["impact"]["down"]["supplier_id"])
    assert {"S22", "S08"} <= down          # magnets maker -> motor maker that depends on it


def test_plans_never_make_things_worse():
    res = agent.analyze_report({"supplier_id": "S01", "issue_type": "flood", "days_down": 5, "note": ""}, T, save=False)
    for p in res["plans"]:
        t = p["totals"]
        assert t["late_days_after"] <= t["late_days_before"]
        assert t["extra_cost"] >= 0 or p["name"] == "Lowest cost"
    assert sum(p.get("recommended", False) for p in res["plans"]) == 1


def test_approve_records_actions():
    res = agent.analyze_report({"supplier_id": "S01", "issue_type": "flood", "days_down": 5, "note": ""}, T, save=False)
    n = agent.approve(res, "Balanced")
    assert len(db.read_rows("plan_actions")) >= n


# ---------------------------------------------------------------- showcase: ports, tariffs, agents
from reroute import network  # noqa: E402

PORT = "Chennai Port Authority: all container terminal operations suspended for 8 days. Vessels diverted."
TARIFF = "Finance ministry raises basic customs duty on imported lithium-ion cells from 10% to 35%."
STRIKE = "Transporters announce statewide strike across Tamil Nadu from Monday for 3 days."


def test_port_closure_hits_importers_not_neighbours():
    ev = signals.match_suppliers(signals.classify_text(PORT, T), T)
    assert ev.event_type == "port" and [m["supplier_id"] for m in ev.matched] == ["S23"]


def test_tariff_raises_cost_and_plan_saves_money():
    res = agent.analyze_text(TARIFF, T)
    ev, s = res["event"], res["impact"]["summary"]
    assert ev.event_type == "tariff" and ev.material_ids == ["M23"] and ev.cost_pct == 25
    assert s["kind"] == "cost" and s["cost_increase_if_wait"] > 0 and s["sales_orders_late"] == 0
    rec = next(p for p in res["plans"] if p.get("recommended"))
    assert rec["totals"]["cost_avoided"] > 0


def test_agent_network_autonomy_approval_and_audit():
    net = network.Network(T)
    msgs = list(network.simulate(net, [("d1", "port_notice", PORT), ("d2", "tariff_bulletin", TARIFF),
                                       ("d3", "news", STRIKE)]))
    assert net.stats["auto"] > 0 and net.pending, "expected both autonomous actions and escalations"
    pos_acted = [m.data["action"]["po_id"] for m in msgs if m.kind in ("action.authorised", "approval.requested")]
    assert len(pos_acted) == len(set(pos_acted)), "an order was changed twice"
    first, second = list(net.pending)[:2]
    net.decide(first, True, "ok")
    net.decide(second, False, "no")
    net.run_all()
    assert net.stats["approved"] == 1 and net.stats["rejected"] == 1
    rows = db.read_rows("audit_log")
    assert network.verify_audit(rows)["ok"]
    rows.loc[rows.index[3], "summary"] = "edited"
    assert not network.verify_audit(rows)["ok"]
