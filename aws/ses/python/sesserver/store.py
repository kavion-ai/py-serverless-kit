"""Everything the server keeps, in memory and on disk under ``SES_DATA_DIR``:

``ses.json``                the account settings, identities (with their DKIM keys), templates, configuration sets
                            and the suppression list; one JSON file written atomically (mode 600)
``messages/<id>.json``      one record per message: envelope, status per recipient, events
``messages/<id>.eml``       the message as sent (CRLF, DKIM-signed)

The Node.js server reads and writes the same files. The running store is reached through :func:`db`; callers hold
``lock`` while they read or change it.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import MESSAGES_DIR, RETENTION_DAYS, STORE_FILE, log

FORMAT = 1


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(json.dumps(data, indent=1, sort_keys=True).encode("utf-8"))
        handle.flush()
        os.fsync(handle.fileno())
    for attempt in range(50):
        try:
            os.replace(str(tmp), str(path))
            return
        except PermissionError:  # Windows: a reader has the file open; it closes it in a moment
            if attempt == 49:
                raise
            time.sleep(0.02)


class Store:
    def __init__(self, path: Path = STORE_FILE, messages_dir: Path = MESSAGES_DIR) -> None:
        self.path, self.messages_dir = path, messages_dir
        self.lock = threading.RLock()
        self.account: Dict[str, Any] = {"SendingEnabled": True, "SuppressedReasons": ["BOUNCE", "COMPLAINT"]}
        self.identities: Dict[str, Dict[str, Any]] = {}
        self.templates: Dict[str, Dict[str, Any]] = {}
        self.configuration_sets: Dict[str, Dict[str, Any]] = {}
        self.suppressed: Dict[str, Dict[str, Any]] = {}
        self.messages: Dict[str, Dict[str, Any]] = {}
        if path.is_file():
            data = json.loads(path.read_text("utf-8") or "{}")
            self.account.update(data.get("account") or {})
            self.identities = data.get("identities") or {}
            self.templates = data.get("templates") or {}
            self.configuration_sets = data.get("configuration_sets") or {}
            self.suppressed = data.get("suppressed") or {}
        if messages_dir.is_dir():
            for item in sorted(messages_dir.glob("*.json")):
                try:
                    rec = json.loads(item.read_text("utf-8"))
                    self.messages[str(rec["MessageId"])] = rec
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    log("skipping unreadable message record", item.name, repr(exc))

    def save(self) -> None:
        with self.lock:
            write_json(self.path, {
                "format": FORMAT, "account": self.account, "identities": self.identities,
                "templates": self.templates, "configuration_sets": self.configuration_sets,
                "suppressed": self.suppressed,
            })

    # ------------------------------------------------------------------ messages

    def save_message(self, rec: Dict[str, Any], raw: Optional[bytes] = None) -> None:
        with self.lock:
            self.messages[rec["MessageId"]] = rec
            if raw is not None:
                path = self.messages_dir / f"{rec['MessageId']}.eml"
                path.parent.mkdir(parents=True, exist_ok=True)
                fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, "wb") as handle:
                    handle.write(raw)
            write_json(self.messages_dir / f"{rec['MessageId']}.json", rec)

    def raw(self, message_id: str) -> bytes:
        return (self.messages_dir / f"{message_id}.eml").read_bytes()

    def delete_message(self, message_id: str) -> None:
        with self.lock:
            self.messages.pop(message_id, None)
            for ext in (".json", ".eml"):
                try:
                    (self.messages_dir / f"{message_id}{ext}").unlink()
                except OSError:
                    pass

    def purge(self) -> int:
        """Remove finished messages older than ``SES_RETENTION_DAYS`` (at least one day: the quota counts them)."""
        cutoff = time.time() - max(RETENTION_DAYS, 1) * 86400
        with self.lock:
            old = [m for m, r in self.messages.items() if r["Timestamp"] < cutoff and r.get("Status") not in
                   ("QUEUED", "DELAYED", "SENDING")]
        for message_id in old:
            self.delete_message(message_id)
        return len(old)

    def recent(self, since: float) -> List[Dict[str, Any]]:
        with self.lock:
            return [r for r in self.messages.values() if r["Timestamp"] >= since]


_STORE: Optional[Store] = None


def db() -> Store:
    if _STORE is None:
        raise RuntimeError("the store is not loaded")
    return _STORE


def set_store(store: Store) -> None:
    global _STORE
    _STORE = store
