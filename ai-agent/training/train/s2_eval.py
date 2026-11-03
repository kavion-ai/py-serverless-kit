"""Stage 2, step C: next-step accuracy on the task validation set.

Run in Colab:
  BASE=/content/drive/MyDrive/hana/hana-stage1-merged ADAPTER=/content/drive/MyDrive/hana/stage2/adapter_final \
      python ./training/train/s2_eval.py
Env (optional):
  N          validation conversations, default 80 (all = 156; about 1 min each on a T4)
  COMPARE=1  also score the stage-1 model (adapter switched off), to see what stage 2 added
  GEN_BATCH  generations at once, default 6
For every assistant turn of a validation conversation, Hana gets the real conversation up to that point and must
produce the next step. Scored:
  action    she calls the same tool as the reference (or answers in text when the reference does)
  args      the call is valid JSON with the reference's argument names
  plan      in changing conversations, propose_plan comes before the first set_config / write_file
  final     the last answer cites a doc ([docs/...]) when the reference does, and uses the "In studio" /
            "In the terminal" / "In code" headings when the reference does
Writes <ADAPTER>/../eval_stage2.md with every reference vs. Hana step.
"""

import json
import os
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

import torch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from step3_train import _skip_old_torchao  # noqa: E402

_skip_old_torchao()
from peft import PeftModel  # noqa: E402
from step2_prepare import clean  # noqa: E402
from transformers import AutoModelForCausalLM, AutoTokenizer  # noqa: E402

BASE = os.environ.get("BASE", str(HERE / "work" / "hana-stage1-merged"))
ADAPTER = Path(os.environ.get("ADAPTER", str(HERE / "work" / "stage2" / "adapter_final")))
N = int(os.environ.get("N", "80"))
COMPARE = os.environ.get("COMPARE") == "1"
GEN_BATCH = int(os.environ.get("GEN_BATCH", "6"))
VAL = HERE.parent / "data" / "final" / "task_val.jsonl"
TOOL_CALL = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.S)
CHANGE = {"set_config", "write_file"}
HEADINGS = ("**In studio**", "**In the terminal**", "**In code**")


def parse(text):
    """Generated text -> ("tool", name, args) or ("answer", text)."""
    m = TOOL_CALL.search(text)
    if not m:
        return ("answer", text.strip(), None)
    try:
        call = json.loads(m.group(1))
        args = call.get("arguments", {})
        if isinstance(args, str):
            args = json.loads(args)
        return ("tool", call.get("name", "?"), args if isinstance(args, dict) else None)
    except (json.JSONDecodeError, AttributeError):
        return ("tool", "?invalid-json", None)


def reference(msg):
    if msg.get("tool_calls"):
        fn = msg["tool_calls"][0]["function"]
        return ("tool", fn["name"], fn["arguments"] if isinstance(fn["arguments"], dict) else json.loads(fn["arguments"]))
    return ("answer", msg["content"], None)


def generate(model, tok, prompts):
    tok.padding_side = "left"
    out = []
    for i in range(0, len(prompts), GEN_BATCH):
        batch = tok(prompts[i:i + GEN_BATCH], return_tensors="pt", padding=True, add_special_tokens=False).to(model.device)
        with torch.no_grad():
            gen = model.generate(**batch, max_new_tokens=450, do_sample=False, pad_token_id=tok.pad_token_id)
        out += [tok.decode(g[batch["input_ids"].shape[1]:], skip_special_tokens=False) for g in gen]
    return [o.replace("<|im_end|>", "").replace("<|endoftext|>", "").strip() for o in out]


def score(rows, outputs):
    s = defaultdict(lambda: [0, 0])
    per_cat = defaultdict(lambda: [0, 0])
    for (row, i, ref), text in zip(rows, outputs):
        got = parse(text)
        ok = got[0] == ref[0] and (ref[0] == "answer" or got[1] == ref[1])
        s["action"][0] += ok
        s["action"][1] += 1
        per_cat[row["meta"]["category"]][0] += ok
        per_cat[row["meta"]["category"]][1] += 1
        if ref[0] == "tool":
            s["args"][1] += 1
            s["args"][0] += got[0] == "tool" and got[2] is not None and set(got[2]) == set(ref[2] or {})
        if ref[0] == "answer" and i == len(row["messages"]) - 1:
            for name, test in (("final cites a doc", lambda t: "[docs/" in t),
                               ("final uses how-to headings", lambda t: any(h in t for h in HEADINGS))):
                if test(ref[1]):
                    s[name][1] += 1
                    s[name][0] += got[0] == "answer" and test(got[1])
        if ref[0] == "tool" and ref[1] in CHANGE:
            planned = any(m.get("tool_calls") and m["tool_calls"][0]["function"]["name"] == "propose_plan"
                          for m in row["messages"][:i])
            if planned:
                s["plan before change"][1] += 1
                s["plan before change"][0] += got[0] == "tool" and got[1] in CHANGE | {"propose_plan", "validate"}
    return s, per_cat


def main():
    rows = [json.loads(line) for line in VAL.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = random.Random(2200).sample(rows, min(N, len(rows)))
    tok = AutoTokenizer.from_pretrained(str(ADAPTER))
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    bf16 = torch.cuda.is_available() and torch.cuda.get_device_capability(0)[0] >= 8
    base = AutoModelForCausalLM.from_pretrained(BASE, dtype=torch.bfloat16 if bf16 else torch.float16,
                                                device_map="cuda")
    model = PeftModel.from_pretrained(base, str(ADAPTER)).eval()

    items, prompts = [], []
    for r in rows:
        messages, tools = clean(r, {"redacted": 0})
        for i, m in enumerate(messages):
            if m["role"] == "assistant" and i >= 2:
                items.append((r, i, reference(r["messages"][i])))
                prompts.append(tok.apply_chat_template(messages[:i], tools=tools, tokenize=False,
                                                       add_generation_prompt=True))
    print(f"{len(rows)} conversations, {len(prompts)} assistant steps, adapter {ADAPTER}")
    runs = {"stage 2": generate(model, tok, prompts)}
    if COMPARE:
        with model.disable_adapter():
            runs["stage 1 (no stage-2 adapter)"] = generate(model, tok, prompts)

    lines = ["# Stage-2 evaluation", ""]
    for name, outs in runs.items():
        s, per_cat = score(items, outs)
        print(f"\n== {name} ==")
        lines.append(f"## {name}\n")
        for k, (a, b) in s.items():
            print(f"{k:28s} {a}/{b} = {a / max(b, 1):.0%}")
            lines.append(f"- {k}: {a}/{b} = {a / max(b, 1):.0%}")
        print("action per category:", ", ".join(f"{c} {a}/{b}" for c, (a, b) in sorted(per_cat.items())))
        lines.append("- action per category: " + ", ".join(f"{c} {a}/{b}" for c, (a, b) in sorted(per_cat.items())))
        lines.append("")
    lines.append("## Steps (reference vs. stage 2)\n")
    for (r, i, ref), out in zip(items, runs["stage 2"]):
        want = f"tool {ref[1]} {json.dumps(ref[2], ensure_ascii=False)[:200]}" if ref[0] == "tool" else ref[1][:600]
        lines += [f"### {r['id']} step {i} ({r['meta']['category']}, {r['meta']['provider']})",
                  f"**user:** {r['messages'][1]['content'][:300]}", f"**reference:** {want}", f"**hana:** {out[:600]}", ""]
    path = ADAPTER.parent / "eval_stage2.md"
    path.write_bytes("\n".join(lines).encode("utf-8"))
    print("\nwrote", path)


if __name__ == "__main__":
    main()
