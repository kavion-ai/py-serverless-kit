"""Load, merge and interpolate ``pskit.yml``.

Resolution order (later wins):

1. ``extends: other.yml``            - parent file(s), deep-merged
2. the file itself
3. ``providers.<provider>:``         - per-cloud overrides of any top-level key
4. ``stages.<stage>:``               - per-stage overrides of any top-level key
5. CLI flags (``--provider``, ``--stage``, ``--region``)

Then variables are interpolated:

* ``${env:NAME}`` / ``${env:NAME, default}``  - environment variable
* ``${opt:stage}`` / ``${opt:region}`` / ``${opt:provider}`` - effective CLI values
* ``${self:dotted.path}``                     - any value in the merged config
* ``${file(path/to/file.json)}`` / ``.yml`` / ``.txt`` - file content (relative to the config)

``${tf:aws_dynamodb_table.orders.arn}`` is left for Terraform (see providers.terraform_doc.escape),
and any other ``${...}`` (e.g. IAM policy variables like ``${aws:username}``) is kept verbatim.
"""

from __future__ import annotations

import copy
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import ValidationError

from .schema import PROVIDERS, ServiceConfig

DEFAULT_FILES = ("pskit.yml", "pskit.yaml", "serverless_kit.yml", "serverless_kit.yaml")
# Only these sources are resolved here. Anything else - IAM policy variables such
# as ${aws:username}, or ${tf:resource.attr} Terraform references - is kept as is.
_VAR = re.compile(r"\$\{\s*(env|opt|self|file)(?::([^}]*)|\(([^)]*)\))\s*\}")
MAX_PASSES = 10


class ConfigError(Exception):
    """User-facing configuration problem."""


@dataclass
class LoadedConfig:
    config: ServiceConfig
    path: Path
    root: Path
    raw: Dict[str, Any]

    @property
    def provider(self) -> str:
        return self.config.provider.name

    @property
    def stage(self) -> str:
        return self.config.provider.stage


def deep_merge(base: Any, override: Any) -> Any:
    if isinstance(base, dict) and isinstance(override, dict):
        out = dict(base)
        for key, value in override.items():
            out[key] = deep_merge(base[key], value) if key in base else copy.deepcopy(value)
        return out
    return copy.deepcopy(override)


def find_config(path: Optional[str] = None, cwd: Optional[Path] = None) -> Path:
    cwd = cwd or Path.cwd()
    if path:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = cwd / candidate
        if not candidate.is_file():
            raise ConfigError(f"config file not found: {candidate}")
        return candidate
    for name in DEFAULT_FILES:
        if (cwd / name).is_file():
            return cwd / name
    raise ConfigError(f"no config found in {cwd} (looked for {', '.join(DEFAULT_FILES)}); run `pskit init`")


