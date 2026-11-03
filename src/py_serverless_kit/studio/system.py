"""Studio helpers that reach outside the project: a file picker, setup checks and deployed logs.

* ``browse`` lists one folder (names, sizes, no contents) so the UI can pick a
  file such as an SSH private key by path; the browser can't hand out paths.
* ``setup_*`` wrap :mod:`py_serverless_kit.core.setup_check` (prerequisites,
  ``~/.aws`` profiles, session environment variables, CLI logins, SSH test).
* ``logs_*`` read and delete the logs of the deployment recorded in
  ``.pskit/<provider>-<stage>/deployment.json`` through :mod:`core.cloud_logs`.
"""

from __future__ import annotations

import json
import os
import re
import string
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from .project import StudioError

MAX_ENTRIES = 1000
_KEY_NAME = re.compile(r"(^id_[a-z0-9_]+$)|(\.(pem|key|ppk)$)", re.I)
_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
_ALWAYS_SETTABLE = ("AWS_PROFILE", "AWS_REGION", "AWS_DEFAULT_REGION")


# --------------------------------------------------------------------- file picker


def _roots() -> List[str]:
    if sys.platform != "win32":
        return ["/"]
    return [f"{d}:\\" for d in string.ascii_uppercase if os.path.isdir(f"{d}:\\")]


def browse(path: Optional[str] = None) -> Dict[str, Any]:
    """One folder listing. ``path`` may be a file (its folder is listed) or empty (``~/.ssh`` or home)."""
    home = Path.home()
    if path:
        folder = Path(os.path.expandvars(path)).expanduser()
        if not folder.is_absolute():
            raise StudioError(400, "path must be absolute")
    else:
        folder = home / ".ssh" if (home / ".ssh").is_dir() else home
    if folder.is_file():
        folder = folder.parent
    try:
        folder = folder.resolve()
    except OSError as exc:
        raise StudioError(400, f"cannot open {folder}: {exc}") from None
    if not folder.is_dir():
        raise StudioError(404, f"{folder} is not a folder")
    entries: List[Dict[str, Any]] = []
    try:
        children = sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError as exc:
        raise StudioError(403, f"cannot list {folder}: {exc.strerror or exc}") from None
    for child in children[:MAX_ENTRIES]:
        try:
            is_dir = child.is_dir()
            size = None if is_dir else child.stat().st_size
        except OSError:
            continue
        entries.append(
            {
                "name": child.name,
                "path": str(child),
                "type": "dir" if is_dir else "file",
                "size": size,
                "key": not is_dir and bool(_KEY_NAME.search(child.name)),
            }
        )
    parent = folder.parent
    return {
        "path": str(folder),
        "parent": None if parent == folder else str(parent),
        "home": str(home),
        "roots": _roots(),
        "entries": entries,
        "truncated": len(children) > MAX_ENTRIES,
    }


# --------------------------------------------------------------------- setup


def settable_env() -> Dict[str, Dict[str, Any]]:
    from ..core.setup_check import ENV_HINTS

    out: Dict[str, Dict[str, Any]] = {name: {"name": name, "help": "", "secret": False} for name in _ALWAYS_SETTABLE}
    for hints in ENV_HINTS.values():
        for hint in hints:
            out[str(hint["name"])] = dict(hint)
    return out


def setup_status(provider: str, raw: Optional[Dict[str, Any]], root: Path) -> Dict[str, Any]:
    from ..core.setup_check import ENV_HINTS, check

    result = dict(check(provider, raw, root))
    env = []
    for hint in ENV_HINTS.get(provider, []):
        name = str(hint["name"])
        value = os.environ.get(name)
        secret = bool(hint.get("secret"))
        env.append(
            {
                **hint,
                "set": value is not None and value != "",
                # Never send secret values back to the browser.
                "value": None if secret or value is None else value,
            }
        )
    result["env"] = env
    result["platform"] = "windows" if sys.platform == "win32" else "macos" if sys.platform == "darwin" else "linux"
    return result


def set_env(name: str, value: Optional[str]) -> Dict[str, Any]:
    """Set (or unset with an empty value) a variable for this studio process and the jobs it starts."""
    name = str(name or "").strip()
    if not _ENV_NAME.match(name):
        raise StudioError(400, "invalid variable name")
    allowed = settable_env()
    if name not in allowed:
        raise StudioError(400, f"{name} is not a provider credential or setting the studio can set")
    if value is None or value == "":
        os.environ.pop(name, None)
        return {"name": name, "set": False}
    text = str(value)
    if "\n" in text or "\r" in text or "\0" in text or len(text) > 8192:
        raise StudioError(400, "the value must be a single line of at most 8192 characters")
    os.environ[name] = text
    return {"name": name, "set": True}


