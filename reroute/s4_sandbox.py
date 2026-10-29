"""Pull sample purchase orders from the SAP S/4HANA Cloud sandbox on SAP Business Accelerator Hub.

Run:  python -m reroute.s4_sandbox
Needs in .env:
  S4_SANDBOX_API_KEY  api.sap.com -> log in -> open the API page -> Show API Key
  S4_SANDBOX_PO_URL   (optional) the full sandbox URL of the purchase order list, copied from the
                      API's "Try Out" page. Use it for the newer OData V4 Purchase Order API, e.g.
                      https://sandbox.api.sap.com/s4hanacloud/sap/opu/odata4/.../PurchaseOrder

Both the older OData V2 API (API_PURCHASEORDER_PROCESS_SRV, now deprecated) and the newer OData V4
successor are understood. The sandbox is read-only shared demo data: we use it to show the
integration and the field mapping, while the demo network itself is synthetic.

Field mapping, S/4HANA -> ReRoute purchase_orders (V2 name / V4 name):
  PurchaseOrder                          -> po_id
  Supplier                               -> supplier_id
  PurchaseOrderDate                      -> order_date
  to_PurchaseOrderItem / _PurchaseOrderItem:
    Material                             -> material_id
    OrderQuantity                        -> qty
    NetPriceAmount                       -> unit_price
    Plant                                -> (plant)
  to_ScheduleLine / _PurchaseOrderScheduleLine:
    ScheduleLineDeliveryDate             -> due_date
"""
import csv
import re
import sys
from datetime import datetime, timezone

import requests

from . import config

OUT = config.DATA_DIR / "s4_sandbox_pos.csv"


def _date(v) -> str:
    """V2 sends /Date(1730160000000)/, V4 sends 2024-10-29."""
    v = v or ""
    m = re.search(r"/Date\((\d+)", v)
    if m:
        return datetime.fromtimestamp(int(m.group(1)) / 1000, tz=timezone.utc).date().isoformat()
    return v[:10] if re.match(r"\d{4}-\d{2}-\d{2}", v) else ""


def _list(node) -> list:
    """V2 wraps lists as {"results": [...]}, V4 sends plain lists."""
    if isinstance(node, dict):
        return node.get("results", [])
    return node or []


def _first(d: dict, *keys):
    for k in keys:
        if k in d:
            return d[k]
    return None


def _get(url, params):
    r = requests.get(url, params=params, timeout=30,
                     headers={"APIKey": config.S4_SANDBOX_API_KEY, "Accept": "application/json"})
    r.raise_for_status()
    return r.json()


def fetch(top: int = 20) -> list:
    if not config.S4_SANDBOX_API_KEY:
        raise RuntimeError("Set S4_SANDBOX_API_KEY in .env first (see the build guide, Day 1 morning).")
    url = config.S4_SANDBOX_PO_URL or f"{config.S4_SANDBOX_BASE}/A_PurchaseOrder"
    v4 = "odata4" in url.lower()
    if v4:
        attempts = [{"$top": top, "$expand": "_PurchaseOrderItem($expand=_PurchaseOrderScheduleLine)"},
                    {"$top": top, "$expand": "_PurchaseOrderItem"},
                    {"$top": top}]
    else:
        attempts = [{"$top": top, "$expand": "to_PurchaseOrderItem,to_PurchaseOrderItem/to_ScheduleLine",
                     "$format": "json"},
                    {"$top": top, "$expand": "to_PurchaseOrderItem", "$format": "json"}]
    data, last_error = None, None
    for params in attempts:  # richest query first; fall back if the service rejects an expand
        try:
            data = _get(url, params)
            break
        except requests.HTTPError as e:
            last_error = e
            if e.response is None or e.response.status_code != 400:
                raise
    if data is None:
        raise last_error

    pos = data["value"] if "value" in data else data["d"]["results"]
    rows = []
    for po in pos:
        items = _list(_first(po, "_PurchaseOrderItem", "to_PurchaseOrderItem")) or [{}]
        for item in items:
            lines = _list(_first(item, "_PurchaseOrderScheduleLine", "to_ScheduleLine"))
            rows.append({
                "po_id": po.get("PurchaseOrder", ""), "supplier_id": po.get("Supplier", ""),
                "order_date": _date(po.get("PurchaseOrderDate")),
                "due_date": _date(lines[0].get("ScheduleLineDeliveryDate")) if lines else "",
                "item": item.get("PurchaseOrderItem", ""), "material_id": item.get("Material", ""),
                "description": item.get("PurchaseOrderItemText", ""), "qty": item.get("OrderQuantity", ""),
                "unit": item.get("PurchaseOrderQuantityUnit", ""), "unit_price": item.get("NetPriceAmount", ""),
                "currency": item.get("DocumentCurrency", "") or po.get("DocumentCurrency", ""),
                "plant": item.get("Plant", ""),
            })
    return rows


def main():
    try:
        rows = fetch()
    except Exception as e:
        print(f"Could not fetch from the sandbox: {e}")
        sys.exit(1)
    if not rows:
        print("The sandbox returned no purchase order items.")
        return
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"Saved {len(rows)} purchase order items from the S/4HANA sandbox to {OUT}")


if __name__ == "__main__":
    main()
