"""Lowest cost is a real option, and plan figures never show "0 of 0" or a meaningless cost avoided."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["REROUTE_DB"] = "sqlite"
os.environ["REROUTE_LLM"] = "off"

from reroute import agent, db, explain  # noqa: E402

T = db.load_tables()
SMELTER = {"supplier_id": "S20", "issue_type": "flood", "days_down": 8, "note": ""}
PORT = "Chennai Port Authority: all container terminal operations suspended for 8 days."
TARIFF = "Finance ministry raises basic customs duty on imported lithium-ion cells from 10% to 35%."


def plan(res, name):
    return next(p for p in res["plans"] if p["name"] == name)


def test_lowest_cost_acts_when_a_cheap_fix_exists_and_stays_cheapest():
    for res in [agent.analyze_report(SMELTER, T, save=False), agent.analyze_text(PORT, T)]:
        low, bal = plan(res, "Lowest cost")["totals"], plan(res, "Balanced")["totals"]
        assert low["pos_changed"] > 0 and low["delay_avoided_days"] > 0      # not just "wait"
        assert low["extra_cost"] <= bal["extra_cost"]


def test_tariff_figures_read_as_no_late_orders_not_zero_of_zero():
    res = agent.analyze_text(TARIFF, T)
    t = plan(res, "Balanced")["totals"]
    assert explain.delay_avoided_text(t) == "No late orders"
    assert explain.high_priority_text(t) == "None at risk"
    assert explain.cost_avoided_text(t).startswith("Rs ")
    assert "nothing is late" in explain.same_plans_note(res["plans"])


def test_delay_event_has_no_cost_avoided_and_counts_order_days():
    res = agent.analyze_text(PORT, T)
    t = plan(res, "Balanced")["totals"]
    assert explain.cost_avoided_text(t) == "n/a"
    assert explain.delay_avoided_text(t) == f"{t['delay_avoided_days']} of {t['late_days_before']}"
    assert explain.same_plans_note(res["plans"]) == ""        # the plans differ, so no note
