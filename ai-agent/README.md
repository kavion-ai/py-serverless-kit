# pskit Studio AI Agent — research, design and plan

An assistant built into `pskit studio` that answers questions about py-serverless-kit, builds things (functions,
triggers, resources, workflows, handler code), debugs failed validations/deploys/invocations and fixes them, with an
**Ask before acting** or **Auto-approve** mode. It runs on a model fine-tuned for pskit, shipped as a public Docker
image that the user starts **on this machine or on one of their saved servers** from the chat panel.

Status: **proposal** (written against pskit v2.10.0, 2026-10-31). Nothing here is implemented yet.

## Read in this order

| # | Document | What it answers |
|---|---|---|
| 1 | [01-research.md](01-research.md) | Requirements, every approach considered (fine-tune vs RAG vs hosted API ...), model and serving options, the decision |
| 2 | [02-architecture.md](02-architecture.md) | Components, where each piece runs, the agent loop, context building, retrieval, data flow |
| 3 | [03-tools-and-approval.md](03-tools-and-approval.md) | Every tool the agent gets (mapped to existing studio code), risk tiers, Ask vs Auto, changesets, undo |
| 4 | [04-fine-tuning.md](04-fine-tuning.md) | Dataset generation with verification, training recipe, export, retraining per release |
| 5 | [05-docker-and-serving.md](05-docker-and-serving.md) | Images, tags, hardware sizing, local vs remote server install, publishing publicly |
| 6 | [06-studio-integration.md](06-studio-integration.md) | Chat UI, setup wizard, API endpoints, CLI (`pskit agent ...`) |
| 7 | [07-evaluation.md](07-evaluation.md) | `pskit-bench`: how we measure answers, generation, fixes, agent tasks, safety; release gates |
| 8 | [08-security.md](08-security.md) | Threat model: prompt injection, secrets, remote model endpoint, destructive actions |
| 9 | [09-roadmap.md](09-roadmap.md) | Phases, milestones, team, cost, risks, open decisions |
| 10 | [10-data-generation.md](10-data-generation.md) | Background: a teacher/judge pipeline with open-source Hugging Face models (record format, generator and judge prompts, cleaning) |
| 11 | [11-knowledge-dataset-prompt.md](11-knowledge-dataset-prompt.md) | **Final, training stage 1:** prompt for your coding agent to build Hana's **knowledge** dataset: all CLI commands, studio pages and navigation, Terraform/Docker, code map, resources per cloud, on-prem servers/services/databases/replicas, clusters, scaling, load balancers, network map. Also Hana's system prompt |
| 12 | [12-task-dataset-prompt.md](12-task-dataset-prompt.md) | **Final, training stage 2:** prompt for the **task** dataset (tools, plans, build, fix, debug, how-to steps in studio / terminal / code), and the two-stage training order |

## The decision in one paragraph

**Train behaviour, retrieve facts, verify with tools.** Fine-tuning alone would be the wrong tool. pskit ships a new
minor version every few days (v2.6 → v2.10 in the recent history), so knowledge baked into weights goes stale and the
model will make up options that don't exist. So:

1. **Facts** (options, providers, error messages, guides) come from a **versioned retrieval index** built from
   `docs/`, `examples/`, the pydantic schema and the source at release time, plus live tools such as `get_capabilities`
   (studio `meta.py`).
2. **Behaviour** (pskit.yml style, tool-calling discipline, the debug loop, when to ask, how to cite) is **fine-tuned**
   with LoRA into an open-weight coding model (Apache-2.0, so the weights can go into a public image).
3. **Correctness** is **checked, not trusted**: every config the agent writes goes through the same checks as
   `pskit validate`, handlers through `pskit invoke` locally, and fixes are re-run until they pass or the agent stops
   and asks. The same checkers mark training data correct or incorrect, so the dataset is verified rather than guessed.
4. **Safety is enforced in code, not by the model**: the approval policy, risk tiers, secret redaction and path
   confinement live in studio's Python. A weak or manipulated model still can't deploy to `prod` or delete
   resources without a typed confirmation.

The agent loop lives **inside studio** (the user's machine, with their files and cloud credentials). The Docker
container only serves the model through an OpenAI-compatible API and **never sees cloud credentials**. The same
loop also works against any OpenAI-compatible endpoint or the Claude API (bring your own key), so the product is
useful before the fine-tuned model is ready, and the fine-tuned model can be measured against a strong reference.

## Proposed repository layout

```text
ai-agent/                         # this folder: design docs now, training + images later
  training/                       # dataset generators, train configs, export scripts (not shipped in the wheel)
  eval/                           # pskit-bench tasks + runner
  docker/                         # Dockerfiles, Modelfile, entrypoint, compose examples
  knowledge/                      # index builder (docs/examples/schema/source -> chunks)
src/py_serverless_kit/studio/agent/   # shipped: loop, tools, policy, retrieval, model client (stdlib only)
dashboard-ui/src/studio/agent/        # shipped: chat panel, approvals, diff view, setup wizard
```
