"""Handler stubs for Node.js services (TypeScript, ESM or CommonJS JavaScript).

The Python counterpart is ``project.ensure_handler``; the API used here is the
``pskit`` package vendored into every Node.js bundle (deploy_docs/NODE_RUNTIME.md).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# TypeScript; JavaScript is derived by dropping the annotations listed in _TS_ONLY.
NODE_TEMPLATES: Dict[str, str] = {
    "http": """
/** HTTP handler: event.http has method, path, query, pathParams, headers and json(). */
export async function __FUNC__(event: Event, ctx: Context) {
  const name = event.http?.query.name ?? "world";
  return { message: `Hello, ${name}!` };
}
""",
    "schedule": """
/** Scheduled job: event.data is the schedule's `input`. */
export async function __FUNC__(event: Event, ctx: Context) {
  ctx.logger.info("tick", { input: event.data });
}
""",
    "queue": """
/** Queue consumer: failed records are retried, then dead-lettered. */
export async function __FUNC__(event: Event, ctx: Context): Promise<BatchResult> {
  const result = new BatchResult();
  for (const record of event.records) {
    try {
      ctx.logger.info("message", { id: record.id, body: record.text() });
    } catch (err) {
      result.fail(record); // retry only this record
    }
  }
  return result;
}
""",
    "storage": """
/** Storage trigger: one record per created / deleted object. */
export async function __FUNC__(event: Event, ctx: Context) {
  for (const record of event.records) {
    ctx.logger.info("object", { bucket: record.bucket, key: record.key, action: record.action });
  }
}
""",
    "topic": """
/** Topic subscriber: record.attributes holds the message attributes. */
export async function __FUNC__(event: Event, ctx: Context) {
  for (const record of event.records) {
    ctx.logger.info("published", { id: record.id, body: record.text() });
  }
}
""",
    "invoke": """
/** Called with invoke("<name>", data) or from a workflow: event.data is the payload. */
export async function __FUNC__(event: Event, ctx: Context) {
  return { ok: true, input: event.data };
}
""",
    "workflow": """
/** Workflow task: return the state's output (it becomes the next state's input). */
export async function __FUNC__(event: Event, ctx: Context) {
  return { ...(event.data ?? {}), __FUNC__: "done" };
}
""",
}
_TS_ONLY = ((": Promise<BatchResult>", ""), ("(event: Event, ctx: Context)", "(event, ctx)"))
_EXTS = (".ts", ".mts", ".js", ".mjs", ".cjs")
_HANDLER_RE = re.compile(r"^([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)[.:]([A-Za-z_$][\w$]*)$")


def _template(kind: str, func: str, flavour: str) -> str:
    text = NODE_TEMPLATES.get(kind, NODE_TEMPLATES["invoke"]).replace("__FUNC__", func).lstrip("\n")
    if flavour == "ts":
        return text
    for a, b in _TS_ONLY:
        text = text.replace(a, b)
    if flavour == "cjs":
        text = text.replace(f"export async function {func}(", f"exports.{func} = async function {func}(", 1)
        text = text.rstrip("\n") + ";\n"
    return text


def _flavour(path: Path, text: str, package_type: str) -> str:
    if path.suffix in (".ts", ".mts"):
        return "ts"
    if path.suffix == ".mjs" or re.search(r"^\s*(import|export)\s", text, re.M):
        return "esm"
    if path.suffix == ".cjs" or re.search(r"\brequire\(|\bmodule\.exports\b|\bexports\.", text):
        return "cjs"
    return "esm" if package_type == "module" else "cjs"


def _find(base: Path, parts: List[str], typescript: bool) -> Path:
    stem = base.joinpath(*parts)
    for ext in _EXTS:
        if stem.with_suffix(ext).is_file():
            return stem.with_suffix(ext)
    for ext in _EXTS:
        if (stem / f"index{ext}").is_file():
            return stem / f"index{ext}"
    return stem.with_suffix(".ts" if typescript else ".js")


def defines(text: str, func: str) -> Optional[int]:
    """1-based line where ``func`` is exported, if it is."""
    name = re.escape(func)
    pattern = re.compile(
        rf"^\s*(export\s+(async\s+)?function\s*\*?\s*{name}\b|export\s+(const|let|var)\s+{name}\b|"
        rf"(module\.)?exports\.{name}\s*=|export\s*\{{[^}}]*\b{name}\b)",
        re.M,
    )
    match = pattern.search(text)
    return text.count("\n", 0, match.start()) + 1 if match else None


def _imports(flavour: str, names: List[str]) -> str:
    if flavour == "ts":
        types = [n for n in names if n in ("Event", "Context")]
        values = [n for n in names if n not in ("Event", "Context")]
        out = []
        if types:
            out.append(f'import type {{ {", ".join(types)} }} from "pskit";')
        if values:
            out.append(f'import {{ {", ".join(values)} }} from "pskit";')
        return "\n".join(out)
    values = [n for n in names if n not in ("Event", "Context")]
    if not values:
        return ""
    if flavour == "esm":
        return f'import {{ {", ".join(values)} }} from "pskit";'
    return f'const {{ {", ".join(values)} }} = require("pskit");'


def ensure_node_handler(
    source: Path, root: Path, handler: str, kind: str, typescript: bool, package_type: str = "commonjs"
) -> Tuple[Path, bool, int]:
    """Append a stub for ``handler`` unless it is already exported. Returns (path, created, line)."""
    match = _HANDLER_RE.match(handler.strip())
    if not match:
        raise ValueError(f"handler {handler!r} must look like 'src.handlers.function'")
    module, func = match.group(1), match.group(2)
    path = _find(source, module.split("."), typescript)
    text = path.read_text("utf-8") if path.is_file() else ""
    line = defines(text, func)
    if line is not None:
        return path, False, line
    flavour = _flavour(path, text, package_type)
    needed = ["Event", "Context"] + (["BatchResult"] if kind == "queue" else [])
    have = set(re.findall(r"\b(Event|Context|BatchResult)\b", "\n".join(ln for ln in text.splitlines() if "pskit" in ln)))
    header = _imports(flavour, [n for n in needed if n not in have])
    if not text:
        intro = "// Handlers created with pskit studio. This code runs unchanged on every supported cloud."
        body = intro + "\n" + (header + "\n" if header else "")
    elif header:
        lines = text.splitlines()
        # After the leading comments, "use strict" and imports (not after trailing blank lines).
        insert_at = 0
        for i, ln in enumerate(lines):
            s = ln.strip()
            header_line = s.startswith(("import ", "//", "'use strict'", '"use strict"')) or (
                s.startswith("const ") and "require(" in s
            )
            if header_line:
                insert_at = i + 1
            elif s:
                break
        lines[insert_at:insert_at] = header.splitlines()
        body = "\n".join(lines).rstrip("\n") + "\n"
    else:
        body = text.rstrip("\n") + "\n"
    body += "\n" + _template(kind, func, flavour)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body.encode("utf-8"))
    return path, True, defines(body, func) or 1


__all__ = ["NODE_TEMPLATES", "defines", "ensure_node_handler"]
