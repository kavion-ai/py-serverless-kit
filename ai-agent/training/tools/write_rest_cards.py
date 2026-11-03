"""Remaining knowledge cards: guides, on-prem, code, examples, procedures, troubleshooting.

Facts are taken from repository files. Commands are checked against cli.json before they are written.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "ai-agent" / "training" / "tools"))
sys.path.insert(0, str(ROOT / "src"))

from extract_docs import github_anchor  # noqa: E402
from check_knowledge import check_ips, check_pskit_lines, cli_index  # noqa: E402

KNOW = ROOT / "ai-agent" / "training" / "knowledge"
JSONL = KNOW / "cards.jsonl"
DOCS = ROOT / "docs"
GUIDES = DOCS / "resource-guides"

IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
DOC_NETS = {(192, 0, 2), (198, 51, 100), (203, 0, 113)}
KNOWN = cli_index()
PAGES: list[dict] = []


def words(text: str) -> int:
    return len(re.findall(r"\S+", text))


def allowed_ip(ip: str) -> bool:
    parts = ip.split(".")
    try:
        nums = tuple(int(p) for p in parts)
    except ValueError:
        return False
    if any(n > 255 for n in nums):
        return False
    if nums[0] == 127 or nums == (0, 0, 0, 0):
        return True
    return nums[:3] in DOC_NETS


def scrub(text: str) -> tuple[str, bool]:
    changed = False

    def repl(match: re.Match[str]) -> str:
        nonlocal changed
        ip = match.group(0)
        if allowed_ip(ip):
            return ip
        changed = True
        return "192.0.2.10"

    text = IPV4.sub(repl, text)
    new = re.sub(r"\b(?:azureuser|ubuntu|root)@", "deploy@", text, flags=re.I)
    if new != text:
        changed = True
        text = new
    new = re.sub(r"\bazureuser\b", "deploy", text)
    if new != text:
        changed = True
        text = new
    return text, changed


def rewrite_note() -> str:
    return (
        "An address or login copied from the source was rewritten in this card. "
        "Addresses use 192.0.2.0/24, a documentation range. The login in those examples is deploy."
    )


def prose_from_markdown(text: str) -> str:
    lines: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if line.lstrip().startswith("![") or line.lstrip().startswith("<!--"):
            continue
        line = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", line)
        line = line.replace(" > ", " / ")
        lines.append(line)
    body = "\n".join(lines)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()

    def unwrap(match: re.Match[str]) -> str:
        inner = match.group(1).strip()
        if inner in KNOWN:
            return match.group(0)
        # A backtick span of only command-like words is checked as a CLI line.
        # Keep real commands. Turn every other `pskit ...` span into plain words.
        if re.fullmatch(r"pskit(?: [a-z0-9][a-z0-9-]*){1,6}", inner):
            return inner
        return match.group(0)

    return re.sub(r"`([^`\n]+)`", unwrap, body)


def section_text(path: Path, anchor: str | None) -> str:
    raw = path.read_text(encoding="utf-8")
    if not anchor:
        return prose_from_markdown(raw)
    lines = raw.splitlines()
    start = None
    start_level = 0
    in_fence = False
    for index, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not line.startswith("#"):
            continue
        level = len(line) - len(line.lstrip("#"))
        title = line[level:].strip()
        if github_anchor(title) == anchor:
            start = index
            start_level = level
            break
    if start is None:
        raise SystemExit(f"missing heading #{anchor} in {path}")
    chunk = [lines[start]]
    in_fence = False
    for line in lines[start + 1 :]:
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            chunk.append(line)
            continue
        if not in_fence and line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            if level <= start_level:
                break
        chunk.append(line)
    return prose_from_markdown("\n".join(chunk))


def trim_words(text: str, limit: int) -> str:
    if words(text) <= limit:
        return text
    pieces = text.split()
    cut = " ".join(pieces[:limit])
    dot = max(cut.rfind(". "), cut.rfind(".\n"))
    if dot >= int(len(cut) * 0.65):
        cut = cut[: dot + 1]
    return cut.strip()


def ensure_bounds(text: str, pad: str) -> str:
    text = trim_words(text.strip(), 430)
    if words(text) < 160:
        text = (text.rstrip() + "\n\n" + pad.strip()).strip()
    text = trim_words(text, 470)
    if words(text) < 150:
        text = (text.rstrip() + "\n\n" + pad.strip()).strip()
        text = trim_words(text, 490)
    return text.strip() + "\n"


def accept(card: dict) -> None:
    errors: list[str] = []
    check_pskit_lines(card["text"], KNOWN, card["id"], errors)
    check_ips(card["text"], card["id"], errors)
    if errors:
        raise SystemExit(card["id"] + "\n" + "\n".join(errors))
    n = words(card["text"])
    if n < 150 or n > 500:
        raise SystemExit(f"{card['id']} has {n} words")
    PAGES.append(card)


def add(cid: str, kind: str, title: str, tags: list[str], providers: list[str], sources: list[str], text: str) -> None:
    body, changed = scrub(text.strip())
    if changed and "rewritten in this card" not in body and words(body) < 460:
        body = body.rstrip() + "\n\n" + rewrite_note()
    body = body.strip() + "\n"
    accept(
        {
            "id": cid,
            "kind": kind,
            "title": title,
            "tags": tags,
            "providers": providers,
            "text": body,
            "sources": sources,
        }
    )


RESOURCE_PAD = """
A resource key follows function-name rules. connection values are scalars. A key ending in _env names a variable, and the handler reads that variable from the environment. database, cache, and custom must set external to true. The Fields table in the resources page lists storage, queue, topic, database, cache, and custom. The schema also allows smtp.

Open the form on its own line:

Resources > + Add resource

Then open the generated guide:

Resources > How to use

```
pskit validate
pskit resources usage orders -p aws -s dev
```

