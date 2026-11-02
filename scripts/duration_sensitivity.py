"""Smelter flood (S20) at different durations, all three plans.

Answers the judge question "what if the flood lasts longer?" with real numbers.

Run from the repo root:
    python -m scripts.duration_sensitivity

Writes results/duration_sensitivity.csv and prints a Markdown table.
"""
import csv
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from reroute import agent, db  # noqa: E402

LAKH = 100000
DURATIONS = (3, 5, 8, 11, 14)
T = db.load_tables()

rows = []
for days in DURATIONS:
    r = agent.analyze_report(
        {"supplier_id": "S20", "issue_type": "flood", "days_down": days, "note": ""},
        T, save=False)
    imp = r["impact"]
    for p in r["plans"]:
        t = p["totals"]
        rows.append({
            "days_down": days,
            "suppliers_down": imp["summary"]["suppliers_down"],
            "pos_late": imp["summary"]["pos_at_risk"],
            "plan": p["name"],
            "pos_changed": t["pos_changed"],
            "extra_cost_lakh": round(t["extra_cost"] / LAKH, 2),
            "delay_avoided": f'{t["delay_avoided_days"]} of {t["late_days_before"]}',
            "high_priority_on_time": f'{t["high_priority_protected"]} of {t["high_priority_affected"]}',
        })

os.makedirs(ROOT / "results", exist_ok=True)
with open(ROOT / "results" / "duration_sensitivity.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=rows[0].keys())
    w.writeheader()
    w.writerows(rows)

print("| " + " | ".join(rows[0].keys()) + " |")
print("|" + "---|" * len(rows[0]))
for row in rows:
    print("| " + " | ".join(str(v) for v in row.values()) + " |")
print("\nSaved results/duration_sensitivity.csv")
