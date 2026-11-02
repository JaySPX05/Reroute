"""Cost breakdown and routes: the parts must add up to the cost the planner ranks plans on."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["REROUTE_DB"] = "sqlite"
os.environ["REROUTE_LLM"] = "off"

from reroute import agent, config, db, logistics, planner  # noqa: E402

T = db.load_tables()
SMELTER = {"supplier_id": "S20", "issue_type": "flood", "days_down": 8, "note": ""}
PORT = "Chennai Port Authority: all container terminal operations suspended for 8 days."
TARIFF = "Finance ministry raises basic customs duty on imported lithium-ion cells from 10% to 35%."
PARTS = ["price_difference", "new_supplier_checks", "extra_freight", "expedite_fee", "duty_if_waiting"]


def test_parts_add_up_to_the_planners_extra_cost():
    for res in [agent.analyze_report(SMELTER, T, save=False), agent.analyze_text(PORT, T), agent.analyze_text(TARIFF, T)]:
        for p in res["plans"]:
            b = logistics.cost_breakdown(T, res["impact"], p)
            assert abs(sum(b[k] for k in PARTS) - p["totals"]["extra_cost"]) < 1
            lines = logistics.plan_lines(T, res["impact"], p)
            if len(lines):   # and row by row
                assert (abs(lines[PARTS].sum(axis=1) - lines["planner_extra_cost"]) < 1).all()


def test_freight_only_for_extra_distance():
    res = agent.analyze_text(PORT, T)   # Chennai battery orders move to Pune, much farther from the plant
    for p in res["plans"]:
        for r in logistics.plan_lines(T, res["impact"], p).itertuples():
            if r.action == "switch":
                extra = max(0.0, planner._plant_km(r.to_supplier_id, T) - planner._plant_km(r.from_supplier_id, T))
                assert r.extra_freight == round(extra * config.FREIGHT_RS_PER_KM, 2)
            else:
                assert r.extra_freight == 0


def test_routes_show_original_and_new_legs():
    res = agent.analyze_report(SMELTER, T, save=False)
    bal = next(p for p in res["plans"] if p["name"] == "Balanced")
    kinds = set(logistics.routes(T, res["impact"], bal)["kind"])
    assert "original" in kinds and kinds & {"switch", "expedite"}
    assert set(logistics.routes(T, res["impact"], None)["kind"]) == {"original"}
