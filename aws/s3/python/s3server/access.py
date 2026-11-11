"""Access control: ACLs, block public access, ownership controls, and the access decision for a request."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .config import ALL_USERS, AUTH_USERS, CANNED, LOG_DELIVERY, OWNER_ID, OWNER_NAME
from .errors import S3Error, invalid, malformed
from .policy import POLICY_ACTIONS, Context, evaluate_policy, is_public_policy, parse_policy
from .store import Bucket
from .util import doc, owner_xml, parse_xml, text, x


def acl_from_canned(canned: str) -> List[Dict[str, str]]:
    grants = [{"type": "CanonicalUser", "id": OWNER_ID, "permission": "FULL_CONTROL"}]
    if canned in ("public-read", "public-read-write"):
        grants.append({"type": "Group", "uri": ALL_USERS, "permission": "READ"})
    if canned == "public-read-write":
        grants.append({"type": "Group", "uri": ALL_USERS, "permission": "WRITE"})
    if canned == "authenticated-read":
        grants.append({"type": "Group", "uri": AUTH_USERS, "permission": "READ"})
    if canned == "log-delivery-write":
        grants += [
            {"type": "Group", "uri": LOG_DELIVERY, "permission": "WRITE"},
            {"type": "Group", "uri": LOG_DELIVERY, "permission": "READ_ACP"},
        ]
    return grants


def acl_grants(acl: Any) -> List[Dict[str, str]]:
    if isinstance(acl, dict) and isinstance(acl.get("grants"), list):
        return acl["grants"]
    canned = acl.get("canned", "private") if isinstance(acl, dict) else "private"
    return acl_from_canned(canned)


def acl_xml(acl: Any) -> bytes:
    inner = []
    for g in acl_grants(acl):
        if g["type"] == "Group":
            grantee = (
                f'<Grantee xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="Group">'
                f"{x('URI', g['uri'])}</Grantee>"
            )
        elif g["type"] == "AmazonCustomerByEmail":
            grantee = (
                f'<Grantee xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
                f'xsi:type="AmazonCustomerByEmail">{x("EmailAddress", g.get("email", ""))}</Grantee>'
            )
        else:
            name = OWNER_NAME if g.get("id") == OWNER_ID else g.get("name", "")
            grantee = (
                f'<Grantee xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="CanonicalUser">'
                f"{x('ID', g.get('id', ''))}{x('DisplayName', name) if name else ''}</Grantee>"
            )
        inner.append(f"<Grant>{grantee}{x('Permission', g['permission'])}</Grant>")
    return doc("AccessControlPolicy", owner_xml() + "<AccessControlList>" + "".join(inner) + "</AccessControlList>")


_GRANT_HEADERS = {
    "x-amz-grant-read": "READ",
    "x-amz-grant-write": "WRITE",
    "x-amz-grant-read-acp": "READ_ACP",
    "x-amz-grant-write-acp": "WRITE_ACP",
    "x-amz-grant-full-control": "FULL_CONTROL",
}


def acl_from_request(
    headers: Dict[str, str], body: bytes, default: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    canned = headers.get("x-amz-acl", "")
    grants: List[Dict[str, str]] = []
    for header, permission in _GRANT_HEADERS.items():
        for item in re.findall(r'(id|uri|emailAddress)\s*=\s*"?([^",]+)"?', headers.get(header, "")):
            kind, value = item
            if kind == "id":
                grants.append({"type": "CanonicalUser", "id": value, "permission": permission})
            elif kind == "uri":
                grants.append({"type": "Group", "uri": value, "permission": permission})
            else:
                grants.append({"type": "AmazonCustomerByEmail", "email": value, "permission": permission})
    if canned and grants:
        raise invalid("Specifying both Canned ACLs and Header Grants is not allowed")
    if canned:
        if canned not in CANNED:
            raise invalid(f"{canned} is not a canned ACL.", "x-amz-acl", canned)
        return {"canned": canned}
    if grants:
        return {"grants": grants}
    if body.strip():
        root = parse_xml(body)
        found = []
        for grant in root.iter("Grant"):
            grantee, permission = grant.find("Grantee"), text(grant, "Permission")
            if grantee is None or permission not in ("READ", "WRITE", "READ_ACP", "WRITE_ACP", "FULL_CONTROL"):
                raise malformed()
            if text(grantee, "URI"):
                found.append({"type": "Group", "uri": text(grantee, "URI"), "permission": permission})
            elif text(grantee, "EmailAddress"):
                found.append(
                    {"type": "AmazonCustomerByEmail", "email": text(grantee, "EmailAddress"), "permission": permission}
                )
            else:
                found.append(
                    {
                        "type": "CanonicalUser",
                        "id": text(grantee, "ID"),
                        "name": text(grantee, "DisplayName"),
                        "permission": permission,
                    }
                )
        return {"grants": found}
    return default


def acl_public(acl: Any, permission: str) -> bool:
    return any(
        g["type"] == "Group"
        and g.get("uri") in (ALL_USERS, AUTH_USERS)
        and g["permission"] in (permission, "FULL_CONTROL")
        for g in acl_grants(acl)
    )


def acl_canned_name(acl: Any) -> str:
    if isinstance(acl, dict) and acl.get("canned"):
        return str(acl["canned"])
    return "custom" if isinstance(acl, dict) and acl.get("grants") else "private"


def bucket_owner_enforced(bucket: Bucket) -> bool:
    return "BucketOwnerEnforced" in (bucket.meta.get("configs") or {}).get("ownershipControls", "")


def public_block(bucket: Bucket) -> Dict[str, bool]:
    raw = (bucket.meta.get("configs") or {}).get("publicAccessBlock", "")
    out = {
        "BlockPublicAcls": False,
        "IgnorePublicAcls": False,
        "BlockPublicPolicy": False,
        "RestrictPublicBuckets": False,
    }
    if raw:
        try:
            root = parse_xml(raw.encode())
        except S3Error:
            return out
        for name in out:
            out[name] = text(root, name).lower() == "true"
    return out


def ownership(bucket: Bucket) -> str:
    """The bucket's ObjectOwnership setting, or "" when it has no ownership controls."""
    raw = (bucket.meta.get("configs") or {}).get("ownershipControls", "")
    if not raw:
        return ""
    try:
        return text(parse_xml(raw.encode()), "Rule/ObjectOwnership")
    except S3Error:
        return ""


