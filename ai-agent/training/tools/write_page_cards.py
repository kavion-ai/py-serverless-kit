"""Write the first studio page cards. Facts are taken from the view files and docs/studio.md."""

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
    "page-new-project",
    "Studio: New project",
    ["studio", "new-project", "init"],
    [],
    [
        "dashboard-ui/src/studio/views/NewProject.tsx",
        "dashboard-ui/src/studio/App.tsx",
        "src/py_serverless_kit/studio/project.py",
        "src/py_serverless_kit/cli/main.py",
        "docs/studio.md#what-you-can-do",
    ],
    """
# Studio: New project

How to open: This screen replaces the studio shell when the folder has no pskit.yml. It is not in the left navigation. `App.tsx` renders `NewProject` in that case. docs/studio.md says the page appears when the folder has no pskit.yml.

What it is for: Scaffold a project. The heading is "Create a pskit project". The intro says there is no pskit.yml in this folder yet, and that you pick a name, a cloud and a starting point.

What you see:
- Service name. Help text: 2–32 characters, lowercase letters, digits and dashes, used to name every cloud resource. The error text says the name must start with a letter. The field lowercases what you type. The initial value in the component is my-service.
- Provider, shown as provider cards from `meta.providers`.
- Language: Python, JavaScript, TypeScript. JavaScript and TypeScript are disabled when the selected provider has no Node runtimes. The disabled title is "This provider runs Python only in pskit". Help text says Python handlers live in app/*.py, JavaScript in src/*.js, and TypeScript in src/*.ts compiled with tsc when packaging.
- Template: HTTP API ("One HTTP function. The smallest start."), Events ("HTTP plus schedule, queue, storage and topic examples."), Workflow ("HTTP plus a small step-function workflow."), Everything ("All of the above.").

What you can do: Create project calls `api.init`. While that runs the label is Creating…. The studio endpoint is POST project/init, handled by `init_project` in `src/py_serverless_kit/studio/project.py`. That function checks the service name with `[a-z][a-z0-9-]{1,31}`, checks the provider is one of `PROVIDERS`, and checks the template is http, events, workflow or full. It then calls `render` from `cli/templates.py`. `pskit init` calls that same `render`. Studio sets the Python runtime string to python3.12. For JavaScript or TypeScript it uses the provider's `default_runtime_for("node")`. If a pskit.yml already exists, the API returns 409 and the UI asks "Files already exist" with confirm label Overwrite, then calls init again with force.

Tips and limits: Overwrite is only offered after that 409. The screen does not show the top bar. After a project exists, the left navigation is Overview & provider, Setup & credentials, Functions, Workflows, Resources, Scaling cluster, Load balancers, Network map, Code, Test, Deploy, Logs, YAML.

Sources: `dashboard-ui/src/studio/views/NewProject.tsx`, `dashboard-ui/src/studio/App.tsx`, `src/py_serverless_kit/studio/project.py`, `src/py_serverless_kit/cli/main.py`, `docs/studio.md#what-you-can-do`
""",
)

