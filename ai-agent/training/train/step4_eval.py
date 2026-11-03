"""Step 4: score the stage-1 adapter on knowledge_val (optionally against the untrained base model).

Run:  ADAPTER=/content/drive/MyDrive/hana/stage1/adapter_final python ./training/train/step4_eval.py
Env (optional):
  MODEL_ID  default Qwen/Qwen2.5-1.5B-Instruct (must match steps 2-3)
  ADAPTER   default ai-agent/training/train/work/stage1/adapter_final
  N         validation conversations to answer, default 230 (all)
  BASE      1 also answers with the adapter switched off, for comparison; default 0
  GEN_BATCH answers generated at once, default 8
Closed book: each conversation is answered at its first assistant turn (system + first user message), greedy.
Open book: for conversations whose first move is a search_docs call, Hana also gets the real search result and is
scored on the answer after it (how she works in studio).
Writes <ADAPTER>/../eval_stage1.md (question, expected answer, Hana's answer) and prints a summary.
"""

import json
import os
import random
import re
import sys
import time
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer


def _skip_old_torchao():
    """Colab ships torchao 0.10; peft refuses it even though LoRA here never uses torchao. Skip that check."""
    try:
        import peft.tuners.lora.torchao as peft_torchao
        peft_torchao.is_torchao_available = lambda: False
    except (ImportError, AttributeError):
        pass


_skip_old_torchao()

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from step2_prepare import FINAL, clean, load  # noqa: E402  (same record conversion as training)

MODEL_ID = os.environ.get("MODEL_ID", "Qwen/Qwen2.5-1.5B-Instruct")
ADAPTER = Path(os.environ.get("ADAPTER", str(HERE / "work" / "stage1" / "adapter_final")))
N = int(os.environ.get("N", "230"))
BASE = os.environ.get("BASE", "0") == "1"
GEN_BATCH = int(os.environ.get("GEN_BATCH", "8"))
SECTIONS = ("**In studio**", "**In the terminal**", "**In code**")
IDENTITY = ("who are you?", "what base model do you use?", "is this llama or mistral?", "are you ChatGPT?",
            "hi, what can you do?", "who is the developer of hana?")
FOREIGN = re.compile(r"Qwen|Alibaba Cloud|OpenAI|Tongyi|I am ChatGPT|I'm ChatGPT")

FENCE = re.compile(r"```[^\n]*\n(.*?)```", re.S)
INLINE = re.compile(r"`([^`\n]{2,80})`")
BOLD = re.compile(r"\*\*([^*\n]{2,60})\*\*")
FLAG = re.compile(r"(?<![\w-])--[a-z][a-z0-9-]+")
SUBCMD = re.compile(r"\bpskit(?: [a-z][a-z-]+){1,2}")


def facts(text):
    """Things that can be right or wrong: code spans, studio labels, flags, pskit subcommands."""
    out = set()
    for block in FENCE.findall(text):
        out |= set(FLAG.findall(block)) | set(SUBCMD.findall(block))
    plain = FENCE.sub(" ", text)
    out |= {s.strip() for s in INLINE.findall(plain)}
    out |= {b.strip() for b in BOLD.findall(plain) if "**" + b.strip() + "**" not in SECTIONS}
    out |= set(FLAG.findall(plain)) | set(SUBCMD.findall(plain))
    return out


def known_facts():
    """Every fact that appears anywhere in the training data (answers, excerpts, cards)."""
    known = set()
    for r in load("knowledge_train.jsonl") + load("cards_train.jsonl"):
        for m in r["messages"]:
            known |= facts(m.get("content") or "")
    return known


def item(record, prompt, tools, ref):
    question = next(m["content"] for m in prompt if m["role"] == "user")
    return {"id": record["id"], "prompt": prompt, "tools": tools, "ref": ref, "question": question}


