# Stage 1 (knowledge) on Google Colab: every command

The exact path that produces the stage-1 model (`hana-stage1-merged`). Run the cells in order in a Colab
notebook with a **T4 GPU** (Runtime > Change runtime type > T4 GPU).

Model: `Qwen/Qwen2.5-1.5B-Instruct`, LoRA r=32 / alpha=64, data `data/final_v2`, 3 epochs.
Last result: eval_loss 0.931, searched in 225 of 225 cases where expected, open-book recall 39%.

## The one rule: everything that matters goes to Google Drive

The Colab disk (`/content/...`) is **deleted** whenever the runtime disconnects, resets or changes type.
Only Google Drive survives. So:

1. **Mount Drive first, in every session**, before any step (cell 1 below).
2. Every output path is under `/content/drive/MyDrive/hana/`.
3. If Drive is **not** mounted, `/content/drive/MyDrive/...` is just an ordinary folder on the Colab disk,
   and it disappears with the runtime. This is how the first trained model was lost. Steps 3 and 5 now
   stop with an error if Drive isn't mounted.
4. Check the files on **drive.google.com** (same Google account) after training and after merging,
   before closing Colab.

| Path | What | Survives a runtime reset? |
|---|---|---|
| `/content/drive/MyDrive/hana_stage1_colab.zip` | Scripts + data (you upload once) | Yes |
| `/content/drive/MyDrive/hana/stage1_v2/` | Checkpoints, `adapter_final`, `eval_stage1.md` | Yes |
| `/content/drive/MyDrive/hana/hana-stage1-merged/` | The merged stage-1 model, about 2.9 GB | Yes |
| `/content/training/...` | Unzipped scripts and data | No, unzip again each session (cell 2) |
| `/content/training/train/work/tok_train`, `tok_val` | Tokenized data from step 2 | No, rerun step 2 (about 2 min) |

## 0. Once: make the zip and put it on Drive

On your PC, from the repo root:

```
python ai-agent/training/train/make_colab_zip.py
```

