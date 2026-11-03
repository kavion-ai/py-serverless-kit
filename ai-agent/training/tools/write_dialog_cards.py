"""Studio dialog cards. Labels and behavior are copied from the view files and docs."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
KNOW = ROOT / "ai-agent" / "training" / "knowledge"
CARDS = KNOW / "cards" / "page"
JSONL = KNOW / "cards.jsonl"

PAGES: list[dict] = []


def add(cid: str, title: str, tags: list[str], providers: list[str], sources: list[str], text: str) -> None:
    PAGES.append(
        {
            "id": cid,
            "kind": "page",
            "title": title,
            "tags": tags,
            "providers": providers,
            "text": text.strip() + "\n",
            "sources": sources,
        }
    )


add(
    "page-create-function-wizard",
    "Studio: Create function wizard",
    ["studio", "functions", "wizard"],
    [],
    [
        "dashboard-ui/src/studio/views/Functions.tsx",
        "docs/studio.md#what-you-can-do",
    ],
    """
# Studio: Create function wizard

How to open: Functions > + Create function

The same wizard edits an existing function. The header is "Create function", or "Edit <name>" when a function is already selected. The subtitle is "Target: <provider display name>. Triggers the provider can't run are disabled."

What it is for: Add or change one function in the draft. docs/studio.md describes four steps: basics, triggers, environment and permissions, and a review that shows a YAML diff. Applying the wizard updates the in-memory draft. The toast says "Created <name> (not saved yet)" or "Updated <name> (not saved yet)". The top bar Save writes pskit.yml.

What you see: The stepper labels are Basics, Triggers, Environment & permissions, and Review. Basics has Function name, Deploy, Description, and Handler. The handler help says it is derived from the name until you edit it. A new function starts with its own folder (`subproject` state begins true). The Dependencies toggle is "Own folder with its own <requirements.txt or package.json>". On premises, Basics also has Runs on, which writes provider.options.placement. Runtime, Memory (MB), Timeout (s), and Architecture can inherit the provider defaults. Triggers has section Add a trigger. Types the provider cannot run are listed as "Not available on <provider>", with the providers that can run them. Environment & permissions has Environment variables (hint "merged over the provider-wide ones"), Concurrency & tags, Permissions (IAM), and Provider-specific options when the provider has function fields. Review is section Changes to pskit.yml, a before/after diff, and the toggle "Create the handler stub in the code now (otherwise when you save)".

What you can do: Next moves one step. The button text is "Next: <step>". ← Back goes to the previous step and is disabled on Basics. Cancel returns to the function list. Open code is shown only while editing, and it links to the handler file. Create function or Apply changes calls `apply`. If fields are blocking, the toast is "Fix the highlighted fields first" and the review shows "Some steps have errors. Fix them before creating the function." Renaming asks "Rename <old> to <new>?" and updates workflow task states and resource bindings. A new handler stub is written with `api.ensureHandler` when the review toggle is on. If that call fails, the stub is queued and the toast says it will be created on save.

Tips and limits: Suggested Python handlers look like `functions.<name>.handler.main`. Node handlers look like `functions.<name>.index.main`. Disabled functions stay in pskit.yml. The Deploy help for a new function says "Off: kept in pskit.yml but never deployed."

Sources: `dashboard-ui/src/studio/views/Functions.tsx`, `docs/studio.md#what-you-can-do`
""",
)

add(
    "page-create-service",
    "Studio: Create service",
    ["studio", "onprem", "services"],
    ["onprem"],
    [
        "dashboard-ui/src/studio/components/OnPremServices.tsx",
        "dashboard-ui/src/studio/views/Resources.tsx",
        "docs/studio.md#project-environment-trigger-resources-and-remove",
    ],
    """
# Studio: Create service

How to open: Resources > + On-prem service

The + Create service button on the On-prem services panel opens the same drawer. Resources > + SMTP server

That button opens the drawer with the smtp type. Both resource buttons are disabled when the provider is not onprem.

What it is for: Start a catalog service with Docker, or install a runtime, and add a service to the draft. The drawer title is "Create a service" until you pick a card, then "Create <label>".

