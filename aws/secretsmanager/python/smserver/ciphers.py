"""The ciphers behind encryption at rest: AES-256 (FIPS-197), GCM (NIST SP 800-38D), ChaCha20-Poly1305 (RFC 8439)
and AES-256-CBC + HMAC-SHA256 (encrypt-then-MAC, keys from HKDF-SHA256).

The standard library has no ciphers, so they are written out here and checked against the published test vectors and
against Node's ``crypto`` (``../nodejs/lib/crypto.js``). When the ``cryptography`` package is installed its vetted,
constant-time AES-GCM and ChaCha20-Poly1305 are used instead; the formats are the same either way.

This module imports only the standard library (and optionally ``cryptography``), so it can be loaded on its own.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from typing import Any, Dict, List, Tuple

try:  # A vetted, constant-time implementation when it is installed; the same formats either way.
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM, ChaCha20Poly1305
except ImportError:
    AESGCM = ChaCha20Poly1305 = None  # type: ignore[assignment,misc]
    InvalidTag = Exception  # type: ignore[assignment,misc]


def _gf_mul(a: int, b: int) -> int:
    out = 0
    while b:
        if b & 1:
            out ^= a
        a = ((a << 1) ^ 0x11B) if a & 0x80 else a << 1
        b >>= 1
    return out


def _aes_tables() -> Tuple[List[int], List[int], List[List[int]], List[List[int]]]:
    exp, log_ = [0] * 255, [0] * 256
    g = 1
    for i in range(255):  # powers of the generator 3
        exp[i], log_[g] = g, i
        g = _gf_mul(g, 3)
    sbox = [0] * 256
    for x in range(256):
        inv = exp[(255 - log_[x]) % 255] if x else 0
        s = inv
        for shift in (1, 2, 3, 4):
            s ^= ((inv << shift) | (inv >> (8 - shift))) & 0xFF
        sbox[x] = s ^ 0x63
    inv_sbox = [0] * 256
    for x, s in enumerate(sbox):
        inv_sbox[s] = x
    te: List[List[int]] = [[], [], [], []]
    td: List[List[int]] = [[], [], [], []]
    for x in range(256):
        s, i = sbox[x], inv_sbox[x]
        col = (_gf_mul(s, 2), s, s, _gf_mul(s, 3))
        icol = (_gf_mul(i, 14), _gf_mul(i, 9), _gf_mul(i, 13), _gf_mul(i, 11))
        for r in range(4):  # Te[r] / Td[r] are Te[0] / Td[0] rotated right by r bytes
            te[r].append(int.from_bytes(bytes(col[(k - r) % 4] for k in range(4)), "big"))
            td[r].append(int.from_bytes(bytes(icol[(k - r) % 4] for k in range(4)), "big"))
    return sbox, inv_sbox, te, td


_SBOX: List[int] = []
_INV_SBOX: List[int] = []
_TE: List[List[int]] = []
_TD: List[List[int]] = []


class _AES256:
    """The AES-256 block cipher (FIPS-197) with 32-bit lookup tables."""

    def __init__(self, key: bytes) -> None:
        global _SBOX, _INV_SBOX, _TE, _TD
        if not _SBOX:
            _SBOX, _INV_SBOX, _TE, _TD = _aes_tables()
        if len(key) != 32:
            raise ValueError("AES-256 needs a 32-byte key")
        sb = _SBOX
        w = [int.from_bytes(key[i:i + 4], "big") for i in range(0, 32, 4)]
        rcon = 1
        for i in range(8, 60):
            t = w[i - 1]
            if i % 8 == 0:
                t = ((t << 8) | (t >> 24)) & 0xFFFFFFFF
                t = (sb[t >> 24] << 24 | sb[(t >> 16) & 255] << 16 | sb[(t >> 8) & 255] << 8 | sb[t & 255]) ^ (rcon << 24)
                rcon = _gf_mul(rcon, 2)
            elif i % 8 == 4:
                t = sb[t >> 24] << 24 | sb[(t >> 16) & 255] << 16 | sb[(t >> 8) & 255] << 8 | sb[t & 255]
            w.append(w[i - 8] ^ t)
        self.enc = w
        dec: List[int] = []
        for r in range(14, -1, -1):
            for t in w[4 * r:4 * r + 4]:
                if 0 < r < 14:  # InvMixColumns on the middle round keys (the equivalent inverse cipher)
                    t = (_TD[0][sb[t >> 24]] ^ _TD[1][sb[(t >> 16) & 255]] ^ _TD[2][sb[(t >> 8) & 255]]
                         ^ _TD[3][sb[t & 255]])
                dec.append(t)
        self.dec = dec

    def encrypt_block(self, block: bytes) -> bytes:
        te0, te1, te2, te3 = _TE
        sb, k = _SBOX, self.enc
        s0, s1, s2, s3 = (int.from_bytes(block[i:i + 4], "big") ^ k[i // 4] for i in range(0, 16, 4))
        for r in range(1, 14):
            o = 4 * r
            s0, s1, s2, s3 = (
                te0[s0 >> 24] ^ te1[(s1 >> 16) & 255] ^ te2[(s2 >> 8) & 255] ^ te3[s3 & 255] ^ k[o],
                te0[s1 >> 24] ^ te1[(s2 >> 16) & 255] ^ te2[(s3 >> 8) & 255] ^ te3[s0 & 255] ^ k[o + 1],
                te0[s2 >> 24] ^ te1[(s3 >> 16) & 255] ^ te2[(s0 >> 8) & 255] ^ te3[s1 & 255] ^ k[o + 2],
                te0[s3 >> 24] ^ te1[(s0 >> 16) & 255] ^ te2[(s1 >> 8) & 255] ^ te3[s2 & 255] ^ k[o + 3],
            )
        out = (
            (sb[s0 >> 24] << 24 | sb[(s1 >> 16) & 255] << 16 | sb[(s2 >> 8) & 255] << 8 | sb[s3 & 255]) ^ k[56],
            (sb[s1 >> 24] << 24 | sb[(s2 >> 16) & 255] << 16 | sb[(s3 >> 8) & 255] << 8 | sb[s0 & 255]) ^ k[57],
            (sb[s2 >> 24] << 24 | sb[(s3 >> 16) & 255] << 16 | sb[(s0 >> 8) & 255] << 8 | sb[s1 & 255]) ^ k[58],
            (sb[s3 >> 24] << 24 | sb[(s0 >> 16) & 255] << 16 | sb[(s1 >> 8) & 255] << 8 | sb[s2 & 255]) ^ k[59],
        )
        return b"".join(v.to_bytes(4, "big") for v in out)

    def decrypt_block(self, block: bytes) -> bytes:
        td0, td1, td2, td3 = _TD
        ib, k = _INV_SBOX, self.dec
        s0, s1, s2, s3 = (int.from_bytes(block[i:i + 4], "big") ^ k[i // 4] for i in range(0, 16, 4))
        for r in range(1, 14):
            o = 4 * r
            s0, s1, s2, s3 = (
                td0[s0 >> 24] ^ td1[(s3 >> 16) & 255] ^ td2[(s2 >> 8) & 255] ^ td3[s1 & 255] ^ k[o],
                td0[s1 >> 24] ^ td1[(s0 >> 16) & 255] ^ td2[(s3 >> 8) & 255] ^ td3[s2 & 255] ^ k[o + 1],
                td0[s2 >> 24] ^ td1[(s1 >> 16) & 255] ^ td2[(s0 >> 8) & 255] ^ td3[s3 & 255] ^ k[o + 2],
                td0[s3 >> 24] ^ td1[(s2 >> 16) & 255] ^ td2[(s1 >> 8) & 255] ^ td3[s0 & 255] ^ k[o + 3],
            )
        out = (
            (ib[s0 >> 24] << 24 | ib[(s3 >> 16) & 255] << 16 | ib[(s2 >> 8) & 255] << 8 | ib[s1 & 255]) ^ k[56],
            (ib[s1 >> 24] << 24 | ib[(s0 >> 16) & 255] << 16 | ib[(s3 >> 8) & 255] << 8 | ib[s2 & 255]) ^ k[57],
            (ib[s2 >> 24] << 24 | ib[(s1 >> 16) & 255] << 16 | ib[(s0 >> 8) & 255] << 8 | ib[s3 & 255]) ^ k[58],
            (ib[s3 >> 24] << 24 | ib[(s2 >> 16) & 255] << 16 | ib[(s1 >> 8) & 255] << 8 | ib[s0 & 255]) ^ k[59],
        )
        return b"".join(v.to_bytes(4, "big") for v in out)


class DecryptError(Exception):
    """A tag did not match: wrong master key, or the data was changed."""


def _xor(a: bytes, b: bytes) -> bytes:
    return (int.from_bytes(a, "big") ^ int.from_bytes(b[:len(a)], "big")).to_bytes(len(a), "big")


_GCM_R = 0xE1 << 120


def _ghash(h: int, aad: bytes, ct: bytes) -> int:
    # GF(2^128) multiplication by H, 4 bits at a time with a 16-entry table built per message.
    table = [0] * 16
    v = h
    for bit in (8, 4, 2, 1):
        table[bit] = v
        v = (v >> 1) ^ (_GCM_R if v & 1 else 0)
    for i in (3, 5, 6, 7, 9, 10, 11, 12, 13, 14, 15):
        table[i] = table[i & 8] ^ table[i & 4] ^ table[i & 2] ^ table[i & 1]
    reduce = [0] * 16  # the bits shifted out of the low nibble, folded back with R
    for i in range(16):
        r = 0
        for bit in range(4):
            if i & (1 << bit):
                r ^= _GCM_R >> (3 - bit)
        reduce[i] = r

    def mul(x: int) -> int:
        z = 0
        for shift in range(0, 128, 4):
            low = z & 15
            z = (z >> 4) ^ reduce[low]
            z ^= table[(x >> shift) & 15]
        return z

    y = 0
    for data in (aad, ct):
        for i in range(0, len(data), 16):
            y = mul(y ^ int.from_bytes(data[i:i + 16].ljust(16, b"\0"), "big"))
    return mul(y ^ ((len(aad) * 8) << 64 | len(ct) * 8))


def _ctr(cipher: _AES256, iv: bytes, start: int, data: bytes) -> bytes:
    out = bytearray()
    for n, i in enumerate(range(0, len(data), 16)):
        pad = cipher.encrypt_block(iv + ((start + n) & 0xFFFFFFFF).to_bytes(4, "big"))
        out += _xor(data[i:i + 16], pad)
    return bytes(out)


def _aead_seal(aead: Any, key: bytes, nonce: bytes, plain: bytes, aad: bytes) -> Tuple[bytes, bytes]:
    sealed = aead(key).encrypt(nonce, plain, aad or None)
    return sealed[:-16], sealed[-16:]


def _aead_open(aead: Any, key: bytes, nonce: bytes, ct: bytes, tag: bytes, aad: bytes, name: str) -> bytes:
    try:
        return bytes(aead(key).decrypt(nonce, ct + tag, aad or None))
    except InvalidTag:
        raise DecryptError(f"{name} tag mismatch") from None


def _vetted(key: bytes, nonce: bytes, tag: bytes = bytes(16)) -> bool:
    """Use the ``cryptography`` package for this call? Odd sizes stay with the code below, which reports them."""
    return AESGCM is not None and len(key) == 32 and len(nonce) == 12 and len(tag) == 16


def aes_gcm_encrypt(key: bytes, iv: bytes, plain: bytes, aad: bytes) -> Tuple[bytes, bytes]:
    if _vetted(key, iv):
        return _aead_seal(AESGCM, key, iv, plain, aad)
    cipher = _AES256(key)
    h = int.from_bytes(cipher.encrypt_block(bytes(16)), "big")
    ct = _ctr(cipher, iv, 2, plain)
    tag = _xor(cipher.encrypt_block(iv + b"\0\0\0\1"), _ghash(h, aad, ct).to_bytes(16, "big"))
    return ct, tag


def aes_gcm_decrypt(key: bytes, iv: bytes, ct: bytes, tag: bytes, aad: bytes) -> bytes:
    if _vetted(key, iv, tag):
        return _aead_open(AESGCM, key, iv, ct, tag, aad, "AES-GCM")
    cipher = _AES256(key)
    h = int.from_bytes(cipher.encrypt_block(bytes(16)), "big")
    want = _xor(cipher.encrypt_block(iv + b"\0\0\0\1"), _ghash(h, aad, ct).to_bytes(16, "big"))
    if not hmac.compare_digest(want, tag):
        raise DecryptError("AES-GCM tag mismatch")
    return _ctr(cipher, iv, 2, ct)


def _chacha_block(key: bytes, counter: int, nonce: bytes) -> bytes:
    m = 0xFFFFFFFF
    state = [0x61707865, 0x3320646E, 0x79622D32, 0x6B206574,
             *(int.from_bytes(key[i:i + 4], "little") for i in range(0, 32, 4)),
             counter & m, *(int.from_bytes(nonce[i:i + 4], "little") for i in range(0, 12, 4))]
    x = list(state)

    def qr(a: int, b: int, c: int, d: int) -> None:
        x[a] = (x[a] + x[b]) & m
        x[d] ^= x[a]
        x[d] = ((x[d] << 16) | (x[d] >> 16)) & m
        x[c] = (x[c] + x[d]) & m
        x[b] ^= x[c]
        x[b] = ((x[b] << 12) | (x[b] >> 20)) & m
        x[a] = (x[a] + x[b]) & m
        x[d] ^= x[a]
        x[d] = ((x[d] << 8) | (x[d] >> 24)) & m
        x[c] = (x[c] + x[d]) & m
        x[b] ^= x[c]
        x[b] = ((x[b] << 7) | (x[b] >> 25)) & m

    for _ in range(10):
        qr(0, 4, 8, 12)
        qr(1, 5, 9, 13)
        qr(2, 6, 10, 14)
        qr(3, 7, 11, 15)
        qr(0, 5, 10, 15)
        qr(1, 6, 11, 12)
        qr(2, 7, 8, 13)
        qr(3, 4, 9, 14)
    return b"".join(((x[i] + state[i]) & m).to_bytes(4, "little") for i in range(16))


def _chacha20(key: bytes, nonce: bytes, start: int, data: bytes) -> bytes:
    out = bytearray()
    for n, i in enumerate(range(0, len(data), 64)):
        out += _xor(data[i:i + 64], _chacha_block(key, start + n, nonce))
    return bytes(out)


def _poly1305(key: bytes, msg: bytes) -> bytes:
    r = int.from_bytes(key[:16], "little") & 0x0FFFFFFC0FFFFFFC0FFFFFFC0FFFFFFF
    s = int.from_bytes(key[16:32], "little")
    p = (1 << 130) - 5
    acc = 0
    for i in range(0, len(msg), 16):
        acc = (acc + int.from_bytes(msg[i:i + 16] + b"\1", "little")) * r % p
    return ((acc + s) & ((1 << 128) - 1)).to_bytes(16, "little")


def _chacha_mac_data(aad: bytes, ct: bytes) -> bytes:
    pad = lambda b: b + bytes(-len(b) % 16)  # noqa: E731
    return pad(aad) + pad(ct) + len(aad).to_bytes(8, "little") + len(ct).to_bytes(8, "little")


def chacha20_poly1305_encrypt(key: bytes, nonce: bytes, plain: bytes, aad: bytes) -> Tuple[bytes, bytes]:
    if _vetted(key, nonce):
        return _aead_seal(ChaCha20Poly1305, key, nonce, plain, aad)
    ct = _chacha20(key, nonce, 1, plain)
    return ct, _poly1305(_chacha_block(key, 0, nonce)[:32], _chacha_mac_data(aad, ct))


def chacha20_poly1305_decrypt(key: bytes, nonce: bytes, ct: bytes, tag: bytes, aad: bytes) -> bytes:
    if _vetted(key, nonce, tag):
        return _aead_open(ChaCha20Poly1305, key, nonce, ct, tag, aad, "ChaCha20-Poly1305")
    want = _poly1305(_chacha_block(key, 0, nonce)[:32], _chacha_mac_data(aad, ct))
    if not hmac.compare_digest(want, tag):
        raise DecryptError("ChaCha20-Poly1305 tag mismatch")
    return _chacha20(key, nonce, 1, ct)


def hkdf_sha256(key: bytes, info: bytes, length: int = 32, salt: bytes = b"") -> bytes:
    prk = hmac.new(salt or bytes(32), key, hashlib.sha256).digest()
    out, block = b"", b""
    for n in range(1, -(-length // 32) + 1):
        block = hmac.new(prk, block + info + bytes([n]), hashlib.sha256).digest()
        out += block
    return out[:length]


def _cbc_keys(dek: bytes) -> Tuple[bytes, bytes]:
    return hkdf_sha256(dek, b"pskit-sm aes-256-cbc enc"), hkdf_sha256(dek, b"pskit-sm hmac-sha256 mac")


def _cbc_mac(mac_key: bytes, aad: bytes, iv: bytes, ct: bytes) -> bytes:
    return hmac.new(mac_key, len(aad).to_bytes(8, "big") + aad + iv + ct, hashlib.sha256).digest()


def aes_cbc_hmac_encrypt(dek: bytes, iv: bytes, plain: bytes, aad: bytes) -> Tuple[bytes, bytes]:
    enc_key, mac_key = _cbc_keys(dek)
    cipher = _AES256(enc_key)
    pad = 16 - len(plain) % 16
    data = plain + bytes([pad]) * pad
    out, prev = bytearray(), iv
    for i in range(0, len(data), 16):
        prev = cipher.encrypt_block(_xor(data[i:i + 16], prev))
        out += prev
    return bytes(out), _cbc_mac(mac_key, aad, iv, bytes(out))


def aes_cbc_hmac_decrypt(dek: bytes, iv: bytes, ct: bytes, tag: bytes, aad: bytes) -> bytes:
    enc_key, mac_key = _cbc_keys(dek)
    if not hmac.compare_digest(_cbc_mac(mac_key, aad, iv, ct), tag) or not ct or len(ct) % 16:
        raise DecryptError("AES-CBC HMAC-SHA256 tag mismatch")
    cipher = _AES256(enc_key)
    out, prev = bytearray(), iv
    for i in range(0, len(ct), 16):
        block = ct[i:i + 16]
        out += _xor(cipher.decrypt_block(block), prev)
        prev = block
    pad = out[-1]
    if not 1 <= pad <= 16 or out[-pad:] != bytes([pad]) * pad:
        raise DecryptError("AES-CBC padding is not valid")
    return bytes(out[:-pad])


# name -> (SM_ENCRYPTION value, nonce bytes, encrypt, decrypt)
ALGORITHMS: Dict[str, Tuple[str, int, Any, Any]] = {
    "AES-256-GCM": ("aes-256-gcm", 12, aes_gcm_encrypt, aes_gcm_decrypt),
    "ChaCha20-Poly1305": ("chacha20-poly1305", 12, chacha20_poly1305_encrypt, chacha20_poly1305_decrypt),
    "AES-256-CBC-HMAC-SHA256": ("aes-256-cbc-hmac", 16, aes_cbc_hmac_encrypt, aes_cbc_hmac_decrypt),
}
def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")
