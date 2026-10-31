"""Stage 1 - Detect: turn a supplier report, news item or IMD alert into a disruption event,
then find which suppliers it touches.

classify_text() asks Generative AI Hub first and falls back to keyword rules offline.
"""
import math
import re
import uuid
from dataclasses import asdict, dataclass, field

from . import llm

EVENT_TYPES = ["flood", "strike", "fire", "power", "port", "tariff", "transport", "equipment", "none"]

# km from the event location within which a supplier counts as hit (port and tariff events match differently)
RADIUS_KM = {"flood": 35, "strike": 25, "fire": 3, "power": 15, "transport": 30, "equipment": 0, "port": 0, "tariff": 0}
DEFAULT_DAYS = {"flood": 4, "strike": 2, "fire": 7, "power": 1, "transport": 2, "equipment": 3, "port": 4, "tariff": 0}

# words that name an imported input, for tariff events
MATERIAL_WORDS = {"M23": ["lithium", "li-ion", "battery cell", "cells"], "M22": ["magnet", "rare earth", "rare-earth", "ndfeb"],
                  "M20": ["aluminium", "aluminum"], "M21": ["copper"]}

KEYWORDS = {
    # port and tariff come first so they win ties against the generic transport words
    "port": ["port closure", "port closed", "port shut", "terminal operations suspended", "port operations suspended",
             "terminal closed", "shipping suspended", "vessels diverted", "port authority", "port gates",
             "port blocked"],
    "tariff": ["tariff", "import duty", "customs duty", "anti-dumping", "duty hike", "countervailing duty", "safeguard duty",
               "levy"],
    "flood": ["flood", "waterlog", "water-logged", "heavy rain", "extremely heavy rainfall", "inundat", "cyclone",
              "red alert", "orange alert", "deluge", "submerged", "overflow", "downpour", "knee-deep", "cloudburst"],
    "strike": ["strike", "bandh", "agitation", "walkout", "lockout", "go-slow"],
    "fire": ["fire", "blaze", "explosion", "blast"],
    "power": ["power cut", "power shutdown", "power outage", "outage", "load shedding", "grid failure"],
    "transport": ["landslide", "highway blocked", "road closed", "held at port", "port congestion",
                  "customs", "bridge collapse", "suspend operations"],
    "equipment": ["breakdown", "machine failure", "furnace", "line down"],
}
NEGATIONS = ["no warnings", "no warning issued", "light to moderate", "called off", "calls off", "call off",
             "withdraw", "mock drill", "safety drill", "no impact on production", "no disruption expected"]
HIGH_WORDS = ["halted", "shut", "suspended", "indefinite", "red alert", "destroyed", "submerged", "extremely"]

ALIASES = {"bangalore": "Bengaluru", "peenya": "Bengaluru", "sriperumbudur": "Chennai", "kancheepuram": "Chennai",
           "ennore": "Chennai", "chakan": "Pune", "kovai": "Coimbatore", "mysore": "Mysuru", "tumkur": "Tumakuru",
           "gurugram": "Manesar", "gurgaon": "Manesar", "krishnagiri": "Hosur", "sipcot": "Hosur",
           "jnpt": "Nhava Sheva", "jawaharlal nehru port": "Nhava Sheva", "madras": "Chennai",
           "kanchipuram": "Chennai", "oragadam": "Chennai", "irungattukottai": "Chennai"}
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
                "ten": 10, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "forty-eight": 48, "seventy-two": 72}
STATES = ["Tamil Nadu", "Karnataka", "Maharashtra", "Haryana"]


@dataclass
class Event:
    event_id: str
    source: str                      # supplier_report | news | imd
    text: str
    relevant: bool
    event_type: str
    severity: int                    # 1 (minor) .. 5 (severe)
    duration_days: int
    location: str = ""               # city, if known
    state: str = ""
    scope: str = "city"              # site | city | state | port | national
    supplier_ids: list = field(default_factory=list)   # named explicitly in the signal
    confidence: float = 0.6
    method: str = "rules"            # llm | rules | report
    matched: list = field(default_factory=list)        # filled by match_suppliers()
    material_ids: list = field(default_factory=list)   # tariff events: the imported inputs affected
    cost_pct: float = 0.0                              # tariff events: rise in landed cost, percentage points

    def to_dict(self):
        return asdict(self)


def _new_id() -> str:
    return "EV-" + uuid.uuid4().hex[:6].upper()


# ------------------------------------------------------------------ rules
def _find_city(text: str, cities) -> str:
    low = text.lower()
    for c in cities:
        if c.lower() in low:
            return c
    for alias, city in ALIASES.items():
        if alias in low:
            return city
    return ""


