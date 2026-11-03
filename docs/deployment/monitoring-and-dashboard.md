# Monitor deployments and use the dashboard

Search terms: dashboard, pskit dashboard, monitoring, monitor, health, stats, invocations, errors, CPU, memory, disk,
live monitoring, alerts, webhook, Slack, capacity, cluster full, replica lag, server usage, --serve

pskit gives you two kinds of monitoring. The **deployment dashboard** is one HTML page that lists everything you
deployed, on every provider and stage, with live logs and workflow executions when served. **On-prem monitoring**
measures your own servers, services and clusters: CPU, memory, disk, connections, replica lag, with alerts to a
function or a webhook.

## Generate the deployment dashboard with pskit dashboard

The deployment dashboard is one self-contained HTML file at `.pskit/dashboard/index.html`. `pskit deploy` and
`pskit remove` regenerate it (skip on deploy with `--no-dashboard`). It reads every `.pskit/*/deployment.json`, so
`aws/dev`, `aws/prod` and `onprem/dev` all show on one page.

```bash
pskit dashboard                        # regenerate the static page
pskit dashboard --open                 # regenerate and open it in the browser
pskit dashboard -o site/index.html     # write it somewhere else
pskit dashboard -d path/to/project     # another project folder
```

| Flag | Meaning |
|---|---|
| `-d, --dir DIR` | project root (default `.`) |
| `-o, --output FILE` | write the HTML here |
| `--serve` | serve the page with live logs and workflow executions |
| `--host HOST` | bind address for `--serve` (default `127.0.0.1`) |
| `--port PORT` | port for `--serve` (default `8765`) |
| `--open` | open it in the browser |

With nothing deployed yet, the page shows the configured functions as a `local` record.

## Serve the live dashboard with pskit dashboard --serve

The live dashboard is the same page served by a small local server that adds a JSON API. It re-reads the records on
every refresh and adds what a static file can't: on-prem host health and stats, live logs, and workflow executions.

1. Run:

   ```bash
   pskit dashboard --serve --open
   ```

2. The browser opens `http://127.0.0.1:8765/`. Click a deployment row.
3. Use the tabs: **Functions**, **Workflows**, **Executions**, **Logs**, **Resources**, **Outputs**.
4. Stop the server with Ctrl+C in the terminal.

