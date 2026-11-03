"""External backends the on-premises host can use for queues and storage.

A ``resources:`` entry selects one with ``options.driver``. ``builtin`` and
``directory`` are handled by the host's file broker itself, so the factories
below return ``None`` for them. The others implement these interfaces
(standard library only, Python 3.9+, vendored into every bundle):

* queues: ``redis``, ``redis_stream`` (a stream with a consumer group), ``sqs`` (AWS), ``azure_queue``, ``pubsub`` (GCP), ``mns``
  (Alibaba Cloud), ``cloudflare_queue``, ``pskit_host`` (a built-in queue of another
  on-premises host) and ``custom`` (a class of your own);
* storage: ``s3`` (any S3-compatible store; presets ``aws``, ``oss``, ``cos``,
  ``obs``, ``oci``, ``ibm_cos``, ``spaces``, ``r2``, ``minio``, ``wasabi``, ``b2``,
  ``linode``, ``scaleway``; Ceph, SeaweedFS, Garage, RustFS... through ``s3`` with an ``endpoint``), ``azure_blob``,
  ``gcs`` and ``custom``.

Any option ``<name>_env: VAR`` is read from the host's environment when the
driver is built, so secrets never have to be written into ``pskit_host.json``.

``QueueDriver``
    ``submit(body, attributes) -> id``
    ``claim(batch, visibility, now) -> [message]`` where a message is a dict with
    ``id``, ``body``, ``attributes``, ``receives`` and ``enqueued_at`` (plus
    private keys starting with ``_`` the driver needs to settle it)
    ``settle(claimed, failed_ids, max_receive, dead_letter, now)`` deletes
    delivered messages, makes failed ones visible again, and moves a message to
    ``dead_letter`` (another driver) once it has failed ``max_receive`` times
    ``depth() -> int`` (-1 when the service cannot tell) and
    ``recover(now, visibility)`` (requeue claims older than ``visibility``
    seconds, e.g. after a crash; a no-op for services with native leases)

``StorageDriver``
    ``scan() -> {key: (etag, size)}``, ``put(key, data)``, ``get(key) -> bytes``,
    ``delete(key) -> bool`` (False when the key did not exist)
"""

from __future__ import annotations

import importlib
import os
from typing import Any, Dict, List, Optional, Protocol, Set, Tuple


class QueueDriver(Protocol):
    def submit(self, body: str, attributes: Dict[str, Any]) -> str: ...

    def claim(self, batch: int, visibility: float, now: float) -> List[Dict[str, Any]]: ...

    def settle(
        self,
        claimed: List[Dict[str, Any]],
        failed_ids: Set[str],
        max_receive: int,
        dead_letter: Optional[QueueDriver],
        now: float,
    ) -> None: ...

    def depth(self) -> int: ...

    def recover(self, now: float, visibility: float) -> None: ...


class StorageDriver(Protocol):
    def scan(self) -> Dict[str, Tuple[str, int]]: ...

    def put(self, key: str, data: bytes) -> None: ...

    def get(self, key: str) -> bytes: ...

    def delete(self, key: str) -> bool: ...


_FILE_BACKED = ("", "builtin", "directory")

QUEUE_DRIVERS = ("redis", "redis_stream", "sqs", "azure_queue", "pubsub", "mns", "cloudflare_queue", "pskit_host", "custom")
# S3-compatible object stores. A preset fills in the endpoint, addressing style and
# signing region; the user still supplies the bucket and the HMAC keys.
S3_PRESETS = ("aws", "oss", "cos", "obs", "oci", "ibm_cos", "spaces", "r2", "minio", "wasabi", "b2", "linode", "scaleway")
STORAGE_DRIVERS = ("s3", "azure_blob", "gcs", "custom") + S3_PRESETS
QUEUE_METHODS = ("submit", "claim", "settle")
STORAGE_METHODS = ("scan", "put", "get", "delete")
_PRIVATE = ("use", "resource", "class")


