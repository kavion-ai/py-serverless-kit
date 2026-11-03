"""Step 5: merge the stage-1 LoRA adapter into the base model -> stage-1 checkpoint K (a full fp16 model).

Run:  ADAPTER=/content/drive/MyDrive/hana/stage1_v2/adapter_final \
      MERGED=/content/drive/MyDrive/hana/hana-stage1-merged python ./training/train/step5_merge.py
Env (optional):
  MODEL_ID  default Qwen/Qwen2.5-1.5B-Instruct (must match steps 2-4)
  ADAPTER   default ai-agent/training/train/work/stage1/adapter_final
  MERGED    default <ADAPTER>/../../hana-stage1-merged
  STAGE     2 for the stage-2 merge (MODEL_ID=<stage-1 merge folder>); labels the README. Default 1
Checks that the merged model predicts the same tokens as base + adapter, then saves model, tokenizer and a
README to MERGED (about 3 GB). Stage 2 trains a new LoRA on top of this folder.
"""

import json
import os
import sys
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from step3_train import _skip_old_torchao, require_drive  # noqa: E402  (Colab's old torchao breaks peft)

_skip_old_torchao()
from peft import PeftModel  # noqa: E402
from step2_prepare import clean, load  # noqa: E402

MODEL_ID = os.environ.get("MODEL_ID", "Qwen/Qwen2.5-1.5B-Instruct")
ADAPTER = Path(os.environ.get("ADAPTER", str(HERE / "work" / "stage1" / "adapter_final")))
MERGED = Path(os.environ.get("MERGED", str(ADAPTER.parent.parent / "hana-stage1-merged")))
STAGE = os.environ.get("STAGE", "1")  # 2 = merging the stage-2 adapter (MODEL_ID = the stage-1 merge)
QUESTIONS = ("who are you?", "which flag of pskit deploy picks the stage?")


def prompts(tok):
    """Two identity/search questions plus one real open-book conversation from the val set."""
    row = next(r for r in load("knowledge_val.jsonl") if any(m["role"] == "tool" for m in r["messages"]))
    messages, tools = clean(row, {"redacted": 0})
    tool_i = next(i for i, m in enumerate(messages) if m["role"] == "tool")
    system = messages[0]
    out = [[system, {"role": "user", "content": q}] for q in QUESTIONS] + [messages[: tool_i + 1]]
    return [tok.apply_chat_template(m, tools=tools, tokenize=False, add_generation_prompt=True) for m in out]


def answer(model, tok, text):
    ids = tok(text, return_tensors="pt", add_special_tokens=False).to(model.device)
    with torch.no_grad():
        out = model.generate(**ids, max_new_tokens=160, do_sample=False)
        logits = model(**ids).logits[0, -1].float()
    return tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True).strip(), logits


def main():
    require_drive(ADAPTER, MERGED)
    tok = AutoTokenizer.from_pretrained(str(ADAPTER))
    bf16 = torch.cuda.is_available() and torch.cuda.get_device_capability(0)[0] >= 8
    dtype = torch.bfloat16 if bf16 else torch.float16
    base = AutoModelForCausalLM.from_pretrained(MODEL_ID, dtype=dtype, device_map="cuda")
    model = PeftModel.from_pretrained(base, str(ADAPTER)).eval()
    texts = prompts(tok)
    before = [answer(model, tok, t) for t in texts]

    merged = model.merge_and_unload().eval()
    after = [answer(merged, tok, t) for t in texts]
    print("== base + adapter vs merged ==")
    same_all = True
    for t, (a1, l1), (a2, l2) in zip(texts, before, after):
        same = a1 == a2
        same_all &= same
        diff = (l1 - l2).abs().max().item()
        print(f"[{'same' if same else 'DIFF'}] max logit diff {diff:.3f} | {a2[:150]!r}")
        if not same:
            print(f"        adapter said: {a1[:150]!r}")
    if not same_all:
        print("note: small fp16 differences can change a greedy token; paste this output before using the merge")

    MERGED.mkdir(parents=True, exist_ok=True)
    merged.save_pretrained(str(MERGED), safe_serialization=True)
    tok.save_pretrained(str(MERGED))
    info = {"base_model": MODEL_ID, "adapter": str(ADAPTER), "stage": "stage-1 knowledge (checkpoint K)" if STAGE == "1" else "stage-2 tasks (final Hana model)",
            "dtype": str(dtype).replace("torch.", "")}
    (MERGED / "hana_stage.json").write_bytes(json.dumps(info, indent=2).encode("utf-8"))
    if STAGE == "1":
        head = f"# Hana, stage-1 checkpoint K\n\n{MODEL_ID} with the stage-1 knowledge LoRA merged in. "
        tail = "Stage 2 (tasks) trains a new LoRA on top of this folder; export to GGUF / Ollama comes after stage 2.\n"
    else:
        head = f"# Hana, stage 2 (final)\n\n{MODEL_ID} (the stage-1 merge) with the stage-2 task LoRA merged in. "
        tail = "Next: export to GGUF / Ollama.\n"
    (MERGED / "README.md").write_bytes(
        (head + "Created by Asif Khan (https://www.linkedin.com/in/asif-khan-31b7a8187/).\n\n" + tail).encode("utf-8"))
    size = sum(p.stat().st_size for p in MERGED.rglob("*") if p.is_file()) / 2**30
    print(f"\nsaved merged model to {MERGED} ({size:.1f} GiB)")
    print("files:", ", ".join(sorted(p.name for p in MERGED.iterdir())))


if __name__ == "__main__":
    main()
