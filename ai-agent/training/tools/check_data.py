"""Checker for Hana's stage-2 task dataset (12-task-dataset-prompt.md section 6).

    python tools/check_data.py                       # every task file in data/raw (not k_*.jsonl)
    python tools/check_data.py data/raw/a_qa.jsonl   # one or more files

Errors must be fixed (or the line deleted) before continuing; warnings are worth a look. Checks per line:
  JSON + required fields + meta values; role order (system, user, then assistant/tool, ends with assistant);
  system prompt == SYSTEM_PROMPT + a valid Environment line; one tool call per assistant message, each id answered by
  exactly one tool message; tool names and argument names; length < 3000 tokens (chars / 3.5);
  B/C/D: last validate/set_config/invoke output succeeds; A: first call is search_docs; changes come after
  propose_plan and are followed by validate; mode=auto -> auto_approved; search_docs excerpts are verbatim from the
  cited file (or card); `pskit ...` commands and flags exist (knowledge/cli.json); YAML keys in answers exist in
  config/schema.py; studio paths start with a NAV label; citations [path#anchor] exist; one-way how-to answers;
  no duplicate user messages; no secrets / non-documentation IPs; Hana never names a base model or model company.
"""

from __future__ import annotations

import json
import re
import shlex
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from task_common import (  # noqa: E402
    CATEGORIES, LEGACY_MAX_ID, MODES, STAGE2_PROVIDERS, NAV_LABELS, PAGES, PERSONAS, PROVIDERS, STAGES, SYSTEM_PROMPT, TOOL_ARGS,
)

TRAIN = Path(__file__).resolve().parents[1]
REPO = TRAIN.parents[1]
RAW = TRAIN / "data" / "raw"
CLI_JSON = TRAIN / "knowledge" / "cli.json"
HEADINGS = TRAIN / "knowledge" / "docs_headings.json"
CARDS = TRAIN / "knowledge" / "cards.jsonl"
MAX_TOKENS = 3000
CHECKED_CATS = {"b_build", "c_fix", "d_debug"}
ENV_RE = re.compile(r"^Environment: provider=(\S+) stage=(\S+) mode=(\S+) page=(.+)$")
DOC_IP = re.compile(r"^(127\.|0\.0\.0\.0|192\.0\.2\.|198\.51\.100\.|203\.0\.113\.|255\.)")
PRIVATE_IP = re.compile(r"^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)")
MODEL_NAMES = re.compile(r"\b(Claude|Anthropic|OpenAI|ChatGPT|GPT-?\d|Qwen|Llama|Mistral|Gemini|DeepSeek|Phi-\d|Gemma)\b",
                         re.I)


# ------------------------------------------------------------------ reference data


def load_cli() -> Dict[Tuple[str, ...], Set[str]]:
    data = json.loads(CLI_JSON.read_text(encoding="utf-8"))
    out: Dict[Tuple[str, ...], Set[str]] = {}
    for c in data["commands"]:
        flags = {"-h", "--help"}
        for o in c.get("options", []):
            flags.update(o.get("flags", []))
            flags.update(o.get("secondary_flags", []) or [])
        if not c["parts"]:
            flags.add("--version")
        out[tuple(c["parts"])] = flags
    return out


def load_anchors() -> Dict[str, Set[str]]:
    data = json.loads(HEADINGS.read_text(encoding="utf-8"))
    return {f["path"]: {h["anchor"] for h in f.get("headings", [])} for f in data["files"]}


def load_cards() -> Dict[str, str]:
    out = {}
    if CARDS.exists():
        for line in CARDS.read_text(encoding="utf-8").splitlines():
            c = json.loads(line)
            out[c["id"]] = c["text"]
    return out