def resolve_env(binding: Optional[Dict[str, Any]], label: str = "") -> Dict[str, Any]:
    """Copy of ``binding`` where every ``<name>_env: VAR`` became ``<name>: os.environ[VAR]``.

    An explicit ``<name>`` wins. A variable that is not set is an error naming it.
    """
    out: Dict[str, Any] = {}
    pending: Dict[str, str] = {}
    for key, value in (binding or {}).items():
        if key.endswith("_env") and len(key) > 4 and isinstance(value, str) and value:
            pending[key[:-4]] = value
        else:
            out[key] = value
    for name, var in pending.items():
        if out.get(name) not in (None, ""):
            continue
        if var not in os.environ:
            where = f" for {label}" if label else ""
            raise ValueError(f"environment variable {var} (option {name}_env{where}) is not set on the host")
        out[name] = os.environ[var]
    return out


def flag(value: Any, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, str):
        return value.strip().lower() not in ("0", "false", "no", "off")
    return bool(value)


def s3_preset(provider: str, b: Dict[str, Any]) -> Tuple[str, bool, str]:
    """``(endpoint, path_style, signing_region)`` of an S3-compatible provider."""
    region = str(b.get("region") or "")

    def need(*names: str) -> None:
        missing = [n for n in names if not b.get(n)]
        if missing:
            raise ValueError(f"the {provider} storage preset needs {', '.join(missing)}")

    if provider in ("", "aws"):
        region = region or "us-east-1"
        return f"https://s3.{region}.amazonaws.com", False, region
    if (
        provider == "oss"
    ):  # https://www.alibabacloud.com/help/en/oss/developer-reference/use-amazon-s3-sdks-to-access-oss
        need("region")
        return f"https://oss-{region}.aliyuncs.com", False, region
    if provider == "cos":  # https://www.tencentcloud.com/document/product/436/32537
        need("region")
        return f"https://cos.{region}.myqcloud.com", False, region
    if provider == "obs":  # https://support.huaweicloud.com/intl/en-us/api-obs/obs_04_0000.html
        need("region")
        return f"https://obs.{region}.myhuaweicloud.com", False, region
    if provider == "oci":  # https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/s3compatibleapi.htm
        need("region", "namespace")
        return f"https://{b['namespace']}.compat.objectstorage.{region}.oraclecloud.com", True, region
    if provider == "ibm_cos":  # https://cloud.ibm.com/docs/cloud-object-storage?topic=cloud-object-storage-endpoints
        need("region")
        return f"https://s3.{region}.cloud-object-storage.appdomain.cloud", True, region
    if provider == "spaces":  # https://docs.digitalocean.com/products/spaces/reference/s3-compatibility/
        need("region")
        return f"https://{region}.digitaloceanspaces.com", False, region
    if provider == "r2":  # https://developers.cloudflare.com/r2/api/s3/api/
        need("account_id")
        return f"https://{b['account_id']}.r2.cloudflarestorage.com", True, "auto"
    if provider == "minio":
        need("endpoint")
        return str(b["endpoint"]), True, region or "us-east-1"
    if provider == "wasabi":  # https://docs.wasabi.com/docs/what-are-the-service-urls-for-wasabi-s-different-storage-regions
        region = region or "us-east-1"
        return f"https://s3.{region}.wasabisys.com", False, region
    if provider == "b2":  # https://www.backblaze.com/docs/cloud-storage-s3-compatible-api
        need("region")
        return f"https://s3.{region}.backblazeb2.com", False, region
    if provider == "linode":  # https://techdocs.akamai.com/cloud-computing/docs/object-storage
        need("region")
        return f"https://{region}.linodeobjects.com", False, region
    if provider == "scaleway":  # https://www.scaleway.com/en/docs/object-storage/api-cli/using-api-call-list/
        need("region")
        return f"https://s3.{region}.scw.cloud", False, region
    raise ValueError(f"unknown S3-compatible provider {provider!r}; expected one of {', '.join(S3_PRESETS)}")


# --------------------------------------------------------------------- custom


def load_class(path: str, where: str = "") -> Any:
    module_name, sep, attr = str(path).partition(":")
    if not sep or not module_name or not attr:
        raise ValueError(f"custom driver{where}: `class` must look like 'package.module:ClassName', got {path!r}")
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:  # noqa: BLE001 - any import failure is reported with the class name
        raise ValueError(f"custom driver{where}: cannot import {module_name!r} for {path}: {exc}") from exc
    cls = getattr(module, attr, None)
    if cls is None:
        raise ValueError(f"custom driver{where}: module {module_name!r} has no attribute {attr!r}")
    return cls


