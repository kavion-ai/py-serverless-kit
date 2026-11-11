"""Key listings: prefix / delimiter paging over a bucket's sorted keys, continuation tokens and ``<Contents>``."""

from __future__ import annotations

import base64
import binascii
import bisect
from typing import Any, Callable, Dict, List, Tuple

from .config import ARCHIVED
from .errors import invalid
from .store import Bucket
from .util import iso, owner_xml, url_enc, x


def list_keys(
    bucket: Bucket, prefix: str, delimiter: str, after: str, max_keys: int, include: Callable[[str], bool]
) -> Tuple[List[str], List[str], bool, str]:
    keys = bucket.keys()
    i = bisect.bisect_left(keys, prefix)
    if after:
        i = max(i, bisect.bisect_right(keys, after))
        if delimiter and after.endswith(delimiter):
            while i < len(keys) and keys[i].startswith(after):
                i += 1
    contents: List[str] = []
    prefixes: List[str] = []
    last = ""
    count = 0
    truncated = False
    while i < len(keys):
        key = keys[i]
        if not key.startswith(prefix):
            break
        if not include(key):
            i += 1
            continue
        if delimiter:
            pos = key.find(delimiter, len(prefix))
            if pos >= 0:
                common = key[: pos + len(delimiter)]
                if count >= max_keys:
                    truncated = True
                    break
                prefixes.append(common)
                last = common
                count += 1
                while i < len(keys) and keys[i].startswith(common):
                    i += 1
                continue
        if count >= max_keys:
            truncated = True
            break
        contents.append(key)
        last = key
        count += 1
        i += 1
    return contents, prefixes, truncated, last


def max_keys_param(q: Dict[str, str], name: str = "max-keys", default: int = 1000) -> int:
    try:
        value = int(q.get(name, default))
    except ValueError:
        raise invalid("Provided max-keys not an integer or within integer range", name, q.get(name, "")) from None
    if value < 0:
        raise invalid("Argument maxKeys must be an integer between 0 and 2147483647", name, str(value))
    return min(value, 1000)


def token_encode(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode()


def token_decode(value: str) -> str:
    try:
        return base64.urlsafe_b64decode(value.encode() + b"=" * (-len(value) % 4)).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        raise invalid("The continuation token provided is incorrect", "continuation-token", value) from None


def contents_xml(bucket: Bucket, key: str, version: Dict[str, Any], enc: bool, owner: bool) -> str:
    out = (
        f"<Contents>{x('Key', url_enc(key, enc))}{x('LastModified', iso(version['time']))}"
        f"{x('ETag', chr(34) + version['etag'] + chr(34))}{x('Size', version['size'])}"
        f"{x('StorageClass', version.get('class', 'STANDARD'))}"
    )
    if version.get("checksum"):
        out += x("ChecksumAlgorithm", version["checksum"]["alg"]) + x(
            "ChecksumType", version["checksum"].get("type", "FULL_OBJECT")
        )
    if owner:
        out += owner_xml()
    if version.get("class") in ARCHIVED and version.get("restore"):
        expiry = x("RestoreExpiryDate", iso(version["restore"]))
        out += f"<RestoreStatus><IsRestoreInProgress>false</IsRestoreInProgress>{expiry}</RestoreStatus>"
    return out + "</Contents>"


def visible(bucket: Bucket) -> Callable[[str], bool]:
    return lambda k: bool(bucket.objects.get(k)) and not bucket.objects[k]["versions"][0].get("dm")
