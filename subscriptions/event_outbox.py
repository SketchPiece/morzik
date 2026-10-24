"""Durable MCP event batches, acknowledged by Hermes' execution ledger, never by the model.

Delivery is at least once: a run interrupted after a partial action can repeat that action.
Only the owning cron process can claim a batch; missing/ambiguous identity fails closed.
"""

import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

JOB_ID = "6b373df40d0d"


class Outbox:
    def __init__(self, state_dir, ledger_path, job_id=JOB_ID):
        self.path = Path(state_dir) / "outbox.db"
        self.ledger_path = Path(ledger_path)
        self.job_id = job_id
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_CREAT | os.O_WRONLY, 0o600)
        os.close(fd)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS subscription_state (
                    id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS reports (
                    id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS deliveries (
                    execution_id TEXT PRIMARY KEY, report_ids TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.execute("PRAGMA synchronous=FULL")
            with db:
                yield db
        finally:
            db.close()

    def ledger(self):
        return sqlite3.connect(self.ledger_path.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)

    def current_execution(self):
        """Identity comes from Hermes' context-local plugin API, not model output or a PID guess."""
        execution_id = os.environ.get("MORZIK_CRON_EXECUTION_ID")
        if not execution_id or os.environ.get("MORZIK_CRON_JOB_ID") != self.job_id:
            raise RuntimeError("Event polling must run inside its owning Hermes cron execution")
        db = self.ledger()
        try:
            rows = db.execute(
                "SELECT id FROM executions WHERE job_id=? AND id=? AND status='running'",
                (self.job_id, execution_id)).fetchall()
        finally:
            db.close()
        if len(rows) != 1:
            raise RuntimeError("Event polling must run inside its owning Hermes cron execution")
        return rows[0][0]

    def load_state(self, sub_id):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM subscription_state WHERE id=?", (sub_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def save_poll(self, sub_id, state, report=None):
        """Cursor and its received events commit together, or neither commits."""
        with self.connect() as db:
            if report is not None:
                db.execute("INSERT INTO reports VALUES (?, ?, ?)",
                           (uuid.uuid4().hex, json.dumps(report, ensure_ascii=False), time.time()))
            db.execute("INSERT OR REPLACE INTO subscription_state VALUES (?, ?)",
                       (sub_id, json.dumps(state, ensure_ascii=False)))

    def reconcile(self):
        """Only a terminal success for the exact job + attempt may remove queued reports."""
        ledger = self.ledger()
        try:
            with self.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                for execution_id, ids in db.execute("SELECT * FROM deliveries").fetchall():
                    row = ledger.execute("SELECT status FROM executions WHERE id=? AND job_id=?",
                                         (execution_id, self.job_id)).fetchone()
                    if not row or row[0] not in ("completed", "failed", "unknown"):
                        continue  # A live or unverified attempt must not be delivered twice.
                    if row[0] == "completed":
                        db.executemany("DELETE FROM reports WHERE id=?", [(x,) for x in json.loads(ids)])
                    db.execute("DELETE FROM deliveries WHERE execution_id=?", (execution_id,))
        finally:
            ledger.close()

    def claim(self, execution_id, max_events=200):
        """Reserve a bounded FIFO batch before printing it for the agent."""
        ledger = self.ledger()
        try:
            row = ledger.execute("SELECT status FROM executions WHERE id=? AND job_id=?",
                                 (execution_id, self.job_id)).fetchone()
        finally:
            ledger.close()
        if not row or row[0] != "running":
            raise RuntimeError("Cannot deliver events outside a running cron execution")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            reservations = db.execute("SELECT execution_id, report_ids FROM deliveries").fetchall()
            if reservations:
                # No second batch until the previous run has a durable terminal verdict.
                for owner, ids in reservations:
                    if owner == execution_id:
                        return [json.loads(db.execute("SELECT payload FROM reports WHERE id=?", (x,))
                                           .fetchone()[0]) for x in json.loads(ids)]
                return []
            chosen, count = [], 0
            for report_id, payload in db.execute("SELECT id, payload FROM reports ORDER BY created_at, id"):
                report = json.loads(payload)
                weight = max(1, len(report[1]))  # Report tuple: subscription, events, status flags.
                if chosen and count + weight > max_events:
                    break
                chosen.append((report_id, report))
                count += weight
                if count >= max_events:
                    break
            if chosen:
                db.execute("INSERT INTO deliveries VALUES (?, ?)",
                           (execution_id, json.dumps([x[0] for x in chosen])))
            return [x[1] for x in chosen]

    def pending_count(self):
        with self.connect() as db:
            return db.execute("SELECT count(*) FROM reports").fetchone()[0]