class Schema:
    """Allowed pskit.yml keys, walked from the pydantic models in config/schema.py."""

    FREE = {"environment", "tags", "options", "custom", "connection", "authorizer", "filter", "extra", "config",
            "input", "result", "hooks"}

    def __init__(self) -> None:
        sys.path.insert(0, str(REPO / "src"))
        from py_serverless_kit.config import schema as s  # noqa: WPS433

        self.s = s
        self.events = dict(s._EVENT_MODELS)

    def fields(self, model) -> Dict[str, Any]:
        return dict(model.model_fields)

    def check(self, node: Any, model, where: str, bad: List[str]) -> None:
        s = self.s
        if not isinstance(node, dict):
            return
        fields = self.fields(model)
        extra = set()
        if model is s.ServiceConfig:
            extra = {"providers", "stages", "extends"}
        for key, val in node.items():
            k = str(key)
            if k not in fields and k not in extra:
                bad.append(f"{where}{k}")
                continue
            if k in self.FREE:
                continue
            self._descend(k, val, model, where + k + ".", bad)

    def _descend(self, key: str, val: Any, model, where: str, bad: List[str]) -> None:
        s = self.s
        if model is s.ServiceConfig:
            if key == "provider" and isinstance(val, dict):
                self.check(val, s.ProviderConfig, where, bad)
            elif key == "package":
                self.check(val, s.PackageConfig, where, bad)
            elif key == "functions" and isinstance(val, dict):
                for n, f in val.items():
                    self.check(f, s.FunctionConfig, f"{where}{n}.", bad)
            elif key == "workflows" and isinstance(val, dict):
                for n, w in val.items():
                    self.check(w, s.WorkflowConfig, f"{where}{n}.", bad)
            elif key == "resources" and isinstance(val, dict):
                for n, r in val.items():
                    self.check(r, s.ResourceConfig, f"{where}{n}.", bad)
            elif key in ("providers", "stages") and isinstance(val, dict):
                for n, block in val.items():
                    if isinstance(block, dict):
                        self.overlay(block, f"{where}{n}.", bad)
            return
        if model is s.FunctionConfig and key == "events" and isinstance(val, list):
            self.check_events(val, where, bad)
        elif model is s.FunctionConfig and key == "iam" or model is s.ProviderConfig and key == "iam":
            self.check(val, s.IamConfig, where, bad)
            for st in (val or {}).get("statements", []) if isinstance(val, dict) else []:
                self.check(st, s.IamStatement, where + "statements.", bad)
        elif model is s.ProviderConfig and key == "state":
            self.check(val, s.StateBackend, where, bad)
        elif model is s.ProviderConfig and key == "terraform":
            self.check(val, s.TerraformSettings, where, bad)
        elif model is s.PackageConfig and key == "node":
            self.check(val, s.NodePackageConfig, where, bad)
        elif key == "states" and isinstance(val, dict):
            for n, st in val.items():
                self.check(st, s.WorkflowState, f"{where}{n}.", bad)
        elif key in ("retry", "catch") and isinstance(val, list):
            for r in val:
                self.check(r, s.RetryRule if key == "retry" else s.CatchRule, where, bad)
        elif key in ("branches",) and isinstance(val, list):
            for b in val:
                self.check(b, s.WorkflowDefinition, where, bad)
        elif key == "iterator":
            self.check(val, s.WorkflowDefinition, where, bad)

    def overlay(self, block: Dict[str, Any], where: str, bad: List[str]) -> None:
        s = self.s
        top = set(self.fields(s.ServiceConfig)) | {"providers"}
        prov = set(self.fields(s.ProviderConfig))
        for k, v in block.items():
            if k in top:
                self.check({k: v}, s.ServiceConfig, where, bad)
            elif k in prov:
                self.check({k: v}, s.ProviderConfig, where + "provider.", bad)
            else:
                bad.append(f"{where}{k}")

    def check_events(self, events: List[Any], where: str, bad: List[str]) -> None:
        for i, ev in enumerate(events):
            if not isinstance(ev, dict) or len(ev) != 1:
                bad.append(f"{where}{i} (not a single-key mapping)")
                continue
            ((kind, body),) = ev.items()
            if kind not in self.events:
                bad.append(f"{where}{i}.{kind}")
                continue
            if isinstance(body, dict):
                if kind == "http" and isinstance(body.get("cors"), dict):
                    self.check(body["cors"], self.s.CorsConfig, f"{where}{i}.http.cors.", bad)
                    body = {k: v for k, v in body.items() if k != "cors"}
                for k in body:
                    if k not in self.fields(self.events[kind]):
                        bad.append(f"{where}{i}.{kind}.{k}")

    def check_snippet(self, data: Any) -> List[str]:
        """Find the model a (possibly partial) snippet belongs to and return unknown keys."""
        s = self.s
        if isinstance(data, list):
            if all(isinstance(e, dict) and len(e) == 1 and next(iter(e)) in self.events for e in data):
                bad: List[str] = []
                self.check_events(data, "events.", bad)
                return bad
            return []
        if not isinstance(data, dict):
            return []
        top = set(map(str, data))
        root_keys = set(self.fields(s.ServiceConfig)) | {"providers", "stages", "extends"}
        if top <= root_keys and top & {"service", "provider", "functions", "workflows", "resources", "providers",
                                       "stages", "package", "custom", "hooks", "extends"}:
            bad = []
            self.check(data, s.ServiceConfig, "", bad)
            return bad
        candidates = [s.FunctionConfig, s.ProviderConfig, s.PackageConfig]
        if "type" in top:
            candidates += [s.ResourceConfig, s.WorkflowState]
        if top & {"start_at", "states"}:
            candidates.append(s.WorkflowConfig)
        best: Optional[List[str]] = None
        for model in candidates:
            bad = []
            self.check(data, model, "", bad)
            if not bad:
                return []
            if best is None or len(bad) < len(best):
                best = bad
        if set(data) <= set(self.events):
            bad = []
            self.check_events([{k: v} for k, v in data.items()], "", bad)
            return bad
        return best or []


