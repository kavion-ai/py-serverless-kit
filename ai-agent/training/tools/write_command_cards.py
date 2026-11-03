"""Write one command card per Click node from knowledge/cli.json.

Option lines, defaults and examples come from that dump and from the command
docstring. Safety lines come from the callback source in cli/main.py.
Studio paths are only the ones listed in STUDIO, whose labels were read in
dashboard-ui/src/studio.
"""

from __future__ import annotations

import inspect
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
KNOW = ROOT / "ai-agent" / "training" / "knowledge"
CARDS = KNOW / "cards" / "command"
CLI_JSON = KNOW / "cli.json"

from py_serverless_kit.cli.main import cli  # noqa: E402

# Labels confirmed in dashboard-ui/src/studio (see the view files).
STUDIO = {
    "pskit validate": "Deploy > Validate",
    "pskit package": "Deploy > Package",
    "pskit plan": "Deploy > Plan",
    "pskit deploy": "Deploy > Deploy",
    "pskit info": "Deploy > Info",
    "pskit remove": "Deploy > Remove",
    "pskit invoke": "Test > Run locally",
    "pskit trigger": "Test > Send to",
    "pskit workflow run": "Deploy > Run",
    "pskit doctor": "Setup & credentials > Check again",
    "pskit logs": "Logs > Stored logs",
    "pskit function split": "Functions > Own folder",
    "pskit settings export": "Setup & credentials > Export settings",
    "pskit settings import": "Setup & credentials > Import into this project",
    "pskit resources usage": "Resources > How to use",
    "pskit resources send": "Resources > Test",
    "pskit resources data": "Resources > Data",
    "pskit resources delete": "Resources > Delete",
    "pskit resources list": "Resources > Load",
    "pskit cluster create": "Scaling cluster > + New cluster",
    "pskit cluster join": "Scaling cluster > + Join server",
    "pskit cluster scale": "Scaling cluster > Scale",
    "pskit cluster check": "Scaling cluster > Check & alert",
    "pskit firewall": "Deploy > Firewall",
    "pskit lb create": "Load balancers > + Create load balancer",
    "pskit lb update": "Load balancers > Update",
    "pskit lb attach": "Load balancers > + Attach cluster",
    "pskit lb detach": "Load balancers > Detach",
    "pskit lb sync": "Load balancers > Sync",
    "pskit lb logs": "Load balancers > Logs",
    "pskit lb remove": "Load balancers > Remove",
    "pskit lb forget": "Load balancers > Forget",
    "pskit lb algorithms": "Load balancers > How it spreads requests",
}

ONPREM_PREFIXES = (
    "pskit cluster",
    "pskit lb",
    "pskit firewall",
    "pskit resources onprem",
    "pskit client",
)

# Groups copied from ROOT_EPILOG in src/py_serverless_kit/cli/main.py.
EPILOG_RELATED = {
    "pskit init": ["pskit studio", "pskit doctor"],
    "pskit studio": ["pskit init", "pskit doctor"],
    "pskit doctor": ["pskit init", "pskit studio"],
    "pskit dev": ["pskit invoke", "pskit validate"],
    "pskit invoke": ["pskit dev", "pskit validate"],
    "pskit validate": ["pskit dev", "pskit invoke"],
    "pskit package": ["pskit plan", "pskit deploy", "pskit remove"],
    "pskit plan": ["pskit package", "pskit deploy", "pskit tf"],
    "pskit deploy": ["pskit package", "pskit plan", "pskit info", "pskit remove", "pskit tf"],
    "pskit info": ["pskit deploy", "pskit dashboard"],
    "pskit remove": ["pskit deploy", "pskit plan"],
    "pskit tf": ["pskit plan", "pskit deploy"],
    "pskit logs": ["pskit trigger", "pskit dashboard"],
    "pskit trigger": ["pskit logs", "pskit invoke"],
    "pskit dashboard": ["pskit info", "pskit studio"],
    "pskit providers": ["pskit doctor", "pskit validate"],
}

IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
DOC_NETS = ((192, 0, 2), (198, 51, 100), (203, 0, 113))


def scrub(text: str) -> str:
    """Replace addresses that are not documentation-range examples."""

    def repl(match: re.Match) -> str:
        ip = match.group(0)
        parts = ip.split(".")
        try:
            nums = tuple(int(part) for part in parts)
        except ValueError:
            return "192.0.2.10"
        if any(n > 255 for n in nums):
            return "192.0.2.10"
        if nums[0] == 127 or nums == (0, 0, 0, 0) or nums[:3] in DOC_NETS:
            return ip
        return "192.0.2.10"

    text = IPV4.sub(repl, text)
    text = text.replace("azureuser@", "deploy@").replace("ubuntu@", "deploy@").replace("root@", "deploy@")
    return text


