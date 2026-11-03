# Studio: build a project without writing YAML

`pskit studio` opens a local web app for creating and editing a pskit project in forms: functions and triggers,
workflows, resources, on-premises drivers, provider settings and handler code. You can deploy from it too. Everything
it produces is an ordinary `pskit.yml` plus Python files, so the CLI, CI and code review work exactly as before.

```bash
pip install py-serverless-kit
cd my-service            # an existing project, or an empty folder
pskit studio --open
```

```text
pskit studio for /home/me/my-service
Open http://127.0.0.1:8770/#token=q3V...  (Ctrl+C to stop)
```

| Option | Default | Meaning |
|---|---|---|
| `-d, --dir DIR` | `.` | Project folder (the one holding `pskit.yml`, or an empty folder for a new project) |
| `--host` | `127.0.0.1` | Bind address. Anything other than loopback prints a warning: studio can edit files and deploy |
| `--port` | `8770` | Port |
| `--open` | off | Open the browser |
| `--vscode-image` | `codercom/code-server:4.96.4` | Image for **Full VS Code** (also `PSKIT_STUDIO_VSCODE_IMAGE`) |

## What you can do

| Page | What it does |
|---|---|
| **New project** | Appears when the folder has no `pskit.yml`: service name, one of the 11 providers, starter template |
| **Overview & provider** | Pick the provider from cards that show what each supports (HTTP, schedule, queue, storage, topic, native workflows). Switching first lists the triggers that would stop working. Region, runtime, memory, timeout, architecture, environment, tags and the provider's own options (project, subscription, compartment, account id, ...). On premises adds the deploy method (local / ssh / docker), host, port, admin token, services and host tuning |
| **Functions** | A table of functions and a four-step **Create function** wizard like the AWS Lambda console: basics, triggers, environment & permissions, review (a YAML diff). Trigger types the selected provider can't run are disabled, with a tooltip naming the providers that can. HTTP has a path-parameter preview, CORS and auth. Schedule has rate presets and a cron editor with a plain-English preview. Queue/storage/topic can be **new**, a **resource** from the Resources page, **Browse account** (lists what already exists in your cloud), or a typed name. Creating a function writes a handler stub into your code |
| **Workflows** | A visual step-function builder: an auto-laid-out diagram (next, choice, default and catch edges) with a palette for task, choice, wait, pass, parallel, map, succeed and fail. The inspector edits each state: task function (or create a new one), choice rules with and/or/not groups, retry and catch, wait seconds or path, pass result, fail error. Parallel branches and map iterators open as nested workflows. Engine (auto / native / embedded) and timeout |
| **Resources** | Managed or external buckets, queues, topics, databases, caches and custom services. Connection values (secrets as `${env:VAR}`), which functions get the binding, **Browse account**. For on premises there's a driver picker grouped by cloud: SQS / S3, Azure Queue / Blob, Pub/Sub / GCS, MNS / OSS, Cloudflare Queues / R2, COS, OBS, Oracle, IBM COS, Spaces, MinIO, Redis, directory and **custom class**. Each driver shows its own fields, and secret fields can be read from an environment variable (`<key>_env`) |
| **Scaling cluster** | On premises: run the functions on Docker Swarm, Kubernetes (k3s) or Nomad over a master plus joined servers. Create a cluster on a saved server, **+ Join server** at any time (a new server can be saved in the same dialog), live CPU / memory / disk bars per server with the limits, replicas running / desired and replicas that cannot be placed, **Scale**, drain / remove a server, and the alert when every server is full (a function of the project and / or a webhook, test button, recent alerts). The *Deploy this project's functions to …* switch writes `provider.options.cluster`. See [cluster.md](cluster.md) |
| **Code** | A file tree and a VS Code-style editor (CodeMirror: Python, YAML, JSON highlighting, search, tabs, Ctrl+S), or **Full VS Code**: see below |
| **Deploy** | Validate, package, plan, deploy, info and remove, with a live log. Remove, and any stage named `prod*`, need a typed confirmation. Also **Invoke** a function with a JSON payload, and run a workflow locally |
| **YAML** | The generated `pskit.yml`, a diff against the file on disk, and a raw-YAML editing mode |

Every edit goes into an in-memory draft and is validated as you type (the same checks as `pskit validate`, for the
provider and stage you pick in the top bar). Problems link to the field they concern. **Save** (Ctrl/Cmd+S) writes
`pskit.yml`; undo/redo work across pages. Nothing touches disk until you save, and closing the tab with unsaved changes
asks first.

## Setup, logs and provider differences

