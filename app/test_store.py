"""python3 app/test_store.py"""

import os
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from store import CODE_ATTEMPTS, Store  # noqa: E402


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(os.path.join(self.tmp.name, "chat.db"))

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_resend_with_same_client_id_returns_the_stored_message(self):
        first, created = self.store.add("user", "привет", client_id="c1")
        again, created_again = self.store.add("user", "привет", client_id="c1")
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first["id"], again["id"])
        self.assertEqual(len(self.store.tail()), 1)

    def test_changes_after_a_revision_include_edits_in_order(self):
        a, _ = self.store.add("user", "a", client_id="a")
        b, _ = self.store.add("morzik", "b", buttons=[{"id": "x", "title": "Войти", "kind": "login", "value": "r1"}])
        seen = self.store.current_rev()
        self.store.update(b["id"], buttons=[])
        c, _ = self.store.add("morzik", "c")
        changes, more = self.store.since(seen)
        self.assertFalse(more)
        self.assertEqual([m["id"] for m in changes], [b["id"], c["id"]])
        self.assertEqual(changes[0]["buttons"], [])
        self.assertLess(a["seq"], b["seq"])
        self.assertLess(b["seq"], c["seq"])  # chat order never changes with edits

    def test_since_pages(self):
        for i in range(7):
            self.store.add("morzik", str(i))
        rev, got = 0, []
        while True:
            page, more = self.store.since(rev, limit=3)
            got += page
            rev = page[-1]["rev"]
            if not more:
                break
        self.assertEqual([m["text"] for m in got], [str(i) for i in range(7)])

    def test_read_marks_only_users_messages_up_to_seq(self):
        a, _ = self.store.add("user", "a", client_id="a")
        self.store.add("morzik", "ok")
        c, _ = self.store.add("user", "c", client_id="c")
        changed = self.store.mark_read_until(a["seq"])
        self.assertEqual([m["id"] for m in changed], [a["id"]])
        self.assertEqual(self.store.get(c["id"])["status"], "sent")
        self.assertEqual(self.store.mark_read_until(a["seq"]), [])

    def test_unread_and_history(self):
        device, _ = self.store.add_device("iPhone")
        m = [self.store.add("morzik", str(i))[0] for i in range(5)]
        self.assertEqual(self.store.unread(device), 5)
        self.store.set_read(device, m[2]["seq"])
        self.assertEqual(self.store.unread(device), 2)
        self.store.set_read(device, m[0]["seq"])  # never goes back
        self.assertEqual(self.store.unread(device), 2)
        self.assertEqual([x["text"] for x in self.store.before(m[3]["seq"], 2)], ["1", "2"])

    def test_deleted_messages_leave_tail_but_come_as_changes(self):
        a, _ = self.store.add("morzik", "progress")
        rev = self.store.current_rev()
        self.store.update(a["id"], deleted=True)
        self.assertEqual(self.store.tail(), [])
        changes, _ = self.store.since(rev)
        self.assertTrue(changes[0]["deleted"])

    def test_sign_in_code(self):
        pairing, code = self.store.new_code("iPhone", now=1000)
        self.assertIsNone(self.store.new_code("iPhone", now=1001))  # too often
        wrong = "000000" if code != "000000" else "111111"
        self.assertEqual(self.store.redeem(pairing, wrong, now=1002), "wrong")
        device_id, token = self.store.redeem(pairing, code, now=1003)
        self.assertEqual(self.store.device_for(token)["id"], device_id)
        self.assertEqual(self.store.redeem(pairing, code, now=1004), "expired")  # one use
        self.assertIsNone(self.store.device_for("nope"))
        self.store.revoke(device_id)
        self.assertIsNone(self.store.device_for(token))

    def test_code_locks_after_attempts_and_expires(self):
        pairing, code = self.store.new_code("iPhone", now=0)
        wrong = "000000" if code != "000000" else "111111"
        for _ in range(CODE_ATTEMPTS - 1):
            self.assertEqual(self.store.redeem(pairing, wrong, now=1), "wrong")
        self.assertEqual(self.store.redeem(pairing, wrong, now=1), "locked")
        self.assertEqual(self.store.redeem(pairing, code, now=2), "locked")
        pairing2, code2 = self.store.new_code("iPhone", now=100)
        self.assertEqual(self.store.redeem(pairing2, code2, now=100 + 11 * 60), "expired")

    def test_push_token_moves_to_the_newest_device(self):
        d1, _ = self.store.add_device("old")
        d2, _ = self.store.add_device("new")
        self.store.set_push(d1, "tok", "development")
        self.store.set_push(d2, "tok", "development")
        self.assertEqual([d["id"] for d in self.store.push_devices()], [d2])

    def test_reactions_change_the_revision_and_old_databases_get_the_column(self):
        m, _ = self.store.add("morzik", "напомнить вечером?")
        rev = self.store.current_rev()
        changed = self.store.update(m["id"], reactions=["👍"])
        self.assertEqual(changed["reactions"], ["👍"])
        self.assertGreater(changed["rev"], rev)
        self.assertEqual(self.store.update(m["id"], reactions=[])["reactions"], [])
        self.store.close()
        import sqlite3
        path = os.path.join(self.tmp.name, "old.db")
        old = sqlite3.connect(path)
        old.executescript(open(os.path.join(os.path.dirname(__file__), "store.py")).read().split('SCHEMA = """')[1]
                          .split('"""')[0].replace("  reactions TEXT,\n", ""))
        old.close()
        self.store = Store(path)
        self.assertEqual(self.store.add("user", "x", client_id="x")[0]["reactions"], [])

    def test_concurrent_writers(self):
        def write(n):
            for i in range(50):
                self.store.add("user", f"{n}-{i}", client_id=f"{n}-{i}")
                self.store.add("user", f"{n}-{i}", client_id=f"{n}-{i}")
        threads = [threading.Thread(target=write, args=(n,)) for n in range(4)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        changes, _ = self.store.since(0, limit=1000)
        self.assertEqual(len(changes), 200)
        revs = [m["rev"] for m in changes]
        self.assertEqual(len(set(revs)), 200)


if __name__ == "__main__":
    unittest.main()
