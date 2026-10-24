import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))

import classify  # noqa: E402
from classify import HEAVY, LIGHT  # noqa: E402


class ClassifyTest(unittest.TestCase):
    def route(self, message, history=None):
        return classify.classify(message, history)[0]

    def test_small_talk_is_light(self):
        for text in ("Привет", "Ты тут?", "Что умеешь?", "Помурлыкай мне :3", "Спасибо, бро", "Как оно быть котом?"):
            self.assertEqual(self.route(text), LIGHT, text)

    def test_quick_lookups_are_light(self):
        for text in ("Есть что на почте?", "Пометь их прочитанными", "Напомни завтра в 9 позвонить в сервис",
                     "Что у меня завтра в календаре?", "Когда построили Эйфелеву башню?"):
            self.assertEqual(self.route(text), LIGHT, text)

    def test_real_work_is_heavy(self):
        for text in ("Зайди на сайт банка и достань выписку", "Сделай драфт письма ответа",
                     "Сравни эти два варианта жилья", "Почини флуд бота", "Оплати счёт за домен",
                     "Подумай, как лучше распланировать неделю", "Отправь ему файл",
                     "Что посоветуешь по поездке?", "Поменяй жильё в плане на это", "Надо им что-то отписать?"):
            self.assertEqual(self.route(text), HEAVY, text)

    def test_attachments_and_links_are_heavy(self):
        self.assertEqual(self.route("Что тут?  [Image attached at: /tmp/x.png]"), HEAVY)
        self.assertEqual(self.route("[The user sent a document: 'a.pdf'. It is saved at: /tmp/a.pdf]"), HEAVY)
        self.assertEqual(self.route("А эта норм? https://example.com/rooms/1"), HEAVY)
        self.assertEqual(self.route([{"type": "text", "text": "что это"}, {"type": "image_url"}]), HEAVY)

    def test_long_message_is_heavy(self):
        self.assertEqual(self.route("слово " * 50), HEAVY)

    def test_follow_up_to_long_task_is_heavy(self):
        busy = [{"role": "user", "content": "x"}] + [
            {"role": "assistant", "tool_calls": [{"id": str(i)}]} for i in range(3)
        ] + [{"role": "assistant", "content": "готово"}]
        self.assertEqual(self.route("Давай ещё раз", busy), HEAVY)
        quiet = [{"role": "user", "content": "x"}, {"role": "assistant", "content": "мур"}]
        self.assertEqual(self.route("Давай ещё раз", quiet), LIGHT)

    def test_empty_is_heavy(self):
        self.assertEqual(self.route(""), HEAVY)
        self.assertEqual(self.route(None), HEAVY)


class HookTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.TemporaryDirectory()
        os.environ["HERMES_HOME"] = self.home.name
        import importlib
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        self.plugin = importlib.import_module("router")

    def tearDown(self):
        os.environ.pop("HERMES_HOME", None)
        self.home.cleanup()

    def test_light_telegram_turn_is_routed(self):
        self.assertEqual(self.plugin._pre_llm_call(platform="telegram", user_message="Привет"),
                         {"turn_route": "morzik_light"})

    def test_heavy_turn_and_other_platforms_stay(self):
        self.assertIsNone(self.plugin._pre_llm_call(platform="telegram", user_message="Сделай драфт письма"))
        self.assertIsNone(self.plugin._pre_llm_call(platform="cron", user_message="Привет"))
        self.assertIsNone(self.plugin._pre_llm_call(platform="api_server", user_message="Привет"))

    def test_decision_log_has_no_text(self):
        self.plugin._pre_llm_call(platform="telegram", user_message="Секретное слово", session_id="s1")
        with open(os.path.join(self.home.name, "logs", "morzik-router.jsonl"), encoding="utf-8") as fh:
            line = fh.read()
        self.assertIn('"route": "light"', line)
        self.assertNotIn("Секретное", line)


if __name__ == "__main__":
    unittest.main()
