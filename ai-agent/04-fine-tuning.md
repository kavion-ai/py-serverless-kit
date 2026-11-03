# 4. Fine-tuning: data, training, export, retraining

## 4.1 What fine-tuning is for (and what it isn't)

| Teach with fine-tuning (behaviour) | Leave to retrieval / tools (facts) |
|---|---|
| Idiomatic `pskit.yml` (structure, `${env:...}` for secrets, portable handlers, provider `options:` only for provider-specific things) | The current list of options, providers, regions, drivers |
| The tool protocol: when to search, read, validate, invoke; parallel reads; never claiming success without a check | Error messages of the current version |
| Planning format, Ask/Auto etiquette, asking one precise question when information is missing | What each studio page does |
| Reading a Terraform/provider/runtime error and mapping it to a cause class | Exact CLI flags |
| Citing sources, saying "not supported on <provider>" instead of making things up | Changelog deltas |
| Handler code style (sync/async, `Event`/`Context`, `BatchResult`) | |

Target: the fine-tuned **small** model reaches the stock **medium** model's score on `pskit-bench`, and the fine-tuned
medium model gets close to the hosted reference (see 07).

## 4.2 Data sources and generators

All generators live in `ai-agent/training/gen/`, import `py_serverless_kit` directly (fast, in-process
validation), and write JSONL in OpenAI chat format with `tools`. **Every sample that can be checked is checked;
samples that fail are dropped or turned into negative/preference data.**

| # | Generator | How | Check | Target count |
|---|---|---|---|---|
| G1 | **Docs Q&A** | Teacher model reads one doc chunk (+ neighbours) and writes 3–8 user questions of different kinds (how-to, why, compare, "can I …"), then answers *with a `search_docs` tool call first* and a cited answer | A second teacher pass grades whether the answer is fully supported by the chunk; unsupported → dropped | 6–8k |
| G2 | **Reverse config generation** | A **sampler** builds random *valid* configs from the schema + provider capabilities (provider × trigger types × resources × workflows × stages). The teacher then writes the *natural-language request* a user would type for it. Pair = request → tool calls producing that config | Correct by construction: the sampler's config passes validation; the model's tool calls are replayed and the result must validate and match structurally | 6–10k |
| G3 | **Break-and-fix (mutation)** | Take valid configs (examples + G2) and apply mutation operators: drop a required field, a trigger the provider can't run, bad cron, unknown provider option, undefined `${self:...}`, wrong handler path, dangling workflow `next`, duplicate route, wrong resource key, Python 3.10-only syntax in a handler … Capture the **real** validator/invoke error | The fix must make validation pass **and** be minimal (diff size limit). Several fixes possible → the shortest wins | 5–8k |
| G4 | **Runtime debug** | Handlers with injected bugs (wrong event field, missing import, sync/async mix-up, returning a non-serialisable object, wrong `BatchResult`) run with `pskit invoke` → traceback | Fixed handler must pass the same invoke + a hidden assertion | 2–3k |
| G5 | **Deploy/Terraform debug** | Captured real failures from `scripts/validate_all_providers.py`, CI logs, issue reports, plus synthetic ones from known provider error formats (permission denied, quota, name conflict, region not available) | Expected outcome labels (fix config / hand back to user with steps) checked against a rubric | 1–2k |
| G6 | **Agent trajectories** | The *teacher* runs the real agent loop with real tools in a sandbox project (Docker, no cloud credentials; cloud tools return recorded or simulated outputs) on task prompts drawn from G2–G5 and from scripted scenarios ("add a scheduled job that…", "move this from AWS to GCP", "my queue worker never fires") | Keep only trajectories whose final state passes the task's checks; also keep a *shortest successful* version | 3–5k |
| G7 | **Clarify / refuse / hand back** | Ambiguous requests, unsupported features, destructive requests in Auto mode, out-of-scope questions, prompt-injection in tool output | Rubric: asked the right single question / declined to escalate / didn't follow injected text | 1k |
| G8 | **Studio UI questions** | "Where do I …" from `docs/studio.md` + the page list | Graded like G1 | 0.5–1k |
| G9 | **General replay** | A slice of a permissive general instruction + code dataset | Keeps general coding and chat ability (stops forgetting) | 10–15% of the mix |

Approximate mix of the final SFT set (~30k samples): Q&A 22%, generation 22%, fix 20%, debug 10%,
trajectories 13%, clarify/safety 4%, studio 2%, replay ~7–12% (tuned with eval).

### Seeds that keep it grounded
- `examples/` (21 projects) → seed configs, gold few-shot, eval fixtures.
- Test assertions with `match=` error strings → G3 mutation operators (each tested validator error becomes an operator).
- `docs/troubleshooting.md` → G5 seeds.

### Teacher model choice: check the licence
The teacher writes questions, answers and trajectories. **Check the teacher's terms on using its outputs to train
another model before generating.** Some hosted model terms restrict training competing models on their outputs.
Safe default: an **open-weight Apache-2.0/MIT teacher** (the largest model of the chosen family, or another
permissively licensed large model) running on rented GPUs. A hosted frontier model can still be the **eval
reference and grader** where its terms allow that use.