What you see: Catalog groups in the component are Queues & streams, Redis-compatible (cache, queue, stream), Object storage, Databases, Mail (receive e-mail, run functions), Secret managers, AWS emulators, Monitoring & tracing, Identity & search, Automation, web & tools, and three "Install on a server" groups (languages and Docker, web servers, process managers and tools). Each card shows the label, notes or image, the port, and a web UI line when the catalog entry has one. After you pick a service: Resource key (help says handlers use resource("key")), Use as when the entry has more than one role. The labels in the file are Queue, Stream (consumer group), Cache, Database, Bucket, Service, Secret manager, and SMTP server (mail trigger). Where follows. Where is This machine (disabled for a runtime), One SSH server, or Scaling cluster. Scaling cluster is hidden for a database, because that role uses the Scaling control, unless the service is already on a cluster. It is disabled when no cluster exists. A database also has Scaling: Single server, or Primary + read replicas when that service supports replicas. Port, and a Security box. SMTP adds Domains. The placeholder is inbound.example.com. The domains help says mail for other domains is refused, so it is never an open relay.

What you can do: Create, or Install for a runtime, calls `api.onpremCreate`. The label is Creating… while the job runs and Created when it succeeds. An empty password is generated. The password help says it is stored only in the env file and .pskit/, never in pskit.yml. Generate fills a password. The service user help says the default is the catalog `default_user`, or the string pskit. Pick another returns to the catalog. A new SSH connection has Host, User, SSH port, Log in with (Key file, SSH agent / default key, or Password), and Use sudo. This card does not copy the host or user placeholders from the form.

Tips and limits: This machine help says functions deployed elsewhere cannot reach 127.0.0.1, and to use an SSH server for them. The Server in the cluster help says Auto picks the reachable server with the most free memory that is under every capacity limit, when the job starts. docs/studio.md says a ready service can add the resource, provider.options.env_file, and triggers on the functions you ticked.

Sources: `dashboard-ui/src/studio/components/OnPremServices.tsx`, `dashboard-ui/src/studio/views/Resources.tsx`, `docs/studio.md#project-environment-trigger-resources-and-remove`
""",
)

add(
    "page-create-cluster",
    "Studio: Create cluster",
    ["studio", "cluster", "onprem"],
    ["onprem"],
    [
        "dashboard-ui/src/studio/views/Cluster.tsx",
        "src/py_serverless_kit/studio/server.py",
        "docs/studio.md#what-you-can-do",
    ],
    """
# Studio: Create cluster

How to open: Scaling cluster > + New cluster

The button is also on the empty state "No cluster yet".

What it is for: Install Docker Swarm, Kubernetes (k3s), or HashiCorp Nomad on a saved master server. The drawer title is "New scaling cluster". The studio posts to the cluster create endpoint, which calls `create_cluster`. The server requires orchestrator to be swarm, kubernetes, or nomad.

What you see: Cluster name. The field lowercases what you type. The initial value is prod, or prod-2, prod-3, and so on when that name is already used. The error text is "lowercase letter first; lowercase letters, digits and -", and "already used" when the name is taken. Help says you refer to it with `pskit deploy --cluster <name>` and with provider.options.cluster. Orchestrator is a segmented control of the orchestrators the API returned. Its help includes that orchestrator's summary and the ports to open between servers. Master server is required. Its help says it runs the control plane and the main replica (schedules, queues, logs, data), and needs root or passwordless sudo. Servers already in a cluster, and a cluster's load-balancer server, are excluded (`inCluster`). Cluster address is optional. The help says it is the master's IP the other servers reach, for example its private IP, and the default is its SSH host. Master serves requests is a toggle labeled "Send requests to the master too, not only to the joined servers". The code comment says Nomad keeps the master as a backup, and Swarm and k3s send it requests. The initial value follows that: on unless the orchestrator is nomad.

What you can do: Create starts the job. The button says Installing… while it runs. When the job succeeds, the drawer calls `onCreated` with the name. You can add a server from the master picker without leaving the drawer. The empty-state steps say to use Use for this project, set replicas, then deploy. Join more servers any time from Scaling cluster > + Join server

