"""The S3 checksum algorithms: CRC32, CRC32C, CRC64NVME (table-driven), SHA1 and SHA256."""

from __future__ import annotations

import base64
import binascii
import hashlib
from typing import Any, List

from .errors import invalid


def _crc_table(poly: int) -> List[int]:
    table = []
    for i in range(256):
        c = i
        for _ in range(8):
            c = (c >> 1) ^ poly if c & 1 else c >> 1
        table.append(c)
    return table


_CRC32C = _crc_table(0x82F63B78)
_CRC64 = _crc_table(0x9A6C9329AC4BC9B5)


class _Crc:
    def __init__(self, table: List[int], mask: int, size: int) -> None:
        self.table, self.mask, self.size, self.value = table, mask, size, mask

    def update(self, data: bytes) -> None:
        t, c = self.table, self.value
        for b in data:
            c = t[(c ^ b) & 0xFF] ^ (c >> 8)
        self.value = c

    def digest(self) -> bytes:
        return (self.value ^ self.mask).to_bytes(self.size, "big")


class _Crc32:
    def __init__(self) -> None:
        self.value = 0

    def update(self, data: bytes) -> None:
        self.value = binascii.crc32(data, self.value)

    def digest(self) -> bytes:
        return (self.value & 0xFFFFFFFF).to_bytes(4, "big")


def new_checksum(alg: str) -> Any:
    if alg == "CRC32":
        return _Crc32()
    if alg == "CRC32C":
        return _Crc(_CRC32C, 0xFFFFFFFF, 4)
    if alg == "CRC64NVME":
        return _Crc(_CRC64, 0xFFFFFFFFFFFFFFFF, 8)
    if alg == "SHA1":
        return hashlib.sha1()  # noqa: S324 - the S3 checksum algorithm, not a security use
    if alg == "SHA256":
        return hashlib.sha256()
    raise invalid(f"Checksum algorithm {alg} is not supported.", "x-amz-checksum-algorithm", alg)


def checksum_of(alg: str, data: bytes) -> str:
    h = new_checksum(alg)
    h.update(data)
    return base64.b64encode(h.digest()).decode()


def checksum_header(alg: str) -> str:
    return "x-amz-checksum-" + alg.lower()


def checksum_element(alg: str) -> str:
    return "Checksum" + alg
