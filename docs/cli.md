# CLI reference

```
pskit [--version] [-h] <command> [options]
```

`py-serverless-kit` is an alias of `pskit`.

`pskit --help` lists every command and `workflow` subcommand, grouped (getting started, develop, deploy, operate,
reference) with a one-line example each. `pskit COMMAND --help` shows every option of a command plus examples.

| Group | Commands |
|---|---|
| Getting started | `init`, `studio`, `doctor` |
| Develop | `dev`, `invoke`, `validate` |
| Deploy | `package`, `plan`, `deploy`, `info`, `remove`, `tf` |
| Operate | `logs`, `dashboard`, `workflow run / show / start / executions / status / cancel` |
| Reference | `providers` |

## Common project options

Every command that loads a project accepts:

| Flag | Meaning |
|---|---|
| `-c, --config FILE` | config file (default: `pskit.yml`, `pskit.yaml`, `serverless_kit.yml`, `serverless_kit.yaml`) |
| `-p, --provider NAME` | override `provider.name` (`aws`, `azure`, `gcp`, `alibaba`, `oracle`, `ibm`, `digitalocean`, `tencent`, `huawei`, `cloudflare`, `onprem`) |
| `-s, --stage NAME` | stage, e.g. `dev`, `staging`, `prod` |
| `-r, --region NAME` | override `provider.region` |
| `-v, --verbose` | print tracebacks on errors |

Configuration, packaging, provider and Terraform errors print a single `Error: …` line and exit with code 1.

## `pskit init [DIRECTORY]`

Scaffold a project (default directory `.`).

| Flag | Default | |
|---|---|---|
| `--name` | directory name | service name |
| `-p, --provider` | `aws` | target cloud (fills in region and required options) |
| `-t, --template` | `http` | `http`, `events` (+ schedule/queue/storage), `workflow` (+ order workflow), `full` (everything) |
| `--force` | | overwrite existing files |

```bash
pskit init orders-api -p gcp -t full
```

## `pskit validate`

Validate the config for the selected provider: schema, unsupported triggers/options, runtime, timeouts, required options, and that handler modules exist. Prints errors and warnings, and exits 1 on errors.

```bash
pskit validate --provider azure --stage prod
```

## `pskit package`

Build `.pskit/<provider>-<stage>/artifact.zip` and `main.tf.json` without calling the cloud.

| Flag | |
|---|---|
| `--skip-deps` | don't pip-install `requirements.txt` into the bundle |

## `pskit plan`

Package, `terraform init`, then `terraform plan`.

| Flag | |
|---|---|
| `--skip-deps` | as above |
| `--destroy` | plan a destroy |

## `pskit deploy`

Package, then `terraform init` and `terraform apply`. Saves `deployment.json`, prints endpoints and ids, and regenerates the dashboard.

| Flag | |
|---|---|
| `--skip-deps` | don't vendor dependencies |
| `--confirm` | run `terraform plan -out tfplan`, then apply that plan instead of `-auto-approve` |
| `--upgrade` | `terraform init -upgrade` (update provider plugins) |
| `--no-dashboard` | don't regenerate `.pskit/dashboard/index.html` |

Hooks `before_package`, `after_package`, `before_deploy` and `after_deploy` run around these steps.

## `pskit remove`

`terraform destroy` for this service, stage and provider. Marks the deployment record as `removed`.

| Flag | |
|---|---|
| `-y, --yes` | don't ask for confirmation |
| `--keep-resources` | keep managed buckets, queues and topics (and their data); only functions, triggers and gateways are destroyed |

With `--keep-resources` the kept resources are taken out of the Terraform state first, so pskit no longer manages
them: delete them in the cloud console when you no longer need them, or import them into another stack. The
code-upload bucket is not kept. On Azure the storage account, Service Bus namespace and resource group that hold kept
queues, containers or topics are kept as well. Supported on AWS, GCP, Azure, Alibaba, Tencent, Huawei and Oracle; the
other providers create no buckets, queues or topics.

Kept resources are remembered in `.pskit/<provider>-<stage>/kept/` (their Terraform state plus the provider settings),
so they can be deleted later with `pskit resources delete`.

## `pskit trigger`

