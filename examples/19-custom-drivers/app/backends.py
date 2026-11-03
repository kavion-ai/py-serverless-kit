"""Custom on-premises drivers, written as plain classes.

The on-prem host loads a class named in ``resources.<name>.options.class`` and
passes the remaining options to its constructor. It calls the methods below; it
handles retries, dead-lettering, logging and the dashboard itself.

These two use only the standard library, so the example runs anywhere:

* :class:`SqliteQueue`  - a durable queue in one SQLite file (visibility timeout,
  receive counts, dead-letter, crash recovery);
* :class:`FolderStorage` - a "bucket" that is a folder, e.g. an NFS / SMB share.

See ``rabbitmq_queue.py`` and ``kafka_queue.py`` for drivers that wrap a client library.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple


def _resolve(path: str) -> Path:
    """Relative paths are relative to the deployed host (``PSKIT_ONPREM_ROOT``)."""
    target = Path(os.path.expanduser(path))
    if not target.is_absolute():
        target = Path(os.environ.get("PSKIT_ONPREM_ROOT") or os.getcwd()) / target
    return target


class SqliteQueue:
    """QueueDriver: ``submit / claim / settle / depth / recover``.

    Options: ``path`` (SQLite file), ``table`` (default ``messages``).
    """

    def __init__(self, path: str, table: str = "messages") -> None:
        if not table.isidentifier():
            raise ValueError(f"invalid table name {table!r}")
        self.path = _resolve(path)
        self.table = table
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._db() as db:
            db.execute(
                f"CREATE TABLE IF NOT EXISTS {self.table} ("
                "id TEXT PRIMARY KEY, body TEXT NOT NULL, attributes TEXT NOT NULL, "
                "receives INTEGER NOT NULL DEFAULT 0, enqueued_at REAL NOT NULL, visible_at REAL NOT NULL)"
            )
            db.execute(f"CREATE INDEX IF NOT EXISTS {self.table}_visible ON {self.table} (visible_at, enqueued_at)")

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.path), timeout=30, isolation_level=None)
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def submit(self, body: str, attributes: Dict[str, Any]) -> str:
        ident = uuid.uuid4().hex
        now = time.time()
        with self._lock, self._db() as db:
            db.execute(
                f"INSERT INTO {self.table} (id, body, attributes, receives, enqueued_at, visible_at) "
                "VALUES (?, ?, ?, 0, ?, ?)",
                (ident, body, json.dumps(attributes or {}), now, 0),
            )
        return ident

    def claim(self, batch: int, visibility: float, now: float) -> List[Dict[str, Any]]:
        with self._lock, self._db() as db:
            rows = db.execute(
                f"SELECT id, body, attributes, receives, enqueued_at FROM {self.table} "
                "WHERE visible_at <= ? ORDER BY enqueued_at LIMIT ?",
                (now, max(1, int(batch))),
            ).fetchall()
            db.executemany(
                f"UPDATE {self.table} SET visible_at = ? WHERE id = ?",
                [(now + visibility, row[0]) for row in rows],
            )
        return [
            {"id": r[0], "body": r[1], "attributes": json.loads(r[2]), "receives": r[3], "enqueued_at": r[4]}
            for r in rows
        ]

    def settle(
        self,
        claimed: List[Dict[str, Any]],
        failed_ids: Set[str],
        max_receive: int,
        dead_letter: Optional[Any],
        now: float,
    ) -> None:
        dead: List[Dict[str, Any]] = []
        with self._lock, self._db() as db:
            for msg in claimed:
                if msg["id"] not in failed_ids:
                    db.execute(f"DELETE FROM {self.table} WHERE id = ?", (msg["id"],))
                    continue
                receives = int(msg.get("receives") or 0) + 1
                if dead_letter is not None and receives >= max_receive:
                    db.execute(f"DELETE FROM {self.table} WHERE id = ?", (msg["id"],))
                    dead.append(dict(msg, receives=receives))
                else:
                    db.execute(
                        f"UPDATE {self.table} SET receives = ?, visible_at = ? WHERE id = ?",
                        (receives, now, msg["id"]),
                    )
        for msg in dead:  # outside our transaction: the DLQ may be this same file
            attrs = dict(msg.get("attributes") or {}, pskit_receives=msg["receives"])
            dead_letter.submit(msg["body"], attrs)  # type: ignore[union-attr]

    def depth(self) -> int:
        with self._lock, self._db() as db:
            return int(db.execute(f"SELECT COUNT(*) FROM {self.table}").fetchone()[0])

    def recover(self, now: float, visibility: float) -> None:
        # Claims expire by themselves (visible_at), so nothing is stuck after a crash.
        return None


class FolderStorage:
    """StorageDriver: ``scan / put / get / delete`` on a folder.

    Options: ``root`` (folder), ``prefix`` (only watch keys under it).
    """

    def __init__(self, root: str, prefix: str = "") -> None:
        self.root = _resolve(root)
        self.prefix = prefix.lstrip("/")
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        parts = [p for p in key.replace("\\", "/").split("/") if p not in ("", ".")]
        if not parts or ".." in parts:
            raise ValueError(f"invalid object key {key!r}")
        return self.root.joinpath(*parts)

    def scan(self) -> Dict[str, Tuple[str, int]]:
        found: Dict[str, Tuple[str, int]] = {}
        for path in self.root.rglob("*"):
            if not path.is_file() or path.name.endswith(".part"):
                continue
            key = path.relative_to(self.root).as_posix()
            if self.prefix and not key.startswith(self.prefix):
                continue
            stat = path.stat()
            etag = hashlib.sha1(f"{stat.st_mtime_ns}:{stat.st_size}".encode(), usedforsecurity=False).hexdigest()
            found[key] = (etag, stat.st_size)
        return found

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".part")  # readers never see half-written files
        tmp.write_bytes(data)
        os.replace(tmp, path)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> bool:
        path = self._path(key)
        if not path.is_file():
            return False
        path.unlink()
        return True
