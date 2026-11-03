# 6. Studio integration: UI, API, CLI

## 6.1 UI

A **dockable chat panel** on the right of every studio page (toggle `Ctrl/Cmd+I`), plus a full-page *Assistant* view
for long sessions. Built in `dashboard-ui/src/studio/agent/` and compiled into the same single-file `studio.html`.

```text
┌ Studio page (Functions, Resources, …) ─────────────┬ Assistant ── medium · local ● ── [Ask ▾] ┐
│                                                     │ ▸ Session: "orders worker"   [+ New]     │
│                                                     │                                          │
│                                                     │ You: add an SQS worker that saves to S3  │
│                                                     │ ┌ Plan (5 steps) ──────────────────────┐ │
│                                                     │ │ 1 add queue `orders`       draft      │ │
│                                                     │ │ 2 function process_order   draft      │ │
│                                                     │ │ 3 handler src/orders.py    draft      │ │
│                                                     │ │ 4 validate aws/dev         local ⚑    │ │
│                                                     │ │ 5 invoke with sample event local ⚑    │ │
│                                                     │ │ [Approve] [Edit plan] [Reject]        │ │
│                                                     │ └──────────────────────────────────────┘ │
│                                                     │ ▸ Changes (3 files)  [View diff]         │
│                                                     │ ✓ validate passed  ✓ invoke 200          │
│                                                     │ Sources: docs/events.md#queue …          │
│                                                     │ [ message…                     ] [Send]  │
└─────────────────────────────────────────────────────┴──────────────────────────────────────────┘
```

Elements:

| Element | Behaviour |
|---|---|
| Header chip | Backend + size + location + status dot; menu: switch, stop, logs, settings |
| Mode switch | **Plan only / Ask before acting / Auto-approve**. Auto shows a one-time explanation of what it will and won't do (tiers 3–4) |
| Plan card | Steps with tier badges (draft / local / cloud / destructive). Approve, Edit plan (free text back to the model), Reject |
| Step approvals | Inline buttons; tier 4 shows the same typed-confirmation dialog studio already uses |
| Diff viewer | Per file, accept/reject per file, open in Code editor |
| Live tool activity | Collapsible "Running validate…" rows that stream job logs (reuse the Deploy page's log component) |
| Citations | Links open the in-studio Guides/Markdown viewer at the anchor |
| Context chips | "Using: Functions › process_order", "Last failed job: deploy #12". Removable |
| **Ask the assistant** entry points | Buttons next to things studio already shows: a validation issue (*Fix with assistant*), a failed job (*Debug this*), a log error line, an empty project (*Describe what you want to build*) |
| Feedback | 👍/👎 per answer, "Share session" (opt-in, preview of redacted export) |
| Stop | Cancels the model stream and any not-yet-started step; running deploys are not killed (same as today) |

Accessibility: keyboard reachable and screen-reader labels, like the rest of studio. Streaming text goes into an
`aria-live="polite"` region.

## 6.2 Setup wizard (first open)

1. **Where should it run?** (dialog in 05 §5.4), with a recommendation from detected hardware.
2. **Install & start** with a streamed log and progress.
3. **Quick check**: "Hello" round trip + tool smoke test + embeddings build (progress bar; skippable, BM25 still works).
4. **Pick the default mode** (Plan only is preselected for new users).
5. Done. The first suggested prompts come from the project state (e.g. no `pskit.yml` → "Create a REST API on AWS
   with two routes"; validation issues → "Fix the 3 validation problems").

## 6.3 Server API (new routes in `studio/server.py`, same token/Origin/Host checks)

| Method & path | Purpose |
|---|---|
| `GET /api/agent/runtime` | Configured backend, status, model info, compatibility |
| `POST /api/agent/runtime/install` | `{target: local\|server:<name>\|native-ollama, size, variant, gpu}` → job id (streamed log) |
| `POST /api/agent/runtime/start` / `stop` / `remove` | Lifecycle |
| `PUT /api/agent/runtime/endpoint` | Custom endpoint / Claude API key (stored server-side only) |
| `GET /api/agent/hardware?target=` | RAM/GPU/disk → recommended size |
| `GET /api/agent/sessions` / `POST` / `DELETE /{id}` | List, create, delete sessions |
| `POST /api/agent/sessions/{id}/messages` | `{text, mode, context:{page, item, selection}}` → turn id |
| `GET /api/agent/turns/{id}/events?since=n` | Event stream: tokens, tool start/end, plan, approval requests, diffs, final. Polling with `since` like jobs (works in the existing server without SSE); SSE later as an option |
| `POST /api/agent/turns/{id}/approve` | `{step_id, decision: approve\|reject\|edit, note?, confirm_text?}` |
| `POST /api/agent/turns/{id}/stop` | Cancel |
| `GET /api/agent/changesets/{id}` / `POST …/apply` / `POST …/undo` | Diffs, apply, undo |
| `POST /api/agent/feedback` | Rating / comment |
| `GET/PUT /api/agent/policy` | Project policy (allow non-prod cloud actions in Auto, budgets) |

The turn runs in a background thread with an event buffer (the same pattern as `JobManager`, max lines, keep last N
turns). The UI polls. A turn waiting for approval is parked, not blocking a thread.

## 6.4 CLI (same loop, no browser)

```bash
pskit agent up [--server NAME] [--size small|medium|large] [--gpu auto|on|off] [--slim] [--pull]
pskit agent status | down | logs | remove [--keep-models]
pskit agent use --endpoint URL [--key-env VAR]        # or: --claude --key-env ANTHROPIC_API_KEY
pskit agent ask "why does my queue trigger not fire on gcp?"      # read-only answer
pskit agent do  "add a nightly job that cleans old objects" [--mode ask|auto|plan]   # interactive approvals in the terminal
```

The terminal version renders plans and diffs as text and asks `[y/N/e]` for each approval. Tier 4 asks for typed
confirmation. `--mode auto` on a non-interactive terminal refuses tier ≥ 3 (CI-safe).

## 6.5 Code layout (shipped package)

```text
src/py_serverless_kit/studio/agent/
  __init__.py
  loop.py          # turn state machine, budgets, repair loop, compaction
  model.py         # OpenAI-compatible client (urllib, SSE), tool-call fallback, embeddings, capability probe
  tools.py         # tool registry: JSON schemas + wrappers over studio/core functions
  policy.py        # tiers, mode rules, prod detection, project policy file
  changeset.py     # staged edits, diffs, atomic apply, checkpoints, undo
  knowledge.py     # load index-<version>.json.gz, BM25, embedding cache (sqlite3), hybrid ranking
  redact.py        # secret patterns + known secret values from env files / services state
  sessions.py      # jsonl persistence, export
  runtime.py       # install/start/stop the model container (local / ssh) via onprem_services
  prompts/system.md, prompts/plan.md, prompts/repair.md
  knowledge/index-2.10.0.json.gz
src/py_serverless_kit/cli/main.py   # `pskit agent` group
tests/studio/agent/                  # fake-model tests (scripted tool calls), policy tests, redaction tests
```

**Testing without a model:** a `FakeModel` that replays scripted responses (tool calls / text) makes the loop,
policy, approval and changeset logic fully testable in the normal `pytest` run, with no GPU and no network, the same
way the rest of pskit is tested without cloud access.

## 6.6 Docs to add when built

`docs/assistant.md` (user guide), a section in `docs/studio.md`, `docs/cli.md` for `pskit agent`, README feature line,
`deploy_docs/CONTRIBUTING.md` (adding a tool: schema + tier + test + bench items), CHANGELOG entries.
