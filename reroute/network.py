"""The ReRoute agent network: six agents passing messages, with a human in the loop.

  Signals --> Sentinel --> Impact --> Sourcing --> Policy --+--> Execution --> Audit
                                                           |        ^
                                                           +--> Human planner (approve / reject)

Every message is delivered through one queue and written to a hash-chained audit log
(SAP HANA Cloud when connected), so the whole run can be replayed and checked.

In production each agent would be a Joule Studio agent calling the same functions as tools;
here they are small Python classes so the demo runs anywhere.
"""
import hashlib
import json
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import timedelta

from . import config, db, explain, impact, planner, signals

AGENTS = {
    "signals": ("Signals", "news · ports · tariffs · suppliers"),
    "sentinel": ("Sentinel", "detects disruptions"),
    "impact": ("Impact", "traces orders · HANA Cloud"),
    "sourcing": ("Sourcing", "ranks plans · Gen AI Hub"),
    "policy": ("Policy", "applies autonomy limits"),
    "planner": ("Human planner", "approves escalations"),
    "execution": ("Execution", "changes POs · S/4HANA API"),
    "audit": ("Audit", "hash-chained log · HANA"),
}


@dataclass
class Message:
    sender: str
    recipient: str
    kind: str
    summary: str
    data: dict = field(default_factory=dict)
    ts: str = ""
    seq: int = 0
    hash: str = ""


# ------------------------------------------------------------------ audit log
class AuditLog:
    """Append-only log where each record carries the hash of the one before it.

    Changing or deleting any stored record breaks every hash after it, which verify() detects.
    """

    def __init__(self, run_id: str, persist: bool = True):
        self.run_id, self.persist = run_id, persist
        self.records = []
        self.last_hash, self.next_seq = "GENESIS", 1
        if persist:
            db.ensure_runtime_tables()
            rows = db.read_rows("audit_log")
            if len(rows):
                rows = rows.sort_values("seq")
                self.last_hash = rows.iloc[-1]["hash"]
                self.next_seq = int(rows.iloc[-1]["seq"]) + 1

    @staticmethod
    def digest(prev: str, rec: dict) -> str:
        body = "|".join(str(rec[k]) for k in ["seq", "ts", "run_id", "sender", "recipient", "kind", "summary", "details"])
        return hashlib.sha256((prev + "|" + body).encode("utf-8")).hexdigest()

    def append(self, msg: Message) -> dict:
        details = json.dumps(msg.data, default=str)
        if len(details) > 4500:
            details = details[:4500] + "...(truncated)"
        rec = {"seq": f"{self.next_seq:08d}", "ts": msg.ts, "run_id": self.run_id, "sender": msg.sender,
               "recipient": msg.recipient, "kind": msg.kind, "summary": msg.summary[:1900], "details": details,
               "prev_hash": self.last_hash}
        rec["hash"] = self.digest(self.last_hash, rec)
        if self.persist:
            db.insert_row("audit_log", rec)
        self.records.append(rec)
        self.last_hash, self.next_seq = rec["hash"], self.next_seq + 1
        msg.seq, msg.hash = int(rec["seq"]), rec["hash"]
        return rec


def verify_audit(rows) -> dict:
    """Recompute the chain over stored audit rows. Returns {ok, records, broken_at}."""
    rows = rows.sort_values("seq") if len(rows) else rows
    prev = "GENESIS"
    for r in rows.to_dict("records"):
        if r["prev_hash"] != prev or AuditLog.digest(prev, r) != r["hash"]:
            return {"ok": False, "records": len(rows), "broken_at": r["seq"]}
        prev = r["hash"]
    return {"ok": True, "records": len(rows), "broken_at": None}


# ------------------------------------------------------------------ policy
def policy_decision(action: dict, extra_cost_wait: float) -> tuple:
    """Return (auto: bool, rule: str). Rules are deliberately few, so a judge can read them."""
    net = float(action["extra_cost"]) - float(extra_cost_wait)
    if action["so_priority"] == "High":
        return False, "Feeds a high-priority customer order"
    if net > config.AUTO_COST_LIMIT_INR:
        return False, f"Costs {explain.inr(net)} more than doing nothing (limit {explain.inr(config.AUTO_COST_LIMIT_INR)})"
    if action["action"] == "switch" and float(action["value"]) > config.BIG_SWITCH_LIMIT_INR:
        return False, (f"Moves {explain.inr(action['value'])} of business to another supplier "
                       f"(limit {explain.inr(config.BIG_SWITCH_LIMIT_INR)})")
    return True, "Within autonomy limits"


