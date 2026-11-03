"""Step 1: check the machine and the stage-1 data before installing anything for training.

Run from the repo root:  python ai-agent/training/train/step1_env_check.py
Only reads; prints a report to paste back.
"""

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

TRAIN = Path(__file__).resolve().parents[1]
FINAL = TRAIN / "data" / "final"


def section(title):
    print(f"\n== {title} ==")


def run(cmd):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return (out.stdout or out.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"not available ({exc.__class__.__name__})"


section("System")
print("os:", platform.platform())
print("python:", sys.version.split()[0], sys.executable)
print("cpus:", os.cpu_count())
try:
    import psutil

    print("ram_gb:", round(psutil.virtual_memory().total / 2**30, 1))
except ImportError:
    print("ram_gb: unknown (psutil not installed)")
print("disk_free_gb:", round(shutil.disk_usage(TRAIN).free / 2**30, 1))

section("GPU (nvidia-smi)")
print(run(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"]))
print("cuda (driver max):", run(["nvidia-smi"]).split("CUDA Version:")[-1].split("|")[0].strip()
      if "CUDA Version" in run(["nvidia-smi"]) else "unknown")

section("Python packages")
for name in ("torch", "transformers", "peft", "trl", "datasets", "accelerate", "bitsandbytes"):
    try:
        mod = __import__(name)
        print(f"{name}: {getattr(mod, '__version__', '?')}")
    except Exception as exc:  # noqa: BLE001 - report any import problem
        print(f"{name}: missing ({exc.__class__.__name__})")
try:
    import torch

    print("torch.cuda.is_available:", torch.cuda.is_available())
    if torch.cuda.is_available():
        p = torch.cuda.get_device_properties(0)
        print("gpu0:", p.name, f"{p.total_memory / 2**30:.1f} GiB", "bf16:", torch.cuda.is_bf16_supported())
    print("mps (Apple):", getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available())
except ImportError:
    pass

section("Hugging Face")
print("HF_TOKEN set:", bool(os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")))
print("huggingface-cli:", run(["huggingface-cli", "whoami"])[:80])

section("Stage-1 data")
for name in ("knowledge_train.jsonl", "knowledge_val.jsonl", "cards_train.jsonl"):
    path = FINAL / name
    if not path.exists():
        print(f"{name}: MISSING")
        continue
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    chars = sorted(sum(len(m.get("content") or "") for m in r["messages"]) for r in rows)
    tools = sum(1 for r in rows if any(m.get("tool_calls") for m in r["messages"]))
    print(f"{name}: rows={len(rows)} chars p50={chars[len(chars) // 2]} max={chars[-1]} with_tool_calls={tools}")
card = TRAIN / "knowledge" / "cards" / "onprem" / "onprem-one-click-services.md"
if card.exists():
    print("literal password still in card:", "Str0ng" in card.read_text(encoding="utf-8"))