def _custom(binding: Dict[str, Any], methods: Tuple[str, ...], where: str) -> Any:
    path = str(binding.get("class") or "")
    cls = load_class(path, where)
    kwargs = {k: v for k, v in binding.items() if k not in _PRIVATE}
    try:
        instance = cls(**kwargs)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"custom driver{where}: {path}(**options) failed: {type(exc).__name__}: {exc}") from exc
    missing = [m for m in methods if not callable(getattr(instance, m, None))]
    if missing:
        raise ValueError(f"custom driver{where}: {path} does not implement {', '.join(missing)}")
    return instance


class CustomQueue:
    """Wraps a user queue class; ``depth`` and ``recover`` are optional there."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner

    def submit(self, body: str, attributes: Dict[str, Any]) -> str:
        return str(self.inner.submit(body, attributes))

    def claim(self, batch: int, visibility: float, now: float) -> List[Dict[str, Any]]:
        return list(self.inner.claim(batch, visibility, now) or [])

    def settle(
        self,
        claimed: List[Dict[str, Any]],
        failed_ids: Set[str],
        max_receive: int,
        dead_letter: Optional[QueueDriver],
        now: float,
    ) -> None:
        self.inner.settle(claimed, failed_ids, max_receive, dead_letter, now)

    def depth(self) -> int:
        fn = getattr(self.inner, "depth", None)
        return int(fn()) if callable(fn) else -1

    def recover(self, now: float, visibility: float) -> None:
        fn = getattr(self.inner, "recover", None)
        if callable(fn):
            fn(now, visibility)


# --------------------------------------------------------------------- self-provisioning

_MISSING = ("404", "NotFound", "NoSuchBucket", "QueueNotFound", "ContainerNotFound", "does not exist")


class Ensured:
    """A driver whose queue / bucket is created on first use (emulators such as Azurite, LocalStack,
    fake-gcs-server, MinIO-compatible stores), and again when the service reports it missing.

    ``create`` must be idempotent: an "already exists" answer counts as success.
    """

    def __init__(self, inner: Any, create: Any, what: str) -> None:
        self.inner = inner
        self._create = create
        self._what = what
        self._ready = False

    def _ensure(self) -> None:
        if not self._ready:
            status = self._create()
            if isinstance(status, int) and status >= 400 and status != 409:
                raise RuntimeError(f"could not create {self._what} (HTTP {status})")
            self._ready = True

    def __getattr__(self, name: str) -> Any:
        target = getattr(self.inner, name)
        if not callable(target) or name.startswith("_") or name == "peek":
            return target

        def call(*args: Any, **kwargs: Any) -> Any:
            self._ensure()
            try:
                return target(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 - only "missing" errors are retried
                if not any(m in str(exc) for m in _MISSING):
                    raise
                self._ready = False
                self._ensure()
                return target(*args, **kwargs)

        return call


def _ensured(driver: Any, use: str, b: Dict[str, Any]) -> Any:
    """Wrap ``driver`` when the binding asks to create its queue (``create_queue``) or bucket (``create_bucket``)."""
    wanted = flag(b.get("create_queue"), False) if use in ("azure_queue",) else flag(b.get("create_bucket"), False)
    if not wanted:
        return driver
    if use == "azure_queue":
        return Ensured(driver, lambda: driver.auth.call("PUT", driver._path())[0], f"queue {driver.queue}")
    if use == "azure_blob":
        container = driver.container
        return Ensured(
            driver,
            lambda: driver.auth.call("PUT", "/" + container, {"restype": "container"})[0],
            f"container {container}",
        )
    if use == "gcs":
        import json as _json

        from ._http import request as _request

        def create_gcs() -> int:
            url = f"{driver.endpoint}/storage/v1/b?project={b.get('project') or 'pskit'}"
            headers = dict(driver.tokens.headers(), **{"content-type": "application/json"})
            return _request("gcs", "POST", url, headers, _json.dumps({"name": driver.bucket}).encode(), driver.timeout)[0]

        return Ensured(driver, create_gcs, f"bucket {driver.bucket}")
    if use == "s3" or use in S3_PRESETS:
        return Ensured(driver, driver.create_bucket, f"bucket {driver.bucket}")
    return driver


# --------------------------------------------------------------------- factories


def make_queue_driver(binding: Optional[Dict[str, Any]], label: str = "") -> Optional[QueueDriver]:
    """Driver for an event's ``driver`` mapping, or None for builtin / directory.

    ``label`` (the queue name) is the default native name and appears in errors.
    """
    use = str((binding or {}).get("use") or "").lower()
    if use in _FILE_BACKED:
        return None
    where = f" (queue {label})" if label else ""
    b = resolve_env(binding, f"queue {label}" if label else "")
    if use == "redis":
        from .redis import RedisQueue

        return RedisQueue(str(b["url"]), str(b.get("key") or label or "pskit"))
    if use == "redis_stream":
        from .redis_stream import RedisStreamQueue

        return RedisStreamQueue.from_binding(b, label)
    if use == "sqs":
        from .sqs import SqsQueue

        return SqsQueue.from_binding(b, label)
    if use == "azure_queue":
        from .azure import AzureQueue

        return _ensured(AzureQueue.from_binding(b, label), use, b)  # type: ignore[no-any-return]
    if use == "pubsub":
        from .gcp import PubSubQueue

        return PubSubQueue.from_binding(b, label)
    if use == "mns":
        from .mns import MnsQueue

        return MnsQueue.from_binding(b, label)
    if use == "cloudflare_queue":
        from .cloudflare import CloudflareQueue

        return CloudflareQueue.from_binding(b, label)
    if use == "pskit_host":
        from .pskit_host import PskitHostQueue

        return PskitHostQueue.from_binding(b, label)
    if use == "custom":
        return CustomQueue(_custom(b, QUEUE_METHODS, where))
    raise ValueError(f"unsupported queue driver {use!r}{where}; expected one of {', '.join(QUEUE_DRIVERS)}")


def make_storage_driver(binding: Optional[Dict[str, Any]], label: str = "") -> Optional[StorageDriver]:
    """Driver for an event's ``driver`` mapping, or None for builtin / directory."""
    use = str((binding or {}).get("use") or "").lower()
    if use in _FILE_BACKED:
        return None
    where = f" (bucket {label})" if label else ""
    b = resolve_env(binding, f"bucket {label}" if label else "")
    if use == "s3" or use in S3_PRESETS:
        return _ensured(_s3(use, b, label), use, b)  # type: ignore[no-any-return]
    if use == "azure_blob":
        from .azure import AzureBlobStorage

        return _ensured(AzureBlobStorage.from_binding(b, label), use, b)  # type: ignore[no-any-return]
    if use == "gcs":
        from .gcp import GcsStorage

        return _ensured(GcsStorage.from_binding(b, label), use, b)  # type: ignore[no-any-return]
    if use == "custom":
        return _custom(b, STORAGE_METHODS, where)  # type: ignore[no-any-return]
    raise ValueError(f"unsupported storage driver {use!r}{where}; expected one of {', '.join(STORAGE_DRIVERS)}")


