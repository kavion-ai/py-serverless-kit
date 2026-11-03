"""Stage 2, step E: chat with the final Hana model, with all 10 tools working for real on a copy of a project.

Run in Colab (pskit must be installed: see COLAB_STAGE2.md, cell 2):
  MERGED=/content/drive/MyDrive/hana/hana-stage2-merged python ./training/train/s2_chat.py
Env (optional):
  PROJECT  a folder with pskit.yml; it is COPIED to training/scratch/chat/ and Hana works on the copy.
           Default /content/examples/01-hello-http (the zip ships 01, 04, 07, 16 and 18).
  ENV      "provider=onprem stage=dev mode=ask page=none" (provider aws, azure, gcp or onprem)
  Q        one message, then exit; plans are approved automatically in this mode
  TEMPERATURE 0 = greedy (default)
Tools: search_docs = keyword search over the knowledge cards; get_project / read_file / write_file / set_config /
validate / get_validation / invoke_local = real pskit on the copy (validate and local invoke only: nothing deploys);
propose_plan and ask_user = you answer in the terminal (in mode=auto plans are approved automatically).
Commands: /reset (new chat, fresh project copy), /project (print pskit.yml), /quit.
"""

import json
import os
import re
import sys
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

HERE = Path(__file__).resolve().parent
TRAIN = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(TRAIN / "tools"))
from run_tool import Scratch  # noqa: E402
from step6_chat import INDEX, Search  # noqa: E402
from task_common import ENV_LINE, SYSTEM_PROMPT, TOOLS  # noqa: E402

MERGED = Path(os.environ.get("MERGED", str(HERE / "work" / "hana-stage2-merged")))
PROJECT = Path(os.environ.get("PROJECT", "/content/examples/01-hello-http"))
ENV = dict(kv.split("=", 1) for kv in os.environ.get("ENV", "provider=onprem stage=dev mode=ask page=none").split())
TEMP = float(os.environ.get("TEMPERATURE", "0"))
ONE = os.environ.get("Q")
TOOL_CALL = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.S)
MAX_STEPS = 14


def ask(prompt, default):
    if ONE:
        print(f"{prompt} {default}  (auto, Q mode)")
        return default
    try:
        return input(prompt + " ").strip() or default
    except EOFError:
        return default


class Tools:
    def __init__(self):
        self.search = Search(INDEX)
        self.reset()

    def reset(self):
        if not (PROJECT / "pskit.yml").exists():
            raise SystemExit(f"PROJECT {PROJECT} has no pskit.yml")
        self.project = Scratch("chat").create(base=str(PROJECT.resolve()))

    def run(self, name, a):
        p, stage = ENV.get("provider", "onprem"), ENV.get("stage", "dev")
        if name == "search_docs":
            text, ids = self.search(a.get("query", ""))
            print(f"   [search] {a.get('query')!r} -> {', '.join(ids)}")
            return text
        if name == "get_project":
            return self.project.get_project()
        if name == "read_file":
            return self.project.read_file(a["path"])
        if name == "write_file":
            return self.project.write_file(a["path"], a.get("content", ""))
        if name == "set_config":
            return self.project.set_config(a["path"], a.get("value"), p, stage)
        if name in ("validate", "get_validation"):
            return self.project.validate(a.get("provider") or p, stage)
        if name == "invoke_local":
            return self.project.invoke(a["function"], a.get("type"), a.get("data"), a.get("method"), a.get("path"),
                                       stage=stage)
        if name == "propose_plan":
            print("   [plan]\n" + "\n".join(f"     {n}. {s}" for n, s in enumerate(a.get("steps", []), 1)))
            if ENV.get("mode") == "auto":
                return json.dumps({"decision": "auto_approved"})
            ans = ask("   approve? [y = yes / n <note> = reject / or type a note to approve with]", "y")
            if ans.lower() in ("y", "yes"):
                return json.dumps({"decision": "approved", "note": ""})
            if ans.lower().startswith("n"):
                return json.dumps({"decision": "rejected", "note": ans[1:].strip()})
            return json.dumps({"decision": "approved", "note": ans})
        if name == "ask_user":
            opts = a.get("options") or []
            print(f"   [hana asks] {a.get('question')}" + (f"  options: {', '.join(map(str, opts))}" if opts else ""))
            return ask("   your answer:", str(opts[0]) if opts else "")
        return f"error: unknown tool {name}"