add(
    "page-top-bar",
    "Studio: top bar",
    ["studio", "save", "stage", "provider"],
    [],
    [
        "dashboard-ui/src/studio/App.tsx",
        "docs/studio.md#what-you-can-do",
        "docs/studio.md#saving-what-changes-in-pskityml",
        "docs/studio.md#security",
    ],
    """
# Studio: top bar

How to open: The top bar is part of the studio shell in `App.tsx`. It is shown after a project exists. It is not a left-navigation item.

What it is for: Choose the provider and stage that validation and deploy use, save pskit.yml, undo edits, and open settings. docs/studio.md says every edit goes into an in-memory draft and is validated as you type, with the same checks as `pskit validate`, for the provider and stage picked in the top bar. Nothing touches disk until Save.

What you see:
- The brand shows the service name and the subtitle pskit studio. The brand link goes to Overview & provider.
- The label "validate & deploy as" is a provider select (aria-label Target provider). Options are `meta.providers` display names.
- The stage input (aria-label Stage) lowercases the text, keeps only `[a-z0-9-]`, and slices it to 16 characters.
- Undo (title "Undo (Ctrl+Z)"), Redo (title "Redo (Ctrl+Shift+Z)").
- A Problems button (title Problems) shows the error count and the warning count.
- Validate (title Validate now) calls `studio.validateNow`.
- The save button title is "Save pskit.yml (Ctrl+S)". Its label is Saving…, Save, or Saved.
- ⇅ Settings opens a drawer titled "Import / export settings and config".
- Theme toggle, aria-label Toggle theme.
- On a narrow window, Menu (aria-label Menu) opens the navigation.

What you can do: Ctrl or Cmd+S saves, except when the current page is Code. Ctrl or Cmd+Z undoes, and with Shift it redoes. Ctrl or Cmd+Y also redoes. Those undo and redo keys are ignored while focus is in an editable field (`isEditable`). The Problems panel can be closed with Close problems. A conflict modal titled "pskit.yml changed on disk" offers Cancel, Reload (discard my changes), and Overwrite. Overwrite calls save with force. The modal text says a backup of the file on disk is kept in `.pskit/studio/backups/`.

Tips and limits: If the HTTP API returns 401, the shell is replaced by a screen titled "This studio session needs its link". That screen shows:

```
pskit studio --open
```

The screen says the token lives only in this browser tab and is never written to disk. docs/studio.md#security says studio binds to 127.0.0.1 by default and that every API call needs the session token from the printed URL.

Sources: `dashboard-ui/src/studio/App.tsx`, `docs/studio.md#what-you-can-do`, `docs/studio.md#saving-what-changes-in-pskityml`, `docs/studio.md#security`
""",
)

add(
    "page-overview",
    "Studio: Overview & provider",
    ["studio", "overview", "provider"],
    [],
    [
        "dashboard-ui/src/studio/views/Overview.tsx",
        "dashboard-ui/src/studio/App.tsx",
        "docs/studio.md#what-you-can-do",
    ],
    """
# Studio: Overview & provider

How to open: Left navigation label Overview & provider. The brand in the top bar links to the same view.

What it is for: The page subtitle says "Service-wide settings. Every function inherits these unless it overrides them." docs/studio.md says this page picks the provider from cards that show what each supports (HTTP, schedule, queue, storage, topic, native workflows). Switching first lists the triggers that would stop working.

What you see: Section Service (Service name, and the button Use the values shown here). Section Provider. Section Defaults for every function: Region, Stage (help "dev, staging, prod… (lowercase, ≤ 16)"), Runtime, Memory (MB) with help "64–32768", Timeout (s), Architecture, Log retention (days). Section Environment variables, hint "available to every function". Section Tags, with Add tag. A section titled with the provider display name plus "options", hint provider.options. Section Packaging, hint package. Section On-premises deployment, hint provider.options.deploy: Saved server (an option "None: use the method below"), and Deploy method. The deploy-method help says local is "This machine.", ssh is "A server reached over SSH (scp + process or systemd).", and docker is "A Docker container, locally or on a server over SSH." Section Built-in services, hint provider.options.services. Section Host tuning, hint "logs, executions, concurrency".

What you can do: Use the values shown here calls `absorbShadows` on the draft. The nearby copy says current provider options move under `providers.<name>` so switching back restores them. Test SSH connection is shown in the on-premises deployment section. Its title is `ssh <user>@<host> echo pskit-ok` when a host is set, and "Set the SSH host first" when it is not. The code default for the user in that title is the string pskit. A missing ssh, scp or Docker note links to Setup & credentials.

Tips and limits: The Stage field on this page is separate from the top-bar stage input. docs/studio.md says the top bar is what validate and deploy use. Memory help text on the form is 64–32768. Timeout help includes the provider's `max_timeout` when a provider is selected.

Sources: `dashboard-ui/src/studio/views/Overview.tsx`, `dashboard-ui/src/studio/App.tsx`, `docs/studio.md#what-you-can-do`
""",
)

