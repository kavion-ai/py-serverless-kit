"""Assemble hand-written task conversations into JSONL, with REAL tool outputs.

A batch file (data/task_src/<category>_NN.py) defines CONVERSATIONS, a list of dicts written by hand (see notes.md):
user message, the tool steps Hana takes, the plan, and the final answer. This script only runs the steps:

  * search_docs  -> the verbatim excerpts given by D(path, anchor, ...) / D(card=...)
  * get_project / read_file / write_file / set_config / validate / get_validation / invoke_local
                 -> run for real on a fresh scratch project (tools/run_tool.py)
  * propose_plan / ask_user -> the decision / answer written in the batch file

and upserts the records (by id) into data/raw/<category>.jsonl. It prints every tool output so the author can check
that the final answer matches what really happened.

    python tools/assemble.py data/task_src/b_build_01.py [--only ID ...] [--quiet]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_tool import TRAIN, Scratch, doc_excerpt  # noqa: E402
from task_common import system_message  # noqa: E402

RAW = TRAIN / "data" / "raw"
CARDS = TRAIN / "knowledge" / "cards.jsonl"


def S(tool: str, say: str = "", **args: Any) -> Dict[str, Any]:
    """One tool call. Extra keys that are not tool arguments: docs (search_docs), result (propose_plan),
    answer (ask_user), provider/stage for validate are tool arguments."""
    return {"tool": tool, "say": say, "args": args}


def D(path: str = "", anchor: str = "", start: str = None, end: str = None, words: int = 220, card: str = "") -> str:
    if card:
        for line in CARDS.read_text(encoding="utf-8").splitlines():
            c = json.loads(line)
            if c["id"] == card:
                src = (c.get("sources") or [""])[0]
                text = c["text"]
                if start:
                    text = text[text.index(start):]
                if end:
                    text = text[: text.index(end) + len(end)]
                return f"[{src}]\n{text.strip()}"
        raise SystemExit(f"no card {card}")
    return doc_excerpt(path, anchor, start, end, words)


def build(conv: Dict[str, Any], quiet: bool = False) -> Dict[str, Any]:
    provider, stage = conv["provider"], conv.get("stage", "dev")
    msgs: List[Dict[str, Any]] = [
        {"role": "system", "content": system_message(provider, stage, conv["mode"], conv["page"])},
        {"role": "user", "content": conv["user"]},
    ]
    scratch = None
    proj = conv.get("project")
    if proj is not None:
        scratch = Scratch(conv["id"].replace("/", "_")).create(base=proj.get("base"), files=proj.get("files"))
    verified = {"validate": "n/a", "invoke": "n/a"}
    for n, step in enumerate(conv["steps"], 1):
        tool, a = step["tool"], dict(step["args"])
        extra = {k: a.pop(k) for k in ("docs", "result", "answer", "run_provider") if k in a}
        if tool in ("get_project", "read_file", "write_file", "set_config", "validate", "get_validation", "invoke_local") \
                and scratch is None:
            raise SystemExit(f"{conv['id']}: {tool} needs a project")
        if tool == "search_docs":
            out = "\n\n".join(extra["docs"])
        elif tool == "get_project":
            out = scratch.get_project()
        elif tool == "read_file":
            out = scratch.read_file(a["path"])
        elif tool == "write_file":
            out = scratch.write_file(a["path"], a["content"])
        elif tool == "set_config":
            out = scratch.set_config(a["path"], a["value"], extra.get("run_provider", provider), stage)
            verified["validate"] = _ok(out)
        elif tool in ("validate", "get_validation"):
            out = scratch.validate(a.get("provider", provider), stage)
            verified["validate"] = _ok(out)
        elif tool == "invoke_local":
            data = a.get("data")
            out = scratch.invoke(a["function"], a.get("type"), data, a.get("method"), a.get("path"), stage=stage)
            verified["invoke"] = _ok(out)
        elif tool == "propose_plan":
            res = extra.get("result") or ({"decision": "auto_approved"} if conv["mode"] == "auto"
                                           else {"decision": "approved", "note": ""})
            out = json.dumps(res, ensure_ascii=False)
        elif tool == "ask_user":
            out = extra["answer"]
        else:
            raise SystemExit(f"{conv['id']}: unknown tool {tool}")
        cid = f"call_{n:02d}"
        msgs.append({"role": "assistant", "content": step.get("say", ""),
                     "tool_calls": [{"id": cid, "type": "function",
                                     "function": {"name": tool, "arguments": json.dumps(a, ensure_ascii=False)}}]})
        msgs.append({"role": "tool", "tool_call_id": cid, "name": tool, "content": out})
        if not quiet:
            print(f"--- {conv['id']} #{n} {tool} {json.dumps(a, ensure_ascii=False)[:120]}\n{out}\n")
    msgs.append({"role": "assistant", "content": conv["final"]})
    if scratch is not None:
        scratch.clean()
    return {"id": conv["id"], "messages": msgs,
            "meta": {"category": conv["category"], "provider": provider, "mode": conv["mode"],
                     "persona": conv["persona"], "verified": verified, "sources": conv.get("sources", [])}}


def _ok(out: str) -> str:
    bad = "Traceback" in out or "ERROR:" in out or any(l.startswith("Error:") for l in out.splitlines())
    return "fail" if bad else "pass"


def upsert(category: str, records: List[Dict[str, Any]]) -> Path:
    path = RAW / f"{category}.jsonl"
    if category.startswith("k_"):
        raise SystemExit("k_*.jsonl belong to stage 1")
    existing: List[Dict[str, Any]] = []
    if path.exists():
        existing = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    new = {r["id"]: r for r in records}
    out = [new.pop(r["id"], r) for r in existing] + list(new.values())
    path.write_bytes(("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out)).encode("utf-8"))
    return path


def _utf8() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except AttributeError:
            pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("batch")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    spec = importlib.util.spec_from_file_location("batch", a.batch)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["batch"] = mod
    spec.loader.exec_module(mod)
    by_cat: Dict[str, List[Dict[str, Any]]] = {}
    for conv in mod.CONVERSATIONS:
        if a.only and conv["id"] not in a.only:
            continue
        by_cat.setdefault(conv["category"], []).append(build(conv, a.quiet))
    for cat, recs in by_cat.items():
        print(f"{upsert(cat, recs)}: {len(recs)} conversation(s) written")
    return 0


if __name__ == "__main__":
    _utf8()
    raise SystemExit(main())
