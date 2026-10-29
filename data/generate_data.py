"""Generate a synthetic supplier network for a mock two-wheeler EV maker.

Run:  python data/generate_data.py
Writes CSV files into data/ that the rest of ReRoute loads into SQLite or SAP HANA Cloud.

Everything here is invented demo data. Column names for purchase orders follow
S/4HANA field meanings (see reroute/s4_sandbox.py for the mapping).
"""
import csv
import random
from datetime import date, timedelta
from pathlib import Path

random.seed(42)
OUT = Path(__file__).parent
AS_OF = date.today()

# ---------------------------------------------------------------- locations
CITIES = {
    "Bidadi":     ("Karnataka",   12.7967, 77.3842),
    "Hosur":      ("Tamil Nadu",  12.7409, 77.8253),
    "Coimbatore": ("Tamil Nadu",  11.0168, 76.9558),
    "Chennai":    ("Tamil Nadu",  12.9675, 79.9419),
    "Bengaluru":  ("Karnataka",   13.0285, 77.5197),
    "Mysuru":     ("Karnataka",   12.2958, 76.6394),
    "Tumakuru":   ("Karnataka",   13.3379, 77.1173),
    "Madurai":    ("Tamil Nadu",   9.9252, 78.1198),
    "Pune":       ("Maharashtra", 18.7603, 73.8630),
    "Manesar":    ("Haryana",     28.3540, 76.9400),
    "Nhava Sheva": ("Maharashtra", 18.9490, 72.9512),   # JNPT container port, no suppliers here
}

# ---------------------------------------------------------------- materials
# id, name, unit, plant cover (days of stock at the plant)
MATERIALS = [
    ("M01", "Aluminium wheel casting", "pcs", 3),
    ("M02", "Brake assembly", "sets", 4),
    ("M03", "Wiring harness", "pcs", 3),
    ("M04", "Hub motor", "pcs", 3),
    ("M05", "Battery pack", "pcs", 3),
    ("M06", "Controller PCB", "pcs", 5),
    ("M07", "Chassis frame", "pcs", 3),
    ("M08", "Tyre set", "sets", 6),
    # inputs used by Tier-1 suppliers (never ordered by the plant directly)
    ("M20", "Aluminium ingot", "kg", 0),
    ("M21", "Copper wire", "kg", 0),
    ("M22", "NdFeB magnets", "pcs", 0),
    ("M23", "Li-ion cells", "pcs", 0),
]

PRODUCTS = [
    ("P1", "Scooter S1"),
    ("P2", "Scooter S2 Pro"),
    ("P3", "Motorcycle M1"),
]

BOM = [  # product, material, qty per unit
    ("P1", "M01", 2), ("P1", "M02", 1), ("P1", "M03", 1), ("P1", "M04", 1), ("P1", "M05", 1), ("P1", "M06", 1), ("P1", "M07", 1), ("P1", "M08", 1),
    ("P2", "M01", 2), ("P2", "M02", 1), ("P2", "M03", 1), ("P2", "M04", 1), ("P2", "M05", 2), ("P2", "M06", 1), ("P2", "M07", 1), ("P2", "M08", 1),
    ("P3", "M01", 2), ("P3", "M02", 2), ("P3", "M03", 1), ("P3", "M04", 1), ("P3", "M05", 2), ("P3", "M06", 1), ("P3", "M07", 1), ("P3", "M08", 1),
]

# ---------------------------------------------------------------- suppliers
# id, name, tier, city, buffer_days (input stock a supplier holds), is_msme
SUPPLIERS = [
    ("S01", "Hosur Precision Castings", 1, "Hosur", 3, True),
    ("S02", "Coimbatore Alloy Works", 1, "Coimbatore", 3, True),
    ("S03", "Pune Foundry Ltd", 1, "Pune", 5, False),
    ("S04", "Chennai Brake Systems", 1, "Chennai", 4, False),
    ("S05", "Mysuru Brakes & Clutches", 1, "Mysuru", 3, True),
    ("S06", "Hosur Harness Co", 1, "Hosur", 2, True),
    ("S07", "Tumakuru Wiring Pvt Ltd", 1, "Tumakuru", 3, True),
    ("S08", "Bengaluru E-Motors", 1, "Bengaluru", 4, False),
    ("S09", "Manesar Motor Tech", 1, "Manesar", 6, False),
    ("S10", "Chennai Cell Packs", 1, "Chennai", 3, False),
    ("S11", "Bengaluru PCB Assembly", 1, "Bengaluru", 6, True),
    ("S12", "Hosur Frames & Fabrication", 1, "Hosur", 2, True),
    ("S13", "Madurai Steel Frames", 1, "Madurai", 3, True),
    ("S14", "Chennai Tyres", 1, "Chennai", 7, False),
    ("S15", "Pune Battery Systems", 1, "Pune", 4, False),   # backup battery maker, domestic cells
    # Tier-2
    ("S20", "Hosur Aluminium Smelters", 2, "Hosur", 0, True),
    ("S21", "Coimbatore Copper Drawing", 2, "Coimbatore", 0, True),
    ("S22", "Pune Magnetics", 2, "Pune", 0, True),
    ("S23", "Chennai Cell Imports", 2, "Chennai", 0, False),
]

