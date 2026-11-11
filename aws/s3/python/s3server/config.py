"""Settings from the environment (``S3_*``), fixed limits and S3 constants, and the credentials."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Dict, Tuple

VERSION = "1.0.0"
ENV = os.environ
PORT = int(ENV.get("S3_PORT") or 9000)
BIND = ENV.get("S3_BIND") or "0.0.0.0"  # noqa: S104 - a server; set S3_BIND=127.0.0.1 to keep it local
DATA_DIR = Path(ENV.get("S3_DATA_DIR") or Path.cwd() / "data")
REGION = ENV.get("S3_REGION") or "us-east-1"
ACCOUNT = ENV.get("S3_ACCOUNT_ID") or "000000000000"
AUTH = (ENV.get("S3_AUTH") or "sigv4").lower()
DOMAINS = [d.strip().lower() for d in (ENV.get("S3_DOMAIN") or "localhost").split(",") if d.strip()]
UI_ON = (ENV.get("S3_UI") or "on").lower() not in ("off", "0", "false", "no")
UI_PASSWORD = ENV.get("S3_UI_PASSWORD") or ""
UI_DIR = ENV.get("S3_UI_DIR") or ""
MAX_OBJECT = int(ENV.get("S3_MAX_OBJECT_SIZE") or 5 * 1024**3)
MIN_PART = int(ENV.get("S3_MIN_PART_SIZE") or 5 * 1024**2)
LIFECYCLE_INTERVAL = float(ENV.get("S3_LIFECYCLE_INTERVAL") or 3600)
DAY = float(ENV.get("S3_LIFECYCLE_DAY_SECONDS") or 86400)
MAX_XML = 4 * 1024 * 1024
MAX_POST = 256 * 1024 * 1024
MAX_PARTS = 10000
SKEW = 15 * 60
SESSION_TTL = 12 * 3600
OWNER_ID = hashlib.sha256(("pskit-s3:" + ACCOUNT).encode()).hexdigest()
OWNER_NAME = "pskit"
NS = "http://s3.amazonaws.com/doc/2006-03-01/"
ALL_USERS = "http://acs.amazonaws.com/groups/global/AllUsers"
AUTH_USERS = "http://acs.amazonaws.com/groups/global/AuthenticatedUsers"
LOG_DELIVERY = "http://acs.amazonaws.com/groups/s3/LogDelivery"
STORAGE_CLASSES = (
    "STANDARD",
    "REDUCED_REDUNDANCY",
    "STANDARD_IA",
    "ONEZONE_IA",
    "INTELLIGENT_TIERING",
    "GLACIER",
    "DEEP_ARCHIVE",
    "GLACIER_IR",
    "OUTPOSTS",
    "SNOW",
    "EXPRESS_ONEZONE",
)
ARCHIVED = ("GLACIER", "DEEP_ARCHIVE")
CANNED = (
    "private",
    "public-read",
    "public-read-write",
    "authenticated-read",
    "aws-exec-read",
    "bucket-owner-read",
    "bucket-owner-full-control",
    "log-delivery-write",
)
STD_HEADERS = ("cache-control", "content-disposition", "content-encoding", "content-language", "expires")
ALGORITHMS = ("CRC32", "CRC32C", "CRC64NVME", "SHA1", "SHA256")
# Bucket configurations kept as the XML the client sent: subresource -> (error when missing, delete allowed).
CONFIGS: Dict[str, Tuple[str, str]] = {
    "cors": ("NoSuchCORSConfiguration", "The CORS configuration does not exist"),
    "lifecycle": ("NoSuchLifecycleConfiguration", "The lifecycle configuration does not exist"),
    "website": ("NoSuchWebsiteConfiguration", "The specified bucket does not have a website configuration"),
    "encryption": (
        "ServerSideEncryptionConfigurationNotFoundError",
        "The server side encryption configuration was not found",
    ),
    "replication": ("ReplicationConfigurationNotFoundError", "The replication configuration was not found"),
    "ownershipControls": ("OwnershipControlsNotFoundError", "The bucket ownership controls were not found"),
    "publicAccessBlock": (
        "NoSuchPublicAccessBlockConfiguration",
        "The public access block configuration was not found",
    ),
    "object-lock": ("ObjectLockConfigurationNotFoundError", "Object Lock configuration does not exist for this bucket"),
    "logging": ("", ""),
    "notification": ("", ""),
    "accelerate": ("", ""),
    "requestPayment": ("", ""),
}
# Defaults returned by GET when a stored-only configuration was never set.
EMPTY_CONFIGS = {
    "logging": f'<BucketLoggingStatus xmlns="{NS}"/>',
    "notification": f'<NotificationConfiguration xmlns="{NS}"/>',
    "accelerate": f'<AccelerateConfiguration xmlns="{NS}"/>',
    "requestPayment": (
        f'<RequestPaymentConfiguration xmlns="{NS}"><Payer>BucketOwner</Payer></RequestPaymentConfiguration>'
    ),
}
ID_CONFIGS = {
    "metrics": "MetricsConfiguration",
    "analytics": "AnalyticsConfiguration",
    "inventory": "InventoryConfiguration",
    "intelligent-tiering": "IntelligentTieringConfiguration",
}
BUCKET_SUBRESOURCES = (
    "acl",
    "cors",
    "delete",
    "encryption",
    "lifecycle",
    "location",
    "logging",
    "notification",
    "policy",
    "policyStatus",
    "replication",
    "requestPayment",
    "tagging",
    "uploads",
    "versioning",
    "versions",
    "website",
    "accelerate",
    "ownershipControls",
    "publicAccessBlock",
    "object-lock",
    "metrics",
    "analytics",
    "inventory",
    "intelligent-tiering",
)
OBJECT_SUBRESOURCES = (
    "acl",
    "tagging",
    "retention",
    "legal-hold",
    "attributes",
    "restore",
    "uploads",
    "uploadId",
    "select",
    "torrent",
)
V2_SUBRESOURCES = {
    "acl",
    "cors",
    "delete",
    "lifecycle",
    "location",
    "logging",
    "notification",
    "partNumber",
    "policy",
    "requestPayment",
    "restore",
    "tagging",
    "torrent",
    "uploadId",
    "uploads",
    "versionId",
    "versioning",
    "versions",
    "website",
    "response-cache-control",
    "response-content-disposition",
    "response-content-encoding",
    "response-content-language",
    "response-content-type",
    "response-expires",
    "retention",
    "legal-hold",
    "object-lock",
    "encryption",
    "accelerate",
    "publicAccessBlock",
    "ownershipControls",
    "replication",
    "attributes",
    "policyStatus",
}


def _credentials() -> Dict[str, str]:
    out: Dict[str, str] = {}
    if ENV.get("S3_SECRET_ACCESS_KEY"):
        out[ENV.get("S3_ACCESS_KEY_ID") or "pskit"] = ENV["S3_SECRET_ACCESS_KEY"]
    for pair in (ENV.get("S3_CREDENTIALS") or "").split(","):
        key, sep, secret = pair.strip().partition(":")
        if sep and key and secret:
            out[key] = secret
    return out


CREDENTIALS = _credentials()
