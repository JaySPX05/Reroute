"""Check that explanations never use a number that isn't in the computed facts.

Run:  python scripts/check_explanations.py
First check the model is connected:  python -c "from reroute import llm; print(llm.status())"
Without the service key it still runs, but checks the offline templates instead of the model.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reroute import agent, db, explain, llm  # noqa: E402

NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
TARIFF = "Finance ministry raises basic customs duty on imported lithium-ion cells from 10% to 35%."
QUESTIONS = ["Why not switch everything to Coimbatore?",
             "Which customers should we call today?",
             "What if the flood lasts 3 more days?"]
RERUN_WORDS = ("rerun", "re-run", "run again", "run the", "recompute", "re-simulate", "resimulate",
               "not in the facts", "facts do not", "facts don't", "missing", "don't have", "do not have")


def sample_text(word: str) -> str:
    items = json.loads((Path(__file__).resolve().parents[1] / "data" / "sample_signals.json").read_text())
    return next(i["text"] for i in items if word.lower() in i["text"].lower())


def fact_values(obj) -> list:
    """Every number in the facts: numeric fields plus numbers written inside text fields (ids, dates, signal text)."""
    out = []
    if isinstance(obj, dict):
        for v in obj.values():
            out += fact_values(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out += fact_values(v)
    elif isinstance(obj, bool) or obj is None:
        pass
    elif isinstance(obj, (int, float)):
        out.append(float(obj))
    else:
        try:
            out.append(float(obj))  # numpy numbers
        except (TypeError, ValueError):
            out += [float(n.replace(",", "")) for n in NUM.findall(str(obj))]
    return out


def supported(token: str, values: list) -> bool:
    """A number is supported if some fact value, as-is or shown in lakh/crore/percent, rounds to it."""
    x = float(token.replace(",", ""))
    dec = len(token.split(".")[1]) if "." in token else 0
    for v in values:
        for c in (v, abs(v), v / 1e5, v / 1e7, v * 100):
            if round(c, dec) == x or (dec == 0 and abs(c - x) < 0.5):
                return True
    return False


def check(text: str, facts: dict) -> tuple:
    values = fact_values(json.loads(json.dumps(facts, default=str)))
    tokens = NUM.findall(text)
    ok = [t for t in tokens if supported(t, values)]
    bad = [t for t in tokens if not supported(t, values)]
    return ok, bad


def main():
    print("Model status:", llm.status())
    T = db.load_tables()
    scenarios = [
        ("Hosur flood", lambda: agent.analyze_text(sample_text("Hosur"), T)),
        ("Pune fire", lambda: agent.analyze_text(sample_text("Pune Magnetics"), T)),
        ("Tamil Nadu strike", lambda: agent.analyze_text(sample_text("Tamil Nadu"), T)),
        ("S20 flood report, 8 days", lambda: agent.analyze_report(
            {"supplier_id": "S20", "issue_type": "flood", "days_down": 8, "note": ""}, T, save=False)),
        ("Lithium-ion tariff", lambda: agent.analyze_text(TARIFF, T)),
    ]

    total_bad = 0
    hosur = None
    print(f"\n{'Scenario':28} {'Method':9} {'Supported':>9} {'Unsupported':>11}  Unsupported numbers")
    print("-" * 90)
    for name, fn in scenarios:
        r = fn()
        hosur = hosur or r
        ok, bad = check(r["explanation"], explain.facts(r["impact"], r["plans"]))
        total_bad += len(bad)
        print(f"{name:28} {r['explain_method']:9} {len(ok):>9} {len(bad):>11}  {', '.join(bad) or '-'}")

    print("\nChat questions (asked about the Hosur flood):")
    for q in QUESTIONS:
        text, method = explain.answer(q, hosur["impact"], hosur["plans"])
        ok, bad = check(text, explain.facts(hosur["impact"], hosur["plans"]))
        total_bad += len(bad)
        print(f"\nQ: {q}  [{method}]  supported {len(ok)}, unsupported {len(bad)}: {', '.join(bad) or '-'}")
        print("A:", text.strip().replace("\n", "\n   "))
        if "3 more days" in q:
            says = any(w in text.lower() for w in RERUN_WORDS)
            print("-> Says a rerun / missing facts is needed:", "YES" if says else "NO - check by eye")

    print(f"\nTotal unsupported numbers: {total_bad}")
    if total_bad:
        print("Read each one above. If the model made it up, tighten SYSTEM in reroute/explain.py and run again.")


if __name__ == "__main__":
    main()
