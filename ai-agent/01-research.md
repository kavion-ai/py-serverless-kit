# 1. Research: requirements, options, decision

## 1.1 Requirements (from the request, made precise)

| ID | Requirement | Notes |
|---|---|---|
| R1 | **Ask** questions about pskit (CLI, `pskit.yml`, providers, runtime, studio, on-prem, clusters ...) | Answers must match the installed pskit version and cite the doc/source used |
| R2 | **Create** things: project, functions, triggers, resources, workflows, handler code, tests, CI | The output is ordinary `pskit.yml` + files, the same as what studio's forms produce |
| R3 | **Ask before implementing** mode | A plan is shown first, then each mutating step waits for Approve / Edit / Reject |
| R4 | **Auto-approve** mode | Runs the plan and fixes problems itself, but **always** stops for destructive/prod actions |
| R5 | **Debug** problems: validation issues, package/plan/deploy failures, Terraform errors, runtime errors in logs, failed invocations | Reproduce → diagnose → fix → verify |
| R6 | **Solve** them end to end, not only explain | Changes are applied and checked with pskit's own commands |
| R7 | **Fine-tuned** on this library | See 1.3: fine-tuning is used for behaviour, retrieval for facts |
| R8 | Model **published as a public Docker image** | License of base model must allow redistribution |
| R9 | When the chat opens, the user **picks where the model runs**: this machine, or a saved server; studio **installs and starts** it | Reuse studio's Docker checks and saved SSH servers |
| R10 | Works **offline / on-prem** once the image is pulled | No call to a third-party API is required |

Implied (a senior engineer would add these):