def card_id(name: str) -> str:
    parts = name.split()[1:]
    return "cmd-pskit" if not parts else "cmd-" + "-".join(parts)


def words(text: str) -> int:
    return len(re.findall(r"\S+", text))


def clean_help(text: str) -> str:
    text = text.replace("\b", "")
    lines = [re.sub(r"^\s{0,4}", "", line).rstrip() for line in text.splitlines()]
    return "\n".join(lines).strip()


def callbacks() -> dict[str, object]:
    found: dict[str, object] = {}

    def walk(cmd, parts: list[str]) -> None:
        name = "pskit" if not parts else "pskit " + " ".join(parts)
        if cmd.callback is not None:
            found[name] = inspect.unwrap(cmd.callback)
        if hasattr(cmd, "list_commands"):
            ctx = None
            import click

            ctx = click.Context(cmd, info_name=parts[-1] if parts else "pskit")
            for sub_name in cmd.list_commands(ctx):
                sub = cmd.get_command(ctx, sub_name)
                if sub is not None:
                    walk(sub, parts + [sub_name])

    walk(cli, [])
    return found


def safety_lines(name: str, source: str, options: list[dict]) -> list[str]:
    lines = [f"Safety: callback for `{name}` in `src/py_serverless_kit/cli/main.py`."]
    found = []
    if "click.confirm" in source:
        found.append("The function calls `click.confirm`.")
        prompts = re.findall(r"click\.confirm\(\s*f?([\"'])(.{0,200}?)\1", source)
        if prompts:
            quote = prompts[0][1].replace("\n", " ")
            found.append(f"Prompt text starts: {quote}")
    if ".deploy(" in source:
        found.append("The function calls `.deploy(`. The command help describes terraform apply, so this changes the selected stage.")
    if ".plan(" in source:
        found.append("The function calls `.plan(`. The command help describes a terraform plan.")
    if ".remove(" in source:
        found.append("The function calls `.remove(`.")
    if ".package(" in source or "skip_deps" in source and "package" in name:
        if ".package(" in source:
            found.append("The function calls `.package(`.")
    for opt in options:
        help_text = opt.get("help") or ""
        flags = "/".join(opt.get("flags") or [])
        if "do not ask" in help_text.lower() or "don't ask" in help_text.lower():
            found.append(f"Option `{flags}`: {help_text}")
        if opt.get("name") == "confirm":
            found.append(f"Option `{flags}`: {help_text}")
    if not found:
        found.append(
            "This function body has no `click.confirm`, `.deploy(`, `.plan(`, or `.remove(`. "
            "That only describes this function. The help text says what the command does."
        )
    lines.extend(f"- {item}" for item in found)
    return lines


def examples_from(help_text: str, name: str) -> list[tuple[str, str]]:
    rows = []
    for line in clean_help(help_text).splitlines():
        stripped = line.strip()
        if not stripped.startswith("pskit "):
            continue
        comment = ""
        command = stripped
        if " #" in stripped:
            command, comment = stripped.split(" #", 1)
            command = command.strip()
            comment = comment.strip()
        if command.startswith(name):
            rows.append((command, comment))
    return rows


def option_line(opt: dict, limit: int = 0) -> str:
    flags = "/".join(opt.get("flags") or []) or opt.get("name") or "option"
    bits = []
    if opt.get("is_flag"):
        bits.append("flag")
    else:
        bits.append(opt.get("type") or "string")
    if opt.get("choices"):
        bits.append("choices " + ", ".join(opt["choices"]))
    if opt.get("required"):
        bits.append("required")
    default = opt.get("default")
    if opt.get("is_flag"):
        bits.append("default off" if default in (False, None) else f"default {default}")
    elif default not in (None, ""):
        bits.append(f"default {default}")
    if opt.get("multiple"):
        bits.append("repeatable")
    help_text = (opt.get("help") or "").strip() or "(no help text)"
    if limit and len(help_text) > limit:
        help_text = help_text[: limit - 1].rstrip() + "…"
    return f"- `{flags}` ({'; '.join(bits)}): {help_text}"


def arg_line(arg: dict) -> str:
    name = arg.get("name") or "ARG"
    req = "required" if arg.get("required") else "optional"
    return f"- `{name}` ({arg.get('type') or 'string'}, {req})"


