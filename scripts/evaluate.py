"""Produce the numbers for slide 6 (Experimental results).

Run:  python scripts/evaluate.py           (rules only, works offline)
      python scripts/evaluate.py --llm     (also scores Generative AI Hub detection)

Writes results/eval_detection.csv, results/eval_scenarios.csv and results/eval_summary.md.
Every number comes from this run on the synthetic test bed. Say so on the slide.
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from reroute import agent, config, db, llm, signals  # noqa: E402

OUT = ROOT / "results"

SCENARIOS = [  # supplier reports: (supplier_id, issue, days down)
    ("S01", "flood", 5), ("S06", "strike", 3), ("S12", "fire", 7), ("S08", "power", 2),
    ("S20", "flood", 8), ("S22", "fire", 10), ("S10", "transport", 4), ("S04", "equipment", 3),
]


def detection(use_llm: bool, signals_file: Path) -> pd.DataFrame:
    T = db.load_tables()
    items = json.loads(signals_file.read_text(encoding="utf-8"))
    rows = []
    for it in items:
        t0 = time.perf_counter()
        ev = signals.match_suppliers(signals.classify_text(it["text"], T, source=it["source"], use_llm=use_llm), T)
        ms = (time.perf_counter() - t0) * 1000
        got, want = {m["supplier_id"] for m in ev.matched}, set(it["label"]["suppliers"])
        rows.append({"id": it["id"], "method": ev.method, "relevant_ok": ev.relevant == it["label"]["relevant"],
                     "type_ok": (ev.event_type == it["label"]["event_type"]) if it["label"]["relevant"] else None,
                     "true_pos": len(got & want), "false_pos": len(got - want), "false_neg": len(want - got),
                     "ms": round(ms, 1), "text": it["text"]})
    return pd.DataFrame(rows)


def scenarios() -> pd.DataFrame:
    T = db.load_tables()
    rows = []
    for sid, issue, days in SCENARIOS:
        res = agent.analyze_report({"supplier_id": sid, "issue_type": issue, "days_down": days, "note": "eval"}, T, save=False)
        s = res["impact"]["summary"]
        bal = next(p for p in res["plans"] if p["name"] == "Balanced")["totals"]
        rows.append({"supplier": sid, "issue": issue, "days_down": days, "suppliers_down": s["suppliers_down"],
                     "pos_at_risk": s["pos_at_risk"], "orders_late_if_wait": s["sales_orders_late"],
                     "late_days_if_wait": s["baseline_late_days"], "late_days_with_plan": bal["late_days_after"],
                     "delay_avoided_days": bal["delay_avoided_days"], "extra_cost_inr": bal["extra_cost"],
                     "high_priority_protected": bal["high_priority_protected"],
                     "high_priority_affected": bal["high_priority_affected"],
                     "signal_to_plan_ms": res["timings_ms"]["total"]})
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true", help="also score detection with Generative AI Hub")
    ap.add_argument("--signals", default=str(config.DATA_DIR / "sample_signals.json"),
                    help="labelled signals to score; use a held-out file a teammate wrote without seeing the rules")
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)

    sig_file = Path(args.signals)
    det = [detection(False, sig_file)]
    if args.llm:
        if not llm.available():
            print("Generative AI Hub is not configured; skipping --llm.")
        else:
            det.append(detection(True, sig_file))
    det = pd.concat(det)
    det.to_csv(OUT / "eval_detection.csv", index=False)

    sc = scenarios()
    sc.to_csv(OUT / "eval_scenarios.csv", index=False)

    lines = ["# ReRoute evaluation (synthetic test bed)", "", f"Signals scored: {sig_file.name}"]
    if sig_file.name == "sample_signals.json":
        lines.append("Warning: these samples were written alongside the keyword rules, so this is a smoke test. "
                     "Report the score on a held-out file instead (--signals data/heldout_signals.json).")
    lines.append("")
    for method, d in det.groupby("method"):
        tp, fp, fn = d["true_pos"].sum(), d["false_pos"].sum(), d["false_neg"].sum()
        typed = d["type_ok"].dropna()
        lines += [f"## Detection ({method}, {len(d)} labelled signals)",
                  f"- Relevant vs not relevant: {d['relevant_ok'].mean():.0%} correct",
                  f"- Event type on real disruptions: {typed.mean():.0%} correct ({int(typed.sum())}/{len(typed)})",
                  f"- Supplier matching: precision {tp / max(1, tp + fp):.0%}, recall {tp / max(1, tp + fn):.0%}",
                  f"- Median time per signal: {statistics.median(d['ms']):.0f} ms", ""]
    hp_aff, hp_ok = sc["high_priority_affected"].sum(), sc["high_priority_protected"].sum()
    lines += [f"## Replanning ({len(sc)} supplier-report scenarios, Balanced plan)",
              f"- Median time from report to ranked plan: {sc['signal_to_plan_ms'].median():.0f} ms",
              f"- Order-days late: {sc['late_days_if_wait'].sum()} if we wait, {sc['late_days_with_plan'].sum()} with the plan "
              f"({sc['delay_avoided_days'].sum() / max(1, sc['late_days_if_wait'].sum()):.0%} avoided)",
              f"- High-priority customer orders kept on time: {hp_ok} of {hp_aff}",
              f"- Extra cost per scenario: median Rs {sc['extra_cost_inr'].median():,.0f}", "",
              "Not measured here: the manual baseline (time a teammate doing it by hand) and planner acceptance."]
    (OUT / "eval_summary.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print("\nPer-scenario detail:\n" + sc.drop(columns=["signal_to_plan_ms"]).to_string(index=False))


if __name__ == "__main__":
    main()
