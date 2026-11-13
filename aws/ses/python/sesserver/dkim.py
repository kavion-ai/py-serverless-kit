"""DKIM signatures (RFC 6376): ``rsa-sha256``, ``relaxed/relaxed``, as Amazon SES signs.

``sign(raw, domain, selector, key)`` returns the message with a ``DKIM-Signature`` header on top. ``raw`` uses CRLF
line endings (see :func:`crlf`).
"""

from __future__ import annotations

import base64
import hashlib
import re
import time
from typing import List, Optional, Tuple

from .rsa import Key, verify_sha256

# What SES signs, when present (each once, the last instance).
SIGNED = ("from", "reply-to", "subject", "date", "message-id", "to", "cc", "mime-version", "content-type",
          "content-transfer-encoding", "in-reply-to", "references", "list-unsubscribe", "list-unsubscribe-post",
          "feedback-id")
_WSP = re.compile(rb"[ \t]+")


def crlf(raw: bytes) -> bytes:
    """Every line ending as CRLF (a bare LF or CR becomes CRLF)."""
    return re.sub(rb"\r\n|\r|\n", b"\r\n", raw)


def split(raw: bytes) -> Tuple[bytes, bytes]:
    """(header block with its final CRLF, body) of a CRLF message."""
    if raw.startswith(b"\r\n"):
        return b"", raw[2:]
    head, sep, body = raw.partition(b"\r\n\r\n")
    return (head + b"\r\n", body) if sep else (raw if raw.endswith(b"\r\n") else raw + b"\r\n", b"")


def header_fields(head: bytes) -> List[Tuple[str, bytes]]:
    """(lower-case name, the whole field with its folding but without the last CRLF) of each header field."""
    fields: List[Tuple[str, bytes]] = []
    for line in head.split(b"\r\n"):
        if not line:
            continue
        if line[:1] in (b" ", b"\t") and fields:
            name, value = fields[-1]
            fields[-1] = (name, value + b"\r\n" + line)
        else:
            fields.append((line.split(b":", 1)[0].strip().lower().decode("latin-1"), line))
    return fields


def relaxed_header(field: bytes) -> bytes:
    name, _sep, value = field.partition(b":")
    value = value.replace(b"\r\n", b"")
    value = _WSP.sub(b" ", value).strip(b" \t")
    return name.strip().lower() + b":" + value


def relaxed_body(body: bytes) -> bytes:
    lines = body.split(b"\r\n")
    out = [_WSP.sub(b" ", ln).rstrip(b" ") for ln in lines]
    while out and out[-1] == b"":
        out.pop()
    return b"".join(ln + b"\r\n" for ln in out)


def sign(raw: bytes, domain: str, selector: str, key: Key, when: Optional[int] = None) -> bytes:
    raw = crlf(raw)
    head, body = split(raw)
    fields = header_fields(head)
    names = [n for n in SIGNED if any(f[0] == n for f in fields)]
    body_hash = base64.b64encode(hashlib.sha256(relaxed_body(body)).digest()).decode("ascii")
    tags = [f"v=1; a=rsa-sha256; c=relaxed/relaxed; d={domain}; s={selector};",
            f"t={int(when if when is not None else time.time())}; h={':'.join(names)};", f"bh={body_hash};", "b="]
    unsigned = "DKIM-Signature: " + "\r\n\t".join(tags)
    canon = b"".join(relaxed_header(_last(fields, n)) + b"\r\n" for n in names)
    canon += relaxed_header(unsigned.encode("ascii"))
    signature = base64.b64encode(key.sign_sha256(canon)).decode("ascii")
    return (unsigned + signature).encode("ascii") + b"\r\n" + raw


def verify(raw: bytes, public_b64: str) -> bool:
    """Check the first ``DKIM-Signature`` of ``raw`` with a public key (the tests' and the console's self-check)."""
    raw = crlf(raw)
    head, body = split(raw)
    fields = header_fields(head)
    sig_field = next((f for n, f in fields if n == "dkim-signature"), None)
    if sig_field is None:
        return False
    tags = {}
    for part in relaxed_header(sig_field).split(b":", 1)[1].split(b";"):
        name, _eq, value = part.strip().partition(b"=")
        if name:
            tags[name.decode()] = re.sub(rb"\s+", b"", value).decode()
    if base64.b64encode(hashlib.sha256(relaxed_body(body)).digest()).decode() != tags.get("bh"):
        return False
    others = [(n, f) for n, f in fields if f is not sig_field]
    canon = b"".join(relaxed_header(_last(others, n)) + b"\r\n" for n in tags["h"].split(":") if _has(others, n))
    stripped = re.sub(rb"(;\s*b=)[^;]*$", rb"\1", relaxed_header(sig_field))
    return verify_sha256(public_b64, canon + stripped, base64.b64decode(tags["b"]))


def _has(fields: List[Tuple[str, bytes]], name: str) -> bool:
    return any(n == name for n, _f in fields)


def _last(fields: List[Tuple[str, bytes]], name: str) -> bytes:
    return [f for n, f in fields if n == name][-1]