def providers_for(name: str) -> list[str]:
    if name == "pskit" or any(name == prefix or name.startswith(prefix + " ") for prefix in ONPREM_PREFIXES):
        if name == "pskit":
            return []
        return ["onprem"]
    return []


def tags_for(name: str) -> list[str]:
    parts = name.split()[1:]
    tags = parts[:4] or ["cli"]
    if providers_for(name) == ["onprem"]:
        tags.append("onprem")
    return tags


def doc_anchor(name: str, headings: list[dict]) -> str | None:
    best = None
    for item in headings:
        if item.get("path") != "docs/cli.md":
            continue
        title = item["title"].replace("`", "")
        title = re.sub(r"\s*\[.*", "", title).strip()
        if title == name or title.startswith(name + " "):
            if best is None or len(title) > len(best[0]):
                best = (title, item["anchor"])
    if best:
        return f"docs/cli.md#{best[1]}"
    return None


def build(record: dict, source: str, siblings: list[str], doc: str | None, help_limit: int = 0) -> str:
    name = record["name"]
    short = (record.get("short_help") or "").strip()
    help_text = clean_help(record.get("help") or "")
    purpose = short or help_text.split("\n", 1)[0]
    when = [f"The command help says: {purpose}"]
    for _cmd, comment in examples_from(help_text, name)[:3]:
        if comment:
            when.append(comment[0].upper() + comment[1:] if comment else comment)
    if len(when) < 2:
        when.append("The command is defined in `src/py_serverless_kit/cli/main.py`.")
    when = when[:4]

    if record.get("is_group"):
        usage = name + " COMMAND"
    else:
        usage = name + " [OPTIONS]"
        if record.get("arguments"):
            rendered = []
            for arg in record["arguments"]:
                token = (arg.get("name") or "ARG").upper()
                if not arg.get("required"):
                    token = f"[{token}]"
                rendered.append(token)
            usage = name + " " + " ".join(rendered) + " [OPTIONS]"

    lines = [
        f"# {name}",
        "",
        f"Purpose: {purpose}",
        "",
        "When to use:",
    ]
    for item in when:
        lines.append(f"- {item}")
    lines += ["", "Usage:", "", "```", usage, "```", ""]
    if record.get("arguments"):
        lines.append("Arguments:")
        for arg in record["arguments"]:
            lines.append(arg_line(arg))
        lines.append("")
    lines.append("Options:")
    opts = record.get("options") or []
    if not opts:
        lines.append("- (no options)")
    else:
        for opt in opts:
            lines.append(option_line(opt, help_limit))
    lines.append("")
    samples = examples_from(help_text, name)[:4]
    lines.append("Examples:")
    if not samples:
        lines.append(f"- No example is written in this command's help. The synopsis is `{usage}`.")
    else:
        for command, comment in samples:
            lines.append("")
            lines.append("```")
            lines.append(command)
            lines.append("```")
            if comment:
                lines.append("")
                lines.append(comment)
            else:
                lines.append("")
                lines.append("Example copied from this command's help text.")
    lines += ["", f"Studio equivalent: {STUDIO.get(name, 'none')}", ""]
    related = [item for item in EPILOG_RELATED.get(name, []) if item != name]
    if not related:
        related = [item for item in siblings if item != name][:8]
    lines.append("Related: " + (", ".join(f"`{item}`" for item in related) if related else "none"))
    lines.append("")
    lines.extend(safety_lines(name, source, opts))
    sources = ["src/py_serverless_kit/cli/main.py"]
    if doc:
        sources.append(doc)
    lines += ["", "Sources: " + ", ".join(f"`{item}`" for item in sources)]
    lines.append("")
    text = "\n".join(lines)
    if words(text) < 150:
        extra = [
            "",
            "Help text from the command (click docstring, with the `\\b` marker removed):",
            "",
            help_text or "(empty help)",
            "",
        ]
        child_names = [item for item in siblings if item != name]
        if record.get("is_group") and child_names:
            extra.append("Subcommands: " + ", ".join(f"`{item}`" for item in child_names) + ".")
            extra.append("")
        text = text.rstrip() + "\n" + "\n".join(extra)
    return text


