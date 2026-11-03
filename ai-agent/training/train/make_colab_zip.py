"""Build ai-agent/hana_stage1_colab.zip: the stage-1 scripts and data, unzipped in Colab to /content/training/.

Run on your PC from anywhere:  python ai-agent/training/train/make_colab_zip.py
(Don't use tar for this: Git Bash's GNU tar writes a tar archive even when the name ends in .zip.)
"""

import zipfile
from pathlib import Path

AI_AGENT = Path(__file__).resolve().parents[2]
ITEMS = [
    "training/train/step1_env_check.py", "training/train/step2_prepare.py", "training/train/step3_train.py",
    "training/train/step4_eval.py", "training/train/step5_merge.py", "training/train/step6_chat.py",
    "training/train/COLAB_STAGE1.md",
    "training/data/final",  # step 3's smoke test reads data/final/knowledge_val.jsonl
    "training/data/final_v2",
    "training/knowledge/index_source.jsonl",  # search index for step 6
]


def main():
    out = AI_AGENT / "hana_stage1_colab.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for item in ITEMS:
            path = AI_AGENT / item
            files = [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file())
            for f in files:
                z.write(f, f.relative_to(AI_AGENT).as_posix())
    with zipfile.ZipFile(out) as z:
        bad = z.testzip()
        names = z.namelist()
    if bad:
        raise SystemExit(f"broken entry in zip: {bad}")
    print(f"{out} ({out.stat().st_size / 2**20:.1f} MiB, {len(names)} files)")
    print("\n".join(names))


if __name__ == "__main__":
    main()