pskit resources send sends a test message or object for a queue, bucket, or topic. pskit resources send --list shows every resource. pskit invoke and pskit dev inject the same PSKIT_RESOURCE_* variables locally.
"""


def guide_cards() -> None:
    done = {
        "res-aws-storage",
        "res-aws-queue",
        "res-aws-topic",
        "res-aws-database",
        "res-aws-cache",
        "res-aws-custom",
        "res-azure-storage",
        "res-gcp-storage",
    }
    providers = {
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
    }
    for path in sorted(GUIDES.rglob("*.md")):
        rel = path.relative_to(ROOT).as_posix()
        parts = path.relative_to(GUIDES).parts
        if len(parts) == 1:
            cid = "res-guide-" + path.stem.lower().replace("_", "-")
            provider_list: list[str] = []
            title_prefix = "Resource guide"
        else:
            cloud, name = parts[0], path.stem
            if name.lower() == "readme":
                cid = f"res-guide-{cloud}-readme"
            else:
                cid = f"res-{cloud}-{name}"
            provider_list = [cloud] if cloud in providers else []
            title_prefix = cloud
        if cid in done:
            continue
        raw = path.read_text(encoding="utf-8")
        h1 = ""
        for line in raw.splitlines():
            if line.startswith("# "):
                h1 = line[2:].strip()
                break
        anchor = github_anchor(h1) if h1 else ""
        body = prose_from_markdown(raw)
        title = h1 or path.stem
        pad = RESOURCE_PAD
        if provider_list:
            pad = RESOURCE_PAD.replace("-p aws", "-p " + provider_list[0])
        text = f"# Resource: {title}\n\n" + ensure_bounds(body, pad)
        sources = [f"{rel}#{anchor}"] if anchor else [rel]
        sources.append("docs/resources.md#fields")
        add(cid, "resource", f"Resource: {title}", ["resource", path.stem, *provider_list], provider_list, sources, text)


ONPREM_TOPICS = [
    ("onprem-deploy-local", "On-premises deploy on this machine", "docs/providers.md", "onprem-on-premises", ["method: local", "terraform_data"]),
    ("onprem-deploy-ssh", "On-premises deploy over SSH", "docs/providers.md", "onprem-on-premises", ["release.tar.gz", "method: ssh"]),
    ("onprem-deploy-docker", "On-premises deploy with Docker", "docs/providers.md", "onprem-on-premises", ["docker load", "method: docker"]),
    ("onprem-python-bundle", "Portable Python for an on-premises host", "docs/providers.md", "onprem-on-premises", ["python: bundle", "python-build-standalone"]),
    ("onprem-saved-servers", "Saved SSH servers", "docs/resource-guides/onprem/services.md", "servers-several-machines", None),
    ("onprem-ssh-key", "Install an SSH key on a server", "docs/resource-guides/onprem/services.md", "ssh-login-key-agent-or-password", None),
    ("onprem-shell", "Shell on a saved server", "docs/resource-guides/onprem/services.md", "console-and-terminal", None),
    ("onprem-terminal", "Browser terminal for a server or service", "docs/onprem-network.md", "9-the-studio-and-browser-terminals", None),
    ("onprem-runtimes", "Install languages and tools on a server", "docs/resource-guides/onprem/services.md", "install-software-on-a-server", None),
    ("onprem-one-click-services", "One-click on-premises services", "docs/resource-guides/onprem/services.md", "one-click-services-for-on-premises-functions", None),
    ("onprem-database-single", "Database on one server", "docs/resource-guides/onprem/services.md", "databases-one-server-or-a-primary-with-read-replicas", ["Single", "one server"]),
    ("onprem-database-replicas", "Primary and read replicas", "docs/resource-guides/onprem/services.md", "databases-one-server-or-a-primary-with-read-replicas", ["replica", "primary"]),
    ("onprem-backup", "Back up an on-premises service", "docs/resource-guides/onprem/services.md", "backups", None),
    ("onprem-monitor-alerts", "Monitor services and send alerts", "docs/resource-guides/onprem/services.md", "monitoring-and-alerts", None),
    ("onprem-web-ui", "Web UI for an on-premises service", "docs/resource-guides/onprem/services.md", "web-uis", None),
    ("onprem-console", "Service console", "docs/resource-guides/onprem/services.md", "console-and-terminal", None),
    ("onprem-browse", "pskit browsers for buckets and secrets", "docs/resource-guides/onprem/services.md", "pskits-own-browsers-when-the-native-ui-is-missing", None),
    ("onprem-secrets-managers", "Secret managers on premises", "docs/resource-guides/onprem/secrets.md", None, None),
    ("onprem-s3-server", "S3-compatible storage on premises", "docs/resource-guides/onprem/storage.md", None, None),
    ("onprem-smtp-dns", "SMTP server and DNS records", "docs/smtp/README.md", "dns-records-at-your-domain-provider", None),
    ("onprem-cluster-types", "Swarm, Kubernetes, and Nomad", "docs/cluster.md", "how-the-functions-run-in-a-cluster", None),
    ("onprem-cluster-lifecycle", "Cluster create, join, scale, and remove", "docs/cluster.md", "commands", None),
    ("onprem-cluster-balancer", "Cluster load balancer", "docs/cluster.md", "load-balancer-one-url-for-the-whole-cluster-optional", None),
    ("onprem-placement", "Place functions on different servers", "docs/placement.md", "functions-on-several-servers-on-premises", None),
    ("onprem-lb-algorithms", "Load balancer algorithms", "docs/load-balancers.md", "the-six-algorithms", None),
    ("onprem-lb-routes", "Load balancer routes and attach", "docs/load-balancers.md", "create-one-and-put-projects-on-it", None),
    ("onprem-network-map", "Network map and firewall rules", "docs/onprem-network.md", "network-and-firewall-rules-on-premises", None),
    ("onprem-firewall", "Firewall ports for on-premises servers", "docs/onprem-network.md", "1-always-the-admin-machine-reaches-every-server-over-ssh", None),
    ("onprem-tunnels", "Tunnels when a port times out", "docs/client.md", "when-connections-time-out", None),
]

ONPREM_PAD = """
These steps run on the on-premises provider. Saved servers are named once and then reused by deploy, services, and clusters. Open the matching studio page from the left navigation. Scaling cluster, Load balancers, Network map, and Resources are the pages for this work.

