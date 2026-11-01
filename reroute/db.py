"""Data access. The same code talks to SQLite (default) or SAP HANA Cloud.

Both drivers use '?' placeholders, so one set of SQL statements serves both.
Runtime writes (approvals, audit log) reuse one connection per thread, so a live
showcase doesn't open a new HANA connection for every agent message.
"""
import csv
import json
import logging
import os
import sqlite3
import threading
from datetime import datetime

import pandas as pd

from . import config

TABLES = ["meta", "cities", "materials", "products", "bom", "suppliers", "supplier_materials",
          "supplier_links", "sales_orders", "purchase_orders"]

# Tables the app writes to while running (all text columns)
RUNTIME_DDL = {
    "supplier_reports": ["report_id", "created_at", "supplier_id", "issue_type", "days_down", "note"],
    "plan_actions": ["action_id", "created_at", "event_id", "plan_name", "action_type", "po_id",
                     "details", "supplier_message", "status", "decided_by", "policy_rule", "extra_cost",
                     "s4_request"],
    "agent_audit_log": ["seq", "ts", "run_id", "sender", "recipient", "kind", "summary", "details",
                  "prev_hash", "hash"],
}

_tl = threading.local()
log = logging.getLogger("reroute.db")


def backend() -> str:
    return "hana" if config.DB_BACKEND == "hana" else "sqlite"


def _guard_reset(what: str) -> None:
    """HANA is shared by the whole team, so never wipe it by accident.

    SQLite is one person's local file, so it can always be reset.
    """
    if backend() == "hana" and os.getenv("REROUTE_ALLOW_RESET", "").lower() != "yes":
        raise RuntimeError(
            f"Refusing to {what} on SAP HANA Cloud: it is shared by the whole team, and this would delete the "
            "supplier reports, approvals and audit log. If everyone agrees, run this one command with "
            "REROUTE_ALLOW_RESET=yes set in the terminal (not in .env).")


def connect():
    if backend() == "hana":
        from hdbcli import dbapi  # pip install hdbcli
        conn = dbapi.connect(address=config.HANA["address"], port=config.HANA["port"],
                             user=config.HANA["user"], password=config.HANA["password"], encrypt=True)
        if config.HANA["schema"]:
            conn.cursor().execute(f'SET SCHEMA "{config.HANA["schema"]}"')
        return conn
    return sqlite3.connect(config.SQLITE_PATH)


def _shared():
    """One reusable connection per thread for frequent small writes and reads."""
    conn = getattr(_tl, "conn", None)
    if conn is None:
        conn = _tl.conn = connect()
    return conn


