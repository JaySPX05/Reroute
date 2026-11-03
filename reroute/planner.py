"""Stage 3 - Simulate and rank: recovery options for every late purchase order.

This is the stand-in for SAP IBP scenario planning. For each late PO it considers:
  wait      keep the order with the original supplier; the customer order may slip
  expedite  ask the original supplier to prioritise our order and ship express after restart
  switch    move the whole order to an alternate supplier that is not down and has spare capacity

Spare capacity at alternate suppliers is SHARED across all late POs, so the order in which POs are
planned matters: high-priority customer orders are planned first.

Three plans come out, from three sets of weights: Fastest recovery, Lowest cost, Balanced.
"""
from datetime import timedelta

import pandas as pd

from . import config
from .impact import PRIORITY_WEIGHT, as_of
from .signals import haversine_km

EXPEDITE_SAVES_DAYS = 1
EXPEDITE_COST_SHARE = 0.08    # express freight + overtime, as a share of PO value
SWITCH_ONBOARD_SHARE = 0.02   # extra logistics and quality checks for a new source
FREIGHT_RS_PER_KM = config.FREIGHT_RS_PER_KM   # road freight for one truckload (assumption, set in .env)
ROAD_FACTOR = config.ROAD_FACTOR   # roads are longer than the straight line (set in .env)


_KM_CACHE = []   # [(meta, cities, suppliers, {supplier_id: km})], newest last


def _km_by_supplier(tables) -> dict:
    """Road km to the plant for every supplier, worked out once per set of tables.

    The planner asks for these distances hundreds of times per plan; re-indexing the tables on each
    call made planning several times slower. The cache keeps the table objects themselves and checks
    identity, so reloaded tables are always worked out afresh.
    """
    frames = (tables["meta"], tables["cities"], tables["suppliers"])
    for *cached, km in _KM_CACHE:
        if all(a is b for a, b in zip(cached, frames)):
            return km
    plant = tables["meta"].set_index("key").loc["plant", "value"]
    c = tables["cities"].set_index("city").loc[plant]
    km = {s.supplier_id: haversine_km(c["lat"], c["lon"], s.lat, s.lon) * ROAD_FACTOR
          for s in tables["suppliers"].itertuples()}
    _KM_CACHE.append((*frames, km))
    del _KM_CACHE[:-4]
    return km


def _plant_km(supplier_id, tables) -> float:
    """Road distance in km from a supplier to our plant (straight line x ROAD_FACTOR)."""
    return _km_by_supplier(tables)[supplier_id]

PLAN_WEIGHTS = {
    "Fastest recovery": {"cost": 0.10, "delay": 0.55, "service": 0.35},
    "Lowest cost": {"cost": 0.65, "delay": 0.15, "service": 0.20},
    "Balanced": config.WEIGHTS_BALANCED,
}


def _alternates(sm, material_id, exclude_supplier) -> list:
    """Rows of supplier_materials for this material from other suppliers, in table order.

    Grouped once per table: filtering the DataFrame for every PO, twice per PO, was most of the planning time.
    """
    for cached, groups in _ALT_CACHE:
        if cached is sm:
            break
    else:
        groups = {}
        for r in sm.itertuples():
            groups.setdefault(r.material_id, []).append(r)
        _ALT_CACHE.append((sm, groups))
        del _ALT_CACHE[:-4]
    return [r for r in groups.get(material_id, []) if r.supplier_id != exclude_supplier]


_ALT_CACHE = []   # [(supplier_materials, {material_id: [rows]})], newest last


