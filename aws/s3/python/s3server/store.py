"""The on-disk data (buckets, object records, blobs, uploads; atomic writes) and the open store accessor.

Other modules reach the store with ``get_store()``; ``main()`` opens it with ``set_store()``.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import NS
from .errors import S3Error, no_bucket
from .util import esc, log, timestamp

_BUCKET = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
_IP = re.compile(r"^\d+\.\d+\.\d+\.\d+$")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex[:8] + ".tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    os.replace(str(tmp), str(path))


def unlink(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass  # open on Windows, or gone: the startup sweep removes blobs nothing refers to


def key_hash(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


class Bucket:
    """A bucket: its settings (``meta``), object records by key, unfinished uploads, parsed-settings cache."""

    def __init__(self, path: Path, meta: Dict[str, Any]) -> None:
        self.path = path
        self.meta = meta
        self.objects: Dict[str, Dict[str, Any]] = {}
        self.uploads: Dict[str, Dict[str, Any]] = {}
        self._sorted: Optional[List[str]] = None
        self.parsed: Dict[str, Any] = {}

    @property
    def name(self) -> str:
        return str(self.meta["name"])

    def keys(self) -> List[str]:
        if self._sorted is None:
            self._sorted = sorted(self.objects)
        return self._sorted

    def record_path(self, key: str) -> Path:
        h = key_hash(key)
        return self.path / "objects" / h[:2] / (h + ".json")

    def blob_path(self, blob: str) -> Path:
        return self.path / "blobs" / blob[:2] / blob

    def upload_dir(self, upload_id: str) -> Path:
        return self.path / "uploads" / upload_id

    def save_meta(self) -> None:
        self.parsed.clear()
        write_json(self.path / "bucket.json", self.meta)

    def save_record(self, key: str) -> None:
        rec = self.objects.get(key)
        path = self.record_path(key)
        if rec is None or not rec["versions"]:
            self.objects.pop(key, None)
            unlink(path)
            self._sorted = None
            return
        if self._sorted is not None and key not in self.objects:
            self._sorted = None
        write_json(path, rec)

    def set_record(self, key: str, rec: Dict[str, Any]) -> None:
        if key not in self.objects:
            self._sorted = None
        self.objects[key] = rec
        self.save_record(key)


class Store:
    """Every bucket, loaded from ``<root>/buckets`` at start (blobs nothing refers to are removed)."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.lock = threading.RLock()
        self.buckets: Dict[str, Bucket] = {}
        self.tmp = root / "tmp"
        (root / "buckets").mkdir(parents=True, exist_ok=True)
        if self.tmp.is_dir():
            shutil.rmtree(self.tmp, ignore_errors=True)
        self.tmp.mkdir(parents=True, exist_ok=True)
        for meta_file in sorted((root / "buckets").glob("*/bucket.json")):
            try:
                meta = json.loads(meta_file.read_text("utf-8"))
            except (OSError, ValueError):
                log("skipping unreadable", meta_file)
                continue
            bucket = Bucket(meta_file.parent, meta)
            self._load(bucket)
            self.buckets[bucket.name] = bucket

    def _load(self, bucket: Bucket) -> None:
        used = set()
        for rec_file in (bucket.path / "objects").glob("*/*.json"):
            try:
                rec = json.loads(rec_file.read_text("utf-8"))
            except (OSError, ValueError):
                log("skipping unreadable", rec_file)
                continue
            if rec.get("versions"):
                bucket.objects[rec["key"]] = rec
                used.update(v["blob"] for v in rec["versions"] if v.get("blob"))
        for up_file in (bucket.path / "uploads").glob("*/upload.json"):
            try:
                up = json.loads(up_file.read_text("utf-8"))
            except (OSError, ValueError):
                continue
            up["parts"] = {}
            for part_file in up_file.parent.glob("*.json"):
                if part_file.name == "upload.json":
                    continue
                try:
                    part = json.loads(part_file.read_text("utf-8"))
                except (OSError, ValueError):
                    continue
                if (up_file.parent / (f"{part['n']:05d}.part")).is_file():
                    up["parts"][part["n"]] = part
            bucket.uploads[up["id"]] = up
        for blob in (bucket.path / "blobs").glob("*/*"):
            if blob.name not in used:
                unlink(blob)

    def get(self, name: str) -> Bucket:
        bucket = self.buckets.get(name)
        if bucket is None:
            raise no_bucket(name)
        return bucket

    def temp_file(self) -> Path:
        return self.tmp / uuid.uuid4().hex

    def commit_blob(self, bucket: Bucket, tmp: Path) -> str:
        blob = uuid.uuid4().hex
        dest = bucket.blob_path(blob)
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.replace(str(tmp), str(dest))
        return blob


_STORE: Optional[Store] = None


def get_store() -> Store:
    """The store ``main()`` opened (every module reaches it through here, never by copying it)."""
    if _STORE is None:
        raise RuntimeError("the store is not open")
    return _STORE


def set_store(store: Store) -> None:
    global _STORE
    _STORE = store


def create_bucket(
    name: str, region: str, acl: Optional[Dict[str, Any]], object_lock: bool, ownership: str = ""
) -> Bucket:
    if (
        not _BUCKET.match(name)
        or ".." in name
        or _IP.match(name)
        or name.startswith("xn--")
        or name.endswith("-s3alias")
        or name.endswith("--ol-s3")
    ):
        raise S3Error("InvalidBucketName", "The specified bucket is not valid.", 400, BucketName=name)
    with get_store().lock:
        if name in get_store().buckets:
            raise S3Error(
                "BucketAlreadyOwnedByYou",
                "Your previous request to create the named bucket succeeded and you already own it.",
                409,
                BucketName=name,
            )
        path = get_store().root / "buckets" / name
        meta: Dict[str, Any] = {
            "name": name,
            "created": timestamp(),
            "region": region,
            "versioning": "",
            "mfa_delete": "",
            "object_lock": object_lock,
            "acl": acl or {"canned": "private"},
            "tags": {},
            "policy": None,
            "configs": {},
            "ids": {},
        }
        if object_lock:
            meta["versioning"] = "Enabled"
            meta["configs"]["object-lock"] = (
                f'<ObjectLockConfiguration xmlns="{NS}"><ObjectLockEnabled>Enabled'
                "</ObjectLockEnabled></ObjectLockConfiguration>"
            )
        if ownership:
            meta["configs"]["ownershipControls"] = (
                f'<OwnershipControls xmlns="{NS}"><Rule><ObjectOwnership>'
                f"{esc(ownership)}</ObjectOwnership></Rule></OwnershipControls>"
            )
        bucket = Bucket(path, meta)
        bucket.save_meta()
        get_store().buckets[name] = bucket
        log("bucket created", name)
        return bucket


def delete_bucket(name: str) -> None:
    with get_store().lock:
        bucket = get_store().get(name)
        if bucket.objects:
            raise S3Error("BucketNotEmpty", "The bucket you tried to delete is not empty", 409, BucketName=name)
        for upload_id in list(bucket.uploads):
            abort_upload(bucket, upload_id)
        del get_store().buckets[name]
        shutil.rmtree(bucket.path, ignore_errors=True)
        log("bucket deleted", name)


def abort_upload(bucket: Bucket, upload_id: str) -> None:
    bucket.uploads.pop(upload_id, None)
    shutil.rmtree(bucket.upload_dir(upload_id), ignore_errors=True)