def aws_profile(body: Dict[str, Any]) -> Dict[str, Any]:
    from ..core.setup_check import write_aws_profile

    try:
        return write_aws_profile(
            str(body.get("profile") or "default"),
            str(body.get("access_key_id") or ""),
            str(body.get("secret_access_key") or ""),
            region=str(body["region"]) if body.get("region") else None,
            session_token=str(body["session_token"]) if body.get("session_token") else None,
        )
    except ValueError as exc:
        raise StudioError(400, str(exc)) from None


def login_command(action: str) -> List[str]:
    from ..core.setup_check import login_argv

    try:
        return login_argv(str(action or ""))
    except ValueError as exc:
        raise StudioError(400, str(exc)) from None


def ssh_command(deploy: Any) -> List[str]:
    from ..core.setup_check import ssh_test_argv

    if not isinstance(deploy, dict):
        raise StudioError(400, "deploy must be the provider.options.deploy mapping")
    try:
        return ssh_test_argv(deploy)
    except ValueError as exc:
        raise StudioError(400, str(exc)) from None


# --------------------------------------------------------------------- deployed logs


TEST_EVENTS = Path(".pskit") / "studio" / "test-events.json"


def test_guide(root: Path, provider: str, stage: str) -> Dict[str, Any]:
    """How to test every function on provider/stage: payloads, commands and console steps."""
    from ..core.project import Project
    from ..core.testing import guide

    try:
        project = Project.load(cwd=root, provider=provider, stage=stage)
    except Exception as exc:  # noqa: BLE001 - an invalid draft is shown as a message
        raise StudioError(400, f"the saved pskit.yml does not load for {provider}/{stage}: {exc}") from None
    return guide(project, deployment_record(root, provider, stage))


def resource_test_guide(root: Path, provider: str, stage: str) -> Dict[str, Any]:
    """How to test every resource on provider/stage."""
    from ..core.project import Project
    from ..core.testing import resource_guide

    try:
        project = Project.load(cwd=root, provider=provider, stage=stage)
    except Exception as exc:  # noqa: BLE001
        raise StudioError(400, f"the saved pskit.yml does not load for {provider}/{stage}: {exc}") from None
    return resource_guide(project, deployment_record(root, provider, stage))


