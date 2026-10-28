import atexit
import json
import os
import pathlib
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import browser  # noqa: E402

HARNESS = pathlib.Path(browser.HARNESS).read_text()


class FakeHelpers(types.ModuleType):
    """A browser with tabs a..: the attached one, the one in front, closed ones."""

    INTERNAL = ("chrome://", "about:")

    def __init__(self, tabs, current):
        super().__init__("browser_harness.helpers")
        self.tabs, self.current, self.front, self.closed, self.switched = list(tabs), current, None, [], []

    def switch_tab(self, target, activate=False):
        self.switched.append((target, activate))
        self.current = target
        if activate:
            self.front = target

    def current_tab(self):
        return {"targetId": self.current, "url": "https://example.com/", "title": ""}

    def activate_tab(self, tab):
        self.front = tab["targetId"]

    def list_tabs(self, include_chrome=True):
        return [{"targetId": t, "url": "https://example.com/"} for t in self.tabs]

    def close_tab(self, target):
        self.tabs.remove(target)
        self.closed.append(target)


class HarnessTest(unittest.TestCase):
    def run_harness(self, helpers, state, used=None, keep=3):
        if used is not None:
            pathlib.Path(state).write_text(json.dumps({"used": used}))
        pkg = types.ModuleType("browser_harness")
        pkg.helpers = helpers
        finish = []
        g = {"switch_tab": helpers.switch_tab}
        with mock.patch.dict(sys.modules, {"browser_harness": pkg, "browser_harness.helpers": helpers}), \
                mock.patch.object(atexit, "register", finish.append):
            exec(compile(HARNESS, "harness.py", "exec"), {"G": g, "STATE": state, "KEEP": keep})
        return g, finish[0]

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.state = os.path.join(self.dir.name, "state", "tabs.json")
        os.makedirs(os.path.dirname(self.state))

    def tearDown(self):
        self.dir.cleanup()

    def test_current_tab_comes_to_front_at_start(self):
        helpers = FakeHelpers("ab", current="b")
        self.run_harness(helpers, self.state)
        self.assertEqual(helpers.front, "b")

    def test_switch_tab_shows_the_tab(self):
        helpers = FakeHelpers("ab", current="a")
        g, _ = self.run_harness(helpers, self.state)
        g["switch_tab"]("b")
        self.assertEqual(helpers.front, "b")
        helpers.switch_tab("a")  # what new_tab and ensure_real_tab call
        self.assertEqual(helpers.front, "a")

    def test_end_closes_the_oldest_beyond_keep(self):
        helpers = FakeHelpers("abcde", current="a")
        _, finish = self.run_harness(helpers, self.state, used={"a": 1, "b": 5, "c": 2, "d": 4, "e": 3})
        helpers.current = "c"
        finish()
        self.assertEqual(helpers.front, "c")
        self.assertEqual(sorted(helpers.closed), ["a", "e"])
        saved = json.loads(pathlib.Path(self.state).read_text())
        self.assertEqual(saved["current"], "c")
        self.assertEqual(sorted(saved["used"]), ["b", "c", "d"])

    def test_new_tabs_are_kept(self):
        helpers = FakeHelpers("abcd", current="a")
        _, finish = self.run_harness(helpers, self.state, used={"a": 1, "b": 2})
        finish()
        self.assertEqual(helpers.closed, ["b"])


class WithHarnessTest(unittest.TestCase):
    def test_after_leading_comment(self):
        code = browser.with_harness("# Открываю почту\nprint(1)")
        lines = code.splitlines()
        self.assertEqual(lines[0], "# Открываю почту")
        self.assertIn("harness.py", lines[1])
        self.assertEqual(lines[2], "print(1)")
        compile(code, "x", "exec")

    def test_only_a_comment(self):
        code = browser.with_harness("# шаг")
        self.assertEqual(code.splitlines()[0], "# шаг")
        compile(code, "x", "exec")

    def test_empty_stays_empty(self):
        self.assertEqual(browser.with_harness("  "), "  ")


class IdleTidyTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.login = pathlib.Path(self.dir.name, "requests")
        self.login.mkdir()
        self.state = pathlib.Path(self.dir.name, "tabs.json")
        self.state.write_text(json.dumps({"current": "b", "used": {"a": 1, "b": 2}, "at": 1000}))
        self.closed = []
        pages = [{"id": i, "type": "page", "url": f"https://{i}.example/"} for i in "abc"]
        pages.append({"id": "w", "type": "service_worker", "url": "https://a.example/sw.js"})

        def urlopen(url, timeout=None):
            if url.endswith("/json/list"):
                return _Resp(json.dumps(pages))
            self.closed.append(url.rsplit("/", 1)[1])
            return _Resp("")
        self.patches = [mock.patch.object(browser, "STATE", str(self.state)),
                        mock.patch.object(browser, "LOGIN", self.login),
                        mock.patch.object(browser.urllib.request, "urlopen", urlopen)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.dir.cleanup()

    def test_keeps_only_the_last_tab_when_idle(self):
        self.assertEqual(len(browser.idle_tidy(now=1000 + browser.IDLE + 1)), 2)
        self.assertEqual(sorted(self.closed), ["a", "c"])

    def test_not_while_recently_used(self):
        self.assertEqual(browser.idle_tidy(now=1000 + 60), [])

    def test_not_while_a_login_waits(self):
        now = 1000 + browser.IDLE + 1
        (self.login / "r.json").write_text(json.dumps({"status": "waiting", "created": now - 60}))
        self.assertEqual(browser.idle_tidy(now=now), [])


class _Resp:
    def __init__(self, body):
        self.body = body

    def read(self):
        return self.body.encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def close(self):
        pass


if __name__ == "__main__":
    unittest.main()