def _reset_shared():
    conn = getattr(_tl, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
    _tl.conn = None


def _run(fn):
    """Run fn(cursor) on the shared connection, reconnecting once if it went stale."""
    for attempt in range(2):
        try:
            conn = _shared()
            cur = conn.cursor()
            result = fn(cur)
            conn.commit()
            return result
        except Exception:
            _reset_shared()
            if attempt == 1:
                raise


def _q(name: str) -> str:
    """Quote a table or column name the same way on both databases."""
    return f'"{name.upper()}"' if backend() == "hana" else f'"{name}"'


def _sql_type(values) -> str:
    def is_num(v, kind):
        try:
            kind(v)
            return True
        except ValueError:
            return False
    vals = [v for v in values if v != ""]
    if vals and all(is_num(v, int) for v in vals):
        return "BIGINT"  # PO numbers like 4500000001 overflow HANA's 32-bit INTEGER
    if vals and all(is_num(v, float) for v in vals):
        return "DOUBLE"
    return "NVARCHAR(500)"


def _convert(v, t):
    if v == "":
        return None
    return int(v) if t == "BIGINT" else float(v) if t == "DOUBLE" else v


def _drop(cur, table):
    try:
        cur.execute(f"DROP TABLE {_q(table)}")
    except Exception:
        pass  # table did not exist


def _create_runtime(cur, table):
    width = 5000 if table == "agent_audit_log" else 2000
    cols = ", ".join(f"{_q(c)} NVARCHAR({width})" for c in RUNTIME_DDL[table])
    cur.execute(f"CREATE TABLE {_q(table)} ({cols})")


def init_db(reset_runtime: bool = True) -> None:
    """Load every CSV from data/ into the database (re-creating the tables).

    reset_runtime=True also clears supplier reports, approvals and the audit log.
    On SAP HANA Cloud this is refused unless REROUTE_ALLOW_RESET=yes (see _guard_reset).
    """
    _guard_reset("re-create all tables")
    _reset_shared()
    conn = connect()
    cur = conn.cursor()
    for table in TABLES:
        with open(config.DATA_DIR / f"{table}.csv", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        header, body = rows[0], rows[1:]
        types = [_sql_type([r[i] for r in body]) for i in range(len(header))]
        _drop(cur, table)
        cols = ", ".join(f"{_q(c)} {t}" for c, t in zip(header, types))
        cur.execute(f"CREATE TABLE {_q(table)} ({cols})")
        placeholders = ", ".join("?" for _ in header)
        data = [tuple(_convert(v, t) for v, t in zip(r, types)) for r in body]
        cur.executemany(f"INSERT INTO {_q(table)} VALUES ({placeholders})", data)
    conn.commit()
    conn.close()
    ensure_runtime_tables(reset=reset_runtime)


def ensure_runtime_tables(reset: bool = False) -> None:
    """Create the runtime tables if missing, or re-create one whose columns are out of date."""
    _reset_shared()
    conn = connect()
    for table, cols in RUNTIME_DDL.items():
        cur = conn.cursor()
        current = None
        try:
            cur.execute(f"SELECT * FROM {_q(table)} WHERE 1 = 0")
            current = [d[0].lower() for d in cur.description]
        except Exception:
            conn.rollback() if backend() == "sqlite" else None
        if reset or (current is not None and current != cols):
            if current is not None:
                _guard_reset(f"clear the {table} table" if reset else
                             f"re-create the {table} table (its columns changed)")
            _drop(cur, table)
            current = None
        if current is None:
            _create_runtime(cur, table)
    _ensure_audit_seq_unique(conn)
    conn.commit()
    conn.close()


def _ensure_audit_seq_unique(conn) -> None:
    """A unique seq makes the database refuse a second record with the same number, so two runs
    writing at once can never fork the audit chain (AuditLog.append retries instead)."""
    cur = conn.cursor()
    name, table, col = _q("agent_audit_log_seq"), _q("agent_audit_log"), _q("seq")
    try:
        if backend() == "sqlite":
            cur.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS {name} ON {table} ({col})")
            return
        cur.execute("SELECT COUNT(*) FROM INDEXES WHERE SCHEMA_NAME = CURRENT_SCHEMA AND INDEX_NAME = ?",
                    ["AGENT_AUDIT_LOG_SEQ"])
        if cur.fetchone()[0] == 0:
            cur.execute(f"CREATE UNIQUE INDEX {name} ON {table} ({col})")
    except Exception as e:  # e.g. old duplicate seq values: keep running, the retry still narrows the gap
        log.warning("Could not make audit seq unique: %s", e)


def audit_tail() -> tuple:
    """(last seq number, last hash) of the stored audit log, read fresh; (0, 'GENESIS') if empty."""
    def fetch(cur):
        cur.execute(f"SELECT {_q('seq')}, {_q('hash')} FROM {_q('agent_audit_log')} "
                    f"ORDER BY {_q('seq')} DESC LIMIT 1")
        return cur.fetchone()
    row = _run(fetch)
    return (int(row[0]), row[1]) if row else (0, "GENESIS")


def load_tables() -> dict:
    """Return every network table as a pandas DataFrame with lower-case columns.

    On SQLite, an empty or missing database is loaded from the CSVs automatically.
    """
    if backend() == "sqlite":
        conn = sqlite3.connect(config.SQLITE_PATH)
        found = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='meta'").fetchone()
        conn.close()
        if not found:
            init_db()
    conn = connect()
    out = {}
    for table in TABLES:
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM {_q(table)}")
        cols = [d[0].lower() for d in cur.description]
        out[table] = pd.DataFrame([tuple(r) for r in cur.fetchall()], columns=cols)
    conn.close()
    return out


def insert_row(table: str, values: dict) -> None:
    cols = RUNTIME_DDL[table]
    row = []
    for c in cols:
        v = values.get(c, "")
        row.append(json.dumps(v, default=str) if isinstance(v, (dict, list)) else str(v))
    _run(lambda cur: cur.execute(f"INSERT INTO {_q(table)} VALUES ({', '.join('?' for _ in cols)})", row))


def update_row(table: str, key_col: str, key: str, values: dict) -> None:
    sets = ", ".join(f"{_q(c)} = ?" for c in values)
    params = [str(v) for v in values.values()] + [str(key)]
    _run(lambda cur: cur.execute(f"UPDATE {_q(table)} SET {sets} WHERE {_q(key_col)} = ?", params))


def read_rows(table: str) -> pd.DataFrame:
    def fetch(cur):
        cur.execute(f"SELECT * FROM {_q(table)}")
        return pd.DataFrame([tuple(r) for r in cur.fetchall()], columns=[d[0].lower() for d in cur.description])
    return _run(fetch)


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")
