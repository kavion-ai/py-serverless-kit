# Read the logs of your functions

Search terms: logs, log, pskit logs, tail, follow, -f, CloudWatch, Cloud Logging, Log Analytics, Application Insights,
log streams, delete logs, ctx.logger, logging, print, log level, Logs page, live logs, ailogs, debug

Every deployment type has logs, and pskit reads most of them for you in one format: time, level, function, message.
This page lists every way to write logs from a handler and every way to read them: the terminal, the studio, the
dashboard and the cloud consoles.

## Where the logs of each deployment type come from

pskit picks the log source from the deployment record (`deployment.json`) of the provider and stage.

| Deployment | pskit reads | Delete from pskit | Needs on this machine |
|---|---|---|---|
| On premises (this machine, SSH, Docker, cluster, groups) | the host's log buffer | yes: per function, host notes, or all | the host is running |
| AWS | CloudWatch Logs group `/aws/lambda/<function>` | log streams (the group itself stays) | `pip install "py-serverless-kit[aws]"` and AWS credentials |
| GCP | Cloud Logging entries of the function | no (set retention on the log bucket) | `pip install google-cloud-logging` and application-default credentials |
| Azure | `AppTraces` in the Log Analytics workspace | no (workspace retention) | `pip install azure-monitor-query azure-identity` and Azure credentials |
| Alibaba, Tencent, Huawei, IBM, DigitalOcean, Oracle, Cloudflare | nothing: pskit shows the console link | no | open the console link from `pskit info` |

When a source can't be read, `pskit logs` and the studio say why, for example
`reading CloudWatch Logs needs boto3: pip install 'py-serverless-kit[aws]'. Open the function's console link instead.`

## Write logs from a handler

Handlers log with `ctx.logger`, the standard `logging` module, or `print()`. `ctx.logger` already carries the
function name, the request id and the provider.

```python
import logging

log = logging.getLogger(__name__)


def create(event, ctx):
    ctx.logger.info("order created", extra={"order_id": 42, "amount": 9.5})
    log.warning("stock is low")
    print("plain output")          # recorded as stdout on premises
    return {"ok": True}
```

In the cloud each line is one JSON object, which every cloud log service indexes; pskit splits it back into level,
message, request id and fields:

```json
{"ts": "2026-01-01T12:00:00+00:00", "level": "INFO", "logger": "pskit.function", "message": "order created",
 "function": "create", "request_id": "...", "provider": "aws", "order_id": 42, "amount": 9.5}
```

| Variable | Effect |
|---|---|
| `PSKIT_LOG_LEVEL` (or `LOG_LEVEL`) | minimum level, default `INFO` |
| `PSKIT_LOG_FORMAT` | `json` (default in the cloud) or `text` (default under the CLI) |

