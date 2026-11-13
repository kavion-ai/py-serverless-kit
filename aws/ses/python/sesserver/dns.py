"""A small DNS client (the standard library has none for MX / TXT): one question over UDP, again over TCP when the
answer is truncated.

The server is ``SES_DNS_SERVER`` (``host`` or ``host:port``), else the first ``nameserver`` of /etc/resolv.conf,
else 1.1.1.1. :class:`DnsError` carries ``kind``: ``HOST_NOT_FOUND`` (NXDOMAIN), ``TYPE_NOT_FOUND`` (no record of
that type) or ``DNS_SERVER_ERROR`` (no answer), the names SES uses for verification errors.
"""

from __future__ import annotations

import secrets
import socket
import struct
from pathlib import Path
from typing import List, Tuple

from .config import DNS_SERVER

MX, TXT = 15, 16


class DnsError(Exception):
    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


def server() -> Tuple[str, int]:
    text = DNS_SERVER
    if not text:
        try:
            for line in Path("/etc/resolv.conf").read_text("utf-8").splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[0] == "nameserver":
                    text = parts[1]
                    break
        except OSError:
            pass
    text = text or "1.1.1.1"
    if text.startswith("[") and "]:" in text:
        host, port = text[1:].split("]:", 1)
        return host, int(port)
    if text.count(":") == 1:
        host, port = text.split(":")
        return host, int(port)
    return text, 53


def _encode_name(name: str) -> bytes:
    out = b""
    for label in name.rstrip(".").split("."):
        raw = label.encode("idna") if label else b""
        out += bytes([len(raw)]) + raw
    return out + b"\x00"


def _read_name(msg: bytes, off: int) -> Tuple[str, int]:
    labels: List[str] = []
    end = -1
    for _ in range(128):
        length = msg[off]
        if length & 0xC0 == 0xC0:
            if end < 0:
                end = off + 2
            off = ((length & 0x3F) << 8) | msg[off + 1]
            continue
        if length == 0:
            off += 1
            break
        labels.append(msg[off + 1:off + 1 + length].decode("latin-1"))
        off += 1 + length
    return ".".join(labels), (end if end >= 0 else off)


def _ask(qname: str, qtype: int, timeout: float) -> bytes:
    ident = secrets.randbelow(65536)
    query = struct.pack(">HHHHHH", ident, 0x0100, 1, 0, 0, 0) + _encode_name(qname) + struct.pack(">HH", qtype, 1)
    host, port = server()
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.socket(family, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        for _attempt in range(2):
            sock.sendto(query, (host, port))
            try:
                while True:
                    data, _addr = sock.recvfrom(4096)
                    if len(data) >= 12 and struct.unpack(">H", data[:2])[0] == ident:
                        break
            except socket.timeout:
                continue
            if data[2] & 0x02:  # truncated: ask again over TCP
                return _ask_tcp(query, host, port, family, timeout)
            return data
    raise DnsError("DNS_SERVER_ERROR", f"the DNS server {host}:{port} did not answer")


def _ask_tcp(query: bytes, host: str, port: int, family: int, timeout: float) -> bytes:
    with socket.socket(family, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        sock.connect((host, port))
        sock.sendall(struct.pack(">H", len(query)) + query)
        head = sock.recv(2)
        size = struct.unpack(">H", head)[0]
        data = b""
        while len(data) < size:
            chunk = sock.recv(size - len(data))
            if not chunk:
                break
            data += chunk
        return data


def query(qname: str, qtype: int, timeout: float = 3.0) -> List[Tuple[int, int, bytes]]:
    """(offset of the rdata, its length, the whole message) of each answer record of ``qtype``: names in the rdata
    may point back into the message, so it is kept."""
    try:
        msg = _ask(qname, qtype, timeout)
    except OSError as exc:
        raise DnsError("DNS_SERVER_ERROR", f"DNS lookup of {qname} failed: {exc}") from None
    rcode = msg[3] & 0x0F
    if rcode == 3:
        raise DnsError("HOST_NOT_FOUND", f"{qname} does not exist (NXDOMAIN)")
    if rcode != 0:
        raise DnsError("DNS_SERVER_ERROR", f"the DNS server answered rcode {rcode} for {qname}")
    qd, an = struct.unpack(">HH", msg[4:8])
    off = 12
    for _ in range(qd):
        _name, off = _read_name(msg, off)
        off += 4
    out = []
    for _ in range(an):
        _name, off = _read_name(msg, off)
        rtype, _cls, _ttl, rdlen = struct.unpack(">HHIH", msg[off:off + 10])
        off += 10
        if rtype == qtype:
            out.append((off, rdlen, msg))
        off += rdlen
    return out


def mx(domain: str, timeout: float = 3.0) -> List[Tuple[int, str]]:
    """(preference, host) of the domain's MX records, best first. No MX record: the domain itself (RFC 5321)."""
    out = []
    for off, _length, msg in query(domain, MX, timeout):
        pref = struct.unpack(">H", msg[off:off + 2])[0]
        host, _end = _read_name(msg, off + 2)
        out.append((pref, host.rstrip(".").lower()))
    if not out:
        return [(0, domain)]
    out.sort()
    if out == [(0, "")]:  # null MX (RFC 7505): the domain takes no mail
        raise DnsError("TYPE_NOT_FOUND", f"{domain} accepts no mail (null MX)")
    return out


def txt(name: str, timeout: float = 3.0) -> List[str]:
    """The TXT records of ``name``, each record's strings joined."""
    out = []
    for off, length, msg in query(name, TXT, timeout):
        data = msg[off:off + length]
        parts, i = [], 0
        while i < len(data):
            n = data[i]
            parts.append(data[i + 1:i + 1 + n].decode("utf-8", "replace"))
            i += 1 + n
        out.append("".join(parts))
    return out
