"""Stage 2, step B: LoRA training on top of the stage-1 merged model (checkpoint K).

Run in Colab:
  BASE=/content/drive/MyDrive/hana/hana-stage1-merged OUTPUT_DIR=/content/drive/MyDrive/hana/stage2 \
      python ./training/train/s2_train.py
Env (optional):
  EPOCHS   default 2
  LR       default 1e-4 (half of stage 1, so the stage-1 knowledge is not overwritten)
  BATCH    default 1 per step (sequences go up to 4096 tokens; accumulation keeps the effective batch at 16)
  SMOKE=1  30 steps only, saves nothing (speed and memory check)
Evaluates on two sets every 100 steps: eval_task_loss (picks the best checkpoint) and eval_knowledge_loss (should
stay near stage 1's value; if it climbs a lot, stage 2 is forgetting stage 1). Re-running resumes from the newest
checkpoint in OUTPUT_DIR.
"""

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

import torch  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from step3_train import Speed, _skip_old_torchao, require_drive  # noqa: E402

_skip_old_torchao()
from datasets import load_from_disk  # noqa: E402
from peft import LoraConfig, get_peft_model  # noqa: E402
from transformers import (AutoModelForCausalLM, AutoTokenizer, DataCollatorForSeq2Seq, Trainer,  # noqa: E402
                          TrainingArguments)

BASE = os.environ.get("BASE", str(HERE / "work" / "hana-stage1-merged"))
OUT = Path(os.environ.get("OUTPUT_DIR", str(HERE / "work" / "stage2")))
EPOCHS = float(os.environ.get("EPOCHS", "2"))
LR = float(os.environ.get("LR", "1e-4"))
BATCH = int(os.environ.get("BATCH", "1"))
SMOKE = os.environ.get("SMOKE") == "1"


def main():
    require_drive(BASE, OUT)
    if not Path(BASE, "config.json").exists():
        raise SystemExit(f"{BASE} is not a model folder (no config.json). Point BASE at hana-stage1-merged.")
    bf16 = torch.cuda.is_available() and torch.cuda.get_device_capability(0)[0] >= 8
    dtype = torch.bfloat16 if bf16 else torch.float16
    tok = AutoTokenizer.from_pretrained(BASE)
    model = AutoModelForCausalLM.from_pretrained(BASE, dtype=dtype, attn_implementation="sdpa")
    model.config.use_cache = False
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.enable_input_require_grads()
    model = get_peft_model(model, LoraConfig(
        r=32, lora_alpha=64, lora_dropout=0.05, bias="none", task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]))
    model.print_trainable_parameters()

    work = HERE / "work"
    train = load_from_disk(str(work / "s2_train"))
    evals = {"task": load_from_disk(str(work / "s2_val_task")),
             "knowledge": load_from_disk(str(work / "s2_val_knowledge"))}
    print(f"train={len(train)} val_task={len(evals['task'])} val_knowledge={len(evals['knowledge'])} "
          f"dtype={dtype} lr={LR} out={OUT}")

    wanted = dict(
        output_dir=str(OUT), num_train_epochs=EPOCHS, max_steps=30 if SMOKE else -1,
        per_device_train_batch_size=BATCH, gradient_accumulation_steps=max(1, 16 // BATCH),
        per_device_eval_batch_size=BATCH, learning_rate=LR, lr_scheduler_type="cosine", warmup_steps=20,
        weight_decay=0.0, max_grad_norm=1.0, fp16=not bf16, bf16=bf16, logging_steps=10,
        eval_strategy="steps", eval_steps=100, save_strategy="steps", save_steps=100, save_total_limit=3,
        load_best_model_at_end=True, metric_for_best_model="eval_task_loss", greater_is_better=False,
        report_to="none", dataloader_num_workers=2, seed=2200,
    )
    known = set(TrainingArguments.__dataclass_fields__)
    skipped = sorted(set(wanted) - known)
    if skipped:
        print("[args] not supported by this transformers version, skipped:", skipped)
    if "eval_strategy" in skipped or "save_strategy" in skipped:
        raise SystemExit("eval/save strategy argument missing in this transformers version; paste this output")
    trainer = Trainer(
        model=model, args=TrainingArguments(**{k: v for k, v in wanted.items() if k in known}),
        train_dataset=train, eval_dataset=evals,
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
    (final / "hana_stage.json").write_bytes(json.dumps(
        {"stage": "stage-2 tasks LoRA", "base": BASE, "metrics": metrics}, indent=2, default=str).encode("utf-8"))
    print("saved adapter to", final)


if __name__ == "__main__":
    main()
