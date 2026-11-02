"""Stage 4 - Explain: plain-language summaries and answers, grounded ONLY in computed facts.

The LLM never invents numbers: every figure comes from the facts JSON built here, and the
prompt tells it to say so when the facts don't answer a question. Offline, templates take over.
"""
import json

from . import llm

SYSTEM = """You are ReRoute, a supply chain replanning assistant for a planner at an Indian manufacturer.
Use ONLY the facts in the JSON you are given. Never invent suppliers, orders, numbers or dates.
Quote numbers exactly as they appear in the facts. Do not calculate new numbers: no differences, totals,
averages, percentages or per-unit costs. To compare two options, state both numbers instead.
This includes simple arithmetic. Never split a count into parts (do not work out Tier-1 suppliers as total
minus Tier-2), never say how much cheaper or faster one plan is than another, never add up units or
quantities across orders, and never add days to a duration. If a number you want is not in the facts,
leave it out.
For a what-if the facts do not cover (a longer or shorter disruption, a different supplier, more orders),
do not estimate the result: say the plan must be rerun in ReRoute with the new input. Never offer to take
actions yourself; only the planner and ReRoute's agents act.
Each late sales order is one record: take its sales_order_id, customer, due_date and priority from that
same record and never combine fields from different records.
late_days and delay figures are forecasts of how late things will be if nothing is done, counted from
summary.as_of. Do not say an order is already late unless the facts say so.
Money is given as text such as "Rs 2.72 lakh" or "Rs 1.36 crore". Copy it exactly; never convert it to
other units (no million, no thousands) and never write a rupee amount that isn't in the facts.
In plan totals, high_priority_still_late counts only high-priority orders; sales_orders_late_after counts
orders of every priority. customer_orders_late_after_plan gives each order still late after that plan and by
how many days. A plan's "changes" list shows at most 12 changes: for totals use changes_total and
units_switched, never add up the list.
If the facts do not answer the question, say what is missing.
Write short, plain sentences a busy planner can act on. The planner makes the final decision."""


def inr(x: float) -> str:
    x = float(x)
    if abs(x) >= 1e7:
        return f"Rs {x / 1e7:.2f} crore"
    if abs(x) >= 1e5:
        return f"Rs {x / 1e5:.2f} lakh"
    return f"Rs {x:,.0f}"


def facts(impact: dict, plans: list) -> dict:
    e = impact["event"]
    out = {
        "event": {"type": e.event_type, "source": e.source, "text": e.text, "location": e.location,
                  "expected_days": e.duration_days, "severity_1_to_5": e.severity,
                  "cost_pct": getattr(e, "cost_pct", 0.0), "materials": getattr(e, "material_ids", [])},
        # Tier-1 count given outright so the model quotes it instead of subtracting
        "summary": {**impact["summary"], **({"tier1_down": impact["summary"]["suppliers_down"]
                                               - impact["summary"]["tier2_plus_down"]}
                                            if "tier2_plus_down" in impact["summary"] else {})},
        "suppliers_down": impact["down"].to_dict("records"),
        "late_sales_orders": impact["sales_orders"][["sales_order_id", "customer", "product", "qty", "due_date",
                                                     "priority", "late_days"]].head(15).to_dict("records"),
        "plans": [],
    }
    for p in plans:
        acts = p["actions"]
        changed = acts[acts["action"] != "wait"] if len(acts) else acts
        switched = changed[changed["action"] == "switch"] if len(changed) else changed
        late_after = (acts[acts["so_late_after"] > 0].groupby("sales_order_id")["so_late_after"].max()
                      if len(acts) and "so_late_after" in acts else {})
        out["plans"].append({
            "name": p["name"], "recommended": p.get("recommended", False), "totals": p["totals"],
            # totals over ALL changes, computed here, because "changes" below lists at most 12
            "changes_total": int(len(changed)),
            "units_switched": int(switched["qty"].sum()) if len(switched) else 0,
            "customer_orders_late_after_plan": [{"sales_order_id": k, "late_days": int(v)}
                                                for k, v in dict(late_after).items()],
            # alternate suppliers that had no spare capacity left, and who booked it (capped like "changes")
            "capacity_limits": ([f"PO {r.po_id}: {r.capacity_note}" for r in acts.itertuples()
                                 if getattr(r, "capacity_note", "")][:8] if len(acts) else []),
            "changes": acts[acts["action"] != "wait"][["po_id", "material", "qty", "from_supplier", "action",
                                                     "to_supplier", "delay_before", "delay_after",
                                                     "extra_cost"]].head(12).to_dict("records") if len(acts) else [],
        })
    return out


