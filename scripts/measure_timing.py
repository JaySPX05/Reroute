"""Measure how long ReRoute takes, for the "time to list affected orders" and
"time to a ranked recovery plan" rows on slide 6.

Run from the repo root:
    python -m scripts.measure_timing

Explanations are excluded: they depend on whether Generative AI Hub is connected,
and the planner's own speed is what we want to report.
Writes results/timing.csv.
"""
import csv
import os
import pathlib
import statistics
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from reroute import agent, db  # noqa: E402

T = db.load_tables()
REPEATS = 5

SCENARIOS = {
    "Smelter flood (S20, 8 days)": lambda: agent.analyze_report(
        {"supplier_id": "S20", "issue_type": "flood", "days_down": 8, "note": ""}, T, save=False),
    "Chennai port closed (8 days)": lambda: agent.analyze_text(
        "Chennai Port Authority: all container terminal operations suspended for 8 days.",
        T, use_llm=False),
    "Li-ion cell tariff 10% to 35%": lambda: agent.analyze_text(
        "Finance ministry raises basic customs duty on imported lithium-ion cells from 10% to 35%.",
        T, use_llm=False),
}

rows = []
for name, run in SCENARIOS.items():
    list_ms, plan_ms = [], []
    for _ in range(REPEATS):
        tm = run()["timings_ms"]
        listing = tm.get("detect", 0.0) + tm["match"] + tm["trace"]
        list_ms.append(listing)
        plan_ms.append(listing + tm["simulate"])
    rows.append({
        "scenario": name,
        "median_ms_to_list_affected_orders": round(statistics.median(list_ms), 1),
        "median_ms_to_ranked_plan": round(statistics.median(plan_ms), 1),
        "runs": REPEATS,
    })

os.makedirs(ROOT / "results", exist_ok=True)
with open(ROOT / "results" / "timing.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=rows[0].keys())
    w.writeheader()
    w.writerows(rows)

print("| " + " | ".join(rows[0].keys()) + " |")
print("|" + "---|" * len(rows[0]))
for row in rows:
    print("| " + " | ".join(str(v) for v in row.values()) + " |")
print("\nSaved results/timing.csv")
