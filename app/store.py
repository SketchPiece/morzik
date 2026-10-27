"""Morzik App storage: the chat, devices and sign-in codes, in one SQLite file. No Hermes imports.

Sync is built on two numbers per message:
- ``seq`` — its place in the chat, never changes (the app sorts by it);
- ``rev`` — bumped from one counter on every insert or change (button taken away, read mark, deletion).

The app keeps the highest ``rev`` it has seen and asks for everything after it, so a dropped connection, a
killed app or a phone offline for a day all end the same way: one request brings the chat up to date.
Sending is idempotent: the app picks ``client_id`` for each outgoing message and resends until it gets an
answer; a repeat returns the stored message instead of a second copy.
"""

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  id TEXT NOT NULL UNIQUE,
  client_id TEXT UNIQUE,
  role TEXT NOT NULL,               -- 'user' | 'morzik'
  text TEXT NOT NULL DEFAULT '',
  media TEXT,                       -- JSON: {id, kind, mime, name, size, duration, width, height, url}
  buttons TEXT,                     -- JSON list: {id, title, kind: 'login'|'url'|'reply'|'approval', value}
  status TEXT NOT NULL DEFAULT 'sent',  -- user messages: 'sent' | 'read'
  deleted INTEGER NOT NULL DEFAULT 0,
  created REAL NOT NULL,
  rev INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS messages_rev ON messages(rev);