| ID | Requirement |
|---|---|
| N1 | Runs on a normal developer laptop (CPU only, 16 GB RAM) at a usable speed; better on GPU |
| N2 | No new heavy Python dependency in `py-serverless-kit` (studio is stdlib + what pskit already needs) |
| N3 | Python 3.9 compatible, like the rest of the package |
| N4 | Undo for everything the agent changes |
| N5 | Measurable quality and a release gate (a model that's worse than the previous one is never published) |
| N6 | Survives pskit releases without retraining every time |
| N7 | Cloud credentials and secrets never go to the model server |

## 1.2 What we have to work with (measured in this repo)

| Asset | Size | Use |
|---|---|---|
| `docs/**/*.md` | 106 files, ~93k words (~125k tokens) | Retrieval index, Q&A generation |
| `src/**/*.py` | 142 files, ~52k lines (~500k tokens) | Retrieval for "how does X work", error strings, schema |
| `config/schema.py` (pydantic `ServiceConfig`) | — | JSON schema → constrained decoding + config sampler for synthetic data |
| `examples/` | 21 projects, auto-tested by `tests/test_examples.py` | Gold examples, few-shot, eval seeds |
| `tests/` | 102 files | Expected error messages (`pytest.raises(..., match=...)`) → fix/debug training pairs |
| `docs/troubleshooting.md`, `CHANGELOG.md` | — | Known-issue knowledge, version deltas |
| Studio `meta.py::build_meta()` | — | Live provider capabilities: a tool, not training data |
| Studio `jobs.py` | validate, package, plan, deploy, remove, info, invoke, workflow-run, trigger ... | The agent's actions reuse it unchanged |
| `core/onprem_services.py` | Docker containers locally or over SSH on saved servers | Install/run the model container (R9) |
| Git history | 68 commits | Too few for learning from history; useful as debug scenarios |

**Conclusion:** the corpus is ~0.6M tokens. That is far too little for continued pre-training, and plenty for
retrieval and for producing tens of thousands of checked synthetic training examples.

## 1.3 Approaches considered

| # | Approach | Quality | Freshness | Offline | Cost | Verdict |
|---|---|---|---|---|---|---|
| A | Train a model from scratch | Very poor | — | yes | Huge | **Rejected** |
| B | Continued pre-training on the pskit corpus | Poor (0.6M tokens) | Stale after each release | yes | Medium | **Rejected** |
| C | Fine-tune only (no retrieval) | Good on old facts, makes up new ones | **Stale after each release** | yes | Medium | **Rejected** as the only approach |
| D | Stock open-weight model + retrieval + tools | Fair: weak on pskit idioms, unreliable tool calls on small models | Fresh | yes | Low | **Phase 0–1 baseline** |
| E | Hosted frontier model (e.g. Claude API) + retrieval + tools | Best | Fresh | **no** | Pay per use, needs a key | **Offered as "bring your own key"** + reference/teacher in eval |
| F | **Fine-tuned open-weight model (LoRA) + retrieval + tools + verifiers** | Good, and improves each release | Fresh (retrieval) | yes | Medium, one-off per release train | **Chosen** |
| G | Mixture: small fine-tuned model locally, escalate hard tasks to E | Best value | Fresh | partly | Variable | **Later option** (09-roadmap, phase 5) |

Why F wins: the model only has to be good at the *pskit way of working* (read the right doc, call tools in the right
order, write idiomatic `pskit.yml`, read a Terraform error, ask when unsure). Facts come from the index built for
the installed version, and verifiers catch the rest.

## 1.4 Base model candidates

Selection criteria: **Apache-2.0 or MIT** (public image, no attribution or user-count limits), strong at code and
tool calls, 32k+ context, has a good GGUF/quantised path, size classes that fit laptops and GPU servers.

The open-weight field changes every few months. **Re-run the comparison in `07-evaluation.md` on the then-current
models before Phase 3.** As of writing, these are the families to test:

| Size class | Candidates (check licence + latest version at decision time) | Runs on |
|---|---|---|
| Small (3–8B dense) | Qwen2.5-Coder-7B-Instruct / Qwen3-8B (Apache-2.0) | Laptop CPU 16 GB (Q4), any 8 GB GPU |
| Medium MoE (~30B total, ~3B active) | Qwen3-Coder-30B-A3B-Instruct (Apache-2.0), gpt-oss-20b (Apache-2.0) | 32 GB RAM CPU at good speed (few active params), 24 GB GPU |
| Large (24–32B dense) | Devstral (Apache-2.0, agentic coding), Qwen2.5-Coder-32B (Apache-2.0) | 24–48 GB GPU |

Avoid for a *public* image unless the licence is reviewed: Llama (community licence, naming/attribution rules),
Gemma (own terms), Codestral (non-production licence), DeepSeek (own licence), and anything "research only".

**Recommendation:** fine-tune **one family in two or three sizes** (same chat template and tool format, so one
dataset and one parser). A MoE medium model is the best default for CPU-only users because only ~3B parameters
are active per token.

## 1.5 Serving engines

| Engine | CPU | NVIDIA | AMD | Apple GPU | Tool calls | OpenAI API | Notes |
|---|---|---|---|---|---|---|---|
| **Ollama** | yes | yes | yes (ROCm image) | only native, **not in Docker** | yes | `/v1/*` | Easiest; GGUF; `num_ctx` must be raised (default context is small) |
| llama.cpp `llama-server` | yes | yes | yes | native only | yes (`--jinja`) | yes | Smallest image; GBNF/JSON-schema constrained output |
| **vLLM** | weak | best | yes | no | yes (`--enable-auto-tool-choice --tool-call-parser ...`) | yes | GPU servers and teams; `guided_json`; LoRA hot-swap |
| SGLang | no | very good | partial | no | yes | yes | Alternative to vLLM |
| LocalAI | yes | yes | yes | no | yes | yes | Wraps several backends; more moving parts |

**Decision:** two image variants built from the same weights: **`ollama`** (default; CPU / NVIDIA / AMD; laptops
and small servers) and **`vllm`** (NVIDIA GPU servers, many users). Studio only depends on the OpenAI-compatible
`/v1/chat/completions` + `/v1/embeddings` API, so the engine can be swapped, and a user can also point studio at any
compatible endpoint (their own vLLM, LM Studio, a cloud endpoint, or the Claude API).

Apple Silicon note: Docker on macOS cannot use the GPU. Studio detects macOS and offers either the CPU container or
**"use native Ollama"** (studio pulls the same model into a locally installed Ollama), which is several times faster.

## 1.6 Retrieval options

| Option | Verdict |
|---|---|
| Vector DB service (Qdrant, Weaviate, pgvector) | Overkill for ~0.6M tokens; one more container |
| FAISS / chromadb in studio | New heavy dependency (violates N2) |
| **BM25 (pure Python or sqlite3 FTS5) + optional embeddings from the model server's `/v1/embeddings`, hybrid-ranked** | **Chosen.** Stdlib only, index is a few MB, built at release time and shipped with the wheel; embeddings are a bonus when the server provides them |

The corpus is technical and full of exact identifiers (`provider.options.cluster`, `PSKIT_RESOURCE_*`,
`redis_stream`), which BM25 finds well. Embeddings help with paraphrased questions ("how do I run on my own box").

## 1.7 Agent framework options

| Option | Verdict |
|---|---|
| LangChain / LangGraph / LlamaIndex / CrewAI | Big dependency trees, fast API churn, Python 3.9 support fading; would sit inside studio |
| OpenAI Agents SDK / Claude Agent SDK | Good, but couple us to one vendor's loop; Claude Agent SDK expects Claude models |
| MCP server exposing pskit tools | **Yes, as an extra:** lets Claude Code / Claude Desktop / IDE agents use the same tools (phase 5) |
| **Own small loop (~1–2k lines, stdlib)** | **Chosen.** The loop is simple (plan → tool calls → observe → verify); what matters is the tools and the policy, which are pskit-specific anyway. Fully testable with a fake model |

## 1.8 Decision record (summary)

| # | Decision | Alternatives rejected |
|---|---|---|
| D1 | Hybrid: LoRA fine-tune for behaviour + versioned retrieval for facts + verifiers | Fine-tune only; RAG only |
| D2 | Open-weight Apache-2.0 family, 2–3 sizes, picked by `pskit-bench` | Non-permissive licences for a public image |
| D3 | Agent loop in studio (stdlib); container serves the model only | Agent inside the container (would need credentials and the project mounted) |
| D4 | OpenAI-compatible API is the only contract with the model server | Engine-specific APIs |
| D5 | Ollama image default, vLLM image for GPU servers | One engine only |
| D6 | Approval policy, risk tiers and secret redaction enforced in code | Prompting the model to "be careful" |
| D7 | Install/run the model with the existing on-prem services machinery (local / SSH saved server) | New deployment code |
| D8 | Bring-your-own endpoint/key supported from day one | Only our model |
