"""Object lock: a bucket's default retention and whether a version is protected from deletion."""

from __future__ import annotations

import time
from typing import Any, Dict

from .errors import S3Error, denied
from .store import Bucket
from .util import parse_xml, text


def lock_config(bucket: Bucket) -> Dict[str, Any]:
    raw = (bucket.meta.get("configs") or {}).get("object-lock", "")
    out: Dict[str, Any] = {"enabled": bool(bucket.meta.get("object_lock")), "mode": "", "days": 0, "years": 0}
    if raw:
        try:
            root = parse_xml(raw.encode())
        except S3Error:
            return out
        out["enabled"] = out["enabled"] or text(root, "ObjectLockEnabled") == "Enabled"
        out["mode"] = text(root, "Rule/DefaultRetention/Mode")
        out["days"] = int(text(root, "Rule/DefaultRetention/Days") or 0)
        out["years"] = int(text(root, "Rule/DefaultRetention/Years") or 0)
    return out


def is_locked(version: Dict[str, Any], now: float, bypass: bool = False) -> bool:
    if version.get("hold"):
        return True
    retention = version.get("retention") or {}
    if retention.get("until") and retention["until"] > now:
        return not (retention.get("mode") == "GOVERNANCE" and bypass)
    return False


def check_unlocked(version: Dict[str, Any], bypass: bool) -> None:
    if version.get("hold"):
        raise denied("Access Denied because object protected by object lock.")
    if is_locked(version, time.time(), bypass):
        raise denied("Access Denied because object protected by object lock.")