def first_turn(record):
    messages, tools = clean(record, {"redacted": 0})
    user_i = next(i for i, m in enumerate(messages) if m["role"] == "user")
    ref = next(m for m in messages[user_i + 1:] if m["role"] == "assistant")
    return item(record, messages[: user_i + 1], tools, ref)


def after_search(record):
    """Prompt up to and including the first search result, and the answer that follows it (or None)."""
    messages, tools = clean(record, {"redacted": 0})
    tool_i = next((i for i, m in enumerate(messages) if m["role"] == "tool"), None)
    if tool_i is None or tool_i + 1 >= len(messages) or messages[tool_i + 1]["role"] != "assistant":
        return None
    return item(record, messages[: tool_i + 1], tools, messages[tool_i + 1])


def generate(model, tok, prompts, label):
    t0, answers = time.time(), []
    for i in range(0, len(prompts), GEN_BATCH):
        texts = [tok.apply_chat_template(msgs, tools=tools, tokenize=False, add_generation_prompt=True)
                 for msgs, tools in prompts[i: i + GEN_BATCH]]
        enc = tok(texts, return_tensors="pt", padding=True, add_special_tokens=False).to(model.device)
        with torch.no_grad():
            out = model.generate(**enc, max_new_tokens=384, do_sample=False, pad_token_id=tok.pad_token_id)
        answers += tok.batch_decode(out[:, enc["input_ids"].shape[1]:], skip_special_tokens=True)
    print(f"{label}: {len(prompts)} answers in {time.time() - t0:.0f}s", flush=True)
    return [a.strip() for a in answers]


def score(items, answers, known):
    s = {"n": 0, "recall": [], "invented": 0, "facts": 0, "sections_ok": 0, "extra_sec": 0, "missing_sec": 0,
         "searches": 0, "search_ok": 0, "search_extra": 0}
    for it, ans in zip(items, answers):
        ref_text = it["ref"].get("content") or ""
        got_tool = "<tool_call>" in ans
        if it["ref"].get("tool_calls"):  # expected first move is a search: only the decision is scored here
            s["searches"] += 1
            s["search_ok"] += got_tool
            continue
        s["n"] += 1
        s["search_extra"] += got_tool
        want, got = facts(ref_text), facts(ans)
        if want:
            s["recall"].append(len(want & got) / len(want))
        it["invented"] = sorted(got - known)
        s["facts"] += len(got)
        s["invented"] += len(it["invented"])
        s["sections_ok"] += all((h in ref_text) == (h in ans) for h in SECTIONS)
        s["extra_sec"] += any(h in ans and h not in ref_text for h in SECTIONS)
        s["missing_sec"] += any(h in ref_text and h not in ans for h in SECTIONS)
    return s


def summary(name, s):
    rec = sum(s["recall"]) / max(1, len(s["recall"]))
    print(f"{name:>12}: {s['n']} answers | fact recall {rec:.0%} | invented {s['invented']}/{s['facts']} facts "
          f"| sections exact {s['sections_ok']}/{s['n']} (extra in {s['extra_sec']}, missing in {s['missing_sec']})")
    if s["searches"]:
        print(f"{'':>12}  search: called when expected {s['search_ok']}/{s['searches']}, "
              f"called when not expected {s['search_extra']}/{s['n']}")


def loss_history(adapter):
    """eval_loss per checkpoint, from the newest trainer_state.json next to the adapter."""
    states = sorted(adapter.parent.glob("checkpoint-*/trainer_state.json"),
                    key=lambda p: int(p.parent.name.split("-")[1]))
    if not states:
        return "no checkpoint found"
    log = json.loads(states[-1].read_text(encoding="utf-8"))["log_history"]
    return "  ".join(f"{e['step']}:{e['eval_loss']:.3f}" for e in log if "eval_loss" in e)