It writes `ai-agent/hana_stage1_colab.zip` and tests it. (Don't use `tar`: Git Bash's GNU tar writes a tar archive even when the name ends in `.zip`, and Colab's unzip rejects it.)

Upload `hana_stage1_colab.zip` to **My Drive** (top level) at drive.google.com. Then no session needs an
upload again.

`data/final` must be in the zip: step 3's smoke test reads `data/final/knowledge_val.jsonl`.
`knowledge/index_source.jsonl` is the search index step 6 uses.

## 1. Start of EVERY session

**Cell 1: mount Google Drive** (sign in with the account that holds `hana_stage1_colab.zip`)

```python
from google.colab import drive
drive.mount("/content/drive")
```

**Cell 2: check the mount, unzip, fix torchao**

```
!test -d /content/drive/MyDrive && echo "DRIVE OK" || echo "DRIVE NOT MOUNTED - run cell 1"
!ls /content/drive/MyDrive/
!mkdir -p /content/drive/MyDrive/hana
%cd /content
!unzip -o -q /content/drive/MyDrive/hana_stage1_colab.zip -d /content/
!pip uninstall -y torchao
!ls /content/training/train
```

You must see `DRIVE OK`, and `hana_stage1_colab.zip` in the `My Drive` listing. If the listing shows
someone else's files, you signed in with the wrong account: Runtime > Disconnect and delete runtime, then run
cell 1 again and choose the right account.

`torchao` must go every session: Colab ships 0.10 and peft refuses to import with it.

**Cell 3 (optional): see what is already saved**

```
!ls -lh /content/drive/MyDrive/hana/ /content/drive/MyDrive/hana/* 2>/dev/null
```

## 2. Step 1: check the environment

```
!python ./training/train/step1_env_check.py
```

Prints GPU, library versions and data counts. Nothing to install if torch, transformers 5.x, peft and datasets
are listed. `!nvidia-smi --query-gpu=name,memory.total --format=csv` also shows the GPU.

## 3. Step 2: tokenize (about 2 min)

```
!DATA=final_v2 python ./training/train/step2_prepare.py
```

Options: `MODEL_ID=...` (default Qwen/Qwen2.5-1.5B-Instruct), `MAX_LEN=2048`. It adds `identity_train.jsonl`
×3, removes password literals and puts the loss on assistant tokens only. Rerun it in every new session before
step 3 or step 4.

## 4. Step 3: train (about 3 h 45 min, 915 steps)

Smoke test first (30 steps, about 5 min, saves nothing), to see speed and memory:

```
!SMOKE=1 python ./training/train/step3_train.py
```

The real run, saving to Drive:

```
!OUTPUT_DIR=/content/drive/MyDrive/hana/stage1_v2 EPOCHS=3 python ./training/train/step3_train.py
```

- A checkpoint is saved to Drive every 100 steps (the newest 3 are kept). Training ends on the best one
  (lowest eval_loss).
- **If Colab disconnects:** run cells 1 and 2 again, rerun step 2, then run **the same command**. It resumes
  from the newest `checkpoint-*` in `stage1_v2`.
- Keep the browser tab open. Free Colab stops idle or long sessions; Colab Pro is more stable for 4 hours.
- `BATCH=2` is the default; 4 runs out of memory on a T4.

When it ends (`saved adapter to ...` and 3 smoke answers), check that it is on Drive:

```
!ls -lh /content/drive/MyDrive/hana/stage1_v2/ /content/drive/MyDrive/hana/stage1_v2/adapter_final/
```

`adapter_final/` must hold `adapter_model.safetensors` (about 150 MB), `adapter_config.json` and tokenizer files.

## 5. Step 4: evaluate (about 30–40 min)

```
!DATA=final_v2 ADAPTER=/content/drive/MyDrive/hana/stage1_v2/adapter_final python ./training/train/step4_eval.py
```

Options: `N=80` (fewer questions, faster), `BASE=1` (also score the untrained model), `GEN_BATCH=8`.
Writes `stage1_v2/eval_stage1.md` on Drive.

## 6. Step 5: merge into one model (checkpoint K, about 5 min)

```
!DATA=final_v2 ADAPTER=/content/drive/MyDrive/hana/stage1_v2/adapter_final MERGED=/content/drive/MyDrive/hana/hana-stage1-merged python ./training/train/step5_merge.py
```

All 3 lines should say `[same]`. Then check, and make Drive finish writing the 2.9 GB before you close Colab:

```
!ls -lh /content/drive/MyDrive/hana/hana-stage1-merged/
```

```python
from google.colab import drive
drive.flush_and_unmount()   # waits until every file is written to Drive; run cell 1 again to keep working
```

Expect `model.safetensors` (about 2.9 GB), `config.json`, tokenizer files, `hana_stage.json` and `README.md`.
Stage 2 starts from this folder. Look at it on drive.google.com too.

If you only have the adapter (the merge was lost), just rerun step 5: no retraining needed.

## 7. Step 6: chat with the merged model

Interactive (`/reset` clears, `/quit` exits):

```
!MERGED=/content/drive/MyDrive/hana/hana-stage1-merged python ./training/train/step6_chat.py
```

One question, no typing:

```
!Q="can u provide step for studio how to create a postgress db" MERGED=/content/drive/MyDrive/hana/hana-stage1-merged python ./training/train/step6_chat.py
```

Options: `ENV="provider=aws stage=dev mode=ask page=none"`, `TEMPERATURE=0.3`, `ONE_WAY=0` (the training system
prompt without the one-way rule). `[search]` lines show what Hana searched for.

## 8. Second copy on your PC (do it once the merge is done)

Drive alone is one copy; folders get deleted or the wrong account gets used. Zip without checkpoints (about
3.2 GB, the checkpoints are only for resuming a run):

```
!cd /content/drive/MyDrive && zip -r -0 hana_backup_small.zip hana -x "*/checkpoint-*"
!ls -lh /content/drive/MyDrive/hana_backup_small.zip
```

Then on drive.google.com: right-click `hana_backup_small.zip` > Download, and keep it outside the git repo
(for example `C:\Users\asif.khan\Documents\hana_backup\`).

Other backups:

```
!du -sh /content/drive/MyDrive/hana/*
!cd /content/drive/MyDrive && zip -r -0 hana_backup.zip hana
!python -c "from huggingface_hub import snapshot_download; snapshot_download('Qwen/Qwen2.5-1.5B-Instruct', local_dir='/content/drive/MyDrive/hana/base-Qwen2.5-1.5B-Instruct')"
```

(The last one is an offline copy of the base model; only needed if Hugging Face is unreachable.)

## Errors seen and fixes

| Error | Fix |
|---|---|
| `... is on Google Drive, but Drive is not mounted` | Run cell 1 (`drive.mount`), then the same command |
| `ls: cannot access '/content/drive/MyDrive/hana/'` after a reset | Files were written while Drive wasn't mounted, or a different Google account is mounted. Check the account and drive.google.com (Search, Trash) |
| `ImportError ... torchao` when peft loads | `!pip uninstall -y torchao` (every new session) |
| `CUDA out of memory` with BATCH=4 | Keep the default `BATCH=2` |
| `TypeError ... group_by_length` | Old script; use the current `step3_train.py` |
| `No such file ... tok_train` | New session: rerun step 2 |
| `unzip: cannot find ... hana_stage1_colab.zip` | Upload it to the top of My Drive (section 0), or into `/content` and unzip from there |

## v1 (first run, replaced by v2)

`DATA=final` (no search-first, no identity data), 2 epochs, `OUTPUT_DIR=/content/drive/MyDrive/hana/stage1`.
eval_loss 1.269, searched in 46 of 99 cases where expected. Kept only for comparison.
