"""Guardrails for the shared SAP HANA Cloud database (tests use SQLite, no accounts needed)."""
import os
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["REROUTE_DB"] = "sqlite"
os.environ["REROUTE_LLM"] = "off"

from reroute import config, db, network  # noqa: E402

STRIKE = "Transporters announce statewide strike across Tamil Nadu from Monday for 3 days over toll hike."


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SQLITE_PATH", str(tmp_path / "guard.db"))
    db.init_db()
    yield db.load_tables()
    db._reset_shared()  # don't leave this thread pointing at the temporary database


def test_concurrent_runs_keep_one_valid_audit_chain(fresh_db):
    # all four runs start before any of them writes, like four viewers pressing Start together
    nets = [network.Network(fresh_db, persist=True, use_llm=False) for _ in range(4)]

    def go(net):
        net.inject(STRIKE, "news", "guardrail test")
        net.run_all()
        for aid in list(net.pending):
            net.decide(aid, True, "test")
            net.run_all()

    threads = [threading.Thread(target=go, args=(n,)) for n in nets]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    rows = db.read_rows("agent_audit_log")
    assert len(rows) == sum(n.stats["messages"] for n in nets)
    assert rows["seq"].nunique() == len(rows)
    assert network.verify_audit(rows)["ok"]


def test_tampering_is_still_detected(fresh_db):
    net = network.Network(fresh_db, persist=True, use_llm=False)
    net.inject(STRIKE, "news")
    net.run_all()
    rows = db.read_rows("agent_audit_log")
    rows.loc[rows.index[2], "summary"] = "edited afterwards"
    assert network.verify_audit(rows)["ok"] is False


def test_hana_reset_is_refused_without_explicit_permission(monkeypatch):
    monkeypatch.setattr(config, "DB_BACKEND", "hana")
    monkeypatch.delenv("REROUTE_ALLOW_RESET", raising=False)
    with pytest.raises(RuntimeError, match="Refusing"):
        db.init_db()  # refused before any connection is opened, so no HANA account is needed


def test_timestamps_are_indian_time_even_on_a_utc_server():
    from datetime import datetime, timedelta, timezone
    expected = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
    got = datetime.fromisoformat(db.now())
    assert got.tzinfo is None                                    # same format as stored records
    assert abs((got - expected.replace(tzinfo=None)).total_seconds()) < 5


def test_clearing_a_report_hides_it_but_keeps_it(fresh_db):
    from reroute import agent
    for sid in ["S14", "S20"]:
        agent.analyze_report({"supplier_id": sid, "issue_type": "flood", "days_down": 3, "note": ""}, fresh_db, save=True)
    target = db.supplier_reports().query("supplier_id == 'S14'").iloc[0].to_dict()
    db.clear_supplier_report(target)
    assert list(db.supplier_reports()["supplier_id"]) == ["S20"]                     # hidden from the dashboard
    assert set(db.supplier_reports(include_cleared=True)["supplier_id"]) == {"S14", "S20"}  # still stored


def test_resolving_works_even_if_the_new_table_was_never_created(fresh_db):
    # Streamlit Cloud reloads code without restarting, so start-up table creation may not have run
    import sqlite3
    from reroute import agent
    agent.analyze_report({"supplier_id": "S20", "issue_type": "flood", "days_down": 8, "note": ""}, fresh_db, save=True)
    conn = sqlite3.connect(config.SQLITE_PATH)
    conn.execute('DROP TABLE "cleared_reports"')
    conn.commit()
    conn.close()
    db._reset_shared()
    db.clear_supplier_report(db.supplier_reports().iloc[0].to_dict())
    assert db.supplier_reports().empty and len(db.supplier_reports(include_cleared=True)) == 1