add(
    "page-setup",
    "Studio: Setup & credentials",
    ["studio", "setup", "doctor"],
    [],
    [
        "dashboard-ui/src/studio/views/Setup.tsx",
        "docs/studio.md#setup-logs-and-provider-differences",
        "docs/studio.md#project-environment-trigger-resources-and-remove",
    ],
    """
# Studio: Setup & credentials

How to open: Left navigation label Setup & credentials. The top bar button ⇅ Settings opens the same transfer form in a drawer, not this whole page.

What it is for: docs/studio.md says this page runs the same checks as `pskit doctor` for the provider in the top bar: Terraform, the cloud CLI, credentials, required provider options and, for on premises, ssh, scp, Docker and the key file. Each problem shows the download link and the steps for Windows, macOS or Linux.

What you see: A Check again button (Checking… while it loads). Section Checks. Section "Move settings to another machine", hint "export / import .pskit, encrypted", with Export settings (Exporting… while busy). Section "AWS credentials (aws configure)", hint "~/.aws/credentials". Section Environment variables, hint "read by Terraform and the provider". Section On-premises connection, hint provider.options.deploy. Section Project environment. Its hint is "npm install" for a Node project and ".venv + requirements" otherwise.

What you can do: Check again re-runs the doctor-style checks. docs/studio.md says you can save an AWS access key as a profile in ~/.aws, set provider variables such as ARM_SUBSCRIPTION_ID or CLOUDFLARE_API_TOKEN for this studio session only (secret values are never sent back to the browser), start a browser login (`az login`, `gcloud auth application-default login`, `aws sso login`), and test the SSH connection of an on-prem deploy. Export settings matches `pskit settings export`. The import button label is "Import into this project", which matches `pskit settings import`. Under Project environment the button is "Create .venv and install", or "Install requirements" when a venv already exists and recreate is off. The Node row says "npm install", and the help says npm ci when package-lock.json exists, else npm install.

Tips and limits: Session environment values are for Terraform and the provider during this studio process. docs/studio.md says secret values are not sent back to the browser. The private-key Browse… control, described in that same section, lists names and sizes under the machine running studio and starts in ~/.ssh. File contents are not read.

Sources: `dashboard-ui/src/studio/views/Setup.tsx`, `docs/studio.md#setup-logs-and-provider-differences`, `docs/studio.md#project-environment-trigger-resources-and-remove`
""",
)

add(
    "page-functions",
    "Studio: Functions",
    ["studio", "functions", "wizard"],
    [],
    [
        "dashboard-ui/src/studio/views/Functions.tsx",
        "docs/studio.md#what-you-can-do",
    ],
    """
# Studio: Functions

How to open: Left navigation label Functions. A count badge on that item is the number of functions (`countFor` in App.tsx). Test and Code on a row open the Test and Code pages for that function.

What it is for: A table of functions plus the create-function flow. docs/studio.md describes a four-step Create function wizard: basics, triggers, environment and permissions, review (a YAML diff). Trigger types the selected provider cannot run are disabled, with a tooltip naming the providers that can. Creating a function writes a handler stub into the project.

What you see: The page header is the functions list. The button + Create function opens the wizard. A row action Own folder shows Moving… while a split runs. Wizard section Basics. Section Add a trigger. Section Logging, hint "log level and live logs". Section Environment variables, hint "merged over the provider-wide ones". Section Concurrency & tags, with Add tag. Section Provider-specific options, hint functions.<name>.options. Section Permissions (IAM), hint advanced. Section Changes to pskit.yml. If the route names a function that is not in the draft, the header is "Function not found".

What you can do: Own folder is the studio control for giving a function its own directory. Delete asks "Delete function <name>?" The confirm body says the function and its triggers are removed from pskit.yml and the handler code is not deleted. The toast after confirm says the delete is not saved yet, because the change is in the draft until the top bar saves. The matching CLI for Own folder is:

```
pskit function split
```

The wizard review shows the YAML diff before the function is written into the draft. docs/studio.md says HTTP has a path-parameter preview, CORS and auth, and schedule has rate presets and a cron editor with a plain-English preview. Queue, storage and topic can be new, a resource from the Resources page, Browse account, or a typed name. Delete on a workflow is a different page. On this page, deleting a function removes it from the draft. Save in the top bar writes pskit.yml.

Tips and limits: Provider-specific options and IAM statements are per function. Environment variables here are merged over the provider-wide ones from Overview & provider. Disabled trigger types stay visible with the reason, rather than being omitted, which is what docs/studio.md describes under provider differences.

Sources: `dashboard-ui/src/studio/views/Functions.tsx`, `docs/studio.md#what-you-can-do`
""",
)