def resource_action(
    root: Path, provider: str, stage: str, key: str, action: str, extra: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """``check`` (is it reachable?) or ``clear`` (delete a built-in on-prem resource's data)."""
    from ..core.project import Project
    from ..core.testing import TriggerError, browse_resource, check_resource, host_call, purge_resource

    extra = extra or {}

    try:
        project = Project.load(cwd=root, provider=provider, stage=stage)
    except Exception as exc:  # noqa: BLE001
        raise StudioError(400, f"the saved pskit.yml does not load for {provider}/{stage}: {exc}") from None
    record = deployment_record(root, provider, stage)
    try:
        if action == "check":
            return check_resource(project, record, key)
        if action == "data":
            return browse_resource(project, record, key, int(extra.get("offset") or 0), int(extra.get("limit") or 50),
                                   str(extra.get("prefix") or ""))
        if action == "object":
            obj = str(extra.get("object") or "")
            if extra.get("delete"):
                return dict(host_call(project, record, "DELETE", f"/__pskit/resources/{key}/object", {"key": obj}))
            return dict(host_call(project, record, "GET", f"/__pskit/resources/{key}/object", {"key": obj}))
        if action == "message-delete":
            return dict(host_call(project, record, "DELETE", f"/__pskit/resources/{key}/message", {"id": str(extra.get("id") or "")}))
        if action == "usage":
            from ..core.resource_usage import usage

            return usage(project, record, key)
        return purge_resource(project, record, key)
    except TriggerError as exc:
        raise StudioError(400, str(exc)) from None


def test_events(root: Path) -> Dict[str, Any]:
    """Saved test payloads: ``{function: [{"name", "event", "payload", "path"?}]}``."""
    path = root / TEST_EVENTS
    try:
        data = json.loads(path.read_text("utf-8")) if path.is_file() else {}
    except (OSError, ValueError):
        data = {}
    return data if isinstance(data, dict) else {}


def save_test_events(root: Path, events: Any) -> Dict[str, Any]:
    if not isinstance(events, dict):
        raise StudioError(400, "events must be an object of function name -> list")
    text = json.dumps(events, indent=2, sort_keys=True)
    if len(text) > 512 * 1024:
        raise StudioError(413, "saved test events are limited to 512 KiB")
    for name, items in events.items():
        if not isinstance(items, list) or not all(isinstance(i, dict) and isinstance(i.get("name"), str) for i in items):
            raise StudioError(400, f"events.{name} must be a list of {{name, event, payload}}")
    path = root / TEST_EVENTS
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((text + "\n").encode("utf-8"))
    return events


def cloud_resources(root: Path, provider: str, stage: str) -> Dict[str, Any]:
    """Buckets, queues and topics pskit created for provider/stage: deployed and kept."""
    from ..core.deployer import Deployer
    from ..core.project import Project

    if not (root / ".pskit" / f"{provider}-{stage}").is_dir():
        return {"deployed": [], "kept": [], "reason": f"{provider}/{stage} has not been packaged or deployed from here"}
    try:
        project = Project.load(cwd=root, provider=provider, stage=stage)
        return dict(Deployer(project, echo=lambda _m: None).cloud_resources())
    except Exception as exc:  # noqa: BLE001 - config, terraform or credential problems: show them
        raise StudioError(502, f"{type(exc).__name__}: {exc}") from None


def deployment_record(root: Path, provider: str, stage: str) -> Optional[Dict[str, Any]]:
    from ..dashboard.generator import collect_records, record_key

    key = f"{provider}-{stage}"
    for record in collect_records(root):
        if record_key(record) == key:
            return record
    return None


def _not_deployed(provider: str, stage: str) -> Dict[str, Any]:
    return {
        "supported": False,
        "reason": f"{provider}/{stage} hasn't been deployed from this folder yet. Deploy it, then come back for logs.",
        "entries": [],
        "items": [],
        "next": 0,
        "can_delete": False,
    }


def _backend(root: Path, provider: str, stage: str, server: Optional[str] = None) -> Any:
    from ..core.cloud_logs import log_backend

    record = deployment_record(root, provider, stage)
    if record is None:
        return None
    try:
        if server and provider == "onprem":
            return log_backend(record, root, server)
        return log_backend(record, root)
    except ValueError as exc:                    # an unknown saved server
        raise StudioError(400, str(exc)) from None


def _call(fn: Any) -> Dict[str, Any]:
    from ..core.cloud_logs import LogError

    try:
        return dict(fn() or {})
    except LogError as exc:
        raise StudioError(502, str(exc)) from None
    except (OSError, ValueError) as exc:
        raise StudioError(502, f"{type(exc).__name__}: {exc}") from None


def logs_query(root: Path, provider: str, stage: str, server: Optional[str] = None, **params: Any) -> Dict[str, Any]:
    backend = _backend(root, provider, stage, server)
    if backend is None:
        return _not_deployed(provider, stage)
    out = _call(lambda: backend.query(**params))
    out.setdefault("console", getattr(backend, "console", None))
    return out


def logs_streams(
    root: Path, provider: str, stage: str, function: Optional[str] = None, server: Optional[str] = None
) -> Dict[str, Any]:
    backend = _backend(root, provider, stage, server)
    if backend is None:
        return _not_deployed(provider, stage)
    out = _call(lambda: backend.streams(function=function))
    out.setdefault("can_delete", bool(getattr(backend, "can_delete", False)))
    return out


def logs_delete(
    root: Path, provider: str, stage: str, body: Dict[str, Any], server: Optional[str] = None
) -> Dict[str, Any]:
    backend = _backend(root, provider, stage, server)
    if backend is None:
        raise StudioError(404, f"{provider}/{stage} is not deployed from this folder")
    ids = body.get("ids")
    if ids is not None and (not isinstance(ids, list) or not all(isinstance(i, str) for i in ids)):
        raise StudioError(400, "ids must be a list of stream ids")
    if not ids and not body.get("all"):
        raise StudioError(400, "pass ids, or all: true")
    function = body.get("function")
    return _call(
        lambda: backend.delete(ids=ids or None, function=str(function) if function else None, all=bool(body.get("all")))
    )
