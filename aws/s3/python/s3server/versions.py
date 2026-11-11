"""Object versions: finding one, writing a new current version, deleting (delete markers) and removing."""

from __future__ import annotations

import base64
import re
import secrets
from typing import Any, Dict, Optional

from .config import OWNER_ID
from .errors import S3Error, invalid, no_key
from .objectlock import check_unlocked
from .store import Bucket, unlink
from .util import http_date, timestamp


def new_version_id() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(24)).decode().replace("-", ".")


def find_version(bucket: Bucket, key: str, version_id: Optional[str], *, allow_marker: bool = False) -> Dict[str, Any]:
    rec = bucket.objects.get(key)
    if version_id is not None:
        if version_id == "":
            raise invalid("Version id cannot be the empty string", "versionId", "")
        for version in (rec or {}).get("versions", []):
            if version["id"] == version_id:
                if version.get("dm") and not allow_marker:
                    err = S3Error(
                        "MethodNotAllowed",
                        "The specified method is not allowed against this resource.",
                        405,
                        Method="GET",
                        ResourceType="DeleteMarker",
                    )
                    err.headers = {
                        "x-amz-delete-marker": "true",
                        "x-amz-version-id": version_id,
                        "Last-Modified": http_date(version["time"]),
                    }
                    raise err
                return version
        if rec is None and not re.fullmatch(r"[A-Za-z0-9._=-]+", version_id):
            raise invalid("Invalid version id specified", "versionId", version_id)
        raise S3Error("NoSuchVersion", "The specified version does not exist.", 404, Key=key, VersionId=version_id)
    if not rec:
        raise no_key(key)
    latest = rec["versions"][0]
    if latest.get("dm"):
        err = no_key(key)
        err.headers = {"x-amz-delete-marker": "true", "x-amz-version-id": latest["id"]}
        raise err
    return latest


def remove_version(bucket: Bucket, key: str, version_id: str) -> Optional[Dict[str, Any]]:
    rec = bucket.objects.get(key)
    if not rec:
        return None
    for idx, version in enumerate(rec["versions"]):
        if version["id"] == version_id:
            del rec["versions"][idx]
            bucket.save_record(key)
            if version.get("blob"):
                unlink(bucket.blob_path(version["blob"]))
            return version
    return None


def put_version(bucket: Bucket, key: str, version: Dict[str, Any]) -> Dict[str, Any]:
    """Make ``version`` the newest version of ``key``, under the bucket's versioning state. Caller holds the lock."""
    rec = bucket.objects.get(key) or {"key": key, "versions": []}
    if bucket.meta.get("versioning") == "Enabled":
        version["id"] = new_version_id()
    else:
        version["id"] = "null"
        for old in [v for v in rec["versions"] if v["id"] == "null"]:
            rec["versions"].remove(old)
            if old.get("blob"):
                unlink(bucket.blob_path(old["blob"]))
    rec["versions"].insert(0, version)
    bucket.set_record(key, rec)
    return version


def delete_object(bucket: Bucket, key: str, version_id: Optional[str], *, bypass: bool) -> Dict[str, Any]:
    """{"marker": bool, "id": version id or ""}. Caller holds the lock."""
    rec = bucket.objects.get(key)
    if version_id is not None:
        for version in (rec or {}).get("versions", []):
            if version["id"] == version_id:
                if not version.get("dm"):
                    check_unlocked(version, bypass)
                remove_version(bucket, key, version_id)
                return {"marker": bool(version.get("dm")), "id": version_id}
        return {"marker": False, "id": version_id}
    state = bucket.meta.get("versioning")
    if not state:
        if rec:
            for version in list(rec["versions"]):
                remove_version(bucket, key, version["id"])
        return {"marker": False, "id": ""}
    marker = {"dm": True, "time": timestamp(), "owner": OWNER_ID}
    put_version(bucket, key, marker)
    return {"marker": True, "id": marker["id"]}
