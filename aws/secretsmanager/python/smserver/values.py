"""Helpers of the operations: request tokens, values, tags, staging labels, versions, paging and ListSecrets filters."""

from __future__ import annotations

import base64
import uuid
from typing import Any, Dict, List, Optional, Tuple

from .config import MAX_VALUE, MAX_VERSIONS
from .errors import ApiError, invalid
from .util import now


def request_token(params: Dict[str, Any]) -> str:
    token = params.get("ClientRequestToken")
    if token is None:
        return str(uuid.uuid4())
    if not isinstance(token, str) or not 32 <= len(token) <= 64:
        raise invalid("ClientRequestToken must be 32-64 characters.")
    return token


def parse_value(params: Dict[str, Any], required: bool = False) -> Optional[Dict[str, str]]:
    text, blob = params.get("SecretString"), params.get("SecretBinary")
    if text is not None and blob is not None:
        raise invalid("You can't specify both a binary secret value and a string secret value in the same secret.")
    if text is not None:
        if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_VALUE:
            raise invalid(f"SecretString must be a string of at most {MAX_VALUE} bytes.")
        return {"SecretString": text}
    if blob is not None:
        try:
            raw = base64.b64decode(str(blob), validate=True)
        except ValueError:
            raise invalid("SecretBinary must be base64.") from None
        if len(raw) > MAX_VALUE:
            raise invalid(f"SecretBinary must be at most {MAX_VALUE} bytes.")
        return {"SecretBinary": base64.b64encode(raw).decode("ascii")}
    if required:
        raise invalid("You must provide either SecretString or SecretBinary.")
    return None


