# 9. Roadmap, team, cost, risks

Principle: **usable value early, fine-tuning when we can measure it.** The agent loop, tools and UI are useful with
a stock model or the Claude API, and they're needed anyway to generate trajectory data and to run the benchmark.
So they come first.

## 9.1 Phases

| Phase | Weeks | Deliverables | Exit criteria |
|---|---|---|---|
| **0. Foundations** | 1–2 | Licence review of base/teacher candidates; `pskit-bench` v0 (100 dev items across suites, fixtures from `examples/`); knowledge index builder + CI step; `FakeModel` test harness | Bench runs end to end on a stock model and on the Claude API; index builds in CI |
| **1. Ask** | 3–5 | `studio/agent/` loop with tier-0 tools, retrieval, citations, model client (OpenAI-compatible + Claude), chat panel (Ask only), *Existing endpoint* + *Native Ollama* backends, `pskit agent ask` | QA ≥ 70% on stock medium model; 0 safety violations; docs `docs/assistant.md` |
| **2. Create & fix** | 6–8 | Tier-1/2 tools, changesets + diff UI + undo, Plan only / Ask / Auto modes, verify + repair loop, *Fix with assistant* on validation issues | GEN pass@1 ≥ 60% and FIX ≥ 60% on stock medium; all policy tests green |
| **3. Fine-tune v1** | 6–10 (parallel with 2) | Generators G1–G9, data pipeline, SFT (+DPO) for small and medium, export GGUF, Ollama images, eval gate, model card, image CI (sign, SBOM) | Fine-tuned medium beats stock medium by ≥ 10 points on GEN/FIX and meets 07 §7.5 gates |
| **4. Run anywhere & debug** | 9–12 | Runtime installer (local Docker / saved server via SSH tunnel / GPU detection), setup wizard, `pskit agent up/down/...`, tier-3 tools, debug playbook with logs/jobs/deployments, *Debug this* on failed jobs | Install works on Windows/macOS/Linux and on an Ubuntu server with/without GPU; DEBUG ≥ 60% |
| **5. Scale & polish** | 13+ | vLLM images + team mode, large model, preference tuning from opt-in feedback, MCP server exposing pskit tools to Claude Code / IDEs, routing small↔large/hosted, terminal tool (Ask-only), nightly bench on new pskit versions | — |

Public release of the first image at the end of Phase 4, marked **beta** (like providers start `experimental`).

## 9.2 Team (minimum)

| Role | Load | Main phases |
|---|---|---|
| Backend/Python engineer (knows pskit/studio) | 1 FTE | 1, 2, 4 |
| Frontend engineer (React, studio UI) | 0.5–1 FTE | 1, 2, 4 |
| ML engineer (data generation, training, eval) | 1 FTE | 0, 3, 5 |
| DevOps (images, CI, signing, GPU infra) | 0.3 FTE | 3, 4 |
| pskit maintainer review (bench items, spot checks) | ~4 h/week | all |

## 9.3 Cost (order of magnitude; recheck prices when buying)

| Item | Estimate |
|---|---|
| Teacher generation (open-weight large model on rented GPUs, ~30k samples + trajectories) | a few days of 1–4 high-end GPUs: roughly low thousands USD per full regeneration |
| Training runs (small + medium, sweeps + final, DPO) | roughly hundreds to low thousands USD per release cycle |
| Eval with a hosted reference/grader | low hundreds USD per full run (cache answers; only re-grade changed items) |
| Registry/model hub hosting for public multi-GB images | free tiers may suffice; budget for bandwidth if pulls grow |
| User side | free: runs on their hardware |

## 9.4 Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Small models are unreliable at multi-step tool use | Auto mode feels broken on laptops | Constrained JSON tool calls, budgets, verify loop; recommend medium MoE on CPU; Plan/Ask default for small; hosted/remote option |
| Model goes stale as pskit changes | Wrong answers | Retrieval from versioned index (04 §4.6), nightly bench on new versions, retrain triggers |
| Hallucinated options | Broken configs | Schema-constrained generation + validation on every change + hallucination metric gate |
| Multi-GB images, slow pulls | Bad first-run experience | Slim images, resumable downloads, progress UI, native Ollama path, small default |
| No GPU on macOS Docker | Slow | Native Ollama recommendation |
| Licence problems with base or teacher | Can't publish | Phase-0 licence review, permissive-only shortlist, licence files in image |
| Security incident (injection → destructive action) | Severe | Tiers in code, typed confirmations, no shell, SAFETY gate = 0 violations |
| Scope creep (it's a whole product) | Slips | Phase exits are measurable; Phase 1 alone is shippable value |
| Studio stays stdlib, agent code grows | Maintenance | Small, well-tested modules; FakeModel tests in normal CI |

## 9.5 Decisions needed from you (product owner)

1. **Default backend at launch**: our fine-tuned model only, or also offer the Claude API (bring your own key) from
   Phase 1? Recommendation: offer both; ours is the default when installed.
2. **Base model family**: confirm after the Phase-0 bench (shortlist in 01 §1.4).
3. **Where to publish**: GHCR (`ghcr.io/<org>/pskit-agent`) and/or Docker Hub; model hub organisation name.
4. **Auto mode and cloud**: should *allow non-prod deploys in Auto* exist at all, or should cloud actions always ask?
   Recommendation: exists, off by default, per project.
5. **Telemetry**: none (recommended), or opt-in anonymous usage counts in addition to opt-in session sharing.
6. **Training repo**: keep `ai-agent/training` in this repo (excluded from the wheel) or a separate private repo
   (recommended if datasets/teacher outputs are not to be public).

## 9.6 First two weeks, concretely

1. Licence table for the candidate base and teacher models → decision memo.
2. `ai-agent/knowledge/build.py` + index for 2.10.0 + a CLI to query it (judge retrieval quality by hand on 30 questions).
3. `ai-agent/eval/`: item format, 100 dev items (QA 40, GEN 25, FIX 25, SAFETY 10), runner with recorders.
4. `studio/agent/model.py` + `loop.py` skeleton with `FakeModel` tests; run QA on a stock model via Ollama and on the
   Claude API → the first baseline numbers that every later step is measured against.