add(
    "page-workflows",
    "Studio: Workflows",
    ["studio", "workflows"],
    [],
    [
        "dashboard-ui/src/studio/views/Workflows.tsx",
        "docs/studio.md#what-you-can-do",
    ],
    """
# Studio: Workflows

How to open: Left navigation label Workflows. Opening a name in the list shows the editor for that workflow. A missing name shows the header "Workflow not found".

What it is for: docs/studio.md calls this a visual step-function builder: an auto-laid-out diagram (next, choice, default and catch edges) and a palette. The inspector edits each state. Engine (auto / native / embedded) and timeout are on the workflow.

What you see: The list has a modal titled New workflow, with Name, Cancel and Create. Each row has Delete. The confirm title is "Delete workflow <name>?" and the confirm label is Delete. After confirm, the workflow key is removed from the draft and a toast says it is not saved yet. The editor palette is aria-label "Add state". The state types in `TYPE_INFO` are task ("Call a function"), choice ("Branch on the data"), wait ("Pause for N seconds"), pass ("Pass data through / inject a value"), parallel ("Run branches at the same time"), map ("Run steps for every item in a list"), succeed ("Stop successfully") and fail ("Stop with an error"). Section Settings contains Engine and Timeout (s). The timeout help says "Whole-run limit; TIMED_OUT when exceeded." An empty diagram says "Add a state from the palette."

What you can do: Add a state from the palette. The editor text says a new state is chained after the selected one. Click a state to edit it. Task states pick a function. Choice rules use the operators from `meta.workflow.choice_operators`, or the fallback list equals, not_equals, gt, gte, lt, lte, in, contains, matches, is_null, is_present. docs/studio.md says parallel branches and map iterators open as nested workflows, and that retry and catch are edited in the inspector.

Tips and limits: Delete updates the in-memory draft only. The top-bar Save writes pskit.yml. Engine values auto, native and embedded are the ones named in docs/studio.md. The diagram layout code lives in `dashboard-ui/src/studio/views/flow.ts`, imported by this view.

Sources: `dashboard-ui/src/studio/views/Workflows.tsx`, `docs/studio.md#what-you-can-do`
""",
)

add(
    "page-resources",
    "Studio: Resources",
    ["studio", "resources"],
    [],
    [
        "dashboard-ui/src/studio/views/Resources.tsx",
        "docs/studio.md#what-you-can-do",
        "docs/studio.md#project-environment-trigger-resources-and-remove",
    ],
    """
# Studio: Resources

How to open: Left navigation label Resources.

What it is for: The page subtitle says "Buckets, queues, topics, databases and any other service your functions use, once for every cloud." docs/studio.md says the page covers managed or external buckets, queues, topics, databases, caches and custom services, connection values with secrets written as `${env:VAR}`, which functions get the binding, and Browse account.

What you see: Buttons Guides, + SMTP server, + On-prem service, and + Add resource. + SMTP server and + On-prem service are disabled when the provider is not onprem. The SMTP button title says it is an SMTP server (Node.js) that receives mail for your domain and runs functions with it. The on-prem service title says "Start Redis, Kafka, PostgreSQL, MinIO, OpenBao, ... with Docker and add it here". A row has How to use, and DNS guide for an smtp resource that matches an on-prem service. The How to use drawer title is "How to use <key>".

What you can do: + Add resource opens the resource form. Guides opens the in-studio resource guides. docs/studio.md says deleting a managed resource from the Resources table only removes it from pskit.yml, and the next deploy then deletes it in the cloud. The same chapter says Resources, then In the cloud, lists buckets, queues and topics pskit created for the top-bar provider and stage, and that deleting them there runs `pskit resources delete` behind a typed confirmation. How to use opens the end-to-end guide: library, pskit.yml, handler, local tests and deployed tests. See docs/resource-usage.md from that chapter.

Tips and limits: SMTP and one-click services are on-prem controls. The buttons stay on the page and are disabled for other providers. Connection secrets in the form are written as `${env:VAR}` and are not resolved when saved (docs/studio.md#saving-what-changes-in-pskityml). Services that exist on a host but are not in pskit.yml are listed with an Add control, as that chapter describes.

Sources: `dashboard-ui/src/studio/views/Resources.tsx`, `docs/studio.md#what-you-can-do`, `docs/studio.md#project-environment-trigger-resources-and-remove`
""",
)