```
pskit deploy --cluster prod
```

Tips and limits: If the top-bar provider is not onprem, the page warns that clusters run on-prem functions and links to Overview. Create does not deploy the project's functions. The name you type is the cluster name, not the top-bar stage.

Sources: `dashboard-ui/src/studio/views/Cluster.tsx`, `src/py_serverless_kit/studio/server.py`, `docs/studio.md#what-you-can-do`
""",
)

add(
    "page-join-server",
    "Studio: Join server",
    ["studio", "cluster", "onprem"],
    ["onprem"],
    [
        "dashboard-ui/src/studio/views/Cluster.tsx",
        "src/py_serverless_kit/studio/server.py",
        "src/py_serverless_kit/cli/main.py",
    ],
    """
# Studio: Join server

How to open: Scaling cluster > + Join server

The drawer opens only when a cluster is selected. The title is "Join a server to <cluster name>".

What it is for: Add one saved server to a cluster that already exists. The drawer text says pskit installs the cluster's orchestrator on the server over SSH, joins it to the master, and copies the deployed function images to it. Running functions keep running. New replicas can start there right away.

What you see: Server, required. The picker excludes servers that are already nodes of any cluster and servers that are a cluster load balancer (`inCluster` in Cluster.tsx). The same picker can save a new server. Cluster address is optional. The help says it is this server's IP in the cluster network, and the default is its SSH host. This card does not copy the address placeholder from the source file.

What you can do: Join is disabled until a server is chosen. It starts the studio job action join with that server and the optional address. The studio server calls `join_server` for that action. The CLI command that calls the same function is `pskit cluster join`. Removing a joined server is a different control. Its confirm title is "Remove <server> from <cluster>?" and the confirm label is "Remove server". The body says replicas move to the other servers first, then its agent stops, and the saved server is kept. That job action is leave, which calls `leave_server`. The master row does not use leave. Its Remove uninstalls the orchestrator from the master and every joined server.

Tips and limits: Join does not change provider.options.cluster. The page subtitle says you can join servers while functions run. A server that is already a member of this or another cluster is not offered. Refresh loads cluster status. That status includes each server's CPU, memory, and disk.

Sources: `dashboard-ui/src/studio/views/Cluster.tsx`, `src/py_serverless_kit/studio/server.py`, `src/py_serverless_kit/cli/main.py`
""",
)

add(
    "page-servers",
    "Studio: Servers",
    ["studio", "onprem", "servers"],
    ["onprem"],
    [
        "dashboard-ui/src/studio/components/OnPremMachines.tsx",
        "docs/studio.md#project-environment-trigger-resources-and-remove",
    ],
    """
# Studio: Servers

How to open: The Servers panel is on the On-prem services area opened from Resources. The cluster empty state links to Resources, then On-prem services, then Servers. The panel heading is Servers.

What it is for: Save each SSH machine once, then reuse it for services, installs, a shell, a terminal, or a deploy. The intro says you deploy with `pskit deploy --server NAME` or Deploy, then Machine.

What you see: Re-check (Checking… while the first reachability probe runs). Its title is "Probe every server's SSH port again". + Add server opens a drawer titled "Add a server", or "Edit server <name>" when editing. The button is Save and test, or Saving… while the request runs. Fields: Name (error "start with a letter; letters, digits, _ . -", or "already saved"), Host (error "host name or IP"), User, SSH port, Log in with, Private key (.pem) for a key login, SSH password for a password login, Use sudo, Home path, Bind address, Data directory, and Description. Log in with is Key file (.pem), SSH agent / default key, or Password. The table columns are a reachability mark, Name, Connection, Login, and Used in. Row actions include Test, Live (title "Live CPU, RAM and disk use (every 4 s while on)"), Shell (title "Run commands on the server"), Terminal (title "A full SSH terminal in the browser (Docker)"), Install / create, Edit, and Forget.

