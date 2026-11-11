"""Envelope encryption, as AWS does with KMS.

Every secret version gets its own random 256-bit data key (DEK) that encrypts the value; the DEK is stored wrapped
(AES-256-GCM) by a master key (``SM_MASTER_KEY`` / ``SM_MASTER_KEYS``). The value's associated data is
``ARN|VersionId``, so a ciphertext can't be moved to another secret or version.
"""

from __future__ import annotations

import base64
import secrets
from typing import Any, Dict

from .ciphers import ALGORITHMS, DecryptError, aes_gcm_decrypt, aes_gcm_encrypt, b64
from .errors import bad_request


class Keyring:
    """The master keys (``SM_MASTER_KEY`` is key id ``default``, ``SM_MASTER_KEYS=id:key,...`` adds more), the
    algorithm new versions are encrypted with (``SM_ENCRYPTION``) and the key id they are wrapped with."""

    def __init__(self, env: Any) -> None:
        self.keys: Dict[str, bytes] = {}
        if env.get("SM_MASTER_KEY"):
            self.keys["default"] = self._key("SM_MASTER_KEY", env["SM_MASTER_KEY"])
        for pair in (env.get("SM_MASTER_KEYS") or "").split(","):
            if not pair.strip():
                continue
            kid, sep, value = pair.strip().partition(":")
            if not sep or not kid.strip() or not value.strip():
                raise ValueError("SM_MASTER_KEYS must be id1:base64key,id2:base64key")
            self.keys[kid.strip()] = self._key(f"SM_MASTER_KEYS ({kid.strip()})", value.strip())
        self.current = (env.get("SM_MASTER_KEY_ID") or "").strip() or \
            ("default" if "default" in self.keys else min(self.keys, default="default"))
        mode = (env.get("SM_ENCRYPTION") or "").strip().lower()
        names = {v[0]: k for k, v in ALGORITHMS.items()}
        if mode not in ("", "off", *names):
            raise ValueError(f"SM_ENCRYPTION must be one of {', '.join(names)} or off")
        self.alg = "" if mode == "off" or (not mode and not self.keys) else names[mode or "aes-256-gcm"]
        if self.alg and not self.keys:
            raise ValueError(f"SM_ENCRYPTION={mode} needs a master key: set SM_MASTER_KEY (32 bytes, base64)")
        if self.alg and self.current not in self.keys:
            raise ValueError(f"SM_MASTER_KEY_ID {self.current!r} is not in SM_MASTER_KEY / SM_MASTER_KEYS")

    @staticmethod
    def _key(name: str, value: str) -> bytes:
        try:
            raw = base64.b64decode(value.strip(), validate=True)
        except ValueError:
            raw = b""
        if len(raw) != 32:
            raise ValueError(f"{name} must be 32 random bytes in base64 (openssl rand -base64 32)")
        return raw

    def key_id(self, kms_key_id: Any, strict: bool = False) -> str:
        """The master key id a secret's ``KmsKeyId`` names (an id, ``alias/<id>``, or a KMS ARN ending in one).
        ``aws/secretsmanager`` and no KmsKeyId mean the current key."""
        if not kms_key_id:
            return self.current
        name = str(kms_key_id).rsplit(":", 1)[-1]
        for prefix in ("alias/", "key/"):
            if name.startswith(prefix):
                name = name[len(prefix):]
        if name == "aws/secretsmanager":
            return self.current
        if name in self.keys:
            return name
        if strict and self.alg:
            raise bad_request(f"KmsKeyId {kms_key_id} is not a master key of this server "
                           f"(known: {', '.join(sorted(self.keys))}).")
        return self.current

    def _wrap(self, dek: bytes, kid: str, aad: bytes) -> Dict[str, str]:
        iv = secrets.token_bytes(12)
        ct, tag = aes_gcm_encrypt(self.keys[kid], iv, dek, aad + b"|" + kid.encode("utf-8"))
        return {"kid": kid, "dek": b64(ct + tag), "dek_iv": b64(iv)}

    def _unwrap(self, rec: Dict[str, Any], aad: bytes) -> bytes:
        kid = str(rec.get("kid"))
        if kid not in self.keys:
            raise DecryptError(f"master key {kid!r} is not set (SM_MASTER_KEY / SM_MASTER_KEYS)")
        blob = base64.b64decode(rec["dek"])
        try:
            return aes_gcm_decrypt(self.keys[kid], base64.b64decode(rec["dek_iv"]), blob[:-16], blob[-16:],
                                   aad + b"|" + kid.encode("utf-8"))
        except DecryptError:
            raise DecryptError(f"master key {kid!r} does not open the data key (wrong key?)") from None

    def seal(self, field: str, plain: bytes, aad: bytes, kid: str) -> Dict[str, str]:
        _mode, size, encrypt, _decrypt = ALGORITHMS[self.alg]
        dek, iv = secrets.token_bytes(32), secrets.token_bytes(size)
        ct, tag = encrypt(dek, iv, plain, aad)
        return {"alg": self.alg, "field": field, "iv": b64(iv), "ct": b64(ct), "tag": b64(tag),
                **self._wrap(dek, kid, aad)}

    def open(self, rec: Dict[str, Any], aad: bytes) -> bytes:
        if rec.get("alg") not in ALGORITHMS:
            raise DecryptError(f"unknown algorithm {rec.get('alg')!r}")
        dek = self._unwrap(rec, aad)
        try:
            return ALGORITHMS[rec["alg"]][3](dek, base64.b64decode(rec["iv"]), base64.b64decode(rec["ct"]),
                                             base64.b64decode(rec["tag"]), aad)
        except DecryptError:
            raise DecryptError("the value's tag does not match (the data was changed)") from None

    def rewrap(self, rec: Dict[str, Any], aad: bytes, kid: str) -> Dict[str, str]:
        """The same ciphertext with its data key wrapped by master key ``kid``."""
        return {**rec, **self._wrap(self._unwrap(rec, aad), kid, aad)}


def aad_of(secret: Dict[str, Any], vid: str) -> bytes:
    return f"{secret['ARN']}|{vid}".encode("utf-8")