def s4_request(action: dict) -> dict:
    """The change Execution would send to the S/4HANA Purchase Order API (A2X, OData V4).

    Prepared, not sent: the public sandbox is read-only. With a real tenant this becomes the API call.
    """
    po = action["po_id"]
    if action["action"] == "switch":
        return {"method": "POST", "service": "Purchase Order (A2X, OData V4)", "entity": "PurchaseOrder",
                "body": {"Supplier": action.get("to_supplier_id", ""),
                         "_PurchaseOrderItem": [{"Material": action.get("material_id", ""),
                                                 "OrderQuantity": action["qty"]}]},
                "follow_up": f"Reduce the open quantity on PO {po} with the original supplier"}
    return {"method": "PATCH", "service": "Purchase Order (A2X, OData V4)",
            "entity": f"Schedule line of PO {po}",
            "body": {"ScheduleLineDeliveryDate": action.get("new_delivery_date", "")},
            "follow_up": "Express shipment agreed with the supplier"}


# ------------------------------------------------------------------ the network
class Network:
    def __init__(self, tables, persist: bool = True, use_llm: bool = True):
        self.tables, self.use_llm = tables, use_llm
        self.run_id = "RUN-" + uuid.uuid4().hex[:6].upper()
        self.audit = AuditLog(self.run_id, persist)
        self.persist = persist
        self.queue = deque()
        self.events = {}          # event_id -> {"event", "impact", "plans"}
        self.pending = {}         # action_id -> action awaiting a human
        self.claimed = {}         # po_id -> event_id that already acted on it in this run
        self.decided = []         # actions executed or rejected
        self.stats = {"messages": 0, "auto": 0, "approved": 0, "rejected": 0, "escalated": 0, "extra_cost": 0.0}
        self.handlers = {"sentinel": self._sentinel, "impact": self._impact, "sourcing": self._sourcing,
                         "policy": self._policy, "execution": self._execution}

    # ---- plumbing
    def send(self, sender, recipient, kind, summary, **data):
        self.queue.append(Message(sender, recipient, kind, summary, data))

    def inject(self, text: str, source: str = "news", label: str = ""):
        """A disruption signal arrives from outside the network."""
        self.send("signals", "sentinel", "signal.received", (f"{label}: " if label else "") + text,
                  text=text, source=source)

    def step(self):
        if not self.queue:
            return None
        msg = self.queue.popleft()
        msg.ts = db.now()
        self.audit.append(msg)
        self.stats["messages"] += 1
        handler = self.handlers.get(msg.recipient)
        if handler:
            handler(msg)
        return msg

    def run(self):
        """Deliver messages until the network is quiet; yields each one (for live display)."""
        while self.queue:
            yield self.step()

    def run_all(self):
        return list(self.run())

    # ---- agents
    def _sentinel(self, msg):
        ev = signals.classify_text(msg.data["text"], self.tables, source=msg.data.get("source", "news"),
                                   use_llm=self.use_llm)
        ev = signals.match_suppliers(ev, self.tables)
        if not ev.relevant or not ev.matched:
            self.send("sentinel", "audit", "signal.ignored",
                      f"Not a disruption for our network ({ev.event_type}, detected by {ev.method})",
                      event=ev.to_dict())
            return
        self.events[ev.event_id] = {"event": ev}
        names = self.tables["suppliers"].set_index("supplier_id")["name"]
        hit = ", ".join(names[m["supplier_id"]] for m in ev.matched[:3]) + (
            f" and {len(ev.matched) - 3} more" if len(ev.matched) > 3 else "")
        mats = self.tables["materials"].set_index("material_id")["name"]
        where = f"across {ev.state}" if ev.scope == "state" else f"at {ev.location}" if ev.location else ""
        label = {"port": "Port closure", "tariff": "Tariff spike", "power": "Power cut",
                 "transport": "Transport disruption", "equipment": "Breakdown"}.get(ev.event_type, ev.event_type.title())
        what = (f"{label}: import duty on {', '.join(mats[m].lower() for m in ev.material_ids)} up {ev.cost_pct:.0f} points"
                if ev.event_type == "tariff" else f"{label} {where}, about {ev.duration_days} days")
        self.send("sentinel", "impact", "disruption.detected", f"{what}. Hits {hit}.",
                  event_id=ev.event_id, event_type=ev.event_type, method=ev.method,
                  matched=[m["supplier_id"] for m in ev.matched])

    def _impact(self, msg):
        st = self.events[msg.data["event_id"]]
        imp = impact.trace(st["event"], self.tables)
        st["impact"] = imp
        s = imp["summary"]
        if s["kind"] == "cost":
            text = (f"{s['suppliers_down']} suppliers pay more; {s['pos_at_risk']} open POs would cost "
                    f"{explain.inr(s['cost_increase_if_wait'])} extra if we do nothing.")
        else:
            text = (f"{s['suppliers_down']} suppliers down ({s['tier2_plus_down']} Tier-2+); {s['pos_at_risk']} POs late; "
                    f"{s['sales_orders_late']} customer orders slip ({s['high_priority_late']} high-priority).")
        self.send("impact", "sourcing", "impact.assessed", text, event_id=msg.data["event_id"], impact_summary=s,
                  suppliers=imp["down"].to_dict("records"))

    def _sourcing(self, msg):
        eid = msg.data["event_id"]
        st = self.events[eid]
        if st["impact"]["summary"]["pos_at_risk"] == 0:
            self.send("sourcing", "audit", "plan.none", "Stock and lead times absorb this event; no PO changes.",
                      event_id=eid)
            return
        plans = planner.build_plans(st["impact"], self.tables)
        st["plans"] = plans
        rec = next(p for p in plans if p.get("recommended"))
        st["explanation"], method = explain.explain_plans(st["impact"], plans)
        t = rec["totals"]
        gain = (f"saves {explain.inr(t['cost_avoided'])} of {explain.inr(t['cost_if_wait'])}"
                if st["impact"]["summary"]["kind"] == "cost" else
                f"avoids {t['delay_avoided_days']} of {t['late_days_before']} order-days late for {explain.inr(t['extra_cost'])}")
        hp = (f"; {t['high_priority_protected']} of {t['high_priority_affected']} high-priority orders on time"
              if t["high_priority_affected"] else "")
        self.send("sourcing", "policy", "plan.proposed",
                  f"{rec['name']} plan: {t['pos_changed']} PO changes, {gain}{hp}.",
                  event_id=eid, plan=rec["name"], totals=t, explanation=st["explanation"], explained_by=method,
                  alternatives={p["name"]: p["totals"] for p in plans if not p.get("recommended")})

    def _policy(self, msg):
        eid = msg.data["event_id"]
        st = self.events[eid]
        rec = next(p for p in st["plans"] if p["name"] == msg.data["plan"])
        acts = rec["actions"]
        pos = st["impact"]["pos"].set_index("po_id")
        sm_ids = self.tables["suppliers"].set_index("name")["supplier_id"]
        waits = acts[acts["action"] == "wait"]
        if len(waits):
            kind = st["impact"]["summary"]["kind"]
            self.send("policy", "audit", "orders.monitored",
                      f"{len(waits)} POs stay as they are ("
                      + ("absorb the higher duty" if kind == "cost" else "stock covers the delay or it is cheapest to wait")
                      + "); Sentinel keeps watching.", event_id=eid, po_ids=list(waits["po_id"].astype(str)))
        for a in acts[acts["action"] != "wait"].to_dict("records"):
            row = pos.loc[a["po_id"]]
            a["po_id"] = str(a["po_id"])
            a["event_id"], a["plan"] = eid, rec["name"]
            a["material_id"] = str(row["material_id"])
            a["new_delivery_date"] = (row["due"] + timedelta(days=int(a["delay_after"]))).isoformat()
            a["to_supplier_id"] = sm_ids.get(a["to_supplier"], "") if a["to_supplier"] else ""
            wait_cost = float(row["extra_cost_wait"])
            if a["po_id"] in self.claimed:
                # agents coordinate: an order already being rerouted is not touched twice
                self.send("policy", "audit", "action.skipped",
                          f"PO {a['po_id']} is already being handled for event {self.claimed[a['po_id']]}; no second change.",
                          event_id=eid, po_id=a["po_id"])
                continue
            self.claimed[a["po_id"]] = eid
            auto, rule = policy_decision(a, wait_cost)
            a["rule"], a["action_id"] = rule, "A-" + uuid.uuid4().hex[:6].upper()
            a["net_cost"] = round(float(a["extra_cost"]) - wait_cost, 2)
            what = (f"switch PO {a['po_id']} ({a['qty']} x {a['material']}) to {a['to_supplier']}"
                    if a["action"] == "switch" else f"expedite PO {a['po_id']} ({a['qty']} x {a['material']})")
            if auto:
                self.send("policy", "execution", "action.authorised", f"Auto-approved: {what}. {rule}.",
                          action=a, decided_by="Policy agent")
            else:
                self.pending[a["action_id"]] = a
                self.stats["escalated"] += 1
                self.send("policy", "planner", "approval.requested", f"Needs approval: {what}. Reason: {rule}.",
                          action=a)

    def decide(self, action_id: str, approve: bool, reason: str = "", by: str = "Planner"):
        """The human planner's answer to an escalation."""
        a = self.pending.pop(action_id)
        if not approve:
            self.claimed.pop(a["po_id"], None)   # a rejected order may be planned again later
        kind = "approval.granted" if approve else "approval.rejected"
        text = ("Approved" if approve else "Rejected") + f" PO {a['po_id']} {a['action']}" + (f": {reason}" if reason else "")
        self.send("planner", "execution", kind, text, action=a, decided_by=by, reason=reason)

    def _execution(self, msg):
        a = msg.data["action"]
        if msg.kind == "approval.rejected":
            status, who = "Rejected by planner", msg.data.get("decided_by", "Planner")
            self.stats["rejected"] += 1
            self._record(a, status, who, request={})
            self.decided.append({**a, "status": status})
            self.send("execution", "audit", "action.cancelled", f"Cancelled PO {a['po_id']} {a['action']} as instructed.",
                      action_id=a["action_id"])
            return
        auto = msg.kind == "action.authorised"
        status = "Executed by agent" if auto else "Executed after approval"
        self.stats["auto" if auto else "approved"] += 1
        self.stats["extra_cost"] += float(a["extra_cost"])
        req = s4_request(a)
        if a["action"] == "switch":
            note = (f"Dear {a['to_supplier']} team, please confirm {a['qty']} x {a['material']} "
                    f"within your standard lead time (replaces PO {a['po_id']}).")
        else:
            note = (f"Dear {a['from_supplier']} team, please prioritise PO {a['po_id']} ({a['qty']} x {a['material']}) "
                    f"and ship express once you restart.")
        self._record(a, status, msg.data.get("decided_by", ""), request=req, message=note)
        self.decided.append({**a, "status": status})
        self.send("execution", "audit", "action.executed",
                  f"{status}: PO {a['po_id']} {a['action']}"
                  + (f" to {a['to_supplier']}" if a["action"] == "switch" else "")
                  + f"; supplier notified; S/4HANA {req['method']} prepared.",
                  action_id=a["action_id"], s4_request=req, supplier_message=note)

    def _record(self, a, status, who, request, message=""):
        if not self.persist:
            return
        details = (f"Move {a['qty']} x {a['material']} from {a['from_supplier']} to {a['to_supplier']}"
                   if a["action"] == "switch" else f"Expedite {a['qty']} x {a['material']} with {a['from_supplier']}")
        db.insert_row("plan_actions", {
            "action_id": a["action_id"], "created_at": db.now(), "event_id": a["event_id"], "plan_name": a["plan"],
            "action_type": a["action"], "po_id": a["po_id"], "details": details, "supplier_message": message,
            "status": status, "decided_by": who, "policy_rule": a["rule"], "extra_cost": a["extra_cost"],
            "s4_request": request})


def simulate(network: Network, steps, pause: float = 0.0):
    """Feed scripted signals into the network one after another. steps = [(label, source, text)]."""
    for label, source, text in steps:
        network.inject(text, source, label)
        for msg in network.run():
            yield msg
            if pause:
                time.sleep(pause)
