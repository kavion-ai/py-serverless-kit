# 3. Tools, risk tiers and approval modes

## 3.1 Principle

Each tool is a thin wrapper over code studio **already has and tests**. The agent gets no new powers; it presses
the same buttons a user does, with the same confirmations. A tool's risk **tier** is fixed in code in
`agent/policy.py`. Neither the model nor the plan can change it.

## 3.2 Risk tiers

| Tier | Meaning | Ask mode | Auto mode |
|---|---|---|---|
| **0 Read** | Reads the project, docs, logs, status. No side effects | auto | auto |
| **1 Draft** | Changes the in-memory draft or the staged changeset only. Nothing on disk yet | auto (shown in the plan's diff) | auto |
| **2 Local** | Writes to disk, or runs locally without touching the cloud: apply changeset, validate, package, invoke locally, run tests, create `.venv` | **ask** (per step, or "approve all local steps in this plan") | auto |
| **3 Cloud / remote** | Changes something outside this machine: deploy to a non-prod stage, `trigger`, send to a resource, start on-prem services / containers on a server, `terraform plan` with credentials | **ask** | **ask** by default; the user can tick *Auto mode may deploy to non-prod stages* (per project, stored in `.pskit/studio/agent/policy.json`) |
| **4 Destructive / prod** | `remove`, `resources delete`, delete data/backups, cluster remove, anything on a stage matching `prod*`, uninstall from a server, editing files outside the project | **typed confirmation** | **typed confirmation, always**. Can't be turned off |

This matches what studio already does (typed confirmation for remove and `prod*`), so the agent never weakens the
existing protections.

## 3.3 Tool catalog (v1)

Names are what the model sees. "Backed by" is the existing code it calls.

### Tier 0: read and diagnose

| Tool | Args | Backed by | Returns |
|---|---|---|---|
| `search_docs` | `query, k?, provider?` | `agent/knowledge.py` | chunks with `path#anchor` |
| `read_doc` | `path, anchor?` | docs shipped with the package / `studio/guides.py` | section text |
| `get_project` | — | `studio/project.py` (raw config, redacted) | `pskit.yml` as YAML, provider, stage, file list summary |
| `get_validation` | `provider?, stage?` | same checks as `pskit validate`, in-process | issues with field paths |
| `get_capabilities` | `provider?` | `studio/meta.py::build_meta()` | triggers, options, regions, runtimes, what each provider supports |
| `list_files` / `read_file` / `search_project` | `path / glob / regex` | `studio/files.py` (already confined to the project, skips `.pskit .git .venv node_modules`) + `agent/redact.py` | text (≤ 1 MiB, binary refused) |
| `get_deployment` | `provider, stage` | `system.deployment_record`, `pskit info --json` | functions, URLs, workflows, last deploy time |
| `get_logs` | `function?, since?, filter?, limit?` | `system.logs_query` | recent log lines (redacted) |
| `get_job` / `read_job_log` | `job_id, offset?` | `studio/jobs.py` | status, exit code, log lines |
| `setup_check` | `provider` | `system.setup_status` (`pskit doctor`) | missing tools/credentials with fix steps |
| `explain_error` | `text` | knowledge index (error-signature chunks) + troubleshooting | likely causes + doc links |
| `list_servers` / `server_status` | `name?` | `core/onprem_servers.py` | saved servers, OS/CPU/RAM/Docker (no secrets) |
| `resource_check` | `key` | `pskit resources check` | reachable? depth? |

### Tier 1: draft (staged, reversible)

| Tool | Args | Backed by |
|---|---|---|
| `patch_config` | RFC 6902 JSON Patch on the raw `pskit.yml` structure | draft store + validation; rejects patches that write resolved `${...}` values |
| `create_function` | name, handler, memory?, timeout?, events[] (pskit.yml `events` entries), environment{}, description? | the same builder as the *Create function* wizard (writes the handler stub too) |
| `add_trigger` / `remove_trigger` | function, trigger spec | wizard code |
| `add_resource` | type, key, managed/external, driver, options | Resources form code |
| `upsert_workflow` | name, states (ASL-like) | Workflows builder model |
| `write_file` | path, content **or** unified diff | changeset (path confined; `.env*`, keys, `.pskit/` refused) |
| `set_provider` | provider, region, options | Overview page logic, including the "these triggers stop working" check |

### Tier 2: local execution

| Tool | Backed by |
|---|---|
| `apply_changes` | changeset → disk (with backup/checkpoint, conflict check) |
| `validate` | `jobs.py` `validate` |
| `package` | `jobs.py` `package` |
| `invoke_local` | `jobs.py` `invoke` (sample event from `system.test_guide`, or one the agent writes) |
| `workflow_run_local` | `jobs.py` `workflow-run` |
| `run_tests` | `pytest` in the project's `.venv` (from `devenv.py`) with a timeout, no shell |
| `lint` | `ruff` if present in the project venv |
| `setup_venv` | `devenv.py` (create `.venv`, install requirements) |

### Tier 3: cloud / remote

`plan`, `deploy` (non-prod), `info`, `trigger`, `resource_send`, `create_onprem_service`, `install_on_server`,
`cluster_join`, `scale`.

### Tier 4: destructive / prod

`deploy` (prod stage), `remove`, `resources_delete`, `delete_service`, `cluster_remove`, `logs_delete`,
`delete_data`.

**Not exposed at all:** a raw shell, arbitrary HTTP, reading `~/.aws` / `~/.ssh` / env files, editing pskit's own
installation, git push. If the model asks for something missing, it tells the user the command to run instead.
Later, a *terminal* tool could exist only in Ask mode with per-command approval (phase 5).

## 3.4 Changesets (how edits are shown and applied)

- Every tier-1 edit appends to the session's **changeset**: a list of `{path, before_hash, after_text}` plus the
  `pskit.yml` draft delta.
- The UI shows a **unified diff per file** (reusing the YAML page's diff view), each file with *Accept / Reject /
  Edit*.
- `apply_changes` writes the accepted files atomically (temp file + rename), after a checkpoint copy. `pskit.yml`
  goes through studio's normal Save path (backup to `.pskit/studio/backups/`, comments-not-kept notice).
- **Undo**: "Undo agent changes" restores the last checkpoint (per changeset). If the project is a git repo, the
  report also shows `git diff --stat`. The agent never commits.

## 3.5 Ask vs Auto, precisely

| | Ask before implementing | Auto-approve |
|---|---|---|
| Questions | Answered directly | Same |
| Plan | Shown as a card: **Approve / Edit plan / Reject**. Edit sends the user's notes back to the model, which re-plans | Shown, and execution starts at once (the user can **Pause** / **Stop**) |
| Tier 0–1 steps | Run | Run |
| Tier 2 steps | Inline approval per step, or *Approve all local steps of this plan* | Run |
| Tier 3 steps | Inline approval | Approval, unless the project-level *allow non-prod cloud actions* is on |
| Tier 4 steps | Typed confirmation | Typed confirmation |
| Repair loop | Each repair attempt that changes files is shown as a new diff; tier ≥ 2 retries ask again | Up to 3 attempts per failure signature, then stop and report |
| End | Summary + "Apply / Discard" for anything still staged | Summary of what was applied, with **Undo** |

A third mode, **Plan only**, runs tier 0 tools only and returns a plan and a diff preview with nothing applied.
It's the safe default for a first-time user.

## 3.6 The debug playbook (what the fine-tune teaches, what tools enforce)

```text
1. Locate      get_job / get_validation / get_logs / get_deployment   -> the actual error text, not the user's paraphrase
2. Classify    config | packaging | terraform/provider | credentials/setup | runtime handler | resource connectivity | on-prem host
3. Ground      explain_error + search_docs on the error signature; read the involved file(s)
4. Reproduce   cheapest first: get_validation -> invoke_local -> package -> plan -> (ask) deploy
5. Fix         smallest change in the changeset; prefer config over code; never change handler code to work around one cloud
6. Verify      re-run the step that reproduced it; then the broader check (validate + invoke)
7. Report      root cause in one sentence, the diff, the evidence (passing check), and anything the user must do (e.g. credentials)
```

Classes the agent must hand back to the user rather than "fix": missing credentials/logins (it runs `setup_check`
and shows the steps, or offers the studio login button), quota/permission errors in the cloud account, billing,
DNS. These are wired as explicit outcomes so the model doesn't loop on them.

## 3.7 Tool result hygiene

- Every tool output goes through `redact.py` (see 08) and truncation (head 60 lines + tail 60 lines + every line
  that matches `error|exception|traceback|failed`).
- Outputs are wrapped as data: `<tool_result name="get_logs" trusted="false">…</tool_result>`. The system prompt
  says these are never instructions. The policy layer makes this matter less, because instructions inside them still
  can't escalate tiers.