What you can do: Save and test calls `api.onpremServerSave`. An empty user is stored as the string root. SSH port is sent as the number you set, or 22. A password login is described as saved in .pskit/ssh/ (owner-only, out of git) and used through sshpass on Linux and macOS. The password help says that on Windows you run `pskit resources onprem ssh-key` once and then use the key. Home path help says an empty value means /opt/pskit for functions and the SSH user's home for cluster files. Bind address help allows 0.0.0.0, 127.0.0.1, or one of the server's IPs, and says empty means 127.0.0.1 for functions and 0.0.0.0 for services. Forget asks "Forget server <name>?". Shell opens "Shell on <name>". Terminal opens a drawer that embeds the terminal URL.

```
pskit deploy --server app-1
```

Tips and limits: This card does not copy the host placeholder or the user placeholder from the form. Use a documentation-range address such as 192.0.2.10 and the login deploy when you need an example. Install / create opens the create-service flow with that server selected.

Sources: `dashboard-ui/src/studio/components/OnPremMachines.tsx`, `docs/studio.md#project-environment-trigger-resources-and-remove`
""",
)

add(
    "page-browse-account",
    "Studio: Browse account",
    ["studio", "resources", "discover"],
    [],
    [
        "dashboard-ui/src/studio/components/Misc.tsx",
        "docs/studio.md#browse-account",
    ],
    """
# Studio: Browse account

How to open: The resource form and the queue, storage, and topic trigger forms open this picker. The component comment in Misc.tsx calls it "Browse account". The modal title is "Existing <noun> in <provider>", and the region is appended in parentheses when the caller passed one. The noun is "buckets" for storage and "<kind>s" otherwise.

What it is for: Pick a queue, bucket, topic, or workflow that already exists, instead of typing its name. docs/studio.md#browse-account says it runs with the credentials of the machine running studio. A missing SDK or credential shows a message, and you can still type the name.

What you see: While the request runs, the spinner is "Listing <noun>…". The component calls `api.discover(provider, kind, region)`, which the file comment says is GET /api/discover. The kind is queue, storage, topic, or workflow. If the result says listing is not supported, the empty title is "Listing isn't available here" and the body is the result reason, or "Type the name instead." A filter field placeholder is "Filter <noun>…". It matches name, id, arn, region, and detail. An empty list says "No <noun> found" and "Create one, or type a name in the form." A filter that removes every row says "No match" and "Try another filter." Each row shows the name, then the arn or id, then region and detail.

What you can do: Choosing a row calls `onPick` with that item and closes the modal. Retry on an error banner runs the request again. docs/studio.md lists what each provider can list: AWS lists SQS queues, S3 buckets, SNS topics, and Step Functions state machines, and needs `py-serverless-kit[aws]` plus AWS credentials. GCP lists Pub/Sub topics and subscriptions and Cloud Storage buckets. Azure lists storage queues and blob containers. On premises lists existing queue and bucket directories under the host's data directory. The doc says other providers are not available and you type the name.

Tips and limits: The picker does not create the cloud object. Picking one fills the form so the resource or trigger can point at it. Discover uses the studio machine's credentials, not a credential stored in the browser.

Sources: `dashboard-ui/src/studio/components/Misc.tsx`, `docs/studio.md#browse-account`
""",
)

add(
    "page-full-vscode",
    "Studio: Full VS Code",
    ["studio", "code", "docker"],
    [],
    [
        "dashboard-ui/src/studio/views/Code.tsx",
        "docs/studio.md#full-vs-code-code-server-in-docker",
    ],
    """
# Studio: Full VS Code

How to open: Code > Full VS Code

The segmented control is labeled Editor. The other choice is Built-in editor.

What it is for: Run code-server in Docker on this project and embed it. docs/studio.md says the project is mounted at /home/coder/project, the container is published on 127.0.0.1 only, and Stop removes the container while files stay in the project folder. The default image in that doc's option table is codercom/code-server:4.96.4, also set with `pskit studio --vscode-image` or PSKIT_STUDIO_VSCODE_IMAGE.