def _options(po, today, tables, down_days, spare):
    """All feasible options for one PO given the spare capacity still free.

    down_days = {supplier_id: days down}. An alternate that is itself down for a few days
    (for example through a shared Tier-2 supplier) can still be used, just later.
    """
    # waiting costs nothing extra after a downtime event, but means paying the new duty after a tariff
    opts = [{"action": "wait", "alt_supplier_id": "", "delay_days": int(po.delay_days),
             "extra_cost": float(getattr(po, "extra_cost_wait", 0.0) or 0.0)}]
    if po.delay_days > 0:
        opts.append({"action": "expedite", "alt_supplier_id": "",
                     "delay_days": max(0, int(po.delay_days) - EXPEDITE_SAVES_DAYS),
                     "extra_cost": round(po.value * EXPEDITE_COST_SHARE, 2)})
    for a in _alternates(tables["supplier_materials"], po.material_id, po.supplier_id):
        if spare.get((a.supplier_id, po.material_id), 0) < po.qty:
            continue
        arrival = today + timedelta(days=int(down_days.get(a.supplier_id, 0)) + int(a.lead_days))
        delay = max(0, (arrival - po.due).days)
        # a farther supplier costs more to truck in: pay only the extra distance over the original route
        extra_km = max(0.0, _plant_km(a.supplier_id, tables) - _plant_km(po.supplier_id, tables))
        extra = (po.qty * (a.unit_price - po.unit_price) + po.value * SWITCH_ONBOARD_SHARE
                 + extra_km * FREIGHT_RS_PER_KM)
        opts.append({"action": "switch", "alt_supplier_id": a.supplier_id, "delay_days": delay,
                     "extra_cost": round(extra, 2)})
    for o in opts:
        o["so_late_days"] = max(0, o["delay_days"] - int(po.cover_days))
    return opts


COST_REFERENCE_SHARE = 0.20   # a 20% premium on the PO value counts as the worst acceptable cost
COVERED_DELAY_FACTOR = 0.1    # a PO delay that plant stock absorbs matters far less than one that reaches a customer


def _score(opt, po, w):
    """Lower is better. Each part is scaled to 0..1 so the weights mean what they say."""
    cost = min(1.0, max(0.0, opt["extra_cost"]) / max(1.0, po.value) / COST_REFERENCE_SHARE)
    delay = opt["delay_days"] / max(1, po.delay_days)
    if po.so_late_days == 0:
        delay *= COVERED_DELAY_FACTOR
    service = PRIORITY_WEIGHT.get(po.so_priority, 0.2) * min(1.0, opt["so_late_days"] / max(1, po.so_late_days or 1))
    return w["cost"] * cost + w["delay"] * delay + w["service"] * service


def _capacity_note(po, sm, spare, booked, sup_names, only: str = "") -> str:
    """Why an alternate supplier could NOT take this PO: not enough spare capacity left.

    Names the earlier POs that booked the rest, so the planner sees the plans don't clash.
    """
    notes = []
    for a in _alternates(sm, po.material_id, po.supplier_id):
        if only and a.supplier_id != only:
            continue
        left = spare.get((a.supplier_id, po.material_id), 0)
        if left >= po.qty:
            continue
        taken = booked.get((a.supplier_id, po.material_id), [])
        why = f"Not switched to {sup_names.get(a.supplier_id, a.supplier_id)}: needs {int(po.qty)}, only {int(left)} spare left, {int(po.qty) - int(left)} short"
        if taken:
            why += " (" + ", ".join(f"{q} booked for PO {pid}" + (f" in {where}" if where else "")
                                    for pid, q, where in taken) + ")"
        notes.append(why + ".")
    return " ".join(notes)