MONEY = {"po_value_at_risk", "cost_increase_if_wait", "extra_cost", "cost_if_wait", "cost_avoided"}


def for_model(f: dict) -> dict:
    """The facts as the language model sees them: every amount of money already written as "Rs ... lakh/crore"
    (so the model never converts units), cost fields dropped for delay events (where they are 0 or negative
    and only confuse), and high-priority orders still late spelled out instead of left to the model."""
    delay = f["summary"].get("kind") != "cost"

    def money(d: dict) -> dict:
        out = {}
        for k, v in d.items():
            if k in MONEY:
                if delay and k != "extra_cost" and k != "po_value_at_risk":
                    continue
                out[k] = inr(v)
            else:
                out[k] = v
        return out

    g = dict(f)
    g["summary"] = money(f["summary"])
    g["plans"] = []
    for p in f["plans"]:
        t = money(p["totals"])
        t["high_priority_still_late"] = p["totals"]["high_priority_affected"] - p["totals"]["high_priority_protected"]
        g["plans"].append({**p, "totals": t, "changes": [money(c) for c in p["changes"]]})
    return g


def explain_plans(impact: dict, plans: list) -> tuple:
    """Returns (text, method)."""
    f = facts(impact, plans)
    if impact["summary"]["pos_at_risk"] == 0:
        return "No open purchase orders are at risk from this event. No action is needed; ReRoute will keep watching.", "template"
    msg = [{"role": "system", "content": SYSTEM},
           {"role": "user", "content": "Facts:\n" + json.dumps(for_model(f), default=str) +
            "\n\nIn under 150 words: what happened, what is at risk, then compare the three plans in one line each "
            "and say why the recommended plan is the best trade-off. End with one line on what the planner should check before approving."}]
    text = llm.chat(msg)
    return (text, "llm") if text else (_template(f), "template")


def _template(f: dict) -> str:
    s, e = f["summary"], f["event"]
    if s.get("kind") == "cost":
        lines = [f"Import duty rises by {e.get('cost_pct', 0):.0f} percentage points. {s['suppliers_down']} suppliers pass "
                 f"the cost on, so {s['pos_at_risk']} open purchase orders worth {inr(s['po_value_at_risk'])} would cost "
                 f"{inr(s['cost_increase_if_wait'])} more if we do nothing. No order is late."]
        for p in f["plans"]:
            t = p["totals"]
            tag = " (recommended)" if p["recommended"] else ""
            lines.append(f"- {p['name']}{tag}: moves {t['pos_changed']} POs to suppliers without the duty, saving "
                         f"{inr(t['cost_avoided'])}; {t['sales_orders_late_after']} customer orders late.")
        lines.append("Before approving, confirm the alternate supplier's quality and capacity for the switched volume.")
        return "\n".join(lines)
    where = f" in {e['location']}" if e["location"] else ""
    label = {"port": "port closure", "power": "power cut", "transport": "transport disruption",
             "equipment": "breakdown"}.get(e["type"], e["type"])
    lines = [f"A {label}{where} is expected to last about {e['expected_days']} days. "
             f"{s['suppliers_down']} suppliers are affected ({s['tier2_plus_down']} of them Tier-2 or deeper), "
             f"putting {s['pos_at_risk']} purchase orders worth {inr(s['po_value_at_risk'])} at risk. "
             f"Without action, {s['sales_orders_late']} customer orders slip ({s['high_priority_late']} high-priority), "
             f"{s['baseline_late_days']} order-days late in total."]
    for p in f["plans"]:
        t = p["totals"]
        tag = " (recommended)" if p["recommended"] else ""
        lines.append(f"- {p['name']}{tag}: changes {t['pos_changed']} POs for {inr(t['extra_cost'])} extra, "
                     f"avoids {t['delay_avoided_days']} order-days of delay, keeps "
                     f"{t['high_priority_protected']} of {t['high_priority_affected']} high-priority orders on time.")
    lines.append("Before approving, confirm the alternate suppliers' spare capacity by phone.")
    return "\n".join(lines)


def answer(question: str, impact: dict, plans: list, history: list | None = None) -> tuple:
    f = facts(impact, plans)
    msgs = [{"role": "system", "content": SYSTEM + "\nFacts:\n" + json.dumps(for_model(f), default=str)}]
    msgs += (history or [])[-6:]
    msgs.append({"role": "user", "content": question})
    text = llm.chat(msgs)
    if text:
        return text, "llm"
    return ("The language model isn't connected, so here is the computed summary instead:\n\n" + _template(f),
            "template")
