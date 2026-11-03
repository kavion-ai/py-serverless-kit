"""Read (and write) secrets from handlers with one call on every provider.

``get_secret("db-password")`` asks a *store*. The store is chosen by environment variables, so handler code does
not change between machines and clouds:

``PSKIT_<STORE>_DRIVER``
    ``vault`` (HashiCorp Vault / OpenBao KV v2), ``aws`` (AWS Secrets Manager, or LocalStack with a URL) or ``env``.
    Default: ``vault`` when ``PSKIT_<STORE>_URL`` and ``_TOKEN`` are set, otherwise ``env``.
``PSKIT_<STORE>_URL``, ``PSKIT_<STORE>_TOKEN``, ``PSKIT_<STORE>_MOUNT`` (default ``secret``)
    Vault / OpenBao address, token and KV v2 mount.
``PSKIT_<STORE>_URL``, ``PSKIT_<STORE>_REGION``, ``PSKIT_<STORE>_ACCESS_KEY`` / ``_SECRET_KEY``
    Secrets Manager endpoint (empty: the regional AWS endpoint), region (default ``AWS_REGION``) and keys
    (default: the ``AWS_*`` variables, as in Lambda).
``PSKIT_<STORE>_DRIVER=infisical``, ``_URL``, ``_CLIENT_ID`` / ``_CLIENT_SECRET`` (a machine identity with
    Universal Auth) or ``_TOKEN``, ``_PROJECT_ID``, ``_ENVIRONMENT`` (default ``dev``), ``_PATH`` (default ``/``)
    Infisical (self-hosted or cloud). A secret's value is one string; JSON objects become fields.

The default store is ``secrets`` (``PSKIT_SECRETS_*``; override with ``PSKIT_SECRETS_STORE``), which is what the
on-prem one-click *OpenBao* / *LocalStack secrets* service writes into the env file when its key is ``secrets``.

With the ``env`` driver (no store configured) ``get_secret("db-password")`` reads ``PSKIT_SECRET_DB_PASSWORD``, then
``DB_PASSWORD``: on clouds, map the provider's secret manager into the function's environment, and the same code
runs everywhere. Standard library only.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from urllib.parse import quote, urlsplit

__all__ = ["SecretNotFound", "SecretError", "get_secret", "get_secrets", "put_secret"]

_TTL = 60.0
_cache: Dict[Tuple[str, str], Tuple[float, Dict[str, str]]] = {}
_lock = threading.Lock()


class SecretError(RuntimeError):
    """The store could not be reached or refused the request."""


class SecretNotFound(SecretError, KeyError):
    """No such secret (or field)."""

    def __str__(self) -> str:  # KeyError would add quotes
        return str(self.args[0]) if self.args else "secret not found"


def _var(name: str) -> str:
    return re.sub(r"[^A-Z0-9]", "_", name.upper())


def _config(store: Optional[str]) -> Dict[str, str]:
    name = store or os.environ.get("PSKIT_SECRETS_STORE") or "secrets"
    prefix = "PSKIT_" + _var(name) + "_"
    env = {k[len(prefix):].lower(): v for k, v in os.environ.items() if k.startswith(prefix)}
    driver = env.get("driver") or ("vault" if env.get("token") and env.get("url") else "env")
    return {"store": name, "driver": driver.lower(), **env}


def _http(method: str, url: str, headers: Dict[str, str], body: Optional[bytes] = None) -> Tuple[int, bytes]:
    import urllib.error
    import urllib.request

    req = urllib.request.Request(url, data=body, method=method)  # noqa: S310 - operator-configured endpoint
    for key, value in headers.items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except (urllib.error.URLError, OSError) as exc:
        raise SecretError(f"secret store {urlsplit(url).netloc} is unreachable: {getattr(exc, 'reason', exc)}") from exc


# ----------------------------------------------------------------------------- drivers


def _vault_read(cfg: Dict[str, str], name: str) -> Dict[str, str]:
    url = cfg.get("url", "").rstrip("/")
    mount = cfg.get("mount") or "secret"
    status, body = _http("GET", f"{url}/v1/{mount}/data/{quote(name)}", {"X-Vault-Token": cfg.get("token", "")})
    if status == 404:
        raise SecretNotFound(f"secret {name!r} not found in {cfg['store']} ({mount}/)")
    if status != 200:
        raise SecretError(f"vault: reading {name!r} failed ({status}): {body[:200].decode('utf-8', 'replace')}")
    data = (json.loads(body.decode("utf-8")).get("data") or {}).get("data") or {}
    return {str(k): v if isinstance(v, str) else json.dumps(v) for k, v in data.items()}


def _vault_write(cfg: Dict[str, str], name: str, values: Dict[str, str]) -> None:
    url = cfg.get("url", "").rstrip("/")
    mount = cfg.get("mount") or "secret"
    payload = json.dumps({"data": values}).encode("utf-8")
    status, body = _http("POST", f"{url}/v1/{mount}/data/{quote(name)}",
                         {"X-Vault-Token": cfg.get("token", ""), "Content-Type": "application/json"}, payload)
    if status not in (200, 204):
        raise SecretError(f"vault: writing {name!r} failed ({status}): {body[:200].decode('utf-8', 'replace')}")


def _aws_call(cfg: Dict[str, str], target: str, payload: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    from .drivers._aws import credentials, sign

    region = cfg.get("region") or os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
    url = (cfg.get("url") or f"https://secretsmanager.{region}.amazonaws.com").rstrip("/")
    parts = urlsplit(url)
    access, secret, token = credentials(cfg.get("access_key", ""), cfg.get("secret_key", ""))
    if not access or not secret:
        raise SecretError("aws secrets: no credentials (PSKIT_<STORE>_ACCESS_KEY / AWS_ACCESS_KEY_ID)")
    body = json.dumps(payload).encode("utf-8")
    import hashlib

    headers = {"content-type": "application/x-amz-json-1.1", "x-amz-target": f"secretsmanager.{target}"}
    if token:
        headers["x-amz-security-token"] = token
    signed = sign("POST", parts.netloc, parts.path or "/", {}, headers, hashlib.sha256(body).hexdigest(), access,
                  secret, region, datetime.now(timezone.utc), service="secretsmanager")
    status, raw = _http("POST", url + "/", {k: v for k, v in signed.items() if k != "host"}, body)
    try:
        data = json.loads(raw.decode("utf-8")) if raw.strip() else {}
    except ValueError:
        data = {"message": raw[:200].decode("utf-8", "replace")}
    return status, data


def _aws_read(cfg: Dict[str, str], name: str) -> Dict[str, str]:
    status, data = _aws_call(cfg, "GetSecretValue", {"SecretId": name})
    if status == 400 and "ResourceNotFound" in str(data.get("__type", "")):
        raise SecretNotFound(f"secret {name!r} not found in {cfg['store']} (Secrets Manager)")
    if status != 200:
        raise SecretError(f"secretsmanager: reading {name!r} failed ({status}): {data.get('message') or data.get('Message') or data}")
    text = str(data.get("SecretString") or "")
    try:
        parsed = json.loads(text)
    except ValueError:
        parsed = None
    if isinstance(parsed, dict):
        return {str(k): v if isinstance(v, str) else json.dumps(v) for k, v in parsed.items()}
    return {"value": text}


def _aws_write(cfg: Dict[str, str], name: str, values: Dict[str, str]) -> None:
    text = values["value"] if list(values) == ["value"] else json.dumps(values)
    import uuid

    status, data = _aws_call(cfg, "PutSecretValue", {"SecretId": name, "SecretString": text,
                                                     "ClientRequestToken": str(uuid.uuid4())})
    if status == 400 and "ResourceNotFound" in str(data.get("__type", "")):
        status, data = _aws_call(cfg, "CreateSecret", {"Name": name, "SecretString": text,
                                                       "ClientRequestToken": str(uuid.uuid4())})
    if status != 200:
        raise SecretError(f"secretsmanager: writing {name!r} failed ({status}): {data.get('message') or data.get('Message') or data}")


def _env_read(_cfg: Dict[str, str], name: str) -> Dict[str, str]:
    for var in ("PSKIT_SECRET_" + _var(name), _var(name)):
        if var in os.environ:
            text = os.environ[var]
            try:
                parsed = json.loads(text)
            except ValueError:
                parsed = None
            if isinstance(parsed, dict):
                return {str(k): v if isinstance(v, str) else json.dumps(v) for k, v in parsed.items()}
            return {"value": text}
    raise SecretNotFound(f"secret {name!r} not found: set PSKIT_SECRET_{_var(name)} (or {_var(name)}), or configure a "
                         "store (PSKIT_SECRETS_URL / _TOKEN)")


_tokens: Dict[str, Tuple[float, str]] = {}


def _infisical_token(cfg: Dict[str, str]) -> str:
    if cfg.get("token"):
        return cfg["token"]
    if not cfg.get("client_id") or not cfg.get("client_secret"):
        raise SecretError(f"infisical: set PSKIT_{_var(cfg['store'])}_CLIENT_ID and _CLIENT_SECRET (a machine identity "
                          "with Universal Auth) or _TOKEN")
    url = cfg.get("url", "").rstrip("/")
    with _lock:
        hit = _tokens.get(url + cfg["client_id"])
    if hit and hit[0] > time.monotonic():
        return hit[1]
    payload = json.dumps({"clientId": cfg["client_id"], "clientSecret": cfg["client_secret"]}).encode("utf-8")
    status, body = _http("POST", f"{url}/api/v1/auth/universal-auth/login", {"Content-Type": "application/json"},
                         payload)
    if status != 200:
        raise SecretError(f"infisical: login failed ({status}): {body[:200].decode('utf-8', 'replace')}")
    data = json.loads(body.decode("utf-8"))
    token = str(data.get("accessToken") or "")
    with _lock:
        _tokens[url + cfg["client_id"]] = (time.monotonic() + max(60, int(data.get("expiresIn") or 600)) - 30, token)
    return token


def _infisical_scope(cfg: Dict[str, str]) -> Dict[str, str]:
    if not cfg.get("project_id"):
        raise SecretError(f"infisical: set PSKIT_{_var(cfg['store'])}_PROJECT_ID (Project settings -> Project ID)")
    return {"workspaceId": cfg["project_id"], "environment": cfg.get("environment") or "dev",
            "secretPath": cfg.get("path") or "/"}


def _infisical_read(cfg: Dict[str, str], name: str) -> Dict[str, str]:
    from urllib.parse import urlencode

    url = cfg.get("url", "").rstrip("/")
    query = urlencode(_infisical_scope(cfg))
    status, body = _http("GET", f"{url}/api/v3/secrets/raw/{quote(name)}?{query}",
                         {"Authorization": f"Bearer {_infisical_token(cfg)}"})
    if status == 404:
        raise SecretNotFound(f"secret {name!r} not found in {cfg['store']} (infisical)")
    if status != 200:
        raise SecretError(f"infisical: reading {name!r} failed ({status}): {body[:200].decode('utf-8', 'replace')}")
    text = str((json.loads(body.decode("utf-8")).get("secret") or {}).get("secretValue") or "")
    try:
        parsed = json.loads(text)
    except ValueError:
        parsed = None
    if isinstance(parsed, dict):
        return {str(k): v if isinstance(v, str) else json.dumps(v) for k, v in parsed.items()}
    return {"value": text}


def _infisical_write(cfg: Dict[str, str], name: str, values: Dict[str, str]) -> None:
    url = cfg.get("url", "").rstrip("/")
    text = values["value"] if list(values) == ["value"] else json.dumps(values, sort_keys=True)
    payload = json.dumps({**_infisical_scope(cfg), "secretValue": text, "type": "shared"}).encode("utf-8")
    headers = {"Authorization": f"Bearer {_infisical_token(cfg)}", "Content-Type": "application/json"}
    status, body = _http("PATCH", f"{url}/api/v3/secrets/raw/{quote(name)}", headers, payload)
    if status in (400, 404):  # not there yet
        status, body = _http("POST", f"{url}/api/v3/secrets/raw/{quote(name)}", headers, payload)
    if status != 200:
        raise SecretError(f"infisical: writing {name!r} failed ({status}): {body[:200].decode('utf-8', 'replace')}")


_READ = {"vault": _vault_read, "aws": _aws_read, "env": _env_read, "infisical": _infisical_read}
_WRITE = {"vault": _vault_write, "aws": _aws_write, "infisical": _infisical_write}


# ----------------------------------------------------------------------------- API


def get_secrets(name: str, *, store: Optional[str] = None, refresh: bool = False) -> Dict[str, str]:
    """Every field of secret ``name`` (a plain secret is ``{"value": ...}``). Cached for 60 s."""
    cfg = _config(store)
    reader = _READ.get(cfg["driver"])
    if reader is None:
        raise SecretError(f"unknown secrets driver {cfg['driver']!r} (vault, aws, infisical or env)")
    key = (cfg["store"], name)
    now = time.monotonic()
    with _lock:
        hit = _cache.get(key)
    if hit and not refresh and now - hit[0] < _TTL:
        return dict(hit[1])
    values = reader(cfg, name)
    with _lock:
        _cache[key] = (now, values)
    return dict(values)


def get_secret(name: str, field: Optional[str] = None, *, store: Optional[str] = None,
               default: Optional[str] = None) -> str:
    """One secret value: ``field`` of secret ``name``, or its only / ``value`` field.

    ``default`` is returned instead of raising :class:`SecretNotFound` when it is given.
    """
    try:
        values = get_secrets(name, store=store)
    except SecretNotFound:
        if default is not None:
            return default
        raise
    if field is None:
        if "value" in values:
            return values["value"]
        if len(values) == 1:
            return next(iter(values.values()))
        return json.dumps(values, sort_keys=True)
    if field in values:
        return values[field]
    if default is not None:
        return default
    raise SecretNotFound(f"secret {name!r} has no field {field!r} (fields: {', '.join(sorted(values))})")


def put_secret(name: str, value: Any, *, store: Optional[str] = None) -> None:
    """Create or update secret ``name``: a string (stored as ``value``) or a dict of fields."""
    cfg = _config(store)
    writer = _WRITE.get(cfg["driver"])
    if writer is None:
        raise SecretError(f"the {cfg['driver']} secrets driver is read-only; write with your provider's tools")
    values = {str(k): str(v) for k, v in value.items()} if isinstance(value, dict) else {"value": str(value)}
    writer(cfg, name, values)
    with _lock:
        _cache.pop((cfg["store"], name), None)