def generate(model, tok, messages):
    text = tok.apply_chat_template(messages, tools=TOOLS, tokenize=False, add_generation_prompt=True)
    ids = tok(text, return_tensors="pt", add_special_tokens=False).to(model.device)
    extra = {"do_sample": True, "temperature": TEMP, "top_p": 0.9} if TEMP > 0 else {"do_sample": False}
    with torch.no_grad():
        out = model.generate(**ids, max_new_tokens=900, repetition_penalty=1.05, **extra)
    return tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True).strip()


def turn(model, tok, tools, messages):
    for step in range(MAX_STEPS):
        reply = generate(model, tok, messages)
        m = TOOL_CALL.search(reply)
        if not m:
            messages.append({"role": "assistant", "content": reply})
            return reply
        say = reply[:m.start()].strip()
        if say:
            print(f"hana> {say}")
        try:
            call = json.loads(m.group(1))
            name, args = call.get("name", "?"), call.get("arguments", {})
            args = json.loads(args) if isinstance(args, str) else args
            result = tools.run(name, args)
        except (json.JSONDecodeError, KeyError, TypeError, AttributeError) as exc:
            name, args, result = "?", {}, f"error: bad tool call ({exc})"
        except SystemExit as exc:  # run_tool refuses paths outside the project
            result = f"error: {exc}"
        print(f"   [{name}] {json.dumps(args, ensure_ascii=False)[:160]}")
        if name in ("validate", "get_validation", "set_config", "invoke_local"):
            print("     " + result.replace("\n", "\n     ")[:1500])
        messages.append({"role": "assistant", "content": say, "tool_calls": [
            {"type": "function", "function": {"name": name, "arguments": args}}]})
        messages.append({"role": "tool", "name": name, "content": result, "tool_call_id": f"call_{step + 1:02d}"})
    messages.append({"role": "assistant", "content": "(stopped: too many tool steps)"})
    return "(stopped: too many tool steps)"


def main():
    if ENV.get("provider") not in ("aws", "azure", "gcp", "onprem"):
        print("note: stage 2 was trained on aws, azure, gcp and onprem only")
    tools = Tools()
    system = SYSTEM_PROMPT + "\n" + ENV_LINE.format(provider=ENV.get("provider", "onprem"),
                                                    stage=ENV.get("stage", "dev"), mode=ENV.get("mode", "ask"),
                                                    page=ENV.get("page", "none"))
    tok = AutoTokenizer.from_pretrained(str(MERGED))
    bf16 = torch.cuda.is_available() and torch.cuda.get_device_capability(0)[0] >= 8
    dtype = torch.bfloat16 if bf16 else (torch.float16 if torch.cuda.is_available() else torch.float32)
    model = AutoModelForCausalLM.from_pretrained(str(MERGED), dtype=dtype,
                                                 device_map="cuda" if torch.cuda.is_available() else None).eval()
    print(f"Hana from {MERGED}\nproject copy: {tools.project.root} (from {PROJECT})\nEnvironment: {ENV}")
    messages = [{"role": "system", "content": system}]
    if ONE:
        print(f"\nyou> {ONE}")
        messages.append({"role": "user", "content": ONE})
        print(f"hana> {turn(model, tok, tools, messages)}")
        return
    print("type a message; /reset, /project, /quit\n")
    while True:
        try:
            q = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if q in ("/quit", "/exit"):
            break
        if q == "/reset":
            messages = messages[:1]
            tools.reset()
            print("(new chat, fresh project copy)")
            continue
        if q == "/project":
            print(tools.project.get_project())
            continue
        if q:
            messages.append({"role": "user", "content": q})
            print(f"hana> {turn(model, tok, tools, messages)}\n")


if __name__ == "__main__":
    main()
