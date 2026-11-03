"""IMD alerts: dates in the alert decide when the outage starts; a yellow alert puts suppliers on watch only."""
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["REROUTE_DB"] = "sqlite"
os.environ["REROUTE_LLM"] = "off"

from reroute import agent, db, explain, signals  # noqa: E402

T = db.load_tables()
TODAY = date(2026, 10, 29)          # data/meta.csv as_of
SIK = "South Interior Karnataka: {} alert for heavy rain, thunderstorms, and lightning from November 3 to November 5"


def test_alert_window_reads_dates():
    assert signals.alert_window("from November 3 to November 5", TODAY) == (5, 3)
    assert signals.alert_window("from 4th Nov to 6th Nov", TODAY) == (6, 3)
    assert signals.alert_window("red alert till 2 November", TODAY) == (0, 5)
    assert signals.alert_window("rain from 30 Dec to 2 Jan", TODAY) == (62, 4)       # into next year
    assert signals.alert_window("flood from Oct 20 to Oct 22", TODAY) == (0, 0)      # already over
    assert signals.alert_window("for the next 72 hours", TODAY) is None
    assert signals.alert_level("IMD Yellow alert for rain") == "yellow"
    assert signals.alert_level("orange warning issued") == "orange"


def test_orders_due_before_the_alert_starts_are_not_late():
    res = agent.analyze_text(SIK.format("Orange"), T, source="imd")
    ev, s = res["event"], res["impact"]["summary"]
    assert ev.starts_in_days == 5 and ev.duration_days == 3 and s["starts_on"] == "2026-11-03"
    assert s["pos_at_risk"] > 0
    assert (res["impact"]["pos"]["due"] >= date(2026, 11, 3)).all()
    assert (res["impact"]["sales_orders"]["due_date"] >= "2026-11-03").all()   # nothing due 1 Nov


def test_yellow_alert_is_watch_only():
    res = agent.analyze_text(SIK.format("Yellow"), T, source="imd")
    s = res["impact"]["summary"]
    assert res["event"].relevant and res["event"].alert_level == "yellow"
    assert s["pos_at_risk"] == 0 and s["suppliers_down"] == 0
    assert set(s["on_watch"]) == {"Mysuru Brakes & Clutches", "Tumakuru Wiring Pvt Ltd", "Bengaluru E-Motors",
                                  "Bengaluru PCB Assembly"}
    assert res["explanation"].startswith("IMD yellow alert from 3 Nov to 5 Nov")


def test_alert_without_dates_starts_today_as_before():
    res = agent.analyze_text("IMD red alert: extremely heavy rainfall likely over Chennai and Kancheepuram districts "
                             "for the next 72 hours.", T, source="imd")
    assert res["event"].starts_in_days == 0 and res["impact"]["summary"]["starts_on"] == "2026-10-29"
    assert res["impact"]["summary"]["sales_orders_late"] >= 1


def test_facts_give_expedited_units_to_quote():
    res = agent.analyze_text(SIK.format("Orange"), T, source="imd")
    f = explain.facts(res["impact"], res["plans"])
    for p, plan in zip(f["plans"], res["plans"]):
        a = plan["actions"]
        assert p["units_expedited"] == int(a[a["action"] == "expedite"]["qty"].sum())
    assert f["event"]["starts_on"] == "2026-11-03" and f["event"]["imd_alert_colour"] == "orange"
