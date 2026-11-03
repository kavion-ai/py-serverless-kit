"""Portable function-to-function invocation.

``invoke("billing", {"order": 1})`` calls another function of the *same
service* regardless of the cloud it runs on:

* ``PSKIT_ENDPOINT_<NAME>`` env var set -> HTTP POST to that URL (any provider)
* on premises, a function placed on another server -> that server's host (``runtime/peers.py``)
* local (CLI / tests)                   -> in-process call through the dispatcher
* aws                                   -> ``lambda:InvokeFunction`` via boto3
* gcp                                   -> authenticated HTTPS call (ID token from metadata server)

Other providers need ``PSKIT_ENDPOINT_<NAME>`` in the caller's ``environment``
(for example the target's HTTP URL from ``pskit info``).
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Any, Callable, Dict, Optional

from .adapters.base import envelope
from .manifest import load_manifest


class InvokeError(RuntimeError):
    pass


NOT_ROUTED = object()
_ROUTER: Optional[Callable[[str, Any], Any]] = None


def install_router(router: Optional[Callable[[str, Any], Any]]) -> None:
    """``router(function, event)`` runs a function that lives elsewhere and returns its result, or
    :data:`NOT_ROUTED` for one that runs here. The on-prem host installs one when functions are placed on several
    servers, so ``invoke()`` and workflow steps reach them unchanged."""
    global _ROUTER
    _ROUTER = router


def route(function: str, event: Any) -> Any:
    """The router's answer for ``function`` (:data:`NOT_ROUTED` without a router)."""
    router = _ROUTER
    return NOT_ROUTED if router is None else router(function, event)


def _env_key(name: str) -> str:
    return "PSKIT_ENDPOINT_" + re.sub(r"[^A-Za-z0-9]", "_", name).upper()


def physical_name(function: str) -> str:
    manifest = load_manifest()
    spec = manifest.functions.get(function)
    if spec is not None and spec.resource_name:
        return spec.resource_name
    service = manifest.service or os.environ.get("PSKIT_SERVICE", "")
    stage = manifest.stage or os.environ.get("PSKIT_STAGE", "")
    return "-".join(p for p in (service, stage, function) if p)


def _http_post(url: str, payload: Any, timeout: float, headers: Optional[Dict[str, str]] = None) -> Any:
    if not url.lower().startswith(("https://", "http://")):
        raise InvokeError(f"invoke endpoint must be an http(s) URL, got {url!r}")
    data = json.dumps(envelope("invoke", payload)).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")  # noqa: S310 - scheme checked above
    req.add_header("content-type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - URL is operator supplied
            raw = resp.read()
    except Exception as exc:  # pragma: no cover - network
        raise InvokeError(f"HTTP invoke of {url} failed: {exc}") from exc
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return raw.decode("utf-8", "replace")


def _gcp_id_token(audience: str) -> str:  # pragma: no cover - needs GCP metadata server
    url = (
        "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity"
        f"?audience={audience}"
    )
    req = urllib.request.Request(url, headers={"Metadata-Flavor": "Google"})  # noqa: S310 - fixed http URL
    with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310
        return resp.read().decode("utf-8")


def logical_name(function: str) -> str:
    """The pskit function name for ``function`` given as a name, a deployed name or an ARN.

    ``arn:aws:lambda:eu-west-1:123:function:shop-dev-billing[:alias]`` and ``shop-dev-billing``
    both become ``billing`` when that is a function of this service, so code written against
    cloud names keeps working on every provider.
    """
    name = str(function)
    if name.startswith("arn:"):
        parts = name.split(":")
        # arn:partition:service:region:account:function:NAME[:qualifier]
        name = parts[6] if len(parts) > 6 and parts[5] == "function" else parts[-1]
    try:
        functions = load_manifest().functions
    except Exception:  # noqa: BLE001 - no manifest (plain scripts, tests): keep the name
        return name
    if name in functions:
        return name
    for logical, spec in functions.items():
        if name == getattr(spec, "resource_name", None) or name == physical_name(logical):
            return logical
    return name


def invoke(function: str, payload: Any = None, *, asynchronous: bool = False, timeout: float = 30.0) -> Any:
    """Invoke another function of this service and return its result.

    ``function`` may be the pskit name, the deployed name or a Lambda ARN.
    """
    function = logical_name(function)
    override = os.environ.get(_env_key(function))
    if override:
        return _http_post(override, payload, timeout)

    provider = os.environ.get("PSKIT_PROVIDER", "local")
    if provider in ("local", "onprem"):
        # In-process, including on-premises (no function URL required). asynchronous
        # still finishes before invoke() returns, same as a local run.
        from .context import Context
        from .dispatch import execute
        from .event import Event, EventType

        event = Event(type=EventType.INVOKE, provider=provider, function=function, data=payload)
        routed = route(function, event)
        if routed is not NOT_ROUTED:
            return routed
        saved = os.environ.get("PSKIT_FUNCTION")
        os.environ["PSKIT_FUNCTION"] = function
        try:
            return execute(event, Context(function=function, provider=provider), function)
        finally:
            if saved is None:
                os.environ.pop("PSKIT_FUNCTION", None)
            else:
                os.environ["PSKIT_FUNCTION"] = saved

    if provider == "aws":
        try:
            import boto3  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover
            raise InvokeError("boto3 is required for invoke() on AWS") from exc
        client = boto3.client("lambda")
        resp = client.invoke(
            FunctionName=physical_name(function),
            InvocationType="Event" if asynchronous else "RequestResponse",
            Payload=json.dumps(envelope("invoke", payload)).encode("utf-8"),
        )
        if asynchronous:
            return None
        body = resp["Payload"].read()
        if resp.get("FunctionError"):
            raise InvokeError(f"{function} failed: {body.decode('utf-8', 'replace')}")
        return json.loads(body) if body else None

    if provider == "gcp":  # pragma: no cover - needs GCP
        project = os.environ.get("PSKIT_GCP_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT", "")
        region = os.environ.get("PSKIT_REGION", "")
        url = f"https://{region}-{project}.cloudfunctions.net/{physical_name(function)}"
        token = _gcp_id_token(url)
        return _http_post(url, payload, timeout, {"authorization": f"Bearer {token}"})

    raise InvokeError(
        f"invoke() on provider {provider!r} needs the target URL in ${_env_key(function)}. "
        "Give the target function an http event and set that URL in the caller's environment."
    )
