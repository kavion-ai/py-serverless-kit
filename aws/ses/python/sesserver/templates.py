"""The template language: the part of Handlebars that SES templates use.

``{{name}}``, ``{{a.b}}``, ``{{this}}``, ``{{@index}}`` (HTML-escaped in the HTML part), ``{{{raw}}}`` (never
escaped), ``{{#if x}}...{{else}}...{{/if}}``, ``{{#unless x}}``, ``{{#each list}}...{{else}}...{{/each}}``,
``{{#with obj}}``, ``{{! comment }}`` / ``{{!-- comment --}}``. A name that the current object does not have is
looked up in the enclosing ones; a missing value renders as nothing. Falsy (``#if``): missing, null, false, 0, ""
and []. The Node.js server's ``lib/templates.js`` implements the same rules.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from .errors import ApiError

_TOKEN = re.compile(r"\{\{\{\s*(.*?)\s*\}\}\}|\{\{!--.*?--\}\}|\{\{(.*?)\}\}", re.S)
_PATH = re.compile(r"^(@index|@first|@last|@key|this|[A-Za-z_$][\w$-]*)(\.[A-Za-z_$][\w$-]*|\.\d+)*$|^\.$")
_ESCAPE = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#x27;", "`": "&#x60;", "=": "&#x3D;"}
_BLOCKS = ("if", "unless", "each", "with")


class TemplateError(ApiError):
    def __init__(self, message: str) -> None:
        super().__init__("BadRequestException", message, 400, "InvalidTemplate")


Node = Tuple[Any, ...]  # ("text", s) | ("var", path, escape) | ("block", kind, path, body, else_body)


def parse(text: str) -> List[Node]:
    root: List[Node] = []
    stack: List[Tuple[str, str, List[Node], Optional[List[Node]]]] = []
    current = root
    pos = 0
    for m in _TOKEN.finditer(text or ""):
        if m.start() > pos:
            current.append(("text", text[pos:m.start()]))
        pos = m.end()
        raw, inner = m.group(1), m.group(2)
        if raw is not None:
            current.append(("var", _path(raw), False))
            continue
        if inner is None:  # {{!-- --}}
            continue
        inner = inner.strip()
        if inner.startswith("!"):
            continue
        if inner.startswith("#"):
            kind, _sp, arg = inner[1:].strip().partition(" ")
            if kind not in _BLOCKS:
                raise TemplateError(f"Unsupported block helper {{{{#{kind}}}}}.")
            body: List[Node] = []
            stack.append((kind, _path(arg.strip()), body, None))
            current = body
        elif inner == "else":
            if not stack or stack[-1][3] is not None:
                raise TemplateError("{{else}} outside a block.")
            kind, path, body, _else = stack[-1]
            stack[-1] = (kind, path, body, [])
            current = stack[-1][3]  # type: ignore[assignment]
        elif inner.startswith("/"):
            kind = inner[1:].strip()
            if not stack or stack[-1][0] != kind:
                raise TemplateError(f"{{{{/{kind}}}}} does not close an open block.")
            kind, path, body, else_body = stack.pop()
            current = stack[-1][3] if stack and stack[-1][3] is not None else (stack[-1][2] if stack else root)
            current.append(("block", kind, path, body, else_body or []))
        else:
            current.append(("var", _path(inner), True))
    if stack:
        raise TemplateError(f"{{{{#{stack[-1][0]}}}}} is not closed.")
    if pos < len(text or ""):
        current.append(("text", text[pos:]))
    return root


def _path(expr: str) -> List[str]:
    if not expr or not _PATH.match(expr):
        raise TemplateError(f"Invalid expression {{{{{expr}}}}}.")
    if expr == ".":
        return ["this"]
    return expr.split(".")


def _lookup(scopes: List[Dict[str, Any]], path: List[str]) -> Any:
    head, rest = path[0], path[1:]
    if head == "this":
        value = scopes[-1].get("this")
    elif head.startswith("@"):
        value = scopes[-1].get(head)
    else:
        value = None
        for scope in reversed(scopes):
            ctx = scope.get("this")
            if isinstance(ctx, dict) and head in ctx:
                value = ctx[head]
                break
    for part in rest:
        if isinstance(value, dict):
            value = value.get(part)
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            return None
    return value


def _truthy(value: Any) -> bool:
    if isinstance(value, list):
        return bool(value)
    return value not in (None, False, 0, "")


def to_text(value: Any) -> str:
    """A value as JavaScript prints it, so both servers render the same text."""
    if value is None:
        return ""
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, float):
        if value != value:
            return "NaN"
        return str(int(value)) if value.is_integer() and abs(value) < 1e21 else repr(value)
    if isinstance(value, list):
        return ",".join(to_text(v) for v in value)
    if isinstance(value, dict):
        return "[object Object]"
    return str(value)


def _render(nodes: List[Node], scopes: List[Dict[str, Any]], html: bool, out: List[str]) -> None:
    for node in nodes:
        if node[0] == "text":
            out.append(node[1])
        elif node[0] == "var":
            text = to_text(_lookup(scopes, node[1]))
            out.append("".join(_ESCAPE.get(c, c) for c in text) if (node[2] and html) else text)
        else:
            _kind, kind, path, body, else_body = node
            value = _lookup(scopes, path)
            if kind == "if":
                _render(body if _truthy(value) else else_body, scopes, html, out)
            elif kind == "unless":
                _render(else_body if _truthy(value) else body, scopes, html, out)
            elif kind == "with":
                if _truthy(value):
                    _render(body, scopes + [{"this": value}], html, out)
                else:
                    _render(else_body, scopes, html, out)
            else:  # each
                items: List[Tuple[Any, Any]] = []
                if isinstance(value, list):
                    items = list(enumerate(value))
                elif isinstance(value, dict):
                    items = list(value.items())
                if not items:
                    _render(else_body, scopes, html, out)
                for i, (key, item) in enumerate(items):
                    scope = {"this": item, "@index": i, "@first": i == 0, "@last": i == len(items) - 1, "@key": key}
                    _render(body, scopes + [scope], html, out)


def render(text: Optional[str], data: Dict[str, Any], html: bool = False) -> str:
    if not text:
        return ""
    out: List[str] = []
    _render(parse(text), [{"this": data}], html, out)
    return "".join(out)


def data_of(text: Any) -> Dict[str, Any]:
    """The template data (a JSON object in a string, as SES takes it)."""
    if isinstance(text, dict):
        return text
    try:
        data = json.loads(text or "{}")
    except (TypeError, ValueError):
        raise ApiError("BadRequestException", "TemplateData is not valid JSON.", 400, "InvalidRenderingParameter") \
            from None
    if not isinstance(data, dict):
        raise ApiError("BadRequestException", "TemplateData must be a JSON object.", 400, "InvalidRenderingParameter")
    return data


def check(subject: Optional[str], text: Optional[str], html: Optional[str]) -> None:
    """Parse the three parts (an error names what is wrong)."""
    for part in (subject, text, html):
        parse(part or "")
