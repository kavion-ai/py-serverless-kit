"""RSA for DKIM, in pure Python: key generation, DER encoding (PKCS#1, PKCS#8, SubjectPublicKeyInfo) and
RSASSA-PKCS1-v1_5 signatures with SHA-256.

Keys are stored as base64 DER of the PKCS#1 ``RSAPrivateKey`` (what ``openssl genrsa -traditional`` writes without
the PEM lines), which Node.js reads with ``crypto.createPrivateKey({format: "der", type: "pkcs1"})``. Bring-your-own
keys may be PKCS#1 or PKCS#8, PEM or bare base64.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from typing import List, Tuple

_SMALL_PRIMES = [p for p in range(3, 2000, 2) if all(p % d for d in range(3, int(p ** 0.5) + 1, 2))]
_RSA_OID = bytes.fromhex("06092a864886f70d0101010500")  # rsaEncryption OID + NULL
_SHA256_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")


def _probable_prime(n: int, rounds: int = 40) -> bool:
    for p in _SMALL_PRIMES:
        if n % p == 0:
            return n == p
    d, r = n - 1, 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for _ in range(rounds):
        a = secrets.randbelow(n - 3) + 2
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(r - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def _prime(bits: int, e: int) -> int:
    while True:
        cand = secrets.randbits(bits) | (1 << (bits - 1)) | (1 << (bits - 2)) | 1
        if (cand - 1) % e and _probable_prime(cand):
            return cand


class Key:
    """An RSA private key (``n``, ``e``, ``d``, ``p``, ``q``)."""

    def __init__(self, n: int, e: int, d: int, p: int, q: int) -> None:
        self.n, self.e, self.d, self.p, self.q = n, e, d, p, q

    @classmethod
    def generate(cls, bits: int = 2048, e: int = 65537) -> Key:
        while True:
            p, q = _prime(bits // 2, e), _prime(bits - bits // 2, e)
            if p == q:
                continue
            n = p * q
            if n.bit_length() != bits:
                continue
            d = pow(e, -1, (p - 1) * (q - 1) // _gcd(p - 1, q - 1))
            return cls(n, e, d, max(p, q), min(p, q))

    @property
    def bits(self) -> int:
        return self.n.bit_length()

    # ------------------------------------------------------------------ DER

    def pkcs1(self) -> bytes:
        p, q = self.p, self.q
        return _seq(_int(0), _int(self.n), _int(self.e), _int(self.d), _int(p), _int(q), _int(self.d % (p - 1)),
                    _int(self.d % (q - 1)), _int(pow(q, -1, p)))

    def spki(self) -> bytes:
        """SubjectPublicKeyInfo: what goes in the DKIM DNS record (``p=``) in base64."""
        return _seq(_seq_raw(_RSA_OID), b"\x03" + _len(len(_seq(_int(self.n), _int(self.e))) + 1) + b"\x00"
                    + _seq(_int(self.n), _int(self.e)))

    def private_b64(self) -> str:
        return base64.b64encode(self.pkcs1()).decode("ascii")

    def public_b64(self) -> str:
        return base64.b64encode(self.spki()).decode("ascii")

    @classmethod
    def load(cls, text: str) -> Key:
        """A key from PEM or bare base64, PKCS#1 or PKCS#8."""
        lines = [ln.strip() for ln in str(text).strip().splitlines() if ln.strip() and not ln.startswith("-----")]
        der = base64.b64decode("".join(lines), validate=False)
        items = _parse_seq(der)
        if len(items) >= 3 and items[1][0] == 0x30:  # PKCS#8: version, AlgorithmIdentifier, OCTET STRING
            items = _parse_seq(items[2][1])
        ints = [_from_int(v) for tag, v in items if tag == 0x02]
        if len(ints) < 6:
            raise ValueError("not an RSA private key")
        _v, n, e, d, p, q = ints[:6]
        if p * q != n:
            raise ValueError("not an RSA private key")
        return cls(n, e, d, p, q)

    # ------------------------------------------------------------------ signatures

    def sign_sha256(self, data: bytes) -> bytes:
        k = (self.n.bit_length() + 7) // 8
        digest = _SHA256_PREFIX + hashlib.sha256(data).digest()
        em = b"\x00\x01" + b"\xff" * (k - len(digest) - 3) + b"\x00" + digest
        m = int.from_bytes(em, "big")
        # Chinese remainder theorem: four times faster than pow(m, d, n).
        p, q = self.p, self.q
        s1, s2 = pow(m, self.d % (p - 1), p), pow(m, self.d % (q - 1), q)
        s = s2 + q * ((pow(q, -1, p) * (s1 - s2)) % p)
        return s.to_bytes(k, "big")


def verify_sha256(spki_b64: str, data: bytes, signature: bytes) -> bool:
    """Check a signature with a public key (SubjectPublicKeyInfo in base64)."""
    outer = _parse_seq(base64.b64decode(spki_b64))
    bits = outer[1][1][1:]
    n, e = (_from_int(v) for _t, v in _parse_seq(bits))
    k = (n.bit_length() + 7) // 8
    em = pow(int.from_bytes(signature, "big"), e, n).to_bytes(k, "big")
    digest = _SHA256_PREFIX + hashlib.sha256(data).digest()
    return em == b"\x00\x01" + b"\xff" * (k - len(digest) - 3) + b"\x00" + digest


def _gcd(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return a


def _len(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(raw)]) + raw


def _int(v: int) -> bytes:
    raw = v.to_bytes(max(1, (v.bit_length() + 8) // 8), "big")  # a leading 0 keeps it positive
    return b"\x02" + _len(len(raw)) + raw


def _seq(*parts: bytes) -> bytes:
    body = b"".join(parts)
    return b"\x30" + _len(len(body)) + body


def _seq_raw(body: bytes) -> bytes:
    return b"\x30" + _len(len(body)) + body


def _from_int(raw: bytes) -> int:
    return int.from_bytes(raw, "big")


def _parse_seq(der: bytes) -> List[Tuple[int, bytes]]:
    """The (tag, content) items of the outer SEQUENCE of ``der``."""
    tag, body, _rest = _tlv(der)
    if tag != 0x30:
        raise ValueError("not a DER SEQUENCE")
    items = []
    while body:
        t, v, body = _tlv(body)
        items.append((t, v))
    return items


def _tlv(data: bytes) -> Tuple[int, bytes, bytes]:
    if len(data) < 2:
        raise ValueError("truncated DER")
    tag, first = data[0], data[1]
    if first < 0x80:
        length, off = first, 2
    else:
        count = first & 0x7F
        length, off = int.from_bytes(data[2:2 + count], "big"), 2 + count
    if off + length > len(data):
        raise ValueError("truncated DER")
    return tag, data[off:off + length], data[off + length:]