def _find_suppliers(text: str, suppliers) -> list:
    low = text.lower()
    hits = []
    for _, s in suppliers.iterrows():
        name = s["name"].lower()
        short = " ".join(name.split()[:2])
        # full name, or its first two words when those are unique ("Chennai Cell ..." is shared by two)
        if name in low or (len(short) > 8 and short in low and short.split()[1] != "cell"):
            hits.append(s["supplier_id"])
    return hits


def _duration(text: str, event_type: str) -> int:
    low = text.lower()
    # "three days", "forty-eight hours" -> digits; longest words first so "forty-eight" beats "eight"
    for word in sorted(NUMBER_WORDS, key=len, reverse=True):
        low = re.sub(rf"\b{word}(?=[\s-]*(?:days?|hours?|hrs?|weeks?)\b)", str(NUMBER_WORDS[word]), low)
    m = re.search(r"(\d+)\s*(?:-|to)\s*(\d+)\s*days?", low)
    if m:
        return int(m.group(2))
    m = re.search(r"(\d+)\s*days?", low)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)[\s-]*(?:hours?|hrs?)\b", low)
    if m:
        return max(1, math.ceil(int(m.group(1)) / 24))
    m = re.search(r"(\d+)\s*weeks?", low)
    if m:
        return 7 * int(m.group(1))
    if "fortnight" in low:
        return 14
    if "a week" in low:
        return 7
    if re.search(r"\ba day\b", low):
        return 1
    if "indefinite" in low:
        return 10
    return DEFAULT_DAYS.get(event_type, 2)


def _tariff_details(text: str) -> tuple:
    """Which imported inputs a tariff names, and by how many percentage points their duty rises."""
    low = text.lower()
    mats = [m for m, words in MATERIAL_WORDS.items() if any(w in low for w in words)]
    m = re.search(r"from\s*(\d+(?:\.\d+)?)\s*%\s*to\s*(\d+(?:\.\d+)?)\s*%", low)
    if m:
        pct = float(m.group(2)) - float(m.group(1))
    else:
        nums = re.findall(r"(\d+(?:\.\d+)?)\s*%", low)
        pct = float(nums[-1]) if nums else 10.0
    return mats, max(0.0, pct)


def classify_rules(text: str, tables) -> dict:
    low = text.lower()
    scores = {t: sum(k in low for k in kws) for t, kws in KEYWORDS.items()}
    event_type = max(scores, key=scores.get)
    if scores[event_type] == 0 or any(n in low for n in NEGATIONS):
        event_type = "none"
    city = _find_city(text, list(tables["cities"]["city"]))
    state = next((s for s in STATES if s.lower() in low), "")
    if city and not state:
        state = tables["cities"].set_index("city").loc[city, "state"]
    named = _find_suppliers(text, tables["suppliers"])
    statewide = any(w in low for w in ["statewide", "state-wide", "across the state", "across tamil nadu",
                                       "across karnataka", "nationwide"])
    scope = "site" if named else "state" if statewide else "city"
    severity = 2 + min(2, sum(w in low for w in HIGH_WORDS)) + (1 if scope == "state" else 0)
    mats, pct = [], 0.0
    if event_type == "port":
        scope, named = "port", []
    elif event_type == "tariff":
        mats, pct = _tariff_details(text)
        scope, named, city, state = "national", [], "", ""
        severity = 2 + (1 if pct >= 10 else 0) + (1 if pct >= 20 else 0)
    return {"relevant": event_type != "none", "event_type": event_type, "severity": min(5, severity),
            "duration_days": _duration(text, event_type), "location": city, "state": state,
            "scope": scope, "supplier_ids": named, "confidence": 0.6, "material_ids": mats, "cost_pct": pct}


# ------------------------------------------------------------------ LLM
SYSTEM = """You read short news items, weather alerts and supplier messages for an Indian manufacturer's
supply chain team. Decide if the text describes a disruption that could stop or slow a factory, warehouse
or transport. Answer ONLY with JSON:
{"relevant": true|false,
 "event_type": one of ["flood","strike","fire","power","port","tariff","transport","equipment","none"]
   ("port" = a seaport or container terminal closed; "tariff" = import duty or tariff change),
 "severity": 1-5,
 "duration_days": integer estimate (round hours up to 1 day),
 "location": the city or industrial area named, or "",
 "state": the Indian state, or "",
 "scope": "site" if one company or plant, "state" if statewide or nationwide, "port" for a port closure,
   "national" for a tariff, else "city",
 "supplier_names": [company names mentioned, exactly as written],
 "confidence": 0-1}"""


