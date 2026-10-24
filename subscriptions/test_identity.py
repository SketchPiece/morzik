import contextvars
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


class IdentityTest(unittest.TestCase):
    def test_context_identity_is_propagated_without_leaking_to_other_runs(self):
        spec = importlib.util.spec_from_file_location("events_plugin", Path(__file__).with_name("__init__.py"))
        plugin = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(plugin)
        identity = contextvars.ContextVar("test_identity", default=None)
        callbacks = []
        ctx = types.SimpleNamespace(current_cron_execution=identity.get, on_unload=callbacks.append)
        original_env = {"PATH": "/bin", "MORZIK_CRON_EXECUTION_ID": "stale", "MORZIK_CRON_JOB_ID": "stale"}
        local = types.SimpleNamespace(build_subprocess_env=lambda **kwargs: dict(original_env))
        modules = {"tools": types.ModuleType("tools"),
                   "tools.environments": types.ModuleType("tools.environments")}
        modules["tools.environments"].local = local
        with patch.dict(sys.modules, modules):
            plugin.register(ctx)
            wrapped = local.build_subprocess_env
            plugin.register(ctx)
            self.assertIs(local.build_subprocess_env, wrapped)
            first, second = contextvars.copy_context(), contextvars.copy_context()
            first.run(identity.set, types.SimpleNamespace(execution_id="one", job_id="job1"))
            second.run(identity.set, types.SimpleNamespace(execution_id="two", job_id="job2"))
            self.assertEqual(first.run(wrapped)["MORZIK_CRON_EXECUTION_ID"], "one")
            self.assertEqual(second.run(wrapped)["MORZIK_CRON_EXECUTION_ID"], "two")
            self.assertEqual(wrapped(), {"PATH": "/bin"})
            self.assertEqual(original_env["MORZIK_CRON_EXECUTION_ID"], "stale")
            self.assertEqual(len(callbacks), 1)
            callbacks[0]()
            self.assertFalse(getattr(local.build_subprocess_env, "_morzik_events_identity", False))


if __name__ == "__main__":
    unittest.main()