add(
    "page-cluster",
    "Studio: Scaling cluster",
    ["studio", "cluster", "onprem"],
    ["onprem"],
    [
        "dashboard-ui/src/studio/views/Cluster.tsx",
        "src/py_serverless_kit/studio/server.py",
        "src/py_serverless_kit/cli/main.py",
        "src/py_serverless_kit/core/onprem_cluster.py",
        "docs/studio.md#what-you-can-do",
        "docs/cluster.md",
    ],
    """
# Studio: Scaling cluster

How to open: Left navigation label Scaling cluster.

What it is for: The page subtitle says functions can run on several servers with Docker Swarm, Kubernetes (k3s) or HashiCorp Nomad. You pick a master, join more servers, and watch CPU, memory and disk. Without a cluster, functions run on one server as before. docs/studio.md says the switch "Deploy this project's functions to …" writes `provider.options.cluster`.

What you see: The action + New cluster. If the top-bar provider is not onprem, a warning says clusters run on-prem functions and points at Overview to switch the provider to onprem. An empty state titled "No cluster yet" has three steps: save servers (Resources, On-prem services, Servers, or Add a server), + New cluster to choose the orchestrator and the master (pskit installs it over SSH), then Use for this project, set replicas, and deploy. When a cluster exists, the toolbar has Refresh (Checking… while loading), Check & alert, and Forget. Check & alert's title is "Check now and send the alert if every server is full". The servers area has + Join server. Workload rows have Scale. The scale control's title says "Until the next deploy; keep it in Web replicas above".

What you can do: + New cluster opens a drawer titled "New scaling cluster" and the studio calls `create_cluster` (the same function as `pskit cluster create`). + Join server starts the join action (`pskit cluster join`). Scale starts the scale action (`pskit cluster scale`). Check & alert posts to the cluster check endpoint, which calls `check` with the default `alert=True`. That is the same default as `pskit cluster check`. Forget asks "Forget cluster <name>?" with confirm label Forget, and the body says pskit stops managing it and leaves the servers as they are. That job calls `remove_cluster` without uninstall, which is `pskit cluster remove` without `--uninstall`. The dialog says uninstall is Remove on the master's row. That path passes uninstall, which is `pskit cluster remove --uninstall`. The page text says a server is full at the cluster capacity percentages for CPU, memory and disk.

Tips and limits: This page does not deploy the functions by itself. The empty-state steps say to deploy after Use for this project. Join is allowed while functions run, which the subtitle states. The further guide is docs/cluster.md, linked from docs/studio.md.

Sources: `dashboard-ui/src/studio/views/Cluster.tsx`, `src/py_serverless_kit/studio/server.py`, `src/py_serverless_kit/cli/main.py`, `src/py_serverless_kit/core/onprem_cluster.py`, `docs/studio.md#what-you-can-do`, `docs/cluster.md`
""",
)

add(
    "page-load-balancers",
    "Studio: Load balancers",
    ["studio", "load-balancer", "onprem"],
    ["onprem"],
    [
        "dashboard-ui/src/studio/views/LoadBalancers.tsx",
        "src/py_serverless_kit/studio/server.py",
        "src/py_serverless_kit/cli/main.py",
        "docs/load-balancers.md",
    ],
    """
# Studio: Load balancers

How to open: Left navigation label Load balancers.

What it is for: One URL in front of projects and clusters, installed over SSH. The empty-state text says + Create load balancer: name it, pick the server and how it spreads requests, and pskit installs it over SSH.

What you see: The action + Create load balancer. The create form has the label "How it spreads requests" with help "Change it any time with Update; a project can pick another one for its own route." It also has "Attach clusters now (optional)", help "Every deployment on them gets /<service>/ on this load balancer." A balancer that is in use shows Forget. The confirm title is "Forget load balancer <name>?" and the body says only this project stops managing it, it keeps running on the server, and you can add it back with + Create load balancer using the same name and server. The confirm label is Forget. A routes heading is "Routes". An attach control is + Attach cluster. The sync help says it rewrites settings on the server and reloads OpenResty without dropping requests, and that routes which chose their own algorithm keep it.

What you can do: Create calls `create_balancer` (the same function as `pskit lb create`). Update calls `update_balancer` (`pskit lb update`). Sync calls `sync_balancer` (`pskit lb sync`). Attach calls `attach_cluster` (`pskit lb attach`). Forget calls `forget_balancer` and leaves the process running (`pskit lb forget`). Remove calls `remove_balancer`, which is what `pskit lb remove` calls. The command that prints the algorithm ids is `pskit lb algorithms`. The form label for that choice is How it spreads requests.

Tips and limits: Forget and remove are different. The Forget dialog says the balancer keeps running for other projects and clusters. Algorithm choices come from the form backed by `pskit lb algorithms`. A project route can use a different algorithm from the balancer default. The help text on the form says that, and so does the sync sentence about routes that chose their own algorithm.

Sources: `dashboard-ui/src/studio/views/LoadBalancers.tsx`, `src/py_serverless_kit/studio/server.py`, `src/py_serverless_kit/cli/main.py`, `docs/load-balancers.md`
""",
)

