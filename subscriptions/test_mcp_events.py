"""Persistent event delivery checks: python3 -m unittest discover -s subscriptions."""

import contextlib
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
from event_outbox import Outbox, JOB_ID
import mcp_events


SUB = {"id": "mail", "server": "email", "event": "email.received", "arguments": {},
       "enabled": True, "instructions": "Проверь письмо."}


def report(event_id):
    return [SUB, [{"eventId": event_id, "data": {"subject": "test"}}], False, None, False]


class DeliveryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.state = self.home / "state/subscriptions"
        (self.home / "cron").mkdir()
        self.ledger = self.home / "cron/executions.db"
        self.db = sqlite3.connect(self.ledger)
        self.addCleanup(self.db.close)
        self.db.execute("CREATE TABLE executions (id TEXT PRIMARY KEY, job_id TEXT, pid INTEGER, status TEXT)")
        self.outbox = Outbox(self.state, self.ledger)

    def execution(self, eid, status, job_id=JOB_ID):
        self.db.execute("INSERT OR REPLACE INTO executions VALUES (?,?,?,?)",
                        (eid, job_id, os.getpid(), status))
        self.db.commit()

    def test_failure_replays_identical_batch_after_restart_then_success_acks(self):
        self.outbox.save_poll("mail", {"cursor": "c1"}, report("e1"))
        self.execution("run1", "running")
        original = self.outbox.claim("run1")
        self.execution("run1", "failed")
        restarted = Outbox(self.state, self.ledger)
        restarted.reconcile()
        self.assertEqual(restarted.load_state("mail"), {"cursor": "c1"})
        self.assertEqual(restarted.pending_count(), 1)
        self.execution("run2", "running")
        self.assertEqual(restarted.claim("run2"), original)
        self.execution("run2", "completed")
        restarted.reconcile()
        self.assertEqual(restarted.pending_count(), 0)
        self.execution("run3", "running")
        self.assertEqual(restarted.claim("run3"), [])

    def test_success_only_removes_its_batch_and_new_events_stay_queued(self):
        self.execution("run1", "running")
        self.outbox.save_poll("mail", {"cursor": "c1"}, report("e1"))
        self.outbox.claim("run1")
        self.outbox.save_poll("mail", {"cursor": "c2"}, report("e2"))
        self.execution("run1", "completed")
        self.outbox.reconcile()
        self.execution("run2", "running")
        self.assertEqual(self.outbox.claim("run2"), [report("e2")])
        self.assertEqual(self.outbox.load_state("mail"), {"cursor": "c2"})

    def test_cursor_and_events_roll_back_together(self):
        self.outbox.save_poll("mail", {"cursor": "old"})
        with self.outbox.connect() as db:
            db.execute("CREATE TRIGGER fail_state BEFORE INSERT ON subscription_state "
                       "BEGIN SELECT RAISE(ABORT, 'disk failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.outbox.save_poll("mail", {"cursor": "new"}, report("e1"))
        self.assertEqual(self.outbox.load_state("mail"), {"cursor": "old"})
        self.assertEqual(self.outbox.pending_count(), 0)

    def test_live_missing_and_foreign_attempts_cannot_ack_or_redeliver(self):
        self.outbox.save_poll("mail", {"cursor": "c1"}, report("e1"))
        self.execution("run1", "running")
        self.outbox.claim("run1")
        self.execution("run2", "running")
        self.outbox.reconcile()
        self.assertEqual(self.outbox.claim("run2"), [])
        self.execution("run1", "completed", job_id="another-job")
        self.outbox.reconcile()
        self.assertEqual(self.outbox.pending_count(), 1)
        self.assertEqual(self.outbox.claim("run2"), [])
        self.db.execute("DELETE FROM executions WHERE id='run1'")
        self.db.commit()
        self.outbox.reconcile()
        self.assertEqual(self.outbox.pending_count(), 1)

    def test_unknown_crashed_attempt_is_retained_and_retried(self):
        self.execution("run1", "running")
        self.outbox.save_poll("mail", {"cursor": "c1"}, report("e1"))
        self.outbox.claim("run1")
        self.execution("run1", "unknown")
        self.outbox.reconcile()
        self.execution("run2", "running")
        self.assertEqual(self.outbox.claim("run2"), [report("e1")])

    def test_identity_and_fifo_limit(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(RuntimeError):
            self.outbox.current_execution()
        self.execution("run1", "running")
        with patch.dict(os.environ, {"MORZIK_CRON_EXECUTION_ID": "run1", "MORZIK_CRON_JOB_ID": JOB_ID}):
            self.assertEqual(self.outbox.current_execution(), "run1")
        with patch.dict(os.environ, {"MORZIK_CRON_EXECUTION_ID": "run1", "MORZIK_CRON_JOB_ID": "wrong"}), \
                self.assertRaises(RuntimeError):
            self.outbox.current_execution()
        for i in range(3):
            self.outbox.save_poll("mail", {"cursor": str(i)}, report(str(i)))
        self.assertEqual(self.outbox.claim("run1", max_events=2), [report("0"), report("1")])
        self.assertEqual(self.outbox.pending_count(), 3)
        self.assertEqual(os.stat(self.outbox.path).st_mode & 0o777, 0o600)

    def test_poll_gate_migrates_cursor_and_retries_even_when_source_is_not_due(self):
        (self.state / "mail.json").write_text(json.dumps({"cursor": "legacy"}))
        seen = []

        class FakeClient:
            def __init__(self, *args):
                pass

            def connect(self):
                return self

            def request(self, method, params):
                seen.append(params["cursor"])
                return {"cursor": "next", "events": report("e1")[1], "nextPollMs": 3600000}

        def run(eid):
            with patch.object(mcp_events, "HOME", str(self.home)), \
                    patch.object(mcp_events, "STATE", str(self.state)), \
                    patch.object(mcp_events, "subscriptions", return_value=[SUB]), \
                    patch.object(mcp_events, "mcp_servers", return_value={"email": {}}), \
                    patch.object(mcp_events, "dotenv", return_value={}), \
                    patch.object(mcp_events, "Client", FakeClient), \
                    patch.object(Outbox, "current_execution", return_value=eid), \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                mcp_events.poll_all()
                return output.getvalue()

        self.execution("run1", "running")
        first = run("run1")
        self.assertIn('"eventId": "e1"', first)
        self.assertEqual(seen, ["legacy"])
        self.execution("run1", "failed")
        self.execution("run2", "running")
        self.assertEqual(run("run2"), first)
        self.assertEqual(seen, ["legacy"])  # No new poll needed to retry durable events.
        self.execution("run2", "completed")
        self.execution("run3", "running")
        self.assertEqual(json.loads(run("run3")), {"wakeAgent": False})
        self.assertEqual(self.outbox.pending_count(), 0)


if __name__ == "__main__":
    unittest.main()