- **Setup & credentials** runs the same checks as `pskit doctor` for the provider in the top bar: Terraform, the cloud's CLI, credentials, required provider options and, for on premises, ssh/scp/Docker and the key file. Each problem shows the download link and the steps for Windows, macOS or Linux. You can also:
  - save an AWS access key as a profile in `~/.aws`;
  - set provider variables such as `ARM_SUBSCRIPTION_ID` or `CLOUDFLARE_API_TOKEN` for this studio session only (secret values are never sent back to the browser);
  - start a browser login (`az login`, `gcloud auth application-default login`, `aws sso login`);
  - test the SSH connection of an on-prem deploy.
- **Logs** shows the logs of the deployed provider/stage (on-prem, AWS, GCP and Azure with a Log Analytics workspace). You can list the stored log streams and delete the ones you select, or all of them (AWS and on-prem). Each function's **Logging** section sets its log level and can show its live logs.
- **Private key**: the SSH key field has **Browse…**, which lists folders on the machine running studio (it starts in `~/.ssh`). Only names and sizes are listed; file contents are never read.
- **Provider differences**: trigger types the provider can't run aren't offered. Options it rejects (for example `auth: jwt` on Azure) or ignores (a timezone on Azure timers) are listed on each trigger, worked out from the provider's own validation.
- **Enable / disable**: functions and workflows can be disabled everywhere (`enabled: false`) or only on the current provider (`providers.<cloud>...enabled: false`). A single trigger can be disabled on one provider too. The Deploy page and the provider switch list everything that won't run on the target and offer to disable it there.

## Test functions

The **Test** page (or **Test** on a function row) sends events to a function:

1. Pick the function and the event: one of its triggers (HTTP, schedule, queue, storage, topic) or **Direct invoke**.
2. Edit the payload. It starts from a sample for that trigger type (a storage sample matches the trigger's prefix and
   suffix; a schedule uses its own `input`). **Save event** keeps named payloads per function in
   `.pskit/studio/test-events.json`, like test events in the Lambda console.
3. **Run locally** runs the handler on this machine with a synthetic event (`pskit invoke`): no cloud, no deploy.
   **Send to <provider>/<stage>** fires the real trigger of the deployed function (`pskit trigger`): a queue message,
   an uploaded object, a topic message, an HTTP request or an invocation. Turn on *Show the function's logs* to watch it.