Send a **real** test event to a deployed function, the way its trigger would: an HTTP request to its URL, a message to
its queue, an object uploaded to its bucket, a message published to its topic, or a direct invocation (schedules are
fired by invoking the function with the schedule's input). Test without deploying with `pskit invoke`.

```bash
pskit trigger --list                                   # every function and trigger: payload, local command,
                                                       # pskit command, cloud CLI command and console steps
pskit trigger -f worker -e 0 -d '{"order_id": 1}'      # trigger #0 of worker, e.g. an SQS message
pskit trigger -f worker -e 0 -d '[{"id": 1}, {"id": 2}]'   # two queue messages
pskit trigger -f thumbnails -e 0 -d '{"key": "in/a.png", "content": "x"}'   # upload an object
pskit trigger -f fanout -e 0 -d '{"message": {"id": 1}, "attributes": {"type": "order"}}'
pskit trigger -f api -e 0 --path '/orders/7?verbose=1'  # HTTP trigger with a path
pskit trigger -f nightly --direct                      # invoke directly, no trigger
pskit logs -f --function worker                        # then watch what it did
```

| Flag | |
|---|---|
| `-f, --function` | the function (all of them with `--list`) |
| `-e, --event N` | trigger number, in the order of `events:` (default: the first) |
| `--direct` | invoke the function directly instead of through a trigger |
| `-d, --data` | payload JSON or `@file.json`; default: a sample for the trigger type |
| `--path` | HTTP path and query string for HTTP triggers |
| `--list` | show how to test each trigger (works before deploying, too) |
| `--json` | JSON output |

What pskit can send itself (with the machine's credentials and SDKs):

| Provider | HTTP | queue | storage | topic | schedule / invoke |
|---|---|---|---|---|---|
| AWS (boto3) | ✓ | SQS | S3 | SNS | `lambda invoke` |
| GCP | ✓ | Pub/Sub | Cloud Storage | Pub/Sub | via the function URL (HTTP functions) |
| Azure | ✓ | Storage queue¹ | Blob¹ | Service Bus² | — |
| On premises | ✓ | ✓ | ✓ | ✓ | ✓ |
| IBM, DigitalOcean, Cloudflare, Oracle | ✓ | — | — | — | via the function URL |
| Alibaba, Tencent, Huawei | ✓ | — | — | — | — |

¹ `AZURE_STORAGE_CONNECTION_STRING` of the Function App's storage account. ² `AZURE_SERVICEBUS_CONNECTION_STRING`.
Where pskit can't send, `--list` prints the cloud CLI command (`aws`, `gcloud`, `az`, `ossutil`, `coscli`, `obsutil`,
`oci`, `ibmcloud`, `tccli`, `doctl`, `curl`) and the console steps instead.

Payload shapes per trigger type:

| Type | `-d` |
|---|---|
| http | the request body (none for GET) |
| queue | one message, or a list of messages |
| storage | `{"key": "...", "content": "..."}` (`"action": "deleted"` deletes it) |
| topic | `{"message": ..., "attributes": {...}}` |
| schedule / invoke | `event.data` |

## `pskit resources`

The buckets, queues and topics pskit created for this stage: **deployed** ones (in the stage's Terraform state) and
**kept** ones (left by `pskit remove --keep-resources`).

```bash
pskit resources list -s dev                         # status, kind, name, Terraform address
pskit resources delete aws_s3_bucket.b_uploads -s dev
pskit resources delete --all-kept -s dev --yes
```

| Command / flag | |
|---|---|
| `list [--json]` | list deployed and kept buckets, queues and topics |
| `delete ADDRESS...` | delete them permanently, with their objects and messages |
| `delete --all-kept` | delete every kept resource |
| `send KEY [-d DATA]` | test a resource: a message to a queue, an object to a bucket, a message to a topic |
| `send --list` | how to test every resource: payload, pskit and cloud CLI commands, console steps; for database, cache and custom resources the `PSKIT_RESOURCE_*` variables and a Python / Node.js snippet |
| `usage KEY` | end-to-end guide for the resource as Markdown: libraries to install (Python / Node.js), the `pskit.yml`, handler code, local and deployed tests, provider notes, troubleshooting |
| `data KEY [--offset N] [-n LIMIT] [--prefix P] [--json]` | on premises: page through what a queue, topic or bucket holds (messages are not consumed) |
| `check KEY [--json]` | is it reachable? From the on-prem host once deployed there (queue depth, bucket object count, database / cache / custom connection, Redis `PING`), else a connection check from this machine; exits 1 when it fails |
| `clear KEY [--yes]` | on premises: delete every message / object of a built-in queue, bucket or topic on the host (the resource stays) |
| `-y, --yes` | don't ask for confirmation |

```bash
pskit resources check orders-db
pskit resources clear jobs --yes
pskit resources send --list
pskit resources send jobs -d '{"order_id": 1}'                       # queue message
pskit resources send uploads -d '{"key": "in/a.csv", "content": "a,b"}'   # object upload
pskit resources send events -d '{"message": {"id": 1}, "attributes": {"type": "order"}}'
```

## `pskit cluster`

Scale on-prem functions over a master plus joined servers (Docker Swarm, Kubernetes via k3s, Nomad). Details: [cluster.md](cluster.md).

| Command | |
|---|---|
| `cluster create NAME -o swarm\|kubernetes\|nomad --master SERVER [--advertise IP] [--nomad-version V] [--[no-]master-serves]` | install the orchestrator on a saved server and save the cluster |
| `cluster join NAME SERVER [--advertise IP]` | install the agent on a saved server, join it, copy the deployed images |
| `cluster set NAME --master-serves\|--no-master-serves` | send requests to the master too, or use it only while every other server is down |
| `cluster leave NAME SERVER [--yes]` | drain the server (replicas move) and remove it |
| `cluster status NAME [--json]` | CPU / memory / disk per server, replicas, pending replicas, full or not |
| `cluster check NAME [--no-alert]` | status once; when full, the alert (cooldown applies). Exit 3 when full |
| `cluster watch NAME [--interval 60]` | `check` every interval until Ctrl+C |
| `cluster alerts NAME [--function F] [--stage S] [--webhook URL] [--cooldown M] [--cpu N] [--memory N] [--disk N] [--test]` | who is alerted and when a server counts as full |
| `cluster scale NAME --replicas N [--stack S] [-s STAGE]` | web replicas now (keep it in `options.cluster.replicas`) |
| `cluster requests NAME [--follow] [--stack S] [-n 50]` | recent requests, and each server's URL with its share of HTTP |
| `cluster balancer set NAME SERVER [--port 80] [--address IP]` | run nginx on a saved server outside the cluster: one URL spread over its servers, updated by deploy / remove / join / leave |
| `cluster balancer sync NAME` / `cluster balancer logs NAME [-n 100]` / `cluster balancer remove NAME [--yes]` | rewrite the load balancer's config now / its access log / stop it |
| `cluster list [--json]` / `cluster remove NAME [--yes]` | list / forget clusters |
| `cluster remove NAME --uninstall [--delete-data] [--yes]` | stop the deployments and the load balancer, uninstall the agent from every joined server and the orchestrator from the master, then forget the cluster |

`pskit deploy | package | plan | remove | info --cluster NAME` runs the functions on that cluster instead of one server
(`--server NAME` goes back to one server; the stage remembers either). `pskit resources onprem create KEY --service S
--cluster NAME [--node SERVER]` places a resource on a server of the cluster.

## `pskit settings`

`.pskit` is kept out of git, so a fresh clone on another machine has no saved servers, clusters or SSH logins.
`settings` moves them in one passphrase-encrypted file, with `pskit.yml` too when asked. In the studio: the
**⇅ Settings** button in the header (also *Setup & credentials → Move settings to another machine*).

| Command | |
|---|---|
| `settings export [-o FILE] [--with-config]` | write `<service>.pskit-settings` (asks for a passphrase twice); `--with-config` adds `pskit.yml` |
| `settings import FILE [--dry-run] [--replace] [--yes]` | show what changes, back up the current settings to `.pskit/backups/settings-<time>.json`, then write them |

What the file holds:

| Inside | |
|---|---|
| `.pskit/onprem-servers.json` | saved servers |
| `.pskit/onprem-clusters.json` | scaling clusters, their load balancers, deployments, alert settings |
| `.pskit/onprem-services.json` | on-prem services (Redis, Postgres, MinIO, ...) with their passwords and tokens |
| `.pskit/ssh/` | SSH passwords typed in the studio |
| SSH key files | keys the servers and services use, also from outside the project (`~/.ssh/edge.pem`): written to `.pskit/ssh/keys/` on import, and the settings point there |
| `.pskit/onprem-<stage>/onprem_deployed.json`, `deployment.json` | where each on-prem stage was last deployed, with its admin token, so `pskit logs`, `test`, `info` and the studio reach it at once |
| `.pskit/studio/test-events.json` | the studio's saved test events |
| env files | files named by `env_file` in `pskit.yml`, when they are inside the project |

Not inside: Terraform state (on-prem deploys do not need it; keep a cloud stage's state in a remote backend),
build output and backups. Paths inside the project are stored relative to it, so the project can sit in another
folder, or on another OS, after the import.

**Merge or replace.** By default saved servers, clusters and services merge by name: entries in the file are
added or replace the local ones with the same name, and the others stay. `--replace` (studio: *Replace*) drops
local entries the file does not have. Other files are replaced.

**Encryption.** The file is always encrypted (passphrase of at least 8 characters): scrypt derives the keys, and
the payload is encrypted and authenticated with HMAC-SHA256 (encrypt-then-MAC). A wrong passphrase or a changed
file is refused before anything is written. Send the file and the passphrase by different channels. From a script,
set `PSKIT_SETTINGS_PASSPHRASE` instead of typing it.

## `pskit client`

Call the deployed on-prem host from scripts. Details: [client.md](client.md).

| Command | |
|---|---|
| `client info [-p onprem -s STAGE] [--json]` | endpoint, token, whether this machine reaches the host, Python / Node.js / curl code for each resource |
| `client install-node [--dir DIR]` | copy the `pskit` Node.js package (with `PskitClient`) to `DIR/node_modules/pskit` |
| `client tunnel [--local-port N]` | forward `127.0.0.1:<port>` to the host on its SSH server until Ctrl+C |

### `pskit resources onprem`

Create the services on-premises functions use, as Docker containers on this machine or on an SSH server, and add them
to `pskit.yml`. Step by step: [resource-guides/onprem/services.md](resource-guides/onprem/services.md).

```bash
pskit resources onprem catalog
pskit resources onprem create jobs --service redis --attach worker --save
pskit resources onprem create events --service kafka --ssh ubuntu@10.0.0.7 --pem key.pem --sudo --save
pskit resources onprem create cache --service redis --role cache --ssh ubuntu@10.0.0.7 --gui --gui-login none   # agent / default key
pskit resources onprem ssh-key azureuser@13.72.87.80          # password server: install a key once
pskit resources onprem gui jobs --check                       # why does the web UI not open?
pskit resources onprem status jobs --reveal
pskit resources onprem backup jobs
pskit resources onprem remove jobs --delete-data --save
```

| Command / flag | |
|---|---|
| `catalog [--json]` | services (redis, valkey, kafka, nats, rabbitmq, elasticmq, minio, postgres, mysql, mariadb, mongodb, memcached, mailpit) and runtimes (python, docker) |
| `create KEY --service S` | start it (or install the runtime) and record it in `.pskit/onprem-services.json` |
| `--role` | what the resource is used as: `queue`, `stream` (Redis / Valkey stream), `cache`, `database`, `storage`, `custom` |
| `--ssh user@host[:port] --pem FILE --sudo` | create it on that server (default: `provider.options.deploy` when it targets one, else this machine); `--local` forces this machine. Without `--pem`: the SSH agent / default key |
| `--ssh-password-env VAR`, `--ssh-password-file FILE` | log in with a password instead of a key (through `sshpass`; never on a command line) |
| `--gui`, `--gui-login password\|none`, `--gui-password-env VAR` | also start the companion web UI (Adminer, Redis Commander, Kafka UI, Mongo Express), with a generated password, your own, or none |
| `--user`, `--password`, `--password-env VAR` | credentials to create (default user `pskit`, Redis `default`; default password generated) |
| `--port`, `--address`, `--bind`, `--image` | published port, address functions use, interface to listen on, Docker image |
| `-a, --attach FN` | add a `queue` / `storage` trigger on resource KEY to FN (repeatable) |
| `--save` | write the resource, `provider.options.env_file` and triggers into `pskit.yml` (comments are not kept) |
| `gui KEY [--port N] [--login password\|none] [--password-env VAR] [--remove]` | start (or recreate / remove) the companion web UI, and list every web UI of the service with its login |
| `gui KEY --check` | why a web UI does not open: container, published port, answer on the server and from here, cloud firewall / NSG (Azure, AWS, GCP), ufw / firewalld; exits 1 when one is unreachable |
| `servers list\|add NAME --ssh user@host [--pem\|--ssh-password-env] [--sudo]\|test NAME\|usage [NAME]\|remove NAME` | saved SSH servers; `create --server NAME` and `pskit deploy --server NAME` use them; `usage` lists where each one is used |
| `create KEY --service nodejs\|nginx\|java\|go\|caddy\|certbot\|pm2\|git\|tools [--version V] --server NAME` | install software on a server (Node.js 22 / 20 / 18, Java 21 / 17, Go 1.x.y, ...) |
| `console KEY [COMMAND] [--shell]` | the service's client (redis-cli, psql, mongosh, rpk, bao, ...) here, or one command and its output |
| `shell SERVER [COMMAND]` | ssh to a saved server with its login, or run one command there |
| `terminal [KEY] [--server NAME] [--shell] [--list] [--stop NAME\|all]` | a full terminal in the browser (ttyd in Docker, 127.0.0.1 + secret URL) |
| `ssh-key user@host[:port] [--key FILE]` | log in with the password once and install `~/.ssh/pskit_ed25519` on the server (works on Windows), then use it as `--pem` |
| `tunnel KEY [--local-port N] [--remote-port N]` | forward the service's port to `127.0.0.1` over SSH (firewalled ports) and print the variables to use |
| `usage KEY [--reveal]` | connect from any program: address, credentials, Python / Node.js client code, terminal tools, security |
| `list`, `status KEY [--reveal]`, `logs KEY` | what exists, its state / health / credentials, the container log |
| `backup KEY [-o FILE]` | dump the data to `.pskit/backups/` |
| `remove KEY [--delete-data] [--save]` | delete the container (and volume), and with `--save` the resource and its triggers |

`send` works for managed resources once deployed and for external ones right away (they already exist). It uses the
same senders and credentials as [`pskit trigger`](#pskit-trigger): AWS, GCP, Azure and on premises; elsewhere `--list`
prints the cloud CLI command and console steps.

Deleting a deployed resource runs `terraform destroy -target=...`. If it is still in `pskit.yml`, the next deploy
creates it again, so remove it from `resources:` (or the trigger) first. Kept resources are deleted from their own small
workspace in `.pskit/<provider>-<stage>/kept/`, which is removed when the last one is gone. Credentials are the same as for
`pskit deploy`.

## `pskit info`

Show the deployed functions, triggers, URLs and resource ids.

| Flag | |
|---|---|
| `--json` | machine-readable record |
| `--refresh` | re-read `terraform output` instead of the saved record |

Before anything is deployed, `info` shows the configured functions with status `not deployed`.

## `pskit dashboard`

Generate the HTML dashboard from every `.pskit/*/deployment.json`. It doesn't take the common project options.

| Flag | Default | |
|---|---|---|
| `-d, --dir` | `.` | project root |
| `-o, --output FILE` | `.pskit/dashboard/index.html` | where to write the HTML |
| `--serve` | | serve the live dashboard (page + JSON API: host health, logs, workflow executions) |
| `--host` | `127.0.0.1` | bind address for `--serve`. A non-loopback address prints a warning |
| `--port` | `8765` | port for `--serve` |
| `--open` | | open in the browser |

See [dashboard.md](dashboard.md).

## `pskit studio`

Open the local web UI for editing the project in forms instead of YAML (functions, triggers, workflows, resources,
on-prem drivers, provider options, code) and running validate / deploy / invoke. It doesn't take the common project options.

| Flag | Default | |
|---|---|---|
| `-d, --dir` | `.` | project folder (an empty folder starts the new-project wizard) |
| `--host` | `127.0.0.1` | bind address. A non-loopback address prints a warning |
| `--port` | `8770` | port |
| `--open` | | open in the browser |
| `--vscode-image IMAGE` | `codercom/code-server:4.96.4` | image for Full VS Code (also `PSKIT_STUDIO_VSCODE_IMAGE`) |
| `--ailogs[=true]` | off | print every step of Hana's chats in this terminal: messages, model requests and answers, tool calls and results, cards (also `PSKIT_HANA_AILOGS=1`; see [assistant.md](assistant.md)) |

It prints `http://127.0.0.1:8770/#token=...`. The token is required on every API call, so open that exact URL.
See [studio.md](studio.md).

## `pskit doctor`

Check that this machine can deploy to a provider, and print how to fix what's missing on the current OS: Terraform /
OpenTofu, Python, the cloud's CLI, credentials, required provider options and optional SDKs. For `onprem` it checks
what the deploy method needs: nothing for `local`; `ssh` / `scp`, the host and the private key for `ssh`; the Docker
CLI and a running daemon for `docker`. Nothing is sent anywhere and no command prompts; each tool probe has a short
timeout. It doesn't take the common project options.

| Flag | Default | |
|---|---|---|
| `-p, --provider NAME` | `provider.name` in pskit.yml | provider to check. Required without a pskit.yml |
| `-c, --config FILE` | `pskit.yml` | config to read provider options from |
| `--json` | | the full report (ids, statuses, links, steps for every OS) |

```bash
pskit doctor
pskit doctor -p azure
pskit doctor -p onprem --json
```

```text
pskit doctor: aws
 ✓ Python: Python 3.12.10
 ✓ Terraform (or OpenTofu): Terraform v1.9.8
 ! AWS CLI: aws not found on PATH; used to sign in and inspect resources
     Install AWS CLI, then open a new terminal.
       winget install Amazon.AWSCLI
       Install the AWS CLI: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html
 ✗ AWS credentials: no AWS credentials in the environment or ~/.aws
     Add an access key profile here, run `aws configure`, or `aws sso login` for SSO profiles.
       $ aws configure
```

`✓` ok, `✗` missing (exit code 1), `!` recommended, `i` optional. A missing cloud CLI is only a warning: Terraform
needs credentials, not the CLI. The same checks appear in `pskit studio` (Setup), where you can also add an AWS
profile, run `az login` / `gcloud auth application-default login`, and test an SSH connection.

## `pskit dev`

Local HTTP server that routes requests to your handlers, with hot reload.

| Flag | Default |
|---|---|
| `--host` | `127.0.0.1` |
| `--port` | `3000` |
| `--env-file` | `.env` |

See [local-development.md](local-development.md).

## `pskit invoke`

Invoke one function locally with a synthetic event.

| Flag | |
|---|---|
| `-f, --function` | **required**, function name |
| `-t, --type` | `http`, `schedule`, `queue`, `storage`, `topic`, `invoke`, `workflow` (default: the function's first event type, or `invoke`) |
| `-d, --data` | JSON payload, `@file.json`, or plain text |
| `--method` | HTTP method (default: the route's method or GET) |
| `--path` | HTTP path incl. query string (default: the route's path) |
| `-H, --header` | `"Name: value"`, repeatable |
| `--env-file` | default `.env` |

```bash
pskit invoke -f hello --path "/hello?name=Ada"
pskit invoke -f create-item -d '{"name": "lamp"}'                  # POST route, JSON body
pskit invoke -f worker -t queue -d '[{"id": 1}, {"id": 2}]'        # two records
pskit invoke -f on-upload -t storage -d '{"bucket": "b", "key": "in/a.csv"}'
pskit invoke -f nightly                                            # schedule: uses the configured input
```

Output is the JSON result. For HTTP it's `{"status", "headers", "body"}`; a `BatchResult` prints as `batchItemFailures`. If the handler raises, the traceback is printed and the exit code is 1.

## `pskit workflow`

```bash
pskit workflow run NAME [-i JSON|@file] [--sleep] [--history]
pskit workflow show NAME [--format auto|asl|gcp|json]
```

- `run` executes the workflow locally on the embedded engine. `wait` states are skipped unless `--sleep` is given. A failed run prints `FAILED <error>: <cause>` and exits with code 2.
- `show` prints the compiled definition. `auto` picks ASL for AWS, Cloud Workflows for GCP, and the portable JSON otherwise.

Deployed workflows (on-premises host, AWS Step Functions, Google Cloud Workflows; AWS/GCP need `pip install "py-serverless-kit[aws]"` / `[gcp]`). These read `.pskit/<provider>-<stage>/deployment.json`, so deploy first:

```bash
pskit workflow start NAME [-i JSON|@file] [--wait] [--json]
pskit workflow executions [NAME] [--status S] [-n LIMIT] [--offset N] [--token T] [--json]
pskit workflow status EXECUTION_ID [-w NAME] [--history] [--watch] [--json]
pskit workflow cancel EXECUTION_ID [-w NAME]
```

| Command | Flags |
|---|---|
| `start` | `-i, --input` JSON or `@file.json`. `--wait`: wait for the result (on-premises; native engines return at once; an embedded cloud orchestrator is always synchronous). Prints `execution_id`, status and a console link |
| `executions` | newest first. `--status` is `RUNNING`, `SUCCEEDED`, `FAILED`, `TIMED_OUT`, `CANCELLED` or `ABORTED`. `-n, --limit` (default 20). `--offset` pages on premises; `--token` (printed after a page) pages AWS/GCP |
| `status` | `-w, --workflow` helps AWS/GCP resolve the id. `--history` prints every state event. `--watch` polls every 2 s until the run finishes |
| `cancel` | stops the run before its next state (embedded) or calls `StopExecution` / `cancel` (AWS / GCP) |

See [workflow-executions.md](workflow-executions.md).

## `pskit logs`

Show, list or delete the logs of a deployment. On premises: the host's buffer (handler logging, `print` output, one entry per invocation, host notes). AWS: CloudWatch Logs. GCP: Cloud Logging (read only). Azure: Log Analytics when the deployment has a `log_analytics_workspace_id` output (read only). Elsewhere, use the console link from `pskit info`. Requirements per provider: [dashboard.md](dashboard.md#log-sources).

| Flag | Default | |
|---|---|---|
| `-f, --follow` | | keep printing new entries (polls every second) |
| `-n, --lines` | `100` | how many recent entries to show first |
| `--function NAME` | | only this function |
| `--level LEVEL` | | minimum level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `--source` | | `function`, `host`, `stdout`, `stderr` or `invocation` |
| `-q, --grep TEXT` | | only entries containing this text (case-insensitive) |
| `--json` | | one JSON object per line |
| `--streams` | | list log streams (CloudWatch streams, or one per function on premises) with their ids |
| `--delete STREAM` | | delete a stream by id (repeatable). On premises the id is a function name, or `__host__` for host notes |
| `--delete-all` | | delete every stream, or only those of `--function` |
| `-y, --yes` | | don't ask before deleting |

```bash
pskit logs -f
pskit logs --function worker --level warning -n 500
pskit logs --stage prod --source invocation --json | jq .fields.duration_ms
pskit logs --provider aws --streams
pskit logs --provider aws --function worker --delete-all --yes
```

On AWS, `--level` and `--source` are applied to parsed lines and `-q` becomes a CloudWatch filter pattern. `-f` polls every 3 seconds on clouds.

The admin token comes from the generated `pskit_host.json`. See [providers.md](providers.md#logs-and-stats).

## `pskit providers`

Print the capability matrix of the installed providers (`--json` for details: regions, runtimes, max timeout, Terraform provider, notes).

## `pskit tf -- ARGS…`

Run any Terraform command in the generated workspace (after `package` or `deploy`):

```bash
pskit tf -- state list
pskit tf --stage prod -- output -json
pskit tf -- import aws_s3_bucket.b_uploads my-existing-bucket
```

## Environment variables

| Variable | Used by |
|---|---|
| `PSKIT_TERRAFORM_BIN` | path or name of `terraform` / `tofu` |
| `PSKIT_LOG_FORMAT`, `PSKIT_LOG_LEVEL`, `LOG_LEVEL` | runtime logging (CLI defaults to `text`) |
| `PSKIT_DEBUG` | include exception details in local/remote 500s |
| `PSKIT_SETTINGS_PASSPHRASE` | `pskit settings export` / `import` without a prompt |
