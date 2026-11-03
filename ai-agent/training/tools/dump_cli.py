"""Walk the pskit Click CLI and write knowledge/cli.json.

Run from the repo with the project venv:

    .venv\\Scripts\\python ai-agent\\training\\tools\\dump_cli.py

The file is the source of truth for command paths, options and ``--help`` text.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# tools/ -> training/ -> ai-agent/ -> repo root
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

import click  # noqa: E402
from click.testing import CliRunner  # noqa: E402

from py_serverless_kit.cli.main import cli  # noqa: E402

OUT = ROOT / "ai-agent" / "training" / "knowledge" / "cli.json"


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    try:
        from click.core import UNSET

        if value is UNSET:
            return None
    except Exception:
        pass
    return str(value)


def _type_name(param: click.Parameter) -> str:
    kind = param.type
    if isinstance(kind, click.Choice):
        return "choice"
    if isinstance(kind, click.IntRange):
        return "int_range"
    if isinstance(kind, click.FloatRange):
        return "float_range"
    if isinstance(kind, click.Path):
        return "path"
    if isinstance(kind, click.Tuple):
        return "tuple"
    name = type(kind).__name__
    return {
        "StringParamType": "string",
        "IntParamType": "int",
        "FloatParamType": "float",
        "BoolParamType": "bool",
        "UUIDParameterType": "uuid",
        "UnprocessedParamType": "unprocessed",
    }.get(name, name)


def _param(param: click.Parameter) -> dict[str, Any]:
    is_argument = isinstance(param, click.Argument)
    flags = [] if is_argument else list(param.opts) + list(param.secondary_opts)
    item: dict[str, Any] = {
        "name": param.name,
        "param_type": "argument" if is_argument else "option",
        "flags": flags,
        "type": _type_name(param),
        "required": bool(param.required),
        "default": _jsonable(param.default),
        "help": (getattr(param, "help", None) or "").strip(),
        "is_flag": bool(getattr(param, "is_flag", False)),
        "multiple": bool(getattr(param, "multiple", False)),
        "nargs": getattr(param, "nargs", 1),
        "hidden": bool(getattr(param, "hidden", False)),
    }
    envvar = getattr(param, "envvar", None)
    if envvar:
        item["envvar"] = envvar if isinstance(envvar, str) else list(envvar)
    kind = param.type
    if isinstance(kind, click.Choice):
        item["choices"] = [str(choice) for choice in kind.choices]
    if isinstance(kind, (click.IntRange, click.FloatRange)):
        item["min"] = kind.min
        item["max"] = kind.max
    if isinstance(kind, click.Path):
        item["path"] = {
            "exists": bool(kind.exists),
            "file_okay": bool(kind.file_okay),
            "dir_okay": bool(kind.dir_okay),
        }
    if is_argument:
        item.pop("is_flag", None)
    return item


def _help_output(parts: list[str]) -> str:
    runner = CliRunner()
    result = runner.invoke(cli, parts + ["--help"])
    text = result.output or ""
    if result.exit_code not in (0, None) and "Usage:" not in text:
        text = (text + f"\n[dump_cli: exit {result.exit_code}]").strip()
    return text.replace("\r\n", "\n")


def _walk(cmd: click.Command, parts: list[str], parent: click.Context | None) -> list[dict[str, Any]]:
    info_name = "pskit" if not parts else parts[-1]
    ctx = click.Context(cmd, info_name=info_name, parent=parent)
    full = "pskit" if not parts else "pskit " + " ".join(parts)
    short = ""
    try:
        short = cmd.get_short_help_str(limit=200)
    except Exception:
        short = (cmd.short_help or "").strip()
    options = []
    arguments = []
    for param in cmd.params:
        described = _param(param)
        if described["param_type"] == "argument":
            arguments.append(described)
        else:
            options.append(described)
    record: dict[str, Any] = {
        "name": full,
        "parts": parts,
        "is_group": isinstance(cmd, click.Group),
        "hidden": bool(getattr(cmd, "hidden", False)),
        "short_help": short,
        "help": (cmd.help or "").strip(),
        "help_output": _help_output(parts),
        "arguments": arguments,
        "options": options,
    }
    found = [record]
    if isinstance(cmd, click.Group):
        for sub_name in cmd.list_commands(ctx):
            sub = cmd.get_command(ctx, sub_name)
            if sub is None:
                continue
            found.extend(_walk(sub, parts + [sub_name], ctx))
    return found


def main() -> None:
    records = _walk(cli, [], None)
    leaves = [item for item in records if not item["is_group"]]
    groups = [item for item in records if item["is_group"]]
    payload = {
        "prog": "pskit",
        "count_all": len(records),
        "count_commands": len(leaves),
        "count_groups": len(groups),
        "commands": records,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes((json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    print(f"wrote {OUT}")
    print(f"groups={len(groups)} commands={len(leaves)} all={len(records)}")
    for item in records:
        kind = "group" if item["is_group"] else "cmd"
        print(f"  {kind:5} {item['name']}")


if __name__ == "__main__":
    main()