What you see: Until `api.vscode` returns, the label is "Checking Docker…". If Docker is missing, the heading is "Docker is needed for full VS Code" and the steps say to install Docker Desktop or Docker Engine, come back and press "Pull & start", and, if studio itself is in a container, mount the Docker socket and set PSKIT_STUDIO_HOST_ROOT to the project path on the host. Check again reloads the status. The built-in editor works without Docker, which that panel states. When Docker is available, badges show the Docker version, running or stopped, and "image not pulled yet" when the image is absent. Fields are image, Python (option "image default", versions from the status or 3.13, 3.12, 3.11, 3.10, 3.9), and Node.js (option "none", or 24, 22, 20, 18 as "<version>.x"). The Python title says CPython is installed with uv python install. The Node.js title says the official Node.js build is installed in the editor container.

What you can do: The start button is "Pull & start" when the image is not present, otherwise Start. While the job runs it says Starting…. Open in new tab is shown when a URL is available. Restart with these runtimes is shown when the container is running and the Python or Node selection differs. Its title says the container is recreated and your files are kept. Stop calls `api.vscodeStop` and toasts "VS Code stopped". The running note says the container only listens on 127.0.0.1, and files saved in VS Code are the project files.

```
pskit studio --open
```

Tips and limits: docs/studio.md says the editor runs with `--auth none` because it is reachable only from this machine, and that on Linux and macOS it runs as your user so new files are not owned by root. Changing the image field is disabled while the container is running.

Sources: `dashboard-ui/src/studio/views/Code.tsx`, `docs/studio.md#full-vs-code-code-server-in-docker`
""",
)

add(
    "page-test-resource",
    "Studio: Test a resource",
    ["studio", "resources", "test"],
    [],
    [
        "dashboard-ui/src/studio/components/ResourceTester.tsx",
        "src/py_serverless_kit/studio/jobs.py",
        "docs/studio.md#project-environment-trigger-resources-and-remove",
    ],
    """
# Studio: Test a resource

How to open: Resources > Test

The Test a resource section is the same tester. The section title is "Test a resource" and the hint is "<provider> / <stage>" from the top bar.

What it is for: Send a real message or object to a queue, bucket, or topic, and show how bound functions read the resource. docs/studio.md says this works for managed resources after deploy and for external ones right away. Database, cache, and custom resources show the PSKIT_RESOURCE_* variables and a Python or Node.js snippet.

What you see: If the saved pskit.yml has no resources, the text says to add one and save, and that triggers which create their own queue or bucket can be tested on the Test page. The Resource select shows "<key> · <type> <name>" plus "(external)" or "(managed)". Used by lists functions bound to it. The help says they get its PSKIT_RESOURCE_* variables. Test connection is a button (Checking… while it runs). Its help says it is checked from `item.check.where` and shows a terminal command. A sendable resource has Object for storage, or Message otherwise, Reset to sample, and a primary button whose label is `item.action`. How to test is In the studio, Terminal, or "<provider> console" (the console tab is disabled when there are no console steps). Use it in a handler has a Language control and Python handler and Node.js handler fields.

What you can do: The send button asks "<action> to <name>?" with confirm label Send. The body says this is real: an object is uploaded or a message is delivered, and names bound functions that have a trigger. Confirm starts the studio job resource-send. In jobs.py that command is `pskit resources send`. The button is disabled when `item.remote.supported` is false, and the reason is shown. The in-studio steps say external resources work without deploying and managed resources exist after Deploy. The terminal tab includes the lines the UI builds:

```
pskit resources send --list
pskit logs -f
```

Tips and limits: The confirm is the studio's confirm dialog, not a typed production confirmation. Sending uses the top-bar provider and stage. Unsaved resources are not in this list until you save. The Test page is a different screen: it invokes a function, while this section sends to the resource.

Sources: `dashboard-ui/src/studio/components/ResourceTester.tsx`, `src/py_serverless_kit/studio/jobs.py`, `docs/studio.md#project-environment-trigger-resources-and-remove`
""",
)

add(
    "page-how-to-use",
    "Studio: How to use",
    ["studio", "resources", "usage"],
    [],
    [
        "dashboard-ui/src/studio/views/Resources.tsx",
        "dashboard-ui/src/studio/components/OnPremServices.tsx",
        "docs/studio.md#project-environment-trigger-resources-and-remove",
    ],
    """
