"""Build ai-agent/training/knowledge/inventory.md from dumped CLI, docs and catalog.

Facts in the generated lists come from cli.json, docs_headings.json, facts.json
and onprem_catalog.json. Narrative sections below are limited to labels read
from dashboard-ui/src/studio and the docs cited in each bullet.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
KNOW = ROOT / "ai-agent" / "training" / "knowledge"
OUT = KNOW / "inventory.md"

PROVIDERS = [
    "aws",
    "azure",
    "gcp",
    "alibaba",
    "tencent",
    "huawei",
    "oracle",
    "ibm",
    "digitalocean",
    "cloudflare",
    "onprem",
]
TYPES = ["storage", "queue", "topic", "database", "cache", "custom", "smtp"]


def load(name: str):
    return json.loads((KNOW / name).read_text(encoding="utf-8"))


def flags(command: dict) -> str:
    parts = []
    for opt in command.get("options") or []:
        names = "/".join(opt.get("flags") or [])
        if not names:
            continue
        extra = opt.get("type") or ""
        if opt.get("is_flag"):
            extra = "flag"
        if opt.get("choices"):
            extra = "choice:" + "|".join(opt["choices"])
        default = opt.get("default")
        if default not in (None, False, "") and not opt.get("is_flag"):
            extra = f"{extra} default={default!r}" if extra else f"default={default!r}"
        parts.append(f"{names} ({extra})" if extra else names)
    return ", ".join(parts)


def args_line(command: dict) -> str:
    bits = []
    for arg in command.get("arguments") or []:
        name = arg.get("name") or "ARG"
        mark = "required" if arg.get("required") else "optional"
        bits.append(f"{name} ({arg.get('type')}, {mark})")
    return ", ".join(bits)


PAGES = [
    {
        "title": "New project",
        "nav": "none (replaces the shell when the folder has no pskit.yml)",
        "file": "dashboard-ui/src/studio/views/NewProject.tsx",
        "open": "Open studio in a folder with no pskit.yml. Not a left-nav item.",
        "purpose": "Scaffold a project. Docs: docs/studio.md#what-you-can-do.",
        "sections": [
            "Service name (2–32 lowercase letters, digits, dashes, starting with a letter)",
            "Provider (provider cards)",
            "Language: Python, JavaScript, TypeScript (JS/TS disabled when the provider has no Node runtimes)",
            "Template: HTTP API, Events, Workflow, Everything",
            "Button: Create project (Creating… while busy). Overwrite confirm if files exist.",
        ],
    },
    {
        "title": "Overview & provider",
        "nav": "Overview & provider",
        "file": "dashboard-ui/src/studio/views/Overview.tsx",
        "open": "Left navigation. The brand in the top bar also links here.",
        "purpose": "Service-wide settings every function inherits unless it overrides them. docs/studio.md.",
        "sections": [
            "Service: Service name; Use the values shown here (absorb provider overrides into the base)",
            "Provider: cards; switching lists triggers that would stop working (docs/studio.md)",
            "Defaults for every function: Region, Stage (shown; the live stage is the top-bar stage), Runtime, Memory (MB), Timeout (s), Architecture, Log retention (days)",
            "Environment variables (available to every function)",
            "Tags / Add tag",
            "<provider> options (provider.options)",
            "Packaging (package)",
            "On-premises deployment (provider.options.deploy): Saved server, Deploy method (local / ssh / docker; scp is ssh per docs/providers.md), + Add server, Test SSH connection",
            "Built-in services (provider.options.services)",
            "Host tuning (logs, executions, concurrency)",
        ],
    },
    {
        "title": "Setup & credentials",
        "nav": "Setup & credentials",
        "file": "dashboard-ui/src/studio/views/Setup.tsx",
        "open": "Left navigation.",
        "purpose": "Same checks as pskit doctor for the top-bar provider. docs/studio.md#setup-logs-and-provider-differences.",
        "sections": [
            "Provider, Operating system, Check again",
            "Checks: each row has Details or How to fix, Copy, and a Run action (download / login)",
            "Move settings to another machine: Export settings, passphrase + Again, Include pskit.yml, Preview, Import into this project. Matches pskit settings export / import. Also opened from top bar ⇅ Settings (drawer title Import / export settings and config).",
            "AWS credentials (aws configure): Profile, Access key ID, Secret access key, Default region, Session token, Save profile",
            "Environment variables: Set for this session, Clear (not written back to the browser once set; docs/studio.md)",
            "On-premises connection (provider.options.deploy), Deploy method",
            "Project environment: Create .venv and install / Install requirements, Recreate, npm install",
        ],
    },
    {
        "title": "Functions",
        "nav": "Functions",
        "file": "dashboard-ui/src/studio/views/Functions.tsx",
        "open": "Left navigation. Count badge is the number of functions.",
        "purpose": "Table of functions plus the Create function wizard. docs/studio.md.",
        "sections": [
            "Search name, handler, trigger…",
            "+ Create function; Create your first function; Give each function its own folder (pskit function split)",
            "Row: Test, Code, Own folder, Duplicate, Delete",
            "Wizard steps: Basics, Triggers, Environment & permissions, Review",
            "Basics: Function name, Deploy (enable), Description, Handler, Dependencies, Runs on, Runtime, Memory (MB), Timeout (s), Architecture",
            "Add a trigger; per-trigger skip on this provider",
            "Logging: Log level, Live logs",
            "Environment variables; Concurrency & tags; Provider-specific options",
            "Permissions (IAM): Existing role, Effect Allow/Deny, Actions, Resources, + Add statement, Remove",
            "Review: Changes to pskit.yml; Create function / Apply changes; Back / Next; Cancel; Open code",
        ],
    },
    {
        "title": "Workflows",
        "nav": "Workflows",
        "file": "dashboard-ui/src/studio/views/Workflows.tsx",
        "open": "Left navigation.",
        "purpose": "Visual step-function builder. docs/studio.md; docs/workflows.md.",
        "sections": [
            "List: New workflow (Name, Create, Cancel), Delete",
            "Palette states: task, choice, wait, pass, parallel, map, succeed, fail (docs/studio.md)",
            "Settings: Description, Engine, Timeout (s)",
            "Diagram and inspector: State name, Rename, Comment, Function, Result, Error, Cause",
            "Choice: Rules, conditions, Otherwise",
            "Retry and catch editors (attempts, interval, backoff, max delay, go to)",
            "Parallel branches and map iterator open as nested workflows",
        ],
    },
    {
        "title": "Resources",
        "nav": "Resources",
        "file": "dashboard-ui/src/studio/views/Resources.tsx",
        "open": "Left navigation. On-prem services, servers, guides and testers are components opened from this page.",
        "purpose": "Managed or external resources, plus on-prem services. docs/studio.md, docs/resources.md.",
        "sections": [
            "Buttons: Guides, + SMTP server (onprem only), + On-prem service, + Add resource",
            "Table columns: Key, Type, Mode, Native name. Row: How to use, DNS guide (smtp), Data, Test, Delete",
            "Undeclared on-prem services: + <key> (service) calls Add",
            "Resource drawer: Type, external, Native name, Browse account…, Connection, Bound functions, On-premises driver, Provider-specific options, Create a <type> on premises",
            "How to use drawer: Copy guide, Test it (docs/resource-usage.md)",
            "In the cloud panel (CloudResources.tsx): Load / Refresh, Delete, Delete selected, Delete all kept",
            "On-prem services (OnPremServices.tsx): Guide, + Create service, Details, How to use, Browse, Console, Terminal, Add to pskit.yml, Backup, Remove, Generate, Check/Add/Remove web UI",
            "Servers (OnPremMachines.tsx): + Add server, Test, live use, Shell, Terminal, Install / create, Edit, Forget, Save and test",
            "Replication (Replication.tsx): + Add read replica, Remove",
            "Monitoring (Monitoring.tsx): Save / Turn alerts on, Turn off, Send a test alert, Check now",
            "Data browser, service browser (buckets and secrets), resource tester: Test connection",
        ],
    },
    {
        "title": "Scaling cluster",
        "nav": "Scaling cluster",
        "file": "dashboard-ui/src/studio/views/Cluster.tsx",
        "open": "Left navigation. Warns to switch the provider to onprem.",
        "purpose": "Docker Swarm, k3s or Nomad. docs/cluster.md, docs/studio.md.",
        "sections": [
            "+ New cluster (drawer title New scaling cluster): orchestrator, master, Create / Installing…",
            "Tabs when more than one cluster (name · orchestrator)",
            "Refresh, Check & alert, Forget",
            "Servers table: Server, State, CPU, Memory, Disk; + Join server; Remove; uninstall",
            "Load balancer block: + Set up load balancer, Sync now, Show log, Change, Remove",
            "Shared load balancers: + Attach a load balancer, Detach",
            "Use for this project writes provider.options.cluster (docs/studio.md)",
            "Web replicas, CPU per replica, Memory per replica (MB), Port on the load balancer, Scale",
            "Live requests (Live, Clear), Live logs",
            "Resources on this cluster; Deployed functions",
            "When every server is full: Alert function, Stage, Save, Send test alert",
            "+ Join a server now / + Add a server",
        ],
    },
    {
        "title": "Load balancers",
        "nav": "Load balancers",
        "file": "dashboard-ui/src/studio/views/LoadBalancers.tsx",
        "open": "Left navigation.",
        "purpose": "One URL, a path per project or cluster. docs/load-balancers.md.",
        "sections": [
            "+ Create load balancer (drawer New load balancer): Name, Server, Port, Address in the URL, How it spreads requests, Attach clusters now, Create",
            "Refresh, Update, Sync, Logs, Remove, Forget",
            "CPU, Memory, Disk",
            "+ Attach cluster, Detach",
            "Routes table: Owner, Source, Backends; Remove route",
            "Put this project on a balancer: Path, Algorithm for this route (provider.options.balancer)",
        ],
    },
    {
        "title": "Network map",
        "nav": "Network map",
        "file": "dashboard-ui/src/studio/views/Network.tsx",
        "open": "Left navigation.",
        "purpose": "On-prem servers and the connections they must accept or open. docs/onprem-network.md.",
        "sections": [
            "Refresh",
            "Machines list and map; All machines",
            "Inbound — accept; Outbound — open",
            "Used in",
            "Empty: No servers and no connections yet. Save a server under Resources.",
        ],
    },
    {
        "title": "Code",
        "nav": "Code",
        "file": "dashboard-ui/src/studio/views/Code.tsx",
        "open": "Left navigation, or Code on a function row.",
        "purpose": "File tree and CodeMirror editor, or Full VS Code (code-server). docs/studio.md#full-vs-code-code-server-in-docker.",
        "sections": [
            "Editor: Find file, New file (+), Create, Refresh, Save (Ctrl+S), close tab",
            "Full VS Code: Python and Node.js runtime pickers, Pull & start / Start, Open in new tab, Restart with these runtimes, Stop, Check again",
        ],
    },
    {
        "title": "Test",
        "nav": "Test",
        "file": "dashboard-ui/src/studio/views/Test.tsx",
        "open": "Left navigation, or Test on a function row.",
        "purpose": "Local invoke and real trigger send. docs/studio.md#test-functions.",
        "sections": [
            "1. Choose the event (a trigger or Direct invoke)",
            "2. Edit the event: Request, Payload (JSON), Saved events, Save event",
            "3. Run it: Run locally (pskit invoke); Send to <provider> / <stage> (pskit trigger); Show the function's logs",
            "How to test this: tabs studio, terminal, cloud console; Copy",
        ],
    },
    {
        "title": "Deploy",
        "nav": "Deploy",
        "file": "dashboard-ui/src/studio/views/Deploy.tsx",
        "open": "Left navigation.",
        "purpose": "Validate, package, plan, deploy, info, remove, with a live log. docs/studio.md.",
        "sections": [
            "Action buttons come from the studio job catalog (labels rendered from each action). Remove can pass keep_resources. prod stages need a typed confirmation (docs/studio.md).",
            "Where functions run (provider.options.placement): Run on, Cluster, Machine",
            "Switch: Remove also deletes buckets, queues and topics (docs/studio.md) — off runs pskit remove --keep-resources",
            "Compat panel: Disable trigger / function / workflow on <provider>, Disable all of them",
            "Firewall section (ports each server must allow)",
            "Output tabs: Steps, Raw log",
            "Recent jobs: Clear finished",
            "Invoke a function locally (pskit invoke): Function, Event type, Path, Payload, Invoke",
            "Run a workflow locally (pskit workflow run --history): Workflow, Input, Run",
        ],
    },
    {
        "title": "Logs",
        "nav": "Logs",
        "file": "dashboard-ui/src/studio/views/Logs.tsx",
        "open": "Left navigation. Per-function Live logs also live on the function editor.",
        "purpose": "Logs of the deployed provider/stage. docs/studio.md. CLI: pskit logs.",
        "sections": [
            "Source picker; cluster replica / server filters when on-prem",
            "Stored logs: list, select and delete (AWS and on-prem per docs/studio.md)",
        ],
    },
    {
        "title": "YAML",
        "nav": "YAML",
        "file": "dashboard-ui/src/studio/views/Yaml.tsx",
        "open": "Left navigation.",
        "purpose": "The generated pskit.yml, a diff, and raw edit. docs/studio.md.",
        "sections": [
            "YAML mode",
            "Apply to draft (Parsing… while busy)",
            "Comments are not preserved; backups in .pskit/studio/backups/",
        ],
    },
]

DIALOGS = [
    ("Create function wizard", "Functions > + Create function", "dashboard-ui/src/studio/views/Functions.tsx"),
    ("Create service", "Resources > + On-prem service or On-prem services > + Create service", "dashboard-ui/src/studio/components/OnPremServices.tsx"),
    ("Create cluster", "Scaling cluster > + New cluster", "dashboard-ui/src/studio/views/Cluster.tsx"),
    ("Join server", "Scaling cluster > + Join server", "dashboard-ui/src/studio/views/Cluster.tsx"),
    ("Servers", "Resources > On-prem services > Servers", "dashboard-ui/src/studio/components/OnPremMachines.tsx"),
    ("Browse account", "Resources resource form > Browse account…", "dashboard-ui/src/studio/views/TriggerForms.tsx"),
    ("Full VS Code", "Code > Full VS Code", "dashboard-ui/src/studio/views/Code.tsx"),
    ("Test a resource", "Resources > Test", "dashboard-ui/src/studio/components/ResourceTester.tsx"),
    ("How to use", "Resources > How to use", "dashboard-ui/src/studio/views/Resources.tsx"),
    ("Import / export settings", "Top bar > ⇅ Settings", "dashboard-ui/src/studio/views/Setup.tsx"),
    ("New load balancer", "Load balancers > + Create load balancer", "dashboard-ui/src/studio/views/LoadBalancers.tsx"),
    ("SMTP DNS guide", "Resources row > DNS guide", "dashboard-ui/src/studio/views/Resources.tsx"),
    ("Session token screen", "Shown on HTTP 401", "dashboard-ui/src/studio/App.tsx"),
]

ONPREM_TOPICS = [
    ("deploy-local", "Deploy method local: process on this machine. docs/providers.md#onprem-on-premises"),
    ("deploy-ssh", "Deploy method ssh (scp is the same path): release.tar.gz, systemd or a process, health /__pskit/health. docs/architecture.md#bundle-layout"),
    ("deploy-docker", "Deploy method docker: image built here, copied over SSH, docker load/run; install_docker default true. docs/providers.md"),
    ("python-bundle", "python: bundle portable CPython, or python: system. docs/providers.md"),
    ("saved-servers", "Saved SSH servers: add, list, test, check, top, usage, remove. CLI resources onprem servers *. core/onprem_servers.py"),
    ("ssh-key", "Install an SSH key once (resources onprem ssh-key). docs/studio.md"),
    ("shell", "Shell on a saved server (resources onprem shell). Studio: Shell"),
    ("terminal", "Browser terminal via ttyd in Docker (resources onprem terminal). Studio: Terminal"),
    ("runtimes", "Install docker, python, nodejs, java, go, nginx, caddy, certbot, pm2, git, tools. Catalog kind runtime."),
    ("one-click-services", "Create/list/status/logs/backup/remove/gui/monitor/alerts. docs/resource-guides/onprem/services.md"),
    ("database-single", "Database on one server. docs/resource-guides/onprem/database.md"),
    ("database-replicas", "Primary plus read replicas, add/remove. CLI resources onprem replicas. core/onprem_replication.py"),
    ("backup", "resources onprem backup writes .pskit/backups. docs/studio.md"),
    ("monitor-alerts", "resources onprem monitor and alerts. Studio Monitoring.tsx"),
    ("web-ui", "Also start the web UI; Details > Add/Remove/Check web UI. docs/studio.md"),
    ("console", "resources onprem console (redis-cli, psql, mongosh, rpk, bao, …)"),
    ("browse", "pskit browsers for buckets and secrets. core/onprem_browser.py"),
    ("secrets-managers", "OpenBao, secretsmanager, secretsmanager-node, Infisical, LocalStack. docs/resource-guides/onprem/secrets.md"),
    ("s3-server", "minio, rustfs, s3, s3-node, fake-gcs, azurite, localstack, localemu. docs/resource-guides/onprem/storage.md"),
    ("smtp-dns", "smtp service plus DNS A/MX. docs/smtp/README.md"),
    ("cluster-types", "swarm, kubernetes (k3s), nomad. docs/cluster.md#how-the-functions-run-in-a-cluster"),
    ("cluster-lifecycle", "create, join, leave, set, scale, status, check, watch, alerts, requests, remove. docs/cluster.md#commands"),
    ("cluster-balancer", "cluster balancer set/remove/sync/logs. docs/cluster.md"),
    ("placement", "provider.options.placement groups. docs/placement.md"),
    ("lb-algorithms", "round_robin, sticky_round_robin, weighted_round_robin, ip_hash, least_connections (default), least_time. pskit lb algorithms"),
    ("lb-routes", "lb create/update/list/status/attach/detach/routes remove/sync/logs/remove/forget. docs/load-balancers.md"),
    ("network-map", "Studio Network map. core/onprem_usage.py, docs/onprem-network.md"),
    ("firewall", "pskit firewall. docs/onprem-network.md"),
    ("tunnels", "resources onprem tunnel and client tunnel. docs/client.md#when-connections-time-out"),
]


def guide_index(guides: list[dict]) -> dict[tuple[str, str], str]:
    found = {}
    for guide in guides:
        path = guide["path"]
        parts = path.split("/")
        if len(parts) < 4 or parts[2] not in PROVIDERS:
            continue
        cloud = parts[2]
        stem = Path(parts[-1]).stem
        if stem in TYPES or stem == "secrets" or stem == "services":
            found[(cloud, stem)] = f"{guide['title']} ({path})"
    return found


def main() -> None:
    cli = load("cli.json")
    docs = load("docs_headings.json")
    facts = load("facts.json")
    catalog = load("onprem_catalog.json")
    lines: list[str] = []
    w = lines.append

    w("# Knowledge inventory")
    w("")
    w("Coverage checklist for Hana stage 1. Version **2.10.0** (`src/py_serverless_kit/_version.py`).")
    w("Command options are copied from `ai-agent/training/knowledge/cli.json` (Click walk of `py_serverless_kit.cli.main.cli`).")
    w("Doc headings are copied from `docs_headings.json` (GitHub slug anchors).")
    w("Do not treat this file as a second source of truth: cards re-read the cited files.")
    w("")
    w("Conflicts: `ai-agent/training/knowledge/conflicts.md`.")
    w("")

    commands = cli["commands"]
    leaves = [c for c in commands if not c["is_group"]]
    groups = [c for c in commands if c["is_group"]]

    w("## 1a. Commands")
    w("")
    w(f"Click nodes: {cli['count_all']} ({cli['count_groups']} groups including the root, {cli['count_commands']} leaf commands).")
    w("Source: `src/py_serverless_kit/cli/main.py`. Full help text is the `help_output` field in `cli.json`.")
    w("")
    w("### Groups")
    w("")
    for cmd in groups:
        w(f"- `{cmd['name']}` — {cmd['short_help']}")
    w("")
    w("### Leaf commands")
    w("")
    for cmd in leaves:
        w(f"#### `{cmd['name']}`")
        w("")
        w(cmd["short_help"] or "(no short help)")
        w("")
        arg = args_line(cmd)
        if arg:
            w(f"- Arguments: {arg}")
        flag = flags(cmd)
        if flag:
            w(f"- Options: {flag}")
        w("")

    w("## 1b. Studio pages")
    w("")
    w("Left navigation order from `NAV` in `dashboard-ui/src/studio/App.tsx`:")
    w("")
    w("1. Overview & provider")
    w("2. Setup & credentials")
    w("3. Functions")
    w("4. Workflows")
    w("5. Resources")
    w("6. Scaling cluster")
    w("7. Load balancers")
    w("8. Network map")
    w("9. Code")
    w("10. Test")
    w("11. Deploy")
    w("12. Logs")
    w("13. YAML")
    w("")
    w("New project replaces the shell when `project.exists` is false (`App.tsx`). It is not in `NAV`.")
    w("")
    w("### Top bar (`App.tsx`)")
    w("")
    w("- Brand (service name) links to Overview & provider. Subtitle: pskit studio.")
    w("- Label `validate & deploy as`: provider `<select>` (aria-label Target provider). Options are `meta.providers` display names.")
    w("- Label `stage`: text input (aria-label Stage), lowercased to `[a-z0-9-]`, max 16 characters.")
    w("- Undo (Ctrl+Z), Redo (Ctrl+Shift+Z). Ctrl+Y also redo. Ignored while focus is in an editor.")
    w("- Problems button (error and warning counts) opens the Problems panel. Close problems.")
    w("- Validate (title Validate now) calls `validateNow`.")
    w("- Save / Saved / Saving… (title Save pskit.yml (Ctrl+S)). Ctrl/Cmd+S saves except on the Code page.")
    w("- ⇅ Settings opens drawer `Import / export settings and config` (`SettingsTransfer` in Setup.tsx).")
    w("- Theme toggle (aria-label Toggle theme), stored as `pskit-theme` in localStorage.")
    w("- Menu (burger) opens the nav on small widths.")
    w("- Conflict modal `pskit.yml changed on disk`: Cancel, Reload (discard my changes), Overwrite.")
    w("- Token screen (HTTP 401): `This studio session needs its link`, shows `pskit studio --open`.")
    w("- Nav footer shows project notices and `pskit {meta.version}`.")
    w("- Docs: `docs/studio.md` (Save, undo, validation, backups).")
    w("")
    for page in PAGES:
        w(f"### {page['title']}")
        w("")
        w(f"- Nav label: {page['nav']}")
        w(f"- How to open: {page['open']}")
        w(f"- File: `{page['file']}`")
        w(f"- Purpose: {page['purpose']}")
        w("- Sections and controls:")
        for item in page["sections"]:
            w(f"  - {item}")
        w("")
    w("### Dialogs and panels to card separately")
    w("")
    for name, where, path in DIALOGS:
        w(f"- {name}: {where}. `{path}`")
    w("")

    w("## 1c. Docs")
    w("")
    w(f"Files under `docs/`: {docs['file_count']} ({docs['markdown_count']} Markdown, {docs['file_count'] - docs['markdown_count']} other). Headings: {docs['heading_count']}.")
    w("Anchors use the GitHub slugger rules in `ai-agent/training/tools/extract_docs.py`.")
    w("")
    for item in docs["files"]:
        w(f"### `{item['path']}`")
        w("")
        if not item["headings"]:
            w("- (no Markdown headings)")
            w("")
            continue
        for heading in item["headings"]:
            indent = "  " * (heading["level"] - 1)
            w(f"{indent}- {heading['title']} (`#{heading['anchor']}`)")
        w("")

    w("## 1d. Resources")
    w("")
    w("Schema types (`RESOURCE_TYPES` in `src/py_serverless_kit/config/schema.py`): storage, queue, topic, database, cache, custom, smtp.")
    w("`database`, `cache` and `custom` must be `external: true` (schema `_managed`). `storage`, `queue`, `topic` and `smtp` may be managed.")
    w("`secrets` is not a `type`. Secret managers are on-prem services and `get_secret()` (`docs/resource-guides/onprem/secrets.md`, `docs/handlers.md#get_secret-secrets-on-every-provider`).")
    w("The Fields table in `docs/resources.md#fields` omits smtp. See `conflicts.md`.")
    w("")
    w("Managed vs external summary from `docs/resources.md#provider-support`:")
    w("")
    w("- aws, gcp, azure, onprem: managed resources may exist with or without an event (native names in that section).")
    w("- alibaba, tencent, huawei, oracle, ibm, digitalocean, cloudflare: managed only when an event uses the resource; otherwise `external: true`.")
    w("- database / cache / custom: external on every provider (env only).")
    w("")
    w("Connection variables: `PSKIT_RESOURCES`, `PSKIT_RESOURCE_<KEY>_TYPE`, `_NAME`, `_EXTERNAL`, `_<CONNECTION KEY>`, plus `_ARN` / `_URL` / `_ID` when the provider knows them (`docs/resources.md#what-handlers-receive`).")
    w("Read with `resource(name)` (`runtime/resources.py`). Libraries: `docs/resource-usage.md#which-library-for-which-resource`.")
    w("Events that can name a resource: queue, storage, topic, smtp (`EVENT_RESOURCE_TYPES`).")
    w("")
    w("### Guide cell (type × provider)")
    w("")
    w("A cell is the H1 of `docs/resource-guides/<cloud>/<type>.md` when that file exists. `smtp` has no per-cloud guide file; the on-prem SMTP server is `docs/smtp/README.md` and `docs/resource-guides/onprem/services.md`.")
    w("")
    index = guide_index(facts["guides"])
    header = "| type | " + " | ".join(PROVIDERS) + " |"
    sep = "|---|" + "|".join(["---"] * len(PROVIDERS)) + "|"
    w(header)
    w(sep)
    cells = 0
    guided = 0
    for rtype in TYPES:
        row = [rtype]
        for cloud in PROVIDERS:
            cells += 1
            hit = index.get((cloud, rtype))
            if hit:
                guided += 1
                row.append(hit.split(" (`")[0][:48])
            elif rtype == "smtp" and cloud == "onprem":
                row.append("on-prem SMTP server (docs/smtp/README.md)")
            elif rtype == "smtp":
                row.append("no smtp guide")
            else:
                row.append("—")
        w("| " + " | ".join(row) + " |")
    w("")
    w(f"Cells: {cells} ({len(TYPES)} types × {len(PROVIDERS)} providers). Guide files matched: {guided}.")
    w("")
    w("Extra on-prem pages (not a schema type × provider cell):")
    w("")
    for key in ("secrets", "services"):
        hit = index.get(("onprem", key))
        if hit:
            w(f"- {hit}")
    w("- `docs/resource-guides/README.md` — index table of native services per cloud.")
    w("- `docs/resource-guides/compatibility.md` — existing cloud code.")
    w("- Each cloud `README.md` under `docs/resource-guides/<cloud>/`.")
    w("")
    w("Native service names in the index table (`docs/resource-guides/README.md`):")
    w("")
    w("| provider | storage | queue | topic | database | cache | custom |")
    w("|---|---|---|---|---|---|---|")
    native = {
        "aws": "S3 | SQS | SNS | RDS / Aurora | ElastiCache / MemoryDB | DynamoDB, Secrets Manager, …",
        "gcp": "Cloud Storage | Pub/Sub topic as a queue | Pub/Sub topic | Cloud SQL | Memorystore | Firestore, Secret Manager, …",
        "azure": "Blob container | Storage queue | Service Bus topic | PostgreSQL / MySQL / SQL | Redis | Cosmos DB, Key Vault, …",
        "alibaba": "OSS | SMQ / MNS queue | SMQ / MNS topic | ApsaraDB RDS / PolarDB | Tair (Redis) | Tablestore, KMS, …",
        "tencent": "COS | TDMQ for CMQ queue | TDMQ for CMQ topic | TencentDB MySQL / PostgreSQL | TencentDB for Redis | Secrets Manager, …",
        "huawei": "OBS | DMS RabbitMQ / Kafka | SMN | RDS | DCS Redis | CSMS, DDS, …",
        "oracle": "Object Storage | OCI Queue | Notifications | Autonomous DB, MySQL HeatWave | OCI Cache | Vault, Streaming, …",
        "ibm": "Cloud Object Storage | IBM MQ | Event Streams | Databases for PostgreSQL / MySQL | Databases for Redis | Secrets Manager, Cloudant, …",
        "digitalocean": "Spaces | Valkey list as a queue | Managed Kafka | Managed PostgreSQL / MySQL | Managed Valkey | MongoDB, OpenSearch, DO API",
        "cloudflare": "R2 | Queues | No topics: alternatives | D1 / Hyperdrive | Workers KV | Secrets, Workers AI, HTTP APIs",
        "onprem": "Built-in, MinIO, S3, R2, Blob, GCS | Built-in, Redis, Kafka, NATS, RabbitMQ, another host, SQS, … | Built-in / directory | PostgreSQL / MySQL | Redis / Valkey | SMTP, LDAP, internal APIs",
    }
    for cloud, text in native.items():
        w(f"| {cloud} | {text} |")
    w("")
    w("Source of that table: `docs/resource-guides/README.md` (the link text in the matrix).")
    w("")

    w("## 1e. On-premises topics")
    w("")
    w("Topic checklist (each becomes at least one card):")
    w("")
    for slug, text in ONPREM_TOPICS:
        w(f"- `{slug}` — {text}")
    w("")
    w(f"Topic count: {len(ONPREM_TOPICS)}.")
    w("")
    w("### One-click catalog")
    w("")
    w("From `pskit resources onprem catalog --json` (`core/onprem_services.py` `catalog()`), saved as `onprem_catalog.json`.")
    w("")
    w("| id | kind | group | roles | port | image |")
    w("|---|---|---|---|---|---|")
    for item in catalog:
        roles = ", ".join(item.get("roles") or []) or "runtime"
        port = item.get("port") if item.get("port") is not None else ""
        image = item.get("image") or ""
        w(f"| `{item['id']}` | {item.get('kind','')} | {item.get('group','')} | {roles} | {port} | {image} |")
    w("")
    w(f"Catalog entries: {len(catalog)}.")
    w("")
    w("### Load balancer algorithms")
    w("")
    w("From `pskit lb algorithms` (`core/onprem_lb.py`):")
    w("")
    w("- Static: `round_robin`, `sticky_round_robin`, `weighted_round_robin`, `ip_hash`")
    w("- Dynamic: `least_connections` (default), `least_time`")
    w("")

    w("## 1f. Code map")
    w("")
    w("One line per Python module. The sentence is the module docstring's first sentence, or blank when the file has no module docstring.")
    w("Pipeline (from `docs/architecture.md#deploy-pipeline` and `CLAUDE.md`):")
    w("")
    w("`pskit.yml` → `config/loader.py` → `config/schema.py` (`ServiceConfig`) → `core/project.py` → `Provider.validate()` → `packaging/builder.py` → `Provider.render()` (`TerraformDoc` / `main.tf.json`) → `terraform/runner.py` → `core/describe.py` (`deployment.json`) → `dashboard/generator.py`.")
    w("")
    w("Runtime (`docs/architecture.md#runtime-flow`): platform → shim → `runtime/adapters/<cloud>.py` → `runtime/dispatch.py` `execute` → handler.")
    w("")
    w("`__pskit` envelope: `{\"__pskit\": \"<schedule|workflow|invoke>\", \"data\": ...}` (`docs/architecture.md#runtime-flow`, `runtime/adapters/base.py` `unwrap_envelope`).")
    w("")
    w("Terraform output `pskit`: `{functions, workflows, endpoint}` (`docs/architecture.md#deploy-pipeline`).")
    w("")
    w("Workflow engines: `workflows/asl.py` (AWS), `workflows/gcp.py` (Google Cloud Workflows), `workflows/azure_logic.py` (Azure Logic Apps). Elsewhere `runtime/workflow.py` `orchestrate` (`docs/architecture.md#runtime-flow`, `CLAUDE.md`).")
    w("")
    w(f"Python modules: {len(facts['modules'])}.")
    w("")
    for mod in facts["modules"]:
        summary = mod["summary"] or "(no module docstring)"
        w(f"- `{mod['path']}` — {summary}")
    w("")
    w("### `runtime_js/`")
    w("")
    w("Node runtime copied into Node bundles. Files (from the tree, no per-file docstring walk): `index.js`, `dispatch.js`, `event.js`, `context.js`, `routing.js`, `response.js`, `batch.js`, `errors.js`, `invoke.js`, `log.js`, `manifest.js`, `resources.js`, `secrets.js`, `workflow.js`, `worker.js`, `client.js`, `onprem.js`, `util.js`, `package.json`, `index.d.ts`, `adapters/*.js`. Contract: `deploy_docs/NODE_RUNTIME.md`, `docs/nodejs.md`.")
    w("")

    w("## 1g. Terraform and Docker")
    w("")
    w("### Terraform")
    w("")
    w("- Generated as Python dicts (`providers/terraform_doc.py`), written as `main.tf.json`. User `${` is escaped to `$${` unless written `${tf:...}` (`docs/architecture.md#deploy-pipeline`, `CLAUDE.md`).")
    w("- One directory per provider and stage: `.pskit/<provider>-<stage>/` with its own state (`docs/architecture.md#deploy-pipeline`).")
    w("- Binary: `terraform` or `tofu` (`terraform/runner.py`). Missing binary: `docs/troubleshooting.md#installation-and-tooling`. Override: `PSKIT_TERRAFORM_BIN` or `provider.terraform.binary`.")
    w("- Remote state: `provider.state` (`docs/architecture.md#state-handling`, `docs/configuration.md`).")
    w("- `pskit tf -- ARGS` passes arguments to the binary (`docs/cli.md`).")
    w("- Custom Terraform: `examples/11-custom-terraform`.")
    w("- `pskit remove --keep-resources` keeps data resources (`core/retain.py`, `docs/studio.md`).")
    w("- On-premises uses built-in `terraform_data` and `local-exec` of `onprem_deploy.py` (`docs/providers.md#onprem-on-premises`).")
    w("- DigitalOcean deploys through `terraform_data` running `doctl serverless` (`docs/providers.md`).")
    w("- Oracle functions are container images (`func.py` / `func.js`, `func.yaml`, `Dockerfile`) (`docs/architecture.md#bundle-layout`, `docs/providers.md`).")
    w("")
    w("### Docker")
    w("")
    w("- On-prem `method: docker`: build locally, copy over SSH, `docker load` and `docker run` (`docs/providers.md`, `docs/architecture.md#bundle-layout`).")
    w("- One-click services are containers (`docs/resource-guides/onprem/services.md`, catalog images above).")
    w("- Clusters: Swarm needs Docker on every server; Nomad needs Docker plus the Nomad agent; k3s does not need Docker (`docs/cluster.md#how-the-functions-run-in-a-cluster`). The function image is built on the machine running deploy.")
    w("- Cluster and shared load balancers run OpenResty in container `pskit-lb` (`docs/cluster.md`, `docs/load-balancers.md`).")
    w("- Full VS Code: code-server image `codercom/code-server:4.96.4` (`docs/studio.md#full-vs-code-code-server-in-docker`, `studio/vscode.py`).")
    w("- Browser terminals use ttyd in Docker (`core/onprem_terminal.py`).")
    w("- Studio itself in a container: example `docker run` in `docs/studio.md#full-vs-code-code-server-in-docker` (`PSKIT_STUDIO_HOST_ROOT`, Docker socket).")
    w("- Oracle function images (`docs/providers.md`).")
    w("")

    w("## 1h. Everything else")
    w("")
    w("- `pskit function split` moves a function into its own folder (`core/function_split.py`, `docs/placement.md`). Studio button: Own folder / Give each function its own folder.")
    w("- `pskit settings export` / `import`: encrypted bundle of `.pskit` settings (`core/settings_bundle.py`). Passphrase env `PSKIT_SETTINGS_PASSPHRASE` (`docs/cli.md#environment-variables`).")
    w("- `pskit client info|install-node|tunnel` (`docs/client.md`, `client.py`).")
    w("- Node.js / TypeScript: `docs/nodejs.md`, `examples/21-nodejs-typescript`, `packaging/node.py`, `runtime_js/`.")
    w("- Dashboard: `pskit dashboard` (`docs/dashboard.md`, `dashboard/generator.py`, `dashboard/server.py`). Separate from studio.")
    w("- Workflow executions: `pskit workflow start|executions|status|cancel` (`docs/workflow-executions.md`, `core/executions.py`).")
    w("- Scenarios: `docs/scenarios.md`.")
    w("- Migration from AWS: `docs/migrating-from-aws.md`, `examples/13-migrate-from-aws-lambda`.")
    w("- Existing cloud code: `docs/resource-guides/compatibility.md`.")
    w("- Multi-cloud overrides: `providers:` / `stages:` / `extends` (`docs/configuration.md`, `examples/08-multi-cloud`, `examples/10-stages-and-config`).")
    w("- Variables: `${env|opt|self|file}` (`config/loader.py`, `docs/configuration.md`).")
    w("- Examples (each directory with `pskit.yml` is exercised by `tests/test_examples.py`, `CLAUDE.md`):")
    examples = [
        "01-hello-http",
        "02-rest-api",
        "03-scheduled-jobs",
        "04-queue-worker",
        "05-storage-events",
        "06-pubsub-topic",
        "07-workflow-orders",
        "08-multi-cloud",
        "09-function-invoke",
        "10-stages-and-config",
        "11-custom-terraform",
        "12-async-and-context",
        "13-migrate-from-aws-lambda",
        "14-testing",
        "15-ci-cd-deploy",
        "16-on-premises",
        "17-on-premises-remote",
        "18-resources",
        "19-custom-drivers",
        "20-onprem-external-clouds",
        "21-nodejs-typescript",
    ]
    for name in examples:
        w(f"  - `examples/{name}`")
    w("- Maintainer docs (not under `docs/`): `deploy_docs/CONTRIBUTING.md`, `deploy_docs/How_to_deploy.md`, `deploy_docs/HOW_TO_INSTALL_TERRAFORM.md`, `deploy_docs/NODE_RUNTIME.md`, `deploy_docs/PUBLISHING_TO_PYPI.md`.")
    w("- Root docs used as sources: `README.md`, `CHANGELOG.md`, `CLAUDE.md`, `CONTRIBUTING.md`, `SECURITY.md`.")
    w("- `docs/cli.md` does not mention `pskit lb`, `pskit firewall`, or `pskit function` (see conflicts.md).")
    w("- Event types: http, schedule, queue, storage, topic, smtp (`EVENT_TYPES` in schema.py, `docs/events.md`).")
    w("- Handler API: `docs/handlers.md` (`Event`, `Context`, `BatchResult`, `invoke`, `get_secret`).")
    w("- Local: `pskit dev`, `pskit invoke`, `pskit workflow run` (`docs/local-development.md`).")
    w("- Third-party providers: entry-point group `py_serverless_kit.providers` (`docs/architecture.md#third-party-providers`).")
    w("")

    w("## Counts")
    w("")
    w(f"- Leaf commands: {len(leaves)}")
    w(f"- Click groups (including root `pskit`): {len(groups)}")
    w(f"- Click nodes in cli.json: {len(commands)}")
    w(f"- Studio NAV pages: 13")
    w(f"- Studio pages including New project: {len(PAGES)}")
    w(f"- Extra dialogs/panels listed: {len(DIALOGS)}")
    w(f"- Docs files: {docs['file_count']} ({docs['markdown_count']} Markdown)")
    w(f"- Docs headings: {docs['heading_count']}")
    w(f"- Resource guides (Markdown under docs/resource-guides): {len(facts['guides'])}")
    w(f"- Resource type × provider cells: {len(TYPES) * len(PROVIDERS)} ({len(TYPES)} schema types × {len(PROVIDERS)} providers)")
    w(f"- On-prem topic checklist items: {len(ONPREM_TOPICS)}")
    w(f"- On-prem catalog entries: {len(catalog)}")
    w(f"- Python modules: {len(facts['modules'])}")
    w(f"- Examples: {len(examples)}")
    w("")
    w("Not verified by running (forbidden or out of scope for this pass): `deploy`, `remove`, `plan`, `tf`, cluster mutations, load-balancer mutations, `resources delete/clear`, on-prem create/remove/backup/replicas/servers mutations, firewall changes, `client tunnel` / `install-node`, `settings import`, `studio`, `dashboard`, `dev`. Those commands are described from `--help` in cli.json, docs and code only.")
    w("")

    text = "\n".join(lines)
    OUT.write_bytes(text.encode("utf-8"))
    print(f"wrote {OUT} bytes={len(text.encode('utf-8'))} lines={text.count(chr(10))+1}")
    print(f"commands={len(leaves)} groups={len(groups)} pages={len(PAGES)} docs={docs['file_count']} cells={len(TYPES)*len(PROVIDERS)} topics={len(ONPREM_TOPICS)} catalog={len(catalog)} modules={len(facts['modules'])}")


if __name__ == "__main__":
    main()