# ------------------------------------------------------------------ checks


def ip_problems(text: str) -> Tuple[List[str], List[str]]:
    errs, warns = [], []
    for ip in re.findall(r"(?<![\d.])(\d{1,3}(?:\.\d{1,3}){3})(?![\d.])", text):
        if any(int(p) > 255 for p in ip.split(".")):
            continue
        if DOC_IP.match(ip):
            continue
        (warns if PRIVATE_IP.match(ip) else errs).append(ip)
    return errs, warns


SECRET_RES = [
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key"),
    (re.compile(r"(?i)\b\w*(password|passwd|secret|api_key|token)\w*\s*[:=]\s*['\"]?(?!\$\{|<|\*|\s|['\"]?$)([^\s'\",}]{4,})"),
     "literal secret"),
]
SECRET_OK = {"true", "false", "none", "null", "required", "generate", "secret", "string"}


def secret_problems(text: str) -> List[str]:
    found = []
    for rx, label in SECRET_RES:
        for m in rx.finditer(text):
            if label == "literal secret":
                val = m.group(2).strip("'\"").lower()
                if val in SECRET_OK or val.endswith("_env") or m.group(0).lower().split(":")[0].strip().endswith("_env"):
                    continue
            found.append(f"{label}: {m.group(0)[:60]}")
    return found


def code_blocks(text: str) -> List[Tuple[str, str]]:
    """(language, body) of every fenced block, parsed line by line so fences pair correctly."""
    blocks: List[Tuple[str, str]] = []
    lang, buf = None, []
    for line in text.splitlines():
        s = line.strip()
        if lang is None and s.startswith("```"):
            lang, buf = s[3:].strip().lower(), []
        elif lang is not None and s.startswith("```"):
            blocks.append((lang, chr(10).join(buf)))
            lang = None
        elif lang is not None:
            buf.append(line)
    return blocks


def strip_blocks(text: str) -> str:
    out, inside = [], False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            inside = not inside
            continue
        if not inside:
            out.append(line)
    return chr(10).join(out)