def _read_layers(path: Path, chain: Optional[List[Path]] = None) -> List[Dict[str, Any]]:
    """Return the file and its ``extends`` ancestors as layers, parents first."""
    chain = chain or []
    if path in chain:
        raise ConfigError("circular `extends`: " + " -> ".join(str(p) for p in chain + [path]))
    try:
        data = yaml.safe_load(path.read_text("utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a mapping at the top level")
    parents = data.pop("extends", None)
    layers: List[Dict[str, Any]] = []
    for parent in [parents] if isinstance(parents, str) else parents or []:
        layers.extend(_read_layers((path.parent / parent).resolve(), chain + [path]))
    if isinstance(data.get("provider"), str):
        data["provider"] = {"name": data["provider"]}
    layers.append(data)
    return layers


_PROVIDER_FIELDS = {
    "region",
    "stage",
    "runtime",
    "memory",
    "timeout",
    "architecture",
    "environment",
    "tags",
    "iam",
    "log_retention_days",
    "options",
    "state",
    "terraform",
}


def _known_providers() -> List[str]:
    """Built-in providers plus any registered through entry points."""
    try:
        from ..providers.registry import available  # local import: avoids an import cycle

        return sorted(set(PROVIDERS) | set(available()))
    except Exception:  # noqa: BLE001 - a broken plug-in must not break config loading
        return list(PROVIDERS)


def _provider_override(block: Dict[str, Any]) -> Dict[str, Any]:
    """``providers.<cloud>`` block -> top-level override; ProviderConfig keys may be
    written directly (``region: x``) as shorthand for ``provider: {region: x}``."""
    block = dict(block or {})
    short = {k: block.pop(k) for k in list(block) if k in _PROVIDER_FIELDS}
    return deep_merge(block, {"provider": short}) if short else block


def _lookup(data: Any, dotted: str) -> Any:
    current = data
    for part in dotted.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            raise KeyError(dotted)
    return current


class _Interpolator:
    def __init__(self, root: Dict[str, Any], opts: Dict[str, str], base_dir: Path) -> None:
        self.root = root
        self.opts = opts
        self.base_dir = base_dir
        self.unresolved: List[str] = []

    def resolve_var(self, kind: str, arg: str) -> Any:
        arg = (arg or "").strip()
        if kind == "env":
            name, _, default = arg.partition(",")
            name = name.strip()
            if name in os.environ:
                return os.environ[name]
            if _:
                return _strip_quotes(default.strip())
            raise KeyError(f"env:{name}")
        if kind == "opt":
            name, _, default = arg.partition(",")
            if name.strip() in self.opts:
                return self.opts[name.strip()]
            if _:
                return _strip_quotes(default.strip())
            raise KeyError(f"opt:{name.strip()}")
        if kind == "self":
            name, _, default = arg.partition(",")
            try:
                return _lookup(self.root, name.strip())
            except KeyError:
                if _:
                    return _strip_quotes(default.strip())
                raise KeyError(f"self:{name.strip()}") from None
        if kind == "file":
            target = (self.base_dir / _strip_quotes(arg)).resolve()
            if not target.is_file():
                raise ConfigError(f"${{file({arg})}}: {target} does not exist")
            text = target.read_text("utf-8")
            if target.suffix == ".json":
                return json.loads(text)
            if target.suffix in (".yml", ".yaml"):
                return yaml.safe_load(text)
            return text.strip()
        raise ConfigError(f"unknown variable source ${{{kind}:...}}; use env, opt, self or file")

    def walk(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {k: self.walk(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.walk(v) for v in value]
        if not isinstance(value, str) or "${" not in value:
            return value
        whole = _VAR.fullmatch(value.strip())
        if whole:
            kind, arg1, arg2 = whole.groups()
            try:
                return self.resolve_var(kind, arg1 if arg1 is not None else arg2)
            except KeyError as exc:
                self.unresolved.append(str(exc).strip("'"))
                return value

        def sub(m: re.Match[str]) -> str:
            kind, arg1, arg2 = m.groups()
            try:
                resolved = self.resolve_var(kind, arg1 if arg1 is not None else arg2)
            except KeyError as exc:
                self.unresolved.append(str(exc).strip("'"))
                return m.group(0)
            return resolved if isinstance(resolved, str) else json.dumps(resolved)

        return _VAR.sub(sub, value)


def _strip_quotes(text: str) -> str:
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        return text[1:-1]
    return text


def interpolate(data: Dict[str, Any], opts: Dict[str, str], base_dir: Path) -> Dict[str, Any]:
    current = data
    for _ in range(MAX_PASSES):
        interp = _Interpolator(current, opts, base_dir)
        nxt = interp.walk(current)
        if nxt == current:
            if interp.unresolved:
                missing = ", ".join(sorted(set(interp.unresolved)))
                raise ConfigError(f"unresolved variables: {missing}")
            return nxt
        current = nxt
    raise ConfigError("variable interpolation did not converge (circular ${self:...} reference?)")


def build_raw(
    path: Path,
    *,
    provider: Optional[str] = None,
    stage: Optional[str] = None,
    region: Optional[str] = None,
) -> Dict[str, Any]:
    layers = _read_layers(path.resolve())
    bases = [{k: v for k, v in layer.items() if k not in ("providers", "stages")} for layer in layers]
    merged_base: Dict[str, Any] = {}
    for base in bases:
        merged_base = deep_merge(merged_base, base)
    name = provider or (merged_base.get("provider") or {}).get("name")
    if not name:
        raise ConfigError("provider.name is required (or pass --provider)")
    known = _known_providers()
    if name not in known:
        raise ConfigError(f"unknown provider {name!r}; supported: {', '.join(known)}")

    # Each file's `providers.<name>` override is applied right after that file's own
    # values, so a child file always wins over its parent's per-provider overrides.
    data: Dict[str, Any] = {}
    stage_overrides: Dict[str, Any] = {}
    for layer, base in zip(layers, bases):
        overrides = layer.get("providers") or {}
        unknown = set(overrides) - set(known)
        if unknown:
            raise ConfigError(f"`providers:` has unknown keys {sorted(unknown)}; supported: {', '.join(known)}")
        data = deep_merge(data, base)
        data = deep_merge(data, _provider_override(overrides.get(name) or {}))
        stage_overrides = deep_merge(stage_overrides, layer.get("stages") or {})
    data.setdefault("provider", {})["name"] = name

    effective_stage = stage or data["provider"].get("stage") or "dev"
    stage_override = stage_overrides.get(effective_stage) or {}
    data = deep_merge(data, stage_override)
    # A stage may name a cloud again (`stages.prod.providers.onprem`) so a later
    # stage value, such as a remote state backend, can be replaced for one provider.
    stage_providers = stage_override.get("providers") if isinstance(stage_override, dict) else None
    if isinstance(stage_providers, dict):
        unknown = set(stage_providers) - set(known)
        if unknown:
            raise ConfigError(
                f"`stages.{effective_stage}.providers` has unknown keys {sorted(unknown)}; supported: {', '.join(known)}"
            )
        block = stage_providers.get(name) or {}
        if block:
            data = deep_merge(data, _provider_override(block))
        data.pop("providers", None)
    data["provider"]["stage"] = effective_stage
    if region:
        data["provider"]["region"] = region

    opts = {"stage": effective_stage, "provider": name}
    if data["provider"].get("region"):
        opts["region"] = str(data["provider"]["region"])
    return interpolate(data, opts, path.parent)


def format_validation_error(exc: ValidationError, path: Path) -> str:
    lines = [f"{path.name} is invalid:"]
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"] if p not in ("config",)) or "<root>"
        lines.append(f"  - {loc}: {err['msg']}")
    return "\n".join(lines)


def load_config(
    path: Optional[str] = None,
    *,
    provider: Optional[str] = None,
    stage: Optional[str] = None,
    region: Optional[str] = None,
    cwd: Optional[Path] = None,
) -> LoadedConfig:
    cfg_path = find_config(path, cwd)
    raw = build_raw(cfg_path, provider=provider, stage=stage, region=region)
    try:
        config = ServiceConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(format_validation_error(exc, cfg_path)) from None
    return LoadedConfig(config=config, path=cfg_path, root=cfg_path.parent.resolve(), raw=raw)
