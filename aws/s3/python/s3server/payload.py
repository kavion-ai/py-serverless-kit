"""Request bodies: Content-Length or chunked transfer, ``aws-chunked`` with chunk and trailer signatures, checks."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import re
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from .checksums import checksum_header, new_checksum
from .config import ALGORITHMS
from .errors import S3Error, invalid
from .sigv4 import Auth, chunk_signature
from .store import get_store, unlink


class Raw:
    """The request body as sent: ``Content-Length`` bytes, or HTTP chunked transfer coding."""

    def __init__(self, rfile: Any, length: Optional[int], chunked: bool) -> None:
        self.rfile, self.left, self.chunked = rfile, length or 0, chunked
        self.chunk_left = 0
        self.done = not chunked and not length
        self.buf = b""

    def _fill(self) -> bytes:
        if self.done:
            return b""
        if not self.chunked:
            data = self.rfile.read(min(65536, self.left))
            if not data:
                raise S3Error(
                    "IncompleteBody",
                    "You did not provide the number of bytes specified by the Content-Length HTTP header",
                )
            self.left -= len(data)
            self.done = self.left <= 0
            return data
        if self.chunk_left == 0:
            line = self.rfile.readline(1024)
            size = int(line.split(b";")[0].strip() or b"0", 16)
            if size == 0:
                while self.rfile.readline(8192) not in (b"\r\n", b"\n", b""):
                    pass
                self.done = True
                return b""
            self.chunk_left = size
        data = self.rfile.read(min(65536, self.chunk_left))
        if not data:
            raise S3Error("IncompleteBody", "The request body ended early.")
        self.chunk_left -= len(data)
        if self.chunk_left == 0:
            self.rfile.readline(16)
        return data

    def read(self, n: int) -> bytes:
        while len(self.buf) < n and not self.done:
            self.buf += self._fill()
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def readline(self, limit: int = 8192) -> bytes:
        while b"\n" not in self.buf and not self.done and len(self.buf) < limit:
            self.buf += self._fill()
        idx = self.buf.find(b"\n")
        end = idx + 1 if idx >= 0 else len(self.buf)
        out, self.buf = self.buf[:end], self.buf[end:]
        return out

    def chunks(self) -> Iterator[bytes]:
        if self.buf:
            data, self.buf = self.buf, b""
            yield data
        while not self.done:
            data = self._fill()
            if data:
                yield data

    def drain(self) -> None:
        for _ in self.chunks():
            pass


def payload_chunks(raw: Raw, headers: Dict[str, str], auth: Auth, trailers: Dict[str, str]) -> Iterator[bytes]:
    """The decoded payload: plain, or ``aws-chunked`` with chunk signatures and trailing checksums."""
    mode = auth.payload or headers.get("x-amz-content-sha256", "")
    if not mode.startswith("STREAMING-"):
        yield from raw.chunks()
        return
    if mode not in (
        "STREAMING-AWS4-HMAC-SHA256-PAYLOAD",
        "STREAMING-AWS4-HMAC-SHA256-PAYLOAD-TRAILER",
        "STREAMING-UNSIGNED-PAYLOAD-TRAILER",
    ):
        raise S3Error("NotImplemented", f"x-amz-content-sha256 {mode} is not supported.", 501)
    signed = mode.startswith("STREAMING-AWS4-HMAC") and auth.key
    prev = auth.signature
    while True:
        line = raw.readline(4096).strip().decode("latin-1")
        if not line:
            raise S3Error("IncompleteBody", "The aws-chunked body ended early.")
        size_text, _sep, ext = line.partition(";")
        try:
            size = int(size_text, 16)
        except ValueError:
            raise S3Error("InvalidRequest", "The aws-chunked body is not valid.") from None
        data = raw.read(size) if size else b""
        if len(data) != size:
            raise S3Error("IncompleteBody", "The aws-chunked body ended early.")
        if signed:
            claimed = ext.partition("chunk-signature=")[2].strip()
            expected = chunk_signature(auth, prev, "chunk", hashlib.sha256(data).hexdigest())
            if not hmac.compare_digest(claimed, expected):
                raise S3Error("SignatureDoesNotMatch", "The chunk signature does not match.", 403)
            prev = expected
        if size:
            raw.read(2)
            yield data
            continue
        lines: List[str] = []
        while True:
            tl = raw.readline(8192)
            if tl in (b"\r\n", b"\n", b""):
                break
            lines.append(tl.decode("latin-1").rstrip("\r\n"))
        canonical = ""
        for tl_text in lines:
            name, _c, value = tl_text.partition(":")
            name = name.strip().lower()
            if name == "x-amz-trailer-signature":
                if signed:
                    expected = chunk_signature(auth, prev, "trailer", hashlib.sha256(canonical.encode()).hexdigest())
                    if not hmac.compare_digest(value.strip(), expected):
                        raise S3Error("SignatureDoesNotMatch", "The trailer signature does not match.", 403)
            else:
                trailers[name] = value.strip()
                canonical += f"{name}:{value.strip()}\n"
        raw.drain()
        return


class Received:
    """A received payload: its temporary file, size, MD5 and checksum."""

    def __init__(self) -> None:
        self.path: Optional[Path] = None
        self.size = 0
        self.md5 = ""
        self.checksum: Dict[str, str] = {}  # alg -> base64


def wanted_checksum(headers: Dict[str, str]) -> Tuple[str, str]:
    """(algorithm, value the client sent or "" for a trailer / to compute) of a write."""
    for alg in ALGORITHMS:
        value = headers.get(checksum_header(alg))
        if value:
            return alg, value
    trailer = headers.get("x-amz-trailer", "").strip().lower()
    for alg in ALGORITHMS:
        if trailer == checksum_header(alg):
            return alg, ""
    alg = (headers.get("x-amz-sdk-checksum-algorithm") or headers.get("x-amz-checksum-algorithm") or "").upper()
    if alg:
        if alg not in ALGORITHMS:
            raise invalid(f"Checksum algorithm {alg} is not supported.", "x-amz-checksum-algorithm", alg)
        return alg, ""
    return "", ""


def receive(
    raw: Raw, headers: Dict[str, str], auth: Auth, limit: int, alg: str = "", expected: str = "", to_file: bool = True
) -> Tuple[Received, bytes]:
    """Read the payload into a temporary file (or memory), checking its length, MD5, SHA-256 and checksum."""
    out = Received()
    md5 = hashlib.md5()  # noqa: S324 - the S3 ETag
    claimed = auth.payload or headers.get("x-amz-content-sha256", "")
    sha = hashlib.sha256() if re.fullmatch(r"[0-9a-f]{64}", claimed or "") else None
    hasher = new_checksum(alg) if alg else None
    trailers: Dict[str, str] = {}
    buf = bytearray()
    handle = None
    if to_file:
        out.path = get_store().temp_file()
        handle = open(out.path, "wb")  # noqa: SIM115 - closed below
    try:
        for data in payload_chunks(raw, headers, auth, trailers):
            out.size += len(data)
            if out.size > limit:
                raise S3Error(
                    "EntityTooLarge",
                    "Your proposed upload exceeds the maximum allowed size",
                    400,
                    MaxSizeAllowed=str(limit),
                )
            md5.update(data)
            if sha:
                sha.update(data)
            if hasher:
                hasher.update(data)
            if handle:
                handle.write(data)
            else:
                buf += data
    except BaseException:
        if handle:
            handle.close()
        if out.path:
            unlink(out.path)
        raise
    if handle:
        handle.close()
    try:
        decoded = headers.get("x-amz-decoded-content-length")
        if decoded and claimed.startswith("STREAMING-") and int(decoded) != out.size:
            raise S3Error("IncompleteBody", "The decoded body is not x-amz-decoded-content-length bytes long.")
        if sha and sha.hexdigest() != claimed:
            raise S3Error(
                "XAmzContentSHA256Mismatch",
                "The provided 'x-amz-content-sha256' header does not match what was computed.",
                400,
                ClientComputedContentSHA256=claimed,
                S3ComputedContentSHA256=sha.hexdigest(),
            )
        out.md5 = md5.hexdigest()
        content_md5 = headers.get("content-md5")
        if content_md5:
            try:
                given = base64.b64decode(content_md5, validate=True)
            except (binascii.Error, ValueError):
                raise S3Error("InvalidDigest", "The Content-MD5 you specified was invalid.") from None
            if len(given) != 16:
                raise S3Error("InvalidDigest", "The Content-MD5 you specified was invalid.")
            if given != md5.digest():
                raise S3Error("BadDigest", "The Content-MD5 you specified did not match what we received.")
        if hasher:
            value = base64.b64encode(hasher.digest()).decode()
            sent = expected or trailers.get(checksum_header(alg), "")
            if sent and sent != value:
                raise S3Error("BadDigest", f"The {alg} you specified did not match the calculated checksum.")
            out.checksum = {alg: value}
    except BaseException:
        if out.path:
            unlink(out.path)
        raise
    return out, bytes(buf)


def copy_file(src: Path, start: int, end: int, alg: str) -> Received:
    out = Received()
    out.path = get_store().temp_file()
    md5 = hashlib.md5()  # noqa: S324 - the S3 ETag
    hasher = new_checksum(alg) if alg else None
    with open(src, "rb") as fin, open(out.path, "wb") as fout:
        fin.seek(start)
        left = end - start + 1
        while left > 0:
            data = fin.read(min(1024 * 1024, left))
            if not data:
                break
            left -= len(data)
            md5.update(data)
            if hasher:
                hasher.update(data)
            fout.write(data)
            out.size += len(data)
    out.md5 = md5.hexdigest()
    if hasher:
        out.checksum = {alg: base64.b64encode(hasher.digest()).decode()}
    return out