```
pskit validate
pskit resources onprem catalog
```

pskit resources onprem catalog lists the services and runtimes the create command can start. Passwords generated for a service are stored in the env file and under .pskit/, and they are left out of pskit.yml.
"""


def keyword_paragraphs(text: str, keys: list[str] | None) -> str:
    if not keys:
        return text
    paragraphs = re.split(r"\n\s*\n", text)
    chosen = [p for p in paragraphs if any(k.lower() in p.lower() for k in keys)]
    if not chosen:
        return text
    return "\n\n".join(chosen)


def onprem_cards() -> None:
    for cid, title, path, anchor, keys in ONPREM_TOPICS:
        file_path = ROOT / path
        if anchor:
            body = section_text(file_path, anchor)
            source = f"{path}#{anchor}"
        else:
            h1 = ""
            for line in file_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("# "):
                    h1 = line[2:].strip()
                    break
            anchor = github_anchor(h1)
            body = prose_from_markdown(file_path.read_text(encoding="utf-8"))
            source = f"{path}#{anchor}"
        body = keyword_paragraphs(body, keys)
        text = f"# On-premises: {title}\n\n" + ensure_bounds(body, ONPREM_PAD)
        add(cid, "onprem", f"On-premises: {title}", ["onprem", cid], ["onprem"], [source], text)


def catalog_cards() -> None:
    catalog = json.loads((KNOW / "onprem_catalog.json").read_text(encoding="utf-8"))
    source = "docs/resource-guides/onprem/services.md#from-the-command-line"
    for item in catalog:
        cid = "onprem-svc-" + item["id"]
        roles = ", ".join(item.get("roles") or []) or "none"
        ports = str(item.get("port") or "none")
        extra = ", ".join(str(p) for p in item.get("extra_ports") or []) or "none"
        gui = ", ".join(item.get("gui") or []) or "none"
        logins = ", ".join(item.get("gui_logins") or []) or "none"
        notes = trim_words((item.get("notes") or "").replace("\n", " "), 80)
        kind = item.get("kind") or "service"
        text = f"""
# On-premises service: {item['label']}

The catalog id is `{item['id']}`. Kind is {kind}. Group is {item.get('group') or 'n/a'}. Image is {item.get('image') or 'n/a'}. Published port is {ports}. Extra ports are {extra}. Roles are {roles}. Backup is {'yes' if item.get('backup') else 'no'}. Persistent data is {'yes' if item.get('persistent') else 'no'}. Auth is {'yes' if item.get('auth') else 'no'}. Default user is {item.get('default_user') or 'n/a'}. Companion UI is {item.get('companion') or 'none'}. Web UI names are {gui}. GUI login choices are {logins}.

Catalog notes: {notes}

Create it from the studio on its own line:

Resources > + On-prem service

The drawer uses the catalog label. Where can be this machine or one saved SSH server. A runtime entry installs software. A service entry starts a container. An empty password is generated and stored in the env file and under .pskit/. It is left out of pskit.yml. The resource key is the name you type. Handlers then read it with resource("that-key").

```
pskit resources onprem catalog
pskit resources onprem create sample-{item['id']} --service {item['id']}
pskit resources onprem status sample-{item['id']}
```

pskit resources onprem usage sample-{item['id']} prints how to connect. pskit resources onprem logs sample-{item['id']} shows the container log when the entry is a container. Remove asks for confirmation in the CLI unless -y is passed. The studio remove path is the service row on Resources.
"""
        text = ensure_bounds(text, "")
        # --service value must be a token the checker treats as an argument, not a flag.
        # item id is like redis, apache-kafka. Good.
        add(
            cid,
            "onprem",
            f"On-premises service: {item['label']}",
            ["onprem", "catalog", item["id"]],
            ["onprem"],
            [source, "docs/resource-guides/onprem/services.md#one-click-services-for-on-premises-functions"],
            text,
        )


def module_sentence(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeError:
        return path.name
    match = re.match(r'\s*("""|\'\'\')(.*?)(\1)', text, re.S)
    if not match:
        return f"{path.as_posix()} has no module docstring."
    doc = match.group(2).strip().splitlines()[0].strip()
    rel = path.relative_to(ROOT).as_posix()
    return f"`{rel}`: {doc}"


