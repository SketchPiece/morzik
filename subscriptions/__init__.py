"""Expose trusted, context-local cron identity to pre-run scripts without changing Hermes."""

from functools import wraps


def register(ctx):
    from tools.environments import local

    original = local.build_subprocess_env
    if getattr(original, "_morzik_events_identity", False):
        return

    @wraps(original)
    def build_subprocess_env(*args, **kwargs):
        env = original(*args, **kwargs)
        env.pop("MORZIK_CRON_EXECUTION_ID", None)
        env.pop("MORZIK_CRON_JOB_ID", None)
        identity = ctx.current_cron_execution()
        if identity is not None:
            env["MORZIK_CRON_EXECUTION_ID"] = identity.execution_id
            env["MORZIK_CRON_JOB_ID"] = identity.job_id
        return env

    build_subprocess_env._morzik_events_identity = True
    local.build_subprocess_env = build_subprocess_env

    def unload():
        if local.build_subprocess_env is build_subprocess_env:
            local.build_subprocess_env = original

    ctx.on_unload(unload)
