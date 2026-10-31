"""Compare the three plans across five disruption scenarios.

Run from the repo root:
    python -m scripts.compare_plans

Writes results/plan_comparison.csv and prints a Markdown table.
"""
import csv
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from reroute import agent, db  # noqa: E402

LAKH = 100000
T = db.load_tables()


def get_signal(signal_id):
    """Return the text of one item in data/sample_signals.json, by id (e.g. N01)."""
    items = json.loads((ROOT / "data" / "sample_signals.json").read_text(encoding="utf-8"))
    for item in items:
        if item["id"] == signal_id:
            return item["text"]
    raise SystemExit(f"{signal_id} not found in data/sample_signals.json")


# use_llm=False keeps detection rule-based, so the numbers are identical on every run
SCENARIOS = {
    "Hosur flood (news)": lambda: agent.analyze_text(get_signal("N01"), T, use_llm=False),
    "Smelter flood (S20, 8 days)": lambda: agent.analyze_report(
        {"supplier_id": "S20", "issue_type": "flood", "days_down": 8, "note": ""},
        T, save=False),
    "Pune fire (news)": lambda: agent.analyze_text(get_signal("N03"), T, use_llm=False),
    "Chennai port closed (8 days)": lambda: agent.analyze_text(
        "Chennai Port Authority: all container terminal operations suspended for 8 days.",
        T, use_llm=False),
    "Li-ion cell tariff 10% to 35%": lambda: agent.analyze_text(
        "Finance ministry raises basic customs duty on imported lithium-ion cells from 10% to 35%.",
        T, use_llm=False),
}

rows, checks = [], []
for name, run in SCENARIOS.items():
    r = run()
    ev, imp = r["event"], r["impact"]
    so = imp["sales_orders"]
    so_late = int((so["late_days"] > 0).sum()) if len(so) else 0
    checks.append(f"{name}: type={ev.event_type}, suppliers matched={len(ev.matched)}, "
                  f"POs affected={len(imp['pos'])}, customer orders late={so_late}")
    for p in r["plans"]:
        t = p["totals"]
        is_cost_event = t["cost_if_wait"] > 0  # cost avoided only makes sense for tariffs
        rows.append({
            "scenario": name,
            "plan": p["name"],
            "pos_changed": t["pos_changed"],
            "extra_cost_lakh": round(t["extra_cost"] / LAKH, 2),
            "cost_avoided_lakh": round(t["cost_avoided"] / LAKH, 2) if is_cost_event else "n/a",
            "delay_avoided": f'{t["delay_avoided_days"]} of {t["late_days_before"]}',
            "high_priority_on_time": f'{t["high_priority_protected"]} of {t["high_priority_affected"]}',
        })

os.makedirs(ROOT / "results", exist_ok=True)
with open(ROOT / "results" / "plan_comparison.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=rows[0].keys())
    w.writeheader()
    w.writerows(rows)

print("| " + " | ".join(rows[0].keys()) + " |")
print("|" + "---|" * len(rows[0]))
for row in rows:
    print("| " + " | ".join(str(v) for v in row.values()) + " |")

print("\nSanity check (what each scenario detected):")
for c in checks:
    print(" -", c)
print("\nSaved results/plan_comparison.csv")