# Studio: How to use

How to open: Resources > How to use

The button title is "Libraries, pskit.yml, Python / Node.js code and tests". The drawer title is "How to use <key>".

What it is for: Show the end-to-end guide for that resource at the top-bar provider and stage. The component loads `api.resourceUsage`, which returns markdown. docs/studio.md says the guide includes the library to install for Python and Node.js, how pskit packages it, the pskit.yml and trigger, handler code, local tests (`pskit invoke`, `pskit dev`), deployed tests, and provider notes.

What you see: The intro says the guide is for "<provider> / <stage>, from the saved pskit.yml". If the draft is dirty it adds "you have unsaved changes: save to include them". Copy guide copies `doc.markdown`. Test it closes toward the resource test. The same intro prints the terminal command with the resource key and the top-bar provider and stage. A matching command from the CLI help is:

```
pskit resources usage orders-db -p onprem -s dev
```

What you can do: Read the rendered markdown in the drawer. Copy it. Jump to Test it to send a message or object, for types that support that. An on-prem service has a second drawer with the same title pattern, "How to use <service key>", implemented by `ServiceUsageDrawer`. That one calls `api.onpremUsage` and has a toggle "Show passwords and URLs". Its terminal line is `pskit resources onprem usage <key>`. The flag that shows passwords in the CLI guide is `--reveal`.

```
pskit resources onprem usage inbound-mail --reveal
```

Tips and limits: The resource guide is generated from the saved pskit.yml, so a new resource appears after Save. The on-prem service guide can reveal passwords and URLs. Leave that toggle off when someone else can see the screen. DNS guide on an smtp row opens the service usage drawer for that key. The record values themselves are described in docs/smtp/README.md.

Sources: `dashboard-ui/src/studio/views/Resources.tsx`, `dashboard-ui/src/studio/components/OnPremServices.tsx`, `docs/studio.md#project-environment-trigger-resources-and-remove`
""",
)

add(
    "page-settings-transfer",
    "Studio: Import / export settings",
    ["studio", "settings"],
    [],
    [
        "dashboard-ui/src/studio/views/Setup.tsx",
        "dashboard-ui/src/studio/App.tsx",
        "src/py_serverless_kit/cli/main.py",
    ],
    """
# Studio: Import / export settings

How to open: The top bar button ⇅ Settings opens a drawer titled "Import / export settings and config". The same form is section "Move settings to another machine" on Setup & credentials. The section hint is "export / import .pskit, encrypted".

What it is for: Copy saved servers, clusters, load balancers, on-prem services, and SSH logins to another machine. The section text says .pskit stays out of git, so a fresh clone has none of those. The file holds secrets: SSH passwords and keys (including those in ~/.ssh), service passwords and tokens, admin tokens, and env files named in pskit.yml. It is encrypted with your passphrase. The text says to send the passphrase another way. Terraform state is not included.

What you see: Export has Passphrase, Again, the toggle "Include pskit.yml (functions, resources, providers)", and Export settings (Exporting… while it runs). The passphrase must be at least 8 characters (`MIN_PASSPHRASE` in Setup.tsx). A shorter value shows "at least 8 characters". Again shows "does not match" when it differs. Import has Settings file (accepts .pskit-settings and .json), Passphrase, and Preview (Checking… while the preview runs). The replace toggle label is "Replace: remove saved servers, clusters and services that are not in the file (default: merge, the file's entries win)". After Preview, a table has columns Settings, Added, Replaced, and either Removed or Kept. Import into this project runs the import. The CLI names in the section text are `pskit settings export` and `pskit settings import`.

What you can do: Export downloads the encrypted file after both passphrase fields match. Preview shows what would change and does not write yet. Import into this project writes the planned changes. If one of the written paths is pskit.yml, the page reloads so the imported project replaces the old draft. In `src/py_serverless_kit/cli/main.py`, `pskit settings import` calls `click.confirm` with a prompt that starts "Import into ".

Tips and limits: Merge is the default. Replace removes saved servers, clusters, and services that are not in the file. The section text says the file is always encrypted with the passphrase, and to send the passphrase another way. Do not put the passphrase in pskit.yml.