def build_plan(impact: dict, tables, name: str, weights: dict, booked_before: dict | None = None) -> dict:
    """booked_before = {(supplier_id, material_id): [(po_id, qty, event_label)]}: spare capacity that
    earlier disruptions in the same run already took. It is subtracted before planning, so two
    disruptions never promise the same parts."""
    today = as_of(tables)
    pos = impact["pos"].copy()
    if pos.empty:
        return {"name": name, "actions": pd.DataFrame(), "totals": _totals(impact, pd.DataFrame())}
    down_days = dict(zip(impact["down"]["supplier_id"], impact["down"]["days_down"]))
    sm = tables["supplier_materials"]
    # spare units per alternate supplier, shared by every PO: one week for a short outage,
    # the whole horizon for a tariff, which lasts as long as the orders it touches
    weeks = 4 if impact["summary"].get("kind") == "cost" else 1
    spare = {}
    for r in sm.itertuples():
        spare[(r.supplier_id, r.material_id)] = r.weekly_capacity * r.spare_share * weeks
    for key, taken in (booked_before or {}).items():
        if key in spare:
            spare[key] = max(0.0, spare[key] - sum(q for _, q, _ in taken))
    pos["prio_rank"] = pos["so_priority"].map({"High": 0, "Medium": 1, "Low": 2})
    if weeks > 1:
        # cost shock: nothing is late, so give the cheaper capacity to the orders that have time to move
        pos = pos.sort_values(["due", "po_id"], ascending=[False, True])
    else:
        # delay: protect high-priority customer orders first
        pos = pos.sort_values(["prio_rank", "due", "po_id"])

    sup_names = tables["suppliers"].set_index("supplier_id")["name"]
    # (supplier_id, material_id) -> [(po_id, qty, where)]: capacity already given to other POs
    booked = {k: [(pid, q, f"an earlier disruption ({lab})") for pid, q, lab in v]
              for k, v in (booked_before or {}).items()}
    chosen = []
    for po in pos.itertuples():
        opts = _options(po, today, tables, down_days, spare)
        best = min(opts, key=lambda o: (_score(o, po, weights), o["extra_cost"]))
        # only blame capacity when it changed the decision: with unlimited spare, would we switch to a full supplier?
        free = _options(po, today, tables, down_days, {k: float("inf") for k in spare})
        ideal = min(free, key=lambda o: (_score(o, po, weights), o["extra_cost"]))
        note = (_capacity_note(po, sm, spare, booked, sup_names, only=ideal["alt_supplier_id"])
                if ideal["action"] == "switch" and best["alt_supplier_id"] != ideal["alt_supplier_id"] else "")
        if best["action"] == "switch":
            spare[(best["alt_supplier_id"], po.material_id)] -= po.qty
            booked.setdefault((best["alt_supplier_id"], po.material_id), []).append((po.po_id, int(po.qty), ""))
        chosen.append({
            "po_id": po.po_id, "sales_order_id": po.for_sales_order_id, "so_priority": po.so_priority,
            "material": po.material, "qty": int(po.qty), "from_supplier": po.supplier,
            "action": best["action"],
            "to_supplier": sup_names.get(best["alt_supplier_id"], "") if best["alt_supplier_id"] else "",
            "delay_before": int(po.delay_days), "delay_after": best["delay_days"],
            "so_late_after": best["so_late_days"], "extra_cost": best["extra_cost"],
            "value": float(po.value), "options_considered": len(opts),
            "capacity_note": note,
        })
    actions = pd.DataFrame(chosen)
    return {"name": name, "actions": actions, "totals": _totals(impact, actions)}


def _totals(impact, actions) -> dict:
    """Plan outcome against doing nothing: order-days late, high-priority orders kept on time, and cost."""
    sos = impact["sales_orders"]
    base = int(sos["late_days"].sum()) if len(sos) else 0
    hp_ids = set(sos[sos["priority"] == "High"]["sales_order_id"]) if len(sos) else set()
    cost_if_wait = float(impact["summary"].get("cost_increase_if_wait", 0.0))
    if actions.empty:
        return {"extra_cost": cost_if_wait, "cost_if_wait": cost_if_wait, "cost_avoided": 0.0,
                "late_days_before": base, "late_days_after": base, "delay_avoided_days": 0,
                "sales_orders_late_after": len(sos), "high_priority_affected": len(hp_ids),
                "high_priority_protected": 0, "pos_changed": 0}
    # every customer order a PO feeds, including any a switch would newly make late
    per_so = actions.groupby("sales_order_id")["so_late_after"].max().astype(float)
    extra = round(float(actions["extra_cost"].sum()), 2)
    return {
        "extra_cost": extra,
        "cost_if_wait": round(cost_if_wait, 2),
        "cost_avoided": round(cost_if_wait - extra, 2),
        "late_days_before": base,
        "late_days_after": int(per_so.sum()),
        "delay_avoided_days": base - int(per_so.sum()),
        "sales_orders_late_after": int((per_so > 0).sum()),
        "high_priority_affected": len(hp_ids),
        "high_priority_protected": sum(1 for so in hp_ids if per_so.get(so, 0) == 0),
        "pos_changed": int((actions["action"] != "wait").sum()),
    }


def build_plans(impact: dict, tables, booked_before: dict | None = None) -> list:
    plans = [build_plan(impact, tables, name, w, booked_before) for name, w in PLAN_WEIGHTS.items()]
    for p in plans:
        p["recommended"] = p["name"] == "Balanced"
    return plans
