# Stage-2 task dataset: notes for authors

pskit version 2.10.0 (`src/py_serverless_kit/_version.py`). Facts below were read from the repo or produced by
running pskit (2026-11-01). When in doubt, re-run the command; do not trust memory.

## SCOPE (2026-11-01): stage 2 trains on aws, azure, gcp, onprem ONLY

- Every NEW conversation uses provider aws, azure, gcp or onprem (Environment line and meta.provider). The checker
  rejects other providers for ids above `LEGACY_MAX_ID` (tools/task_common.py).
- Do not write new samples whose topic is another provider (no "can I ... on cloudflare?", no `-p ibm` validate).
- Older records (ids <= LEGACY_MAX_ID) with other providers stay in data/raw but `build_dataset.py` leaves them out.
- The system prompt is unchanged (it still lists all 11 providers; it must equal stage 1 + studio).
- Progress: `python tools/progress.py` recomputes data/progress.json from the files (counts in scope).
- Mix inside the 4 (user's choice): onprem 40%, aws 22%, gcp 20%, azure 18%, in every category. onprem
  includes servers, databases, resources, scaling cluster, load balancers, network map, Docker/Terraform behaviour.

## Tooling (read first)

| File | What it does |
|---|---|
| `tools/run_tool.py` | scratch projects + REAL tool outputs (validate, set_config, invoke, get_project, read_file, docs excerpts) |
| `tools/assemble.py` | turns hand-written batch files `data/task_src/<cat>_NN.py` into JSONL lines, running every tool step live |
| `tools/check_data.py` | the section-6 checker. `python tools/check_data.py` (all task files) or `... data/raw/a_qa.jsonl` |
| `tools/build_dataset.py` | at the end: `data/raw/*.jsonl` (not `k_*`) -> `data/final/task_train.jsonl` / `task_val.jsonl` + `TASK_README.md` |

Run everything with the repo venv: `.venv/Scripts/python.exe` (Windows, Git Bash) or `.venv/bin/python`.
`python -m py_serverless_kit <cmd>` works; `python -m py_serverless_kit.cli` does NOT (no `__main__`).
`.venv/Scripts/pskit.exe` also exists.

### run_tool.py usage

```bash
PY=.venv/Scripts/python.exe; T=ai-agent/training/tools/run_tool.py
$PY $T new demo --from examples/04-queue-worker            # copies pskit.yml, app/, requirements.txt
$PY $T new demo2 --yml my.yml --file app/__init__.py= --file app/jobs.py=@jobs.py
$PY $T project demo                                         # get_project text
$PY $T read demo app/worker.py                              # read_file
$PY $T validate demo -p gcp -s prod                         # validate / get_validation
$PY $T set demo functions.enqueue.timeout 20 -p aws         # set_config ("ok" + validate). value null deletes
$PY $T write demo app/new.py @local.py                      # write_file -> ok
$PY $T invoke demo -f enqueue -t http --method POST --path /jobs -d '{"kind": "email"}'
$PY $T docs docs/events.md queue --start "| Option" --words 150   # verbatim search_docs excerpt
$PY $T clean demo
```
Add `--json` before the subcommand to get a JSON string. Scratch dirs: `ai-agent/training/scratch/` (git-ignored).

### assemble.py batch format (preferred way to write conversations)

A batch file `data/task_src/b_build_01.py` defines `CONVERSATIONS = [ {...}, ... ]`, each written by hand:
```python
dict(id="b_build-0001", category="b_build", provider="aws", stage="dev", mode="ask", page="Functions",
     persona="terse_expert", sources=["docs/events.md#queue"],
     project=dict(base="examples/01-hello-http", files={"app/x.py": "..."}),   # optional
     user="add sqs trigger ...",
     steps=[
       S("get_project"),
       S("search_docs", query="queue batch size", docs=[D("docs/events.md", "queue", words=150)]),
       S("propose_plan", steps=["..."], result={"decision": "approved", "note": ""}),
       S("set_config", path="functions.worker.events", value=[{"queue": {"name": "jobs"}}], say="..."),
       S("validate"),
       S("invoke_local", function="worker", type="queue", data=[{"id": 1}]),
       S("ask_user", question="...", options=["a", "b"], answer="a"),
     ],
     final="...answer...")
```
`S(...)` = one tool call (+ optional `say=` assistant text before it). Tool results of validate / set_config /
invoke_local / get_project / read_file / write_file are produced live by run_tool; search_docs results are verbatim
excerpts made by `D(path, anchor, start=, end=, words=)` (or `D(card="<card id>")`). validate always runs with the
Environment's provider and stage unless `provider=` is given. Then `python tools/assemble.py data/task_src/b_build_01.py`
upserts the lines (by id) into `data/raw/b_build.jsonl`, and prints every tool output so you can check the final
answer matches. Re-read the printed outputs and fix `final` if needed, then re-run.

## Format decisions

- System prompt = section 12.3 text (with "If the user names one way ... give only that way."), Environment line
  `Environment: provider=<p> stage=<s> mode=<ask|auto> page=<page>`. NOTE: the stage-1 system prompt
  (`data/final_v2/*`) does NOT have that one-way sentence; everything else is identical (see report).
- Tool call ids `call_01`, `call_02`, ... (stage 1 used `call_01`). One tool call per assistant message.
- Pages for Environment: Overview, Setup, Functions, Workflows, Resources, Cluster, Load balancers, Network map, Code,
  Test, Deploy, Logs, YAML, none.

## Studio labels (dashboard-ui/src/studio/App.tsx NAV + views/*.tsx)

NAV (exact): `Overview & provider`, `Setup & credentials`, `Functions`, `Workflows`, `Resources`, `Scaling cluster`,
`Load balancers`, `Network map`, `Code`, `Test`, `Deploy`, `Logs`, `YAML`. Write studio paths as
**Functions > + Create function** (the checker requires the first segment to be a NAV label).

- Top bar: target provider select ("validate & deploy as"), stage input, Undo/Redo, Problems button
  ("N errors · N warnings"), **Validate**, **Save** (Ctrl+S), **⇅ Settings**.
- Functions: **+ Create function** (wizard steps `Basics`, `Triggers`, `Environment & permissions`, `Review`;
  buttons `Next: <step> →`, `← Back`, final `Create function` / `Apply changes`). Section `Add a trigger`.
  Fields: Function name, Handler, Runtime, Memory (MB), Timeout (s), Architecture, Description, Log level, Live logs.
  Sections: Basics, Environment variables, Permissions (IAM), Concurrency & tags, Logging, Provider-specific options.
  Empty state: **Create your first function**. Row buttons: Test, Open code, Duplicate, Rename, Delete.
- Test: steps `1. Choose the event`, `2. Edit the event`, `3. Run it`; **▶ Run locally**, **☁ Send to <provider> / <stage>**,
  **Save event**, `Payload (JSON)`, toggle *Show the function's logs*, panel `How to test this`. "Direct invoke".
- Deploy: buttons `Validate`, `Package`, `Plan`, `Deploy`, `Info`, `Remove`; panels `Invoke a function locally`,
  `Run a workflow locally`, `Where functions run`, `Recent jobs`. Remove and `prod*` stages need typed confirmation.
- Workflows: **+ Create workflow**, `Add state`, Engine, Timeout (s); state inspector fields (Function, Then, Result path...).
- Resources: **+ Add resource**, **+ On-prem service**, **+ SMTP server**, Browse account…, How to use, Test, Data, Guides.
- Code: file tree + editor, **New file**, **Full VS Code**. YAML: generated pskit.yml, diff, `YAML mode` raw editing.
- Setup & credentials: Checks, AWS credentials (aws configure), Environment variables (**Set for this session**),
  Project environment (.venv), On-premises connection (**Test SSH connection**).
- docs/studio.md describes all pages; quote it in search_docs for studio questions.

## CLI (from knowledge/cli.json, the checker uses it)

Common: `-c/--config`, `-p/--provider`, `-s/--stage`, `-r/--region`, `--server`, `--cluster`, `-v/--verbose`.
- `pskit validate` (common flags only). `pskit invoke -f FN [-t http|schedule|queue|storage|topic|invoke|workflow|smtp]
  [-d JSON|@file] [--method M] [--path P] [-H "N: v"] [--env-file .env]`.
- `pskit dev [--host] [--port 3000] [--env-file]`, `pskit init [DIR] --name -p -t http|events|workflow|full --force`,
  `pskit package [--skip-deps]`, `pskit plan [--skip-deps --destroy]`, `pskit deploy [--skip-deps --confirm --upgrade
  --no-dashboard]`, `pskit remove [-y --keep-resources]`, `pskit trigger -f FN [-e N] [--direct] [-d] [--path] [--list] [--json]`,
  `pskit info`, `pskit logs [-f -n --function --level --source -q --json --streams --delete --delete-all -y]`,
  `pskit workflow run NAME [-i JSON|@file] [--sleep] [--history]`, `pskit workflow show NAME [--format auto|asl|gcp|json]`,
  `pskit studio [-d DIR --host --port 8770 --open --vscode-image]`, `pskit doctor [-p]`, `pskit providers [--json]`,
  `pskit tf -- ARGS`. Check exact flags with `knowledge/cli.json` before writing any command.

## pskit.yml keys (src/py_serverless_kit/config/schema.py, extra="forbid" everywhere)

- Top: `service` (2-32, `[a-z][a-z0-9-]`), `provider`, `package`, `functions`, `workflows`, `resources`, `hooks`, `custom`,
  plus loader keys `providers`, `stages`, `extends`.
- provider: `name region stage(dev) runtime(python3.12) memory(256, 64-32768) timeout(30, 1-3600) architecture
  environment tags iam{statements,role} log_retention_days(14) options state{backend,config} terraform{binary,
  required_version,provider_version,extra}`.
- function: `handler description enabled runtime memory timeout environment tags events concurrency architecture iam options`.
- events (single-key items): `http{path method cors auth(none|iam|jwt|key) authorizer}`, `schedule{rate cron input enabled
  timezone name}`, `queue{name resource existing batch_size(1-10000, def 10) batch_window(0-300) visibility_timeout
  dead_letter max_receive(5) fifo}`, `storage{bucket resource existing events[created,deleted] prefix suffix}`,
  `topic{name resource existing filter}`, `smtp{resource name}`. Shorthands: `- http: GET /x`, `- schedule: 5 minutes`
  or a 5-field cron string, `- queue: jobs`, `- storage: bucket`, `- topic: t`.
- cors: `origins methods headers expose_headers allow_credentials max_age`.
- workflows: `start_at states description enabled engine(auto|native|embedded) timeout options`; state `type function
  next end comment input_path result_path retry catch timeout_seconds choices default seconds seconds_path result
  branches items_path iterator max_concurrency error cause`; retry `errors max_attempts interval_seconds backoff_rate
  max_delay_seconds`; catch `errors next result_path`.
- resources: `type(storage|queue|topic|database|cache|custom|smtp) external name connection functions options`.
  database/cache/custom must be `external: true`.
- package: `source include exclude requirements pip_args vendor node{install typescript build out_dir bundle npm_args}`.
- hooks: before_/after_ package|deploy|remove.

## Handler API (docs/handlers.md, runtime/*.py)

`from py_serverless_kit import Event, Context, Response, BatchResult, HttpError, BadRequest, NotFound, ... invoke,
get_secret`. Event: `type provider function http records data time source raw`, `json()`, `is_http`, `is_batch`.
HttpRequest: `method path route headers query multi_query path_params body source_ip content_type cookies text()
json(default=) form()`. Record: `id body attributes source bucket key size action raw text() json()`.
Context: `request_id function provider service stage region memory_mb remaining_time_ms() logger env raw`.
Returns: dict -> 200 JSON, None -> 204, str -> text/plain, `(body, status[, headers])`, `Response.json(...)`.
`BatchResult().fail(record)`; invoke prints `{"batchItemFailures": [...]}`. Handlers: `from __future__ import annotations`.

## Providers (docs/providers.md + real validate runs)

| Provider | Triggers | Required options (real error) | Limits seen in validate |
|---|---|---|---|
| aws | http schedule queue storage topic, native wf | none | timeout max 900 ("timeout 1200s exceeds AWS Lambda max 900s"); `auth: key` error |
| gcp | all five, native wf | `options.project` ("GCP needs provider.options.project (the GCP project id)") | event fns max 540 s; auth jwt/key error; fifo/dead_letter warnings |
| azure | all five (blob created only) | subscription_id documented, but validate PASSES without it here | runtimes 3.9-3.12; auth iam/jwt error; queue names lowercase; timezone warning; fifo warning |
| alibaba | http schedule storage topic | none | no queue; no native wf |
| tencent | http schedule storage | none | no PATCH; memory 64/128/n*128; COS bucket `<name>-<APPID>` |
| huawei | http schedule storage topic | `apig_instance_id` when there are http events | no queue |
| ibm | http only | none | python3.11 only, 120 s, 4096 MB |
| digitalocean | http schedule | `options.namespace` (+ warning when doctl missing) | memory 128-1024 |
| oracle | http storage | `compartment_id`, `subnet_ids`, `image` or `image_repository` (+ IAM policy warning) | no schedule/queue/topic |
| cloudflare | http schedule | `options.account_id` (+ Pyodide requirements warning) | no queue/storage/topic |
| onprem | all five + smtp | none (`host`, `port` typical) | auth must be none ("auth `iam` is not enforced on-premises...") |

Unsupported-trigger message form: `ERROR: [functions.<fn>] <Display Name> does not support `<type>` events in pskit (supported: ...)`.
Display names (validate header): AWS Lambda, Google Cloud Functions, Azure Functions, On-premises, Alibaba Cloud Function Compute,
Tencent Cloud SCF, Huawei Cloud FunctionGraph, IBM Cloud Code Engine, DigitalOcean Functions, Oracle Cloud Functions,
Cloudflare Workers.

## validate / invoke output formats (real)

```
<service> -> AWS Lambda [stable] stage=dev region=us-east-1
  3 function(s), 0 workflow(s)
Configuration is valid.
```
Provider issues: `  ERROR: [where] message` / `  WARNING: [where] message` lines after the header; with any ERROR there is
no "Configuration is valid." line. Schema errors replace everything with:
```
Error: pskit.yml is invalid:
  - functions.api.hander: Extra inputs are not permitted
```
Variables: `Error: unresolved variables: self:custom.table`. Embedded workflows add `  workflow <name>: embedded engine`.
invoke: log lines `2026-11-01 12:07:42,587 INFO    pskit.function: <msg>` then the JSON result; HTTP results are
`{"status", "headers", "body"}`; BatchResult prints `{"batchItemFailures": [...]}`; exceptions print a traceback, exit 1.

## Real error messages (from running validate; cause -> message)

1. queue on alibaba/tencent/huawei/ibm/digitalocean/oracle/cloudflare -> `<Provider> does not support `queue` events in pskit (supported: ...)`
2. schedule on oracle -> `Oracle Cloud Functions does not support `schedule` events in pskit (supported: http, storage)`
3. storage on cloudflare -> `Cloudflare Workers does not support `storage` events in pskit (supported: http, schedule)`
4. gcp w/o project -> `GCP needs provider.options.project (the GCP project id)`
5. huawei http w/o apig -> `HTTP events need a dedicated API Gateway instance: set provider.options.apig_instance_id`
6. digitalocean -> `options.namespace is required (see `doctl serverless namespaces list`)`
7. oracle -> `options.compartment_id is required`; 8. `options.subnet_ids (list of subnet OCIDs) is required`;
9. `OCI Functions need a container image. Either set options.image_repository ...`
10. cloudflare -> `options.account_id is required`
11. batch_size 0 -> `functions.worker.events.0.batch_size: Input should be greater than or equal to 1`
12. batch_size 20000 -> `... Input should be less than or equal to 10000`
13. batch_window 400 -> `... batch_window: Input should be less than or equal to 300`
14. memory 50 -> `functions.api.memory: Input should be greater than or equal to 64`
15. timeout 5000 -> `functions.api.timeout: Input should be less than or equal to 3600`
16. aws timeout 1200 -> `timeout 1200s exceeds AWS Lambda max 900s`
17. ibm timeout 300 -> `timeout 300s exceeds IBM Cloud Code Engine max 120s`
18. `hander` typo -> `functions.api.handler: Field required` + `functions.api.hander: Extra inputs are not permitted`
19. `evnets` typo -> `functions.api.evnets: Extra inputs are not permitted`
20. 4-field cron -> `Value error, cron must be a standard 5-field expression: 'min hour dom month dow'`
21. bad rate -> `Value error, rate must look like '<n> minutes|hours|days'`
22. `${self:custom.table}` missing -> `Error: unresolved variables: self:custom.table`
23. `${env:NOPE_XYZ}` unset -> `Error: unresolved variables: env:NOPE_XYZ`
24. handler module missing -> only `WARNING: [functions.api.handler] handler module 'app.nope' not found under .` (still valid!)
25. handler without dots -> `handler 'hello' must be 'package.module.function' (or 'module:function')`
26. workflow next -> `workflows.wf: Value error, state 'A' points to unknown state 'B'`
27. start_at -> `start_at 'X' is not a defined state`
28. task function -> `<root>: Value error, workflow 'wf' references unknown function 'nope'`
29. choice without next -> `choice rule in 'A' has no `next`: {...}`
30. `queue: {resource: jobs}` missing -> `function 'worker' uses unknown resource 'jobs'; known: <none>`
31. method FETCH -> `method must be one of GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS, ANY`
32. `{user-id}` -> `invalid path template '/users/{user-id}'; use /users/{id} or /files/{path+}`
33. duplicate route -> `route GET /hello is used by both 'api' and 'worker'`
34. two keys in one event -> `each event must be a single-key mapping such as `- http: {path: /hello}`; got {...}`
35. `- cron:` -> `unknown event type 'cron'; expected one of http, schedule, queue, storage, topic, smtp`
36. `batch_size` under http -> `functions.api.events.0.batch_size: Extra inputs are not permitted`
37. jwt w/o authorizer -> `jwt auth needs authorizer.issuer and authorizer.audience`
38. jwt on azure -> `http auth 'jwt' is not supported on Azure; use none or key (or put API Management / Easy Auth in front)`
39. key on aws -> `API keys are not available on API Gateway HTTP APIs; use jwt or iam`
40. iam on onprem -> `auth `iam` is not enforced on-premises; use auth: none and check tokens in the handler`
41. python3.13 on azure -> `Azure Functions does not support python3.13; use one of: python3.10, python3.11, python3.12, python3.9`
42. python3.8 -> `runtime must be python3.9 .. python3.14 or nodejs18, nodejs20, nodejs22, nodejs24 (provider support varies)`
43. service `My_Service` -> `service must be 2-32 chars of lowercase letters, digits and dashes`
44. stage `Prod_1` -> `stage must be lowercase alphanumeric/dash, max 16 chars, e.g. dev, prod`
45. tencent PATCH -> `Tencent API Gateway does not support PATCH; use ANY`
46. tencent memory 200 -> `SCF memory must be 64, 128 or a multiple of 128 MB (got 200)`
47. tencent bucket -> `COS bucket 'uploads' must be '<name>-<APPID>', e.g. uploads-1250000000`
48. ibm memory 8192 -> `Code Engine functions support at most 4096 MB`; ibm 3.12 -> `IBM Cloud Code Engine does not support python3.12; use one of: python3.11`
49. gcp event fn timeout 900 -> `event-triggered functions are limited to 540s on GCP`
50. digitalocean memory 2048 -> `memory 2048 MB is outside DigitalOcean's 128-1024 MB range`
51. azure queue `Jobs_Queue` -> `queue name 'Jobs_Queue' must be 3-63 lowercase letters, digits, dashes`
52. azure storage `events: [deleted]` -> `Azure blob triggers only fire on created/updated blobs`
53. onprem port 70000 -> `options.port must be an integer from 1 to 65535`
54. hooks `pre_deploy` -> `unknown hooks ['pre_deploy']; allowed: [...]`
55. `resources.db: {type: database}` -> `pskit does not create `database` resources; set `external: true` and describe it in `connection``
56. `cors: {origin: "*"}` -> `cors.bool: Input should be a valid boolean` + `cors.CorsConfig.origin: Extra inputs are not permitted`
57. workflow task disabled on provider -> `workflow 'wf' calls function 'worker', which is disabled; disable the workflow too`
58. `engine: native` on alibaba -> `Alibaba Cloud Function Compute has no native workflow service supported by pskit; use `engine: embedded` or `auto``
Warnings: gcp fifo `queue.fifo is not supported by Pub/Sub triggers and is ignored`; azure fifo `Storage Queues are not
FIFO; queue.fifo is ignored`; azure timezone `Linux Consumption timers run in UTC; timezone is ignored`.

## invoke facts (real runs)

- `pskit invoke` calls the function directly: `--path /status` on a function routed at `/hello` still runs it (no 404),
  so a route-not-found cannot be reproduced with invoke_local.
- `-t invoke` on an HTTP handler gives `event.http = None` -> AttributeError traceback (a good D-category bug).
- Tracebacks show pskit files as `site-packages\py_serverless_kit\...` (run_tool rewrites the checkout path) and
  handler files as `.\app\x.py`. assemble.py passes the Environment stage to invoke, so `ctx.stage` matches.
- invoke log lines keep real timestamps. A queue/topic handler returning None prints `null`; a schedule invoke
  without `-d` uses the configured `input`. invoke_local has no header argument (the CLI has `-H`).
- validate on digitalocean prints a doctl WARNING and on cloudflare a Pyodide WARNING; both still say valid.
  Oracle prints its API Gateway IAM WARNING only when there are http events.

## Doc vs. reality (do not write samples that contradict the real output)

- `schedule: 7 minutes` on gcp VALIDATES (docs/events.md says it fails on cron-only clouds).
- cron restricting both day-of-month and day-of-week (`0 3 1 * 1`) validates on aws (docs say error).
- topic `filter` on gcp: no warning printed (docs say warning).
- azure without `subscription_id` validates (docs/troubleshooting say it is needed for deploy: say "deploy needs it").
- handler function missing in an existing module: no warning at all; missing module is only a WARNING.
- literal password in `environment`: validate passes. Category C "literal password" fixes must be framed as a
  security fix, not "validate fails".

## Findings from the stage-2 agents (real runs, 2026-11-01)

- Nested variables (`${self:custom.x.${opt:stage}}`) do not resolve; use `stages.<stage>` overrides.
- `${env:X}` with X unset fails validate ("unresolved variables"); give a default `${env:X, not-set}` and say where to set it.
- Env values are strings: `options.port: ${env:PORT, 8080}` fails ("options.port must be an integer"); use `${self:custom.port}`.
- `resources.<r>.functions: [fn]` fails if fn doesn't exist yet; add the function first.
- onprem: `deploy.server` / `cluster` / placement must name saved servers/clusters; seed `.pskit/onprem-servers.json`
  and `.pskit/onprem-clusters.json` in the scratch project. Remote/Docker/cluster deploy with the default bind warns
  "host binds to 127.0.0.1" (set `host: 0.0.0.0`). Two placement groups on one server need different ports.
- Local invoke: `ctx.region` is "local", `ctx.memory_mb` and `ctx.remaining_time_ms()` are None, resource names are
  unprefixed, repeated query params keep the last value, Set-Cookie is not shown, no CORS headers without Origin.
  Function with schedule + http needs `type="http"`. Node.js handlers work (node installed).
- `HttpError(status=500)` prints a traceback in invoke (checker fails): return `(body, 500)`.
- Validate passes (not usable as category C): hour-25 cron, `0 minutes` rate, `/users/:id`, allow_credentials with `*`,
  gcp topic.filter, `balancer: {name: x}` for a missing balancer. `extends:` to a missing file crashes (pskit bug).
- Checker quirks: `>` in answer text trips the studio-path check; inline `KEY=value`, `token =`, `secret =`,
  `password=`, `token_command:`, `password_file:` are flagged as secrets; bare `cors:` snippet is an unknown key.
- D(): start/end inside a fenced block empties the excerpt; end strings must be one line.
- Handlers must not make network calls during invoke_local.
- onprem: `concurrency` is accepted but unused; `memory` only sets ctx.memory_mb; the Python host does not stop a
  handler at `timeout` (it only sets a deadline). Don't claim onprem enforces any of these.
- Checker: YAML snippets in answers must start at a top-level key (wrap `placement:` in `provider: options:`).
- Local invoke: queue `attributes` can't be passed with `-d`; the {"body","attributes"} form arrives as the raw body.
