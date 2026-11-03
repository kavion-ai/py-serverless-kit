# Dashboard

The dashboard is one self-contained HTML page (React, with all JS and CSS inline) listing everything the project has deployed, across all providers and stages. `pskit deploy` and `pskit remove` regenerate it at:

```
.pskit/dashboard/index.html
```

It works in two modes:

| | Static page | Live (`pskit dashboard --serve`) |
|---|---|---|
| How | open the file, or host it anywhere (`file://`, a bucket, a CI artifact) | a local server renders the page and adds a JSON API |
| Deployments, functions, triggers, endpoints, ids, workflows, resources, outputs | yes, as of the last deploy | yes, re-read on every refresh |
| Host health and invocation stats (on-premises) | — | yes |
| Logs: live tail, list streams, delete (on-premises, AWS; read-only on GCP and Azure) | — | yes |
| Workflow executions: list, start, follow, cancel | — | yes (on-premises, AWS Step Functions, GCP Workflows) |

The **Executions** and **Logs** tabs in a static page say live data needs `pskit dashboard --serve`.

```bash
pskit dashboard                       # regenerate the static page
pskit dashboard --open                # regenerate and open it
pskit dashboard --serve               # live, on http://127.0.0.1:8765/
pskit dashboard --serve --open --port 9000
pskit dashboard -o site/index.html    # write somewhere else
pskit dashboard -d path/to/project
```

## What it shows

**Overview:** summary cards (deployments, functions with the HTTP count, workflows, resources, providers), then a sortable, filterable, paginated table of deployments with provider and tier, status (`deployed`, `removed`, `local`), region, endpoint and last update. Light and dark themes follow the system setting, and a toggle remembers your choice.

**Deployment page** (click a row). The header shows region, update time, artifact hash, endpoint and pskit version. On premises in live mode it adds cards for uptime, invocations, errors and queued messages. The tabs are:

