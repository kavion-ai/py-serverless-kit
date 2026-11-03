"""Step 3: stage-1 LoRA training on the tokenized knowledge set (output of step2_prepare.py).

Run:  python ai-agent/training/train/step3_train.py
Env (optional):
  MODEL_ID    default Qwen/Qwen2.5-1.5B-Instruct (must match step 2)
  OUTPUT_DIR  default ai-agent/training/train/work/stage1  (on Colab, point it at Google Drive so it survives)
  EPOCHS      default 2
  BATCH       default 2 per step (accumulation keeps the effective batch at 16)
  SMOKE=1     train 30 steps only, to check speed and memory first
Re-running resumes from the newest checkpoint in OUTPUT_DIR.
"""

import json
import os
import time
from pathlib import Path

os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")  # must be set before torch loads

import torch  # noqa: E402
from datasets import load_from_disk
from peft import LoraConfig, get_peft_model
from transformers import (AutoModelForCausalLM, AutoTokenizer, DataCollatorForSeq2Seq, Trainer,
                          TrainerCallback, TrainingArguments)


def _skip_old_torchao():
    """Colab ships torchao 0.10; peft refuses it even though LoRA here never uses torchao. Skip that check."""
    try:
        import peft.tuners.lora.torchao as peft_torchao
        peft_torchao.is_torchao_available = lambda: False
    except (ImportError, AttributeError):
        pass


_skip_old_torchao()


def require_drive(*paths):
    """Stop if a path is under /content/drive but Drive is not mounted.

    Without the mount, /content/drive/MyDrive/... is an ordinary folder on the Colab disk and is deleted with the
    runtime (this lost the first stage-1 v2 model).
    """
    for path in paths:
        if str(path).startswith("/content/drive") and not os.path.ismount("/content/drive"):
            raise SystemExit(f"{path} is on Google Drive, but Drive is not mounted. Run first:\n"
                             "  from google.colab import drive\n  drive.mount('/content/drive')")


HERE = Path(__file__).resolve().parent
TRAIN = HERE.parent
MODEL_ID = os.environ.get("MODEL_ID", "Qwen/Qwen2.5-1.5B-Instruct")
OUT = Path(os.environ.get("OUTPUT_DIR", str(HERE / "work" / "stage1")))
EPOCHS = float(os.environ.get("EPOCHS", "2"))
SMOKE = os.environ.get("SMOKE") == "1"
BATCH = int(os.environ.get("BATCH", "2"))  # 4 ran out of memory on a T4 (152k-token vocab logits)


class Speed(TrainerCallback):
    """Print seconds per step and an ETA once, after the first 10 steps."""

    def on_step_end(self, args, state, control, **kwargs):
        if state.global_step == 1:
            self.t0 = time.time()
        if state.global_step == 11:
            per = (time.time() - self.t0) / 10
            left = (state.max_steps - state.global_step) * per
            mem = torch.cuda.max_memory_allocated() / 2**30
            print(f"\n[speed] {per:.1f} s/step, {state.max_steps} steps, ETA {left / 60:.0f} min, peak GPU {mem:.1f} GiB\n")


def main():
    require_drive(OUT)
    bf16 = torch.cuda.is_available() and torch.cuda.get_device_capability(0)[0] >= 8  # T4 (7.5) -> fp16
    dtype = torch.bfloat16 if bf16 else torch.float16
    tok = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForCausalLM.from_pretrained(MODEL_ID, dtype=dtype, attn_implementation="sdpa")
    model.config.use_cache = False
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.enable_input_require_grads()

    lora = LoraConfig(
        r=32, lora_alpha=64, lora_dropout=0.05, bias="none", task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    )
    model = get_peft_model(model, lora)  # adapter weights stay fp32, base stays fp16/bf16
    model.print_trainable_parameters()

    train = load_from_disk(str(HERE / "work" / "tok_train"))
    val = load_from_disk(str(HERE / "work" / "tok_val"))
    print(f"train={len(train)} val={len(val)} dtype={dtype} out={OUT}")

    wanted = dict(
        output_dir=str(OUT),
        num_train_epochs=EPOCHS,
        max_steps=30 if SMOKE else -1,
        per_device_train_batch_size=BATCH,
        gradient_accumulation_steps=max(1, 16 // BATCH),  # effective batch 16
        per_device_eval_batch_size=BATCH,
        learning_rate=2e-4,
        lr_scheduler_type="cosine",
        warmup_steps=20,
        weight_decay=0.0,
        max_grad_norm=1.0,
        fp16=not bf16,
        bf16=bf16,
        logging_steps=10,
        eval_strategy="steps",
        eval_steps=100,
        save_strategy="steps",
        save_steps=100,
        save_total_limit=3,
        # stage-1 v2 had its lowest eval_loss at step 600 of 915; keep that checkpoint and end on it
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        report_to="none",
        dataloader_num_workers=2,
        seed=2100,
    )
    # transformers renames/removes arguments between versions: pass only the ones this version knows.
    known = set(TrainingArguments.__dataclass_fields__)
    skipped = sorted(set(wanted) - known)
    if skipped:
        print("[args] not supported by this transformers version, skipped:", skipped)
    if "eval_strategy" in skipped or "save_strategy" in skipped:
        raise SystemExit("eval/save strategy argument missing in this transformers version; paste this output")
    args = TrainingArguments(**{k: v for k, v in wanted.items() if k in known})
    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=train,
        eval_dataset=val,
        data_collator=DataCollatorForSeq2Seq(tok, padding=True, pad_to_multiple_of=8, label_pad_token_id=-100),
        callbacks=[Speed()],
    )
    resume = any(OUT.glob("checkpoint-*")) and not SMOKE
    trainer.train(resume_from_checkpoint=True if resume else None)
    metrics = trainer.evaluate()
    print("final eval:", json.dumps({k: round(v, 4) for k, v in metrics.items() if isinstance(v, float)}))
    if SMOKE:
        print("smoke run done (adapter not saved)")
        return

    final = OUT / "adapter_final"
    model.save_pretrained(str(final))
    tok.save_pretrained(str(final))
    print("saved adapter to", final)
    smoke_test(model, tok)


def smoke_test(model, tok):
    """Three greedy answers with Hana's real system prompt, to eyeball before step 4."""
    row = json.loads((TRAIN / "data" / "final" / "knowledge_val.jsonl").read_text(encoding="utf-8").splitlines()[0])
    system, tools = row["messages"][0]["content"], row.get("tools")
    model.eval()
    model.config.use_cache = True
    for question in (
        "who are you?",
        "which flag of pskit deploy picks the stage?",
        "where in studio do I add a queue resource?",
    ):
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": question}]
        text = tok.apply_chat_template(msgs, tools=tools, tokenize=False, add_generation_prompt=True)
        ids = tok(text, return_tensors="pt", add_special_tokens=False).to(model.device)
        with torch.no_grad():
            out = model.generate(**ids, max_new_tokens=220, do_sample=False)
        print(f"\n### Q: {question}\n{tok.decode(out[0][ids['input_ids'].shape[1]:], skip_special_tokens=False)}")


if __name__ == "__main__":
    main()
