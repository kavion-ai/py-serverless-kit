# Concept: the dashboard

The dashboard is one self-contained HTML page. `pskit deploy` and `pskit remove` regenerate `.pskit/dashboard/index.html`. A static file shows deployments, functions, triggers, endpoints, ids, workflows, resources, and outputs as of the last deploy. You can open it from disk or host it. Live mode is `pskit dashboard --serve`. It re-reads records on refresh and adds host health and invocation stats on premises, logs, and workflow executions.

```
pskit dashboard --open
pskit dashboard --serve --open --port 9000
```

`--serve` binds 127.0.0.1 and port 8765 unless you change them. `-o` writes the HTML somewhere else. `-d` is the project root.

Overview has summary cards and a table of deployments with provider, tier, status (`deployed`, `removed`, or `local`), region, endpoint, and last update. A deployment page has Functions, Workflows, Executions, Logs, Resources, and Outputs. The URL hash keeps the deployment and tab, for example `#/onprem-dev/executions`. User data is rendered as text. Only `http(s)` URLs become links.

Live logs can tail, list streams, and delete on premises and AWS. GCP and Azure are read-only. Executions can be listed, started, followed, and cancelled for on-premises, AWS Step Functions, and GCP Workflows. A static page says those tabs need `--serve`.

Security: loopback is the default. `--host 0.0.0.0` prints a warning because anyone who can reach the port can read logs and start or cancel executions. A foreign Host header gets 421. POST requires `content-type: application/json`. Admin tokens and cloud credentials stay on the server. The page contains resource names, URLs, and ids, so the doc says to treat it as internal.

Sources: `docs/dashboard.md#dashboard`, `docs/dashboard.md#what-it-shows`, `docs/dashboard.md#live-mode`, `docs/dashboard.md#security`
