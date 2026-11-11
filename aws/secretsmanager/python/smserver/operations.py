"""The Secrets Manager API operations (``OPERATIONS``) and :func:`run`, which every request goes through."""

from __future__ import annotations

import json
import secrets
import string
import time
from typing import Any, Dict

from .config import ACCOUNT, NAME_RE, PUNCTUATION, log
from .errors import ApiError, bad_request, invalid
from .store import db
from .util import now, today
from .values import (
    add_version,
    describe,
    matches,
    merge_tags,
    move_stage,
    paginate,
    parse_tags,
    parse_value,
    pick_version,
    request_token,
    same_value,
    value_out,
)


def create_secret(p: Dict[str, Any], region: str) -> Dict[str, Any]:
    name = p.get("Name")
    if not isinstance(name, str) or not NAME_RE.match(name):
        raise invalid("Name must be 1-512 characters of letters, digits and /_+=.@-")
    value = parse_value(p)
    token = request_token(p)
    existing = db().secrets.get(name)
    if existing is not None:
        if existing.get("DeletedDate"):
            raise bad_request("You can't create this secret because a secret with this name is already scheduled for "
                           "deletion.")
        version = existing["Versions"].get(token)
        if value is not None and version is not None and same_value(version, value):
            return {"ARN": existing["ARN"], "Name": name, "VersionId": token}
        raise ApiError("ResourceExistsException", f"The operation failed because the secret {name} already exists.")
    suffix = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(6))
    created = now()
    secret: Dict[str, Any] = {
        "Name": name,
        "ARN": f"arn:aws:secretsmanager:{region}:{ACCOUNT}:secret:{name}-{suffix}",
        "CreatedDate": created,
        "LastChangedDate": created,
        "Tags": parse_tags(p.get("Tags")),
        "Versions": {},
    }
    if p.get("Description") is not None:
        secret["Description"] = str(p["Description"])
    if p.get("KmsKeyId"):
        db().keyring.key_id(p["KmsKeyId"], strict=True)
        secret["KmsKeyId"] = str(p["KmsKeyId"])
    out = {"ARN": secret["ARN"], "Name": name}
    if value is not None:
        add_version(secret, token, value, None)
        out["VersionId"] = token
    db().secrets[name] = secret
    db().save()
    return out


def get_secret_value(p: Dict[str, Any], _region: str) -> Dict[str, Any]:
    secret = db().live(p.get("SecretId"))
    vid, version = pick_version(secret, p)
    if secret.get("LastAccessedDate") != today():
        secret["LastAccessedDate"] = today()
        db().save()
    return value_out(secret, vid, version)


def batch_get_secret_value(p: Dict[str, Any], region: str) -> Dict[str, Any]:
    ids, filters = p.get("SecretIdList"), p.get("Filters")
    if ids and filters:
        raise invalid("Use either SecretIdList or Filters, not both.")
    values, errors = [], []
    if ids:
        if not isinstance(ids, list) or len(ids) > 20:
            raise invalid("SecretIdList holds 1-20 secret ids.")
        for sid in ids:
            try:
                values.append(get_secret_value({"SecretId": sid}, region))
            except ApiError as exc:
                errors.append({"SecretId": sid, "ErrorCode": exc.code, "Message": exc.message})
        return {"SecretValues": values, "Errors": errors}
    matched = [s for n, s in sorted(db().secrets.items()) if not s.get("DeletedDate") and matches(s, filters)]
    chunk, nxt = paginate(p, matched, 20)
    for secret in chunk:
        try:
            values.append(get_secret_value({"SecretId": secret["Name"]}, region))
        except ApiError as exc:
            errors.append({"SecretId": secret["Name"], "ErrorCode": exc.code, "Message": exc.message})
    out: Dict[str, Any] = {"SecretValues": values, "Errors": errors}
    if nxt:
        out["NextToken"] = nxt
    return out


def put_secret_value(p: Dict[str, Any], _region: str) -> Dict[str, Any]:
    secret = db().live(p.get("SecretId"))
    value = parse_value(p, required=True)
    token = request_token(p)
    assert value is not None
    stages = add_version(secret, token, value, p.get("VersionStages"))
    db().save()
    return {"ARN": secret["ARN"], "Name": secret["Name"], "VersionId": token, "VersionStages": stages}


def update_secret(p: Dict[str, Any], _region: str) -> Dict[str, Any]:
    secret = db().live(p.get("SecretId"))
    value = parse_value(p)
    if p.get("KmsKeyId"):
        db().keyring.key_id(p["KmsKeyId"], strict=True)
    out = {"ARN": secret["ARN"], "Name": secret["Name"]}
    if p.get("Description") is not None:
        secret["Description"] = str(p["Description"])
    if p.get("KmsKeyId"):
        secret["KmsKeyId"] = str(p["KmsKeyId"])
    if value is not None:
        token = request_token(p)
        add_version(secret, token, value, None)
        out["VersionId"] = token
    secret["LastChangedDate"] = now()
    db().save()
    return out