CREATE TABLE IF NOT EXISTS devices (
  id TEXT PRIMARY KEY,
  token_hash TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL DEFAULT '',
  created REAL NOT NULL,
  last_seen REAL NOT NULL,
  apns_token TEXT,
  apns_env TEXT,
  read_seq INTEGER NOT NULL DEFAULT 0,
  revoked INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

PUBLIC_FIELDS = ("id", "seq", "rev", "client_id", "role", "text", "status", "deleted", "created")
# Columns added after the first release: (name, definition), added to old databases on open.
LATER_COLUMNS = (("reactions", "TEXT"),  # JSON list of the user's emoji on a message
                 ("reply", "TEXT"))      # JSON: {id, role, quote} — the message (or the fragment of it) answered
CODE_TTL = 10 * 60
CODE_ATTEMPTS = 5
CODE_MIN_INTERVAL = 30
CODES_PER_DAY = 10


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Store:
    """Thread-safe: the gateway's event loop and tool threads (request_login) both write here."""

    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True, mode=0o700)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=NORMAL")
        self._db.executescript(SCHEMA)
        have = {r["name"] for r in self._db.execute("PRAGMA table_info(messages)")}
        for name, kind in LATER_COLUMNS:
            if name not in have:
                self._db.execute(f"ALTER TABLE messages ADD COLUMN {name} {kind}")
        os.chmod(path, 0o600)
        self._codes: dict[str, dict] = {}
        self._code_log: list[float] = []

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # --- revisions -------------------------------------------------------------------------

    def _next_rev(self) -> int:
        row = self._db.execute("SELECT value FROM meta WHERE key='rev'").fetchone()
        rev = (int(row["value"]) if row else 0) + 1
        self._db.execute("INSERT INTO meta(key, value) VALUES('rev', ?) "
                         "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(rev),))
        return rev

    def current_rev(self) -> int:
        with self._lock:
            row = self._db.execute("SELECT value FROM meta WHERE key='rev'").fetchone()
            return int(row["value"]) if row else 0

    # --- messages --------------------------------------------------------------------------

    @staticmethod
    def public(row) -> dict:
        if row is None:
            return None
        out = {k: row[k] for k in PUBLIC_FIELDS}
        out["deleted"] = bool(out["deleted"])
        out["media"] = json.loads(row["media"]) if row["media"] else None
        out["buttons"] = json.loads(row["buttons"]) if row["buttons"] else []
        out["reactions"] = json.loads(row["reactions"]) if row["reactions"] else []
        out["reply"] = json.loads(row["reply"]) if row["reply"] else None
        out["created"] = int(row["created"] * 1000)
        return out

    def _get(self, message_id: str):
        return self._db.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone()

    def get(self, message_id: str) -> dict | None:
        with self._lock:
            return self.public(self._get(message_id))

    def add(self, role: str, text: str = "", *, client_id: str | None = None, media: dict | None = None,
            buttons: list | None = None, reply: dict | None = None, now: float | None = None) -> tuple[dict, bool]:
        """Store a message; returns (message, created). A known client_id returns the stored one."""
        with self._lock:
            if client_id:
                row = self._db.execute("SELECT * FROM messages WHERE client_id=?", (client_id,)).fetchone()
                if row is not None:
                    return self.public(row), False
            self._db.execute("BEGIN IMMEDIATE")
            try:
                rev = self._next_rev()
                message_id = secrets.token_hex(8)
                self._db.execute(
                    "INSERT INTO messages(id, client_id, role, text, media, buttons, reply, status, created, rev) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (message_id, client_id or None, role, text or "", json.dumps(media, ensure_ascii=False) if media else None,
                     json.dumps(buttons, ensure_ascii=False) if buttons else None,
                     json.dumps(reply, ensure_ascii=False) if reply else None,
                     "sent", now if now is not None else time.time(), rev))
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                raise
            return self.public(self._get(message_id)), True

    def update(self, message_id: str, **fields) -> dict | None:
        """Change text/buttons/status/deleted of a message and give it a new rev."""
        allowed = {"text", "buttons", "status", "deleted", "media", "reactions"}
        sets, values = [], []
        for key, value in fields.items():
            if key not in allowed:
                raise ValueError(key)
            if key in ("buttons", "media", "reactions"):
                value = json.dumps(value, ensure_ascii=False) if value else None
            if key == "deleted":
                value = 1 if value else 0
            sets.append(f"{key}=?")
            values.append(value)
        with self._lock:
            if self._get(message_id) is None:
                return None
            self._db.execute("BEGIN IMMEDIATE")
            try:
                rev = self._next_rev()
                self._db.execute(f"UPDATE messages SET {', '.join(sets)}, rev=? WHERE id=?", (*values, rev, message_id))
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                raise
            return self.public(self._get(message_id))

    def mark_read_until(self, seq: int) -> list[dict]:
        """Morzik has read the user's messages up to seq: they turn 'read'. Returns the changed ones."""
        with self._lock:
            ids = [r["id"] for r in self._db.execute(
                "SELECT id FROM messages WHERE role='user' AND status='sent' AND seq<=?", (seq,))]
            return [self.update(i, status="read") for i in ids]

    def since(self, rev: int, limit: int = 500) -> tuple[list[dict], bool]:
        """Everything changed after rev, oldest change first; (messages, more)."""
        with self._lock:
            rows = self._db.execute("SELECT * FROM messages WHERE rev>? ORDER BY rev LIMIT ?", (rev, limit + 1)).fetchall()
        return [self.public(r) for r in rows[:limit]], len(rows) > limit

    def tail(self, limit: int = 60) -> list[dict]:
        """The latest messages, in chat order (first open on a new phone)."""
        with self._lock:
            rows = self._db.execute("SELECT * FROM messages WHERE deleted=0 ORDER BY seq DESC LIMIT ?", (limit,)).fetchall()
        return [self.public(r) for r in reversed(rows)]

    def before(self, seq: int, limit: int = 60) -> list[dict]:
        """Older messages for scrolling up, in chat order."""
        with self._lock:
            rows = self._db.execute("SELECT * FROM messages WHERE deleted=0 AND seq<? ORDER BY seq DESC LIMIT ?",
                                    (seq, limit)).fetchall()
        return [self.public(r) for r in reversed(rows)]

    def last_seq(self) -> int:
        with self._lock:
            row = self._db.execute("SELECT MAX(seq) AS s FROM messages").fetchone()
            return int(row["s"] or 0)

    def unread(self, device_id: str) -> int:
        with self._lock:
            row = self._db.execute("SELECT read_seq FROM devices WHERE id=?", (device_id,)).fetchone()
            read = int(row["read_seq"]) if row else 0
            return int(self._db.execute("SELECT COUNT(*) AS n FROM messages WHERE role='morzik' AND deleted=0 AND seq>?",
                                        (read,)).fetchone()["n"])

    def recent_text(self, limit: int = 20) -> list[dict]:
        with self._lock:
            rows = self._db.execute("SELECT role, text, created, media FROM messages WHERE deleted=0 "
                                    "ORDER BY seq DESC LIMIT ?", (limit,)).fetchall()
        return [{"role": r["role"], "text": r["text"], "created": r["created"]} for r in reversed(rows)]

    # --- devices ---------------------------------------------------------------------------

    def add_device(self, name: str, now: float | None = None) -> tuple[str, str]:
        """A new signed-in phone: (device_id, token). Only the token's hash is kept."""
        now = now if now is not None else time.time()
        token, device_id = secrets.token_urlsafe(32), secrets.token_hex(6)
        with self._lock:
            self._db.execute("INSERT INTO devices(id, token_hash, name, created, last_seen, read_seq) VALUES(?,?,?,?,?,?)",
                             (device_id, token_hash(token), name[:80], now, now, self.last_seq()))
        return device_id, token

    def device_for(self, token: str) -> dict | None:
        if not token:
            return None
        digest = token_hash(token)
        with self._lock:
            row = self._db.execute("SELECT * FROM devices WHERE token_hash=? AND revoked=0", (digest,)).fetchone()
            if row is None or not hmac.compare_digest(row["token_hash"], digest):
                return None
            return dict(row)

    def touch(self, device_id: str, now: float | None = None) -> None:
        with self._lock:
            self._db.execute("UPDATE devices SET last_seen=? WHERE id=?", (now or time.time(), device_id))

    def set_push(self, device_id: str, apns_token: str, env: str) -> None:
        with self._lock:
            # A push token belongs to one install: drop it from any older device record.
            self._db.execute("UPDATE devices SET apns_token=NULL WHERE apns_token=? AND id<>?", (apns_token, device_id))
            self._db.execute("UPDATE devices SET apns_token=?, apns_env=? WHERE id=?", (apns_token, env, device_id))

    def drop_push(self, apns_token: str) -> None:
        with self._lock:
            self._db.execute("UPDATE devices SET apns_token=NULL WHERE apns_token=?", (apns_token,))

    def set_read(self, device_id: str, seq: int) -> None:
        with self._lock:
            self._db.execute("UPDATE devices SET read_seq=MAX(read_seq, ?) WHERE id=?", (int(seq), device_id))

    def push_devices(self) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._db.execute(
                "SELECT * FROM devices WHERE revoked=0 AND apns_token IS NOT NULL")]

    def devices(self) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._db.execute("SELECT id, name, created, last_seen, revoked FROM devices")]

    def revoke(self, device_id: str) -> bool:
        with self._lock:
            return self._db.execute("UPDATE devices SET revoked=1, apns_token=NULL WHERE id=?",
                                    (device_id,)).rowcount > 0

    # --- sign-in codes (kept in memory: a restart just means asking for a new one) ----------

    def new_code(self, name: str, now: float | None = None) -> tuple[str, str] | None:
        """(pairing_id, six-digit code), or None when asked too often."""
        now = now if now is not None else time.time()
        with self._lock:
            self._code_log = [t for t in self._code_log if now - t < 86400]
            if len(self._code_log) >= CODES_PER_DAY or (self._code_log and now - self._code_log[-1] < CODE_MIN_INTERVAL):
                return None
            self._code_log.append(now)
            self._codes = {k: v for k, v in self._codes.items() if now - v["created"] < CODE_TTL}
            pairing_id, code = secrets.token_hex(8), f"{secrets.randbelow(10 ** 6):06d}"
            self._codes[pairing_id] = {"code": code, "name": name[:80], "created": now, "attempts": 0}
            return pairing_id, code

    def redeem(self, pairing_id: str, code: str, now: float | None = None) -> tuple[str, str] | str:
        """(device_id, token) for the right code; otherwise 'expired' | 'wrong' | 'locked'."""
        now = now if now is not None else time.time()
        with self._lock:
            entry = self._codes.get(pairing_id)
            if entry is None or now - entry["created"] > CODE_TTL:
                self._codes.pop(pairing_id, None)
                return "expired"
            if entry["attempts"] >= CODE_ATTEMPTS:
                return "locked"
            entry["attempts"] += 1
            if not hmac.compare_digest(entry["code"], (code or "").strip()):
                return "locked" if entry["attempts"] >= CODE_ATTEMPTS else "wrong"
            del self._codes[pairing_id]
        return self.add_device(entry["name"], now)
