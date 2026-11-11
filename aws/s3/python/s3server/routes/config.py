"""Bucket settings (``?versioning``, ``?policy``, ``?acl``, ``?cors`` ...): get, put and delete."""

from __future__ import annotations

import json

from ..access import acl_from_request, acl_public, acl_xml, bucket_owner_enforced, policy_is_public, public_block
from ..config import CONFIGS, EMPTY_CONFIGS, ID_CONFIGS
from ..cors import validate_cors
from ..errors import S3Error, denied, invalid, malformed
from ..lifecycle import parse_lifecycle
from ..objects import tags_from_xml, tags_xml
from ..policy import is_public_policy
from ..request import Request, Response, xml_response
from ..store import Bucket, get_store
from ..util import as_list, parse_xml, strip_decl, text, x


def bucket_config(req: Request, bucket: Bucket, sub: str) -> Response:
    method = req.method
    configs = bucket.meta.setdefault("configs", {})
    if sub == "versioning":
        if method == "GET":
            inner = ""
            if bucket.meta.get("versioning"):
                inner += x("Status", bucket.meta["versioning"])
            if bucket.meta.get("mfa_delete"):
                inner += x("MfaDelete", bucket.meta["mfa_delete"])
            return xml_response("VersioningConfiguration", inner)
        if method == "PUT":
            root = parse_xml(req.small_body())
            status = text(root, "Status")
            if status not in ("Enabled", "Suspended", ""):
                raise malformed()
            with get_store().lock:
                if bucket.meta.get("object_lock") and status == "Suspended":
                    raise S3Error(
                        "InvalidBucketState",
                        "An Object Lock configuration is present on this bucket, so "
                        "the versioning state cannot be changed.",
                        409,
                    )
                if status:
                    bucket.meta["versioning"] = status
                if text(root, "MfaDelete"):
                    bucket.meta["mfa_delete"] = text(root, "MfaDelete")
                bucket.save_meta()
            return Response(200)
    if sub == "tagging":
        if method == "GET":
            if not bucket.meta.get("tags"):
                raise S3Error("NoSuchTagSet", "The TagSet does not exist", 404, BucketName=bucket.name)
            return Response(200, tags_xml(bucket.meta["tags"]))
        if method == "PUT":
            tags = tags_from_xml(req.small_body(), 50)
            with get_store().lock:
                bucket.meta["tags"] = tags
                bucket.save_meta()
            return Response(204)
        if method == "DELETE":
            with get_store().lock:
                bucket.meta["tags"] = {}
                bucket.save_meta()
            return Response(204)
    if sub == "policy":
        if method == "GET":
            if not bucket.meta.get("policy"):
                raise S3Error("NoSuchBucketPolicy", "The bucket policy does not exist", 404, BucketName=bucket.name)
            return Response(200, bucket.meta["policy"].encode(), ctype="application/json")
        if method == "PUT":
            raw = req.small_body(20 * 1024).decode("utf-8", "replace")
            set_policy(bucket, raw)
            return Response(204)
        if method == "DELETE":
            with get_store().lock:
                bucket.meta["policy"] = None
                bucket.save_meta()
            return Response(204)
    if sub == "policyStatus" and method == "GET":
        return xml_response("PolicyStatus", x("IsPublic", "true" if policy_is_public(bucket) else "false"))
    if sub == "acl":
        if method == "GET":
            return Response(200, acl_xml(bucket.meta.get("acl")))
        if method == "PUT":
            acl = acl_from_request(req.headers, req.small_body())
            if acl is None:
                raise malformed()
            if bucket_owner_enforced(bucket) and acl.get("canned") not in ("private", "bucket-owner-full-control"):
                raise S3Error("AccessControlListNotSupported", "The bucket does not allow ACLs")
            if public_block(bucket)["BlockPublicAcls"] and (acl_public(acl, "READ") or acl_public(acl, "WRITE")):
                raise denied()
            with get_store().lock:
                bucket.meta["acl"] = acl
                bucket.save_meta()
            return Response(200)
    if sub in ID_CONFIGS:
        store = bucket.meta.setdefault("ids", {}).setdefault(sub, {})
        config_id = req.q.get("id", "")
        element = ID_CONFIGS[sub]
        if method == "GET" and not config_id:
            inner = "".join(strip_decl(v) for _k, v in sorted(store.items())) + x("IsTruncated", "false")
            root = {
                "metrics": "ListMetricsConfigurationsResult",
                "analytics": "ListBucketAnalyticsConfigurationResult",
                "inventory": "ListInventoryConfigurationsResult",
                "intelligent-tiering": "ListBucketIntelligentTieringConfigurationsOutput",
            }[sub]
            return xml_response(root, inner)
        if not config_id:
            raise invalid("The id parameter is required", "id", "")
        if method == "GET":
            if config_id not in store:
                raise S3Error("NoSuchConfiguration", "The specified configuration does not exist.", 404)
            return Response(200, ('<?xml version="1.0" encoding="UTF-8"?>\n' + strip_decl(store[config_id])).encode())
        if method == "PUT":
            body = req.small_body()
            root = parse_xml(body)
            if root.tag != element:
                raise malformed()
            with get_store().lock:
                store[config_id] = body.decode("utf-8")
                bucket.save_meta()
            return Response(204 if sub != "inventory" else 200)
        if method == "DELETE":
            with get_store().lock:
                store.pop(config_id, None)
                bucket.save_meta()
            return Response(204)
    if sub in CONFIGS:
        missing_code, missing_message = CONFIGS[sub]
        if method == "GET":
            raw = configs.get(sub)
            if not raw:
                if sub in EMPTY_CONFIGS:
                    return Response(200, ('<?xml version="1.0" encoding="UTF-8"?>\n' + EMPTY_CONFIGS[sub]).encode())
                if sub == "encryption":
                    alg = "AES256"
                    return xml_response(
                        "ServerSideEncryptionConfiguration",
                        f"<Rule><ApplyServerSideEncryptionByDefault>{x('SSEAlgorithm', alg)}"
                        "</ApplyServerSideEncryptionByDefault><BucketKeyEnabled>false"
                        "</BucketKeyEnabled></Rule>",
                    )
                raise S3Error(missing_code, missing_message, 404, BucketName=bucket.name)
            return Response(200, ('<?xml version="1.0" encoding="UTF-8"?>\n' + strip_decl(raw)).encode())
        if method == "PUT":
            body = req.small_body()
            set_config(bucket, sub, body)
            return Response(200)
        if method == "DELETE":
            if sub == "object-lock":
                raise S3Error("MethodNotAllowed", "The specified method is not allowed against this resource.", 405)
            with get_store().lock:
                configs.pop(sub, None)
                bucket.save_meta()
            return Response(204)
    raise S3Error(
        "NotImplemented", "A header or query you provided implies functionality that is not implemented.", 501
    )