def describe_secret(p: Dict[str, Any], _region: str) -> Dict[str, Any]:
    return describe(db().find(p.get("SecretId")))


def list_secrets(p: Dict[str, Any], _region: str) -> Dict[str, Any]:
    include_deleted = bool(p.get("IncludePlannedDeletion"))
    items = [s for _n, s in sorted(db().secrets.items())
             if (include_deleted or not s.get("DeletedDate")) and matches(s, p.get("Filters"))]
    if p.get("SortOrder") == "desc":
        items.reverse()
    elif p.get("SortOrder") not in (None, "asc"):
        raise invalid("SortOrder must be asc or desc.")
    chunk, nxt = paginate(p, items)
    out: Dict[str, Any] = {"SecretList": [describe(s, list_shape=True) for s in chunk]}
    if nxt:
        out["NextToken"] = nxt
    return out


def delete_secret(p: Dict[str, Any], _region: str) -> Dict[str, Any]:
    secret = db().find(p.get("SecretId"))
    force = bool(p.get("ForceDeleteWithoutRecovery"))
    window = p.get("RecoveryWindowInDays")
    if force and window is not None:
        raise invalid("You can't use ForceDeleteWithoutRecovery in conjunction with RecoveryWindowInDays.")
    out = {"ARN": secret["ARN"], "Name": secret["Name"]}
    if force:
        del db().secrets[secret["Name"]]
        out["DeletionDate"] = now()
    else:
        if secret.get("DeletedDate"):
            raise bad_request("You can't perform this operation on the secret because it was already scheduled for "
                           "deletion.")
        try:
            days = int(window if window is not None else 30)
        except (TypeError, ValueError):
            raise invalid("RecoveryWindowInDays must be a number.") from None
        if not 7 <= days <= 30:
            raise invalid("RecoveryWindowInDays must be between 7 and 30 days.")
        secret["DeletedDate"] = now()
        secret["DeletionDate"] = round(time.time() + days * 86400, 3)
        out["DeletionDate"] = secret["DeletionDate"]
    db().save()
    return out


def restore_secret(p: Dict[str, Any], _region: str) -> Dict[str, Any]:
    secret = db().find(p.get("SecretId"))
    secret.pop("DeletedDate", None)
    secret.pop("DeletionDate", None)
    db().save()
    return {"ARN": secret["ARN"], "Name": secret["Name"]}


def list_secret_version_ids(p: Dict[str, Any], _region: str) -> Dict[str, Any]:
    secret = db().find(p.get("SecretId"))
    versions = sorted(secret["Versions"].items(), key=lambda kv: kv[1]["CreatedDate"], reverse=True)
    if not p.get("IncludeDeprecated"):
        versions = [(vid, v) for vid, v in versions if v["Stages"]]
    rows = [{"VersionId": vid, "VersionStages": list(v["Stages"]), "CreatedDate": v["CreatedDate"]}
            for vid, v in versions]
    chunk, nxt = paginate(p, rows)
    out: Dict[str, Any] = {"ARN": secret["ARN"], "Name": secret["Name"], "Versions": chunk}
    if nxt:
        out["NextToken"] = nxt
    return out


def update_secret_version_stage(p: Dict[str, Any], _region: str) -> Dict[str, Any]:
    secret = db().live(p.get("SecretId"))
    stage = p.get("VersionStage")
    if not isinstance(stage, str) or not stage:
        raise invalid("VersionStage is required.")
    remove_from, move_to = p.get("RemoveFromVersionId"), p.get("MoveToVersionId")
    versions = secret["Versions"]
    holder = next((vid for vid, v in versions.items() if stage in v["Stages"]), None)
    if holder and move_to and holder != move_to and remove_from != holder:
        raise invalid(f"The staging label {stage} is currently attached to version {holder}, so you must "
                       "explicitly reference that version in RemoveFromVersionId.")
    for vid in (remove_from, move_to):
        if vid and vid not in versions:
            raise invalid(f"Version {vid} does not exist.")
    if move_to:
        move_stage(secret, stage, move_to)
    elif remove_from:
        if stage == "AWSCURRENT":
            raise invalid("You can't remove AWSCURRENT; move it to another version instead.")
        if stage in versions[remove_from]["Stages"]:
            versions[remove_from]["Stages"].remove(stage)
    secret["LastChangedDate"] = now()
    db().save()
    return {"ARN": secret["ARN"], "Name": secret["Name"]}


def tag_resource(p: Dict[str, Any], _region: str) -> Dict[str, Any]:
    secret = db().find(p.get("SecretId"))
    secret["Tags"] = merge_tags(secret.get("Tags") or [], parse_tags(p.get("Tags")))
    db().save()
    return {}


def untag_resource(p: Dict[str, Any], _region: str) -> Dict[str, Any]:
    secret = db().find(p.get("SecretId"))
    keys = p.get("TagKeys") or []
    if not isinstance(keys, list):
        raise invalid("TagKeys must be a list.")
    secret["Tags"] = [t for t in secret.get("Tags") or [] if t["Key"] not in keys]
    db().save()
    return {}


