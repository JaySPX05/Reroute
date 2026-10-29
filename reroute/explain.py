"""Stage 4 - Explain: plain-language summaries and answers, grounded ONLY in computed facts.

The LLM never invents numbers: every figure comes from the facts JSON built here, and the
prompt tells it to say so when the facts don't answer a question. Offline, templates take over.
"""
import json

from . import llm

SYSTEM = """You are ReRoute, a supply chain replanning assistant for a planner at an Indian manufacturer.
Use ONLY the facts in the JSON you are given. Never invent suppliers, orders, numbers or dates.
If the facts do not answer the question, say what is missing. Amounts are in Indian rupees (Rs).
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
        "summary": impact["summary"],
        "suppliers_down": impact["down"].to_dict("records"),
        "late_sales_orders": impact["sales_orders"][["sales_order_id", "customer", "product", "qty", "due_date",
                                                     "priority", "late_days"]].head(15).to_dict("records"),
        "plans": [],
    }
    for p in plans:
        acts = p["actions"]
        out["plans"].append({
            "name": p["name"], "recommended": p.get("recommended", False), "totals": p["totals"],
            "changes": acts[acts["action"] != "wait"][["po_id", "material", "qty", "from_supplier", "action",
                                                     "to_supplier", "delay_before", "delay_after",
                                                     "extra_cost"]].head(12).to_dict("records") if len(acts) else [],
        })
    return out


def explain_plans(impact: dict, plans: list) -> tuple:
    """Returns (text, method)."""
    f = facts(impact, plans)
    if impact["summary"]["pos_at_risk"] == 0:
        return "No open purchase orders are at risk from this event. No action is needed; ReRoute will keep watching.", "template"
    msg = [{"role": "system", "content": SYSTEM},
           {"role": "user", "content": "Facts:\n" + json.dumps(f, default=str) +
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
    msgs = [{"role": "system", "content": SYSTEM + "\nFacts:\n" + json.dumps(f, default=str)}]
    msgs += (history or [])[-6:]
    msgs.append({"role": "user", "content": question})
    text = llm.chat(msgs)
    if text:
        return text, "llm"
    return ("The language model isn't connected, so here is the computed summary instead:\n\n" + _template(f),
            "template")
