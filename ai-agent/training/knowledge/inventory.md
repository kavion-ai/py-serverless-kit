# Knowledge inventory

Coverage checklist for Hana stage 1. Version **2.10.0** (`src/py_serverless_kit/_version.py`).
Command options are copied from `ai-agent/training/knowledge/cli.json` (Click walk of `py_serverless_kit.cli.main.cli`).
Doc headings are copied from `docs_headings.json` (GitHub slug anchors).
Do not treat this file as a second source of truth: cards re-read the cited files.

Conflicts: `ai-agent/training/knowledge/conflicts.md`.

## 1a. Commands

Click nodes: 103 (13 groups including the root, 90 leaf commands).
Source: `src/py_serverless_kit/cli/main.py`. Full help text is the `help_output` field in `cli.json`.

### Groups

- `pskit` — py-serverless-kit: write Python functions once, deploy them to any cloud.
- `pskit client` — Call the on-prem host from scripts.
- `pskit cluster` — Scale on-prem functions over several servers (Swarm, Kubernetes, Nomad).
- `pskit cluster balancer` — A load balancer in front of the cluster: one more saved server (outside the cluster) running OpenResty.
- `pskit function` — Give a function its own folder, code and requirements.txt.
- `pskit lb` — Shared on-prem load balancers: one URL, a path per project or cluster.
- `pskit lb routes` — Routes on a load balancer (pskit lb status lists them).
- `pskit resources` — List or delete the buckets, queues and topics pskit created.
- `pskit resources onprem` — Create services for on-premises functions with Docker, here or on an SSH server.
- `pskit resources onprem replicas` — Read replicas of a replicated database: list, add, remove.
- `pskit resources onprem servers` — Saved SSH servers: name a machine once, then create services, install software, open shells and deploy to it.
- `pskit settings` — Export / import this project's .pskit settings and secrets (encrypted).
- `pskit workflow` — Run or inspect workflows (state machines).

### Leaf commands

#### `pskit client info`

Endpoint, token, reachability and code to call the host.

- Options: -c/--config (string), -p/--provider (string), -s/--stage (string), -r/--region (string), --server (string), --cluster (string), -v/--verbose (flag), --json (flag)

#### `pskit client install-node`

Put the pskit Node.js package (with PskitClient) in node_modules.

- Options: --dir (string default='.')

#### `pskit client tunnel`

Forward the host's port here over SSH (firewalled host port).

- Options: -c/--config (string), -p/--provider (string), -s/--stage (string), -r/--region (string), --server (string), --cluster (string), -v/--verbose (flag), --local-port (int)

#### `pskit cluster alerts`

Who hears about a full cluster, and when a server counts as full.

- Arguments: name (string, required)
- Options: --function (string), --stage (string), --webhook (string), --cooldown (int), --cpu (int), --memory (int), --disk (int), --test (flag), -c/--config (string)

#### `pskit cluster balancer logs`

The load balancer's recent requests (upstream= is the server that answered) and errors.

- Arguments: name (string, required)
- Options: -n/--lines (int_range default=100), -c/--config (string)

#### `pskit cluster balancer remove`

Stop the load balancer of cluster NAME (the functions keep running on the cluster).

- Arguments: name (string, required)
- Options: --yes (flag), -c/--config (string)

#### `pskit cluster balancer set`

Make saved SERVER the load balancer of cluster NAME (installs Docker and OpenResty there).

- Arguments: name (string, required), server (string, required)
- Options: --port (int_range default=80), --address (string), --algorithm (string), --weight (string), -c/--config (string)

#### `pskit cluster balancer sync`

Rewrite the load balancer's config from the cluster's servers and deployments.

- Arguments: name (string, required)
- Options: -c/--config (string)

#### `pskit cluster check`

Status once; when full, call the alert function / webhook (respecting the cooldown).

- Arguments: name (string, required)
- Options: --alert/--no-alert (flag), -c/--config (string)

#### `pskit cluster create`

Install the orchestrator on MASTER and save cluster NAME.

- Arguments: name (string, required)
- Options: --orchestrator/-o (choice:swarm|kubernetes|nomad), --master (string), --advertise (string), --nomad-version (string), --master-serves/--no-master-serves (flag), -c/--config (string)

#### `pskit cluster join`

Add saved SERVER to cluster NAME (installs the agent and copies the deployed images).

- Arguments: name (string, required), server (string, required)
- Options: --advertise (string), -c/--config (string)

#### `pskit cluster leave`

Drain SERVER (replicas move to the others) and remove it from cluster NAME.

- Arguments: name (string, required), server (string, required)
- Options: --yes (flag), -c/--config (string)

#### `pskit cluster list`

Clusters, their servers and deployments.

- Options: --json (flag), -c/--config (string)

#### `pskit cluster remove`

Forget cluster NAME (the servers and anything running on them are left as they are).

- Arguments: name (string, required)
- Options: --uninstall (flag), --delete-data (flag), --yes (flag), -c/--config (string)

#### `pskit cluster requests`

Recent requests of one deployment, and how HTTP is spread across each server (live with --follow).

- Arguments: name (string, required)
- Options: --stack (string), -f/--follow (flag), -n/--lines (int_range default=50), -c/--config (string)

#### `pskit cluster scale`

Set the web replicas now (until the next deploy; keep it in options.cluster.replicas).

- Arguments: name (string, required)
- Options: --replicas (int_range), --stack (string), -s/--stage (string), -c/--config (string)

#### `pskit cluster set`

Change how cluster NAME spreads requests.

- Arguments: name (string, required)
- Options: --master-serves/--no-master-serves (flag), -c/--config (string)

#### `pskit cluster status`

Every server's CPU, memory and disk, the replicas, and whether the cluster is full.

- Arguments: name (string, required)
- Options: --json (flag), -c/--config (string)

#### `pskit cluster watch`