def get_random_password(p: Dict[str, Any], _region: str) -> Dict[str, Any]:
    try:
        length = int(p.get("PasswordLength") or 32)
    except (TypeError, ValueError):
        raise invalid("PasswordLength must be a number.") from None
    if not 1 <= length <= 4096:
        raise invalid("PasswordLength must be between 1 and 4096.")
    exclude = str(p.get("ExcludeCharacters") or "")
    groups = []
    if not p.get("ExcludeLowercase"):
        groups.append(string.ascii_lowercase)
    if not p.get("ExcludeUppercase"):
        groups.append(string.ascii_uppercase)
    if not p.get("ExcludeNumbers"):
        groups.append(string.digits)
    if not p.get("ExcludePunctuation"):
        groups.append(PUNCTUATION)
    if p.get("IncludeSpace"):
        groups.append(" ")
    groups = [g for g in ("".join(c for c in grp if c not in exclude) for grp in groups) if g]
    if not groups:
        raise invalid("The password has no characters left to use.")
    every = p.get("RequireEachIncludedType", True)
    if every and length < len(groups):
        raise invalid("PasswordLength is too short to include every character type.")
    pool = "".join(groups)
    rng = secrets.SystemRandom()
    chars = [rng.choice(g) for g in groups] if every else []
    chars += [rng.choice(pool) for _ in range(length - len(chars))]
    rng.shuffle(chars)
    return {"RandomPassword": "".join(chars)}


def put_resource_policy(p: Dict[str, Any], _region: str) -> Dict[str, Any]:
    secret = db().live(p.get("SecretId"))
    policy = p.get("ResourcePolicy")
    try:
        json.loads(str(policy))
    except ValueError:
        raise ApiError("MalformedPolicyDocumentException", "ResourcePolicy must be a JSON policy document.") from None
    secret["ResourcePolicy"] = str(policy)
    db().save()
    return {"ARN": secret["ARN"], "Name": secret["Name"]}


def get_resource_policy(p: Dict[str, Any], _region: str) -> Dict[str, Any]:
    secret = db().find(p.get("SecretId"))
    out = {"ARN": secret["ARN"], "Name": secret["Name"]}
    if secret.get("ResourcePolicy"):
        out["ResourcePolicy"] = secret["ResourcePolicy"]
    return out


def delete_resource_policy(p: Dict[str, Any], _region: str) -> Dict[str, Any]:
    secret = db().find(p.get("SecretId"))
    secret.pop("ResourcePolicy", None)
    db().save()
    return {"ARN": secret["ARN"], "Name": secret["Name"]}


def validate_resource_policy(p: Dict[str, Any], _region: str) -> Dict[str, Any]:
    try:
        json.loads(str(p.get("ResourcePolicy")))
    except ValueError:
        raise ApiError("MalformedPolicyDocumentException", "ResourcePolicy must be a JSON policy document.") from None
    return {"PolicyValidationPassed": True, "ValidationErrors": []}


def _unsupported(name: str) -> Any:
    def handler(_p: Dict[str, Any], _region: str) -> Dict[str, Any]:
        raise bad_request(f"{name} is not supported by this Secrets Manager compatible server (no rotation functions or "
                       "replica regions).")
    return handler


OPERATIONS = {
    "CreateSecret": create_secret,
    "GetSecretValue": get_secret_value,
    "BatchGetSecretValue": batch_get_secret_value,
    "PutSecretValue": put_secret_value,
    "UpdateSecret": update_secret,
    "DescribeSecret": describe_secret,
    "ListSecrets": list_secrets,
    "DeleteSecret": delete_secret,
    "RestoreSecret": restore_secret,
    "ListSecretVersionIds": list_secret_version_ids,
    "UpdateSecretVersionStage": update_secret_version_stage,
    "TagResource": tag_resource,
    "UntagResource": untag_resource,
    "GetRandomPassword": get_random_password,
    "PutResourcePolicy": put_resource_policy,
    "GetResourcePolicy": get_resource_policy,
    "DeleteResourcePolicy": delete_resource_policy,
    "ValidateResourcePolicy": validate_resource_policy,
    **{name: _unsupported(name) for name in ("RotateSecret", "CancelRotateSecret", "ReplicateSecretToRegions",
                                              "RemoveRegionsFromReplication", "StopReplicationToReplica")},
}
# Operations that change nothing: they are not logged.
READS = {"GetSecretValue", "BatchGetSecretValue", "DescribeSecret", "ListSecrets", "ListSecretVersionIds",
         "GetRandomPassword", "GetResourcePolicy", "ValidateResourcePolicy"}


def run(operation: str, params: Dict[str, Any], region: str, who: str) -> Dict[str, Any]:
    handler = OPERATIONS.get(operation)
    if handler is None:
        raise ApiError("UnknownOperationException", f"Operation {operation} is not known.")
    if not isinstance(params, dict):
        raise ApiError("SerializationException", "The request body must be a JSON object.")
    with db().lock:
        db().purge()
        out = handler(params, region)
    if operation not in READS:
        log(operation, params.get("SecretId") or params.get("Name") or "", "by", who)
    return out