def expand_short(text: str, record: dict, siblings: list[str], by_name: dict[str, dict]) -> str:
    """Add dump facts until a short card reaches 150 words. Stop before 500."""
    if words(text) >= 150:
        return text
    name = record["name"]
    extra = [
        "",
        (
            f"cli.json lists {len(record.get('options') or [])} options and "
            f"{len(record.get('arguments') or [])} arguments for `{name}`."
        ),
        "Every option line above is copied from that dump (flag, Click type, default, and help).",
    ]

    def joined() -> str:
        return text.rstrip() + "\n" + "\n".join(extra) + "\n"

    if words(joined()) < 150:
        for sib in siblings:
            if sib == name:
                continue
            short = ((by_name.get(sib) or {}).get("short_help") or "").strip()
            if not short:
                continue
            extra.append(f"Subcommand `{sib}` short help: {short}")
            if words(joined()) >= 155:
                break
    if words(joined()) < 150:
        for sib in siblings:
            if sib == name:
                continue
            for opt in (by_name.get(sib) or {}).get("options") or []:
                extra.append(option_line(opt, 80))
                if words(joined()) >= 155:
                    return joined()
    return joined()


def render(record: dict, source: str, siblings: list[str], doc: str | None, by_name: dict[str, dict]) -> str:
    """Build one card. Long option lists keep every option and shorten help text."""

    def once(limit: int) -> tuple[str, str]:
        raw = expand_short(build(record, source, siblings, doc, help_limit=limit), record, siblings, by_name)
        return raw, scrub(raw)

    raw, cleaned = once(0)
    changed = cleaned != raw
    ceiling = 450 if changed else 500
    if words(cleaned) > ceiling:
        for limit in (140, 100, 72, 52, 36, 24):
            raw, cleaned = once(limit)
            changed = cleaned != raw
            ceiling = 450 if changed else 500
            if words(cleaned) <= ceiling:
                break
    if changed:
        note = (
            "\nAn address or login copied from the command help was rewritten in this card. "
            "Addresses use 192.0.2.0/24, a documentation range. The login in those examples is deploy.\n"
        )
        if words(cleaned) + len(note.split()) <= 500:
            cleaned = cleaned.rstrip() + "\n" + note
    return cleaned


def heading_rows() -> list[dict]:
    data = json.loads((KNOW / "docs_headings.json").read_text(encoding="utf-8"))
    rows = []
    for item in data["files"]:
        for heading in item["headings"]:
            rows.append({"path": item["path"], "title": heading["title"], "anchor": heading["anchor"]})
    return rows


def main() -> None:
    data = json.loads(CLI_JSON.read_text(encoding="utf-8"))
    records = data["commands"]
    by_name = {item["name"]: item for item in records}
    cbs = callbacks()
    headings = heading_rows()
    # parent -> children names
    children: dict[str, list[str]] = {}
    for item in records:
        parts = item["parts"]
        parent = "pskit" if len(parts) <= 1 else "pskit " + " ".join(parts[:-1])
        if not parts:
            parent = ""
        children.setdefault(parent, []).append(item["name"])

    CARDS.mkdir(parents=True, exist_ok=True)
    jsonl_rows = []
    lengths = []
    for record in records:
        name = record["name"]
        cb = cbs.get(name)
        source = inspect.getsource(cb) if cb is not None else ""
        parent_parts = record["parts"][:-1]
        parent = "pskit" if parent_parts or record["parts"] else ""
        if record["parts"]:
            parent = "pskit" if len(record["parts"]) == 1 else "pskit " + " ".join(record["parts"][:-1])
        else:
            parent = ""
        siblings = children.get(parent, [])
        if record["is_group"]:
            siblings = children.get(name, siblings)
        doc = doc_anchor(name, headings)
        text = render(record, source, siblings, doc, by_name)
        cid = card_id(name)
        path = CARDS / f"{cid}.md"
        path.write_bytes(text.encode("utf-8"))
        sources = ["src/py_serverless_kit/cli/main.py"]
        if doc:
            sources.append(doc)
        jsonl_rows.append(
            {
                "id": cid,
                "kind": "command",
                "title": name,
                "tags": tags_for(name),
                "providers": providers_for(name),
                "text": text,
                "sources": sources,
            }
        )
        lengths.append((words(text), cid))
    out = KNOW / "cards.jsonl"
    if out.is_file():
        for line in out.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("kind") != "command":
                jsonl_rows.append(row)
    jsonl_rows.sort(key=lambda row: row["id"])
    payload = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in jsonl_rows)
    out.write_bytes(payload.encode("utf-8"))
    lengths.sort()
    print(f"cards={len(jsonl_rows)} shortest={lengths[0]} longest={lengths[-1]}")
    short = [item for item in lengths if item[0] < 150]
    long = [item for item in lengths if item[0] > 500]
    print(f"under 150: {len(short)} over 500: {len(long)}")
    for item in short[:10]:
        print(" short", item)
    for item in long[:10]:
        print(" long", item)


if __name__ == "__main__":
    main()