## 4.3 Data quality pipeline

```text
generate -> parse/schema check -> execute checks (validate / invoke / replay tool calls)
         -> dedupe (exact + MinHash near-dup across questions)
         -> decontaminate (remove anything too close to pskit-bench test items)
         -> redact (no real hosts, keys, emails; synthetic names only)
         -> balance (per provider, per trigger type, per tool; on-prem is large in docs and must not dominate)
         -> human spot check (50 random samples per generator per release; a failure rate > 5% blocks the build)
```

Every sample records `pskit_version`, `generator`, `seed`, `checks_passed`. The dataset is versioned with
`ai-agent/training/data/<version>/manifest.json` (hashes), stored outside git (object storage or HF dataset,
private).

## 4.4 Training recipe

**Method:** LoRA SFT (QLoRA for the large size) on the instruct model, with loss on assistant/tool-call tokens only.
Then optionally **preference tuning** (DPO or KTO) on pairs from G3/G6 (successful vs failed trajectory for the same
task, short fix vs long fix), which improves tool discipline and stops "claims done without checking".

| Setting | Small (7–8B) | Medium MoE (~30B-A3B) | Large (24–32B) |
|---|---|---|---|
| Method | LoRA (bf16) | LoRA on attention + expert-shared layers (check the framework's MoE support) | QLoRA 4-bit |
| Rank / alpha | 32 / 64 | 32 / 64 | 64 / 128 |
| LR / schedule | 1e-4, cosine, 3% warmup | 1e-4 | 1e-4 |
| Epochs | 2–3 | 2 | 2 |
| Max seq len | 16k (packing on, trajectories up to 32k unpacked) | 32k | 32k |
| Hardware (estimate) | 1× 48–80 GB GPU, a few hours | 1–2× 80 GB GPU | 1–2× 80 GB GPU |
| Then | DPO 1 epoch, β≈0.1 | same | same |

Tooling: **Unsloth** or **Axolotl** (configs as YAML in `ai-agent/training/configs/`), **TRL** for DPO, tracked with
an experiment tracker (MLflow, W&B or similar). The chat template and tool-call format must be **exactly** the base
model's. A mismatch is the most common cause of a model that "forgets" tools after fine-tuning. A unit test renders
10 samples with the tokenizer's template and checks it round-trips.

Hyperparameters are starting points. Sweep LR and rank on the small model against `pskit-bench` dev before training
the larger ones.

## 4.5 Export and packaging

```text
LoRA adapter --merge--> fp16/bf16 safetensors
   ├── GGUF (llama.cpp convert) -> quantise: Q4_K_M (default), Q5_K_M, Q8_0   -> Ollama image / native Ollama
   └── AWQ or FP8                                                          -> vLLM image
```

- Publish weights to a model hub (e.g. Hugging Face `kavion/pskit-agent-<size>-<pskit-version>`) with a **model
  card**: base model and licence, training data description, intended use, eval scores, known limits.
- Also publish the **LoRA adapter alone** (small). vLLM can load it on the stock base (multi-LoRA), so a server can
  serve several pskit versions from one base.
- Quantisation is re-evaluated: Q4 must lose ≤ 2 points on `pskit-bench` vs bf16, otherwise ship Q5 as default.

## 4.6 Staying current (the release cadence problem)

pskit releases often. Retraining on every patch release would cost too much and isn't needed:

| pskit change | What happens |
|---|---|
| Patch / docs-only | Rebuild the **knowledge index** only (automatic in the release CI). Model unchanged |
| Minor (new options, providers, pages) | Index rebuilt; nightly eval of the current model on the new version's bench. Retrain only if the score drops more than the threshold (e.g. 3 points) or a new tool is added |
| New agent tool / protocol change | Retrain (trajectory data must include the tool) |
| Major | Full regenerate + retrain |

The studio checks compatibility: the model image reports `trained_for: 2.10` and `tool_protocol: 1`. Studio
accepts any model with the same `tool_protocol`, and shows "model trained for 2.10, you have 2.14: answers use the
2.14 docs" (informational).

## 4.7 Training infrastructure

- Runs on rented GPUs (RunPod / Lambda / a cloud GPU VM), started by a script, not by people clicking. Optionally
  described as a pskit project itself (dog-fooding: a workflow `generate → train → eval → publish`).
- Reproducible: pinned framework versions in a training container, seed fixed, dataset manifest hash recorded in
  the model card.
- Separate repo or `ai-agent/training/` excluded from the wheel (`pyproject` already packages only `src/`).

## 4.8 Feedback loop (after launch)

- 👍/👎 and "this was wrong because…" in the chat. Stored locally in the session.
- **Opt-in** "Share this session to improve the model": redacted session export, sent only when the user clicks
  and reviews it. Never automatic.
- Good sessions → new SFT samples; 👎 sessions with a later correct fix → DPO pairs; recurring failures → new eval items.
