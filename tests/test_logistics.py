"""Shipping estimate and routes (display only: plans and their extra costs must not change)."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["REROUTE_DB"] = "sqlite"
os.environ["REROUTE_LLM"] = "off"

from reroute import agent, db, logistics  # noqa: E402

T = db.load_tables()
SMELTER = {"supplier_id": "S20", "issue_type": "flood", "days_down": 8, "note": ""}
TARIFF = "Finance ministry raises basic customs duty on imported lithium-ion cells from 10% to 35%."


def test_parts_add_up_to_the_planners_extra_cost():
    for res in [agent.analyze_report(SMELTER, T, save=False), agent.analyze_text(TARIFF, T)]:
        for p in res["plans"]:
            b = logistics.cost_breakdown(T, res["impact"], p)
            parts = b["price_difference"] + b["new_supplier_checks"] + b["expedite_fee"] + b["duty_if_waiting"]
            assert abs(parts - p["totals"]["extra_cost"]) < 1
            assert b["total_with_shipping"] == round(b["planner_extra_cost"] + b["shipping_change"], 2)


def test_shipping_follows_the_route():
    res = agent.analyze_report(SMELTER, T, save=False)
    bal = next(p for p in res["plans"] if p["name"] == "Balanced")
    lines = logistics.plan_lines(T, res["impact"], bal)
    for r in lines.itertuples():
        if r.action == "switch":   # new supplier: freight from the new place minus freight from the old one
            assert r.shipping_change == round(logistics.freight(T, r.to_supplier_id) - logistics.freight(T, r.from_supplier_id), 2)
        elif r.action == "expedite":   # same route, express rate
            assert r.shipping_change > 0 and r.km_before == r.km_after
        else:
            assert r.shipping_change == 0


def test_routes_show_original_and_new_legs():
    res = agent.analyze_report(SMELTER, T, save=False)
    bal = next(p for p in res["plans"] if p["name"] == "Balanced")
    kinds = set(logistics.routes(T, res["impact"], bal)["kind"])
    assert {"original", "switch", "expedite"} <= kinds
    assert set(logistics.routes(T, res["impact"], None)["kind"]) == {"original"}
