"""Cryptographic primitives of the vault: AES-256-GCM, scrypt, HKDF-SHA256 and X25519 key wrapping.

Everything here comes from ``cryptography`` / ``hashlib``; nothing is hand-rolled.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import os
from typing import Dict

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .errors import VaultError

KEY_BYTES = 32
NONCE_BYTES = 12
# About 128 MiB and a few hundred ms per guess. Stored per account, so this can be raised later.
SCRYPT_N = 2**17
SCRYPT_R = 8
SCRYPT_P = 1
# A value outside this range in a vault file is refused: low makes guessing cheap, high exhausts memory.
SCRYPT_MIN_N = 2**14
SCRYPT_MAX_N = 2**20


def random_key() -> bytes:
    return os.urandom(KEY_BYTES)


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def unb64(text: str) -> bytes:
    try:
        return base64.b64decode(text.encode("ascii"), validate=True)
    except (binascii.Error, UnicodeEncodeError, AttributeError) as exc:
        raise VaultError("the vault file is damaged", 500, "damaged") from exc


def hkdf(key: bytes, info: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=KEY_BYTES, salt=None, info=b"pskit-vault:" + info).derive(key)


def mac(key: bytes, data: bytes) -> bytes:
    return hmac.new(key, data, hashlib.sha256).digest()


def seal(key: bytes, plain: bytes, aad: bytes) -> bytes:
    """nonce + AES-256-GCM ciphertext and tag. Random nonce: every key here encrypts far under 2^32 messages."""
    nonce = os.urandom(NONCE_BYTES)
    return nonce + AESGCM(key).encrypt(nonce, plain, aad)


def unseal(key: bytes, blob: bytes, aad: bytes) -> bytes:
    """Raises InvalidTag for a wrong key or a changed ciphertext or context."""
    return AESGCM(key).decrypt(blob[:NONCE_BYTES], blob[NONCE_BYTES:], aad)


def password_key(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    if not SCRYPT_MIN_N <= n <= SCRYPT_MAX_N or r != SCRYPT_R or p != SCRYPT_P:
        raise VaultError("the vault has unsafe key derivation settings; refusing to use them", 500, "damaged")
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=2**31 - 1, dklen=KEY_BYTES
    )


def new_keypair() -> Dict[str, bytes]:
    private = X25519PrivateKey.generate()
    return {"private": _private_bytes(private), "public": _public_bytes(private.public_key())}


def public_of(private: bytes) -> bytes:
    return _public_bytes(X25519PrivateKey.from_private_bytes(private).public_key())


def _private_bytes(key: X25519PrivateKey) -> bytes:
    return key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())


def _public_bytes(key: X25519PublicKey) -> bytes:
    return key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)


def wrap(key: bytes, recipient_public: bytes, context: bytes) -> Dict[str, str]:
    """Encrypt ``key`` to a public key, so an admin can grant access without knowing the user's password."""
    ephemeral = X25519PrivateKey.generate()
    shared = ephemeral.exchange(X25519PublicKey.from_public_bytes(recipient_public))
    ephemeral_public = _public_bytes(ephemeral.public_key())
    wrapping = hkdf(shared, b"wrap:" + ephemeral_public + recipient_public + context)
    return {"eph": b64(ephemeral_public), "ct": b64(seal(wrapping, key, context))}


def unwrap(entry: Dict[str, str], private: bytes, context: bytes) -> bytes:
    key = X25519PrivateKey.from_private_bytes(private)
    ephemeral_public = unb64(entry["eph"])
    shared = key.exchange(X25519PublicKey.from_public_bytes(ephemeral_public))
    wrapping = hkdf(shared, b"wrap:" + ephemeral_public + public_of(private) + context)
    return unseal(wrapping, unb64(entry["ct"]), context)


def format_secret(prefix: str, raw: bytes) -> str:
    """Printable key with a checksum, so a typo is told apart from a wrong key."""
    check = hashlib.sha256(prefix.encode("ascii") + raw).digest()[:2]
    text = base64.b32encode(raw + check).decode("ascii").rstrip("=")
    return prefix + "-" + "-".join(text[i : i + 5] for i in range(0, len(text), 5))


def parse_secret(prefix: str, text: str, what: str) -> bytes:
    cleaned = "".join(str(text or "").split())
    if not cleaned.lower().startswith(prefix + "-"):
        raise VaultError(f"that is not a {what} (it starts with {prefix}-)", 400, "bad_key")
    body = cleaned[len(prefix) + 1 :].replace("-", "").upper()
    try:
        data = base64.b32decode(body + "=" * (-len(body) % 8))
    except (binascii.Error, ValueError):
        raise VaultError(f"that is not a valid {what}", 400, "bad_key") from None
    raw, check = data[:-2], data[-2:]
    if len(raw) != KEY_BYTES or not hmac.compare_digest(check, hashlib.sha256(prefix.encode("ascii") + raw).digest()[:2]):
        raise VaultError(f"that {what} has a typo", 400, "bad_key")
    return raw


__all__ = [
    "InvalidTag", "SCRYPT_N", "SCRYPT_P", "SCRYPT_R", "b64", "format_secret", "hkdf", "mac", "new_keypair",
    "parse_secret", "password_key", "public_of", "random_key", "seal", "unb64", "unseal", "unwrap", "wrap",
]