| Tab | Content |
|---|---|
| Functions | name and cloud resource name, type, triggers, runtime/memory/timeout, endpoints, id/ARN with copy, console link. Live on-prem rows add invocations, errors, average duration and the last error |
| Workflows | engine (native/embedded), the state flow, task functions, id and console link, and a **Start** button in live mode |
| Executions | filter by workflow and status, server-side pagination, auto-refresh while anything is `RUNNING`, a **Start execution** dialog with a JSON input editor. Clicking a row opens a detail panel with status, a timeline of the history (current state highlighted), input/output/error, and **Cancel**. It refreshes while the run is going |
| Logs | **Live tail**: level (minimum), function and source filters, text search, pause/resume, auto-scroll, *load older* on premises, and a console link. **Log streams**: CloudWatch streams (AWS) or one row per function (on premises) with checkboxes, *Select all*, **Delete selected** and **Delete all logs** (with a confirmation). Where pskit can't read a provider's logs the tab says why and links the console ([sources](#log-sources)) |
| Resources | each `resources:` entry: type, managed/external, native name, bound functions, connection **key names** |
| Outputs | the other Terraform outputs of the deployment |

The URL hash keeps the selected deployment and tab (`#/onprem-dev/executions`), so views survive a reload and can be linked.

User data is always rendered as text, and only `http(s)` URLs become links.

## Live mode

`pskit dashboard --serve` binds `127.0.0.1:8765` and serves the page at `/` plus this API. `<key>` is the deployment key `<provider>-<stage>`, the name of its `.pskit/` directory:

| Request | Returns |
|---|---|
| `GET /api/deployments` | `{"generated_at", "deployments": [record]}` (the records of every `.pskit/*/deployment.json`) |
| `GET /api/deployments/<key>/health` | `{"live": bool, "reason"?, "health"?, "stats"?}` |
| `GET /api/deployments/<key>/logs?since=&limit=&level=&function=&source=&q=` | `{"supported", "reason", "mode", "can_delete", "console", "entries", "next"}` ([sources](#log-sources)) |
| `GET /api/deployments/<key>/logs/streams?function=` | `{"supported", "reason", "can_delete", "items": [{"id", "function", "name", "first", "last", "bytes"/"count"}]}` |
| `POST /api/deployments/<key>/logs/delete` | body `{"ids": [stream ids]}`, `{"function": name}` or `{"all": true}`. Returns `{"deleted", "errors"}` |
| `GET /api/deployments/<key>/executions?workflow=&status=&limit=&offset=&token=` | `{"items", "total", "next_token", "supported", "reason"}` |
| `GET /api/deployments/<key>/executions/<id>?workflow=` | one execution with history and output |
| `POST /api/deployments/<key>/workflows/<name>/start` | start a run. The JSON body is the input |
| `POST /api/deployments/<key>/executions/<id>/cancel?workflow=` | cancel a run |

Errors are `{"error": "..."}` with `400` (bad parameters, or not available for this deployment, e.g. deleting GCP logs), `404` (unknown deployment, workflow or execution), `413` (body over 1 MiB) or `502` (host unreachable, cloud API error, missing `[aws]`/`[gcp]` extra).

For on-premises deployments the server talks to the host itself: on loopback for `method: local`, otherwise at the advertised endpoint. It reads the admin token from `.pskit/onprem-<stage>/onprem_app/pskit_host.json`. For AWS and GCP it uses your local cloud credentials ([details](workflow-executions.md#aws-step-functions-and-google-cloud-workflows)).

### Log sources

| Provider | Read | Delete | Needs |
|---|---|---|---|
| On premises | the host's log buffer ([details](providers.md#logs-and-stats)) | per function, host notes, or everything (memory and `host.jsonl`) | the host is running |
| AWS | CloudWatch Logs group `/aws/lambda/<function>` | log streams (the log group is kept: Terraform owns it) | `pip install "py-serverless-kit[aws]"`, AWS credentials with `logs:FilterLogEvents`, `logs:DescribeLogStreams`, `logs:DeleteLogStream` |
| GCP | Cloud Logging entries of the function (Cloud Run revision / Cloud Function) | — (set retention on the log bucket) | `pip install google-cloud-logging`, application-default credentials |
| Azure | `AppTraces` in Log Analytics | — (workspace retention) | a Terraform output `log_analytics_workspace_id` (add it with `provider.terraform.extra`), `pip install azure-monitor-query azure-identity` |
| Others | — | — | use the console link the tab shows |

On premises `since`/`next` are sequence numbers (`mode: "seq"`). For clouds (`mode: "time"`) they are millisecond timestamps: `since=0` reads the last 15 minutes, then poll with `next`. Cloud log pipelines lag a few seconds. JSON lines written by `ctx.logger` are split into level, message, request id and fields; Lambda `START`/`END`/`REPORT` lines are `invocation` entries.

### Security

- Loopback only by default. `--host 0.0.0.0` prints a warning: anyone who can reach the port can read logs and start or cancel executions. Put it behind your own authentication if you need that.
- Requests whose `Host` header isn't the bound address (or `localhost`) get `421`, which blocks DNS rebinding.
- `POST` requires `content-type: application/json` and, when the browser sends one, a same-origin `Origin` (`403` otherwise).
- Admin tokens and cloud credentials never reach the browser. Responses carry a strict CSP, `nosniff` and `no-store`.

## Where the data comes from

Each deploy writes `.pskit/<provider>-<stage>/deployment.json`, built from the config plus the `pskit` Terraform output. The dashboard reads all of these files: deploy `aws` and `gcp`, `dev` and `prod`, and they all appear on one page. `pskit info --json` prints the same record. It includes `key` and `resources` (connection key names only).

If nothing is deployed yet, `pskit dashboard` renders the configured functions as a `local` record. `pskit dev` serves that view at `/__pskit/`.

Because `.pskit/` is git-ignored and local, CI runs and other machines each have their own records. To share a dashboard:

- upload `.pskit/dashboard/index.html` as a CI artifact. [`examples/15-ci-cd-deploy`](../examples/15-ci-cd-deploy) does this;
- or publish it to a private static site or bucket.

The page contains resource names, URLs and ids, so treat it as internal.

## Changing the UI

The page is built from [`dashboard-ui/`](../dashboard-ui) (Vite + React + TypeScript). See [Contributing](../deploy_docs/CONTRIBUTING.md#dashboard-ui). You don't need Node to install or use pskit: the built page ships inside the package.
