"""Who did what: an append-only, encrypted log kept in the vault and committed with it.

One file per clone and month, so two developers never get a merge conflict. Each line is
``<key index>:<base64 AES-GCM>``, authenticated together with the hash of the line before it, so changing, removing or
reordering lines is detected when reading (cutting the newest lines off a file is not; git history shows that). Anyone
with the master key can append, because every account has to log. Only accounts with read on ``audit`` see entries
through pskit. Never put secret values in an entry.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import socket
import time
from typing import Any, Dict, List, Optional

from . import crypto
from .store import Vault

_SENSITIVE = ("password", "passphrase", "secret", "token", "key", "content", "text", "value", "raw", "env", "master")
_GENESIS = "pskit-audit"


def _writer(vault: Vault) -> str:
    """Names this clone's own log files. Not the machine: two clones on one computer (or a shared CI host) would write
    to one file, and then `git pull` refuses to overwrite its uncommitted lines."""
    path = vault.root / ".pskit" / ".vault" / "audit-writer"
    try:
        return path.read_text("ascii").strip()
    except OSError:
        name = secrets.token_hex(6)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(name.encode("ascii"))
        return name


def safe_details(body: Any) -> Dict[str, Any]:
    """The harmless fields of a request body (names and paths), for the log. Anything that could hold a secret goes."""
    if not isinstance(body, dict):
        return {}
    out: Dict[str, Any] = {}
    for name, value in body.items():
        lowered = str(name).lower()
        if any(word in lowered for word in _SENSITIVE):
            continue
        if isinstance(value, (str, int, float, bool)):
            out[str(name)] = value[:200] if isinstance(value, str) else value
    return out


def record(
    vault: Vault, master: bytes, user: str, source: str, action: str, target: str = "", outcome: str = "ok",
    details: Optional[Dict[str, Any]] = None,
) -> None:
    keys = vault.accounts(master)["audit_keys"]
    index = len(keys) - 1
    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "user": user, "source": source, "action": action,
        "target": target, "outcome": outcome, "details": details or {}, "host": socket.gethostname(),
    }
    folder = vault.dir / "audit"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{time.strftime('%Y-%m', time.gmtime())}-{_writer(vault)}.log"
    previous = _GENESIS
    if path.is_file():
        lines = path.read_text("ascii").splitlines()
        if lines:
            previous = hashlib.sha256(lines[-1].encode("ascii")).hexdigest()
    plain = json.dumps(entry, sort_keys=True).encode("utf-8")
    blob = crypto.seal(crypto.unb64(keys[index]), plain, previous.encode("ascii"))
    with path.open("ab") as handle:
        handle.write(f"{index}:{crypto.b64(blob)}\n".encode("ascii"))


def read(
    vault: Vault, master: bytes, *, user: Optional[str] = None, action: Optional[str] = None, limit: int = 500,
    offset: int = 0,
) -> Dict[str, Any]:
    """A page of the entries, newest first. ``total`` counts every entry that matches the filters, and ``tampered``
    names the files with a line that fails its check, whichever page was asked for."""
    keys = [crypto.unb64(k) for k in vault.accounts(master)["audit_keys"]]
    entries: List[Dict[str, Any]] = []
    tampered: List[str] = []
    folder = vault.dir / "audit"
    for path in sorted(folder.glob("*.log")) if folder.is_dir() else []:
        previous = _GENESIS
        for line in path.read_text("ascii", errors="replace").splitlines():
            try:
                index, encoded = line.split(":", 1)
                plain = crypto.unseal(keys[int(index)], crypto.unb64(encoded), previous.encode("ascii"))
                entries.append(json.loads(plain.decode("utf-8")))
            except Exception:  # noqa: BLE001 - whatever is wrong with the line, it gets reported
                if path.name not in tampered:
                    tampered.append(path.name)
            previous = hashlib.sha256(line.encode("utf-8")).hexdigest()
    if user:
        entries = [e for e in entries if e.get("user") == user]
    if action:
        entries = [e for e in entries if action in str(e.get("action") or "")]
    entries.sort(key=lambda e: str(e.get("ts") or ""), reverse=True)
    limit, offset = max(1, limit), max(0, offset)
    return {
        "entries": entries[offset : offset + limit], "total": len(entries), "offset": offset, "limit": limit,
        "tampered": tampered,
    }
