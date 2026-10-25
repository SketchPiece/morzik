import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))

import classify  # noqa: E402
from classify import HEAVY, LIGHT  # noqa: E402


def fake_jev(choice="light", confidence=1.0, error=None):
    """An ``opener`` for ``classify``: records the request body, answers like Jev."""
    sent = []

    def opener(request, timeout):
        sent.append(json.loads(request.data))
        if error:
            raise error
        body = {"answers": {"route": {"type": "choice", "choice": choice, "confidence": confidence}}}
        return io.BytesIO(json.dumps(body).encode())

    opener.sent = sent
    return opener


class ClassifyTest(unittest.TestCase):
    def test_confident_light_is_light(self):
        self.assertEqual(classify.classify("Привет", key="k", opener=fake_jev("light", 0.95))[:2], (LIGHT, "jev"))

    def test_unsure_light_is_heavy(self):
        self.assertEqual(classify.classify("Привет", key="k", opener=fake_jev("light", 0.5))[:2], (HEAVY, "unsure"))

    def test_heavy_is_heavy(self):
        self.assertEqual(classify.classify("Сделай драфт письма", key="k", opener=fake_jev("heavy", 0.9))[:2],
                         (HEAVY, "jev"))

    def test_failures_are_heavy(self):
        self.assertEqual(classify.classify("Привет", key="k", opener=fake_jev(error=TimeoutError()))[:2],
                         (HEAVY, "error:TimeoutError"))
        self.assertEqual(classify.classify("Привет", key="", opener=fake_jev())[:2], (HEAVY, "no-key"))
        self.assertEqual(classify.classify("", key="k", opener=fake_jev())[:2], (HEAVY, "empty"))

    def test_state_has_recent_text_but_no_tool_results(self):
        opener = fake_jev()
        history = [
            {"role": "user", "content": "старый вопрос"},
            {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "mcp__email__search_threads"}}]},
            {"role": "tool", "content": "тело письма с секретом"},
            {"role": "assistant", "content": "Нашёл два письма. Ответить?", "tool_calls": [{"name": "web_search"}]},
        ]
        classify.classify("x" * 5000, history, key="k", opener=opener)
        state = opener.sent[0]["state"]
        self.assertEqual(len(state["new_message"]), classify.MAX_CHARS)
        self.assertEqual(state["recent_conversation"], [
            {"role": "user", "text": "старый вопрос"},
            {"role": "assistant", "text": "Нашёл два письма. Ответить?"},
        ])
        self.assertEqual(state["previous_turn_tool_calls"], 2)
        self.assertEqual(state["previous_turn_tools"], ["mcp__email__search_threads", "web_search"])
        self.assertNotIn("секретом", json.dumps(opener.sent[0], ensure_ascii=False))

    def test_context_is_capped(self):
        history = [{"role": "user" if i % 2 else "assistant", "content": "слово " * 500} for i in range(20)]
        picked = classify.recent_conversation(history)
        self.assertLessEqual(len(picked), classify.CONTEXT_MESSAGES)
        self.assertTrue(all(len(m["text"]) <= classify.CONTEXT_MESSAGE_CHARS for m in picked))
        self.assertLessEqual(sum(len(m["text"]) for m in picked), classify.CONTEXT_TOTAL_CHARS)

    def test_attachment_parts_become_a_marker(self):
        opener = fake_jev()
        classify.classify([{"type": "text", "text": "что это"}, {"type": "image_url"}], key="k", opener=opener)
        self.assertEqual(opener.sent[0]["state"]["new_message"], "что это [attachment]")


class HookTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        os.environ["HERMES_HOME"] = self.home.name
        import importlib
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        self.plugin = importlib.import_module("router")
        self.original = self.plugin._classify.classify

    def tearDown(self):
        self.plugin._classify.classify = self.original
        os.environ.pop("HERMES_HOME", None)
        self.home.cleanup()

    def answer(self, route):
        self.plugin._classify.classify = lambda message, history=None: (route, "jev", 0.9)

    def test_light_telegram_turn_is_routed(self):
        self.answer(LIGHT)
        self.assertEqual(self.plugin._pre_llm_call(platform="telegram", user_message="Привет"),
                         {"turn_route": "morzik_light"})

    def test_heavy_turn_and_other_platforms_stay(self):
        self.answer(HEAVY)
        self.assertIsNone(self.plugin._pre_llm_call(platform="telegram", user_message="Сделай драфт письма"))
        self.answer(LIGHT)
        self.assertIsNone(self.plugin._pre_llm_call(platform="cron", user_message="Привет"))
        self.assertIsNone(self.plugin._pre_llm_call(platform="api_server", user_message="Привет"))

    def test_no_key_stays_on_main_model(self):
        self.assertIsNone(self.plugin._pre_llm_call(platform="telegram", user_message="Привет"))

    def test_decision_log_has_no_text(self):
        self.answer(LIGHT)
        self.plugin._pre_llm_call(platform="telegram", user_message="Секретное слово", session_id="s1")
        with open(os.path.join(self.home.name, "logs", "morzik-router.jsonl"), encoding="utf-8") as fh:
            line = fh.read()
        self.assertIn('"route": "light"', line)
        self.assertNotIn("Секретное", line)


if __name__ == "__main__":
    unittest.main()