Sources: `dashboard-ui/src/studio/views/Setup.tsx`, `dashboard-ui/src/studio/App.tsx`, `src/py_serverless_kit/cli/main.py`
""",
)

add(
    "page-new-load-balancer",
    "Studio: New load balancer",
    ["studio", "load-balancer", "onprem"],
    ["onprem"],
    [
        "dashboard-ui/src/studio/views/LoadBalancers.tsx",
        "src/py_serverless_kit/studio/server.py",
        "docs/load-balancers.md",
    ],
    """
# Studio: New load balancer

How to open: Load balancers > + Create load balancer

The drawer title is "New load balancer".

What it is for: Install OpenResty on one saved server over SSH and give projects and clusters a path on one URL. The drawer text says pskit installs Docker on the server over SSH and runs OpenResty there. The server must not be part of a cluster, and it must reach the functions' port on every server behind it. Users call `http://ADDRESS/PATH/`, with a port in the URL when the port is not 80.

What you see: Name, lowercased as you type. Placeholder edge. The error text is "lowercase letter first; lowercase letters, digits and - (up to 31)", and "already used" when the name is taken. Help says projects refer to it as provider.options.balancer and with `pskit lb status <name>`. Server is required. Help says a saved server outside every cluster, not used by another load balancer, with root or passwordless sudo. Port, help "80: http://its-address/". Address in the URL is optional. Help says it is the IP or name users reach it at, and the default is its SSH host. How it spreads requests uses `AlgorithmPicker` with `state.algorithms` and `state.default_algorithm`. Help says you can change it later with Update, and a project can pick another algorithm for its own route. Weights appear when the algorithm uses them. Attach clusters now is shown when the account has clusters. Help says every deployment on them gets /<service>/ on this load balancer. A cluster that contains the chosen server is marked "(contains this server)".

What you can do: Create is disabled until name, server, and port are set and weights are valid. The label is Installing… while the job runs. The studio create handler calls `create_balancer`, then `attach_cluster` for each cluster you ticked. Those are the same functions `pskit lb create` and `pskit lb attach` use. The algorithm ids listed by the product are the ones `pskit lb algorithms` prints.

```
pskit lb status edge
```

Tips and limits: Create installs the balancer. It does not deploy functions. Forget, on an existing balancer, only stops this project managing it. Remove stops the process. The address field's placeholder in the source is a private address. Use a documentation-range address such as 192.0.2.10 if you need an example.

Sources: `dashboard-ui/src/studio/views/LoadBalancers.tsx`, `src/py_serverless_kit/studio/server.py`, `docs/load-balancers.md`
""",
)

add(
    "page-smtp-dns",
    "Studio: SMTP DNS guide",
    ["studio", "smtp", "onprem", "dns"],
    ["onprem"],
    [
        "dashboard-ui/src/studio/views/Resources.tsx",
        "dashboard-ui/src/studio/components/OnPremServices.tsx",
        "docs/smtp/README.md#dns-records-at-your-domain-provider",
        "docs/smtp/README.md#create-it",
    ],
    """
# Studio: SMTP DNS guide

How to open: Resources > DNS guide

Use it on an smtp resource row whose key matches an on-prem service. The button title is "DNS records to add at your domain provider (A, MX), the port, and the mail fields handlers get". On the On-prem services list, an smtp service's guide button is also labeled DNS guide. Both open `ServiceUsageDrawer` for that key. The drawer title is "How to use <key>".

What it is for: Show the DNS records that let other mail servers find this SMTP server. docs/smtp/README.md says you add two records, an A and an MX, at the domain provider, and that the DNS guide lists them with your values. The drawer body is markdown from `api.onpremUsage`. Copy guide copies that markdown. Show passwords and URLs is the same toggle as the other service usage drawer.

What you see: The doc's example table, for the domain inbound.example.com, is an A record whose name is mail.inbound.example.com and whose value is the server's public IP, and an MX record whose name is inbound.example.com and whose value is `10 mail.inbound.example.com`. The doc says the A record is the mail server's address, and the MX sends mail for addresses at that domain to it. Most providers want only the part before the root domain in the name field. The priority in the example is 10. Cloudflare should set the A record to DNS only, because the proxy does not carry mail. An optional TXT record in the doc is `v=spf1 -all` on a subdomain that only receives mail.