# supplier, material, unit price (INR), lead days, weekly capacity, spare capacity share
SUPPLY = [
    ("S01", "M01", 1450, 3, 1400, 0.10), ("S02", "M01", 1560, 2, 1100, 0.55), ("S03", "M01", 1520, 6, 1500, 0.40),
    ("S04", "M02", 2100, 3, 900, 0.30), ("S05", "M02", 2180, 2, 700, 0.45),
    ("S06", "M03", 980, 2, 900, 0.15), ("S07", "M03", 1040, 2, 700, 0.50),
    ("S08", "M04", 8900, 3, 600, 0.20), ("S09", "M04", 9300, 8, 800, 0.50),
    ("S10", "M05", 21500, 4, 650, 0.25), ("S15", "M05", 22800, 3, 1200, 0.50),
    ("S11", "M06", 3200, 3, 900, 0.35),
    ("S12", "M07", 4100, 2, 520, 0.10), ("S13", "M07", 4350, 3, 450, 0.45),
    ("S14", "M08", 2600, 3, 900, 0.40),
    ("S20", "M20", 260, 2, 30000, 0.20),
    ("S21", "M21", 820, 3, 8000, 0.30),
    ("S22", "M22", 140, 5, 40000, 0.10),
    ("S23", "M23", 310, 6, 60000, 0.20),
]

# tier-2 supplier -> tier-1 supplier, input material,
# share = how much of the tier-1's input comes from this tier-2,
# cost_share = how much of the tier-1's product cost that input represents (drives tariff pass-through)
LINKS = [
    ("S20", "S01", "M20", 0.85, 0.45), ("S20", "S02", "M20", 0.30, 0.45), ("S20", "S12", "M20", 0.40, 0.30),
    ("S21", "S06", "M21", 0.70, 0.40), ("S21", "S07", "M21", 0.60, 0.40), ("S21", "S08", "M21", 0.50, 0.15),
    ("S22", "S08", "M22", 0.90, 0.25), ("S22", "S09", "M22", 0.40, 0.25),
    ("S23", "S10", "M23", 0.95, 0.60),
]

# suppliers that import their input, and the port it arrives through (port closures, tariffs)
IMPORT_PORT = {"S23": "Chennai", "S22": "Nhava Sheva"}

# who is the plant's usual (primary) supplier for each material
PRIMARY = {"M01": "S01", "M02": "S04", "M03": "S06", "M04": "S08", "M05": "S10",
           "M06": "S11", "M07": "S12", "M08": "S14"}

CUSTOMERS = ["Kaveri Motors (dealer)", "Deccan EV Fleet", "QuickDrop Logistics", "Namma Rides",
             "Coastal Auto Dealers", "GreenMile Delivery", "Metro Two-Wheelers", "Govt e-Mobility Tender"]


def write(name, header, rows):
    with open(OUT / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def main():
    write("meta", ["key", "value"], [("as_of", AS_OF.isoformat()), ("plant", "Bidadi"),
                                     ("company", "Kaveri EV Motors (demo)")])
    write("cities", ["city", "state", "lat", "lon"], [(c, s, la, lo) for c, (s, la, lo) in CITIES.items()])
    write("materials", ["material_id", "name", "unit", "plant_cover_days"], MATERIALS)
    write("products", ["product_id", "name"], PRODUCTS)
    write("bom", ["product_id", "material_id", "qty_per_unit"], BOM)

    sup_rows = []
    for sid, name, tier, city, buf, msme in SUPPLIERS:
        state, lat, lon = CITIES[city]
        sup_rows.append((sid, name, tier, city, state, lat, lon, buf, int(msme), IMPORT_PORT.get(sid, "")))
    write("suppliers", ["supplier_id", "name", "tier", "city", "state", "lat", "lon", "buffer_days", "is_msme",
                        "import_port"], sup_rows)
    write("supplier_materials", ["supplier_id", "material_id", "unit_price", "lead_days", "weekly_capacity", "spare_share"], SUPPLY)
    write("supplier_links", ["child_supplier_id", "parent_supplier_id", "input_material_id", "share", "cost_share"], LINKS)

    # ---- sales orders over the next 28 days
    sos = []
    weights = {"P1": 60, "P2": 25, "P3": 15}
    for i in range(1, 41):
        product = random.choices(list(weights), weights=list(weights.values()))[0]
        due = AS_OF + timedelta(days=random.randint(3, 28))
        qty = random.choice([40, 60, 80, 100, 120, 150, 200])
        priority = random.choices(["High", "Medium", "Low"], weights=[25, 45, 30])[0]
        sos.append((f"SO{4500 + i}", random.choice(CUSTOMERS), product, qty, due.isoformat(), priority))
    sos.sort(key=lambda r: r[4])
    write("sales_orders", ["sales_order_id", "customer", "product_id", "qty", "due_date", "priority"], sos)

    # ---- purchase orders: each sales order pulls material POs from primary suppliers
    # due 2 days before the sales order (assembly time), with a little noise
    pos = []
    n = 0
    for so_id, _, product, qty, due, _ in sos:
        for p, m, per in BOM:
            if p != product:
                continue
            n += 1
            sid = PRIMARY[m]
            price = next(s[2] for s in SUPPLY if s[0] == sid and s[1] == m)
            po_due = date.fromisoformat(due) - timedelta(days=2 + random.choice([0, 0, 1]))
            pos.append((f"45000{n:05d}", sid, m, qty * per, price, AS_OF.isoformat(), po_due.isoformat(), so_id, "Open"))
    write("purchase_orders", ["po_id", "supplier_id", "material_id", "qty", "unit_price", "order_date", "due_date",
                              "for_sales_order_id", "status"], pos)
    print(f"Wrote {len(sup_rows)} suppliers, {len(sos)} sales orders, {len(pos)} purchase orders (as of {AS_OF}) to {OUT}")


if __name__ == "__main__":
    main()
