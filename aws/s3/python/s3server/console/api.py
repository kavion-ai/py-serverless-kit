"""The console's JSON operations (``POST /ui/api/<Operation>``), its upload and its in-page downloads."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Callable, Dict, List
from urllib.parse import quote

from ..access import (
    acl_canned_name,
    acl_public,
    bucket_access,
    bucket_owner_enforced,
    ownership,
    policy_is_public,
    public_block,
)
from ..config import (
    ACCOUNT,
    ARCHIVED,
    CANNED,
    CONFIGS,
    CREDENTIALS,
    DOMAINS,
    OWNER_ID,
    REGION,
    STD_HEADERS,
    STORAGE_CLASSES,
)
from ..errors import S3Error, denied, invalid, no_key
from ..lifecycle import sweep_lifecycle
from ..listing import list_keys, visible
from ..objectlock import check_unlocked, lock_config
from ..objects import default_encryption, new_version, object_fields, validate_tags
from ..payload import Received, copy_file
from ..request import Request, Response
from ..routes.config import set_config, set_policy
from ..sigv4 import Auth, presign
from ..store import abort_upload, create_bucket, delete_bucket, get_store, unlink
from ..util import iso, log, parse_time, strip_decl
from ..versions import delete_object, find_version, put_version, remove_version


def _p(params: Dict[str, Any], name: str, required: bool = True) -> str:
    value = params.get(name)
    if value is None or value == "":
        if required:
            raise invalid(f"{name} is required.", name, "")
        return ""
    return str(value)


def _version_json(key: str, version: Dict[str, Any], latest: bool = False) -> Dict[str, Any]:
    out = {
        "key": key,
        "versionId": version["id"],
        "modified": iso(version["time"]),
        "latest": latest,
        "deleteMarker": bool(version.get("dm")),
    }
    if not version.get("dm"):
        out.update(
            {
                "size": version["size"],
                "etag": version["etag"],
                "class": version.get("class", "STANDARD"),
                "type": version.get("type", ""),
            }
        )
    return out


def ui_list_buckets(_p_: Dict[str, Any], _r: Request) -> Dict[str, Any]:
    with get_store().lock:
        out = []
        for name in sorted(get_store().buckets):
            b = get_store().buckets[name]
            out.append(
                {
                    "name": name,
                    "created": iso(b.meta["created"]),
                    "region": b.meta.get("region") or REGION,
                    "versioning": b.meta.get("versioning") or "",
                    "objectLock": bool(b.meta.get("object_lock")),
                    "objects": sum(1 for r in b.objects.values() if not r["versions"][0].get("dm")),
                    "public": policy_is_public(b) or acl_public(b.meta.get("acl"), "READ"),
                    "access": bucket_access(b),
                    "publicBlock": public_block(b),
                }
            )
    return {"buckets": out}


def ui_create_bucket(p: Dict[str, Any], _r: Request) -> Dict[str, Any]:
    name = _p(p, "bucket")
    bucket = create_bucket(name, str(p.get("region") or REGION), None, bool(p.get("objectLock")))
    if p.get("versioning") and not bucket.meta.get("versioning"):
        with get_store().lock:
            bucket.meta["versioning"] = "Enabled"
            bucket.save_meta()
    return {"bucket": name}


def ui_delete_bucket(p: Dict[str, Any], _r: Request) -> Dict[str, Any]:
    name = _p(p, "bucket")
    with get_store().lock:
        bucket = get_store().get(name)
        if p.get("force"):
            for key in list(bucket.objects):
                for version in list(bucket.objects.get(key, {}).get("versions", [])):
                    if not version.get("dm"):
                        check_unlocked(version, bool(p.get("bypass")))
                    remove_version(bucket, key, version["id"])
        delete_bucket(name)
    return {"deleted": name}


def ui_bucket_info(p: Dict[str, Any], _r: Request) -> Dict[str, Any]:
    with get_store().lock:
        bucket = get_store().get(_p(p, "bucket"))
        size = versions = objects = 0
        for rec in bucket.objects.values():
            if not rec["versions"][0].get("dm"):
                objects += 1
            for v in rec["versions"]:
                versions += 1
                size += int(v.get("size") or 0)
        meta = bucket.meta
        return {
            "name": bucket.name,
            "created": iso(meta["created"]),
            "region": meta.get("region") or REGION,
            "versioning": meta.get("versioning") or "",
            "mfaDelete": meta.get("mfa_delete") or "",
            "objectLock": bool(meta.get("object_lock")),
            "tags": meta.get("tags") or {},
            "policy": meta.get("policy") or "",
            "acl": acl_canned_name(meta.get("acl")),
            "configs": {k: strip_decl(v) for k, v in (meta.get("configs") or {}).items()},
            "ids": {k: sorted(v) for k, v in (meta.get("ids") or {}).items()},
            "publicBlock": public_block(bucket),
            "policyPublic": policy_is_public(bucket),
            "stats": {"objects": objects, "versions": versions, "bytes": size, "uploads": len(bucket.uploads)},
            "websiteUrl": f"/-/website/{bucket.name}/",
            "websiteHosts": [f"{bucket.name}.s3-website.{d}" for d in DOMAINS],
            "access": bucket_access(bucket),
            "arn": f"arn:aws:s3:::{bucket.name}",
            "ownership": ownership(bucket),
            "account": ACCOUNT,
        }


def ui_list_objects(p: Dict[str, Any], _r: Request) -> Dict[str, Any]:
    with get_store().lock:
        bucket = get_store().get(_p(p, "bucket"))
        prefix = str(p.get("prefix") or "")
        search = str(p.get("search") or "").lower()
        delimiter = "" if search else str(p.get("delimiter", "/"))
        after = str(p.get("token") or "")
        limit = min(int(p.get("max") or 500), 1000)
        include = visible(bucket)
        if p.get("deleted"):
            include = lambda k: bool(bucket.objects.get(k))  # noqa: E731
        if search:
            base = include
            include = lambda k: base(k) and search in k[len(prefix) :].lower()  # noqa: E731
        keys, prefixes, truncated, last = list_keys(bucket, prefix, delimiter, after, limit, include)
        objects = [_version_json(k, bucket.objects[k]["versions"][0], True) for k in keys]
    return {"folders": prefixes, "objects": objects, "next": last if truncated else ""}


def ui_head_object(p: Dict[str, Any], _r: Request) -> Dict[str, Any]:
    with get_store().lock:
        bucket = get_store().get(_p(p, "bucket"))
        key = _p(p, "key")
        rec = bucket.objects.get(key)
        if not p.get("versionId") and rec and rec["versions"][0].get("dm"):
            # A deleted object (shown with "Show deleted"): its newest real version.
            live = [v for v in rec["versions"] if not v.get("dm")]
            if not live:
                raise no_key(key)
            version = live[0]
        else:
            version = find_version(bucket, key, p.get("versionId") or None)
            rec = bucket.objects[key]
        out = _version_json(key, version, version is rec["versions"][0])
        out.update(
            {
                "meta": version.get("meta") or {},
                "headers": version.get("headers") or {},
                "tags": version.get("tags") or {},
                "acl": acl_canned_name(version.get("acl")),
                "checksum": version.get("checksum"),
                "parts": len(version.get("parts") or []),
                "retention": (
                    {"mode": version["retention"]["mode"], "until": iso(version["retention"]["until"])}
                    if version.get("retention")
                    else None
                ),
                "legalHold": bool(version.get("hold")),
                "sse": version.get("sse") or {},
                "redirect": version.get("redirect") or "",
                "objectLock": lock_config(bucket)["enabled"],
                "versions": [_version_json(key, v, i == 0) for i, v in enumerate(rec["versions"])],
                "restore": iso(version["restore"]) if version.get("restore") else "",
            }
        )
        return out


def ui_list_versions(p: Dict[str, Any], _r: Request) -> Dict[str, Any]:
    """Every version and delete marker under ``prefix``; with ``delimiter`` only those of keys directly under it."""
    with get_store().lock:
        bucket = get_store().get(_p(p, "bucket"))
        prefix = str(p.get("prefix") or "")
        delimiter = str(p.get("delimiter") or "")
        out: List[Dict[str, Any]] = []
        folders: List[str] = []
        for key in bucket.keys():
            if not key.startswith(prefix):
                continue
            pos = key.find(delimiter, len(prefix)) if delimiter else -1
            if pos >= 0:
                folder = key[: pos + len(delimiter)]
                if not folders or folders[-1] != folder:
                    folders.append(folder)
                continue
            for i, v in enumerate(bucket.objects[key]["versions"]):
                out.append(_version_json(key, v, i == 0))
                if len(out) >= 2000:
                    return {"versions": out, "folders": folders, "truncated": True}
    return {"versions": out, "folders": folders, "truncated": False}


def ui_delete_objects(p: Dict[str, Any], _r: Request) -> Dict[str, Any]:
    deleted, errors = [], []
    with get_store().lock:
        bucket = get_store().get(_p(p, "bucket"))
        for item in p.get("objects") or []:
            key, vid = str(item.get("key") or ""), item.get("versionId") or None
            try:
                if key.endswith("/") and item.get("recursive"):
                    for sub in [k for k in bucket.keys() if k.startswith(key)]:
                        delete_object(bucket, sub, None, bypass=False)
                else:
                    delete_object(bucket, key, vid, bypass=bool(p.get("bypass")))
                deleted.append(key)
            except S3Error as exc:
                errors.append({"key": key, "code": exc.code, "message": exc.message})
    return {"deleted": deleted, "errors": errors}


def ui_copy(p: Dict[str, Any], req: Request) -> Dict[str, Any]:
    src_bucket, src_key = _p(p, "bucket"), _p(p, "key")
    dst_bucket, dst_key = str(p.get("toBucket") or src_bucket), _p(p, "toKey")
    moved = []
    with get_store().lock:
        sb = get_store().get(src_bucket)
        db = get_store().get(dst_bucket)
        if src_key.endswith("/"):
            pairs = [
                (k, dst_key.rstrip("/") + "/" + k[len(src_key) :])
                for k in sb.keys()
                if k.startswith(src_key) and not sb.objects[k]["versions"][0].get("dm")
            ]
        else:
            pairs = [(src_key, dst_key)]
    for skey, dkey in pairs:
        if sb is db and skey == dkey:
            continue
        with get_store().lock:
            src = dict(find_version(sb, skey, p.get("versionId") or None if len(pairs) == 1 else None))
            path = sb.blob_path(src["blob"])
        received = copy_file(path, 0, int(src["size"]) - 1, (src.get("checksum") or {}).get("alg", ""))
        fields = {
            k: src[k]
            for k in ("type", "meta", "headers", "class", "tags", "acl", "sse", "redirect", "owner")
            if k in src
        }
        with get_store().lock:
            blob = get_store().commit_blob(db, received.path)  # type: ignore[arg-type]
            put_version(db, dkey, new_version(received, fields, blob))
            if p.get("move"):
                delete_object(sb, skey, None, bypass=False)
        moved.append(dkey)
    return {"copied": moved}


def ui_create_folder(p: Dict[str, Any], _r: Request) -> Dict[str, Any]:
    key = _p(p, "key")
    if not key.endswith("/"):
        key += "/"
    with get_store().lock:
        bucket = get_store().get(_p(p, "bucket"))
        tmp = get_store().temp_file()
        tmp.write_bytes(b"")
        received = Received()
        received.path, received.md5 = tmp, hashlib.md5(b"").hexdigest()  # noqa: S324
        blob = get_store().commit_blob(bucket, tmp)
        put_version(
            bucket,
            key,
            new_version(
                received,
                {
                    "type": "application/x-directory",
                    "meta": {},
                    "headers": {},
                    "class": "STANDARD",
                    "tags": {},
                    "owner": OWNER_ID,
                    "sse": default_encryption(bucket),
                },
                blob,
            ),
        )
    return {"key": key}


def ui_put_object_tags(p: Dict[str, Any], _r: Request) -> Dict[str, Any]:
    tags = {str(k): str(v) for k, v in (p.get("tags") or {}).items()}
    validate_tags(tags)
    with get_store().lock:
        bucket = get_store().get(_p(p, "bucket"))
        version = find_version(bucket, _p(p, "key"), p.get("versionId") or None)
        version["tags"] = tags
        bucket.save_record(_p(p, "key"))
    return {"tags": tags}


def ui_update_meta(p: Dict[str, Any], _r: Request) -> Dict[str, Any]:
    """Replace the content type, standard headers, user metadata and storage class (a copy onto itself)."""
    with get_store().lock:
        bucket = get_store().get(_p(p, "bucket"))
        key = _p(p, "key")
        src = dict(find_version(bucket, key, None))
        path = bucket.blob_path(src["blob"])
    headers = {k.lower(): str(v) for k, v in (p.get("headers") or {}).items() if k.lower() in STD_HEADERS and v}
    meta = {str(k).lower(): str(v) for k, v in (p.get("meta") or {}).items() if k}
    if sum(len(k) + len(v) for k, v in meta.items()) > 2048:
        raise S3Error("MetadataTooLarge", "Your metadata headers exceed the maximum allowed metadata size.")
    sclass = str(p.get("class") or src.get("class") or "STANDARD")
    if sclass not in STORAGE_CLASSES:
        raise S3Error("InvalidStorageClass", "The storage class you specified is not valid")
    received = copy_file(path, 0, int(src["size"]) - 1, (src.get("checksum") or {}).get("alg", ""))
    fields = {k: src[k] for k in ("tags", "acl", "sse", "redirect", "owner", "retention", "hold") if k in src}
    fields.update(
        {
            "type": str(p.get("type") or src.get("type") or "binary/octet-stream"),
            "headers": headers,
            "meta": meta,
            "class": sclass,
        }
    )
    with get_store().lock:
        blob = get_store().commit_blob(bucket, received.path)  # type: ignore[arg-type]
        version = put_version(bucket, key, new_version(received, fields, blob))
    return {"versionId": version["id"]}


def ui_restore_version(p: Dict[str, Any], req: Request) -> Dict[str, Any]:
    """Make an older version the current one (copies it on top, like the AWS console)."""
    with get_store().lock:
        bucket = get_store().get(_p(p, "bucket"))
        key = _p(p, "key")
        src = dict(find_version(bucket, key, _p(p, "versionId")))
        path = bucket.blob_path(src["blob"])
    received = copy_file(path, 0, int(src["size"]) - 1, (src.get("checksum") or {}).get("alg", ""))
    fields = {
        k: src[k] for k in ("type", "meta", "headers", "class", "tags", "acl", "sse", "redirect", "owner") if k in src
    }
    with get_store().lock:
        blob = get_store().commit_blob(bucket, received.path)  # type: ignore[arg-type]
        version = put_version(bucket, key, new_version(received, fields, blob))
    return {"versionId": version["id"]}


def ui_put_bucket_setting(p: Dict[str, Any], _r: Request) -> Dict[str, Any]:
    """One bucket setting: versioning, tags, policy, acl, or a configuration document (XML, "" deletes it)."""
    name, setting = _p(p, "bucket"), _p(p, "setting")
    value = p.get("value")
    with get_store().lock:
        bucket = get_store().get(name)
    if setting == "versioning":
        if value not in ("Enabled", "Suspended"):
            raise invalid("versioning must be Enabled or Suspended")
        if bucket.meta.get("object_lock") and value == "Suspended":
            raise S3Error("InvalidBucketState", "Object Lock is on: versioning cannot be suspended.", 409)
        with get_store().lock:
            bucket.meta["versioning"] = value
            bucket.save_meta()
    elif setting == "tags":
        tags = {str(k): str(v) for k, v in (value or {}).items()}
        validate_tags(tags, 50)
        with get_store().lock:
            bucket.meta["tags"] = tags
            bucket.save_meta()
    elif setting == "policy":
        if value:
            set_policy(bucket, str(value))
        else:
            with get_store().lock:
                bucket.meta["policy"] = None
                bucket.save_meta()
    elif setting == "acl":
        if value not in CANNED:
            raise invalid("Unknown canned ACL")
        if bucket_owner_enforced(bucket) and value not in ("private", "bucket-owner-full-control"):
            raise S3Error(
                "AccessControlListNotSupported",
                "The bucket does not allow ACLs (ownership controls are BucketOwnerEnforced).",
            )
        if public_block(bucket)["BlockPublicAcls"] and value in ("public-read", "public-read-write"):
            raise denied("Block public access is on (BlockPublicAcls).")
        with get_store().lock:
            bucket.meta["acl"] = {"canned": value}
            bucket.save_meta()
    elif setting in CONFIGS:
        if value:
            set_config(bucket, setting, str(value).encode("utf-8"))
        else:
            if setting == "object-lock":
                raise invalid("Object Lock cannot be turned off.")
            with get_store().lock:
                bucket.meta.setdefault("configs", {}).pop(setting, None)
                bucket.save_meta()
    else:
        raise invalid(f"Unknown setting {setting}.")
    return ui_bucket_info({"bucket": name}, _r)


def ui_put_object_acl(p: Dict[str, Any], _r: Request) -> Dict[str, Any]:
    value = _p(p, "acl")
    if value not in CANNED:
        raise invalid("Unknown canned ACL")
    with get_store().lock:
        bucket = get_store().get(_p(p, "bucket"))
        if bucket_owner_enforced(bucket) and value not in ("private", "bucket-owner-full-control"):
            raise S3Error("AccessControlListNotSupported", "The bucket does not allow ACLs.")
        if public_block(bucket)["BlockPublicAcls"] and value in ("public-read", "public-read-write"):
            raise denied("Block public access is on (BlockPublicAcls).")
        version = find_version(bucket, _p(p, "key"), p.get("versionId") or None)
        version["acl"] = {"canned": value}
        bucket.save_record(_p(p, "key"))
    return {"acl": value}


def ui_object_lock(p: Dict[str, Any], _r: Request) -> Dict[str, Any]:
    with get_store().lock:
        bucket = get_store().get(_p(p, "bucket"))
        if not lock_config(bucket)["enabled"]:
            raise S3Error("InvalidRequest", "Bucket is missing Object Lock Configuration")
        key = _p(p, "key")
        version = find_version(bucket, key, p.get("versionId") or None)
        if "legalHold" in p:
            version["hold"] = bool(p["legalHold"])
        if "mode" in p:
            mode = str(p.get("mode") or "")
            old = version.get("retention") or {}
            until = parse_time(str(p.get("until") or ""))
            if old.get("until", 0) > time.time():
                shorter = not mode or (until or 0) < old["until"]
                if shorter and (old["mode"] == "COMPLIANCE" or not p.get("bypass")):
                    raise denied("The object is protected by its retention; it cannot be shortened.")
            if mode:
                if mode not in ("GOVERNANCE", "COMPLIANCE") or until is None or until <= time.time():
                    raise invalid("Pick GOVERNANCE or COMPLIANCE and a date in the future.")
                version["retention"] = {"mode": mode, "until": until}
            else:
                version.pop("retention", None)
        bucket.save_record(key)
    return ui_head_object(p, _r)


def ui_presign(p: Dict[str, Any], req: Request) -> Dict[str, Any]:
    try:
        expires = int(p.get("expires") or 3600)
    except (TypeError, ValueError):
        raise invalid("Expiry must be a number of seconds.") from None
    if expires < 1 or expires > 604800:
        raise invalid("Expiry must be between 1 second and 7 days.")
    access = req.who if req.who in CREDENTIALS else next(iter(CREDENTIALS), "")
    if not access:
        raise invalid("Share links need a credential (S3_SECRET_ACCESS_KEY); authentication is off.")
    method = str(p.get("method") or "GET").upper()
    if method not in ("GET", "PUT"):
        raise invalid("method must be GET or PUT")
    host = str(p.get("host") or req.host)
    scheme = "https" if str(p.get("scheme") or "") == "https" else "http"
    key = _p(p, "key")
    params = (
        [("response-content-disposition", _disposition(p, key))] if method == "GET" and p.get("disposition") else []
    )
    return {
        "url": presign(
            method, host, _p(p, "bucket"), key, expires, access, str(p.get("versionId") or ""), scheme, params
        ),
        "expires": expires,
    }


def _disposition(p: Dict[str, Any], key: str) -> str:
    """``inline``, or ``attachment`` with the file name (by default the key's last segment), like the AWS console."""
    disposition = str(p.get("disposition"))
    if disposition not in ("inline", "attachment"):
        raise invalid("disposition must be inline or attachment", "disposition", disposition)
    if disposition == "inline":
        return disposition
    name = str(p.get("filename") or "") or key.rstrip("/").rsplit("/", 1)[-1] or "download"
    return f"attachment; filename*=UTF-8''{quote(name, safe='')}"


def ui_empty_bucket(p: Dict[str, Any], _r: Request) -> Dict[str, Any]:
    """Remove every version and delete marker and abort every unfinished upload; locked versions stay."""
    deleted, errors = 0, []
    with get_store().lock:
        bucket = get_store().get(_p(p, "bucket"))
        for key in list(bucket.keys()):
            for version in list(bucket.objects[key]["versions"]):
                if not version.get("dm"):
                    try:
                        check_unlocked(version, False)
                    except S3Error as exc:
                        errors.append(
                            {"key": key, "versionId": version["id"], "code": exc.code, "message": exc.message}
                        )
                        continue
                remove_version(bucket, key, version["id"])
                deleted += 1
        for upload_id in list(bucket.uploads):
            abort_upload(bucket, upload_id)
    return {"deleted": deleted, "errors": errors}


def ui_list_uploads(p: Dict[str, Any], _r: Request) -> Dict[str, Any]:
    with get_store().lock:
        bucket = get_store().get(_p(p, "bucket"))
        return {
            "uploads": [
                {
                    "key": u["key"],
                    "uploadId": u["id"],
                    "initiated": iso(u["initiated"]),
                    "parts": len(u["parts"]),
                    "bytes": sum(int(x_["size"]) for x_ in u["parts"].values()),
                }
                for u in sorted(bucket.uploads.values(), key=lambda u: u["initiated"])
            ]
        }


def ui_abort_upload(p: Dict[str, Any], _r: Request) -> Dict[str, Any]:
    with get_store().lock:
        bucket = get_store().get(_p(p, "bucket"))
        if _p(p, "uploadId") not in bucket.uploads:
            raise S3Error("NoSuchUpload", "The specified upload does not exist.", 404)
        abort_upload(bucket, _p(p, "uploadId"))
    return {"aborted": True}


def ui_restore_archived(p: Dict[str, Any], _r: Request) -> Dict[str, Any]:
    days = int(p.get("days") or 1)
    with get_store().lock:
        bucket = get_store().get(_p(p, "bucket"))
        version = find_version(bucket, _p(p, "key"), p.get("versionId") or None)
        if version.get("class") not in ARCHIVED:
            raise S3Error("InvalidObjectState", "Only GLACIER and DEEP_ARCHIVE objects are restored.", 403)
        version["restore"] = time.time() + days * 86400
        bucket.save_record(_p(p, "key"))
    return {"restored": True}


def ui_run_lifecycle(_p_: Dict[str, Any], _r: Request) -> Dict[str, Any]:
    return {"changes": sweep_lifecycle()}


UI_OPS: Dict[str, Callable[[Dict[str, Any], Request], Dict[str, Any]]] = {
    "ListBuckets": ui_list_buckets,
    "CreateBucket": ui_create_bucket,
    "DeleteBucket": ui_delete_bucket,
    "EmptyBucket": ui_empty_bucket,
    "BucketInfo": ui_bucket_info,
    "ListObjects": ui_list_objects,
    "HeadObject": ui_head_object,
    "ListVersions": ui_list_versions,
    "DeleteObjects": ui_delete_objects,
    "Copy": ui_copy,
    "CreateFolder": ui_create_folder,
    "PutObjectTags": ui_put_object_tags,
    "UpdateMeta": ui_update_meta,
    "RestoreVersion": ui_restore_version,
    "PutBucketSetting": ui_put_bucket_setting,
    "PutObjectAcl": ui_put_object_acl,
    "ObjectLock": ui_object_lock,
    "Presign": ui_presign,
    "ListUploads": ui_list_uploads,
    "AbortUpload": ui_abort_upload,
    "RestoreArchived": ui_restore_archived,
    "RunLifecycle": ui_run_lifecycle,
}


def ui_upload(req: Request) -> Response:
    bucket_name, key = req.q.get("bucket", ""), req.q.get("key", "")
    if not key:
        raise invalid("key is required", "key", "")
    with get_store().lock:
        bucket = get_store().get(bucket_name)
    headers = {"content-type": req.headers.get("content-type") or "binary/octet-stream"}
    sclass = req.q.get("class")
    if sclass:
        headers["x-amz-storage-class"] = sclass
    fields = object_fields(headers, bucket)
    req.auth = Auth("console", "console")
    req.auth.payload = "UNSIGNED-PAYLOAD"
    received = req.payload("", "")
    try:
        with get_store().lock:
            blob = get_store().commit_blob(bucket, received.path)  # type: ignore[arg-type]
            received.path = None
            version = put_version(bucket, key, new_version(received, fields, blob))
    finally:
        if received.path:
            unlink(received.path)
    log("console upload", bucket_name, key, received.size, "bytes")
    return Response(
        200,
        json.dumps({"key": key, "etag": version["etag"], "versionId": version["id"]}).encode(),
        {"Cache-Control": "no-store"},
        "application/json",
    )


def ui_download(req: Request) -> Response:
    with get_store().lock:
        bucket = get_store().get(req.q.get("bucket", ""))
        key = req.q.get("key", "")
        version = dict(find_version(bucket, key, req.q.get("versionId") or None))
        path = bucket.blob_path(version["blob"])
    name = key.rstrip("/").rsplit("/", 1)[-1] or "download"
    inline = req.q.get("inline") == "1"
    ctype = version.get("type") or "binary/octet-stream"
    # Inline previews only for types a browser shows without running anything from the bucket.
    safe_inline = inline and (
        ctype.startswith(("image/", "video/", "audio/", "text/plain")) or ctype == "application/pdf"
    )
    if ctype.startswith("image/svg"):
        safe_inline = False
    disposition = ("inline" if safe_inline else "attachment") + f"; filename*=UTF-8''{quote(name)}"
    headers = {
        "Content-Disposition": disposition,
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; img-src 'self'; media-src 'self'; "
        "style-src 'unsafe-inline'; sandbox",
    }
    return Response(
        200, b"", headers, ctype if safe_inline else "application/octet-stream", path, 0, int(version["size"])
    )