def parse_tags(raw: Any) -> List[Dict[str, str]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise invalid("Tags must be a list of {Key, Value}.")
    out = []
    for tag in raw:
        if not isinstance(tag, dict) or not isinstance(tag.get("Key"), str) or not 1 <= len(tag["Key"]) <= 128:
            raise invalid("Each tag needs a Key of 1-128 characters.")
        out.append({"Key": tag["Key"], "Value": str(tag.get("Value") or "")})
    return out


def merge_tags(old: List[Dict[str, str]], new: List[Dict[str, str]]) -> List[Dict[str, str]]:
    merged = {t["Key"]: t["Value"] for t in old}
    merged.update({t["Key"]: t["Value"] for t in new})
    return [{"Key": k, "Value": v} for k, v in merged.items()]


def stages_of(secret: Dict[str, Any]) -> Dict[str, List[str]]:
    return {vid: list(v["Stages"]) for vid, v in secret["Versions"].items() if v["Stages"]}


def same_value(version: Dict[str, Any], value: Dict[str, str]) -> bool:
    return version.get("SecretString") == value.get("SecretString") and \
        version.get("SecretBinary") == value.get("SecretBinary")


def move_stage(secret: Dict[str, Any], stage: str, to: str) -> None:
    """Attach ``stage`` to version ``to`` only. Moving AWSCURRENT gives the old current version AWSPREVIOUS."""
    versions = secret["Versions"]
    for vid, version in versions.items():
        if vid != to and stage in version["Stages"]:
            version["Stages"].remove(stage)
            if stage == "AWSCURRENT":
                for other in versions.values():
                    if "AWSPREVIOUS" in other["Stages"]:
                        other["Stages"].remove("AWSPREVIOUS")
                version["Stages"].append("AWSPREVIOUS")
    if stage not in versions[to]["Stages"]:
        versions[to]["Stages"].append(stage)


def prune(secret: Dict[str, Any]) -> None:
    versions = secret["Versions"]
    if len(versions) <= MAX_VERSIONS:
        return
    old = sorted((v["CreatedDate"], vid) for vid, v in versions.items() if not v["Stages"])
    for _created, vid in old[: len(versions) - MAX_VERSIONS]:
        del versions[vid]


def add_version(secret: Dict[str, Any], token: str, value: Dict[str, str], stages: Optional[List[str]]) -> List[str]:
    """A new version of ``secret`` (idempotent for the same token and value). Returns its stages."""
    if token in secret["Versions"]:
        existing = secret["Versions"][token]
        if not same_value(existing, value):
            raise ApiError("ResourceExistsException",
                           "You can't modify an existing version, you can only create a new version.")
        return list(existing["Stages"])
    if stages is None:
        stages = ["AWSCURRENT"]
    if not isinstance(stages, list) or not all(isinstance(s, str) and 1 <= len(s) <= 256 for s in stages):
        raise invalid("VersionStages must be a list of staging labels.")
    secret["Versions"][token] = {**value, "CreatedDate": now(), "Stages": []}
    for stage in dict.fromkeys(stages):
        move_stage(secret, stage, token)
    secret["LastChangedDate"] = now()
    prune(secret)
    return list(secret["Versions"][token]["Stages"])


def pick_version(secret: Dict[str, Any], params: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    vid, stage = params.get("VersionId"), params.get("VersionStage")
    versions = secret["Versions"]
    if vid:
        version = versions.get(vid)
        if version is None or (stage and stage not in version["Stages"]):
            raise ApiError("ResourceNotFoundException",
                           f"Secrets Manager can't find the specified secret value for VersionId: {vid}")
        return vid, version
    stage = stage or "AWSCURRENT"
    for vid, version in versions.items():
        if stage in version["Stages"]:
            return vid, version
    raise ApiError("ResourceNotFoundException",
                   f"Secrets Manager can't find the specified secret value for staging label: {stage}")


def value_out(secret: Dict[str, Any], vid: str, version: Dict[str, Any]) -> Dict[str, Any]:
    out = {"ARN": secret["ARN"], "Name": secret["Name"], "VersionId": vid,
           "VersionStages": list(version["Stages"]), "CreatedDate": version["CreatedDate"]}
    for field in ("SecretString", "SecretBinary"):
        if field in version:
            out[field] = version[field]
    return out


def describe(secret: Dict[str, Any], *, list_shape: bool = False) -> Dict[str, Any]:
    out: Dict[str, Any] = {"ARN": secret["ARN"], "Name": secret["Name"], "RotationEnabled": False,
                           "CreatedDate": secret["CreatedDate"], "LastChangedDate": secret["LastChangedDate"]}
    for field in ("Description", "KmsKeyId", "LastAccessedDate", "DeletedDate"):
        if secret.get(field) is not None:
            out[field] = secret[field]
    if secret.get("Tags"):
        out["Tags"] = [dict(t) for t in secret["Tags"]]
    out["SecretVersionsToStages" if list_shape else "VersionIdsToStages"] = stages_of(secret)
    return out


def paginate(params: Dict[str, Any], items: List[Any], limit_default: int = 100) -> Tuple[List[Any], Optional[str]]:
    try:
        limit = int(params.get("MaxResults") or limit_default)
    except (TypeError, ValueError):
        raise invalid("MaxResults must be a number.") from None
    if not 1 <= limit <= 100:
        raise invalid("MaxResults must be between 1 and 100.")
    start = 0
    if params.get("NextToken"):
        try:
            start = int(base64.b64decode(str(params["NextToken"])).decode("ascii"))
        except (ValueError, UnicodeDecodeError):
            raise invalid("NextToken is not valid.") from None
    chunk = items[start:start + limit]
    more = start + limit < len(items)
    return chunk, (base64.b64encode(str(start + limit).encode("ascii")).decode("ascii") if more else None)


def matches(secret: Dict[str, Any], filters: Any) -> bool:
    """ListSecrets filters: every filter must match; a filter matches when one of its values (a case-insensitive
    prefix, ``!`` in front negates) matches."""
    if not filters:
        return True
    if not isinstance(filters, list):
        raise invalid("Filters must be a list of {Key, Values}.")
    for flt in filters:
        key = (flt or {}).get("Key")
        values = (flt or {}).get("Values") or []
        tags = secret.get("Tags") or []
        fields = {
            "name": [secret["Name"]],
            "description": [secret.get("Description") or ""],
            "tag-key": [t["Key"] for t in tags],
            "tag-value": [t["Value"] for t in tags],
            "primary-region": [],
            "owning-service": [],
        }
        if key == "all":
            candidates = [c for name in ("name", "description", "tag-key", "tag-value") for c in fields[name]]
        elif key in fields:
            candidates = fields[key]
        else:
            raise invalid(f"Filter key {key!r} is not valid.")
        hit = False
        for value in values:
            text = str(value)
            negate = text.startswith("!")
            text = text[1:] if negate else text
            found = any(c.lower().startswith(text.lower()) for c in candidates)
            if found != negate:
                hit = True
                break
        if not hit:
            return False
    return True