add(
    "page-network",
    "Studio: Network map",
    ["studio", "network", "onprem"],
    ["onprem"],
    [
        "dashboard-ui/src/studio/views/Network.tsx",
        "docs/onprem-network.md",
    ],
    """
# Studio: Network map

How to open: Left navigation label Network map.

What it is for: The page subtitle says it shows every on-prem server and the connections it has to accept (inbound) and open (outbound) for this project: deploys, function groups, clusters, load balancers and services. Click a machine for its details.

What you see: A Refresh button. A toolbar of level checkboxes plus "servers not used anywhere". The legend says "inbound to the selected machine" and "outbound from it". The canvas aria-label is "Connections between the project's machines". When a machine is selected, tables are titled "Inbound — accept" and "Outbound — open". An "All machines" control clears the selection. The empty copy is: "No servers and no connections yet. Save a server under Resources → Servers, then deploy to it, create a cluster, a load balancer or a service there; this map follows."

What you can do: Refresh reloads the map. Select a machine to list inbound rules, outbound rules, and where that server is used. The page does not open ports. It describes the connections the project already implies. Changing a deploy target, a cluster, a load balancer or a service changes what the next refresh shows.

Tips and limits: The empty state points at Resources, then Servers, to save a machine first. There is no deploy button on this page. The written guide for the same picture is docs/onprem-network.md. Firewall edits, when you want to change what a host allows, are on Deploy, section Firewall, and the command `pskit firewall`.

Sources: `dashboard-ui/src/studio/views/Network.tsx`, `docs/onprem-network.md`
""",
)

add(
    "page-code",
    "Studio: Code",
    ["studio", "code", "editor"],
    [],
    [
        "dashboard-ui/src/studio/views/Code.tsx",
        "docs/studio.md#what-you-can-do",
        "docs/studio.md#full-vs-code-code-server-in-docker",
        "docs/studio.md#security",
    ],
    """
# Studio: Code

How to open: Left navigation label Code. A Code action on a function row opens this page on that file.

What it is for: The subtitle says "Edit handler code here, or open the whole project in VS Code (code-server in Docker)." docs/studio.md describes a file tree and a CodeMirror editor (Python, YAML, JSON highlighting, search, tabs, Ctrl+S), or Full VS Code.

What you see: A segmented control labeled Editor with "Built-in editor" and "Full VS Code". The built-in editor has a search field whose placeholder is "Find file…" and a button titled "New file". The Full VS Code panel includes the steps that tell you to press "Pull & start", and the buttons Open in new tab and Stop.

What you can do: Edit and save files inside the project. docs/studio.md#security says the file editor only reaches files inside the project. It never touches `.pskit/`, `.git/`, `.venv/`, `node_modules/` or `__pycache__`, and it refuses binary files or files over 1 MiB. Full VS Code checks for the Docker CLI and a running daemon, then Pull & start pulls the image if needed and starts a container. The default image in the `pskit studio` option table is `codercom/code-server:4.96.4` (`--vscode-image`, also the environment variable `PSKIT_STUDIO_VSCODE_IMAGE`). The container name pattern in the doc is `pskit-studio-<id>`, the project is mounted at `/home/coder/project`, and the publish address is 127.0.0.1 only. Stop removes the container. Files stay in the project folder.

Tips and limits: The top-bar Ctrl+S handler in App.tsx does not run when the current view is Code, so the editor handles save itself. docs/studio.md says the first start with a Python and Node selection builds an image tagged from those versions, and later starts reuse it. Changing runtimes while it is running offers Restart with these runtimes. The doc says it runs with `--auth none` because it is reachable only from this machine.

Sources: `dashboard-ui/src/studio/views/Code.tsx`, `docs/studio.md#what-you-can-do`, `docs/studio.md#full-vs-code-code-server-in-docker`, `docs/studio.md#security`
""",
)

