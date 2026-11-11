"""The secrets: in memory (values in plain text) and in one JSON file, written atomically (mode 600), with the values
encrypted when the keyring has an algorithm. The running store is reached through :func:`db`."""

from __future__ import annotations

import base64
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .ciphers import DecryptError, b64
from .config import log
from .errors import bad_request, invalid, not_found
from .keyring import Keyring, aad_of


class Store:
    """Every secret, in memory (values in plain text) and in one JSON file (values encrypted when the keyring has an
    algorithm). Callers hold ``lock``."""

    def __init__(self, path: Path, keyring: Keyring) -> None:
        self.path = path
        self.keyring = keyring
        self.lock = threading.RLock()
        self.secrets: Dict[str, Dict[str, Any]] = {}
        # (ARN, VersionId) -> the version's "Encrypted" record. Versions never change, so each is sealed once.
        self.sealed: Dict[Tuple[str, str], Dict[str, Any]] = {}
        if path.is_file():
            data = json.loads(path.read_text("utf-8") or "{}")
            self.secrets = {s["Name"]: s for s in data.get("secrets") or []}
            for secret in self.secrets.values():
                for vid, version in secret["Versions"].items():
                    rec = version.pop("Encrypted", None)
                    if rec is None:
                        continue
                    try:
                        plain = keyring.open(rec, aad_of(secret, vid))
                    except (DecryptError, KeyError, ValueError) as exc:
                        raise DecryptError(f"can't decrypt secret {secret['Name']!r} version {vid}: {exc}") from None
                    version[rec["field"]] = plain.decode("utf-8") if rec["field"] == "SecretString" else b64(plain)
                    self.sealed[(secret["ARN"], vid)] = rec

    def stale(self) -> bool:
        """The file doesn't match the settings: plain values to encrypt (or the reverse), or data keys to rewrap."""
        for secret in self.secrets.values():
            kid = self.keyring.key_id(secret.get("KmsKeyId"))
            for vid in secret["Versions"]:
                rec = self.sealed.get((secret["ARN"], vid))
                if bool(rec) != bool(self.keyring.alg) or (rec and rec["kid"] != kid):
                    return True
        return False

    def _on_disk(self, secret: Dict[str, Any]) -> Dict[str, Any]:
        if not self.keyring.alg:
            return secret
        kid = self.keyring.key_id(secret.get("KmsKeyId"))
        versions = {}
        for vid, version in secret["Versions"].items():
            key, aad = (secret["ARN"], vid), aad_of(secret, vid)
            rec = self.sealed.get(key)
            if rec is None:
                field = "SecretString" if "SecretString" in version else "SecretBinary"
                plain = version[field].encode("utf-8") if field == "SecretString" else base64.b64decode(version[field])
                rec = self.keyring.seal(field, plain, aad, kid)
            elif rec["kid"] != kid:
                rec = self.keyring.rewrap(rec, aad, kid)
            self.sealed[key] = rec
            versions[vid] = {**{k: v for k, v in version.items() if k not in ("SecretString", "SecretBinary")},
                             "Encrypted": rec}
        return {**secret, "Versions": versions}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        written = [self._on_disk(self.secrets[n]) for n in sorted(self.secrets)]
        live = {(s["ARN"], vid) for s in self.secrets.values() for vid in s["Versions"]}
        self.sealed = {k: v for k, v in self.sealed.items() if k in live and self.keyring.alg}
        payload = {"format": 2 if self.keyring.alg else 1, "secrets": written}
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(json.dumps(payload, indent=1, sort_keys=True).encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(tmp), str(self.path))

    def purge(self) -> None:
        now = time.time()
        gone = [n for n, s in self.secrets.items() if s.get("DeletionDate") and s["DeletionDate"] <= now]
        for name in gone:
            del self.secrets[name]
            log("purged", name)
        if gone:
            self.save()

    def find(self, secret_id: Any) -> Dict[str, Any]:
        if not isinstance(secret_id, str) or not secret_id:
            raise invalid("SecretId is required.")
        if secret_id in self.secrets:
            return self.secrets[secret_id]
        for secret in self.secrets.values():
            arn = secret["ARN"]
            # A full ARN, or a partial one without the 6-character suffix AWS adds to the name.
            if secret_id == arn or (len(arn) == len(secret_id) + 7 and arn.startswith(secret_id + "-")):
                return secret
        raise not_found()

    def live(self, secret_id: Any) -> Dict[str, Any]:
        secret = self.find(secret_id)
        if secret.get("DeletedDate"):
            raise bad_request("You can't perform this operation on the secret because it was marked for deletion.")
        return secret


_STORE: Optional[Store] = None


def db() -> Store:
    """The running server's store (set by :func:`set_store` in ``main``)."""
    if _STORE is None:
        raise RuntimeError("the store is not loaded")
    return _STORE


def set_store(store: Store) -> None:
    global _STORE
    _STORE = store