def classify_llm(text: str, tables):
    out = llm.chat_json([{"role": "system", "content": SYSTEM}, {"role": "user", "content": text}])
    if not out or "event_type" not in out:
        return None
    if out["event_type"] not in EVENT_TYPES:
        out["event_type"] = "none"
    # map the model's free-text location and supplier names onto our master data
    out["location"] = _find_city(out.get("location", "") or text, list(tables["cities"]["city"]))
    names = " | ".join(out.get("supplier_names", []) or [])
    out["supplier_ids"] = _find_suppliers(names, tables["suppliers"]) if names else []
    if out["supplier_ids"]:
        out["scope"] = "site"
    out["material_ids"], out["cost_pct"] = [], 0.0
    if out["event_type"] == "port":
        out["scope"], out["supplier_ids"] = "port", []
    if out["event_type"] == "tariff":
        # which inputs and how big a rise: parsed deterministically, never left to the model
        out["material_ids"], out["cost_pct"] = _tariff_details(text)
        out["scope"], out["supplier_ids"], out["duration_days"] = "national", [], 0
    days = out.get("duration_days")
    out["duration_days"] = 0 if out["event_type"] == "tariff" else max(1, int(days or DEFAULT_DAYS.get(out["event_type"], 2)))
    out["severity"] = int(out.get("severity") or 3)
    out["relevant"] = bool(out.get("relevant")) and out["event_type"] != "none"
    return out


def classify_text(text: str, tables, source: str = "news", use_llm: bool = True) -> Event:
    result, method = (classify_llm(text, tables), "llm") if use_llm and llm.available() else (None, "")
    if result is None:
        result, method = classify_rules(text, tables), "rules"
    keys = ["relevant", "event_type", "severity", "duration_days", "location", "state", "scope", "supplier_ids",
            "confidence", "material_ids", "cost_pct"]
    return Event(event_id=_new_id(), source=source, text=text, method=method, **{k: result[k] for k in keys})


def event_from_report(report: dict, tables) -> Event:
    """A supplier told us directly (mobile form / API): no guessing needed."""
    s = tables["suppliers"].set_index("supplier_id").loc[report["supplier_id"]]
    text = f'{s["name"]} reports {report["issue_type"]}: {report.get("note", "")}'.strip()
    issue = report["issue_type"] if report["issue_type"] in EVENT_TYPES else "equipment"
    return Event(event_id=_new_id(), source="supplier_report", text=text, relevant=True, event_type=issue,
                 severity=4, duration_days=int(report["days_down"]), location=s["city"], state=s["state"],
                 scope="site", supplier_ids=[report["supplier_id"]], confidence=1.0, method="report")


# ------------------------------------------------------------------ geo-matching
def haversine_km(lat1, lon1, lat2, lon2) -> float:
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 12742 * math.asin(math.sqrt(a))


def match_suppliers(event: Event, tables) -> Event:
    """Fill event.matched with [{supplier_id, distance_km, reason}]."""
    sup = tables["suppliers"]
    matched = []
    if not event.relevant:
        event.matched = []
        return event
    imports = {r.supplier_id: r.import_port for r in sup.itertuples() if getattr(r, "import_port", None)}
    if event.event_type == "port":
        # a port closure hits the suppliers whose imports arrive through that port, wherever they are
        matched = [{"supplier_id": sid, "distance_km": None, "reason": f"imports through {port} port"}
                   for sid, port in imports.items() if event.location and port == event.location]
    elif event.event_type == "tariff":
        # a tariff hits the importers of the named inputs
        sm = tables["supplier_materials"]
        makers = set(sm[sm["material_id"].isin(event.material_ids)]["supplier_id"])
        names = tables["materials"].set_index("material_id")["name"]
        matched = [{"supplier_id": sid, "distance_km": None,
                    "reason": f"imports {', '.join(names[m].lower() for m in event.material_ids)}"}
                   for sid in imports if sid in makers]
    elif event.scope == "site" and event.supplier_ids:
        matched = [{"supplier_id": sid, "distance_km": 0.0, "reason": "named in the signal"} for sid in event.supplier_ids]
    elif event.scope == "state" and event.state:
        matched = [{"supplier_id": r.supplier_id, "distance_km": None, "reason": f"statewide event in {event.state}"}
                   for r in sup.itertuples() if r.state == event.state]
    elif event.location:
        c = tables["cities"].set_index("city").loc[event.location]
        radius = RADIUS_KM.get(event.event_type, 20)
        for r in sup.itertuples():
            d = haversine_km(c["lat"], c["lon"], r.lat, r.lon)
            if d <= radius:
                matched.append({"supplier_id": r.supplier_id, "distance_km": round(d, 1),
                                "reason": f"within {radius} km of {event.location}"})
    event.matched = matched
    return event