add(
    "page-test",
    "Studio: Test",
    ["studio", "test", "invoke"],
    [],
    [
        "dashboard-ui/src/studio/views/Test.tsx",
        "docs/studio.md#test-functions",
    ],
    """
# Studio: Test

How to open: Left navigation label Test. Test on a function row opens the same page with that function selected.

What it is for: Send an event at a function. docs/studio.md#test-functions says you pick a trigger or Direct invoke, edit a payload, then run locally or send to the deployed function.

What you see: Section "1. Choose the event". Each trigger is a card. A trigger index below zero is labeled Direct invoke and "no trigger". Section "2. Edit the event". HTTP shows Request, with help "Path with query string, e.g. /items/42?verbose=1. Path parameters ({id}) need real values." Other bodies use Payload (JSON). GET and HEAD hide the payload field. Saved events help says they are kept in `.pskit/studio/test-events.json`. There is a sample chip and a Save event button. Section "3. Run it" has "▶ Run locally" (title "Runs the handler on this machine with a synthetic event") and "☁ Send to <provider> / <stage>". A toggle is labeled "Show the function's logs". Section "How to test this", hint "studio, terminal or cloud console".

What you can do: Run locally is the studio form of `pskit invoke`. Send to the provider and stage is the studio form of `pskit trigger`. The send button is disabled when `trigger.remote.supported` is false, and the title then shows `trigger.remote.reason`. docs/studio.md says a storage sample matches the trigger prefix and suffix, and a schedule sample uses the trigger's own input. How to test this shows studio steps, terminal commands (local `pskit invoke`, deployed `pskit trigger`, and the cloud CLI) with Copy, and cloud-console steps.

Tips and limits: Run locally does not deploy and does not call the cloud. Send does, and it needs a deployed function whose trigger pskit can fire. On premises, section 3 also shows a Server picker when the function is deployed. Saved events are per project file, not per cloud account.

Sources: `dashboard-ui/src/studio/views/Test.tsx`, `docs/studio.md#test-functions`
""",
)

add(
    "page-deploy",
    "Studio: Deploy",
    ["studio", "deploy"],
    [],
    [
        "dashboard-ui/src/studio/views/Deploy.tsx",
        "docs/studio.md#what-you-can-do",
        "docs/studio.md#project-environment-trigger-resources-and-remove",
    ],
    """
# Studio: Deploy

How to open: Left navigation label Deploy.

What it is for: Run validate, package, plan, deploy, info and remove, with a live log. docs/studio.md says Remove, and any stage named `prod*`, need a typed confirmation. The same page can invoke a function with a JSON payload and run a workflow locally.

What you see: Action buttons from the list in Deploy.tsx: Validate ("Check the configuration against the provider."), Package ("Build the bundle and Terraform without deploying."), Plan ("terraform plan: what would change."), Deploy ("Build and apply."), Info ("What is deployed."), Remove ("Destroy every resource of this stage."). A switch label is either "Remove also deletes buckets, queues and topics" or "Remove keeps buckets, queues and topics (and their data)". Output tabs are Steps and Raw log. Section "Where functions run", hint provider.options.placement. Section Firewall, hint "the ports each server must allow". Section "Invoke a function locally", hint `pskit invoke`. Section "Run a workflow locally", hint `pskit workflow run --history`.

What you can do: Validate, Package, Plan, Deploy, Info and Remove start studio jobs for those commands. When the switch says remove keeps buckets, queues and topics, Remove is called with `keep_resources: true`, which is `pskit remove --keep-resources`. docs/studio.md states that flag keeps the data resources and destroys functions and triggers. Invoke on this page runs the handler locally. Run a workflow locally runs the embedded engine with history.

```
pskit plan
pskit deploy
pskit remove --keep-resources
```

Tips and limits: Deploy and Remove change the selected stage. The UI asks before remove, and docs/studio.md says a stage whose name starts with prod also needs a typed confirmation. Package does not apply. Plan shows what would change. If some functions or triggers will not run on this provider, a section lists them and can disable them under `providers.<cloud>`.

Sources: `dashboard-ui/src/studio/views/Deploy.tsx`, `docs/studio.md#what-you-can-do`, `docs/studio.md#project-environment-trigger-resources-and-remove`
""",
)