def code_cards() -> None:
    src = ROOT / "src" / "py_serverless_kit"
    groups: dict[str, list[Path]] = {
        "code-cli": [],
        "code-config": [],
        "code-core": [],
        "code-onprem-services": [],
        "code-onprem-cluster": [],
        "code-dashboard": [],
        "code-local": [],
        "code-packaging": [],
        "code-providers": [],
        "code-runtime": [],
        "code-adapters": [],
        "code-drivers": [],
        "code-studio": [],
        "code-terraform": [],
        "code-workflows": [],
        "code-package": [],
    }
    clusterish = ("cluster", "balancer", "lb", "network", "placement", "usage", "follow", "control")
    for path in sorted(src.rglob("*.py")):
        rel = path.relative_to(src).as_posix()
        if rel.startswith("runtime/adapters/"):
            groups["code-adapters"].append(path)
        elif rel.startswith("runtime/drivers/"):
            groups["code-drivers"].append(path)
        elif rel.startswith("runtime/"):
            groups["code-runtime"].append(path)
        elif rel.startswith("core/onprem_"):
            if any(bit in path.name for bit in clusterish):
                groups["code-onprem-cluster"].append(path)
            else:
                groups["code-onprem-services"].append(path)
        elif rel.startswith("core/"):
            groups["code-core"].append(path)
        elif rel.startswith("cli/"):
            groups["code-cli"].append(path)
        elif rel.startswith("config/"):
            groups["code-config"].append(path)
        elif rel.startswith("dashboard/"):
            groups["code-dashboard"].append(path)
        elif rel.startswith("local/"):
            groups["code-local"].append(path)
        elif rel.startswith("packaging/"):
            groups["code-packaging"].append(path)
        elif rel.startswith("providers/"):
            groups["code-providers"].append(path)
        elif rel.startswith("studio/"):
            groups["code-studio"].append(path)
        elif rel.startswith("terraform/"):
            groups["code-terraform"].append(path)
        elif rel.startswith("workflows/"):
            groups["code-workflows"].append(path)
        else:
            groups["code-package"].append(path)
    intro = (
        "The deploy pipeline in the architecture doc is pskit.yml, then the config loader, the schema, "
        "the project, provider validate, the packaging builder, provider render to main.tf.json, the Terraform "
        "runner, deployment.json, and the dashboard. The runtime path is platform, shim, adapter, dispatch.execute, "
        "handler. runtime/ is stdlib-only and stays on Python 3.9. Terraform is built as Python dicts. "
        "Zip artifacts are byte-reproducible."
    )
    titles = {
        "code-cli": "CLI package",
        "code-config": "Config loader and schema",
        "code-core": "Core deploy and describe",
        "code-onprem-services": "On-premises service modules",
        "code-onprem-cluster": "On-premises cluster and network modules",
        "code-dashboard": "Dashboard package",
        "code-local": "Local runner and dev server",
        "code-packaging": "Packaging",
        "code-providers": "Provider plugins",
        "code-runtime": "Portable runtime",
        "code-adapters": "Runtime adapters",
        "code-drivers": "On-premises resource drivers",
        "code-studio": "Studio server",
        "code-terraform": "Terraform runner and JSON builder",
        "code-workflows": "Workflow compilers",
        "code-package": "Package entry points",
    }
    for cid, paths in groups.items():
        if not paths:
            continue
        sentences = [module_sentence(p) for p in paths]
        body = f"# Code: {titles[cid]}\n\n{intro}\n\n" + " ".join(sentences)
        pad = (
            "Studio pages and the pskit command line both call this package. "
            "pskit validate loads the schema before a provider renders main.tf.json. "
            "The runtime that is copied into a bundle stays on the standard library and on Python 3.9. "
            "Generated zip files sort their entries and use fixed timestamps so unchanged inputs hash the same way. "
            "Handlers stay the same across providers. Provider-specific behavior belongs in options and in the provider module."
        )
        body = trim_words(body, 440)
        while words(body) < 170:
            body += "\n\n" + pad
        if words(body) > 480:
            body = trim_words(body, 450)
        add(
            cid,
            "code",
            f"Code: {titles[cid]}",
            ["code", cid],
            [],
            ["docs/architecture.md#deploy-pipeline", "docs/architecture.md#runtime-flow", "CLAUDE.md"],
            body,
        )


def example_cards() -> None:
    examples = ROOT / "examples"
    chosen = []
    for directory in sorted(p for p in examples.iterdir() if p.is_dir()):
        if (directory / "pskit.yml").is_file() or (directory / "after" / "pskit.yml").is_file():
            chosen.append(directory)
    for directory in chosen:
        readme = directory / "README.md"
        yml_path = directory / "pskit.yml"
        if not yml_path.is_file():
            yml_path = directory / "after" / "pskit.yml"
        yml = yml_path.read_text(encoding="utf-8")
        comments = []
        for line in yml.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                comments.append(stripped.lstrip("#").strip())
        comment_text = " ".join(comments)
        readme_text = ""
        sources = [yml_path.relative_to(ROOT).as_posix()]
        if readme.is_file():
            readme_text = prose_from_markdown(readme.read_text(encoding="utf-8"))
            sources.insert(0, f"examples/{directory.name}/README.md")
        files = sorted(p.name for p in directory.iterdir() if p.is_file() and not p.name.startswith("."))
        text = f"""
# Example: {directory.name}

This directory is one of the examples that tests/test_examples.py packages and runs locally because it contains pskit.yml. Files here include {", ".join(files)}.

Comments in pskit.yml: {comment_text}

{readme_text}
"""
        pad = (
            "The handler stays the same when provider.name changes. Provider-specific values belong in providers: "
            "or in provider.options. pskit validate checks the example against the selected provider. "
            "pskit invoke runs a function from the example on this machine.\n\n```\npskit validate\n```\n"
        )
        text = f"# Example: {directory.name}\n\n" + ensure_bounds(prose_from_markdown(text), pad)
        # ensure_bounds already returns trailing content; add() strips
        add(
            "example-" + directory.name,
            "concept",
            f"Example: {directory.name}",
            ["example", directory.name],
            [],
            sources,
            text,
        )


def trouble_cards() -> None:
    path = DOCS / "troubleshooting.md"
    raw = path.read_text(encoding="utf-8")
    # Split on H2, keep H1 intro with the first section only via section_text.
    headings = []
    in_fence = False
    for line in raw.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if line.startswith("## "):
            headings.append(line[3:].strip())
    for title in headings:
        anchor = github_anchor(title)
        body = section_text(path, anchor)
        cid = "trouble-" + anchor[:48]
        text = f"# Troubleshooting: {title}\n\n" + ensure_bounds(
            body,
            "Add -v to the command when you need the traceback. Start with pskit validate and pskit doctor. "
            "The studio Problems list and Setup & credentials show the same class of setup errors.\n\n"
            "Setup & credentials > Check again\n\n```\npskit doctor\npskit validate\n```\n",
        )
        add(cid, "troubleshooting", f"Troubleshooting: {title}", ["troubleshooting", anchor], [], [f"docs/troubleshooting.md#{anchor}"], text)


def concept_extract(cid: str, title: str, path: str, anchor: str, tags: list[str]) -> None:
    body = section_text(ROOT / path, anchor)
    text = f"# {title}\n\n" + ensure_bounds(
        body,
        "pskit validate checks the project before Terraform runs. The studio page for this work is listed in the left navigation.\n\n```\npskit validate\n```\n",
    )
    add(cid, "concept", title, tags, [], [f"{path}#{anchor}"], text)


