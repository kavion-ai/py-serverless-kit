"""Data catalog of the on-premises resource drivers, used by ``pskit studio`` forms.

Validation lives in :mod:`providers.onprem` (``_driver`` / ``_remote_driver``) and
the runtime in :mod:`runtime.drivers`. A test checks that every driver named
here exists in ``onprem.DRIVERS`` and the other way round, so the two cannot drift.

A field is a plain dict (see :func:`field`). ``env_ok`` means the option may also
be written as ``<key>_env: VARIABLE``, read from the host's environment at start.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def field(
    key: str,
    label: Optional[str] = None,
    type: str = "string",  # noqa: A002 - matches the JSON contract
    *,
    required: bool = False,
    default: Any = None,
    options: Optional[List[Any]] = None,
    help: str = "",  # noqa: A002
    placeholder: str = "",
    env_ok: bool = False,
    min: Optional[float] = None,  # noqa: A002
    max: Optional[float] = None,  # noqa: A002
) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "key": key,
        "label": label or key.replace("_", " ").capitalize(),
        "type": type,
        "required": required,
        "default": default,
        "help": help,
        "placeholder": placeholder,
    }
    if options is not None:
        out["options"] = list(options)
    if env_ok:
        out["env_ok"] = True
    if min is not None:
        out["min"] = min
    if max is not None:
        out["max"] = max
    return out


def _secret(key: str, label: str, required: bool = False, help: str = "") -> Dict[str, Any]:  # noqa: A002
    return field(key, label, "secret", required=required, env_ok=True, help=help)


_ENDPOINT = field(
    "endpoint", "Endpoint", help="Override the service URL (emulators, private endpoints).", placeholder="https://..."
)
_PREFIX = field("prefix", "Prefix", help="Only watch keys below this prefix (strongly advised on large buckets).")
_AWS_CREDS = [
    _secret("access_key", "Access key ID", help="Falls back to AWS_ACCESS_KEY_ID on the host."),
    _secret("secret_key", "Secret access key", help="Falls back to AWS_SECRET_ACCESS_KEY on the host."),
    _secret("session_token", "Session token"),
]
_HMAC_CREDS = [
    _secret("access_key", "Access key (HMAC)", required=True),
    _secret("secret_key", "Secret key (HMAC)", required=True),
]
_AZURE_AUTH = [
    _secret(
        "connection_string",
        "Connection string",
        help="Or account + account_key / sas_token. `UseDevelopmentStorage=true` targets Azurite.",
    ),
    field("account", "Storage account"),
    _secret("account_key", "Account key"),
    _secret("sas_token", "SAS token"),
    _ENDPOINT,
]
_GCP_AUTH = [
    field("project", "Project", help="Needed when names are not full projects/... paths."),
    _secret("access_token", "Access token"),
    field(
        "token_command",
        "Token command",
        "list",
        help="Command printing an access token, cached ~45 min.",
        placeholder="gcloud auth print-access-token",
    ),
    _ENDPOINT,
    field("emulator", "Emulator (no auth)", "bool", default=False),
]
_BUCKET = field("bucket", "Bucket", help="Defaults to the resource name.")
_CUSTOM = [
    field(
        "class",
        "Class",
        required=True,
        help="package.module:ClassName importable from your app.",
        placeholder="app.backends:MyQueue",
    ),
    field("kwargs", "Constructor options", "map", help="Every other option is passed to the constructor."),
]


def _driver(name: str, label: str, cloud: str, fields: List[Dict[str, Any]], notes: str = "") -> Dict[str, Any]:
    return {"name": name, "label": label, "cloud": cloud, "fields": fields, "notes": notes}


def _preset(name: str, label: str, cloud: str, extra: List[Dict[str, Any]], notes: str = "") -> Dict[str, Any]:
    creds = [
        _secret("access_key", "Access key (HMAC)", help="Set both keys, or neither (AWS_* variables, then anonymous)."),
        _secret("secret_key", "Secret key (HMAC)"),
    ]
    return _driver(name, label, cloud, [_BUCKET, *extra, *creds, _PREFIX, _ENDPOINT], notes)


QUEUE_DRIVERS: List[Dict[str, Any]] = [
    _driver("builtin", "Built-in (files)", "self-hosted", [], "One JSON file per message under the host's data_dir."),
    _driver(
        "directory",
        "Directory",
        "self-hosted",
        [field("path", "Path", required=True)],
        "This queue's own directory (e.g. a shared mount).",
    ),
    _driver(
        "redis",
        "Redis",
        "self-hosted",
        [
            field("url", "URL", required=True, env_ok=True, placeholder="redis://127.0.0.1:6379/0"),
            field("key", "List key", help="Defaults to the resource name."),
        ],
        "Lists <key>, <key>:processing and <key>:claims; crash recovery included.",
    ),
    _driver(
        "redis_stream",
        "Redis / Valkey stream",
        "self-hosted",
        [
            field("url", "URL", required=True, env_ok=True, placeholder="redis://127.0.0.1:6379/0"),
            field("key", "Stream key", help="Defaults to the resource name."),
            field("group", "Consumer group", default="pskit", help="Hosts sharing a group share the work."),
            field("maxlen", "Max length", "number", help="Trim the stream to about this many entries (0 = never)."),
        ],
        "A stream with a consumer group (Redis 6.2+ / Valkey): native leases, delivery counts, several hosts.",
    ),
    _driver(
        "sqs",
        "Amazon SQS",
        "aws",
        [
            field(
                "queue_url",
                "Queue URL",
                placeholder="https://sqs.eu-west-1.amazonaws.com/123456789012/jobs",
                help="Or account_id + region (+ name).",
            ),
            field("account_id", "Account ID"),
            field("region", "Region"),
            field("name", "Queue name"),
            *_AWS_CREDS,
            field("wait_seconds", "Long-poll seconds", "int", default=0, min=0, max=20),
            field("message_group_id", "Message group (FIFO)", default="pskit"),
            field("create_queue", "Create the queue if missing", "bool", help="For ElasticMQ and other emulators."),
            _ENDPOINT,
        ],
    ),
    _driver(
        "azure_queue",
        "Azure Storage Queue",
        "azure",
        [
            field("queue", "Queue", help="Defaults to the resource name."),
            *_AZURE_AUTH,
            field("message_encoding", "Message encoding", "enum", default="base64", options=["base64", "text"]),
        ],
        "Message attributes are not supported by Azure queues.",
    ),
    _driver(
        "pubsub",
        "Google Pub/Sub",
        "gcp",
        [
            field("subscription", "Subscription", required=True, placeholder="projects/my-project/subscriptions/jobs"),
            field("topic", "Topic (to publish)", placeholder="projects/my-project/topics/jobs"),
            *_GCP_AUTH,
            field("return_immediately", "Return immediately", "bool", default=False),
        ],
        "Queue depth is not available.",
    ),
    _driver(
        "mns",
        "Alibaba Cloud MNS",
        "alibaba",
        [
            field("account_id", "Account ID", help="Or endpoint."),
            field("region", "Region", placeholder="cn-hangzhou"),
            field("queue", "Queue", help="Defaults to the resource name."),
            *_HMAC_CREDS,
            field("wait_seconds", "Long-poll seconds", "int", default=0, min=0, max=30),
            field("message_encoding", "Message encoding", "enum", default="base64", options=["base64", "text"]),
            _ENDPOINT,
        ],
    ),
    _driver(
        "cloudflare_queue",
        "Cloudflare Queues",
        "cloudflare",
        [
            field("account_id", "Account ID", required=True),
            field("queue_id", "Queue ID", required=True),
            _secret("api_token", "API token", required=True),
            _ENDPOINT,
        ],
        "HTTP pull consumer; queue depth is not available.",
    ),
    _driver(
        "pskit_host",
        "Another on-prem host",
        "self-hosted",
        [
            field("endpoint", "Host URL", required=True, placeholder="http://10.0.0.6:8080"),
            field("queue", "Queue", help="The queue's name on that host. Defaults to the resource name."),
            _secret("token", "Admin token", help="That host's provider.options.admin_token, if it sets one."),
        ],
        "A built-in queue of another pskit on-premises host, leased through its admin API (at-least-once).",
    ),
    _driver(
        "custom",
        "Custom class",
        "any",
        list(_CUSTOM),
        "Your own class (RabbitMQ, Kafka, IBM MQ, OCI Queue, TDMQ, DMS...). See examples/19-custom-drivers.",
    ),
]

STORAGE_DRIVERS: List[Dict[str, Any]] = [
    _driver("builtin", "Built-in (folder)", "self-hosted", [], "A folder under the host's data_dir."),
    _driver("directory", "Directory", "self-hosted", [field("path", "Path", required=True)]),
    _driver(
        "s3",
        "S3 / S3-compatible",
        "any",
        [
            _BUCKET,
            field("endpoint", "Endpoint",
                  help="Empty = AWS. Set it for MinIO, Ceph, SeaweedFS, Garage, RustFS, LocalStack and others."),
            field("region", "Region", default="us-east-1"),
            *_AWS_CREDS,
            _PREFIX,
            field("path_style", "Path-style addressing", "bool"),
            field("signing_region", "Signing region"),
        ],
    ),
    _preset("aws", "Amazon S3", "aws", [field("region", "Region", default="us-east-1")]),
    _preset("oss", "Alibaba OSS", "alibaba", [field("region", "Region", required=True, placeholder="cn-hangzhou")]),
    _preset(
        "cos",
        "Tencent COS",
        "tencent",
        [field("region", "Region", required=True, placeholder="ap-guangzhou")],
        "Bucket names end in -<APPID>.",
    ),
    _preset("obs", "Huawei OBS", "huawei", [field("region", "Region", required=True, placeholder="cn-north-4")]),
    _preset(
        "oci",
        "Oracle Object Storage",
        "oracle",
        [
            field("region", "Region", required=True, placeholder="eu-frankfurt-1"),
            field("namespace", "Namespace", required=True),
        ],
        "Use Customer Secret Keys.",
    ),
    _preset(
        "ibm_cos",
        "IBM Cloud Object Storage",
        "ibm",
        [field("region", "Region", required=True, placeholder="us-south")],
        "HMAC credentials, not an API key.",
    ),
    _preset(
        "spaces", "DigitalOcean Spaces", "digitalocean", [field("region", "Region", required=True, placeholder="nyc3")]
    ),
    _preset("r2", "Cloudflare R2", "cloudflare", [field("account_id", "Account ID", required=True)]),
    _preset(
        "minio", "MinIO", "self-hosted", [field("endpoint", "Endpoint", required=True, placeholder="http://minio:9000")]
    ),
    _preset("wasabi", "Wasabi", "s3-clouds", [field("region", "Region", default="us-east-1")]),
    _preset(
        "b2", "Backblaze B2", "s3-clouds", [field("region", "Region", required=True, placeholder="us-west-004")],
        "Application key ID as the access key.",
    ),
    _preset("linode", "Akamai (Linode) Object Storage", "s3-clouds",
            [field("region", "Region", required=True, placeholder="us-east-1")]),
    _preset("scaleway", "Scaleway Object Storage", "s3-clouds",
            [field("region", "Region", required=True, placeholder="fr-par")]),
    _driver(
        "azure_blob",
        "Azure Blob Storage",
        "azure",
        [field("container", "Container", help="Defaults to the resource name."), *_AZURE_AUTH, _PREFIX],
    ),
    _driver("gcs", "Google Cloud Storage", "gcp", [_BUCKET, *_GCP_AUTH, _PREFIX]),
    _driver("custom", "Custom class", "any", list(_CUSTOM), "Your own StorageDriver class."),
]

TOPIC_DRIVERS: List[Dict[str, Any]] = [
    _driver("builtin", "Built-in", "self-hosted", []),
    _driver("directory", "Directory", "self-hosted", [field("path", "Path", required=True)]),
]

DRIVER_CATALOG: Dict[str, List[Dict[str, Any]]] = {
    "queue": QUEUE_DRIVERS,
    "storage": STORAGE_DRIVERS,
    "topic": TOPIC_DRIVERS,
}
