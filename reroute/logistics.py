"""Shipping routes from suppliers to our plant, and a cost breakdown for each recovery plan.

Display only: the planner ranks plans on its own costs (price difference, 2% new-supplier checks,
8% expedite fee, higher duty) and never sees these shipping figures. Shipping is an estimate:
one truckload per purchase order, road distance = straight-line distance x ROAD_FACTOR, and the
per-km rates in config (set in .env). Say so wherever it is shown.
"""
import pandas as pd

from . import config
from .planner import EXPEDITE_COST_SHARE, SWITCH_ONBOARD_SHARE
from .signals import haversine_km


def plant(tables) -> dict:
    """Our plant: name and coordinates (the plant city in meta, e.g. Bidadi)."""
    name = tables["meta"].set_index("key").loc["plant", "value"]
    c = tables["cities"].set_index("city").loc[name]
    return {"name": name, "lat": float(c["lat"]), "lon": float(c["lon"])}


def road_km(tables, supplier_id: str) -> float:
    s = tables["suppliers"].set_index("supplier_id").loc[supplier_id]
    p = plant(tables)
    return round(haversine_km(float(s["lat"]), float(s["lon"]), p["lat"], p["lon"]) * config.ROAD_FACTOR, 1)


def freight(tables, supplier_id: str, express: bool = False) -> float:
    """Estimated cost of one truckload from a supplier to the plant."""
    rate = config.EXPRESS_FREIGHT_RS_PER_KM if express else config.FREIGHT_RS_PER_KM
    return round(road_km(tables, supplier_id) * rate, 2)


def _ids(tables) -> dict:
    return dict(zip(tables["suppliers"]["name"], tables["suppliers"]["supplier_id"]))


def plan_lines(tables, impact: dict, plan: dict) -> pd.DataFrame:
    """One row per purchase order in the plan, with its cost split into parts and its shipping route.

    price_difference + new_supplier_checks + expedite_fee + duty_if_waiting equals the planner's
    extra_cost for that row; shipping_change is the extra estimate on top.
    """
    acts = plan["actions"]
    if acts.empty:
        return pd.DataFrame()
    ids = _ids(tables)
    pos = impact["pos"].set_index("po_id")
    price = tables["supplier_materials"].set_index(["supplier_id", "material_id"])["unit_price"]
    rows = []
    for a in acts.itertuples():
        po = pos.loc[a.po_id]
        orig = ids[a.from_supplier]
        row = {"po_id": a.po_id, "action": a.action, "from_supplier_id": orig, "from_supplier": a.from_supplier,
               "to_supplier_id": orig, "to_supplier": a.from_supplier, "qty": int(a.qty),
               "price_difference": 0.0, "new_supplier_checks": 0.0, "expedite_fee": 0.0, "duty_if_waiting": 0.0,
               "km_before": road_km(tables, orig), "km_after": road_km(tables, orig), "shipping_change": 0.0,
               "planner_extra_cost": float(a.extra_cost)}
        if a.action == "switch":
            alt = ids[a.to_supplier]
            row.update(to_supplier_id=alt, to_supplier=a.to_supplier, km_after=road_km(tables, alt),
                       price_difference=round(int(a.qty) * (float(price.loc[(alt, po["material_id"])])
                                                           - float(po["unit_price"])), 2),
                       new_supplier_checks=round(float(a.value) * SWITCH_ONBOARD_SHARE, 2),
                       shipping_change=round(freight(tables, alt) - freight(tables, orig), 2))
        elif a.action == "expedite":
            row.update(expedite_fee=round(float(a.value) * EXPEDITE_COST_SHARE, 2),
                       shipping_change=round(freight(tables, orig, express=True) - freight(tables, orig), 2))
        else:  # wait: after a tariff, waiting means paying the higher duty
            row.update(duty_if_waiting=float(a.extra_cost))
        rows.append(row)
    return pd.DataFrame(rows)


PARTS = [("price_difference", "Product price difference (new supplier)"),
         ("new_supplier_checks", f"New-supplier logistics and checks ({SWITCH_ONBOARD_SHARE:.0%} of PO value)"),
         ("expedite_fee", f"Expedite fee: overtime and priority handling ({EXPEDITE_COST_SHARE:.0%} of PO value)"),
         ("duty_if_waiting", "Higher import duty on orders that stay")]


def cost_breakdown(tables, impact: dict, plan: dict) -> dict:
    """Totals for one plan: the planner's parts, the shipping estimate, and the total including shipping."""
    lines = plan_lines(tables, impact, plan)
    parts = {k: round(float(lines[k].sum()), 2) if len(lines) else 0.0 for k, _ in PARTS}
    planner_total = round(float(plan["totals"]["extra_cost"]), 2)
    shipping = round(float(lines["shipping_change"].sum()), 2) if len(lines) else 0.0
    return {**parts, "planner_extra_cost": planner_total, "shipping_change": shipping,
            "total_with_shipping": round(planner_total + shipping, 2)}


def breakdown_table(b: dict, inr) -> pd.DataFrame:
    """The breakdown as rows for display; zero parts are left out. inr formats rupees."""
    rows = [{"Cost": label, "Amount": inr(b[k])} for k, label in PARTS if abs(b[k]) >= 0.5]
    rows.append({"Cost": "Extra cost used to rank plans", "Amount": inr(b["planner_extra_cost"])})
    rows.append({"Cost": "Shipping change (estimate: one truck per PO, "
                         f"Rs {config.FREIGHT_RS_PER_KM:.0f}/km standard, Rs {config.EXPRESS_FREIGHT_RS_PER_KM:.0f}/km express)",
                 "Amount": inr(b["shipping_change"])})
    rows.append({"Cost": "Total including shipping", "Amount": inr(b["total_with_shipping"])})
    return pd.DataFrame(rows)


def routes(tables, impact: dict, plan: dict | None) -> pd.DataFrame:
    """Lines to draw on the map: each disrupted original route, and the routes the plan would use instead.

    kind: original (supplier at risk -> plant), switch (new supplier -> plant), expedite (same route, express).
    """
    p = plant(tables)
    sup = tables["suppliers"].set_index("supplier_id")
    out = []

    def leg(sid, kind, label):
        s = sup.loc[sid]
        out.append({"kind": kind, "supplier_id": sid, "from_lat": float(s["lat"]), "from_lon": float(s["lon"]),
                    "to_lat": p["lat"], "to_lon": p["lon"], "km": road_km(tables, sid), "label": label})

    for sid, n in impact["pos"].groupby("supplier_id").size().items():
        leg(sid, "original", f"{sup.loc[sid, 'name']} → {p['name']}: original route, {n} PO(s) late")
    if plan is not None:
        lines = plan_lines(tables, impact, plan)
        if len(lines):
            for (frm, to), g in lines[lines["action"] == "switch"].groupby(["from_supplier", "to_supplier_id"]):
                leg(to, "switch", f"{sup.loc[to, 'name']} → {p['name']}: replaces {frm} for {len(g)} PO(s)")
            for sid, g in lines[lines["action"] == "expedite"].groupby("from_supplier_id"):
                leg(sid, "expedite", f"{sup.loc[sid, 'name']} → {p['name']}: express shipment, {len(g)} PO(s)")
    return pd.DataFrame(out)
