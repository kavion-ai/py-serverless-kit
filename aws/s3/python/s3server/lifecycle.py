"""Lifecycle rules: parsing them and the periodic sweep that expires, transitions and cleans up."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from .config import DAY, LIFECYCLE_INTERVAL
from .errors import S3Error, invalid, malformed
from .objectlock import is_locked
from .store import Bucket, abort_upload, get_store
from .util import log, parse_time, parse_xml, text
from .versions import delete_object, remove_version


def lifecycle_rules(bucket: Bucket) -> List[Dict[str, Any]]:
    if "lifecycle" in bucket.parsed:
        return bucket.parsed["lifecycle"]
    rules: List[Dict[str, Any]] = []
    raw = (bucket.meta.get("configs") or {}).get("lifecycle")
    if raw:
        try:
            rules = parse_lifecycle(raw.encode())
        except S3Error:
            rules = []
    bucket.parsed["lifecycle"] = rules
    return rules


def _num(value: str) -> Optional[int]:
    try:
        return int(value) if value else None
    except ValueError:
        raise malformed() from None


def parse_lifecycle(body: bytes) -> List[Dict[str, Any]]:
    root = parse_xml(body)
    if root.tag != "LifecycleConfiguration":
        raise malformed()
    rules = []
    for rule in root.findall("Rule"):
        status = text(rule, "Status")
        if status not in ("Enabled", "Disabled"):
            raise malformed()
        flt = rule.find("Filter")
        prefix, tags, gt, lt = text(rule, "Prefix"), {}, None, None
        if flt is not None:
            scope = flt.find("And") if flt.find("And") is not None else flt
            prefix = text(scope, "Prefix", prefix)
            for tag in scope.findall("Tag"):
                tags[text(tag, "Key")] = text(tag, "Value")
            gt, lt = _num(text(scope, "ObjectSizeGreaterThan")), _num(text(scope, "ObjectSizeLessThan"))
        exp = rule.find("Expiration")
        nce = rule.find("NoncurrentVersionExpiration")
        abort = rule.find("AbortIncompleteMultipartUpload")
        transitions = []
        for tr in rule.findall("Transition"):
            transitions.append(
                {
                    "days": _num(text(tr, "Days")),
                    "date": parse_time(text(tr, "Date")),
                    "class": text(tr, "StorageClass"),
                }
            )
        nc_transitions = []
        for tr in rule.findall("NoncurrentVersionTransition"):
            nc_transitions.append({"days": _num(text(tr, "NoncurrentDays")), "class": text(tr, "StorageClass")})
        item = {
            "id": text(rule, "ID"),
            "enabled": status == "Enabled",
            "prefix": prefix,
            "tags": tags,
            "gt": gt,
            "lt": lt,
            "exp_days": _num(text(exp, "Days")),
            "exp_date": parse_time(text(exp, "Date")),
            "exp_marker": text(exp, "ExpiredObjectDeleteMarker").lower() == "true",
            "nc_days": _num(text(nce, "NoncurrentDays")),
            "nc_keep": _num(text(nce, "NewerNoncurrentVersions")),
            "abort_days": _num(text(abort, "DaysAfterInitiation")),
            "transitions": transitions,
            "nc_transitions": nc_transitions,
        }
        if item["exp_days"] is not None and item["exp_days"] < 1:
            raise invalid("'Days' for Expiration action must be a positive integer")
        rules.append(item)
    if not rules or len(rules) > 1000:
        raise malformed()
    return rules


def _rule_matches(rule: Dict[str, Any], key: str, version: Dict[str, Any]) -> bool:
    if not rule["enabled"] or not key.startswith(rule["prefix"]):
        return False
    tags = version.get("tags") or {}
    if any(tags.get(k) != v for k, v in rule["tags"].items()):
        return False
    size = int(version.get("size") or 0)
    if rule["gt"] is not None and not size > rule["gt"]:
        return False
    return not (rule["lt"] is not None and not size < rule["lt"])


def sweep_lifecycle(now: Optional[float] = None) -> int:
    """Apply every bucket's lifecycle rules once. Returns how many changes were made."""
    now = now or time.time()
    changes = 0
    with get_store().lock:
        for bucket in list(get_store().buckets.values()):
            rules = lifecycle_rules(bucket)
            if not rules:
                continue
            for key in list(bucket.keys()):
                rec = bucket.objects.get(key)
                if not rec:
                    continue
                changes += _sweep_key(bucket, key, rec, rules, now)
            for upload_id, up in list(bucket.uploads.items()):
                for rule in rules:
                    if (
                        rule["enabled"]
                        and rule["abort_days"] is not None
                        and up["key"].startswith(rule["prefix"])
                        and now - up["initiated"] >= rule["abort_days"] * DAY
                    ):
                        abort_upload(bucket, upload_id)
                        changes += 1
                        break
    if changes:
        log("lifecycle:", changes, "changes")
    return changes


def _sweep_key(bucket: Bucket, key: str, rec: Dict[str, Any], rules: List[Dict[str, Any]], now: float) -> int:
    changes = 0
    versions = rec["versions"]
    current = versions[0]
    for rule in rules:
        if not current.get("dm") and _rule_matches(rule, key, current):
            due = (rule["exp_days"] is not None and now - current["time"] >= rule["exp_days"] * DAY) or (
                rule["exp_date"] is not None and now >= rule["exp_date"]
            )
            if due and not is_locked(current, now):
                delete_object(bucket, key, None, bypass=False)
                return 1
            for tr in rule["transitions"]:
                due = (tr["days"] is not None and now - current["time"] >= tr["days"] * DAY) or (
                    tr["date"] is not None and now >= tr["date"]
                )
                if due and tr["class"] and current.get("class", "STANDARD") != tr["class"]:
                    current["class"] = tr["class"]
                    bucket.save_record(key)
                    changes += 1
    noncurrent = versions[1:]
    for rule in rules:
        if not rule["enabled"] or not key.startswith(rule["prefix"]):
            continue
        if rule["nc_days"] is not None:
            kept = 0
            for version in list(noncurrent):
                if version.get("dm"):
                    continue
                if rule["nc_keep"] is not None and kept < rule["nc_keep"]:
                    kept += 1
                    continue
                # A version becomes noncurrent when the next newer one is written.
                since = versions[versions.index(version) - 1]["time"]
                if now - since >= rule["nc_days"] * DAY and not is_locked(version, now):
                    remove_version(bucket, key, version["id"])
                    changes += 1
        for tr in rule["nc_transitions"]:
            for version in versions[1:]:
                since = versions[versions.index(version) - 1]["time"]
                if (
                    not version.get("dm")
                    and tr["days"] is not None
                    and now - since >= tr["days"] * DAY
                    and tr["class"]
                    and version.get("class", "STANDARD") != tr["class"]
                ):
                    version["class"] = tr["class"]
                    bucket.save_record(key)
                    changes += 1
    rec = bucket.objects.get(key)
    if rec and len(rec["versions"]) == 1 and rec["versions"][0].get("dm"):
        if any(r["enabled"] and r["exp_marker"] and key.startswith(r["prefix"]) for r in rules):
            remove_version(bucket, key, rec["versions"][0]["id"])
            changes += 1
    return changes


def lifecycle_loop() -> None:
    time.sleep(min(60.0, LIFECYCLE_INTERVAL))
    while True:
        try:
            sweep_lifecycle()
        except Exception as exc:  # noqa: BLE001 - keep sweeping
            log("lifecycle error:", repr(exc))
        time.sleep(LIFECYCLE_INTERVAL)