**How to test this** shows the same for each trigger three ways: the studio steps, the terminal commands (local
`pskit invoke`, deployed `pskit trigger`, and the cloud's own CLI such as `aws sqs send-message` or
`gcloud pubsub topics publish`) with Copy buttons, and the click-by-click steps in the cloud console. See
[`pskit trigger`](cli.md#pskit-trigger) for which events pskit can send on each provider.

## Project environment, trigger resources and remove

- **Setup & credentials → Project environment** creates `.venv` with the Python you pick (every interpreter found on
  this machine is listed, including the Windows `py` launcher's) and installs `requirements.txt` into it, or recreates
  it from scratch. Node.js services get **npm install** (`npm ci` when there is a lockfile). The output streams in the
  page.
- **Triggers → Create new → Create & select** adds the queue, bucket or topic to Resources (managed) and selects it in
  the trigger, so other functions can bind it too. **Pick from <cloud>** can add an existing one as an external resource
  in the same way.
- **Deploy → Remove** has a switch, *Remove also deletes buckets, queues and topics*. Turned off, remove runs
  `pskit remove --keep-resources`: functions and triggers are destroyed and the data resources stay in the cloud.
- **Resources → Test a resource** (or **Test** on a resource row) sends a message to a queue, uploads an object to a
  bucket or publishes to a topic, for managed resources (after deploy) and external ones (right away), with the same
  How-to-test tabs as the Test page. For database, cache and custom resources it shows the `PSKIT_RESOURCE_*`
  variables the bound functions get and a Python / Node.js snippet that reads them.
- **Resources → On-prem services → + Create service** starts Redis / Valkey (queue, stream or cache), Kafka
  (Redpanda), NATS JetStream, RabbitMQ, an SQS-compatible queue, MinIO, PostgreSQL, MySQL, MariaDB, MongoDB, Memcached or
  Mailpit with Docker, on this machine or any SSH server, or installs Python / Docker on a server. When it is ready the
  resource, `provider.options.env_file` and triggers on the functions you ticked are added to the draft. Each service
  has **Details** (state, health, credentials, container log), **Backup** and **Remove**. See
  [resource-guides/onprem/services.md](resource-guides/onprem/services.md).
- **Resources → How to use**, section 7 *Call it from code* (on-prem target): complete Python and Node.js programs
  for that resource with the pskit client (add data, page through it, consume with ack / nack, upload / download /
  list files, publish), the same over HTTP, the service's own library, and what to do if it times out, with a live
  check that this machine reaches the host ([client.md](client.md)). *On-prem services → Details* warns when a
  service's port is unreachable from here.
- **On-prem services**: the create form has a *Security* box (user, password with *Generate*, listen on 127.0.0.1 or
  the network); each service has **How to use** (connect from any program: Python / Node.js clients, terminal,
  security). **Resources → Data** pages through what an on-prem queue, topic or bucket holds, with previews.
- **Resources → How to use** on every resource opens its end-to-end guide: the library to install for Python and
  Node.js and how pskit packages it, the `pskit.yml` and trigger, handler code with copy buttons, local tests
  (`pskit invoke`, `pskit dev`), deployed tests and provider notes ([resource-usage.md](resource-usage.md)).
- **Resources → Test a resource** shows *Use it in a handler* (Python / Node.js code and the library to add) and
  **Test connection** for every resource. **Delete** on a resource asks whether to keep or delete its data (one-click
  services: stop or delete the container; built-in on-prem resources: clear them on the host).
- **On-prem services**: one-click Dragonfly, KeyDB, Apache Kafka, LavinMQ, Azurite, LocalStack, fake-gcs-server and
  RustFS next to the earlier services; *Also start the web UI* in the create form and *Details > Add / Remove web UI*
  (Adminer, Redis Commander, Kafka UI, Mongo Express). Every guide has a **Web UI** section with the URL, login and
  tunnel command. The create form's **Web UI login** chooses *With password* (generated or yours) or *Without
  password*; **Details > Check web UI** finds out why a UI does not open (container, port, server, this machine,
  Azure NSG / AWS security group / GCP firewall, ufw) and prints the fix. *SSH server* targets log in with a key
  file, the SSH agent / default key, or a password (sshpass; on Windows install a key once with
  `pskit resources onprem ssh-key user@host`).
- **On-prem services → Browse / Browse secrets**: pskit's own UI where a service has none (or a limited one):
  buckets and objects for MinIO, RustFS, LocalStack, LocalEmu and fake-gcs-server (upload, download, folders,
  paging, versions, share links, policies); secrets for OpenBao and the AWS emulators (folders, versions,
  add / edit / delete). See [one-click services](resource-guides/onprem/services.md#pskits-own-browsers-when-the-native-ui-is-missing).
- **E-mail (SMTP)**: **Resources → + SMTP server** (or *On-prem services → Mail*) starts a Node.js SMTP server
  for your domains on a server and ticks the functions to run. Its **DNS guide** lists the A and MX records to add at
  the domain provider. The *E-mail (SMTP)* trigger picks the server. See [E-mail triggers](smtp/README.md).
- **Resources → + On-prem service** creates a one-click service and adds it straight to the resource list (with
  triggers); **Add resource** has *Create a <type> on premises*. Services not yet in `pskit.yml` appear above the list
  with an **Add** button, and rows backed by one are marked `on-prem <service> · <server>`.
- **On-prem services → Servers**: save several SSH machines (key file, agent or password), test them (OS, CPU,
  memory, disk, Docker, sudo), open a **Shell** or a full browser **Terminal**, and *Install / create* Node.js (22 /
  20 / 18), nginx, Java, Go, Caddy, Certbot, PM2, Git and tools. The create form's **Server** list and **Deploy →
  Machine** pick one. Every service has a **Console** (redis-cli, psql, mongosh, rpk, bao, ... or a shell in its
  container) and a **Terminal**. **Secret managers**: one-click OpenBao (Vault API), pskit's AWS Secrets Manager compatible server (Python or
  Node.js, with its own console) and LocalStack Secrets Manager,
  read from handlers with `get_secret()` ([guide](resource-guides/onprem/secrets.md)). **Object storage**: also
  pskit's Amazon S3 compatible server (Python or Node.js, with its own S3 console at `/ui/`)
  ([guide](resource-guides/onprem/storage.md)).
- **Resources → Guides → General → Existing cloud code**: what works when you bring Lambda ARNs, boto3 Lambda / SQS
  code or S3 / Azure / GCS SDK code, on every provider ([compatibility](resource-guides/compatibility.md)). On-prem
  queue guides show the boto3 SQS code against the host.
- **Resources → Guides** (and the *How to set up* links in the resource form) shows the step-by-step
  [resource guides](resource-guides/README.md) for every cloud inside the studio.
- **Resources → In the cloud** lists the buckets, queues and topics pskit created for the provider and stage in the top
  bar, deployed or kept. Select some (or **Delete all kept**) and delete them with their data (`pskit resources delete`,
  behind a typed confirmation). Deleting a managed resource from the Resources table only removes it from `pskit.yml`;
  the next deploy then deletes it in the cloud.

## Saving: what changes in pskit.yml

- Values keep their written form: `${env:API_KEY}`, `${self:custom.x}` and `${opt:...}` are saved as written, never resolved.
- Comments are **not** kept, and key order follows the studio's layout. Before every save the previous file is copied
  to `.pskit/studio/backups/pskit.<timestamp>.yml` (the last 20 are kept).
- If `pskit.yml` changed on disk since you loaded it (an editor, `git pull`), Save offers to reload, overwrite or cancel.
- A file that uses `extends:` is shown with a notice: only the main file is edited.
- A config that fails validation can still be saved, so you can stop half-way. The problems stay listed.

## Browse account

**Browse account** lists queues, buckets, topics and state machines that already exist, so you pick one instead of
typing its name. It runs with the credentials of the machine running studio:

| Provider | Lists | Needs |
|---|---|---|
| AWS | SQS queues, S3 buckets, SNS topics, Step Functions state machines | `pip install "py-serverless-kit[aws]"`, AWS credentials |
| GCP | Pub/Sub topics and subscriptions, Cloud Storage buckets | `google-cloud-pubsub` / `google-cloud-storage`, `provider.options.project` or `GOOGLE_CLOUD_PROJECT` |
| Azure | Storage queues and blob containers | `azure-storage-queue` / `azure-storage-blob`, `AZURE_STORAGE_CONNECTION_STRING` |
| On premises | Existing queue and bucket directories under the host's data directory | nothing |
| Others | Not available | type the name |

A missing SDK or credential shows a message in the picker; you can always type the name instead.

## Full VS Code (code-server in Docker)

**Code → Full VS Code** runs [code-server](https://github.com/coder/code-server) on your project and embeds it:

1. Studio checks for the Docker CLI and a running daemon. If either is missing, it shows how to install Docker.
2. **Pull & start** pulls the image if it isn't present (the log streams in the panel), then starts
   `pskit-studio-<id>` with your project mounted at `/home/coder/project`, published on `127.0.0.1` only, and waits
   until it answers.
3. The editor opens inside the studio, with **Open in new tab** and **Stop**. A container that's already running is
   reused. Stop removes it; your files stay in the project folder.

**Runtimes**: pick a **Python** (3.9 to 3.13) and/or **Node.js** (18, 20, 22, 24) version next to the image. The first
start with a combination builds `pskit-code-server:<tag>-py<X>-node<Y>` on top of the code-server image: CPython from
`uv python install`, Node.js from the official nodejs.org Linux build (its SHA-256 is checked), and the Python
extension. Later starts reuse it. The Dockerfile is kept in `.pskit/studio/vscode/`. Changing the selection while
VS Code runs offers **Restart with these runtimes**: the container is replaced, and your files stay where they are.
The default is the project's own runtime.

It runs with `--auth none` because it is reachable only from this machine. On Linux and macOS it runs as your user, so
new files aren't owned by root.

**Studio itself inside a container** (Docker-in-Docker / sibling containers): mount the Docker socket and tell studio
where the project lives on the host, because the code-server container is started by the host's daemon:

```bash
docker run --rm -p 127.0.0.1:8770:8770 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$PWD":/work -w /work \
  -e PSKIT_STUDIO_HOST_ROOT="$PWD" \
  python:3.12-slim sh -c "pip install py-serverless-kit && apt-get update && apt-get install -y docker.io && pskit studio --host 0.0.0.0"
```

## Hana, the AI assistant

Hana's avatar at the bottom right (Ctrl+I) opens a chat with Hana, studio's assistant. She answers pskit questions and can
change the project after you approve her plan, checking every change with `validate`. The model runs on this
machine or a saved server in Docker (studio installs it), or at any OpenAI-compatible URL. See
[assistant.md](assistant.md).

## Security

Studio can write files in the project and run deploys with your cloud credentials, so:

- It binds to `127.0.0.1` by default.
- Every API call needs the session token from the printed URL. Anyone who has that URL has full access, so don't share
  it. A new token is generated each time studio starts.
- Requests with a foreign `Host` header (DNS rebinding) or a cross-site `Origin` are refused, and bodies are capped at 2 MiB.
- The file editor only reaches files inside the project. It never touches `.pskit/`, `.git/`, `.venv/`,
  `node_modules/` or `__pycache__`, and refuses binary files or files over 1 MiB.
- Deploy commands run as `python -m py_serverless_kit ...` with explicit arguments, never through a shell.

## Developing the studio UI

The UI lives in `dashboard-ui/` next to the dashboard (they share components). `npm run build` writes both
`src/py_serverless_kit/dashboard/template.html` and `src/py_serverless_kit/studio/studio.html`; CI fails if either is
out of date. `npm run dev:studio` serves the UI with hot reload against a running `pskit studio --port 8770`, or against
a built-in mock API with `VITE_MOCK=1`. See [`deploy_docs/CONTRIBUTING.md`](../deploy_docs/CONTRIBUTING.md).