Set them in `provider.environment` or `functions.<fn>.environment`. In studio: **Functions** → a function →
**Logging** → **Log level** (*inherit*, *DEBUG*, *INFO*, *WARNING*, *ERROR*) writes `PSKIT_LOG_LEVEL` for that
function. More: [handlers.md](../handlers.md#logging).

## Read logs from the terminal with pskit logs

`pskit logs` prints the newest entries of the current provider and stage.

```bash
pskit logs -s dev                          # the newest 100 entries
pskit logs -s dev -f                       # keep printing new entries (Ctrl+C stops)
pskit logs -f --function worker            # one function
pskit logs --level ERROR -n 500            # errors and worse
pskit logs --source invocation             # one line per handler call
pskit logs -q timeout --json               # text search, one JSON object per line
```

| Flag | Meaning |
|---|---|
| `-f, --follow` | keep printing new entries (polls every 1 s on premises, every 3 s on a cloud) |
| `-n, --lines N` | how many recent entries to show first (default 100) |
| `--function NAME` | only this function |
| `--level LEVEL` | minimum level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `--source KIND` | only `function`, `host`, `stdout`, `stderr` or `invocation` entries |
| `-q, --grep TEXT` | only entries whose message contains this text (case-insensitive) |
| `--json` | one JSON object per line: `seq`, `ts`, `level`, `source`, `function`, `request_id`, `message`, `fields` |
| `--streams` | list log streams instead of entries |
| `--delete STREAM` | delete a log stream (repeatable) |
| `--delete-all` | delete every stream of `--function`, or of all functions |
| `-y, --yes` | do not ask before deleting |

The project options work too: `-p`, `-s`, `-r`, `-c`, `--server`, `--cluster`. Cloud logs read the last 15 minutes
first; cloud log pipelines lag a few seconds behind.

## List and delete log streams

A log stream is one CloudWatch stream on AWS, or one function (plus `__host__` for host notes) on premises.

```bash
pskit logs --streams                         # last event, function, size or count, id
pskit logs --streams --function worker
pskit logs --delete worker --yes             # on premises: clear one function's entries
pskit logs --delete-all --function worker    # every stream of one function
pskit logs --delete-all --yes                # everything of this deployment
```

Deleting works on premises and on AWS. GCP and Azure logs are read-only from pskit: they expire with the log bucket
or workspace retention. On AWS the log group is never deleted (Terraform owns it); `provider.log_retention_days`
(default 14) sets how long CloudWatch keeps entries.

## Read logs on premises

The on-prem host records everything into one log:

- `logging` records, including `ctx.logger` (source `function`), at `INFO` and above by default;
- `print()` and `sys.stdout` lines (source `stdout`, level `INFO`) and `sys.stderr` lines (source `stderr`,
  level `WARNING`);
- one `invocation` entry per handler call with function, event type, duration, and for HTTP the method, path and
  status; a failure (an exception or an HTTP status of 500 or more) is `ERROR`;
- host notes (source `host`): failed schedules, unreachable services, runs aborted by a restart, the listen address.

The newest 5000 entries stay in memory and every entry is appended to `<data_dir>/logs/host.jsonl` (rotated at 10 MiB,
three old files kept). Tune it under `provider.options` (studio: **Overview & provider** → **Host tuning**):

```yaml
provider:
  name: onprem
  options:
    log_buffer: 5000          # entries kept in memory (min 100)
    log_level: INFO           # minimum level captured from logging
    capture_output: true      # also record print() / stdout / stderr
```

`pskit logs` reads the host the stage was last deployed to. `--server NAME` reads another saved server. When the
host's port (default 8080) is closed to this machine, pskit reads the logs over the deploy's SSH login. On a scaling
cluster, web replicas send their lines to the main replica, so one read shows all of them (a Nomad cluster is read
from every server); the `node` field says which replica wrote a line. With placement, every group sends its logs to
the default group; the `group` and `node` fields say where a line ran.

## Read logs on AWS, GCP and Azure

pskit reads cloud logs with this machine's default credentials. Deploy first: logs need `deployment.json`.

- **AWS**: CloudWatch Logs group `/aws/lambda/<function>`. Install `pip install "py-serverless-kit[aws]"`. The
  credentials need `logs:FilterLogEvents`, `logs:DescribeLogStreams` and, to delete, `logs:DeleteLogStream`. Lambda's
  `START`, `END` and `REPORT` lines are `invocation` entries.
- **GCP**: Cloud Logging entries of the function. Install `pip install google-cloud-logging` and sign in with
  `gcloud auth application-default login`.
- **Azure**: the Function App's `AppTraces` in Log Analytics. pskit creates the workspace and Application Insights
  and writes the `log_analytics_workspace_id` output, unless `provider.options.app_insights` is `false`. Install
  `pip install azure-monitor-query azure-identity` and sign in with `az login`.

Studio checks these packages on **Setup & credentials** (*Python package ...*, marked optional).

## Read logs in studio on the Logs page

The studio **Logs** page shows a live tail of the deployment chosen in the top bar.

1. In the top bar, pick the provider in **validate & deploy as** and type the **stage**.
2. Click **Logs** in the sidebar.
3. On premises, check the **Server** (it starts on the server the stage was deployed to). On a cluster or with
   placement the box says **Source**: every replica or every group, and there is no picker.
4. Read the live tail. Use the toolbar: **Search messages…**, **Level**, **Function**, **Source**, **❚❚ Pause** /
   **▶ Resume**, **Clear** (clears the view only; logs stay on the server) and **Console ↗** (the provider console).
   On premises, **Load older** at the top scrolls back.
5. Expand **Stored logs** to list streams: pick a **Function**, **↻ Refresh**, tick rows, then **Delete selected (N)**
   or **Delete all logs** (or *Delete all logs of FUNCTION*). A dialog asks before anything is deleted.

When logs can't be read, the page shows **Logs unavailable** with the reason and a link to the console. Missing
credentials: **Setup & credentials**.

## Read the logs of one function in studio

Two pages show one function's logs next to its settings:

- **Functions** → a function → **Logging** → switch **Live logs** on. All functions: the **Logs** page.
- **Test** → a function → switch **Show the function's logs** on (after the function is deployed). Send a test
  event and watch the result arrive.

Both use the provider and stage in the top bar.

## Read cluster and load balancer logs

On a scaling cluster, the studio **Scaling cluster** page has **Live logs** (pick the deployment) and **Live requests**
(which server handled each request). From the terminal:

```bash
pskit logs -f -s prod                       # every replica of the stage
pskit cluster requests prod --follow        # requests and how HTTP is spread over the servers
pskit lb logs edge -n 200                   # load balancer: requests (upstream= is the server that answered) and errors
```

Details: [scaling](../onprem/scaling/README.md) and [load balancers](../onprem/load-balancers.md).

## Read logs in the dashboard

`pskit dashboard --serve` serves the deployment dashboard with live data. Open a deployment and its **Logs** tab: the
live tail with level, function and source filters, search, pause and *load older*, and a log streams list with
**Delete selected** and **Delete all logs**. The static page (`pskit dashboard` without `--serve`) says that live data
needs the server. See [monitoring and dashboard](monitoring-and-dashboard.md).

## Read logs while developing locally

`pskit dev` runs the functions on this machine with hot reload and prints handler logs in that terminal, as text.
`pskit invoke -f NAME` prints the logs of one local call. See [invoke and test](../functions/invoke-and-test.md).

## See what Hana does with --ailogs

The studio assistant Hana can print every step of every chat to the terminal that runs studio: your messages, model
requests and answers, tool calls with arguments and results, plans, cards and errors. Passwords stay hidden.

```bash
pskit studio --ailogs=true        # or --ailogs, or PSKIT_HANA_AILOGS=1
```

Entry names (`USER`, `MODEL REQUEST`, `TOOL CALL`, ...) are listed in [assistant.md](../assistant.md#see-everything-hana-does---ailogs).

## Fix logs that don't show

| Message | Fix |
|---|---|
| `not deployed yet; run pskit deploy to read its logs` | deploy the stage first, or pick the right `-s` / `-p` |
| `the on-premises host address is unknown; run pskit deploy first` | the stage has no `onprem_deployed.json` yet; deploy it, or import settings from the machine that deployed it |
| `reading ... needs ...: pip install ...` | install the named package in the same Python as pskit |
| `pskit can't read <provider> logs yet` | use the console link from `pskit info` |
| `... some entries were dropped from the host's buffer ...` | the host dropped entries before you read them; raise `log_buffer` |
| No lines at all | lower the level: `PSKIT_LOG_LEVEL=DEBUG`; on premises check `capture_output` |

## See also

- [Monitoring and dashboard](monitoring-and-dashboard.md)
- [Deployment types](README.md)
- [Workflows](workflows.md)
- [Handlers: logging](../handlers.md#logging)
- [Dashboard reference](../dashboard.md#log-sources)
- [On-prem provider: logs and stats](../providers.md#logs-and-stats)
