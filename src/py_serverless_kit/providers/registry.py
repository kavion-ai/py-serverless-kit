"""Provider registry. Third-party providers can register through the
``py_serverless_kit.providers`` entry-point group."""

from __future__ import annotations

import importlib
from typing import Dict, List, Type

from .base import Provider, ProviderError

BUILTIN: Dict[str, str] = {
    "aws": "py_serverless_kit.providers.aws:AwsProvider",
    "azure": "py_serverless_kit.providers.azure:AzureProvider",
    "gcp": "py_serverless_kit.providers.gcp:GcpProvider",
    "alibaba": "py_serverless_kit.providers.alibaba:AlibabaProvider",
    "oracle": "py_serverless_kit.providers.oracle:OracleProvider",
    "ibm": "py_serverless_kit.providers.ibm:IbmProvider",
    "digitalocean": "py_serverless_kit.providers.digitalocean:DigitalOceanProvider",
    "tencent": "py_serverless_kit.providers.tencent:TencentProvider",
    "huawei": "py_serverless_kit.providers.huawei:HuaweiProvider",
    "cloudflare": "py_serverless_kit.providers.cloudflare:CloudflareProvider",
    "onprem": "py_serverless_kit.providers.onprem:OnPremProvider",
}

_CACHE: Dict[str, Provider] = {}


def _load(target: str) -> Type[Provider]:
    module, _, attr = target.partition(":")
    return getattr(importlib.import_module(module), attr)


def _entry_points() -> Dict[str, str]:
    try:
        from importlib.metadata import entry_points
    except ImportError:  # pragma: no cover
        return {}
    try:
        eps = entry_points(group="py_serverless_kit.providers")  # type: ignore[call-arg]
    except TypeError:  # pragma: no cover - Python 3.9
        eps = entry_points().get("py_serverless_kit.providers", [])  # type: ignore[attr-defined,arg-type]
    return {ep.name: ep.value for ep in eps}


def available() -> List[str]:
    return sorted(set(BUILTIN) | set(_entry_points()))


def get_provider(name: str) -> Provider:
    if name in _CACHE:
        return _CACHE[name]
    target = BUILTIN.get(name) or _entry_points().get(name)
    if target is None:
        raise ProviderError(f"unknown provider {name!r}; available: {', '.join(available())}")
    provider = _load(target)()
    _CACHE[name] = provider
    return provider


def all_providers() -> List[Provider]:
    return [get_provider(n) for n in available()]