def pskit_commands(text: str) -> List[str]:
    cmds = []
    for lang, block in code_blocks(text):
        if lang not in ("", "bash", "sh", "shell", "powershell", "console", "text"):
            continue
        for line in block.splitlines():
            line = line.strip()
            if line.startswith("$ "):
                line = line[2:]
            if line.startswith("pskit ") or line == "pskit":
                cmds.append(line.split(" #")[0].strip())
    for inline in re.findall(r"`(pskit(?: [^`]*)?)`", strip_blocks(text)):
        cmds.append(inline.strip())
    return cmds


def check_command(cmd: str, cli: Dict[Tuple[str, ...], Set[str]]) -> Optional[str]:
    try:
        toks = shlex.split(cmd.replace("\\\n", " "), posix=True)
    except ValueError:
        toks = cmd.split()
    toks = toks[1:]
    parts: List[str] = []
    i = 0
    while i < len(toks) and tuple(parts + [toks[i]]) in cli:
        parts.append(toks[i])
        i += 1
    flags = cli.get(tuple(parts))
    if flags is None:
        return f"unknown command: pskit {' '.join(parts)}"
    group_cmds = {k[len(parts)] for k in cli if len(k) > len(parts) and k[:len(parts)] == tuple(parts)}
    if group_cmds and i < len(toks) and not toks[i].startswith("-") and toks[i] not in ("|", ">", "&&"):
        if not cmd.rstrip().endswith("..."):
            return f"unknown subcommand '{toks[i]}' of pskit {' '.join(parts)}"
    for t in toks[i:]:
        if t in ("|", "&&", ";", ">"):
            break
        if t == "--":
            break
        if t.startswith("-") and not re.fullmatch(r"-\d+", t):
            flag = t.split("=", 1)[0]
            if flag not in flags:
                return f"unknown flag {flag} for pskit {' '.join(parts)}"
    return None


def yaml_snippets(text: str) -> List[str]:
    return re.findall(r"```ya?ml\n(.*?)```", text, re.S)


STUDIO_PATH = re.compile(r"\*\*([^*\n]+?(?: > | → )[^*\n]+?)\*\*")


def studio_paths(text: str) -> List[str]:
    return [m.group(1) for m in STUDIO_PATH.finditer(text)]


def citations(text: str) -> List[str]:
    return re.findall(r"\[((?:docs|examples|src|README)[^\]\s#]*(?:#[^\]\s]+)?)\]", text)


def is_verbatim(excerpt: str, cards: Dict[str, str]) -> Optional[str]:
    """Each excerpt is "[path#anchor]\\n<text>"; the text must be a substring of the file (or a card)."""
    m = re.match(r"\[([^\]#]+)(?:#([^\]]+))?\]\n(.*)\Z", excerpt, re.S)
    if not m:
        return "excerpt does not start with [path#anchor]"
    path, body = m.group(1), m.group(3).strip()
    candidates: List[str] = []
    p = REPO / path
    if p.is_file():
        candidates.append(p.read_text(encoding="utf-8").replace("\r\n", "\n"))
    candidates.extend(cards.values())
    if not any(body in c for c in candidates):
        return f"excerpt from {path} is not verbatim"
    return None


def split_excerpts(content: str) -> List[str]:
    parts = re.split(r"\n\n(?=\[(?:docs|examples|src|README|ai-agent)[^\]\n]*\]\n)", content)
    return [p for p in parts if p.strip()]


WAY_HEADINGS = {"studio": "**In studio**", "terminal": "**In the terminal**", "code": "**In code**"}
WAY_WORDS = {
    "studio": re.compile(r"\b(in studio|in the studio|studio steps|in the ui|gui|which button|where do i click|"
                         r"click|studio only|only studio|using studio|from studio)\b", re.I),
    "terminal": re.compile(r"\b(command|cli|terminal|shell)\b", re.I),
    "code": re.compile(r"\b(yaml|pskit\.yml|in code|handler code|the code)\b", re.I),
}


