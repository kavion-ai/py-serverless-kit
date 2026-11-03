# Stage 2 (tasks) on Google Colab: every command

Stage 2 teaches Hana to work with the 10 tools (search_docs, get_project, read_file, get_validation,
propose_plan, ask_user, set_config, write_file, validate, invoke_local) on **aws, azure, gcp and onprem**.
It trains a new LoRA on top of the stage-1 model and replays 25% stage-1 knowledge, at half the stage-1
learning rate, so Hana keeps what she learned in stage 1.

**Before you start:** stage 1 must be finished and its merge must be on Drive:
`/content/drive/MyDrive/hana/hana-stage1-merged/` (about 2.9 GB, see COLAB_STAGE1.md). Use a **T4 GPU**.

| Path | What | Survives a runtime reset? |
|---|---|---|
| `/content/drive/MyDrive/hana_stage2_colab.zip` | scripts, data, pskit wheel, example projects (upload once) | Yes |
| `/content/drive/MyDrive/hana/hana-stage1-merged/` | stage-1 model (the starting point) | Yes |
| `/content/drive/MyDrive/hana/stage2/` | checkpoints, `adapter_final`, `eval_stage2.md` | Yes |
| `/content/drive/MyDrive/hana/hana-stage2-merged/` | the final Hana model | Yes |
| `/content/training/...`, `/content/examples/...` | unzipped files | No: unzip again each session (cell 2) |

Everything that matters is written under `/content/drive/MyDrive/hana/`. The scripts stop with an error if
Drive isn't mounted.

## 0. Once: make the zip and put it on Drive

On your PC, from the repo root:

```
python ai-agent/training/train/make_colab_zip_stage2.py
```

Upload `ai-agent/hana_stage2_colab.zip` to the top of **My Drive**.

## 1. Start of EVERY session

**Cell 1: mount Drive**

```python
from google.colab import drive
drive.mount("/content/drive")
```

**Cell 2: check, unzip, install pskit, fix torchao**

```
!test -d /content/drive/MyDrive/hana/hana-stage1-merged && echo "STAGE-1 MODEL OK" || echo "STAGE-1 MODEL MISSING"
%cd /content
!unzip -o -q /content/drive/MyDrive/hana_stage2_colab.zip -d /content/
!pip install -q /content/py_serverless_kit-*.whl
!pip uninstall -y torchao
!ls /content/training/train /content/examples
```

You must see `STAGE-1 MODEL OK`. pskit is only used by the chat in step E (validate and local invoke); it
never deploys.

## 2. Step A: tokenize (about 3 min)

```
!BASE=/content/drive/MyDrive/hana/hana-stage1-merged python ./training/train/s2_prepare.py
```

It prints three lines (train, val task, val knowledge) with token sizes. `too_long` should be a handful at most.
Rerun this step in every new session before step B or C.

## 3. Step B: train (about 3 to 4 hours)

Smoke test (30 steps, saves nothing):

```
!SMOKE=1 BASE=/content/drive/MyDrive/hana/hana-stage1-merged python ./training/train/s2_train.py
```

The real run:

```
!BASE=/content/drive/MyDrive/hana/hana-stage1-merged OUTPUT_DIR=/content/drive/MyDrive/hana/stage2 python ./training/train/s2_train.py
```

- Every 100 steps it prints `eval_task_loss` and `eval_knowledge_loss`. Task loss should go down.
  Knowledge loss should stay close to stage 1's value (about 0.9). If it climbs above about 1.3, paste the
  output: stage 2 is forgetting stage 1.
- The best checkpoint (lowest `eval_task_loss`) is kept and used at the end.
- **If Colab disconnects:** cells 1 and 2, step A, then **the same command**. It resumes from the newest
  checkpoint on Drive.
- Options: `EPOCHS=2` (default), `LR=1e-4` (default), `BATCH=1` (default; 2 may run out of memory).

Check it is on Drive:

```
!ls -lh /content/drive/MyDrive/hana/stage2/ /content/drive/MyDrive/hana/stage2/adapter_final/
```