def bucket_policy(bucket: Bucket) -> Optional[Dict[str, Any]]:
    """The parsed bucket policy (cached until the bucket's settings change)."""
    if "policy" not in bucket.parsed:
        bucket.parsed["policy"] = parse_policy(bucket.meta.get("policy"))
    return bucket.parsed["policy"]


def policy_is_public(bucket: Bucket) -> bool:
    return is_public_policy(bucket_policy(bucket))


def bucket_access(bucket: Bucket) -> str:
    """The console's access summary: "public", "not-public" or "objects-can-be-public"."""
    block = public_block(bucket)
    if policy_is_public(bucket) and not block["RestrictPublicBuckets"]:
        return "public"
    acl_counts = not block["IgnorePublicAcls"] and not bucket_owner_enforced(bucket)
    if acl_counts and acl_public(bucket.meta.get("acl"), "READ"):
        return "public"
    if all(block.values()):
        return "not-public"
    return "objects-can-be-public"


def allowed(bucket: Bucket, action: str, ctx: Context, key: str = "", version: Optional[Dict[str, Any]] = None) -> bool:
    """May the requester in ``ctx`` do ``action`` on the bucket (or its ``key``, whose ``version`` is known)?

    A matching Deny refuses everyone (a signed request may still manage the policy); a signed request is otherwise
    allowed; an anonymous one needs a policy Allow (ignored under RestrictPublicBuckets) or a public ACL.
    """
    resource = f"arn:aws:s3:::{bucket.name}" + (f"/{key}" if key else "")
    tags = (version or {}).get("tags") or {}
    decision = evaluate_policy(bucket_policy(bucket), action, resource, ctx, tags)
    signed = ctx.principal is not None
    if decision == "deny" and not (signed and action in POLICY_ACTIONS):
        return False
    if signed:
        return True
    if decision == "allow" and not public_block(bucket)["RestrictPublicBuckets"]:
        return True
    return _acl_allows(bucket, action, version)


def _acl_allows(bucket: Bucket, action: str, version: Optional[Dict[str, Any]]) -> bool:
    if public_block(bucket)["IgnorePublicAcls"] or bucket_owner_enforced(bucket):
        return False
    if action in ("s3:ListBucket", "s3:ListBucketVersions", "s3:ListBucketMultipartUploads"):
        return acl_public(bucket.meta.get("acl"), "READ")
    if action in ("s3:PutObject", "s3:DeleteObject", "s3:AbortMultipartUpload", "s3:ListMultipartUploadParts"):
        return acl_public(bucket.meta.get("acl"), "WRITE")
    if action in ("s3:GetObject", "s3:GetObjectVersion") and version is not None:
        return acl_public(version.get("acl"), "READ")
    return False
