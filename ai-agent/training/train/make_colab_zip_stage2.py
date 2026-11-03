"""Build ai-agent/hana_stage2_colab.zip: stage-2 scripts, task data, the stage-1 replay data, a pskit wheel and a
few example projects. In Colab it is unzipped to /content/ (training/, examples/, the wheel).

Run on your PC from the repo root:  python ai-agent/training/train/make_colab_zip_stage2.py
Builds the pskit wheel fresh from this checkout with `pip wheel` (needs the build backend, hatchling, from PyPI).
"""

import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

AI_AGENT = Path(__file__).resolve().parents[2]
REPO = AI_AGENT.parent
TRAINING = [
    "train/step1_env_check.py", "train/step2_prepare.py", "train/step3_train.py", "train/step4_eval.py",
    "train/step5_merge.py", "train/step6_chat.py",
    "train/s2_prepare.py", "train/s2_train.py", "train/s2_eval.py", "train/s2_chat.py", "train/COLAB_STAGE2.md",
    "train/s3_gguf.py", "train/s3_test_endpoint.py", "train/s3_publish_hf.py", "train/PUBLISH.md",
    "tools/run_tool.py", "tools/task_common.py",
    "data/final/task_train.jsonl", "data/final/task_val.jsonl", "data/final/TASK_README.md",
    "data/final_v2/knowledge_train.jsonl", "data/final_v2/identity_train.jsonl", "data/final_v2/knowledge_val.jsonl",
    "knowledge/index_source.jsonl",
]
EXAMPLES = ["01-hello-http", "04-queue-worker", "07-workflow-orders", "16-on-premises", "18-resources"]
SKIP = {"__pycache__", ".pskit", "node_modules", ".venv"}


def wheel(tmp):
    subprocess.run([sys.executable, "-m", "pip", "wheel", str(REPO), "--no-deps", "-q", "-w", tmp], check=True)
    wheels = sorted(Path(tmp).glob("py_serverless_kit-*.whl"))
    if not wheels:
        raise SystemExit("pip wheel did not produce a py_serverless_kit wheel")
    return wheels[-1]


def main():
    out = AI_AGENT / "hana_stage2_colab.zip"
    with tempfile.TemporaryDirectory() as tmp:
        whl = wheel(tmp)
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for rel in TRAINING:
                path = AI_AGENT / "training" / rel
                if not path.exists():
                    raise SystemExit(f"missing {path}")
                z.write(path, f"training/{rel}")
            for ex in EXAMPLES:
                root = REPO / "examples" / ex
                for f in sorted(root.rglob("*")):
                    if f.is_file() and not SKIP & set(f.relative_to(root).parts) and f.suffix != ".pyc":
                        z.write(f, f"examples/{ex}/{f.relative_to(root).as_posix()}")
            z.write(whl, whl.name)
    with zipfile.ZipFile(out) as z:
        bad = z.testzip()
        names = z.namelist()
    if bad:
        raise SystemExit(f"broken entry in zip: {bad}")
    print(f"{out} ({out.stat().st_size / 2**20:.1f} MiB, {len(names)} files), wheel {whl.name}")


if __name__ == "__main__":
    main()