def _s3(use: str, b: Dict[str, Any], label: str) -> StorageDriver:
    from ._aws import credentials
    from .s3 import S3Storage

    provider = use if use in S3_PRESETS else str(b.get("provider") or "").lower()
    if b.get("endpoint") and provider in ("", "minio"):
        # Explicit self-hosted endpoint: path-style unless told otherwise.
        endpoint, path_style, region = str(b["endpoint"]), True, str(b.get("region") or "us-east-1")
    else:
        endpoint, path_style, region = s3_preset(provider, b)
        if b.get("endpoint"):  # e.g. LocalStack, or a private endpoint of the provider
            endpoint = str(b["endpoint"])
    path_style = flag(b.get("path_style"), path_style)
    access, secret, token = credentials(
        str(b.get("access_key") or ""), str(b.get("secret_key") or ""), str(b.get("session_token") or "")
    )
    return S3Storage(
        endpoint=endpoint,
        bucket=str(b.get("bucket") or label),
        region=str(b.get("signing_region") or region),
        access_key=access,
        secret_key=secret,
        session_token=token,
        prefix=str(b.get("prefix") or ""),
        path_style=path_style,
        timeout=float(b.get("timeout") or 30),
    )


__all__ = [
    "QUEUE_DRIVERS",
    "S3_PRESETS",
    "STORAGE_DRIVERS",
    "CustomQueue",
    "QueueDriver",
    "StorageDriver",
    "flag",
    "load_class",
    "make_queue_driver",
    "make_storage_driver",
    "resolve_env",
    "s3_preset",
]