The server binds `127.0.0.1` only. `--host 0.0.0.0` prints a warning: anyone who can reach the port can read logs and
start or cancel executions. Admin tokens and cloud credentials never reach the browser. The API and the security
rules are in [dashboard.md](../dashboard.md#live-mode).

## What the deployment dashboard shows

The overview page has summary cards (deployments, functions, workflows, resources, providers) and a table of
deployments: provider and tier, status (`deployed`, `removed`, `local`), region, endpoint, last update. Click a row
for one deployment:

| Tab | Content |
|---|---|
| **Functions** | name and cloud name, kind, triggers, runtime, memory, timeout, endpoints, id or ARN, console link. Live on premises: invocations, errors, average duration and last error per function |
| **Workflows** | engine, the states, task functions, id and console link; **▶ Start** and **Executions** in live mode |
| **Executions** | filter by **Workflow** and **Status**, **↻ Refresh**, **▶ Start execution**; click a run for its history, input, output, error and **Cancel** |
| **Logs** | live tail with filters, search, pause, *load older*, and a log streams list with delete ([logs](logs.md#read-logs-in-the-dashboard)) |
| **Resources** | each `resources:` entry: type, managed or external, native name, bound functions, connection key names |
| **Outputs** | the other Terraform outputs |

In live mode an on-prem deployment also shows cards for uptime, invocations, errors and queued messages. The URL keeps
the deployment and tab (for example `#/onprem-dev/executions`), so you can bookmark a view.

## Start and follow workflow executions in the dashboard

The dashboard starts and follows workflow runs on the on-prem host, AWS Step Functions and Google Cloud Workflows.

1. `pskit dashboard --serve --open`, then click the deployment.
2. **Workflows** → **▶ Start** on a workflow (or **Executions** → **▶ Start execution**).
3. In **Start workflow execution**, pick the **Workflow**, type the **Input (JSON)**, click **Start execution**.
   The dialog shows the **Execution id** with a copy button.
4. Open **Executions**. The list refreshes while a run is `RUNNING`. Click a run to see its timeline.
5. Click **Cancel** in the detail panel to stop a running execution.

Terminal equivalents: [workflows](workflows.md#follow-a-workflow-execution-status-and-history).

## Share the deployment dashboard

`.pskit/` is local and git-ignored, so each machine and each CI run has its own records. To share the page, upload
`.pskit/dashboard/index.html` as a CI artifact (see [`examples/15-ci-cd-deploy`](../../examples/15-ci-cd-deploy)) or
put it on a private static site. The page holds resource names, URLs and ids: keep it internal.

## Check on-prem host health and invocation stats

Every on-prem host answers two monitoring requests. Health needs no token; stats needs the `x-pskit-token` header when
`provider.options.admin_token` is set.

```bash
curl -s http://127.0.0.1:8080/__pskit/health
curl -s -H "x-pskit-token: $PSKIT_ADMIN_TOKEN" http://127.0.0.1:8080/__pskit/stats
```

Stats return the start time, uptime, and per function the invocations, errors, average and last duration, last call
and last error, plus queue depths. Counters reset when the host restarts. The live dashboard shows the same numbers;
`pskit client info` prints the endpoint and token for scripts ([client.md](../client.md)).

## Watch a server's CPU, RAM and disk in studio

Saved on-prem servers have a live usage view in studio.

1. Open **Resources** → **On-prem services** → **Servers**.
2. Click **Live** on a server row (it turns into **Live ●**).
3. The row shows **CPU** (cores and load), **RAM** and **Disk** bars with small history graphs. They refresh every
   4 seconds while on. Click again to stop.

A server that can't be reached shows the SSH error instead. Which projects use a server: the *Used in* column of the
same list ([servers](../onprem/servers.md)).

## Monitor an on-prem service live

On-prem services (Redis, PostgreSQL, MySQL, MariaDB, MongoDB, MinIO, ...) have live monitoring. pskit measures every
container of the service: CPU and memory (`docker stats`), how full the data disk is, and for PostgreSQL, MySQL,
MariaDB and MongoDB the open connections, the data size and each replica's lag.

In studio:

1. Open **Resources** → **On-prem services**, click **Details** on the service.
2. Under **Live monitoring**, switch the toggle **On (every 5 s)**. Nothing is measured while it is **Off**.
3. Read the badges (connections, data size, `NAME: N s behind` per replica) and the table: **Container**, **State**,
   **CPU**, **Memory**, **Disk (data)**. Bars turn red at the alert limits when alerts are on.

From the terminal:

```bash
pskit resources onprem monitor orders-db               # one measurement
pskit resources onprem monitor orders-db --watch 10    # every 10 s until Ctrl+C
pskit resources onprem monitor orders-db --json
```

## Get alerts when an on-prem service is in trouble

Service alerts fire when a container goes over a CPU, memory or disk limit, a replica falls behind, or a container is
down. An alert runs a function of your project (through the deployed host) and/or POSTs JSON to a webhook (Slack,
Teams, Google Chat, any URL). At most one alert per cooldown.

| Setting | Default | CLI flag |
|---|---|---|
| CPU percent of a container | 90 | `--cpu` |
| Memory percent | 90 | `--memory` |
| Data disk percent | 85 | `--disk` |
| Seconds a replica is behind | 60 | `--lag` |
| Minutes between alerts | 30 | `--cooldown` |
| A container is down | on | (studio: *Also when a container is down*) |

In studio: **Resources** → **On-prem services** → **Details** → **Alerts**. Pick **Run a function** (an existing
function, or **+ Create a new function: KEY-alert**) and/or a **Webhook**, set **CPU %**, **Memory %**, **Disk %**,
**Replica lag (s)** (replicated databases) and **Cooldown (min)**, then click **Turn alerts on** (later **Save**).
**Send a test alert** and **Check now** test it; **Turn off** keeps the settings. The last alerts are listed below.

```bash
pskit resources onprem alerts orders-db --on --webhook https://hooks.slack.com/services/... --cpu 80
pskit resources onprem alerts orders-db --function notify-devops --stage prod
pskit resources onprem alerts orders-db --test         # send a test alert now
pskit resources onprem alerts orders-db --check        # measure now, alert when over a limit (for cron)
```

Studio checks services with alerts on while it runs. Without studio, run `--check` from cron. The alert function gets
`event.data` with `kind` (`pskit.database.alert` or `pskit.service.alert`), `key`, `service`, `reasons`, `message`,
`at` and the measured `sample`.

## Monitor a scaling cluster's capacity

A scaling cluster counts a server as **full** at 85% CPU, 85% memory or 90% disk (defaults). When every server is
full, pskit can call an alert function and/or a webhook, so someone joins another server.

```bash
pskit cluster status prod                         # every server's CPU, memory, disk, the replicas, FULL or not
pskit cluster check prod                          # once; alerts when full; exit code 3 when full
pskit cluster watch prod --interval 60            # check until Ctrl+C (run it on an always-on machine)
pskit cluster alerts prod --function notify-devops --webhook https://... --cpu 80 --test
pskit cluster scale prod --replicas 6
```

In studio, open **Scaling cluster**: the **Servers** table shows CPU, memory and disk meters and refreshes every 30 s;
**Refresh** and **Check & alert** are at the top. Under **When every server is full** set **CPU full at %**,
**Memory full at %**, **Disk full at %**, **Alert function**, **Stage**, **Webhook (optional)**, **Cooldown
(minutes)** and **Watch while the studio runs**, then **Save** and **Send test alert**. **Live requests** shows which
server answered each request. Details: [replicas and alerts](../onprem/scaling/replicas-and-alerts.md).

## Check an on-prem load balancer

Shared on-prem load balancers report whether they run, their server's use and every route on them:

```bash
pskit lb status edge
pskit lb logs edge -n 200
```

In studio: **Load balancers**. Details: [load balancers](../onprem/load-balancers.md).

## See also

- [Logs](logs.md)
- [Workflows](workflows.md)
- [Deployment types](README.md)
- [On-prem overview](../onprem/README.md) and [scaling](../onprem/scaling/README.md)
- Existing reference: [dashboard.md](../dashboard.md), [cluster.md](../cluster.md#monitor-scale-and-add-servers-when-it-is-full)