add(
    "page-logs",
    "Studio: Logs",
    ["studio", "logs"],
    [],
    [
        "dashboard-ui/src/studio/views/Logs.tsx",
        "docs/studio.md#setup-logs-and-provider-differences",
    ],
    """
# Studio: Logs

How to open: Left navigation label Logs. A function's Logging section, on the function editor, sets log level and can show that function's live logs. docs/studio.md says each function's Logging section does that.

What it is for: The page header subtitle says these are logs of the functions deployed to the provider and stage in the top bar. They are read with this machine's credentials. If they cannot be read, the subtitle links to Setup & credentials. The file comment says live tail, streams, and delete.

What you see: For an on-prem deploy that is spread across a cluster or more than one group, the page shows a Source line and does not offer a single-server picker. The comment in the file says logs then come from every replica or group. Section Stored logs, hint "list, select and delete". The component passes `api.deleteLogs` for the current provider, stage, optional function and optional server.

What you can do: Read the live tail for the top-bar target. Open Stored logs, select streams, and delete the selection or all of them. docs/studio.md says list and delete are available for AWS and on-prem, and that the page shows logs for on-prem, AWS, GCP and Azure with a Log Analytics workspace. The matching CLI is:

```
pskit logs
```

Tips and limits: Changing the top-bar provider or stage changes which deployment is read. Credentials are the ones on the machine running studio, which is why a failure points at Setup & credentials. Deleting streams is a delete call, separate from `pskit remove`. Function log level is edited on the function, not on this page.

Sources: `dashboard-ui/src/studio/views/Logs.tsx`, `docs/studio.md#setup-logs-and-provider-differences`
""",
)

add(
    "page-yaml",
    "Studio: YAML",
    ["studio", "yaml", "pskit.yml"],
    [],
    [
        "dashboard-ui/src/studio/views/Yaml.tsx",
        "docs/studio.md#what-you-can-do",
        "docs/studio.md#saving-what-changes-in-pskityml",
    ],
    """
# Studio: YAML

How to open: Left navigation label YAML.

What it is for: The generated pskit.yml, a diff against the file on disk, and a raw edit mode. The page subtitle says "What Save writes. Comments in the original file are not preserved; a backup is kept in .pskit/studio/backups/."

What you see: A segmented control labeled YAML mode with Preview, Diff vs disk, and Edit raw YAML. Preview is a read-only editor, aria-label "Generated pskit.yml". Diff vs disk uses a before/after view of the file on disk and the generated text. Edit raw YAML shows the hint "Edit the YAML directly, then apply it to the draft. Forms update to match." The buttons are Apply to draft (Parsing… while busy) and Discard. Parse issues render in an IssueList. While validation has not yet produced YAML, the page shows Rendering….

What you can do: Preview and diff do not write the file. Apply to draft parses the text and replaces the in-memory draft, so the other pages match. Discard leaves edit mode and drops the edit buffer. The top-bar Save is what writes pskit.yml. docs/studio.md#saving-what-changes-in-pskityml says values keep their written form (`${env:API_KEY}`, `${self:custom.x}`, `${opt:...}` are saved as written), comments are not kept, and key order follows the studio layout. Before every save the previous file is copied to `.pskit/studio/backups/pskit.<timestamp>.yml` and the last 20 are kept. A file that uses `extends:` is shown with a notice: only the main file is edited. A config that fails validation can still be saved.

Tips and limits: Apply to draft is not Save. You can apply a draft that still has problems, then save it, which matches the doc sentence that a failing config can still be saved. If the file on disk changed after load, the top-bar conflict modal (Cancel, Reload, Overwrite) is the one that decides, as described in that same section of the doc.

Sources: `dashboard-ui/src/studio/views/Yaml.tsx`, `docs/studio.md#what-you-can-do`, `docs/studio.md#saving-what-changes-in-pskityml`
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
    print(f"jsonl={len(ordered)} pages={len(PAGES)}")


if __name__ == "__main__":
    main()