def write_report(path, closed, closed_ans, base_ans, opened, open_ans):
    lines = ["# Stage-1 evaluation", "", "## Closed book", ""]
    for i in sorted(range(len(closed)), key=lambda i: -len(closed[i].get("invented", []))):
        it = closed[i]
        lines += [f"### {it['id']}", "", f"**Q:** {it['question']}", "",
                  "**Expected:**", "", it["ref"].get("content") or "(search_docs call)", "",
                  "**Hana:**", "", closed_ans[i], ""]
        if it.get("invented"):
            lines += ["**Not in training data:** " + ", ".join(f"`{x}`" for x in it["invented"]), ""]
        if base_ans[i] is not None:
            lines += ["**Base model:**", "", base_ans[i], ""]
    lines += ["## Open book (answer after the search result)", ""]
    for it, ans in zip(opened, open_ans):
        lines += [f"### {it['id']}", "", f"**Q:** {it['question']}", "", "**Search result:**", "",
                  it["prompt"][-1]["content"], "", "**Expected:**", "", it["ref"].get("content") or "", "",
                  "**Hana:**", "", ans, ""]
        if it.get("invented"):
            lines += ["**Not in training data:** " + ", ".join(f"`{x}`" for x in it["invented"]), ""]
    path.write_bytes("\n".join(lines).encode("utf-8"))


def main():
    rows = load("knowledge_val.jsonl")
    random.Random(2100).shuffle(rows)
    rows = rows[:N]
    closed = [first_turn(r) for r in rows]
    opened = [it for it in (after_search(r) for r in rows) if it]
    print(f"model {MODEL_ID}, adapter {ADAPTER}, {len(closed)} questions from {FINAL / 'knowledge_val.jsonl'}")
    known = known_facts()

    tok = AutoTokenizer.from_pretrained(str(ADAPTER))
    tok.padding_side = "left"
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    bf16 = torch.cuda.is_available() and torch.cuda.get_device_capability(0)[0] >= 8
    base = AutoModelForCausalLM.from_pretrained(MODEL_ID, dtype=torch.bfloat16 if bf16 else torch.float16,
                                                attn_implementation="sdpa", device_map="cuda")
    model = PeftModel.from_pretrained(base, str(ADAPTER)).eval()

    closed_ans = generate(model, tok, [(it["prompt"], it["tools"]) for it in closed], "closed book")
    s_closed = score(closed, closed_ans, known)
    open_ans = generate(model, tok, [(it["prompt"], it["tools"]) for it in opened], "open book")
    s_open = score(opened, open_ans, known)
    system, tools = closed[0]["prompt"][0]["content"], closed[0]["tools"]
    ident = generate(model, tok, [([{"role": "system", "content": system}, {"role": "user", "content": q}], tools)
                                  for q in IDENTITY], "identity")
    s_base, base_ans = None, [None] * len(closed)
    if BASE:
        with model.disable_adapter():
            base_ans = generate(model, tok, [(it["prompt"], it["tools"]) for it in closed], "base model")
        s_base = score([dict(it) for it in closed], base_ans, known)

    out = ADAPTER.parent / "eval_stage1.md"
    write_report(out, closed, closed_ans, base_ans, opened, open_ans)

    print("\n== eval_loss by step ==")
    print(" ", loss_history(ADAPTER))
    print("\n== summary ==")
    summary("closed book", s_closed)
    summary("open book", s_open)
    if s_base:
        summary("base", s_base)
    print("\n== identity ==")
    for q, a in zip(IDENTITY, ident):
        flag = "OK " if "Hana" in a and not FOREIGN.search(a) else "BAD"
        print(f"  [{flag}] {q} -> {a[:160]!r}")
    worst = [it for it in sorted(closed + opened, key=lambda it: -len(it.get("invented", [])))[:12]
             if it.get("invented")]
    print("\nmost invented facts (details in", out, "):")
    for it in worst:
        print(f"  {it['id']}: {it['question'][:70]!r} -> {', '.join(it['invented'][:6])}")
    print("\nwrote", out)


if __name__ == "__main__":
    main()
