"""Push notifications to the Morzik App through APNs.

The team's .p8 key (the same one Volna and Helm use) signs an ES256 provider token; APNs wants HTTP/2,
which httpx here can't do without h2, so each push is one ``curl --http2`` call. Pushes are rare (only
when no phone is connected), so there is no connection to keep.
"""

import asyncio
import json
import logging
import time

logger = logging.getLogger(__name__)

HOSTS = {"development": "api.sandbox.push.apple.com", "production": "api.push.apple.com"}


class Apns:
    def __init__(self, key_path: str, key_id: str, team_id: str, topic: str):
        self.key_path, self.key_id, self.team_id, self.topic = key_path, key_id, team_id, topic
        self._jwt: tuple[str, float] | None = None

    @property
    def configured(self) -> bool:
        return bool(self.key_path and self.key_id and self.team_id and self.topic)

    def provider_token(self, now: float | None = None) -> str:
        """APNs accepts a token for up to an hour and dislikes frequent changes: renewed every 50 minutes."""
        now = now if now is not None else time.time()
        if self._jwt and now - self._jwt[1] < 50 * 60:
            return self._jwt[0]
        import jwt  # pyjwt + cryptography ship with Hermes
        with open(self.key_path, "rb") as f:
            key = f.read()
        token = jwt.encode({"iss": self.team_id, "iat": int(now)}, key, algorithm="ES256", headers={"kid": self.key_id})
        self._jwt = (token, now)
        return token

    async def _post(self, env: str, device_token: str, payload: dict, collapse_id: str | None) -> tuple[int, str]:
        url = f"https://{HOSTS[env]}/3/device/{device_token}"
        args = ["curl", "-sS", "--http2", "--max-time", "15", "-o", "-", "-w", "\n%{http_code}",
                "-H", f"authorization: bearer {self.provider_token()}", "-H", f"apns-topic: {self.topic}",
                "-H", "apns-push-type: alert", "-H", "apns-priority: 10",
                "-H", "content-type: application/json", "--data-binary", "@-", url]
        if collapse_id:
            args[-3:-3] = ["-H", f"apns-collapse-id: {collapse_id}"]
        proc = await asyncio.create_subprocess_exec(*args, stdin=asyncio.subprocess.PIPE,
                                                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, err = await proc.communicate(json.dumps(payload, ensure_ascii=False).encode())
        body, _, code = out.decode(errors="replace").rpartition("\n")
        try:
            status = int(code)
        except ValueError:
            return 0, err.decode(errors="replace")[:200]
        reason = ""
        if body.strip():
            try:
                reason = json.loads(body).get("reason", "")
            except ValueError:
                reason = body[:200]
        return status, reason

    async def send(self, device_token: str, env: str, payload: dict, collapse_id: str | None = None) -> tuple[bool, str, str]:
        """(delivered, env that answered, reason). A build signed for development has sandbox tokens even
        when it calls itself production (and the other way round): on BadDeviceToken the other env is tried."""
        env = env if env in HOSTS else "development"
        status, reason = await self._post(env, device_token, payload, collapse_id)
        if status == 400 and reason == "BadDeviceToken":
            other = "production" if env == "development" else "development"
            status2, reason2 = await self._post(other, device_token, payload, collapse_id)
            if status2 == 200:
                return True, other, ""
            status, reason = status2, reason2 or reason
        if status != 200:
            logger.warning("morzik-app: APNs %s %s", status, reason)
        return status == 200, env, reason
