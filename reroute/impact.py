"""Stage 2 - Trace: from disrupted suppliers to late purchase orders and late sales orders.

Model (simple on purpose, easy to explain to judges):
  1. A directly hit supplier is down for the event's duration.
  2. Downtime travels UP the tiers: a Tier-1 supplier that buys an input from a disrupted Tier-2
     supplier is down for (child downtime - its own buffer stock days), scaled by the share of the
     input that child provides when that share is under 50%.
  3. A purchase order from a down supplier, due before the supplier restarts, arrives the day after
     restart. Delay = new arrival - due date.
  4. A sales order is late by the largest PO delay among its materials, minus the days of stock the
     plant holds for that material.
"""
import math
from datetime import date, timedelta

import pandas as pd

RESTART_LAG_DAYS = 1     # a supplier needs a day after reopening before goods ship
PRIORITY_WEIGHT = {"High": 1.0, "Medium": 0.5, "Low": 0.2}


def as_of(tables) -> date:
    meta = dict(zip(tables["meta"]["key"], tables["meta"]["value"]))
    return date.fromisoformat(meta["as_of"])


def propagate_downtime(direct: dict, tables) -> pd.DataFrame:
    """direct = {supplier_id: days_down}. Returns one row per supplier that is down, with the path."""
    sup = tables["suppliers"].set_index("supplier_id")
    down = {sid: {"days": int(d), "via": "hit directly"} for sid, d in direct.items() if d > 0}
    links = tables["supplier_links"]
    for _ in range(3):  # tiers 3 -> 2 -> 1
        for l in links.itertuples():
            if l.child_supplier_id not in down:
                continue
            child_days = down[l.child_supplier_id]["days"]
            effective = child_days - int(sup.loc[l.parent_supplier_id, "buffer_days"])
            if l.share < 0.5:
                effective = math.ceil(effective * l.share)
            if effective > down.get(l.parent_supplier_id, {"days": 0})["days"]:
                mat = tables["materials"].set_index("material_id").loc[l.input_material_id, "name"]
                down[l.parent_supplier_id] = {
                    "days": effective,
                    "via": f"via {sup.loc[l.child_supplier_id, 'name']} ({mat.lower()}, {int(l.share * 100)}% of input)"}
    rows = [{"supplier_id": sid, "name": sup.loc[sid, "name"], "tier": int(sup.loc[sid, "tier"]),
             "city": sup.loc[sid, "city"], "days_down": v["days"], "via": v["via"]} for sid, v in down.items()]
    return pd.DataFrame(rows, columns=["supplier_id", "name", "tier", "city", "days_down", "via"])


COST_HORIZON_DAYS = 28   # a tariff hits every open order due in the next four weeks


def propagate_cost(direct_pct: dict, tables) -> pd.DataFrame:
    """direct_pct = {supplier_id: % rise in its own cost}. The rise passes up the tiers, scaled by how much of
    the buyer's input comes from that supplier (share) and how much of the buyer's product cost it is (cost_share)."""
    sup = tables["suppliers"].set_index("supplier_id")
    names = tables["materials"].set_index("material_id")["name"]
    up = {sid: {"pct": float(p), "via": "pays the higher import duty"} for sid, p in direct_pct.items() if p > 0}
    for _ in range(3):
        for l in tables["supplier_links"].itertuples():
            if l.child_supplier_id not in up:
                continue
            pct = up[l.child_supplier_id]["pct"] * float(l.share) * float(l.cost_share)
            if pct > up.get(l.parent_supplier_id, {"pct": 0})["pct"]:
                up[l.parent_supplier_id] = {
                    "pct": pct,
                    "via": f"via {sup.loc[l.child_supplier_id, 'name']} ({names[l.input_material_id].lower()}, "
                           f"{int(round(l.cost_share * 100))}% of its product cost)"}
    rows = [{"supplier_id": sid, "name": sup.loc[sid, "name"], "tier": int(sup.loc[sid, "tier"]),
             "city": sup.loc[sid, "city"], "days_down": 0, "cost_increase_pct": round(v["pct"], 2), "via": v["via"]}
            for sid, v in up.items()]
    return pd.DataFrame(rows, columns=["supplier_id", "name", "tier", "city", "days_down", "cost_increase_pct", "via"])


