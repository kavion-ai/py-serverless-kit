"""``GET /api/discover``: list existing queues, buckets, topics and workflows to pick from.

Uses the cloud SDKs only when they are installed, with the machine's normal
credentials (never credentials from the browser). Anything that can't be listed
returns ``supported: false`` and a reason, so the UI falls back to a text field.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

KINDS = ("queue", "storage", "topic", "workflow")
LIMIT = 200
TIMEOUT = 15.0


def _result(
    supported: bool, reason: str = "", items: Optional[List[Dict[str, Any]]] = None, error: Optional[str] = None
) -> Dict[str, Any]:
    out: Dict[str, Any] = {"supported": supported, "reason": reason, "items": (items or [])[:LIMIT]}
    if error:
        out["error"] = error
    return out


def _with_timeout(fn: Callable[[], List[Dict[str, Any]]], timeout: float = TIMEOUT) -> List[Dict[str, Any]]:
    box: Dict[str, Any] = {}

    def run() -> None:
        try:
            box["items"] = fn()
        except BaseException as exc:  # noqa: BLE001 - re-raised in the caller
            box["error"] = exc

    worker = threading.Thread(target=run, name="pskit-studio-discover", daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        raise TimeoutError(f"listing took longer than {int(timeout)} s")
    if "error" in box:
        raise box["error"]
    return list(box.get("items") or [])


# --------------------------------------------------------------------- AWS


def _aws(kind: str, region: Optional[str]) -> List[Dict[str, Any]]:
    import boto3  # type: ignore[import-not-found,import-untyped,unused-ignore]

    session = boto3.session.Session(region_name=region or None)
    items: List[Dict[str, Any]] = []
    if kind == "queue":
        client = session.client("sqs")
        token = None
        while len(items) < LIMIT:
            kwargs: Dict[str, Any] = {"MaxResults": 100}
            if token:
                kwargs["NextToken"] = token
            page = client.list_queues(**kwargs)
            for url in page.get("QueueUrls") or []:
                items.append({"name": url.rstrip("/").rsplit("/", 1)[-1], "id": url, "region": session.region_name})
            token = page.get("NextToken")
            if not token:
                break
    elif kind == "storage":
        client = session.client("s3")
        for bucket in (client.list_buckets().get("Buckets") or [])[:LIMIT]:
            name = bucket.get("Name")
            items.append({"name": name, "id": name, "arn": f"arn:aws:s3:::{name}"})
    elif kind == "topic":
        client = session.client("sns")
        token = None
        while len(items) < LIMIT:
            page = client.list_topics(**({"NextToken": token} if token else {}))
            for topic in page.get("Topics") or []:
                arn = topic.get("TopicArn", "")
                items.append({"name": arn.rsplit(":", 1)[-1], "id": arn, "arn": arn, "region": session.region_name})
            token = page.get("NextToken")
            if not token:
                break
    else:
        client = session.client("stepfunctions")
        token = None
        while len(items) < LIMIT:
            kwargs = {"maxResults": 100}
            if token:
                kwargs["nextToken"] = token
            page = client.list_state_machines(**kwargs)
            for machine in page.get("stateMachines") or []:
                arn = machine.get("stateMachineArn", "")
                items.append(
                    {
                        "name": machine.get("name"),
                        "id": arn,
                        "arn": arn,
                        "region": session.region_name,
                        "detail": machine.get("type"),
                    }
                )
            token = page.get("nextToken")
            if not token:
                break
    return items


# --------------------------------------------------------------------- GCP


def _gcp_project(project: Optional[str]) -> str:
    found = project or os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCLOUD_PROJECT")
    if not found:
        raise ValueError("set provider.options.project (or GOOGLE_CLOUD_PROJECT) to list GCP resources")
    return found


def _gcp(kind: str, project: Optional[str]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if kind == "storage":
        from google.cloud import storage  # type: ignore[import-not-found,import-untyped,unused-ignore]

        client = storage.Client(project=_gcp_project(project))
        for bucket in client.list_buckets(max_results=LIMIT):
            items.append({"name": bucket.name, "id": bucket.name, "region": getattr(bucket, "location", None)})
        return items
    if kind in ("queue", "topic"):
        from google.cloud import pubsub_v1  # type: ignore[import-not-found,import-untyped,unused-ignore]

        proj = _gcp_project(project)
        if kind == "topic":
            publisher = pubsub_v1.PublisherClient()
            for topic in publisher.list_topics(request={"project": f"projects/{proj}"}):
                items.append({"name": topic.name.rsplit("/", 1)[-1], "id": topic.name})
                if len(items) >= LIMIT:
                    break
        else:
            subscriber = pubsub_v1.SubscriberClient()
            for sub in subscriber.list_subscriptions(request={"project": f"projects/{proj}"}):
                items.append({"name": sub.name.rsplit("/", 1)[-1], "id": sub.name, "detail": sub.topic})
                if len(items) >= LIMIT:
                    break
        return items
    raise LookupError("listing Cloud Workflows is not supported; type the name")


_GCP_PACKAGES = {"storage": "google-cloud-storage", "queue": "google-cloud-pubsub", "topic": "google-cloud-pubsub"}


# --------------------------------------------------------------------- Azure


def _azure(kind: str) -> List[Dict[str, Any]]:
    conn = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    if not conn:
        raise PermissionError("set AZURE_STORAGE_CONNECTION_STRING where pskit studio runs to list Azure queues/blobs")
    items: List[Dict[str, Any]] = []
    if kind == "queue":
        from azure.storage.queue import QueueServiceClient  # type: ignore[import-not-found,import-untyped,unused-ignore]

        for queue in QueueServiceClient.from_connection_string(conn).list_queues():
            items.append({"name": queue.name, "id": queue.name})
            if len(items) >= LIMIT:
                break
    elif kind == "storage":
        from azure.storage.blob import BlobServiceClient  # type: ignore[import-not-found,import-untyped,unused-ignore]

        for container in BlobServiceClient.from_connection_string(conn).list_containers():
            items.append({"name": container.name, "id": container.name})
            if len(items) >= LIMIT:
                break
    else:
        raise LookupError(f"listing Azure {kind}s is not supported; type the name")
    return items


_AZURE_PACKAGES = {"queue": "azure-storage-queue", "storage": "azure-storage-blob"}


# --------------------------------------------------------------------- on-prem


def _onprem(root: Path, kind: str, raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    provider = raw.get("provider") or {}
    options = provider.get("options") or {} if isinstance(provider, dict) else {}
    service = str(raw.get("service") or "")
    stage = str((provider.get("stage") if isinstance(provider, dict) else None) or "dev")
    data_dir = options.get("data_dir")
    base = Path(str(data_dir)) if data_dir else Path(".pskit") / "onprem-data" / f"{service}-{stage}"
    if not base.is_absolute():
        base = root / base
    sub = {"queue": "queues", "storage": "buckets", "topic": "topics"}.get(kind)
    if sub is None:
        raise LookupError("on-premises workflows are defined in pskit.yml; there is nothing to list")
    services = options.get("services") or {}
    binding = services.get(kind) if isinstance(services, dict) else None
    folder = base / sub
    if isinstance(binding, dict) and binding.get("path"):
        folder = Path(str(binding["path"]))
        if not folder.is_absolute():
            folder = root / folder
    if not folder.is_dir():
        return []
    return [
        {"name": child.name, "id": str(child), "detail": "directory"}
        for child in sorted(folder.iterdir())
        if child.is_dir() and not child.name.startswith(".")
    ][:LIMIT]


def discover(
    root: Path, provider: str, kind: str, region: Optional[str] = None, raw: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    if kind not in KINDS:
        return _result(False, f"kind must be one of {', '.join(KINDS)}")
    raw = raw or {}
    options = ((raw.get("provider") or {}).get("options") or {}) if isinstance(raw.get("provider"), dict) else {}
    try:
        if provider == "aws":
            try:
                import boto3  # type: ignore[import-not-found,import-untyped,unused-ignore] # noqa: F401
            except ImportError:
                return _result(False, "install boto3 to list AWS resources: pip install 'py-serverless-kit[aws]'")
            return _result(True, items=_with_timeout(lambda: _aws(kind, region)))
        if provider == "gcp":
            if kind == "workflow":
                return _result(False, "listing Cloud Workflows isn't available; type the name")
            package = _GCP_PACKAGES[kind]
            try:
                if kind == "storage":
                    from google.cloud import storage  # type: ignore[import-not-found,import-untyped,unused-ignore] # noqa: F401
                else:
                    from google.cloud import pubsub_v1  # type: ignore[import-not-found,import-untyped,unused-ignore] # noqa: F401
            except ImportError:
                return _result(False, f"install {package} to list GCP resources: pip install {package}")
            project = options.get("project") if isinstance(options.get("project"), str) else None
            if project and "${" in project:
                project = None
            return _result(True, items=_with_timeout(lambda: _gcp(kind, project)))
        if provider == "azure":
            if kind not in _AZURE_PACKAGES:
                return _result(False, f"listing Azure {kind}s isn't available; type the name")
            package = _AZURE_PACKAGES[kind]
            try:
                if kind == "queue":
                    import azure.storage.queue  # type: ignore[import-not-found,import-untyped,unused-ignore] # noqa: F401
                else:
                    import azure.storage.blob  # type: ignore[import-not-found,import-untyped,unused-ignore] # noqa: F401
            except ImportError:
                return _result(False, f"install {package} to list Azure resources: pip install {package}")
            if not os.environ.get("AZURE_STORAGE_CONNECTION_STRING"):
                return _result(
                    False,
                    "set AZURE_STORAGE_CONNECTION_STRING where pskit studio runs to list Azure queues and containers",
                )
            return _result(True, items=_with_timeout(lambda: _azure(kind)))
        if provider == "onprem":
            return _result(True, items=_onprem(root, kind, raw))
    except LookupError as exc:
        return _result(False, str(exc.args[0] if exc.args else exc))
    except Exception as exc:  # noqa: BLE001 - credentials, network, permissions: show, don't 500
        return _result(True, error=f"{type(exc).__name__}: {exc}")
    return _result(False, f"type the name; listing isn't available for {provider}")