What you can do: Create the server first with
Resources > + SMTP server

The doc's create table lists Resource key, Domains, Where, Port 25, Trigger functions, and Advanced (pskit host URL and Largest mail in MB, default 25). The domains field help in the create drawer says mail for any other domain is refused, so the server is never an open relay. After DNS is published, the doc says to check with nslookup for the MX and for the mail host. Changes can take minutes or hours.

```
pskit resources onprem usage inbound-mail
```

Tips and limits: The doc says to use a subdomain such as inbound.example.com when the root domain already receives mail (Microsoft 365 or Google Workspace). Changing the root domain's MX would stop existing mailboxes receiving mail. Port 25 is what other mail servers connect to. The create form says to keep 25 unless something else uses it, and then to forward 25 to the port you chose.

Sources: `dashboard-ui/src/studio/views/Resources.tsx`, `dashboard-ui/src/studio/components/OnPremServices.tsx`, `docs/smtp/README.md#dns-records-at-your-domain-provider`, `docs/smtp/README.md#create-it`
""",
)

add(
    "page-token-screen",
    "Studio: session token screen",
    ["studio", "security"],
    [],
    [
        "dashboard-ui/src/studio/App.tsx",
        "docs/studio.md#security",
    ],
    """
# Studio: session token screen

How to open: This screen replaces the studio when the first project request fails with HTTP 401. `App.tsx` checks `error instanceof ApiError && error.status === 401` and renders `TokenScreen`. It is not a left-navigation item. A different error shows an error banner with retry. While meta or project is still loading, the label is "Loading project…". A folder with no pskit.yml shows the New project screen instead.

What it is for: The studio API refuses calls that do not carry the session token. docs/studio.md#security says every API call needs the session token from the printed URL, a new token is generated each time studio starts, and anyone with that URL has full access. The heading on the screen is "This studio session needs its link".

What you see: The paragraph says pskit studio only answers requests that carry the session token from the link it printed when it started. It tells you to open that link again, or restart. The only command on the screen is:

```
pskit studio --open
```

A smaller line says the token lives only in this browser tab and is never written to disk. There is no passphrase field and no token input on this screen.

What you can do: Open the URL that the `pskit studio` process printed, including the token fragment, in this browser. Or stop the process and start it again so it prints a new URL. `--open` asks the CLI to open the browser. The doc's option table says `--host` defaults to 127.0.0.1, `--port` defaults to 8770, and `--open` defaults to off. Binding to something other than loopback prints a warning, because studio can edit files and deploy.

Tips and limits: Refreshing a tab that never received the token stays on this screen. The token is not in pskit.yml and not in .pskit. docs/studio.md#security also says requests with a foreign Host header or a cross-site Origin are refused, and bodies are capped at 2 MiB. Deploy commands from studio run as `python -m py_serverless_kit` with explicit arguments, never through a shell. Sharing the printed URL shares the session.

Sources: `dashboard-ui/src/studio/App.tsx`, `docs/studio.md#security`
""",
)


def words(text: str) -> int:
    return len(re.findall(r"\S+", text))


def main() -> None:
    CARDS.mkdir(parents=True, exist_ok=True)
    rows = []
    if JSONL.is_file():
        for line in JSONL.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    by_id = {row["id"]: row for row in rows}
    for page in PAGES:
        n = words(page["text"])
        print(f"{page['id']} {n}")
        if n < 150 or n > 500:
            raise SystemExit(f"{page['id']} has {n} words")
        path = CARDS / f"{page['id']}.md"
        path.write_bytes(page["text"].encode("utf-8"))
        by_id[page["id"]] = page
    ordered = [by_id[key] for key in sorted(by_id)]
    payload = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in ordered)
    JSONL.write_bytes(payload.encode("utf-8"))
    print(f"jsonl={len(ordered)} dialogs={len(PAGES)}")


if __name__ == "__main__":
    main()