def set_policy(bucket: Bucket, raw: str) -> None:
    try:
        policy = json.loads(raw)
    except ValueError:
        raise S3Error("MalformedPolicy", "Policies must be valid JSON and the first byte must be '{'") from None
    if not isinstance(policy, dict) or not isinstance(policy.get("Statement"), (list, dict)):
        raise S3Error("MalformedPolicy", "Missing required field Statement")
    for st in as_list(policy["Statement"]):
        if not isinstance(st, dict) or st.get("Effect") not in ("Allow", "Deny"):
            raise S3Error("MalformedPolicy", "Statement must have an Effect of Allow or Deny")
        if "Action" not in st and "NotAction" not in st:
            raise S3Error("MalformedPolicy", "Missing required field Action")
        for resource in as_list(st.get("Resource")):
            if isinstance(resource, str) and not resource.startswith(f"arn:aws:s3:::{bucket.name}"):
                raise S3Error("MalformedPolicy", "Policy has invalid resource")
    if public_block(bucket)["BlockPublicPolicy"] and is_public_policy(policy):
        raise denied()
    with get_store().lock:
        bucket.meta["policy"] = raw
        bucket.save_meta()


def set_config(bucket: Bucket, sub: str, body: bytes) -> None:
    root = parse_xml(body)
    expected = {
        "cors": "CORSConfiguration",
        "lifecycle": "LifecycleConfiguration",
        "website": "WebsiteConfiguration",
        "encryption": "ServerSideEncryptionConfiguration",
        "replication": "ReplicationConfiguration",
        "ownershipControls": "OwnershipControls",
        "publicAccessBlock": "PublicAccessBlockConfiguration",
        "object-lock": "ObjectLockConfiguration",
        "logging": "BucketLoggingStatus",
        "notification": "NotificationConfiguration",
        "accelerate": "AccelerateConfiguration",
        "requestPayment": "RequestPaymentConfiguration",
    }[sub]
    if root.tag != expected:
        raise malformed()
    if sub == "cors":
        validate_cors(body)
    elif sub == "lifecycle":
        parse_lifecycle(body)
    elif sub == "website":
        if root.find("RedirectAllRequestsTo") is None and not text(root, "IndexDocument/Suffix"):
            raise invalid("A value for IndexDocument Suffix must be provided if RedirectAllRequestsTo is empty")
    elif sub == "replication":
        if bucket.meta.get("versioning") != "Enabled":
            raise S3Error(
                "InvalidRequest", "Versioning must be 'Enabled' on the bucket to apply a replication configuration"
            )
    elif sub == "object-lock":
        if text(root, "ObjectLockEnabled") != "Enabled":
            raise malformed()
        if bucket.meta.get("versioning") != "Enabled":
            raise S3Error(
                "InvalidBucketState",
                "Versioning must be 'Enabled' on the bucket to apply a Object Lock configuration",
                409,
            )
        mode = text(root, "Rule/DefaultRetention/Mode")
        if mode and mode not in ("GOVERNANCE", "COMPLIANCE"):
            raise malformed()
        if mode and bool(text(root, "Rule/DefaultRetention/Days")) == bool(text(root, "Rule/DefaultRetention/Years")):
            raise malformed()
    elif sub == "ownershipControls":
        if text(root, "Rule/ObjectOwnership") not in ("BucketOwnerPreferred", "ObjectWriter", "BucketOwnerEnforced"):
            raise malformed()
    elif sub == "accelerate":
        if text(root, "Status") not in ("Enabled", "Suspended"):
            raise malformed()
    elif sub == "requestPayment":
        if text(root, "Payer") not in ("Requester", "BucketOwner"):
            raise malformed()
    elif sub == "encryption":
        alg = text(root, "Rule/ApplyServerSideEncryptionByDefault/SSEAlgorithm")
        if alg not in ("AES256", "aws:kms", "aws:kms:dsse"):
            raise malformed()
    with get_store().lock:
        bucket.meta.setdefault("configs", {})[sub] = body.decode("utf-8")
        if sub == "object-lock":
            bucket.meta["object_lock"] = True
        bucket.save_meta()
