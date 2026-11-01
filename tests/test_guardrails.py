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
