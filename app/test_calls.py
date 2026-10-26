"""python3 app/test_calls.py"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "voice"))
import brain  # noqa: E402
import calls  # noqa: E402

NOW = 1_800_000_000


class CallsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def log(self, call_id, text, ended=NOW - 60, duration=120):
        brain.log_call(self.home, call_id, text, ended - duration, duration, now=ended)

    def test_each_chat_gets_a_call_once(self):
        self.log("conv_1", "Пользователь: Купи молоко\nМорзик: Записал.")
        app = calls.pending_note(self.home, "morzik_app", now=NOW)
        self.assertIn("Пользователь: Купи молоко", app)
        self.assertIn("2 мин", app)
        self.assertIsNone(calls.pending_note(self.home, "morzik_app", now=NOW))
        self.assertIn("Купи молоко", calls.pending_note(self.home, "telegram", now=NOW))
        self.assertIsNone(calls.pending_note(self.home, "telegram", now=NOW))

    def test_only_the_chats_and_only_fresh_calls(self):
        self.log("conv_old", "Пользователь: давно", ended=NOW - 4 * 86400)
        self.assertIsNone(calls.pending_note(self.home, "morzik_app", now=NOW))
        self.log("conv_2", "Пользователь: сейчас")
        self.assertIsNone(calls.pending_note(self.home, "api_server", now=NOW))
        self.assertIsNone(calls.pending_note(self.home, "cron", now=NOW))
        note = calls.pending_note(self.home, "morzik_app", now=NOW)
        self.assertIn("сейчас", note)
        self.assertNotIn("давно", note)

    def test_several_calls_oldest_first_and_new_ones_later(self):
        self.log("conv_a", "Пользователь: первый", ended=NOW - 3600)
        self.log("conv_b", "Пользователь: второй")
        note = calls.pending_note(self.home, "telegram", now=NOW)
        self.assertLess(note.index("первый"), note.index("второй"))
        self.log("conv_c", "Пользователь: третий", ended=NOW)
        note = calls.pending_note(self.home, "telegram", now=NOW)
        self.assertIn("третий", note)
        self.assertNotIn("первый", note)

    def test_long_call_keeps_start_and_end(self):
        text = "Пользователь: начало\n" + "Морзик: бла.\n" * 3000 + "Пользователь: конец"
        self.log("conv_long", text)
        note = calls.pending_note(self.home, "morzik_app", now=NOW)
        self.assertLessEqual(len(note), calls.MAX_CHARS + 200)
        self.assertIn("начало", note)
        self.assertIn("конец", note)
        self.assertIn("пропущена", note)

    def test_webhook_retry_replaces_the_call_and_old_ones_drop_out(self):
        self.log("conv_1", "Пользователь: раз", ended=NOW - 8 * 86400)
        self.log("conv_2", "Пользователь: два")
        self.log("conv_2", "Пользователь: два")
        lines = (self.home / brain.CALLS_LOG).read_text(encoding="utf-8").splitlines()
        self.assertEqual([json.loads(line)["id"] for line in lines], ["conv_2"])

    def test_broken_files_do_not_break_the_turn(self):
        (self.home / "morzik-voice").mkdir()
        (self.home / calls.SEEN).write_text("{oops", encoding="utf-8")
        (self.home / calls.CALLS_LOG).write_text("not json\n", encoding="utf-8")
        self.assertIsNone(calls.pending_note(self.home, "morzik_app", now=NOW))
        self.log("conv_3", "Пользователь: ок")
        self.assertIn("ок", calls.pending_note(self.home, "morzik_app", now=NOW))


if __name__ == "__main__":
    unittest.main()