## 4. Step C: evaluate (about 1 hour for N=80)

Tool use on the task validation set:

```
!BASE=/content/drive/MyDrive/hana/hana-stage1-merged ADAPTER=/content/drive/MyDrive/hana/stage2/adapter_final python ./training/train/s2_eval.py
```

It prints `action` (right next tool, or text when it should answer), `args` (valid JSON with the right argument
names), `plan before change`, and two checks on the final answers. Options: `N=156` (all), `COMPARE=1`
(also score the stage-1 model, to see what stage 2 added). Writes `stage2/eval_stage2.md` on Drive.

Optional, stage-1 knowledge after stage 2 (the same test as stage 1, about 30 min with N=80):

```
!DATA=final_v2 N=80 MODEL_ID=/content/drive/MyDrive/hana/hana-stage1-merged ADAPTER=/content/drive/MyDrive/hana/stage2/adapter_final python ./training/train/step4_eval.py
```

## 5. Step D: merge into the final model (about 5 min)

```
!STAGE=2 DATA=final_v2 MODEL_ID=/content/drive/MyDrive/hana/hana-stage1-merged ADAPTER=/content/drive/MyDrive/hana/stage2/adapter_final MERGED=/content/drive/MyDrive/hana/hana-stage2-merged python ./training/train/step5_merge.py
```

```
!ls -lh /content/drive/MyDrive/hana/hana-stage2-merged/
```

```python
from google.colab import drive
drive.flush_and_unmount()   # waits until the 2.9 GB is on Drive; run cell 1 again to keep working
```

## 6. Step E: chat with Hana, tools working for real

Interactive. She works on a **copy** of the project; plans and questions are answered by you in the terminal:

```
!ENV="provider=onprem stage=dev mode=ask page=Functions" PROJECT=/content/examples/16-on-premises MERGED=/content/drive/MyDrive/hana/hana-stage2-merged python ./training/train/s2_chat.py
```

One message, no typing (plans are approved automatically):

```
!Q="add a GET /health endpoint that returns ok" ENV="provider=aws stage=dev mode=auto page=Functions" PROJECT=/content/examples/01-hello-http MERGED=/content/drive/MyDrive/hana/hana-stage2-merged python ./training/train/s2_chat.py
```

Projects in the zip: `01-hello-http`, `04-queue-worker`, `07-workflow-orders`, `16-on-premises`,
`18-resources`. Good things to try:
- "how do I add a schedule in studio?" (how-to with studio steps)
- "validate fails, fix it" (after you break the YAML with `/project` to look at it)
- "who made you?" (Asif Khan, with the LinkedIn link)
- "deploy it to prod" (she should explain the Deploy page, not do it)

In the chat: `/project` prints pskit.yml, `/reset` starts over with a fresh copy, `/quit` exits.

## 7. Backup to your PC

```
!cd /content/drive/MyDrive && zip -r -0 hana_stage2_backup.zip hana/hana-stage2-merged hana/stage2/adapter_final hana/stage2/eval_stage2.md
!ls -lh /content/drive/MyDrive/hana_stage2_backup.zip
```

Then on drive.google.com: right-click > Download, and keep it outside the git repo.

## Errors and fixes

| Error | Fix |
|---|---|
| `STAGE-1 MODEL MISSING` | Finish stage 1 first (COLAB_STAGE1.md steps 3 to 6), or check the Google account |
| `... is on Google Drive, but Drive is not mounted` | Run cell 1, then the same command |
| `is not a model folder (no config.json)` | BASE must be the `hana-stage1-merged` folder |
| `ImportError ... torchao` | `!pip uninstall -y torchao` (every session) |
| `No such file ... s2_train` | New session: rerun step A |
| `CUDA out of memory` | Keep `BATCH=1`; or `MAX_LEN=3072` in step A (drops the longest conversations) |
| `No module named py_serverless_kit` (step E) | Rerun cell 2 (installs the pskit wheel) |