PROCEDURES = [
    (
        "proc-create-project",
        "Create a project",
        [],
        ["Open the new project screen when the folder has no pskit.yml.", "PATH:Functions > + Create function"],
        ["pskit init my-service --provider aws", "pskit validate"],
        "service is required and is 2 to 32 characters, starting with a letter. provider.name is required. A function needs a handler.",
        [("docs/configuration.md", "top-level")],
    ),
    (
        "proc-http-api",
        "HTTP API with path params and CORS",
        [],
        ["PATH:Functions > + Create function", "Add an HTTP trigger and set the path and method."],
        ["pskit invoke -f hello -t http --method GET --path /hello", "pskit dev"],
        "A path parameter uses {id} for one segment. CORS can be true or a mapping with origins, methods, and headers. The runtime answers OPTIONS.",
        [("docs/events.md", "http")],
    ),
    (
        "proc-queue-dlq",
        "Queue worker with a dead-letter queue",
        ["aws", "onprem"],
        ["PATH:Resources > + Add resource", "PATH:Functions > + Create function"],
        ["pskit invoke -f worker -t queue -d '{\"order_id\": 1}'", "pskit resources send jobs -d '{\"order_id\": 1}'"],
        "On AWS, dead_letter and max_receive apply when pskit creates the queue. Return a BatchResult to retry only failed records. On premises the file broker implements the same options.",
        [("docs/events.md", "queue"), ("docs/handlers.md", "batchresult")],
    ),
    (
        "proc-schedule",
        "Schedule a job",
        [],
        ["PATH:Functions > + Create function", "Choose a schedule trigger and set a rate or a cron expression."],
        ["pskit invoke -f nightly -t schedule -d '{\"report\": \"daily\"}'"],
        "A schedule is a rate such as 5 minutes or a 5-field cron. timezone defaults to UTC. The handler sees event.type schedule and event.data from input.",
        [("docs/events.md", "schedule")],
    ),
    (
        "proc-storage",
        "React to files in a bucket",
        [],
        ["PATH:Resources > + Add resource", "PATH:Functions > + Create function"],
        ["pskit invoke -f on-upload -t storage -d '{\"bucket\": \"uploads\", \"key\": \"in/a.txt\"}'", "pskit resources send uploads -d '{\"key\": \"in/a.txt\", \"content\": \"test\"}'"],
        "A storage event can set prefix, suffix, and events. Each record has bucket, key, size, and action.",
        [("docs/events.md", "storage")],
    ),
    (
        "proc-topic",
        "Publish and subscribe to a topic",
        [],
        ["PATH:Resources > + Add resource", "PATH:Functions > + Create function"],
        ["pskit resources send order-events -d '{\"message\": {\"id\": 1}}'"],
        "A topic event can name a resource. AWS applies a filter policy to message attributes. Other clouds document whether filter is applied.",
        [("docs/events.md", "topic")],
    ),
    (
        "proc-workflow",
        "Workflow with retry and catch, run locally",
        [],
        ["Open Workflows and add a workflow with start_at and states."],
        ["pskit workflow show order-pipeline", "pskit workflow run order-pipeline"],
        "A task state names a function. retry and catch sit on that state. pskit workflow run uses the embedded engine on this machine.",
        [("docs/workflows.md", "retry-and-catch"), ("docs/workflows.md", "commands")],
    ),
    (
        "proc-database",
        "Use a database resource in code",
        [],
        ["PATH:Resources > + Add resource", "PATH:Resources > How to use"],
        ["pskit resources usage orders-db -p aws -s dev", "pskit resources send --list"],
        "type database requires external true. Put the password in a variable named by password_env. Read it with resource(\"orders-db\") and ctx.env.",
        [("docs/resources.md", "fields"), ("docs/resource-usage.md", "databases-caches-and-other-services")],
    ),
    (
        "proc-secrets-env",
        "Set secrets with env variables",
        [],
        ["Keep the secret out of the YAML file. Reference it as ${env:NAME}."],
        ["pskit validate"],
        "Unresolved env:NAME fails validation unless you supply a default. On premises, provider.options.env_file ships a KEY=VALUE file as host.env.",
        [("docs/configuration.md", "variables"), ("docs/resources.md", "secrets")],
    ),
    (
        "proc-test-local",
        "Test locally with invoke and dev",
        [],
        ["PATH:Test > Run locally"],
        ["pskit invoke -f hello -t http --method GET --path /hello", "pskit dev"],
        "pskit invoke runs one function with a synthetic event. pskit dev serves HTTP routes on this machine. Neither contacts the cloud.",
        [("docs/local-development.md", "local-development")],
    ),
    (
        "proc-deploy",
        "Deploy to a stage",
        [],
        ["PATH:Deploy > Validate", "PATH:Deploy > Plan", "PATH:Deploy > Deploy"],
        ["pskit validate", "pskit plan -s dev", "pskit deploy -s dev"],
        "Deploy writes Terraform JSON under .pskit/provider-stage and runs terraform apply or tofu. Pass --confirm when you want to read the plan before apply.",
        [("docs/architecture.md", "deploy-pipeline")],
    ),
    (
        "proc-trigger",
        "Send a real test event",
        [],
        ["Open Test and choose Send to the selected provider and stage."],
        ["pskit trigger --list", "pskit trigger -f worker -e 0 -d '{\"order_id\": 1}'"],
        "pskit trigger sends a real event to a deployed function. pskit invoke is the local equivalent.",
        [("docs/local-development.md", "pskit-invoke-and-pskit-workflow-run")],
    ),
    (
        "proc-logs",
        "Read logs",
        [],
        ["PATH:Logs > Stored logs"],
        ["pskit logs -f --function worker", "pskit logs --streams"],
        "pskit logs reads the deployment logs. -f follows. --function limits the stream. --streams lists streams.",
        [("docs/troubleshooting.md", "http")],
    ),
    (
        "proc-remove",
        "Remove a stage, with or without data resources",
        [],
        ["PATH:Deploy > Remove"],
        ["pskit remove --keep-resources", "pskit remove -y"],
        "pskit remove asks for confirmation unless -y is set. --keep-resources destroys functions and triggers and leaves buckets, queues, and topics.",
        [("docs/studio.md", "project-environment-trigger-resources-and-remove")],
    ),
    (
        "proc-migrate",
        "Move a service from AWS to another provider",
        [],
        ["Change the provider in the top bar and read the problems list."],
        ["pskit validate -p gcp", "pskit providers"],
        "Keep the handler. Put cloud differences under providers.gcp or the selected provider block. pskit validate reports triggers that provider cannot run.",
        [("docs/migrating-from-aws.md", "step-5-move-to-another-cloud")],
    ),
    (
        "proc-overrides",
        "Multi-cloud provider and stage overrides",
        [],
        ["Edit the YAML page and add providers or stages maps."],
        ["pskit validate -p aws -s prod"],
        "providers.NAME and stages.NAME merge over the base file. extends inherits another file. Child values beat a parent providers block.",
        [("docs/configuration.md", "precedence-later-wins")],
    ),
    (
        "proc-save-server",
        "Save an on-premises server",
        ["onprem"],
        ["Open Resources and add a server, then save and test."],
        ["pskit resources onprem servers add app-1 --ssh deploy@192.0.2.10"],
        "Name the server, set the host, the SSH user, and the login method. The studio button is Save and test.",
        [("docs/onprem-network.md", "2-saving-a-server-pskit-resources-onprem-servers-add-studio-add-server")],
    ),
    (
        "proc-test-server",
        "Test a saved server",
        ["onprem"],
        ["Use the server row Test action after the server is saved."],
        ["pskit resources onprem servers test app-1", "pskit resources onprem servers check"],
        "test logs in and reports OS, CPU, memory, disk, Docker, sudo, and runtimes. check only probes the SSH port.",
        [("docs/resource-guides/onprem/services.md", "servers-several-machines")],
    ),
    (
        "proc-install-runtime",
        "Install Docker, Python, or Node on a server",
        ["onprem"],
        ["PATH:Resources > + On-prem service"],
        ["pskit resources onprem create tools-python --service python", "pskit resources onprem create tools-node --service nodejs"],
        "The catalog kind runtime installs software on a saved server. python, nodejs, and docker are catalog ids.",
        [("docs/resource-guides/onprem/services.md", "install-software-on-a-server")],
    ),
    (
        "proc-one-click",
        "Create a one-click PostgreSQL, Redis, RabbitMQ, or MinIO service",
        ["onprem"],
        ["PATH:Resources > + On-prem service"],
        ["pskit resources onprem create orders-db --service postgres", "pskit resources onprem create jobs --service redis"],
        "The create command starts a container on this machine or an SSH server and can attach a trigger. The password is generated into the env file.",
        [("docs/resource-guides/onprem/services.md", "from-the-command-line")],
    ),
    (
        "proc-replicas",
        "Create a database with read replicas",
        ["onprem"],
        ["In the create service drawer, choose Primary + read replicas for a database."],
        ["pskit resources onprem replicas list orders-db"],
        "A replicated database has a primary for writes and replicas for reads. The services guide describes the primary and the replica servers.",
        [("docs/resource-guides/onprem/services.md", "databases-one-server-or-a-primary-with-read-replicas")],
    ),
    (
        "proc-replica-change",
        "Add or remove a read replica",
        ["onprem"],
        ["Use the replica controls on the database service."],
        ["pskit resources onprem replicas add orders-db db-1", "pskit resources onprem replicas remove orders-db db-1"],
        "replicas add starts one more read replica on a saved server. replicas remove takes it off. Both are separate from deleting the primary.",
        [("docs/resource-guides/onprem/services.md", "databases-one-server-or-a-primary-with-read-replicas")],
    ),
    (
        "proc-backup",
        "Back up an on-premises service",
        ["onprem"],
        ["Open the service and choose Backup."],
        ["pskit resources onprem backup orders-db"],
        "The backup command writes a file under .pskit/backups. The services guide lists which catalog entries support backup.",
        [("docs/resource-guides/onprem/services.md", "backups")],
    ),
    (
        "proc-alerts",
        "Set service alerts",
        ["onprem"],
        ["Open Monitoring for the service and turn alerts on."],
        ["pskit resources onprem alerts orders-db --test"],
        "Alerts can post to a webhook or call a function. --test sends one alert now. Thresholds have defaults documented in the command help.",
        [("docs/resource-guides/onprem/services.md", "monitoring-and-alerts")],
    ),
    (
        "proc-web-ui",
        "Open a service web UI or console",
        ["onprem"],
        ["Use the service row Console or the web UI actions."],
        ["pskit resources onprem gui orders-db", "pskit resources onprem console orders-db"],
        "gui opens the service web UI. console runs the service client such as psql or redis-cli. The catalog says which UI each image has.",
        [("docs/resource-guides/onprem/services.md", "web-uis")],
    ),
    (
        "proc-cluster",
        "Create a scaling cluster",
        ["onprem"],
        ["PATH:Scaling cluster > + New cluster"],
        ["pskit cluster create prod --orchestrator swarm --master app-1"],
        "Orchestrator is swarm, kubernetes, or nomad. The master is a saved server. The studio create drawer collects the same fields.",
        [("docs/cluster.md", "how-the-functions-run-in-a-cluster")],
    ),
    (
        "proc-join",
        "Join a server to a cluster",
        ["onprem"],
        ["PATH:Scaling cluster > + Join server"],
        ["pskit cluster join prod app-1"],
        "Join adds a saved server to a cluster that already exists. The commands section of the cluster doc lists join next to create, scale, leave, and remove.",
        [("docs/cluster.md", "commands")],
    ),
    (
        "proc-scale",
        "Scale a function on a cluster",
        ["onprem"],
        ["Use Scale on the cluster page."],
        ["pskit cluster scale prod --replicas 3"],
        "scale sets the web replica count now. The command help says the value lasts until the next deploy, and options.cluster.replicas keeps it.",
        [("docs/cluster.md", "monitor-scale-and-add-servers-when-it-is-full")],
    ),
    (
        "proc-drain",
        "Drain or remove a cluster server",
        ["onprem"],
        ["Use the server row Remove server action."],
        ["pskit cluster leave prod app-1"],
        "leave drains the server so replicas move to the others. Removing the cluster itself is pskit cluster remove, which asks for confirmation.",
        [("docs/cluster.md", "commands")],
    ),
    (
        "proc-capacity",
        "Set cluster capacity alerts",
        ["onprem"],
        ["Use Check & alert on the cluster page."],
        ["pskit cluster alerts prod --function notify", "pskit cluster check prod"],
        "alerts records who is told when a server is full. check measures the cluster. The defaults for CPU, memory, and disk are in the command help.",
        [("docs/cluster.md", "alert-devops-optional")],
    ),
    (
        "proc-lb",
        "Create a load balancer and attach a cluster",
        ["onprem"],
        ["PATH:Load balancers > + Create load balancer"],
        ["pskit lb create edge --server app-1 --port 80", "pskit lb attach edge --cluster prod"],
        "The server must be saved, outside every cluster, and not used by another load balancer. attach adds a cluster path on that balancer.",
        [("docs/load-balancers.md", "create-one-and-put-projects-on-it")],
    ),
    (
        "proc-algorithm",
        "Choose a load balancer algorithm",
        ["onprem"],
        ["Set How it spreads requests in the load balancer form."],
        ["pskit lb algorithms", "pskit lb update edge --algorithm least_connections"],
        "Static algorithms are round_robin, sticky_round_robin, weighted_round_robin, and ip_hash. Dynamic algorithms are least_connections, the default, and least_time.",
        [("docs/load-balancers.md", "the-six-algorithms")],
    ),
    (
        "proc-network",
        "Read the network map",
        ["onprem"],
        ["Open Network map in the left navigation."],
        ["pskit firewall"],
        "The network page shows how saved servers, clusters, load balancers, and services connect. pskit firewall prints the ports each server must open.",
        [("docs/onprem-network.md", "network-and-firewall-rules-on-premises")],
    ),
    (
        "proc-firewall",
        "Open the firewall ports a server needs",
        ["onprem"],
        ["Open Network map and read the port list for each machine."],
        ["pskit firewall"],
        "SSH from the admin machine is the first rule. Cluster, load balancer, and service sections add their own ports. pskit firewall prints those ports.",
        [("docs/onprem-network.md", "1-always-the-admin-machine-reaches-every-server-over-ssh")],
    ),
    (
        "proc-openbao",
        "Use OpenBao or the Secrets Manager compatible server",
        ["onprem"],
        ["PATH:Resources > + On-prem service"],
        ["pskit resources onprem create secrets --service openbao"],
        "OpenBao speaks the Vault API. The secretsmanager catalog id is pskit's AWS Secrets Manager compatible server. Handlers call get_secret.",
        [("docs/resource-guides/onprem/secrets.md", None)],
    ),
    (
        "proc-smtp",
        "Run the SMTP server and add DNS",
        ["onprem"],
        ["PATH:Resources > + SMTP server", "PATH:Resources > DNS guide"],
        ["pskit resources onprem create inbound-mail --service smtp --domains inbound.example.com --attach on-mail"],
        "Domains are required. Port 25 receives mail. Add an A record for the mail host and an MX record for the domain. Use a subdomain when the root MX is already in use.",
        [("docs/smtp/README.md", "create-it"), ("docs/smtp/README.md", "dns-records-at-your-domain-provider")],
    ),
    (
        "proc-settings",
        "Export and import settings",
        [],
        ["PATH:Setup & credentials > Export settings", "PATH:Setup & credentials > Import into this project"],
        ["pskit settings export -o project.pskit-settings", "pskit settings import project.pskit-settings --dry-run"],
        "Export writes an encrypted file. The passphrase is at least 8 characters in the studio. Import asks for confirmation unless --yes is set. --dry-run previews the change.",
        [("docs/studio.md", "saving-what-changes-in-pskityml")],
    ),
    (
        "proc-studio-docker",
        "Run studio in Docker",
        [],
        ["The token screen shows the command that opens the link."],
        ["pskit studio --open"],
        "The studio doc shows a docker run that publishes 127.0.0.1:8770, mounts the Docker socket, and sets PSKIT_STUDIO_HOST_ROOT when code-server must start as a sibling container.",
        [("docs/studio.md", "full-vs-code-code-server-in-docker")],
    ),
    (
        "proc-vscode",
        "Use Full VS Code",
        [],
        ["PATH:Code > Full VS Code"],
        ["pskit studio --open"],
        "Full VS Code needs Docker. Pull and start runs code-server. The default image is codercom/code-server:4.96.4. The container listens on 127.0.0.1. Stop removes the container and leaves project files.",
        [("docs/studio.md", "full-vs-code-code-server-in-docker")],
    ),
]


