"""Read the ``resources:`` bindings of the current function.

The CLI injects, for every resource bound to a function::

    PSKIT_RESOURCES=uploads,jobs
    PSKIT_RESOURCE_UPLOADS_TYPE=storage
    PSKIT_RESOURCE_UPLOADS_NAME=acme-uploads      # native bucket / queue / topic name
    PSKIT_RESOURCE_UPLOADS_EXTERNAL=false
    PSKIT_RESOURCE_UPLOADS_<KEY>=...              # one per `connection:` entry
    PSKIT_RESOURCE_UPLOADS_ARN / _URL / _ID=...   # when the provider knows them

``resource("uploads")`` turns those variables back into a :class:`Resource`, so
handler code stays the same on every cloud.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Dict, Mapping, Optional

_FIXED = ("TYPE", "NAME", "EXTERNAL")


def _env_key(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "_", text).upper()


@dataclass
class Resource:
    name: str
    type: str
    native_name: str
    external: bool = False
    connection: Dict[str, str] = field(default_factory=dict)

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Connection value by case-insensitive key, e.g. ``res.get("endpoint")``."""
        return self.connection.get(key.lower(), default)

    def __getitem__(self, key: str) -> str:
        value = self.get(key)
        if value is None:
            known = ", ".join(sorted(self.connection)) or "<none>"
            raise KeyError(f"resource {self.name!r} has no {key!r}; known: {known}")
        return value

    @property
    def arn(self) -> Optional[str]:
        return self.get("arn")

    @property
    def url(self) -> Optional[str]:
        return self.get("url")

    @property
    def id(self) -> Optional[str]:
        return self.get("id")


def _names(env: Mapping[str, str]) -> list:
    return [n.strip() for n in (env.get("PSKIT_RESOURCES") or "").split(",") if n.strip()]


def _build(name: str, env: Mapping[str, str], names: list) -> Resource:
    prefix = f"PSKIT_RESOURCE_{_env_key(name)}_"
    # Variables of a longer resource key (``a`` vs ``a_b``) share this prefix: skip them.
    longer = [
        f"PSKIT_RESOURCE_{_env_key(other)}_"
        for other in names
        if _env_key(other) != _env_key(name) and f"PSKIT_RESOURCE_{_env_key(other)}_".startswith(prefix)
    ]
    connection: Dict[str, str] = {}
    for var, value in env.items():
        if not var.startswith(prefix) or any(var.startswith(o) for o in longer):
            continue
        suffix = var[len(prefix) :]
        if suffix and suffix not in _FIXED:
            connection[suffix.lower()] = value
    return Resource(
        name=name,
        type=env.get(prefix + "TYPE", ""),
        native_name=env.get(prefix + "NAME", name),
        external=env.get(prefix + "EXTERNAL", "false").lower() == "true",
        connection=connection,
    )


def resources(env: Optional[Mapping[str, str]] = None) -> Dict[str, Resource]:
    """Every resource bound to the current function."""
    source = os.environ if env is None else env
    names = _names(source)
    return {name: _build(name, source, names) for name in names}


def resource(name: str, env: Optional[Mapping[str, str]] = None) -> Resource:
    """The binding of resource ``name`` (the key under ``resources:`` in pskit.yml)."""
    source = os.environ if env is None else env
    names = _names(source)
    match = next((n for n in names if n == name), None)
    if match is None:
        match = next((n for n in names if _env_key(n) == _env_key(name)), None)
    if match is None:
        known = ", ".join(names) or "<none>"
        raise KeyError(
            f"resource {name!r} is not bound to this function; bound: {known}. "
            "Check `resources:` and its `functions:` list in pskit.yml."
        )
    return _build(match, source, names)