def trace(event, tables) -> dict:
    """Late or costlier purchase orders and customer orders for one event.

    Downtime events (flood, strike, port closure ...) make orders late; tariff events make them cost more.
    Both return the same structure, so the planner and the UI treat them alike.
    """
    today = as_of(tables)
    kind = "cost" if event.event_type == "tariff" else "delay"
    po = tables["purchase_orders"].copy()
    po["due"] = pd.to_datetime(po["due_date"]).dt.date
    po = po[(po["status"] == "Open") & (po["due"] >= today)]

    if kind == "cost":
        down = propagate_cost({m["supplier_id"]: event.cost_pct for m in event.matched}, tables)
        pct = dict(zip(down["supplier_id"], down["cost_increase_pct"]))
        po = po[po["supplier_id"].isin(pct) & (po["due"] <= today + timedelta(days=COST_HORIZON_DAYS))].copy()
        po["restart"] = po["due"]
        po["new_arrival"] = po["due"]
        po["delay_days"] = pd.Series(0, index=po.index, dtype="int64")
        po["cost_increase_pct"] = po["supplier_id"].map(pct).astype(float)
    else:
        down = propagate_downtime({m["supplier_id"]: event.duration_days for m in event.matched}, tables)
        down["cost_increase_pct"] = 0.0
        days_down = dict(zip(down["supplier_id"], down["days_down"]))
        po = po[po["supplier_id"].isin(days_down)].copy()
        # row by row so an empty selection (no supplier hit) still works
        po["restart"] = [today + timedelta(days=int(days_down[s])) for s in po["supplier_id"]]
        po["new_arrival"] = [r + timedelta(days=RESTART_LAG_DAYS) for r in po["restart"]]
        po["delay_days"] = pd.Series([max(0, (n - d).days) for n, d in zip(po["new_arrival"], po["due"])],
                                     index=po.index, dtype="int64")
        po = po[po["delay_days"] > 0].copy()
        po["cost_increase_pct"] = 0.0

    mats = tables["materials"].set_index("material_id")
    sups = tables["suppliers"].set_index("supplier_id")
    so = tables["sales_orders"].set_index("sales_order_id")
    po["material"] = po["material_id"].map(mats["name"])
    po["supplier"] = po["supplier_id"].map(sups["name"])
    po["value"] = po["qty"] * po["unit_price"]
    po["extra_cost_wait"] = (po["value"] * po["cost_increase_pct"] / 100).round(2)
    po["cover_days"] = po["material_id"].map(mats["plant_cover_days"]).astype(int)
    po["so_priority"] = po["for_sales_order_id"].map(so["priority"])
    po["so_late_days"] = (po["delay_days"] - po["cover_days"]).clip(lower=0)

    sos = (po.groupby("for_sales_order_id")["so_late_days"].max().rename("late_days").reset_index()
             .rename(columns={"for_sales_order_id": "sales_order_id"}))
    sos = sos.merge(tables["sales_orders"], on="sales_order_id")
    sos = sos[sos["late_days"] > 0].sort_values(["priority", "due_date"],
                                                 key=lambda c: c.map({"High": 0, "Medium": 1, "Low": 2}) if c.name == "priority" else c)
    sos["product"] = sos["product_id"].map(tables["products"].set_index("product_id")["name"])

    po = po.sort_values(["due", "po_id"])
    summary = {
        "as_of": today.isoformat(),
        "kind": kind,
        "suppliers_down": len(down),
        "tier2_plus_down": int((down["tier"] >= 2).sum()) if len(down) else 0,
        "pos_at_risk": len(po),
        "po_value_at_risk": float(po["value"].sum()),
        "sales_orders_late": len(sos),
        "high_priority_late": int((sos["priority"] == "High").sum()),
        "baseline_late_days": int(sos["late_days"].sum()),
        "cost_increase_if_wait": round(float(po["extra_cost_wait"].sum()), 2),
    }
    return {"event": event, "down": down, "pos": po.reset_index(drop=True), "sales_orders": sos.reset_index(drop=True),
            "summary": summary}