Check every INTERVAL seconds until Ctrl+C (run it on an always-on machine, e.g.

- Arguments: name (string, required)
- Options: --interval (int_range default=60), -c/--config (string)

#### `pskit dashboard`

Generate (and optionally serve) the deployment dashboard.

- Options: -d/--dir (path default='.'), -o/--output (path), --serve (flag), --host (string default='127.0.0.1'), --port (int default=8765), --open (flag)

#### `pskit deploy`

Package and deploy with terraform apply.

- Options: -c/--config (string), -p/--provider (string), -s/--stage (string), -r/--region (string), --server (string), --cluster (string), -v/--verbose (flag), --skip-deps (flag), --confirm (flag), --upgrade (flag), --no-dashboard (flag)

#### `pskit dev`

Run a local server with hot reload.

- Options: -c/--config (string), -p/--provider (string), -s/--stage (string), -r/--region (string), --server (string), --cluster (string), -v/--verbose (flag), --host (string default='127.0.0.1'), --port (int default=3000), --env-file (string default='.env')

#### `pskit doctor`

Check terraform, the cloud CLI and credentials.

- Options: -p/--provider (string), -c/--config (string), --json (flag)

#### `pskit firewall`

Ports each on-prem server must open (inbound / outbound), with server names.

- Options: --server (string), --json (flag), -c/--config (string)

#### `pskit function split`

Move functions out of a shared code file into functions/<name>/handler.py with their own requirements.txt.

- Arguments: names (string, optional)
- Options: --all (flag), --dry-run (flag), -c/--config (string)

#### `pskit info`

Show what is deployed (functions, URLs, ids).

- Options: -c/--config (string), -p/--provider (string), -s/--stage (string), -r/--region (string), --server (string), --cluster (string), -v/--verbose (flag), --json (flag), --refresh (flag)

#### `pskit init`

Scaffold a new project (pskit.yml, handlers, tests).

- Arguments: directory (path, optional)
- Options: --name (string), -p/--provider (choice:aws|azure|gcp|alibaba|oracle|ibm|digitalocean|tencent|huawei|cloudflare|onprem default='aws'), -t/--template (choice:http|events|workflow|full default='http'), -l/--language (choice:python|javascript|typescript), --runtime (choice:python3.9|python3.10|python3.11|python3.12|python3.13|python3.14|nodejs18|nodejs20|nodejs22|nodejs24), --typescript/--ts (flag), --force (flag)

#### `pskit invoke`

Invoke a function locally with a synthetic event.

- Options: -c/--config (string), -p/--provider (string), -s/--stage (string), -r/--region (string), --server (string), --cluster (string), -v/--verbose (flag), -f/--function (string), -t/--type (choice:http|schedule|queue|storage|topic|invoke|workflow|smtp), -d/--data (string), --method (string), --path (string), -H/--header (string), --env-file (string default='.env')

#### `pskit lb algorithms`

The load balancing algorithms: how each picks a server, static or dynamic, pros, cons, when to use it.

- Options: --json (flag)

#### `pskit lb attach`

Serve every deployment of a cluster on load balancer NAME (http://<lb>/<service>/), now and on deploys.

- Arguments: name (string, required)
- Options: --cluster (string), -c/--config (string)

#### `pskit lb create`

Make saved SERVER load balancer NAME (Docker and OpenResty there), or add the one already running there.

- Arguments: name (string, required)
- Options: --server (string), --port (int_range), --address (string), --algorithm (string), --weight (string), -c/--config (string)

#### `pskit lb detach`

Stop serving a cluster's deployments on load balancer NAME.

- Arguments: name (string, required)
- Options: --cluster (string), -c/--config (string)

#### `pskit lb forget`

Forget load balancer NAME in this project only (it keeps running for other projects).

- Arguments: name (string, required)
- Options: -c/--config (string)

#### `pskit lb list`

Load balancers this project uses.

- Options: --json (flag), -c/--config (string)

#### `pskit lb logs`

Recent requests (upstream= is the server that answered) and errors.

- Arguments: name (string, required)
- Options: -n/--lines (int_range default=100), -c/--config (string)

#### `pskit lb remove`

Stop load balancer NAME on its server and forget it.

- Arguments: name (string, required)
- Options: --force (flag), --yes (flag), -c/--config (string)

#### `pskit lb routes remove`

Remove the route at PATH (xyz, or port-8081) from load balancer NAME, whichever project owns it.

- Arguments: name (string, required), path (string, required)
- Options: --yes (flag), -c/--config (string)

#### `pskit lb status`

Whether it runs, its server's use, and every route on it (from every project).

- Arguments: name (string, required)
- Options: --json (flag), -c/--config (string)

#### `pskit lb sync`

Rewrite the load balancer from this project's settings: every route, and attached clusters.

- Arguments: name (string, required)
- Options: -c/--config (string)

#### `pskit lb update`

Change the port, default algorithm, weights or address (routes on the default algorithm switch too).

- Arguments: name (string, required)
- Options: --port (int_range), --address (string), --algorithm (string), --weight (string), -c/--config (string)

#### `pskit logs`

Show, list or delete logs of a deployment.

- Options: -c/--config (string), -p/--provider (string), -s/--stage (string), -r/--region (string), --server (string), --cluster (string), -v/--verbose (flag), -f/--follow (flag), -n/--lines (int default=100), --function (string), --level (string), --source (choice:function|host|stdout|stderr|invocation), -q/--grep (string), --json (flag), --streams (flag), --delete (string), --delete-all (flag), -y/--yes (flag)

#### `pskit package`

Build the artifact and Terraform (no cloud calls).

- Options: -c/--config (string), -p/--provider (string), -s/--stage (string), -r/--region (string), --server (string), --cluster (string), -v/--verbose (flag), --skip-deps (flag)

#### `pskit plan`

Show the terraform plan (what would change).

- Options: -c/--config (string), -p/--provider (string), -s/--stage (string), -r/--region (string), --server (string), --cluster (string), -v/--verbose (flag), --skip-deps (flag), --destroy (flag)

#### `pskit providers`

List supported clouds and what each supports.

- Options: --json (flag)

#### `pskit remove`

Destroy every resource of this service/stage.

- Options: -c/--config (string), -p/--provider (string), -s/--stage (string), -r/--region (string), --server (string), --cluster (string), -v/--verbose (flag), -y/--yes (flag), --keep-resources (flag)

#### `pskit resources check`

Check that a resource is reachable (connection, depth).

- Arguments: key (string, required)
- Options: -c/--config (string), -p/--provider (string), -s/--stage (string), -r/--region (string), --server (string), --cluster (string), -v/--verbose (flag), --json (flag)

#### `pskit resources clear`

Delete the data of a built-in on-prem queue, bucket or topic.

- Arguments: key (string, required)
- Options: -c/--config (string), -p/--provider (string), -s/--stage (string), -r/--region (string), --server (string), --cluster (string), -v/--verbose (flag), -y/--yes (flag)

#### `pskit resources data`

Browse what an on-prem queue, topic or bucket holds (paginated).

- Arguments: key (string, required)
- Options: -c/--config (string), -p/--provider (string), -s/--stage (string), -r/--region (string), --server (string), --cluster (string), -v/--verbose (flag), --offset (int), -n/--limit (int default=20), --prefix (string), --json (flag)

#### `pskit resources delete`

Delete buckets, queues or topics by address.

- Arguments: addresses (string, optional)
- Options: -c/--config (string), -p/--provider (string), -s/--stage (string), -r/--region (string), --server (string), --cluster (string), -v/--verbose (flag), --all-kept (flag), -y/--yes (flag)

#### `pskit resources list`

Deployed and kept buckets, queues and topics.

- Options: -c/--config (string), -p/--provider (string), -s/--stage (string), -r/--region (string), --server (string), --cluster (string), -v/--verbose (flag), --json (flag)

#### `pskit resources onprem alerts`

Alerts of a service: show, set, test or check now.

- Arguments: key (string, required)
- Options: --on/--off (flag), --webhook (string), --function (string), --stage (string), --cpu (int), --memory (int), --disk (int), --lag (int), --cooldown (int), --test (flag), --check (flag), -c/--config (string)

#### `pskit resources onprem backup`

Dump a service's data to .pskit/backups.

- Arguments: key (string, required)
- Options: -o/--output (string), -d/--dir (path), -c/--config (string)

#### `pskit resources onprem catalog`

Services and runtimes that can be created.

- Options: --json (flag)

#### `pskit resources onprem console`

Run commands in a service (redis-cli, psql, mongosh, rpk, ...).

- Arguments: key (string, required), command (string, optional)
- Options: --shell (flag), -c/--config (string)

#### `pskit resources onprem create`

Start a service (or install a runtime) and add it as a resource.

- Arguments: key (string, required)
- Options: --service (string), --role (string), --port (int), --image (string), --address (string), --bind (string), --ssh (string), --pem (string), --ssh-password-file (string), --ssh-password-env (string), --sudo (flag), --local (flag), --server (string), --cluster (string), --node (string), --version (string), --user (string), --password (string), --password-env (string), -a/--attach (string), --domains (string), --functions-url (string), --max-size-mb (float), --gui (flag), --gui-login (choice:password|none), --gui-password-env (string), --replica (string), --primary (string), --balancer (string), --balancer-port (int), --sync (choice:async|sync), --import (path), --alert-webhook (string), --alert-function (string), --save (flag), -c/--config (string), --json (flag)

#### `pskit resources onprem gui`

Start (or --remove) the web UI of a service.

- Arguments: key (string, required)
- Options: --port (int), --login (choice:password|none default='password'), --password-env (string), --check (flag), --remove (flag), -c/--config (string)

#### `pskit resources onprem list`

Services created from this project.

- Options: -c/--config (string), --json (flag)

#### `pskit resources onprem logs`

The service container's recent output.

- Arguments: key (string, required)
- Options: -n/--tail (int default=200), -c/--config (string)

#### `pskit resources onprem monitor`

Live CPU, memory, disk, connections and replica lag of a service.

- Arguments: key (string, required)
- Options: --watch (int), --json (flag), -c/--config (string)

#### `pskit resources onprem remove`

Stop and delete a service container.

- Arguments: key (string, required)
- Options: --delete-data (flag), --save (flag), -y/--yes (flag), -c/--config (string)

#### `pskit resources onprem replicas add`

Start one more read replica on a saved server.

- Arguments: key (string, required), server (string, optional)
- Options: -c/--config (string)

#### `pskit resources onprem replicas list`

Members, their state and replication lag.

- Arguments: key (string, required)
- Options: -c/--config (string)

#### `pskit resources onprem replicas remove`

Stop one read replica (by name r2, or its server).

- Arguments: key (string, required), name (string, required)
- Options: --delete-data (flag), -c/--config (string)

#### `pskit resources onprem servers add`

Save (or replace) server NAME.

- Arguments: name (string, required)
- Options: --ssh (string), --pem (string), --ssh-password-env (string), --ssh-password-file (string), --sudo (flag), --description (string), --home (string), --bind (string), --data-dir (string), --test/--no-test (flag), -c/--config (string)

#### `pskit resources onprem servers check`

Which saved servers answer on their SSH port (no login).

- Options: -c/--config (string)

#### `pskit resources onprem servers list`

(no short help)

- Options: --json (flag), -c/--config (string)

#### `pskit resources onprem servers remove`

Forget server NAME (services already created there keep running).

- Arguments: name (string, required)
- Options: -c/--config (string)

#### `pskit resources onprem servers test`

Log in and show the OS, CPU, memory, disk, Docker access, sudo and installed runtimes.

- Arguments: name (string, required)
- Options: -c/--config (string)

#### `pskit resources onprem servers top`

Live CPU, memory and disk use of a saved server.

- Arguments: name (string, required)
- Options: --watch (int), -c/--config (string)

#### `pskit resources onprem servers usage`

Where each saved server is used (functions, clusters, ...).

- Arguments: name (string, optional)
- Options: --json (flag), -c/--config (string)

#### `pskit resources onprem shell`

A shell on a saved SSH server (or run one command there).

- Arguments: server (string, required), command (string, optional)
- Options: -c/--config (string)

#### `pskit resources onprem ssh-key`

Install an SSH key on a server that takes a password (once).

- Arguments: destination (string, required)
- Options: --key (string), --password-env (string)

#### `pskit resources onprem status`

State, health and connection details of a service.

- Arguments: key (string, required)
- Options: --reveal (flag), -c/--config (string)

#### `pskit resources onprem terminal`

A full terminal in the browser (Docker): a server or a service.

- Arguments: key (string, optional)
- Options: --server (string), --shell (flag), --list (flag), --stop (string), --open/--no-open (flag), -c/--config (string)

#### `pskit resources onprem tunnel`

Reach a service on a server through SSH (firewalled port).

- Arguments: key (string, required)
- Options: --local-port (int), --remote-port (int), -c/--config (string)

#### `pskit resources onprem usage`

Connect to a service from any program: code, terminal, security.

- Arguments: key (string, required)
- Options: --reveal (flag), -c/--config (string)

#### `pskit resources send`

Send a test message / object to a queue, bucket or topic.

- Arguments: key (string, optional)
- Options: -c/--config (string), -p/--provider (string), -s/--stage (string), -r/--region (string), --server (string), --cluster (string), -v/--verbose (flag), -d/--data (string), --list (flag), --json (flag)

#### `pskit resources usage`

End-to-end guide: libraries, pskit.yml, code, tests for a resource.

- Arguments: key (string, required)
- Options: -c/--config (string), -p/--provider (string), -s/--stage (string), -r/--region (string), --server (string), --cluster (string), -v/--verbose (flag)

#### `pskit settings export`

Write every local setting and secret of this project to one encrypted file.

- Options: -o/--output (string), --with-config (flag), -c/--config (string)

#### `pskit settings import`

Write the settings of an exported FILE into this project (the current ones are backed up first).

- Arguments: file (path, required)
- Options: --replace (flag), --dry-run (flag), --yes (flag), -c/--config (string)

#### `pskit studio`

Edit the project in the browser (writes pskit.yml).

- Options: -d/--dir (path default='.'), --host (string default='127.0.0.1'), --port (int default=8770), --open (flag), --vscode-image (string)

#### `pskit tf`

Run any terraform command in the generated workspace.

- Arguments: args (unprocessed, optional)
- Options: -c/--config (string), -p/--provider (string), -s/--stage (string), -r/--region (string), --server (string), --cluster (string), -v/--verbose (flag)

#### `pskit trigger`

Send a real test event to a deployed function.

- Options: -c/--config (string), -p/--provider (string), -s/--stage (string), -r/--region (string), --server (string), --cluster (string), -v/--verbose (flag), -f/--function (string), -e/--event (int), --direct (flag), -d/--data (string), --path (string), --list (flag), --json (flag)

#### `pskit validate`

Validate the config against the selected provider.

- Options: -c/--config (string), -p/--provider (string), -s/--stage (string), -r/--region (string), --server (string), --cluster (string), -v/--verbose (flag)

#### `pskit workflow cancel`

Cancel a running execution (stops before its next state).

- Arguments: execution_id (string, required)
- Options: -c/--config (string), -p/--provider (string), -s/--stage (string), -r/--region (string), --server (string), --cluster (string), -v/--verbose (flag), -w/--workflow (string)

#### `pskit workflow executions`

List executions of the deployed workflows (newest first).

- Arguments: name (string, optional)
- Options: -c/--config (string), -p/--provider (string), -s/--stage (string), -r/--region (string), --server (string), --cluster (string), -v/--verbose (flag), --status (string), -n/--limit (int default=20), --offset (int), --token (string), --json (flag)

#### `pskit workflow run`

Run a workflow locally on the embedded engine.

- Arguments: name (string, required)
- Options: -c/--config (string), -p/--provider (string), -s/--stage (string), -r/--region (string), --server (string), --cluster (string), -v/--verbose (flag), -i/--input (string), --sleep (flag), --history (flag)

#### `pskit workflow show`

Print the compiled workflow definition.

- Arguments: name (string, required)
- Options: -c/--config (string), -p/--provider (string), -s/--stage (string), -r/--region (string), --server (string), --cluster (string), -v/--verbose (flag), --format (choice:auto|asl|gcp|json default='auto')

#### `pskit workflow start`

Start a deployed workflow and print its execution id.

- Arguments: name (string, required)
- Options: -c/--config (string), -p/--provider (string), -s/--stage (string), -r/--region (string), --server (string), --cluster (string), -v/--verbose (flag), -i/--input (string), --wait (flag), --json (flag)

#### `pskit workflow status`

Show one execution: status, current state, output or error.

- Arguments: execution_id (string, required)
- Options: -c/--config (string), -p/--provider (string), -s/--stage (string), -r/--region (string), --server (string), --cluster (string), -v/--verbose (flag), -w/--workflow (string), --history (flag), --watch (flag), --json (flag)

## 1b. Studio pages

Left navigation order from `NAV` in `dashboard-ui/src/studio/App.tsx`:

1. Overview & provider
2. Setup & credentials
3. Functions
4. Workflows
5. Resources
6. Scaling cluster
7. Load balancers
8. Network map
9. Code
10. Test
11. Deploy
12. Logs
13. YAML

New project replaces the shell when `project.exists` is false (`App.tsx`). It is not in `NAV`.

### Top bar (`App.tsx`)

- Brand (service name) links to Overview & provider. Subtitle: pskit studio.
- Label `validate & deploy as`: provider `<select>` (aria-label Target provider). Options are `meta.providers` display names.
- Label `stage`: text input (aria-label Stage), lowercased to `[a-z0-9-]`, max 16 characters.
- Undo (Ctrl+Z), Redo (Ctrl+Shift+Z). Ctrl+Y also redo. Ignored while focus is in an editor.
- Problems button (error and warning counts) opens the Problems panel. Close problems.
- Validate (title Validate now) calls `validateNow`.
- Save / Saved / Saving… (title Save pskit.yml (Ctrl+S)). Ctrl/Cmd+S saves except on the Code page.
- ⇅ Settings opens drawer `Import / export settings and config` (`SettingsTransfer` in Setup.tsx).
- Theme toggle (aria-label Toggle theme), stored as `pskit-theme` in localStorage.
- Menu (burger) opens the nav on small widths.
- Conflict modal `pskit.yml changed on disk`: Cancel, Reload (discard my changes), Overwrite.
- Token screen (HTTP 401): `This studio session needs its link`, shows `pskit studio --open`.
- Nav footer shows project notices and `pskit {meta.version}`.
- Docs: `docs/studio.md` (Save, undo, validation, backups).

### New project

- Nav label: none (replaces the shell when the folder has no pskit.yml)
- How to open: Open studio in a folder with no pskit.yml. Not a left-nav item.
- File: `dashboard-ui/src/studio/views/NewProject.tsx`
- Purpose: Scaffold a project. Docs: docs/studio.md#what-you-can-do.
- Sections and controls:
  - Service name (2–32 lowercase letters, digits, dashes, starting with a letter)
  - Provider (provider cards)
  - Language: Python, JavaScript, TypeScript (JS/TS disabled when the provider has no Node runtimes)
  - Template: HTTP API, Events, Workflow, Everything
  - Button: Create project (Creating… while busy). Overwrite confirm if files exist.

### Overview & provider

- Nav label: Overview & provider
- How to open: Left navigation. The brand in the top bar also links here.
- File: `dashboard-ui/src/studio/views/Overview.tsx`
- Purpose: Service-wide settings every function inherits unless it overrides them. docs/studio.md.
- Sections and controls:
  - Service: Service name; Use the values shown here (absorb provider overrides into the base)
  - Provider: cards; switching lists triggers that would stop working (docs/studio.md)
  - Defaults for every function: Region, Stage (shown; the live stage is the top-bar stage), Runtime, Memory (MB), Timeout (s), Architecture, Log retention (days)
  - Environment variables (available to every function)
  - Tags / Add tag
  - <provider> options (provider.options)
  - Packaging (package)
  - On-premises deployment (provider.options.deploy): Saved server, Deploy method (local / ssh / docker; scp is ssh per docs/providers.md), + Add server, Test SSH connection
  - Built-in services (provider.options.services)
  - Host tuning (logs, executions, concurrency)

### Setup & credentials

- Nav label: Setup & credentials
- How to open: Left navigation.
- File: `dashboard-ui/src/studio/views/Setup.tsx`
- Purpose: Same checks as pskit doctor for the top-bar provider. docs/studio.md#setup-logs-and-provider-differences.
- Sections and controls:
  - Provider, Operating system, Check again
  - Checks: each row has Details or How to fix, Copy, and a Run action (download / login)
  - Move settings to another machine: Export settings, passphrase + Again, Include pskit.yml, Preview, Import into this project. Matches pskit settings export / import. Also opened from top bar ⇅ Settings (drawer title Import / export settings and config).
  - AWS credentials (aws configure): Profile, Access key ID, Secret access key, Default region, Session token, Save profile
  - Environment variables: Set for this session, Clear (not written back to the browser once set; docs/studio.md)
  - On-premises connection (provider.options.deploy), Deploy method
  - Project environment: Create .venv and install / Install requirements, Recreate, npm install

### Functions

- Nav label: Functions
- How to open: Left navigation. Count badge is the number of functions.
- File: `dashboard-ui/src/studio/views/Functions.tsx`
- Purpose: Table of functions plus the Create function wizard. docs/studio.md.
- Sections and controls:
  - Search name, handler, trigger…
  - + Create function; Create your first function; Give each function its own folder (pskit function split)
  - Row: Test, Code, Own folder, Duplicate, Delete
  - Wizard steps: Basics, Triggers, Environment & permissions, Review
  - Basics: Function name, Deploy (enable), Description, Handler, Dependencies, Runs on, Runtime, Memory (MB), Timeout (s), Architecture
  - Add a trigger; per-trigger skip on this provider
  - Logging: Log level, Live logs
  - Environment variables; Concurrency & tags; Provider-specific options
  - Permissions (IAM): Existing role, Effect Allow/Deny, Actions, Resources, + Add statement, Remove
  - Review: Changes to pskit.yml; Create function / Apply changes; Back / Next; Cancel; Open code

### Workflows

- Nav label: Workflows
- How to open: Left navigation.
- File: `dashboard-ui/src/studio/views/Workflows.tsx`
- Purpose: Visual step-function builder. docs/studio.md; docs/workflows.md.
- Sections and controls:
  - List: New workflow (Name, Create, Cancel), Delete
  - Palette states: task, choice, wait, pass, parallel, map, succeed, fail (docs/studio.md)
  - Settings: Description, Engine, Timeout (s)
  - Diagram and inspector: State name, Rename, Comment, Function, Result, Error, Cause
  - Choice: Rules, conditions, Otherwise
  - Retry and catch editors (attempts, interval, backoff, max delay, go to)
  - Parallel branches and map iterator open as nested workflows

### Resources

- Nav label: Resources
- How to open: Left navigation. On-prem services, servers, guides and testers are components opened from this page.
- File: `dashboard-ui/src/studio/views/Resources.tsx`
- Purpose: Managed or external resources, plus on-prem services. docs/studio.md, docs/resources.md.
- Sections and controls:
  - Buttons: Guides, + SMTP server (onprem only), + On-prem service, + Add resource
  - Table columns: Key, Type, Mode, Native name. Row: How to use, DNS guide (smtp), Data, Test, Delete
  - Undeclared on-prem services: + <key> (service) calls Add
  - Resource drawer: Type, external, Native name, Browse account…, Connection, Bound functions, On-premises driver, Provider-specific options, Create a <type> on premises
  - How to use drawer: Copy guide, Test it (docs/resource-usage.md)
  - In the cloud panel (CloudResources.tsx): Load / Refresh, Delete, Delete selected, Delete all kept
  - On-prem services (OnPremServices.tsx): Guide, + Create service, Details, How to use, Browse, Console, Terminal, Add to pskit.yml, Backup, Remove, Generate, Check/Add/Remove web UI
  - Servers (OnPremMachines.tsx): + Add server, Test, live use, Shell, Terminal, Install / create, Edit, Forget, Save and test
  - Replication (Replication.tsx): + Add read replica, Remove
  - Monitoring (Monitoring.tsx): Save / Turn alerts on, Turn off, Send a test alert, Check now
  - Data browser, service browser (buckets and secrets), resource tester: Test connection

### Scaling cluster

- Nav label: Scaling cluster
- How to open: Left navigation. Warns to switch the provider to onprem.
- File: `dashboard-ui/src/studio/views/Cluster.tsx`
- Purpose: Docker Swarm, k3s or Nomad. docs/cluster.md, docs/studio.md.
- Sections and controls:
  - + New cluster (drawer title New scaling cluster): orchestrator, master, Create / Installing…
  - Tabs when more than one cluster (name · orchestrator)
  - Refresh, Check & alert, Forget
  - Servers table: Server, State, CPU, Memory, Disk; + Join server; Remove; uninstall
  - Load balancer block: + Set up load balancer, Sync now, Show log, Change, Remove
  - Shared load balancers: + Attach a load balancer, Detach
  - Use for this project writes provider.options.cluster (docs/studio.md)
  - Web replicas, CPU per replica, Memory per replica (MB), Port on the load balancer, Scale
  - Live requests (Live, Clear), Live logs
  - Resources on this cluster; Deployed functions
  - When every server is full: Alert function, Stage, Save, Send test alert
  - + Join a server now / + Add a server

### Load balancers

- Nav label: Load balancers
- How to open: Left navigation.
- File: `dashboard-ui/src/studio/views/LoadBalancers.tsx`
- Purpose: One URL, a path per project or cluster. docs/load-balancers.md.
- Sections and controls:
  - + Create load balancer (drawer New load balancer): Name, Server, Port, Address in the URL, How it spreads requests, Attach clusters now, Create
  - Refresh, Update, Sync, Logs, Remove, Forget
  - CPU, Memory, Disk
  - + Attach cluster, Detach
  - Routes table: Owner, Source, Backends; Remove route
  - Put this project on a balancer: Path, Algorithm for this route (provider.options.balancer)

### Network map

- Nav label: Network map
- How to open: Left navigation.
- File: `dashboard-ui/src/studio/views/Network.tsx`
- Purpose: On-prem servers and the connections they must accept or open. docs/onprem-network.md.
- Sections and controls:
  - Refresh
  - Machines list and map; All machines
  - Inbound — accept; Outbound — open
  - Used in
  - Empty: No servers and no connections yet. Save a server under Resources.

### Code

- Nav label: Code
- How to open: Left navigation, or Code on a function row.
- File: `dashboard-ui/src/studio/views/Code.tsx`
- Purpose: File tree and CodeMirror editor, or Full VS Code (code-server). docs/studio.md#full-vs-code-code-server-in-docker.
- Sections and controls:
  - Editor: Find file, New file (+), Create, Refresh, Save (Ctrl+S), close tab
  - Full VS Code: Python and Node.js runtime pickers, Pull & start / Start, Open in new tab, Restart with these runtimes, Stop, Check again

### Test

- Nav label: Test
- How to open: Left navigation, or Test on a function row.
- File: `dashboard-ui/src/studio/views/Test.tsx`
- Purpose: Local invoke and real trigger send. docs/studio.md#test-functions.
- Sections and controls:
  - 1. Choose the event (a trigger or Direct invoke)
  - 2. Edit the event: Request, Payload (JSON), Saved events, Save event
  - 3. Run it: Run locally (pskit invoke); Send to <provider> / <stage> (pskit trigger); Show the function's logs
  - How to test this: tabs studio, terminal, cloud console; Copy

### Deploy

- Nav label: Deploy
- How to open: Left navigation.
- File: `dashboard-ui/src/studio/views/Deploy.tsx`
- Purpose: Validate, package, plan, deploy, info, remove, with a live log. docs/studio.md.
- Sections and controls:
  - Action buttons come from the studio job catalog (labels rendered from each action). Remove can pass keep_resources. prod stages need a typed confirmation (docs/studio.md).
  - Where functions run (provider.options.placement): Run on, Cluster, Machine
  - Switch: Remove also deletes buckets, queues and topics (docs/studio.md) — off runs pskit remove --keep-resources
  - Compat panel: Disable trigger / function / workflow on <provider>, Disable all of them
  - Firewall section (ports each server must allow)
  - Output tabs: Steps, Raw log
  - Recent jobs: Clear finished
  - Invoke a function locally (pskit invoke): Function, Event type, Path, Payload, Invoke
  - Run a workflow locally (pskit workflow run --history): Workflow, Input, Run

### Logs

- Nav label: Logs
- How to open: Left navigation. Per-function Live logs also live on the function editor.
- File: `dashboard-ui/src/studio/views/Logs.tsx`
- Purpose: Logs of the deployed provider/stage. docs/studio.md. CLI: pskit logs.
- Sections and controls:
  - Source picker; cluster replica / server filters when on-prem
  - Stored logs: list, select and delete (AWS and on-prem per docs/studio.md)

### YAML

- Nav label: YAML
- How to open: Left navigation.
- File: `dashboard-ui/src/studio/views/Yaml.tsx`
- Purpose: The generated pskit.yml, a diff, and raw edit. docs/studio.md.
- Sections and controls:
  - YAML mode
  - Apply to draft (Parsing… while busy)
  - Comments are not preserved; backups in .pskit/studio/backups/

### Dialogs and panels to card separately

- Create function wizard: Functions > + Create function. `dashboard-ui/src/studio/views/Functions.tsx`
- Create service: Resources > + On-prem service or On-prem services > + Create service. `dashboard-ui/src/studio/components/OnPremServices.tsx`
- Create cluster: Scaling cluster > + New cluster. `dashboard-ui/src/studio/views/Cluster.tsx`
- Join server: Scaling cluster > + Join server. `dashboard-ui/src/studio/views/Cluster.tsx`
- Servers: Resources > On-prem services > Servers. `dashboard-ui/src/studio/components/OnPremMachines.tsx`
- Browse account: Resources resource form > Browse account…. `dashboard-ui/src/studio/views/TriggerForms.tsx`
- Full VS Code: Code > Full VS Code. `dashboard-ui/src/studio/views/Code.tsx`
- Test a resource: Resources > Test. `dashboard-ui/src/studio/components/ResourceTester.tsx`
- How to use: Resources > How to use. `dashboard-ui/src/studio/views/Resources.tsx`
- Import / export settings: Top bar > ⇅ Settings. `dashboard-ui/src/studio/views/Setup.tsx`
- New load balancer: Load balancers > + Create load balancer. `dashboard-ui/src/studio/views/LoadBalancers.tsx`
- SMTP DNS guide: Resources row > DNS guide. `dashboard-ui/src/studio/views/Resources.tsx`
- Session token screen: Shown on HTTP 401. `dashboard-ui/src/studio/App.tsx`

## 1c. Docs

Files under `docs/`: 107 (106 Markdown, 1 other). Headings: 814.
Anchors use the GitHub slugger rules in `ai-agent/training/tools/extract_docs.py`.

### `docs/architecture.md`

- Architecture (`#architecture`)
  - Deploy pipeline (`#deploy-pipeline`)
  - Bundle layout (`#bundle-layout`)
  - Runtime flow (`#runtime-flow`)
  - State handling (`#state-handling`)
  - Third-party providers (`#third-party-providers`)

### `docs/cli.md`

- CLI reference (`#cli-reference`)
  - Common project options (`#common-project-options`)
  - `pskit init [DIRECTORY]` (`#pskit-init-directory`)
  - `pskit validate` (`#pskit-validate`)
  - `pskit package` (`#pskit-package`)
  - `pskit plan` (`#pskit-plan`)
  - `pskit deploy` (`#pskit-deploy`)
  - `pskit remove` (`#pskit-remove`)
  - `pskit trigger` (`#pskit-trigger`)
  - `pskit resources` (`#pskit-resources`)
  - `pskit cluster` (`#pskit-cluster`)
  - `pskit settings` (`#pskit-settings`)
  - `pskit client` (`#pskit-client`)
    - `pskit resources onprem` (`#pskit-resources-onprem`)
  - `pskit info` (`#pskit-info`)
  - `pskit dashboard` (`#pskit-dashboard`)
  - `pskit studio` (`#pskit-studio`)
  - `pskit doctor` (`#pskit-doctor`)
  - `pskit dev` (`#pskit-dev`)
  - `pskit invoke` (`#pskit-invoke`)
  - `pskit workflow` (`#pskit-workflow`)
  - `pskit logs` (`#pskit-logs`)
  - `pskit providers` (`#pskit-providers`)
  - `pskit tf -- ARGS…` (`#pskit-tf----args`)
  - Environment variables (`#environment-variables`)

### `docs/client.md`

- Call an on-prem host from any program: pskit client and HTTP API (`#call-an-on-prem-host-from-any-program-pskit-client-and-http-api`)
  - Python (`#python`)
  - Node.js (18+) (`#nodejs-18`)
  - Consuming outside pskit (`#consuming-outside-pskit`)
  - HTTP API (`#http-api`)
  - AWS-compatible APIs (`#aws-compatible-apis`)
  - When connections time out (`#when-connections-time-out`)

### `docs/cluster.md`

- Scaling cluster (on premises) (`#scaling-cluster-on-premises`)
  - How the functions run in a cluster (`#how-the-functions-run-in-a-cluster`)
    - Nomad does not need a load balancer (`#nomad-does-not-need-a-load-balancer`)
  - Set up (`#set-up`)
    - One server or the cluster, per deploy (`#one-server-or-the-cluster-per-deploy`)
  - Per-server settings: home path, bind address, data directory (`#per-server-settings-home-path-bind-address-data-directory`)
  - Resources on a cluster (`#resources-on-a-cluster`)
    - Ports to open (`#ports-to-open`)
  - Load balancer: one URL for the whole cluster (optional) (`#load-balancer-one-url-for-the-whole-cluster-optional`)
    - The master and requests (`#the-master-and-requests`)
  - Live requests: which server handled what (`#live-requests-which-server-handled-what`)
  - Live logs (`#live-logs`)
  - Monitor, scale and add servers when it is full (`#monitor-scale-and-add-servers-when-it-is-full`)
    - Alert DevOps (optional) (`#alert-devops-optional`)
  - Where things are kept (`#where-things-are-kept`)
  - Commands (`#commands`)
  - Limits and notes (`#limits-and-notes`)

### `docs/configuration.md`

- Configuration reference (`pskit.yml`) (`#configuration-reference-pskityml`)
  - Top level (`#top-level`)
  - `provider` (`#provider`)
    - Default runtime (`#default-runtime`)
    - State: remote Terraform backend (`#state-remote-terraform-backend`)
    - `terraform` (`#terraform`)
  - `functions` (`#functions`)
  - `resources` (`#resources`)
  - `package` (`#package`)
  - `hooks` (`#hooks`)
  - Overrides and layering (`#overrides-and-layering`)
    - `providers:`: per-cloud overrides (`#providers-per-cloud-overrides`)
      - Switch something off on one cloud (`#switch-something-off-on-one-cloud`)
    - `stages:`: per-stage overrides (`#stages-per-stage-overrides`)
    - `extends:`: inherit files (`#extends-inherit-files`)
    - Precedence (later wins) (`#precedence-later-wins`)
  - Variables (`#variables`)
  - Escape hatches (`#escape-hatches`)

### `docs/dashboard.md`

- Dashboard (`#dashboard`)
  - What it shows (`#what-it-shows`)
  - Live mode (`#live-mode`)
    - Log sources (`#log-sources`)
    - Security (`#security`)
  - Where the data comes from (`#where-the-data-comes-from`)
  - Changing the UI (`#changing-the-ui`)

### `docs/events.md`

- Events (triggers) (`#events-triggers`)
  - `http` (`#http`)
  - `schedule` (`#schedule`)
  - `queue` (`#queue`)
  - `storage` (`#storage`)
  - `topic` (`#topic`)
  - Events backed by a resource (`#events-backed-by-a-resource`)
  - Provider-specific behaviour worth knowing (`#provider-specific-behaviour-worth-knowing`)
    - GCP: multi-trigger functions are split automatically (`#gcp-multi-trigger-functions-are-split-automatically`)
    - Azure: one Function App per service (`#azure-one-function-app-per-service`)
    - Schedule + invoke envelope (`#schedule-invoke-envelope`)

### `docs/getting-started.md`

- Getting started (`#getting-started`)
  - 1. Install (`#1-install`)
  - 2. Scaffold a project (`#2-scaffold-a-project`)
  - 3. Write a handler (`#3-write-a-handler`)
  - 4. Run locally (`#4-run-locally`)
  - 5. Validate (`#5-validate`)
  - 6. Configure cloud credentials (`#6-configure-cloud-credentials`)
  - 7. Deploy (`#7-deploy`)
  - 8. Switch cloud (`#8-switch-cloud`)
  - 9. Remove (`#9-remove`)
  - Next (`#next`)

### `docs/handlers.md`

- Handler API (`#handler-api`)
  - Handler signatures (`#handler-signatures`)
  - `Event` (`#event`)
  - `HttpRequest` (`#httprequest`)
  - `Record` (`#record`)
  - `Context` (`#context`)
  - Returning a response (`#returning-a-response`)
  - Errors (`#errors`)
  - `BatchResult` (`#batchresult`)
  - `invoke()`: calling another function (`#invoke-calling-another-function`)
  - `get_secret()`: secrets on every provider (`#get_secret-secrets-on-every-provider`)
  - Environment variables (`#environment-variables`)
  - Logging (`#logging`)

### `docs/load-balancers.md`

- Load balancers (on premises) (`#load-balancers-on-premises`)
  - The six algorithms (`#the-six-algorithms`)
  - Create one and put projects on it (`#create-one-and-put-projects-on-it`)
  - Shared between projects and machines (`#shared-between-projects-and-machines`)
  - Commands (`#commands`)
  - Notes (`#notes`)

### `docs/local-development.md`

- Local development (`#local-development`)
  - `pskit dev`: local server (`#pskit-dev-local-server`)
  - `pskit invoke` and `pskit workflow run` (`#pskit-invoke-and-pskit-workflow-run`)
  - Environment (`#environment`)
  - Testing with pytest (`#testing-with-pytest`)
  - On-premises is a deploy, not `pskit dev` (`#on-premises-is-a-deploy-not-pskit-dev`)

### `docs/migrating-from-aws.md`

- Migrating from AWS Lambda and Step Functions (`#migrating-from-aws-lambda-and-step-functions`)
  - Step 1: separate business logic from AWS event parsing (`#step-1-separate-business-logic-from-aws-event-parsing`)
  - Step 2: translate the SAM / Serverless / CDK definition (`#step-2-translate-the-sam-serverless-cdk-definition`)
  - Step 3: translate Step Functions (`#step-3-translate-step-functions`)
  - Step 4: deploy to AWS side by side (`#step-4-deploy-to-aws-side-by-side`)
  - Step 5: move to another cloud (`#step-5-move-to-another-cloud`)

### `docs/nodejs.md`

- Node.js and TypeScript (`#nodejs-and-typescript`)
  - Choosing the runtime (`#choosing-the-runtime`)
  - Handlers (`#handlers`)
    - Secrets (`#secrets`)
  - TypeScript (`#typescript`)
  - Calling an on-prem host from other Node.js programs (`#calling-an-on-prem-host-from-other-nodejs-programs`)
  - Dependencies and packaging (`#dependencies-and-packaging`)
  - Local development (`#local-development`)
  - Limitations (`#limitations`)

### `docs/onprem-network.md`

- Network and firewall rules (on premises) (`#network-and-firewall-rules-on-premises`)
  - The machines (`#the-machines`)
  - 1. Always: the admin machine reaches every server over SSH (`#1-always-the-admin-machine-reaches-every-server-over-ssh`)
  - 2. Saving a server (`pskit resources onprem servers add`, studio "Add server") (`#2-saving-a-server-pskit-resources-onprem-servers-add-studio-add-server`)
  - 3. Deploy to one server (`method: ssh`, `docker`, or `--server NAME`) (`#3-deploy-to-one-server-method-ssh-docker-or---server-name`)
  - 4. Functions on several servers (`provider.options.placement`) (`#4-functions-on-several-servers-provideroptionsplacement`)
  - 5. Scaling cluster: create (`pskit cluster create prod --master edge1`) (`#5-scaling-cluster-create-pskit-cluster-create-prod---master-edge1`)
  - 6. Scaling cluster: join a server (`pskit cluster join prod edge2`) and run (`#6-scaling-cluster-join-a-server-pskit-cluster-join-prod-edge2-and-run`)
  - 7. Load balancer (`pskit lb create`, `pskit lb attach`, `pskit cluster balancer set`) (`#7-load-balancer-pskit-lb-create-pskit-lb-attach-pskit-cluster-balancer-set`)
  - 8. Resources and triggers ("attaching events") (`#8-resources-and-triggers-attaching-events`)
  - 9. The studio and browser terminals (`#9-the-studio-and-browser-terminals`)
  - Example: one load balancer, two placement groups (`#example-one-load-balancer-two-placement-groups`)
  - Example: Docker Swarm cluster (edge1 master, edge2, edge3) behind lb1 (`#example-docker-swarm-cluster-edge1-master-edge2-edge3-behind-lb1`)

### `docs/placement.md`

- Functions on several servers (on premises) (`#functions-on-several-servers-on-premises`)
  - Each function is its own sub-project (`#each-function-is-its-own-sub-project`)
    - Requirements: global plus per function (`#requirements-global-plus-per-function`)
    - Functions that share a code file (`#functions-that-share-a-code-file`)
  - How the groups work together (`#how-the-groups-work-together`)
  - Deploy, URLs and load balancers (`#deploy-urls-and-load-balancers`)

### `docs/providers.md`

- Providers (`#providers`)
  - aws (AWS Lambda) (`#aws-aws-lambda`)
  - gcp (Google Cloud Functions, 2nd gen) (`#gcp-google-cloud-functions-2nd-gen`)
  - azure (Azure Functions) (`#azure-azure-functions`)
  - alibaba (Function Compute 3.0) (`#alibaba-function-compute-30`)
  - tencent (Serverless Cloud Function, SCF) (`#tencent-serverless-cloud-function-scf`)
  - huawei (FunctionGraph) (`#huawei-functiongraph`)
  - ibm (Code Engine functions) (`#ibm-code-engine-functions`)
  - digitalocean (Functions) (`#digitalocean-functions`)
  - oracle (OCI Functions) (`#oracle-oci-functions`)
  - cloudflare (Workers) (`#cloudflare-workers`)
  - onprem (On-premises) (`#onprem-on-premises`)
    - Logs and stats (`#logs-and-stats`)
  - Writing your own provider (`#writing-your-own-provider`)

### `docs/README.md`

- py-serverless-kit documentation (`#py-serverless-kit-documentation`)

### `docs/resource-guides/alibaba/cache.md`

- Alibaba Cloud Tair / Redis (`type: cache`) (`#alibaba-cloud-tair-redis-type-cache`)
  - 1. Create the instance (console) (`#1-create-the-instance-console`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/alibaba/custom.md`

- Other Alibaba Cloud services (`type: custom`) (`#other-alibaba-cloud-services-type-custom`)
  - Tablestore (`#tablestore`)
  - KMS secrets (Secrets Manager) (`#kms-secrets-secrets-manager`)
  - A third-party API (`#a-third-party-api`)
  - Test (`#test`)

### `docs/resource-guides/alibaba/database.md`

- Alibaba Cloud databases (`type: database`) (`#alibaba-cloud-databases-type-database`)
  - 1. Create the instance (console) (`#1-create-the-instance-console`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/alibaba/queue.md`

- Alibaba Cloud SMQ / MNS queue (`type: queue`) (`#alibaba-cloud-smq-mns-queue-type-queue`)
  - 1. Create the queue (console) (`#1-create-the-queue-console`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/alibaba/README.md`

- Alibaba Cloud resources (`#alibaba-cloud-resources`)
  - Values you need for every Alibaba Cloud resource (`#values-you-need-for-every-alibaba-cloud-resource`)
  - How pskit runs on Alibaba Cloud (why some steps matter) (`#how-pskit-runs-on-alibaba-cloud-why-some-steps-matter`)
  - Secrets (`#secrets`)
  - Credentials for deploying (`#credentials-for-deploying`)

### `docs/resource-guides/alibaba/storage.md`

- Alibaba Cloud OSS bucket (`type: storage`) (`#alibaba-cloud-oss-bucket-type-storage`)
  - 1. Create the bucket (console) (`#1-create-the-bucket-console`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/alibaba/topic.md`

- Alibaba Cloud SMQ / MNS topic (`type: topic`) (`#alibaba-cloud-smq-mns-topic-type-topic`)
  - 1. Create the topic (console) (`#1-create-the-topic-console`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/aws/cache.md`

- Amazon ElastiCache / MemoryDB (`type: cache`) (`#amazon-elasticache-memorydb-type-cache`)
  - 1. Create the cache (console) (`#1-create-the-cache-console`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/aws/custom.md`

- Other AWS services (`type: custom`) (`#other-aws-services-type-custom`)
  - DynamoDB (`#dynamodb`)
  - Secrets Manager (`#secrets-manager`)
  - Anything else (`#anything-else`)
  - Test (`#test`)

### `docs/resource-guides/aws/database.md`

- Amazon RDS / Aurora (`type: database`) (`#amazon-rds-aurora-type-database`)
  - Networking first (`#networking-first`)
  - 1. Create the database (console) (`#1-create-the-database-console`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/aws/queue.md`

- Amazon SQS queue (`type: queue`) (`#amazon-sqs-queue-type-queue`)
  - 1. Create the queue (console) (`#1-create-the-queue-console`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/aws/README.md`

- AWS resources (`#aws-resources`)
  - Values you need for every AWS resource (`#values-you-need-for-every-aws-resource`)
  - How pskit runs on AWS (why some steps matter) (`#how-pskit-runs-on-aws-why-some-steps-matter`)
  - Credentials for deploying (`#credentials-for-deploying`)

### `docs/resource-guides/aws/storage.md`

- Amazon S3 bucket (`type: storage`) (`#amazon-s3-bucket-type-storage`)
  - 1. Create the bucket (console) (`#1-create-the-bucket-console`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/aws/topic.md`

- Amazon SNS topic (`type: topic`) (`#amazon-sns-topic-type-topic`)
  - 1. Create the topic (console) (`#1-create-the-topic-console`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/azure/cache.md`

- Azure Redis (`type: cache`) (`#azure-redis-type-cache`)
  - 1. Create the cache (portal) (`#1-create-the-cache-portal`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/azure/custom.md`

- Other Azure services (`type: custom`) (`#other-azure-services-type-custom`)
  - Cosmos DB (NoSQL) (`#cosmos-db-nosql`)
  - Key Vault (`#key-vault`)
  - Event Hubs (`#event-hubs`)
  - Test (`#test`)

### `docs/resource-guides/azure/database.md`

- Azure databases (`type: database`) (`#azure-databases-type-database`)
  - 1. Create the server (portal) (`#1-create-the-server-portal`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/azure/queue.md`

- Azure Storage queue (`type: queue`) (`#azure-storage-queue-type-queue`)
  - 1. Create the queue (portal) (`#1-create-the-queue-portal`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/azure/README.md`

- Azure resources (`#azure-resources`)
  - Values you need for every Azure resource (`#values-you-need-for-every-azure-resource`)
  - How pskit runs on Azure (why some steps matter) (`#how-pskit-runs-on-azure-why-some-steps-matter`)
  - Credentials for deploying (`#credentials-for-deploying`)

### `docs/resource-guides/azure/storage.md`

- Azure Blob container (`type: storage`) (`#azure-blob-container-type-storage`)
  - 1. Create the container (portal) (`#1-create-the-container-portal`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/azure/topic.md`

- Azure Service Bus topic (`type: topic`) (`#azure-service-bus-topic-type-topic`)
  - 1. Create the namespace and topic (portal) (`#1-create-the-namespace-and-topic-portal`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/cloudflare/cache.md`

- Workers KV (`type: cache`) (`#workers-kv-type-cache`)
  - 1. Create the namespace (dashboard) (`#1-create-the-namespace-dashboard`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/cloudflare/custom.md`

- Other Cloudflare services and APIs (`type: custom`) (`#other-cloudflare-services-and-apis-type-custom`)
  - Binding types (`#binding-types`)
  - Example: an external HTTP API with a secret (`#example-an-external-http-api-with-a-secret`)
  - Example: Workers AI (`#example-workers-ai`)
  - Test (`#test`)

### `docs/resource-guides/cloudflare/database.md`

- Cloudflare databases (`type: database`) (`#cloudflare-databases-type-database`)
  - D1 (`#d1`)
    - 1. Create the database (dashboard) (`#1-create-the-database-dashboard`)
    - 2. Collect the values (`#2-collect-the-values`)
    - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
    - 4. Use it in a handler (`#4-use-it-in-a-handler`)
    - 5. Test (`#5-test`)
  - PostgreSQL with Hyperdrive (Node.js) (`#postgresql-with-hyperdrive-nodejs`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/cloudflare/queue.md`

- Cloudflare Queues (`type: queue`) (`#cloudflare-queues-type-queue`)
  - 1. Create the queue (dashboard) (`#1-create-the-queue-dashboard`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/cloudflare/README.md`

- Cloudflare resources (`#cloudflare-resources`)
  - What pskit supports on Cloudflare (`#what-pskit-supports-on-cloudflare`)
  - Values you need for every Cloudflare resource (`#values-you-need-for-every-cloudflare-resource`)
  - Secrets (`#secrets`)
  - Testing (`#testing`)

### `docs/resource-guides/cloudflare/storage.md`

- Cloudflare R2 bucket (`type: storage`) (`#cloudflare-r2-bucket-type-storage`)
  - 1. Create the bucket (dashboard) (`#1-create-the-bucket-dashboard`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - Reacting to uploads (`#reacting-to-uploads`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/cloudflare/topic.md`

- Topics on Cloudflare (`type: topic`) (`#topics-on-cloudflare-type-topic`)
  - What to use instead (`#what-to-use-instead`)
  - Example: an external topic in another cloud (`#example-an-external-topic-in-another-cloud`)

### `docs/resource-guides/compatibility.md`

- Existing cloud code with pskit (`#existing-cloud-code-with-pskit`)
  - Calling functions (`#calling-functions`)
    - The pskit way (every provider) (`#the-pskit-way-every-provider`)
    - Existing boto3 / AWS SDK Lambda code, on premises (`#existing-boto3-aws-sdk-lambda-code-on-premises`)
  - Queues (`#queues`)
    - Existing SQS code, on premises (`#existing-sqs-code-on-premises`)
    - Other clouds' queue SDKs (`#other-clouds-queue-sdks`)
  - Buckets (`#buckets`)
  - Names, ARNs and URLs in handlers (`#names-arns-and-urls-in-handlers`)
  - Not compatible (and what to use) (`#not-compatible-and-what-to-use`)
  - Test it (`#test-it`)

### `docs/resource-guides/digitalocean/cache.md`

- DigitalOcean Managed Valkey (`type: cache`) (`#digitalocean-managed-valkey-type-cache`)
  - 1. Create the cluster (control panel) (`#1-create-the-cluster-control-panel`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/digitalocean/custom.md`

- Other DigitalOcean services (`type: custom`) (`#other-digitalocean-services-type-custom`)
  - Managed MongoDB (`#managed-mongodb`)
  - Managed OpenSearch (`#managed-opensearch`)
  - DigitalOcean API (`#digitalocean-api`)
  - Test (`#test`)

### `docs/resource-guides/digitalocean/database.md`

- DigitalOcean Managed databases (`type: database`) (`#digitalocean-managed-databases-type-database`)
  - 1. Create the cluster (control panel) (`#1-create-the-cluster-control-panel`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/digitalocean/queue.md`

- Queues on DigitalOcean (`type: queue`) (`#queues-on-digitalocean-type-queue`)
  - 1. Create the Valkey cluster (control panel) (`#1-create-the-valkey-cluster-control-panel`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/digitalocean/README.md`

- DigitalOcean resources (`#digitalocean-resources`)
  - What pskit supports on DigitalOcean (`#what-pskit-supports-on-digitalocean`)
  - Values you need for most DigitalOcean services (`#values-you-need-for-most-digitalocean-services`)
  - Secrets on DigitalOcean (`#secrets-on-digitalocean`)
  - Credentials for deploying (`#credentials-for-deploying`)

### `docs/resource-guides/digitalocean/storage.md`

- DigitalOcean Spaces bucket (`type: storage`) (`#digitalocean-spaces-bucket-type-storage`)
  - 1. Create the bucket (control panel) (`#1-create-the-bucket-control-panel`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/digitalocean/topic.md`

- DigitalOcean Managed Kafka topic (`type: topic`) (`#digitalocean-managed-kafka-topic-type-topic`)
  - 1. Create the cluster and topic (control panel) (`#1-create-the-cluster-and-topic-control-panel`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/gcp/cache.md`

- Memorystore for Redis / Valkey (`type: cache`) (`#memorystore-for-redis-valkey-type-cache`)
  - 1. Create the cache and the connector (console) (`#1-create-the-cache-and-the-connector-console`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/gcp/custom.md`

- Other Google Cloud services (`type: custom`) (`#other-google-cloud-services-type-custom`)
  - Firestore (`#firestore`)
  - Secret Manager (`#secret-manager`)
  - Anything else (`#anything-else`)
  - Test (`#test`)

### `docs/resource-guides/gcp/database.md`

- Cloud SQL (`type: database`) (`#cloud-sql-type-database`)
  - 1. Create the instance (console) (`#1-create-the-instance-console`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/gcp/queue.md`

- Pub/Sub as a queue (`type: queue`) (`#pubsub-as-a-queue-type-queue`)
  - 1. Create the topic (console) (`#1-create-the-topic-console`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/gcp/README.md`

- Google Cloud resources (`#google-cloud-resources`)
  - Values you need for every Google Cloud resource (`#values-you-need-for-every-google-cloud-resource`)
  - How pskit runs on Google Cloud (why some steps matter) (`#how-pskit-runs-on-google-cloud-why-some-steps-matter`)
  - Credentials for deploying (`#credentials-for-deploying`)

### `docs/resource-guides/gcp/storage.md`

- Cloud Storage bucket (`type: storage`) (`#cloud-storage-bucket-type-storage`)
  - 1. Create the bucket (console) (`#1-create-the-bucket-console`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/gcp/topic.md`

- Pub/Sub topic (`type: topic`) (`#pubsub-topic-type-topic`)
  - 1. Create the topic (console) (`#1-create-the-topic-console`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/huawei/cache.md`

- Huawei DCS for Redis (`type: cache`) (`#huawei-dcs-for-redis-type-cache`)
  - 1. Create the instance (console) (`#1-create-the-instance-console`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/huawei/custom.md`

- Other Huawei Cloud services (`type: custom`) (`#other-huawei-cloud-services-type-custom`)
  - CSMS secrets (Data Encryption Workshop) (`#csms-secrets-data-encryption-workshop`)
  - Document Database Service (DDS, MongoDB-compatible) (`#document-database-service-dds-mongodb-compatible`)
  - Test (`#test`)

### `docs/resource-guides/huawei/database.md`

- Huawei RDS (`type: database`) (`#huawei-rds-type-database`)
  - 1. Create the instance (console) (`#1-create-the-instance-console`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/huawei/queue.md`

- Huawei DMS queue (`type: queue`) (`#huawei-dms-queue-type-queue`)
  - 1. Create the instance (console) (`#1-create-the-instance-console`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/huawei/README.md`

- Huawei Cloud resources (`#huawei-cloud-resources`)
  - Values you need for every Huawei Cloud resource (`#values-you-need-for-every-huawei-cloud-resource`)
  - How pskit runs on Huawei Cloud (why some steps matter) (`#how-pskit-runs-on-huawei-cloud-why-some-steps-matter`)
  - Credentials for deploying (`#credentials-for-deploying`)

### `docs/resource-guides/huawei/storage.md`

- Huawei OBS bucket (`type: storage`) (`#huawei-obs-bucket-type-storage`)
  - 1. Create the bucket (console) (`#1-create-the-bucket-console`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/huawei/topic.md`

- Huawei SMN topic (`type: topic`) (`#huawei-smn-topic-type-topic`)
  - 1. Create the topic (console) (`#1-create-the-topic-console`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/ibm/cache.md`

- IBM Databases for Redis (`type: cache`) (`#ibm-databases-for-redis-type-cache`)
  - 1. Create the instance (console) (`#1-create-the-instance-console`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/ibm/custom.md`

- Other IBM Cloud services (`type: custom`) (`#other-ibm-cloud-services-type-custom`)
  - Secrets Manager (`#secrets-manager`)
  - Cloudant (`#cloudant`)
  - Test (`#test`)

### `docs/resource-guides/ibm/database.md`

- IBM Cloud databases (`type: database`) (`#ibm-cloud-databases-type-database`)
  - 1. Create the instance (console) (`#1-create-the-instance-console`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/ibm/queue.md`

- IBM MQ queue (`type: queue`) (`#ibm-mq-queue-type-queue`)
  - 1. Create the queue manager and queue (console) (`#1-create-the-queue-manager-and-queue-console`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/ibm/README.md`

- IBM Cloud resources (`#ibm-cloud-resources`)
  - What pskit supports on IBM Cloud (`#what-pskit-supports-on-ibm-cloud`)
  - Values you need for most IBM Cloud services (`#values-you-need-for-most-ibm-cloud-services`)
  - Secrets on Code Engine (`#secrets-on-code-engine`)
  - Credentials for deploying (`#credentials-for-deploying`)

### `docs/resource-guides/ibm/storage.md`

- IBM Cloud Object Storage bucket (`type: storage`) (`#ibm-cloud-object-storage-bucket-type-storage`)
  - 1. Create the bucket (console) (`#1-create-the-bucket-console`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/ibm/topic.md`

- IBM Event Streams topic (`type: topic`) (`#ibm-event-streams-topic-type-topic`)
  - 1. Create the instance and topic (console) (`#1-create-the-instance-and-topic-console`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/onprem/cache.md`

- On-premises caches (`type: cache`) (`#on-premises-caches-type-cache`)
  - 1. Set up Redis (`#1-set-up-redis`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/onprem/custom.md`

- Other on-premises services (`type: custom`) (`#other-on-premises-services-type-custom`)
  - The recipe (`#the-recipe`)
  - Example: SMTP server (`#example-smtp-server`)
  - Example: an internal REST API (`#example-an-internal-rest-api`)
  - Test (`#test`)

### `docs/resource-guides/onprem/database.md`

- On-premises databases (`type: database`) (`#on-premises-databases-type-database`)
  - 1. Set up PostgreSQL (`#1-set-up-postgresql`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/onprem/queue.md`

- On-premises queues (`type: queue`) (`#on-premises-queues-type-queue`)
  - Create one in one click (`#create-one-in-one-click`)
  - Built-in queue (`#built-in-queue`)
  - Redis / Valkey (`#redis-valkey`)
    - 1. Set up Redis (`#1-set-up-redis`)
    - 2. Collect the values (`#2-collect-the-values`)
    - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - Redis / Valkey stream (`redis_stream`) (`#redis-valkey-stream-redis_stream`)
  - Kafka and NATS JetStream (`#kafka-and-nats-jetstream`)
  - A queue on another on-prem host (`pskit_host`) (`#a-queue-on-another-on-prem-host-pskit_host`)
  - RabbitMQ (or other brokers) via a custom driver (`#rabbitmq-or-other-brokers-via-a-custom-driver`)
    - 1. Create the queue (RabbitMQ management UI) (`#1-create-the-queue-rabbitmq-management-ui`)
    - 2. Declare it (`#2-declare-it`)
  - A queue in a cloud (`#a-queue-in-a-cloud`)
  - Use it in a handler (`#use-it-in-a-handler`)
  - Test (`#test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/onprem/README.md`

- On-premises resources (`#on-premises-resources`)
  - How the host uses resources (`#how-the-host-uses-resources`)
  - Secrets: `<name>_env` (`#secrets-name_env`)
  - Publishing from a handler (`#publishing-from-a-handler`)
  - Testing (`#testing`)

### `docs/resource-guides/onprem/secrets.md`

- Secret managers on premises (`#secret-managers-on-premises`)
  - One click: OpenBao, pskit's Secrets Manager or LocalStack (`#one-click-openbao-pskits-secrets-manager-or-localstack`)
  - pskit's AWS Secrets Manager compatible server (`#pskits-aws-secrets-manager-compatible-server`)
  - Infisical (secrets manager with a web UI) (`#infisical-secrets-manager-with-a-web-ui`)
  - Browse secrets in the studio (`#browse-secrets-in-the-studio`)
  - Add and read secrets (`#add-and-read-secrets`)
  - An existing Vault, OpenBao or AWS Secrets Manager (`#an-existing-vault-openbao-or-aws-secrets-manager`)
  - On the clouds (`#on-the-clouds`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/onprem/services.md`

- One-click services for on-premises functions (`#one-click-services-for-on-premises-functions`)
  - pskit's own browsers (when the native UI is missing) (`#pskits-own-browsers-when-the-native-ui-is-missing`)
  - In the studio (`#in-the-studio`)
  - Credentials and network (`#credentials-and-network`)
  - Web UIs (`#web-uis`)
    - With or without a password (`#with-or-without-a-password`)
    - The UI does not open (`#the-ui-does-not-open`)
    - Try the web UIs in local Docker first (`#try-the-web-uis-in-local-docker-first`)
  - Databases: one server, or a primary with read replicas (`#databases-one-server-or-a-primary-with-read-replicas`)
  - Servers: several machines (`#servers-several-machines`)
    - Where a server is used, and how the servers connect (`#where-a-server-is-used-and-how-the-servers-connect`)
    - Deploy the functions to a chosen machine (`#deploy-the-functions-to-a-chosen-machine`)
  - Install software on a server (`#install-software-on-a-server`)
  - Console and terminal (`#console-and-terminal`)
  - Secret managers (`#secret-managers`)
  - SSH login: key, agent or password (`#ssh-login-key-agent-or-password`)
  - Use it from any program (`#use-it-from-any-program`)
  - From the command line (`#from-the-command-line`)
  - What gets written (`#what-gets-written`)
  - Existing cloud code (`#existing-cloud-code`)
  - Same server or a different one (`#same-server-or-a-different-one`)
    - When the functions move (`#when-the-functions-move`)
  - See what is inside (`#see-what-is-inside`)
  - Use it from code and test it (`#use-it-from-code-and-test-it`)
  - Removing (`#removing`)
  - Monitoring and alerts (`#monitoring-and-alerts`)
  - Start a database with data (`#start-a-database-with-data`)
  - Backups (`#backups`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/onprem/storage.md`

- On-premises storage (`type: storage`) (`#on-premises-storage-type-storage`)
  - Built-in bucket (`#built-in-bucket`)
  - pskit's Amazon S3 compatible server (one click) (`#pskits-amazon-s3-compatible-server-one-click`)
  - MinIO (or Ceph, Garage, SeaweedFS, any S3-compatible store) (`#minio-or-ceph-garage-seaweedfs-any-s3-compatible-store`)
    - 1. Create the bucket and keys (MinIO console) (`#1-create-the-bucket-and-keys-minio-console`)
    - 2. Collect the values (`#2-collect-the-values`)
    - 3. Declare it (`#3-declare-it`)
  - A bucket in a cloud (`#a-bucket-in-a-cloud`)
  - Use it in a handler (`#use-it-in-a-handler`)
  - Test (`#test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/onprem/topic.md`

- On-premises topics (`type: topic`) (`#on-premises-topics-type-topic`)
  - Built-in topic (`#built-in-topic`)
  - Use it in a handler (`#use-it-in-a-handler`)
  - Kafka, RabbitMQ exchanges, NATS, MQTT, cloud topics (`#kafka-rabbitmq-exchanges-nats-mqtt-cloud-topics`)
  - Test (`#test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/oracle/cache.md`

- OCI Cache (`type: cache`) (`#oci-cache-type-cache`)
  - 1. Create the cluster (console) (`#1-create-the-cluster-console`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/oracle/custom.md`

- Other OCI services (`type: custom`) (`#other-oci-services-type-custom`)
  - Vault secrets (`#vault-secrets`)
  - Streaming (`#streaming`)
  - Test (`#test`)

### `docs/resource-guides/oracle/database.md`

- OCI databases (`type: database`) (`#oci-databases-type-database`)
  - 1. Create the database (console) (`#1-create-the-database-console`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/oracle/queue.md`

- OCI Queue (`type: queue`) (`#oci-queue-type-queue`)
  - 1. Create the queue (console) (`#1-create-the-queue-console`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Policies (`#3-policies`)
  - 4. Declare it in `pskit.yml` (`#4-declare-it-in-pskityml`)
  - 5. Use it in a handler (`#5-use-it-in-a-handler`)
  - 6. Test (`#6-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/oracle/README.md`

- Oracle Cloud (OCI) resources (`#oracle-cloud-oci-resources`)
  - Values you need for every OCI resource (`#values-you-need-for-every-oci-resource`)
  - How pskit runs on OCI (why some steps matter) (`#how-pskit-runs-on-oci-why-some-steps-matter`)
  - Credentials for deploying (`#credentials-for-deploying`)

### `docs/resource-guides/oracle/storage.md`

- OCI Object Storage bucket (`type: storage`) (`#oci-object-storage-bucket-type-storage`)
  - 1. Create the bucket (console) (`#1-create-the-bucket-console`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Policies (`#3-policies`)
  - 4. Declare it in `pskit.yml` (`#4-declare-it-in-pskityml`)
  - 5. Use it in a handler (`#5-use-it-in-a-handler`)
  - 6. Test (`#6-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/oracle/topic.md`

- OCI Notifications topic (`type: topic`) (`#oci-notifications-topic-type-topic`)
  - 1. Create the topic (console) (`#1-create-the-topic-console`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Policies (`#3-policies`)
  - 4. Declare it in `pskit.yml` (`#4-declare-it-in-pskityml`)
  - 5. Use it in a handler (`#5-use-it-in-a-handler`)
  - 6. Test (`#6-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/README.md`

- Adding resources: step-by-step guides (`#adding-resources-step-by-step-guides`)
  - The pattern every guide follows (`#the-pattern-every-guide-follows`)
  - Secrets (`#secrets`)
  - Adding a guide for another cloud or type (`#adding-a-guide-for-another-cloud-or-type`)

### `docs/resource-guides/tencent/cache.md`

- Tencent Cloud Redis (`type: cache`) (`#tencent-cloud-redis-type-cache`)
  - 1. Create the instance (console) (`#1-create-the-instance-console`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/tencent/custom.md`

- Other Tencent Cloud services (`type: custom`) (`#other-tencent-cloud-services-type-custom`)
  - Secrets Manager (SSM) (`#secrets-manager-ssm`)
  - A third-party API (`#a-third-party-api`)
  - Test (`#test`)

### `docs/resource-guides/tencent/database.md`

- Tencent Cloud databases (`type: database`) (`#tencent-cloud-databases-type-database`)
  - 1. Create the instance (console) (`#1-create-the-instance-console`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/tencent/queue.md`

- Tencent Cloud TDMQ for CMQ queue (`type: queue`) (`#tencent-cloud-tdmq-for-cmq-queue-type-queue`)
  - 1. Create the queue (console) (`#1-create-the-queue-console`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/tencent/README.md`

- Tencent Cloud resources (`#tencent-cloud-resources`)
  - Values you need for every Tencent Cloud resource (`#values-you-need-for-every-tencent-cloud-resource`)
  - How pskit runs on Tencent Cloud (why some steps matter) (`#how-pskit-runs-on-tencent-cloud-why-some-steps-matter`)
  - Secrets (`#secrets`)
  - Credentials for deploying (`#credentials-for-deploying`)

### `docs/resource-guides/tencent/storage.md`

- Tencent Cloud COS bucket (`type: storage`) (`#tencent-cloud-cos-bucket-type-storage`)
  - 1. Create the bucket (console) (`#1-create-the-bucket-console`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-guides/tencent/topic.md`

- Tencent Cloud TDMQ for CMQ topic (`type: topic`) (`#tencent-cloud-tdmq-for-cmq-topic-type-topic`)
  - 1. Create the topic (console) (`#1-create-the-topic-console`)
  - 2. Collect the values (`#2-collect-the-values`)
  - 3. Declare it in `pskit.yml` (`#3-declare-it-in-pskityml`)
  - 4. Use it in a handler (`#4-use-it-in-a-handler`)
  - 5. Test (`#5-test`)
  - Troubleshooting (`#troubleshooting`)

### `docs/resource-usage.md`

- Using resources from code: libraries, code and tests (`#using-resources-from-code-libraries-code-and-tests`)
  - The five steps for any resource (`#the-five-steps-for-any-resource`)
  - How dependencies reach the function (`#how-dependencies-reach-the-function`)
  - Which library for which resource (`#which-library-for-which-resource`)
    - Queues, buckets and topics (`#queues-buckets-and-topics`)
    - Databases, caches and other services (`#databases-caches-and-other-services`)
  - On premises: from any other program (`#on-premises-from-any-other-program`)
  - Secrets (`#secrets`)
  - Testing checklist (`#testing-checklist`)

### `docs/resources.md`

- Resources (storage, queues, topics, databases, any service) (`#resources-storage-queues-topics-databases-any-service`)
  - Fields (`#fields`)
  - Using a resource from an event (`#using-a-resource-from-an-event`)
  - What handlers receive (`#what-handlers-receive`)
    - Runtime API (`#runtime-api`)
  - Provider support (`#provider-support`)
    - AWS IAM (`#aws-iam`)
  - On-premises drivers (`#on-premises-drivers`)
    - Provider matrix (`#provider-matrix`)
    - Queue drivers (`#queue-drivers`)
    - Storage drivers (`#storage-drivers`)
    - Examples (`#examples`)
    - Custom drivers (`#custom-drivers`)
  - Secrets (`#secrets`)
  - Troubleshooting (`#troubleshooting`)

### `docs/scenarios.md`

- Scenarios: step by step (`#scenarios-step-by-step`)
  - A. HTTP API on AWS (`#a-http-api-on-aws`)
  - B. Queue worker with a managed queue (`#b-queue-worker-with-a-managed-queue`)
  - C. Attach an existing queue or bucket (`#c-attach-an-existing-queue-or-bucket`)
  - D. On premises with Redis and MinIO (`#d-on-premises-with-redis-and-minio`)
  - E. Attach a database or custom service (`#e-attach-a-database-or-custom-service`)
  - F. Workflows: start, get the execution id, watch it (`#f-workflows-start-get-the-execution-id-watch-it`)
  - G. Scheduled jobs (`#g-scheduled-jobs`)
  - H. Stages and several clouds (`#h-stages-and-several-clouds`)
  - I. On-premises logs (`#i-on-premises-logs`)
  - J. Local development and tests (`#j-local-development-and-tests`)
  - K. On premises, watching queues and buckets in other clouds (`#k-on-premises-watching-queues-and-buckets-in-other-clouds`)

### `docs/smtp/README.md`

- E-mail triggers (SMTP) on premises (`#e-mail-triggers-smtp-on-premises`)
  - How it works (`#how-it-works`)
  - Create it (`#create-it`)
  - DNS records at your domain provider (`#dns-records-at-your-domain-provider`)
  - Port 25 (`#port-25`)
  - What the handler receives (`#what-the-handler-receives`)
  - Test it (`#test-it`)
  - Change it (`#change-it`)
  - Troubleshooting (`#troubleshooting`)

### `docs/smtp/smtp_flow.jpg`

- (no Markdown headings)

### `docs/studio.md`

- Studio: build a project without writing YAML (`#studio-build-a-project-without-writing-yaml`)
  - What you can do (`#what-you-can-do`)
  - Setup, logs and provider differences (`#setup-logs-and-provider-differences`)
  - Test functions (`#test-functions`)
  - Project environment, trigger resources and remove (`#project-environment-trigger-resources-and-remove`)
  - Saving: what changes in pskit.yml (`#saving-what-changes-in-pskityml`)
  - Browse account (`#browse-account`)
  - Full VS Code (code-server in Docker) (`#full-vs-code-code-server-in-docker`)
  - Security (`#security`)
  - Developing the studio UI (`#developing-the-studio-ui`)

### `docs/troubleshooting.md`

- Troubleshooting & FAQ (`#troubleshooting-faq`)
  - Installation and tooling (`#installation-and-tooling`)
  - Configuration (`#configuration`)
  - Deploy and state (`#deploy-and-state`)
  - HTTP (`#http`)
  - Provider gotchas (`#provider-gotchas`)
  - FAQ (`#faq`)
  - Security notes (`#security-notes`)

### `docs/workflow-executions.md`

- Workflow executions (`#workflow-executions`)
  - Starting a run (`#starting-a-run`)
    - On premises over HTTP (`#on-premises-over-http`)
    - Embedded orchestrator on a cloud (`#embedded-orchestrator-on-a-cloud`)
  - The execution record (`#the-execution-record`)
  - Following a run (`#following-a-run`)
  - Cancel, timeouts and restarts (embedded engine) (`#cancel-timeouts-and-restarts-embedded-engine`)
  - AWS Step Functions and Google Cloud Workflows (`#aws-step-functions-and-google-cloud-workflows`)
  - HTTP API (on-premises host) (`#http-api-on-premises-host`)

### `docs/workflows.md`

- Workflows (state machines) (`#workflows-state-machines`)
  - Workflow keys (`#workflow-keys`)
  - State types (`#state-types`)
    - Data flow (`#data-flow`)
    - Choice rules (`#choice-rules`)
    - Retry and catch (`#retry-and-catch`)
  - Engines (`#engines`)
    - Embedded orchestrator (`#embedded-orchestrator`)
    - Compiler notes and limits (`#compiler-notes-and-limits`)
  - Commands (`#commands`)
  - Migrating Step Functions ASL (`#migrating-step-functions-asl`)

## 1d. Resources

Schema types (`RESOURCE_TYPES` in `src/py_serverless_kit/config/schema.py`): storage, queue, topic, database, cache, custom, smtp.
`database`, `cache` and `custom` must be `external: true` (schema `_managed`). `storage`, `queue`, `topic` and `smtp` may be managed.
`secrets` is not a `type`. Secret managers are on-prem services and `get_secret()` (`docs/resource-guides/onprem/secrets.md`, `docs/handlers.md#get_secret-secrets-on-every-provider`).
The Fields table in `docs/resources.md#fields` omits smtp. See `conflicts.md`.

Managed vs external summary from `docs/resources.md#provider-support`:

- aws, gcp, azure, onprem: managed resources may exist with or without an event (native names in that section).
- alibaba, tencent, huawei, oracle, ibm, digitalocean, cloudflare: managed only when an event uses the resource; otherwise `external: true`.
- database / cache / custom: external on every provider (env only).

Connection variables: `PSKIT_RESOURCES`, `PSKIT_RESOURCE_<KEY>_TYPE`, `_NAME`, `_EXTERNAL`, `_<CONNECTION KEY>`, plus `_ARN` / `_URL` / `_ID` when the provider knows them (`docs/resources.md#what-handlers-receive`).
Read with `resource(name)` (`runtime/resources.py`). Libraries: `docs/resource-usage.md#which-library-for-which-resource`.
Events that can name a resource: queue, storage, topic, smtp (`EVENT_RESOURCE_TYPES`).

### Guide cell (type × provider)

A cell is the H1 of `docs/resource-guides/<cloud>/<type>.md` when that file exists. `smtp` has no per-cloud guide file; the on-prem SMTP server is `docs/smtp/README.md` and `docs/resource-guides/onprem/services.md`.

| type | aws | azure | gcp | alibaba | tencent | huawei | oracle | ibm | digitalocean | cloudflare | onprem |
|---|---|---|---|---|---|---|---|---|---|---|---|
| storage | Amazon S3 bucket | Azure Blob container | Cloud Storage bucket | Alibaba Cloud OSS bucket | Tencent Cloud COS bucket | Huawei OBS bucket | OCI Object Storage bucket | IBM Cloud Object Storage bucket | DigitalOcean Spaces bucket | Cloudflare R2 bucket | On-premises storage |
| queue | Amazon SQS queue | Azure Storage queue | Pub/Sub as a queue | Alibaba Cloud SMQ / MNS queue | Tencent Cloud TDMQ for CMQ queue | Huawei DMS queue | OCI Queue | IBM MQ queue | Queues on DigitalOcean | Cloudflare Queues | On-premises queues |
| topic | Amazon SNS topic | Azure Service Bus topic | Pub/Sub topic | Alibaba Cloud SMQ / MNS topic | Tencent Cloud TDMQ for CMQ topic | Huawei SMN topic | OCI Notifications topic | IBM Event Streams topic | DigitalOcean Managed Kafka topic | Topics on Cloudflare | On-premises topics |
| database | Amazon RDS / Aurora | Azure databases | Cloud SQL | Alibaba Cloud databases | Tencent Cloud databases | Huawei RDS | OCI databases | IBM Cloud databases | DigitalOcean Managed databases | Cloudflare databases | On-premises databases |
| cache | Amazon ElastiCache / MemoryDB | Azure Redis | Memorystore for Redis / Valkey | Alibaba Cloud Tair / Redis | Tencent Cloud Redis | Huawei DCS for Redis | OCI Cache | IBM Databases for Redis | DigitalOcean Managed Valkey | Workers KV | On-premises caches |
| custom | Other AWS services | Other Azure services | Other Google Cloud services | Other Alibaba Cloud services | Other Tencent Cloud services | Other Huawei Cloud services | Other OCI services | Other IBM Cloud services | Other DigitalOcean services | Other Cloudflare services and APIs | Other on-premises services |
| smtp | no smtp guide | no smtp guide | no smtp guide | no smtp guide | no smtp guide | no smtp guide | no smtp guide | no smtp guide | no smtp guide | no smtp guide | on-prem SMTP server (docs/smtp/README.md) |

Cells: 77 (7 types × 11 providers). Guide files matched: 66.

Extra on-prem pages (not a schema type × provider cell):

- Secret managers on premises (docs/resource-guides/onprem/secrets.md)
- One-click services for on-premises functions (docs/resource-guides/onprem/services.md)
- `docs/resource-guides/README.md` — index table of native services per cloud.
- `docs/resource-guides/compatibility.md` — existing cloud code.
- Each cloud `README.md` under `docs/resource-guides/<cloud>/`.

Native service names in the index table (`docs/resource-guides/README.md`):

| provider | storage | queue | topic | database | cache | custom |
|---|---|---|---|---|---|---|
| aws | S3 | SQS | SNS | RDS / Aurora | ElastiCache / MemoryDB | DynamoDB, Secrets Manager, … |
| gcp | Cloud Storage | Pub/Sub topic as a queue | Pub/Sub topic | Cloud SQL | Memorystore | Firestore, Secret Manager, … |
| azure | Blob container | Storage queue | Service Bus topic | PostgreSQL / MySQL / SQL | Redis | Cosmos DB, Key Vault, … |
| alibaba | OSS | SMQ / MNS queue | SMQ / MNS topic | ApsaraDB RDS / PolarDB | Tair (Redis) | Tablestore, KMS, … |
| tencent | COS | TDMQ for CMQ queue | TDMQ for CMQ topic | TencentDB MySQL / PostgreSQL | TencentDB for Redis | Secrets Manager, … |
| huawei | OBS | DMS RabbitMQ / Kafka | SMN | RDS | DCS Redis | CSMS, DDS, … |
| oracle | Object Storage | OCI Queue | Notifications | Autonomous DB, MySQL HeatWave | OCI Cache | Vault, Streaming, … |
| ibm | Cloud Object Storage | IBM MQ | Event Streams | Databases for PostgreSQL / MySQL | Databases for Redis | Secrets Manager, Cloudant, … |
| digitalocean | Spaces | Valkey list as a queue | Managed Kafka | Managed PostgreSQL / MySQL | Managed Valkey | MongoDB, OpenSearch, DO API |
| cloudflare | R2 | Queues | No topics: alternatives | D1 / Hyperdrive | Workers KV | Secrets, Workers AI, HTTP APIs |
| onprem | Built-in, MinIO, S3, R2, Blob, GCS | Built-in, Redis, Kafka, NATS, RabbitMQ, another host, SQS, … | Built-in / directory | PostgreSQL / MySQL | Redis / Valkey | SMTP, LDAP, internal APIs |

Source of that table: `docs/resource-guides/README.md` (the link text in the matrix).

## 1e. On-premises topics

Topic checklist (each becomes at least one card):

- `deploy-local` — Deploy method local: process on this machine. docs/providers.md#onprem-on-premises
- `deploy-ssh` — Deploy method ssh (scp is the same path): release.tar.gz, systemd or a process, health /__pskit/health. docs/architecture.md#bundle-layout
- `deploy-docker` — Deploy method docker: image built here, copied over SSH, docker load/run; install_docker default true. docs/providers.md
- `python-bundle` — python: bundle portable CPython, or python: system. docs/providers.md
- `saved-servers` — Saved SSH servers: add, list, test, check, top, usage, remove. CLI resources onprem servers *. core/onprem_servers.py
- `ssh-key` — Install an SSH key once (resources onprem ssh-key). docs/studio.md
- `shell` — Shell on a saved server (resources onprem shell). Studio: Shell
- `terminal` — Browser terminal via ttyd in Docker (resources onprem terminal). Studio: Terminal
- `runtimes` — Install docker, python, nodejs, java, go, nginx, caddy, certbot, pm2, git, tools. Catalog kind runtime.
- `one-click-services` — Create/list/status/logs/backup/remove/gui/monitor/alerts. docs/resource-guides/onprem/services.md
- `database-single` — Database on one server. docs/resource-guides/onprem/database.md
- `database-replicas` — Primary plus read replicas, add/remove. CLI resources onprem replicas. core/onprem_replication.py
- `backup` — resources onprem backup writes .pskit/backups. docs/studio.md
- `monitor-alerts` — resources onprem monitor and alerts. Studio Monitoring.tsx
- `web-ui` — Also start the web UI; Details > Add/Remove/Check web UI. docs/studio.md
- `console` — resources onprem console (redis-cli, psql, mongosh, rpk, bao, …)
- `browse` — pskit browsers for buckets and secrets. core/onprem_browser.py
- `secrets-managers` — OpenBao, secretsmanager, secretsmanager-node, Infisical, LocalStack. docs/resource-guides/onprem/secrets.md
- `s3-server` — minio, rustfs, s3, s3-node, fake-gcs, azurite, localstack, localemu. docs/resource-guides/onprem/storage.md
- `smtp-dns` — smtp service plus DNS A/MX. docs/smtp/README.md
- `cluster-types` — swarm, kubernetes (k3s), nomad. docs/cluster.md#how-the-functions-run-in-a-cluster
- `cluster-lifecycle` — create, join, leave, set, scale, status, check, watch, alerts, requests, remove. docs/cluster.md#commands
- `cluster-balancer` — cluster balancer set/remove/sync/logs. docs/cluster.md
- `placement` — provider.options.placement groups. docs/placement.md
- `lb-algorithms` — round_robin, sticky_round_robin, weighted_round_robin, ip_hash, least_connections (default), least_time. pskit lb algorithms
- `lb-routes` — lb create/update/list/status/attach/detach/routes remove/sync/logs/remove/forget. docs/load-balancers.md
- `network-map` — Studio Network map. core/onprem_usage.py, docs/onprem-network.md
- `firewall` — pskit firewall. docs/onprem-network.md
- `tunnels` — resources onprem tunnel and client tunnel. docs/client.md#when-connections-time-out

Topic count: 29.

### One-click catalog

From `pskit resources onprem catalog --json` (`core/onprem_services.py` `catalog()`), saved as `onprem_catalog.json`.

| id | kind | group | roles | port | image |
|---|---|---|---|---|---|
| `redis` | service | Caches and queues | queue, stream, cache | 6379 | redis:7-alpine |
| `valkey` | service | Caches and queues | queue, stream, cache | 6379 | valkey/valkey:8-alpine |
| `rabbitmq` | service | Queues and streams | queue | 5672 | rabbitmq:3-management-alpine |
| `elasticmq` | service | Queues and streams | queue | 9324 | softwaremill/elasticmq-native:1.6.11 |
| `postgres` | service | Databases | database | 5432 | postgres:16-alpine |
| `mysql` | service | Databases | database | 3306 | mysql:8.4 |
| `mariadb` | service | Databases | database | 3306 | mariadb:11 |
| `mongodb` | service | Databases | database | 27017 | mongo:7 |
| `minio` | service | Object storage | storage | 9000 | bitnamilegacy/minio:2025.7.23 |
| `kafka` | service | Queues and streams | queue | 9092 | redpandadata/redpanda:v24.3.6 |
| `nats` | service | Queues and streams | queue | 4222 | nats:2.10-alpine |
| `dragonfly` | service | Caches and queues | queue, stream, cache | 6379 | docker.dragonflydb.io/dragonflydb/dragonfly:v1.25.1 |
| `keydb` | service | Caches and queues | queue, stream, cache | 6379 | eqalpha/keydb:latest |
| `apache-kafka` | service | Queues and streams | queue | 9092 | apache/kafka:3.8.1 |
| `lavinmq` | service | Queues and streams | queue | 5672 | cloudamqp/lavinmq:latest |
| `azurite` | service | Object storage | queue, storage | 10000 | mcr.microsoft.com/azure-storage/azurite:3.33.0 |
| `localstack` | service | AWS emulators | queue, storage, secrets | 4566 | localstack/localstack:3.8 |
| `openbao` | service | Secrets | secrets | 8200 | openbao/openbao:2.1.0 |
| `fake-gcs` | service | Object storage | storage | 4443 | fsouza/fake-gcs-server:1.52 |
| `rustfs` | service | Object storage | storage | 9000 | rustfs/rustfs:latest |
| `memcached` | service | Caches and queues | cache | 11211 | memcached:1.6-alpine |
| `mailpit` | service | Tools | custom | 1025 | axllent/mailpit:latest |
| `smtp` | service | Mail | smtp | 25 | node:22-alpine |
| `secretsmanager` | service | Secrets | secrets | 4584 | python:3.12-alpine |
| `secretsmanager-node` | service | Secrets | secrets | 4584 | node:22-alpine |
| `s3` | service | Object storage | storage | 9000 | python:3.12-alpine |
| `s3-node` | service | Object storage | storage | 9000 | node:22-alpine |
| `localemu` | service | AWS emulators | queue, storage, secrets | 4566 | localemu/localemu:latest |
| `infisical` | service | Secrets | secrets | 8080 | infisical/infisical:latest |
| `grafana` | service | Monitoring | custom | 3000 | grafana/grafana:11.3.0 |
| `prometheus` | service | Monitoring | custom | 9090 | prom/prometheus:v2.55.1 |
| `uptime-kuma` | service | Monitoring | custom | 3001 | louislam/uptime-kuma:1 |
| `jaeger` | service | Monitoring | custom | 16686 | jaegertracing/all-in-one:1.62.0 |
| `keycloak` | service | Identity | custom | 8080 | quay.io/keycloak/keycloak:26.0 |
| `meilisearch` | service | Search | custom | 7700 | getmeili/meilisearch:v1.11 |
| `typesense` | service | Search | custom | 8108 | typesense/typesense:27.1 |
| `qdrant` | service | Databases | database | 6333 | qdrant/qdrant:v1.12.4 |
| `clickhouse` | service | Databases | database | 8123 | clickhouse/clickhouse-server:24.8 |
| `neo4j` | service | Databases | database | 7687 | neo4j:5 |
| `mosquitto` | service | Queues and streams | custom | 1883 | eclipse-mosquitto:2 |
| `n8n` | service | Automation | custom | 5678 | n8nio/n8n:latest |
| `portainer` | service | Tools | custom | 9000 | portainer/portainer-ce:2.21.4 |
| `gitea` | service | Tools | custom | 3000 | gitea/gitea:1.22 |
| `nginx-proxy-manager` | service | Web | custom | 81 | jc21/nginx-proxy-manager:latest |
| `docker` | runtime | Languages and Docker | runtime |  |  |
| `python` | runtime | Languages and Docker | runtime |  |  |
| `nodejs` | runtime | Languages | runtime |  |  |
| `java` | runtime | Languages | runtime |  |  |
| `go` | runtime | Languages | runtime |  |  |
| `nginx` | runtime | Web servers | runtime |  |  |
| `caddy` | runtime | Web servers | runtime |  |  |
| `certbot` | runtime | Web servers | runtime |  |  |
| `pm2` | runtime | Process managers | runtime |  |  |
| `git` | runtime | Tools | runtime |  |  |
| `tools` | runtime | Tools | runtime |  |  |

Catalog entries: 55.

### Load balancer algorithms

From `pskit lb algorithms` (`core/onprem_lb.py`):

- Static: `round_robin`, `sticky_round_robin`, `weighted_round_robin`, `ip_hash`
- Dynamic: `least_connections` (default), `least_time`

## 1f. Code map

One line per Python module. The sentence is the module docstring's first sentence, or blank when the file has no module docstring.
Pipeline (from `docs/architecture.md#deploy-pipeline` and `CLAUDE.md`):

`pskit.yml` → `config/loader.py` → `config/schema.py` (`ServiceConfig`) → `core/project.py` → `Provider.validate()` → `packaging/builder.py` → `Provider.render()` (`TerraformDoc` / `main.tf.json`) → `terraform/runner.py` → `core/describe.py` (`deployment.json`) → `dashboard/generator.py`.

Runtime (`docs/architecture.md#runtime-flow`): platform → shim → `runtime/adapters/<cloud>.py` → `runtime/dispatch.py` `execute` → handler.

`__pskit` envelope: `{"__pskit": "<schedule|workflow|invoke>", "data": ...}` (`docs/architecture.md#runtime-flow`, `runtime/adapters/base.py` `unwrap_envelope`).

Terraform output `pskit`: `{functions, workflows, endpoint}` (`docs/architecture.md#deploy-pipeline`).

Workflow engines: `workflows/asl.py` (AWS), `workflows/gcp.py` (Google Cloud Workflows), `workflows/azure_logic.py` (Azure Logic Apps). Elsewhere `runtime/workflow.py` `orchestrate` (`docs/architecture.md#runtime-flow`, `CLAUDE.md`).

Python modules: 142.

- `src/py_serverless_kit/__init__.py` — py_serverless_kit - write a Python function once, deploy it to any cloud.
- `src/py_serverless_kit/__main__.py` — (no module docstring)
- `src/py_serverless_kit/_version.py` — (no module docstring)
- `src/py_serverless_kit/cli/__init__.py` — (no module docstring)
- `src/py_serverless_kit/cli/main.py` — `pskit` command line interface.
- `src/py_serverless_kit/cli/templates.py` — Project scaffolds for `pskit init`.
- `src/py_serverless_kit/client.py` — Use an on-premises pskit host from any Python program (standard library only).
- `src/py_serverless_kit/config/__init__.py` — (no module docstring)
- `src/py_serverless_kit/config/loader.py` — Load, merge and interpolate `pskit.yml`.
- `src/py_serverless_kit/config/schema.py` — Typed model of `pskit.yml`.
- `src/py_serverless_kit/core/__init__.py` — (no module docstring)
- `src/py_serverless_kit/core/client_examples.py` — Complete programs that use one on-prem resource through the pskit host (pskit client).
- `src/py_serverless_kit/core/client_guide.py` — How to call a deployed on-prem host from any program: the pskit client (Python, Node.js) and HTTP.
- `src/py_serverless_kit/core/cloud_logs.py` — Read, list and delete the logs of a deployment, whatever cloud it runs on.
- `src/py_serverless_kit/core/deployer.py` — High level package / deploy / remove orchestration used by the CLI.
- `src/py_serverless_kit/core/describe.py` — Builds the deployment record that powers `pskit info` and the dashboard.
- `src/py_serverless_kit/core/executions.py` — List, inspect, start and cancel workflow executions of a deployment.
- `src/py_serverless_kit/core/function_split.py` — Move a function that shares a code file with others into its own sub-project folder.
- `src/py_serverless_kit/core/onprem_apps.py` — More one-click on-prem services: AWS emulators, secret managers, monitoring, identity, search, automation, tools.
- `src/py_serverless_kit/core/onprem_balancers.py` — Named load balancers: one saved server running OpenResty that many projects and clusters share by path.
- `src/py_serverless_kit/core/onprem_browser.py` — pskit's own web UI for on-prem services whose native UI is missing or limited.
- `src/py_serverless_kit/core/onprem_clients.py` — Use an on-prem resource from *any* program: a script, a web app, a cron job, another service.
- `src/py_serverless_kit/core/onprem_cluster.py` — Scaling clusters for on-prem functions: Docker Swarm, Kubernetes (k3s) or HashiCorp Nomad on saved SSH servers.
- `src/py_serverless_kit/core/onprem_cluster_scripts.py` — Shell scripts and workload manifests for on-prem scaling clusters (Docker Swarm, Kubernetes via k3s, Nomad).
- `src/py_serverless_kit/core/onprem_console.py` — A console for one-click services, in the studio and the CLI: type a command, see its output.
- `src/py_serverless_kit/core/onprem_control.py` — Talk to a deployed on-premises host's control API (`/__pskit/...`).
- `src/py_serverless_kit/core/onprem_follow.py` — On-prem services follow the functions when they move (`pskit deploy` to another server or cluster, or after the server they ran on was removed).
- `src/py_serverless_kit/core/onprem_lb.py` — Load balancing algorithms and the OpenResty (nginx + Lua) config pskit writes for them.
- `src/py_serverless_kit/core/onprem_monitor.py` — Live monitoring, alerts and data import for on-prem databases (and the CPU / memory of any service container).
- `src/py_serverless_kit/core/onprem_network.py` — The firewall rules on-prem servers need, with their real names and addresses (docs/onprem-network.md).
- `src/py_serverless_kit/core/onprem_placement.py` — Function placement on premises: groups of functions on different servers (or clusters), one project.
- `src/py_serverless_kit/core/onprem_replication.py` — Replicated databases: one primary that takes the writes, read replicas on other servers, and an optional load balancer that gives the functions a single address and splits reads from writes.
- `src/py_serverless_kit/core/onprem_runtimes.py` — Software pskit installs on an SSH server: language runtimes, web servers and tools.
- `src/py_serverless_kit/core/onprem_s3.py` — The `s3` / `s3-node` on-prem services: pskit's Amazon S3 compatible server.
- `src/py_serverless_kit/core/onprem_secretsmanager.py` — The `secretsmanager` / `secretsmanager-node` on-prem services: pskit's AWS Secrets Manager compatible server.
- `src/py_serverless_kit/core/onprem_servers.py` — Saved SSH servers: name a machine once, then create services, install software, open consoles and deploy to it.
- `src/py_serverless_kit/core/onprem_services.py` — Create, inspect, back up and remove the services on-premises functions use.
- `src/py_serverless_kit/core/onprem_smtp.py` — The `smtp` on-prem service: a Node.js SMTP server that turns received mail into `smtp` events.
- `src/py_serverless_kit/core/onprem_terminal.py` — A full terminal in the browser (ttyd in Docker on this machine): SSH to a server, or a shell / client inside a service's container.
- `src/py_serverless_kit/core/onprem_usage.py` — Where each saved on-prem server is used, how the machines connect, and which functions really use a resource.
- `src/py_serverless_kit/core/project.py` — A loaded project: config + provider + working directory, ready to build/deploy.
- `src/py_serverless_kit/core/resource_code.py` — Ready-to-paste Python and Node.js handler code for each resource.
- `src/py_serverless_kit/core/resource_usage.py` — End-to-end "how to use this resource" guide, for one resource of the current project.
- `src/py_serverless_kit/core/retain.py` — `pskit remove --keep-resources`: destroy functions and triggers, keep the data.
- `src/py_serverless_kit/core/settings_bundle.py` — Move a project's local settings to another machine: one passphrase-encrypted file.
- `src/py_serverless_kit/core/setup_check.py` — Check what a provider needs on this machine, and explain how to fix what's missing.
- `src/py_serverless_kit/core/testing.py` — Test functions with real events: what to send, how, and sending it.
- `src/py_serverless_kit/dashboard/__init__.py` — (no module docstring)
- `src/py_serverless_kit/dashboard/generator.py` — Generate the deployment dashboard: one self-contained `index.html`.
- `src/py_serverless_kit/dashboard/server.py` — `pskit dashboard --serve`: the dashboard page plus a small JSON API.
- `src/py_serverless_kit/local/__init__.py` — (no module docstring)
- `src/py_serverless_kit/local/runner.py` — Run handlers and workflows on your machine, exactly as the cloud adapters would.
- `src/py_serverless_kit/local/server.py` — `pskit dev` - a local HTTP server that routes requests to your handlers.
- `src/py_serverless_kit/packaging/__init__.py` — (no module docstring)
- `src/py_serverless_kit/packaging/builder.py` — Build the deployment artifact (a deterministic zip).
- `src/py_serverless_kit/packaging/node.py` — Node.js / TypeScript build steps shared by packaging and local runs.
- `src/py_serverless_kit/packaging/subprojects.py` — Function sub-projects: a function whose handler lives in its own folder with its own dependencies.
- `src/py_serverless_kit/providers/__init__.py` — (no module docstring)
- `src/py_serverless_kit/providers/alibaba.py` — Alibaba Cloud: Function Compute 3.0 + HTTP / timer / OSS / MNS-topic triggers.
- `src/py_serverless_kit/providers/aws.py` — AWS: Lambda + API Gateway HTTP API + EventBridge Scheduler + SQS + S3 + SNS + Step Functions.
- `src/py_serverless_kit/providers/azure.py` — Azure: Linux Function App (Consumption plan, Python v2 / Node.js v4 programming model).
- `src/py_serverless_kit/providers/base.py` — Provider plug-in contract.
- `src/py_serverless_kit/providers/cloudflare.py` — Cloudflare Workers, one Worker script per function, in Python (Pyodide) or JavaScript.
- `src/py_serverless_kit/providers/digitalocean.py` — DigitalOcean Functions.
- `src/py_serverless_kit/providers/gcp.py` — GCP: Cloud Functions (2nd gen) + Cloud Scheduler + Pub/Sub + Cloud Storage + Cloud Workflows.
- `src/py_serverless_kit/providers/huawei.py` — Huawei Cloud: FunctionGraph + dedicated API Gateway + timer / OBS / SMN triggers.
- `src/py_serverless_kit/providers/ibm.py` — IBM Cloud: Code Engine functions (HTTP endpoints).
- `src/py_serverless_kit/providers/onprem.py` — On-premises provider.
- `src/py_serverless_kit/providers/onprem_catalog.py` — Data catalog of the on-premises resource drivers, used by `pskit studio` forms.
- `src/py_serverless_kit/providers/onprem_remote.py` — Laptop-side apply/destroy for an on-premises host.
- `src/py_serverless_kit/providers/onprem_spec.py` — Parse and validate `provider.options.deploy` for the on-premises provider.
- `src/py_serverless_kit/providers/oracle.py` — Oracle Cloud Infrastructure: OCI Functions (container images) + API Gateway + Events.
- `src/py_serverless_kit/providers/regions.py` — Public regions per built-in provider, for pickers (studio) and help text.
- `src/py_serverless_kit/providers/registry.py` — Provider registry.
- `src/py_serverless_kit/providers/schedule.py` — Convert the portable schedule syntax into each provider's dialect.
- `src/py_serverless_kit/providers/tencent.py` — Tencent Cloud: SCF + API Gateway + timer / COS triggers.
- `src/py_serverless_kit/providers/terraform_doc.py` — Builder for Terraform JSON configuration (`main.tf.json`).
- `src/py_serverless_kit/runtime/__init__.py` — Portable function runtime.
- `src/py_serverless_kit/runtime/adapters/__init__.py` — Per-provider translation between native payloads and the portable model.
- `src/py_serverless_kit/runtime/adapters/_httpfn.py` — Shared logic for providers where *every* invocation arrives as an HTTP-ish request (IBM Code Engine, DigitalOcean web functions, Cloudflare Workers, OCI behind API Gateway).
- `src/py_serverless_kit/runtime/adapters/alibaba.py` — Alibaba Cloud Function Compute 3.0 adapter.
- `src/py_serverless_kit/runtime/adapters/aws.py` — AWS Lambda adapter.
- `src/py_serverless_kit/runtime/adapters/azure.py` — Azure Functions (Python v2 programming model) adapter.
- `src/py_serverless_kit/runtime/adapters/base.py` — Helpers shared by all adapters.
- `src/py_serverless_kit/runtime/adapters/cloudflare.py` — Cloudflare Python Workers adapter (Pyodide).
- `src/py_serverless_kit/runtime/adapters/digitalocean.py` — DigitalOcean Functions adapter (`main(event, context)`).
- `src/py_serverless_kit/runtime/adapters/gcp.py` — Google Cloud Functions (2nd gen) adapter.
- `src/py_serverless_kit/runtime/adapters/huawei.py` — Huawei Cloud FunctionGraph adapter.
- `src/py_serverless_kit/runtime/adapters/ibm.py` — IBM Cloud Code Engine functions adapter.
- `src/py_serverless_kit/runtime/adapters/onprem.py` — On-premises adapter.
- `src/py_serverless_kit/runtime/adapters/oracle.py` — Oracle Cloud (OCI) Functions adapter, built on the Fn Project Python FDK.
- `src/py_serverless_kit/runtime/adapters/tencent.py` — Tencent Cloud SCF adapter.
- `src/py_serverless_kit/runtime/batch.py` — Partial batch failure reporting for queue / topic / storage events.
- `src/py_serverless_kit/runtime/context.py` — Provider-neutral invocation context.
- `src/py_serverless_kit/runtime/cron.py` — 5-field cron and rate schedules for the on-premises host.
- `src/py_serverless_kit/runtime/dispatch.py` — Calls the user's handler with a normalized event and normalizes the result.
- `src/py_serverless_kit/runtime/drivers/__init__.py` — External backends the on-premises host can use for queues and storage.
- `src/py_serverless_kit/runtime/drivers/_aws.py` — AWS Signature Version 4 and credential lookup, shared by the `s3` and `sqs` drivers.
- `src/py_serverless_kit/runtime/drivers/_http.py` — Small HTTP helper shared by the REST-based drivers (standard library only).
- `src/py_serverless_kit/runtime/drivers/azure.py` — Azure Storage Queue and Blob drivers (REST, standard library only).
- `src/py_serverless_kit/runtime/drivers/cloudflare.py` — Cloudflare Queues driver through the HTTP pull consumer API (standard library only).
- `src/py_serverless_kit/runtime/drivers/gcp.py` — Google Cloud Pub/Sub (pull) and Cloud Storage drivers (REST, standard library only).
- `src/py_serverless_kit/runtime/drivers/mns.py` — Alibaba Cloud MNS (Message Service) queue driver (REST + XML, standard library only).
- `src/py_serverless_kit/runtime/drivers/probe.py` — Check that a database / cache / custom service answers (standard library only).
- `src/py_serverless_kit/runtime/drivers/pskit_host.py` — A built-in queue of another pskit on-premises host (standard library only).
- `src/py_serverless_kit/runtime/drivers/redis.py` — Redis-backed queue for the on-premises host (standard library only).
- `src/py_serverless_kit/runtime/drivers/redis_stream.py` — A Redis / Valkey stream with a consumer group as an on-prem queue (standard library only).
- `src/py_serverless_kit/runtime/drivers/s3.py` — S3-compatible object storage for the on-premises host (standard library only).
- `src/py_serverless_kit/runtime/drivers/sqs.py` — AWS SQS queue driver (JSON protocol, SigV4, standard library only).
- `src/py_serverless_kit/runtime/errors.py` — Exceptions a handler can raise to produce a well-formed HTTP error response.
- `src/py_serverless_kit/runtime/event.py` — Provider-neutral event model.
- `src/py_serverless_kit/runtime/executions.py` — Tracked workflow executions for the embedded engine.
- `src/py_serverless_kit/runtime/hostlog.py` — Log capture for the on-premises host.
- `src/py_serverless_kit/runtime/invoke.py` — Portable function-to-function invocation.
- `src/py_serverless_kit/runtime/log.py` — Structured JSON logging that every provider's log pipeline can ingest.
- `src/py_serverless_kit/runtime/manifest.py` — Reads `pskit_manifest.json` - the per-bundle description of every function.
- `src/py_serverless_kit/runtime/node_worker.py` — Drive Node.js functions from Python through `pskit_runtime/worker.js`.
- `src/py_serverless_kit/runtime/onprem_host.py` — On-premises host: one process for HTTP, schedules, queues, storage and topics.
- `src/py_serverless_kit/runtime/peers.py` — Function groups on other servers (on-prem `provider.options.placement`): reach them over HTTP.
- `src/py_serverless_kit/runtime/resources.py` — Read the `resources:` bindings of the current function.
- `src/py_serverless_kit/runtime/response.py` — Provider-neutral HTTP response model.
- `src/py_serverless_kit/runtime/routing.py` — Tiny route matcher used where the provider has no API gateway in front of the function (GCP, IBM, DigitalOcean, Cloudflare, ...) and by the local dev server.
- `src/py_serverless_kit/runtime/secrets.py` — Read (and write) secrets from handlers with one call on every provider.
- `src/py_serverless_kit/runtime/workflow.py` — Embedded workflow (state machine) engine.
- `src/py_serverless_kit/studio/__init__.py` — `pskit studio`: a local web app that builds pskit projects without hand-written YAML.
- `src/py_serverless_kit/studio/devenv.py` — The project's local environment: a `.venv` with `requirements.txt` (Python) or `npm install` (Node.js).
- `src/py_serverless_kit/studio/discover.py` — `GET /api/discover`: list existing queues, buckets, topics and workflows to pick from.
- `src/py_serverless_kit/studio/files.py` — Project file access for the studio's code editor, confined to the project root.
- `src/py_serverless_kit/studio/guides.py` — The step-by-step resource guides (`docs/resource-guides`) for the studio.
- `src/py_serverless_kit/studio/jobs.py` — Run pskit commands (validate, deploy, ...) for the studio and stream their output.
- `src/py_serverless_kit/studio/meta.py` — `GET /api/meta`: the catalog that drives every studio form.
- `src/py_serverless_kit/studio/node_stubs.py` — Handler stubs for Node.js services (TypeScript, ESM or CommonJS JavaScript).
- `src/py_serverless_kit/studio/project.py` — Read, validate and save `pskit.yml` for the studio.
- `src/py_serverless_kit/studio/server.py` — `pskit studio`: build a project in the browser instead of writing YAML by hand.
- `src/py_serverless_kit/studio/system.py` — Studio helpers that reach outside the project: a file picker, setup checks and deployed logs.
- `src/py_serverless_kit/studio/vscode.py` — Full VS Code in the browser: code-server in Docker, pulled on first use.
- `src/py_serverless_kit/terraform/__init__.py` — (no module docstring)
- `src/py_serverless_kit/terraform/runner.py` — Thin, testable wrapper around the `terraform` / `tofu` binary.
- `src/py_serverless_kit/workflows/__init__.py` — Workflow (state machine) compilers.
- `src/py_serverless_kit/workflows/asl.py` — Compile a portable workflow definition to Amazon States Language.
- `src/py_serverless_kit/workflows/azure_logic.py` — Compile a portable workflow definition to an Azure Logic Apps (Consumption) definition.
- `src/py_serverless_kit/workflows/gcp.py` — Compile a portable workflow definition to Google Cloud Workflows (JSON syntax).

### `runtime_js/`

Node runtime copied into Node bundles. Files (from the tree, no per-file docstring walk): `index.js`, `dispatch.js`, `event.js`, `context.js`, `routing.js`, `response.js`, `batch.js`, `errors.js`, `invoke.js`, `log.js`, `manifest.js`, `resources.js`, `secrets.js`, `workflow.js`, `worker.js`, `client.js`, `onprem.js`, `util.js`, `package.json`, `index.d.ts`, `adapters/*.js`. Contract: `deploy_docs/NODE_RUNTIME.md`, `docs/nodejs.md`.

## 1g. Terraform and Docker

### Terraform

- Generated as Python dicts (`providers/terraform_doc.py`), written as `main.tf.json`. User `${` is escaped to `$${` unless written `${tf:...}` (`docs/architecture.md#deploy-pipeline`, `CLAUDE.md`).
- One directory per provider and stage: `.pskit/<provider>-<stage>/` with its own state (`docs/architecture.md#deploy-pipeline`).
- Binary: `terraform` or `tofu` (`terraform/runner.py`). Missing binary: `docs/troubleshooting.md#installation-and-tooling`. Override: `PSKIT_TERRAFORM_BIN` or `provider.terraform.binary`.
- Remote state: `provider.state` (`docs/architecture.md#state-handling`, `docs/configuration.md`).
- `pskit tf -- ARGS` passes arguments to the binary (`docs/cli.md`).
- Custom Terraform: `examples/11-custom-terraform`.
- `pskit remove --keep-resources` keeps data resources (`core/retain.py`, `docs/studio.md`).
- On-premises uses built-in `terraform_data` and `local-exec` of `onprem_deploy.py` (`docs/providers.md#onprem-on-premises`).
- DigitalOcean deploys through `terraform_data` running `doctl serverless` (`docs/providers.md`).
- Oracle functions are container images (`func.py` / `func.js`, `func.yaml`, `Dockerfile`) (`docs/architecture.md#bundle-layout`, `docs/providers.md`).

### Docker

- On-prem `method: docker`: build locally, copy over SSH, `docker load` and `docker run` (`docs/providers.md`, `docs/architecture.md#bundle-layout`).
- One-click services are containers (`docs/resource-guides/onprem/services.md`, catalog images above).
- Clusters: Swarm needs Docker on every server; Nomad needs Docker plus the Nomad agent; k3s does not need Docker (`docs/cluster.md#how-the-functions-run-in-a-cluster`). The function image is built on the machine running deploy.
- Cluster and shared load balancers run OpenResty in container `pskit-lb` (`docs/cluster.md`, `docs/load-balancers.md`).
- Full VS Code: code-server image `codercom/code-server:4.96.4` (`docs/studio.md#full-vs-code-code-server-in-docker`, `studio/vscode.py`).
- Browser terminals use ttyd in Docker (`core/onprem_terminal.py`).
- Studio itself in a container: example `docker run` in `docs/studio.md#full-vs-code-code-server-in-docker` (`PSKIT_STUDIO_HOST_ROOT`, Docker socket).
- Oracle function images (`docs/providers.md`).

## 1h. Everything else

- `pskit function split` moves a function into its own folder (`core/function_split.py`, `docs/placement.md`). Studio button: Own folder / Give each function its own folder.
- `pskit settings export` / `import`: encrypted bundle of `.pskit` settings (`core/settings_bundle.py`). Passphrase env `PSKIT_SETTINGS_PASSPHRASE` (`docs/cli.md#environment-variables`).
- `pskit client info|install-node|tunnel` (`docs/client.md`, `client.py`).
- Node.js / TypeScript: `docs/nodejs.md`, `examples/21-nodejs-typescript`, `packaging/node.py`, `runtime_js/`.
- Dashboard: `pskit dashboard` (`docs/dashboard.md`, `dashboard/generator.py`, `dashboard/server.py`). Separate from studio.
- Workflow executions: `pskit workflow start|executions|status|cancel` (`docs/workflow-executions.md`, `core/executions.py`).
- Scenarios: `docs/scenarios.md`.
- Migration from AWS: `docs/migrating-from-aws.md`, `examples/13-migrate-from-aws-lambda`.
- Existing cloud code: `docs/resource-guides/compatibility.md`.
- Multi-cloud overrides: `providers:` / `stages:` / `extends` (`docs/configuration.md`, `examples/08-multi-cloud`, `examples/10-stages-and-config`).
- Variables: `${env|opt|self|file}` (`config/loader.py`, `docs/configuration.md`).
- Examples (each directory with `pskit.yml` is exercised by `tests/test_examples.py`, `CLAUDE.md`):
  - `examples/01-hello-http`
  - `examples/02-rest-api`
  - `examples/03-scheduled-jobs`
  - `examples/04-queue-worker`
  - `examples/05-storage-events`
  - `examples/06-pubsub-topic`
  - `examples/07-workflow-orders`
  - `examples/08-multi-cloud`
  - `examples/09-function-invoke`
  - `examples/10-stages-and-config`
  - `examples/11-custom-terraform`
  - `examples/12-async-and-context`
  - `examples/13-migrate-from-aws-lambda`
  - `examples/14-testing`
  - `examples/15-ci-cd-deploy`
  - `examples/16-on-premises`
  - `examples/17-on-premises-remote`
  - `examples/18-resources`
  - `examples/19-custom-drivers`
  - `examples/20-onprem-external-clouds`
  - `examples/21-nodejs-typescript`
- Maintainer docs (not under `docs/`): `deploy_docs/CONTRIBUTING.md`, `deploy_docs/How_to_deploy.md`, `deploy_docs/HOW_TO_INSTALL_TERRAFORM.md`, `deploy_docs/NODE_RUNTIME.md`, `deploy_docs/PUBLISHING_TO_PYPI.md`.
- Root docs used as sources: `README.md`, `CHANGELOG.md`, `CLAUDE.md`, `CONTRIBUTING.md`, `SECURITY.md`.
- `docs/cli.md` does not mention `pskit lb`, `pskit firewall`, or `pskit function` (see conflicts.md).
- Event types: http, schedule, queue, storage, topic, smtp (`EVENT_TYPES` in schema.py, `docs/events.md`).
- Handler API: `docs/handlers.md` (`Event`, `Context`, `BatchResult`, `invoke`, `get_secret`).
- Local: `pskit dev`, `pskit invoke`, `pskit workflow run` (`docs/local-development.md`).
- Third-party providers: entry-point group `py_serverless_kit.providers` (`docs/architecture.md#third-party-providers`).

## Counts

- Leaf commands: 90
- Click groups (including root `pskit`): 13
- Click nodes in cli.json: 103
- Studio NAV pages: 13
- Studio pages including New project: 14
- Extra dialogs/panels listed: 13
- Docs files: 107 (106 Markdown)
- Docs headings: 814
- Resource guides (Markdown under docs/resource-guides): 81
- Resource type × provider cells: 77 (7 schema types × 11 providers)
- On-prem topic checklist items: 29
- On-prem catalog entries: 55
- Python modules: 142
- Examples: 21

Not verified by running (forbidden or out of scope for this pass): `deploy`, `remove`, `plan`, `tf`, cluster mutations, load-balancer mutations, `resources delete/clear`, on-prem create/remove/backup/replicas/servers mutations, firewall changes, `client tunnel` / `install-node`, `settings import`, `studio`, `dashboard`, `dev`. Those commands are described from `--help` in cli.json, docs and code only.