def check_record(rec: Dict[str, Any], ctx: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    E: List[str] = []
    W: List[str] = []
    rid = rec.get("id", "?")
    meta = rec.get("meta") or {}
    cat = meta.get("category")
    if cat not in CATEGORIES:
        E.append(f"meta.category {cat!r}")
    if not str(rid).startswith(f"{cat}-"):
        E.append(f"id {rid!r} should start with '{cat}-'")
    for key in ("provider", "mode", "persona", "verified", "sources"):
        if key not in meta:
            E.append(f"meta.{key} missing")
    if meta.get("persona") not in PERSONAS:
        E.append(f"meta.persona {meta.get('persona')!r}")
    if "tools" in rec:
        E.append("record has a 'tools' field (build_dataset.py adds it)")
    msgs = rec.get("messages") or []
    if len(msgs) < 3 or msgs[0].get("role") != "system" or msgs[1].get("role") != "user":
        E.append("must start with system, user")
        return E, W
    if msgs[-1].get("role") != "assistant" or msgs[-1].get("tool_calls"):
        E.append("must end with a plain assistant message")
    sysmsg = msgs[0]["content"]
    head, _, env = sysmsg.rpartition("\n")
    if head != SYSTEM_PROMPT:
        E.append("system prompt differs from SYSTEM_PROMPT")
    m = ENV_RE.match(env)
    if not m:
        E.append("bad Environment line")
    else:
        p, st, mode, page = m.groups()
        if p not in PROVIDERS or st not in STAGES or mode not in MODES or page not in PAGES:
            E.append(f"bad Environment values: {env}")
        cat, _, num = str(rec.get("id", "")).rpartition("-")
        if p not in STAGE2_PROVIDERS and num.isdigit() and int(num) > LEGACY_MAX_ID.get(cat, 0):
            E.append(f"provider {p} is outside the stage-2 scope {STAGE2_PROVIDERS}")
        if p != meta.get("provider"):
            W.append(f"meta.provider {meta.get('provider')} != Environment provider {p}")
        if mode != meta.get("mode"):
            E.append("meta.mode != Environment mode")
        ctx["mode"] = mode
    # roles, tool calls
    pending: Dict[str, str] = {}
    seen_ids: Set[str] = set()
    calls: List[Tuple[str, Dict[str, Any], str]] = []  # (name, args, output)
    for i, msg in enumerate(msgs[2:], 2):
        role = msg.get("role")
        if role == "assistant":
            if pending:
                E.append(f"message {i}: assistant before all tool results arrived")
            tcs = msg.get("tool_calls") or []
            if len(tcs) > 1:
                E.append(f"message {i}: more than one tool call")
            for tc in tcs:
                fn = tc.get("function", {})
                name = fn.get("name")
                if tc.get("id") in seen_ids:
                    E.append(f"duplicate tool_call id {tc.get('id')}")
                seen_ids.add(tc.get("id"))
                if name not in TOOL_ARGS:
                    E.append(f"unknown tool {name}")
                    continue
                try:
                    args = json.loads(fn.get("arguments", ""))
                except ValueError:
                    E.append(f"{name}: arguments are not a JSON string")
                    continue
                if not isinstance(fn.get("arguments"), str):
                    E.append(f"{name}: arguments must be a string")
                req, opt = TOOL_ARGS[name]
                keys = set(args)
                if not req <= keys:
                    E.append(f"{name}: missing {sorted(req - keys)}")
                if keys - req - opt:
                    E.append(f"{name}: unknown arguments {sorted(keys - req - opt)}")
                if name == "propose_plan" and not (isinstance(args.get("steps"), list) and args["steps"]):
                    E.append("propose_plan.steps must be a non-empty list")
                if args.get("provider") is not None and args.get("provider") not in PROVIDERS:
                    E.append(f"{name}: bad provider {args.get('provider')}")
                pending[tc.get("id")] = name
                calls.append((name, args, ""))
        elif role == "tool":
            tid = msg.get("tool_call_id")
            if tid not in pending:
                E.append(f"message {i}: tool result {tid} has no pending call")
                continue
            if msg.get("name") != pending[tid]:
                E.append(f"message {i}: tool name {msg.get('name')} != call {pending[tid]}")
            pending.pop(tid)
            for j in range(len(calls) - 1, -1, -1):
                if calls[j][2] == "":
                    calls[j] = (calls[j][0], calls[j][1], msg.get("content") or "\u0000")
                    break
        else:
            E.append(f"message {i}: unexpected role {role}")
    if pending:
        E.append(f"tool calls without results: {sorted(pending)}")
    # length
    chars = sum(len(m.get("content") or "") for m in msgs)
    chars += sum(len(tc["function"]["arguments"]) for m in msgs for tc in (m.get("tool_calls") or []))
    if chars / 3.5 >= MAX_TOKENS:
        E.append(f"too long: ~{int(chars / 3.5)} tokens")
    elif chars / 3.5 > 1500:
        ctx["long"] += 1
    names = [c[0] for c in calls]
    # flow rules
    if cat == "a_qa" and (not names or names[0] != "search_docs"):
        E.append("a_qa must start with search_docs")
    changes = [i for i, n in enumerate(names) if n in ("set_config", "write_file")]
    if changes:
        plans = [i for i, n in enumerate(names) if n == "propose_plan"]
        if not plans or plans[0] > changes[0]:
            E.append("set_config/write_file before propose_plan")
        last_change = changes[-1]
        if names[last_change] != "set_config" and not any(n in ("validate", "set_config") for n in names[last_change + 1:]):
            E.append("no validate after the last change")
    for name, args, out in calls:
        if name == "propose_plan":
            try:
                dec = json.loads(out).get("decision")
            except (ValueError, AttributeError):
                E.append("propose_plan result is not JSON with a decision")
                continue
            if ctx.get("mode") == "auto" and dec != "auto_approved":
                E.append("mode=auto but propose_plan was not auto_approved")
            if ctx.get("mode") == "ask" and dec == "auto_approved":
                E.append("mode=ask but propose_plan returned auto_approved")
            if dec == "rejected":
                idx = names.index("propose_plan")
                if any(n in ("set_config", "write_file") for n in names[idx + 1:]):
                    W.append("changes after a rejected plan (only OK if the user agreed to a new plan)")
        if name == "search_docs":
            for ex in split_excerpts(out):
                prob = is_verbatim(ex, ctx["cards"])
                if prob:
                    E.append(prob)
    if cat in CHECKED_CATS:
        checks = [c for c in calls if c[0] in ("validate", "get_validation", "set_config", "invoke_local")]
        last_val = [c for c in checks if c[0] != "invoke_local"]
        last_inv = [c for c in checks if c[0] == "invoke_local"]
        for label, lst in (("validate", last_val), ("invoke", last_inv)):
            if lst:
                out = lst[-1][2]
                if "ERROR:" in out or "Traceback" in out or any(l.startswith("Error:") for l in out.splitlines()):
                    E.append(f"last {label} output is not a success")
        if cat == "b_build" and not last_val:
            E.append("b_build without validate")
        if cat == "b_build" and any(c[0] == "write_file" and c[1].get("path", "").endswith(".py") for c in calls) \
                and not last_inv:
            E.append("handler written but no invoke_local")
    # final answers and assistant texts
    final = msgs[-1].get("content") or ""
    texts = [m.get("content") or "" for m in msgs[2:] if m.get("role") == "assistant"]
    for t in texts:
        for cmd in pskit_commands(t):
            prob = check_command(cmd, ctx["cli"])
            if prob:
                E.append(f"{prob}  [{cmd}]")
        for snip in yaml_snippets(t):
            try:
                import yaml
                data = yaml.safe_load(snip)
            except Exception as exc:  # noqa: BLE001
                W.append(f"YAML snippet does not parse: {str(exc).splitlines()[0]}")
                continue
            bad = ctx["schema"].check_snippet(data)
            if bad:
                E.append(f"YAML keys not in schema: {bad[:5]}")
        for sp in studio_paths(t):
            first = re.split(r" > | → ", sp)[0].strip()
            if first not in NAV_LABELS:
                E.append(f"studio path does not start with a NAV label: {sp}")
        for cite in citations(t):
            path, _, anchor = cite.partition("#")
            if not (REPO / path).exists():
                E.append(f"citation to missing file {cite}")
            elif anchor and path in ctx["anchors"] and anchor not in ctx["anchors"][path]:
                E.append(f"citation anchor not found: {cite}")
        if MODEL_NAMES.search(t):
            E.append(f"assistant names a model/company: {MODEL_NAMES.search(t).group(0)}")
    # one way only
    user = msgs[1]["content"]
    heads = {k for k, h in WAY_HEADINGS.items() if h in final}
    named = {k for k, rx in WAY_WORDS.items() if rx.search(user)}
    if len(heads) > 1 and len(named) == 1 and re.search(r"\bonly\b|\bjust\b", user, re.I):
        E.append(f"user asked for one way ({named.pop()}) but the answer has {sorted(heads)}")
    elif len(heads) > 1 and len(named) == 1:
        W.append(f"user may have named one way ({next(iter(named))}); answer has {sorted(heads)}")
    # secrets, IPs
    for m_ in msgs[1:]:
        content = (m_.get("content") or "") + "".join(tc["function"]["arguments"] for tc in (m_.get("tool_calls") or []))
        for prob in secret_problems(content):
            (E if m_.get("role") == "assistant" else W).append(f"{m_.get('role')}: {prob}")
        errs, warns = ip_problems(content)
        for ip in errs:
            E.append(f"non-documentation IP {ip}")
        for ip in warns:
            W.append(f"private IP {ip}")
    # duplicates
    key = re.sub(r"\s+", " ", user.strip().lower())
    if key in ctx["users"]:
        E.append(f"duplicate user message (also {ctx['users'][key]})")
    else:
        ctx["users"][key] = rid
    return E, W


def _utf8() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except AttributeError:
            pass


def main(argv: Optional[List[str]] = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    files = [Path(a) for a in args] or sorted(p for p in RAW.glob("*.jsonl") if not p.name.startswith("k_"))
    ctx: Dict[str, Any] = {"cli": load_cli(), "anchors": load_anchors(), "cards": load_cards(), "schema": Schema(),
                           "users": {}, "long": 0}
    total = errors = warnings = 0
    failing: List[str] = []
    per_cat: Dict[str, int] = {}
    in_scope: Dict[str, int] = {}
    for f in files:
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            total += 1
            try:
                rec = json.loads(line)
            except ValueError as exc:
                print(f"{f.name}:{n}: ERROR invalid JSON: {exc}")
                errors += 1
                continue
            E, W = check_record(rec, ctx)
            cat = (rec.get("meta") or {}).get("category", "?")
            per_cat[cat] = per_cat.get(cat, 0) + 1
            if (rec.get("meta") or {}).get("provider") in STAGE2_PROVIDERS:
                in_scope[cat] = in_scope.get(cat, 0) + 1
            for e in E:
                print(f"{f.name}:{n} {rec.get('id')}: ERROR {e}")
            for w in W:
                print(f"{f.name}:{n} {rec.get('id')}: warning {w}")
            errors += len(E)
            warnings += len(W)
            if E:
                failing.append(str(rec.get("id")))
    print(f"\n{total} conversation(s) in {len(files)} file(s): {errors} error(s), {warnings} warning(s); "
          f"{ctx['long']} over 1500 tokens")
    print("per category: " + ", ".join(f"{k}={v}" for k, v in sorted(per_cat.items())))
    print("in stage-2 scope (aws/azure/gcp/onprem): " + ", ".join(f"{k}={v}" for k, v in sorted(in_scope.items())))
    if failing:
        print("failing ids: " + ", ".join(failing))
    return 1 if errors else 0


if __name__ == "__main__":
    _utf8()
    raise SystemExit(main())