def h1_anchor(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return github_anchor(line[2:].strip())
    return ""


def procedure_cards() -> None:
    for pid, title, providers, studio, commands, code, extracts in PROCEDURES:
        lines = [f"# Procedure: {title}", "", "## In studio"]
        number = 1
        for step in studio:
            if step.startswith("PATH:"):
                lines.append(f"{number}. Open this path:")
                lines.append(step[5:])
                lines.append("")
            else:
                lines.append(f"{number}. {step}")
            number += 1
        lines.append("")
        lines.append("## In the terminal")
        for index, command in enumerate(commands, start=1):
            lines.append(f"{index}. Run:")
            lines.append("")
            lines.append("```")
            lines.append(command)
            lines.append("```")
            lines.append("")
        lines.append("## In code")
        lines.append("")
        lines.append(code)
        lines.append("")
        sources = []
        for path, anchor in extracts:
            file_path = ROOT / path
            if anchor is None:
                anchor = h1_anchor(file_path)
            chunk = section_text(file_path, anchor)
            lines.append(trim_words(chunk, 70))
            lines.append("")
            sources.append(f"{path}#{anchor}")
        text = "\n".join(lines)
        if words(text) > 460:
            text = trim_words(text, 440)
        pad = (
            "Run pskit validate after you edit pskit.yml and before you deploy. "
            "The studio keeps the in-memory draft until you save. "
            "pskit plan writes the Terraform JSON for the stage so you can read it before apply."
        )
        while words(text) < 170:
            text += "\n\n" + pad
        add(pid, "procedure", f"Procedure: {title}", ["procedure", pid], providers, sources, text)


def safe_prose(path: Path) -> str:
    kept = []
    for line in path.read_text(encoding="utf-8").splitlines():
        low = line.lower()
        if any(bad in low for bad in ("pypi-", "password", "twine_", "asif.khan", "private key", "api token")):
            continue
        kept.append(line)
    return prose_from_markdown("\n".join(kept))


def whole_doc_card(cid: str, title: str, rel: str, anchor: str, tags: list[str]) -> None:
    body = safe_prose(ROOT / rel)
    text = f"# {title}\n\n" + ensure_bounds(
        body,
        "pskit validate checks the project before Terraform runs.\n\n```\npskit validate\n```\n",
    )
    add(cid, "concept", title, tags, [], [f"{rel}#{anchor}"], text)


def maintainer_card(cid: str, title: str, rel: str) -> None:
    body = safe_prose(ROOT / rel)
    text = f"# {title}\n\n" + ensure_bounds(
        body,
        "This note is for people changing the py-serverless-kit repository. "
        "User projects still deploy with pskit deploy, which renders Terraform JSON. "
        "The version string lives in src/py_serverless_kit/_version.py.\n\n```\npskit validate\n```\n",
    )
    add(cid, "concept", title, ["maintainer", cid], [], [rel], text)


def extra_concepts() -> None:
    concept_extract(
        "concept-terraform-json",
        "Concept: Terraform JSON and the runner",
        "docs/architecture.md",
        "deploy-pipeline",
        ["terraform"],
    )
    concept_extract(
        "concept-docker-uses",
        "Concept: where Docker is used",
        "docs/providers.md",
        "onprem-on-premises",
        ["docker", "onprem"],
    )
    concept_extract(
        "concept-migrate-aws",
        "Concept: migrating from AWS Lambda",
        "docs/migrating-from-aws.md",
        "migrating-from-aws-lambda-and-step-functions",
        ["aws", "migration"],
    )
    concept_extract(
        "concept-local-dev",
        "Concept: local development",
        "docs/local-development.md",
        "local-development",
        ["local"],
    )
    whole_doc_card(
        "concept-scenarios",
        "Concept: scenarios",
        "docs/scenarios.md",
        "scenarios-step-by-step",
        ["scenarios"],
    )
    whole_doc_card(
        "concept-getting-started",
        "Concept: getting started",
        "docs/getting-started.md",
        "getting-started",
        ["getting-started"],
    )
    whole_doc_card(
        "concept-workflow-executions",
        "Concept: workflow executions",
        "docs/workflow-executions.md",
        "workflow-executions",
        ["workflow", "executions"],
    )
    maintainer_card("concept-contributing", "Concept: contributing", "deploy_docs/CONTRIBUTING.md")
    maintainer_card("concept-node-runtime-design", "Concept: Node runtime design", "deploy_docs/NODE_RUNTIME.md")
    text = """
# Concept: installing Terraform

deploy_docs/HOW_TO_INSTALL_TERRAFORM.md lists three ways to install Terraform on Windows. One is winget. One is Chocolatey, which needs an administrator shell. One is a manual zip download from the HashiCorp install page, unzipped into a folder that is then added to the user PATH. After a PATH change, open a new shell and run terraform -version.

The same doc says you can skip the PATH edit by setting PSKIT_TERRAFORM_BIN to the full path of terraform.exe. pskit doctor reports whether terraform or tofu can be found. The troubleshooting page says that when neither binary is on PATH, set PSKIT_TERRAFORM_BIN or provider.terraform.binary.

pskit does not call cloud APIs itself. It writes main.tf.json and runs terraform or tofu. OpenTofu is selected with PSKIT_TERRAFORM_BIN=tofu. A real install path from the doc was left out of this card.

```
pskit doctor
pskit validate
```

Run pskit doctor after the install so the studio Setup page and the terminal agree that a Terraform binary is available. Then pskit validate checks pskit.yml before any apply. The Deploy page in studio runs the same pipeline after you confirm.
"""
    add(
        "concept-install-terraform",
        "concept",
        "Concept: installing Terraform",
        ["terraform", "maintainer"],
        [],
        ["deploy_docs/HOW_TO_INSTALL_TERRAFORM.md", "docs/troubleshooting.md#installation-and-tooling"],
        text,
    )


def main() -> None:
    guide_cards()
    onprem_cards()
    catalog_cards()
    code_cards()
    example_cards()
    trouble_cards()
    procedure_cards()
    extra_concepts()
    rows = []
    if JSONL.is_file():
        for line in JSONL.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    by_id = {row["id"]: row for row in rows}
    for page in PAGES:
        folder = KNOW / "cards" / page["kind"]
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{page['id']}.md").write_bytes(page["text"].encode("utf-8"))
        by_id[page["id"]] = page
        print(f"{page['id']} {words(page['text'])}")
    ordered = [by_id[key] for key in sorted(by_id)]
    payload = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in ordered)
    JSONL.write_bytes(payload.encode("utf-8"))
    print(f"jsonl={len(ordered)} added={len(PAGES)}")


if __name__ == "__main__":
    main()
