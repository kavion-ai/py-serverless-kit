"""What an account may do: create / read / update / delete per feature, for the studio and for the CLI.

Anything not listed is refused for non-admins: a new route or command stays admin-only until it is added here.
"""

from __future__ import annotations

from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Sequence, Tuple

from .errors import VaultError

ACTIONS = "crud"
_PROJECT_SECTIONS = ("functions", "workflows", "resources")
# Not a feature, so no account can be granted it: only the admin role passes.
ADMIN_ONLY: Tuple[str, str] = ("admin", "u")

# name -> (label, what it covers, full_access). full_access features reach everything the process can reach, so CRUD
# on other features does not limit an account that holds one.
FEATURES: Dict[str, Tuple[str, str, bool]] = {
    "project": ("Project settings", "pskit.yml outside functions, workflows and resources (everyone can read it)", False),
    "functions": ("Functions", "create, change or delete functions and their triggers in pskit.yml", False),
    "workflows": ("Workflows", "create, change or delete workflows in pskit.yml", False),
    "code": ("Code", "Source files in the project", False),
    "env": ("Env files", ".env and .env.* (read decrypts them)", False),
    "deploy": ("Deployments", "create = deploy, delete = remove, read = plan and info. Decrypts Terraform state and tokens only", False),
    "test": ("Test", "Invoke functions, trigger events, run workflows, saved test events", False),
    "logs": ("Logs", "Function and host logs", False),
    "resources": ("Resources", "Resources in pskit.yml, and using them: list, send, inspect, clear, delete", False),
    "services": ("On-prem services", "Databases, caches, queues and their passwords (read decrypts them)", False),
    "servers": ("Servers", "Saved servers and SSH logins (read decrypts them)", False),
    "clusters": ("Clusters", "Scaling clusters (read decrypts them)", False),
    "balancers": ("Load balancers", "Shared load balancers (read decrypts them)", False),
    "network": ("Network", "Firewall and network map", False),
    "settings": ("Settings", "Setup, credentials, browsing folders, settings export and import", False),
    "shell": ("Terminals & VS Code", "Server terminals, shells and VS Code: FULL ACCESS to all they can reach", True),
    "hana": ("Hana AI", "The assistant runs project and deploy tools itself: FULL ACCESS", True),
    "users": ("Users", "Accounts and permissions", False),
    "audit": ("Audit log", "Read who did what", False),
}

# The areas of encrypted data; holding read on a feature gets the key of its area.
AREA_OF_FEATURE: Dict[str, str] = {
    "env": "env",
    "servers": "servers",
    "services": "services",
    "clusters": "clusters",
    "balancers": "clusters",
    "test": "studio",
    "hana": "studio",
}
AREAS: Tuple[str, ...] = ("env", "servers", "services", "clusters", "deployments", "studio")

PRESETS: Dict[str, Dict[str, str]] = {
    # No read on deploy: that decrypts Terraform state and tokens, so a viewer holds no keys at all.
    "viewer": {"project": "r", "functions": "r", "workflows": "r", "code": "r", "logs": "r", "resources": "r"},
    "developer": {
        "project": "ru", "functions": "crud", "workflows": "crud", "code": "crud", "test": "crud", "logs": "r",
        "resources": "r", "deploy": "r",
    },
    "operator": {
        "project": "ru", "functions": "crud", "workflows": "crud", "code": "crud", "env": "cru", "deploy": "crud",
        "test": "crud", "logs": "r",
        "resources": "crud", "services": "crud", "servers": "crud", "clusters": "crud", "balancers": "crud",
        "network": "r",
    },
}


def project_needs(old: Any, new: Any) -> Tuple[List[Tuple[str, str]], List[str]]:
    """What saving ``new`` over ``old`` takes, and what it changes. A new function is create, a removed one delete, a
    changed one update; the rest of pskit.yml is update on project. Same rules as ``permissions.ts`` in the studio."""
    if not isinstance(old, dict) or not isinstance(new, dict):
        return [("project", "u")], ["pskit.yml"]
    needs: List[Tuple[str, str]] = []
    changes: List[str] = []

    def add(feature: str, action: str, change: str) -> None:
        if (feature, action) not in needs:
            needs.append((feature, action))
        changes.append(change)

    for key in sorted(set(old) | set(new), key=str):
        before, after = old.get(key), new.get(key)
        if before == after:
            continue
        if key not in _PROJECT_SECTIONS:
            add("project", "u", f"changed {key}")
        elif isinstance(before or {}, dict) and isinstance(after or {}, dict):
            before, after = before or {}, after or {}
            for name in sorted(set(before) | set(after), key=str):
                if name not in before:
                    add(key, "c", f"created {key}.{name}")
                elif name not in after:
                    add(key, "d", f"deleted {key}.{name}")
                elif before[name] != after[name]:
                    add(key, "u", f"changed {key}.{name}")
        else:
            add(key, "u", f"changed {key}")
    return needs, changes


def clean(perms: Any) -> Dict[str, str]:
    """Validate ``{feature: "crud" subset}``; the result is sorted, so it diffs and compares cleanly."""
    if not isinstance(perms, dict):
        raise VaultError("permissions must be an object of feature -> letters from crud")
    out: Dict[str, str] = {}
    for feature, letters in perms.items():
        if feature not in FEATURES:
            raise VaultError(f"unknown feature: {feature}")
        if not isinstance(letters, str) or any(c not in ACTIONS for c in letters):
            raise VaultError(f"permissions of {feature} must be letters from crud")
        kept = "".join(c for c in ACTIONS if c in letters)
        if kept:
            out[str(feature)] = kept
    return dict(sorted(out.items()))


def allowed(user: Dict[str, Any], feature: str, action: str) -> bool:
    if user.get("disabled"):
        return False
    if user.get("role") == "admin":
        return True
    if feature == "project" and action == "r":
        return True
    return action in str((user.get("permissions") or {}).get(feature) or "")


def areas_for(user: Dict[str, Any]) -> FrozenSet[str]:
    """The encrypted areas whose key this account holds."""
    if user.get("disabled"):
        return frozenset()
    if user.get("role") == "admin":
        return frozenset(AREAS)
    perms = user.get("permissions") or {}
    areas = {area for feature, area in AREA_OF_FEATURE.items() if "r" in str(perms.get(feature) or "")}
    if perms.get("deploy"):  # its own area only: servers, env and the rest need read on their own feature
        areas.add("deployments")
    return frozenset(areas)


def writable_areas(user: Dict[str, Any]) -> FrozenSet[str]:
    """The areas this account's saves are sealed into; a read-only account's local edits are not."""
    if user.get("disabled"):
        return frozenset()
    if user.get("role") == "admin":
        return frozenset(AREAS)
    perms = user.get("permissions") or {}
    out = {area for feature, area in AREA_OF_FEATURE.items() if set(str(perms.get(feature) or "")) & set("cud")}
    if set(str(perms.get("deploy") or "")) & set("cud"):
        out.add("deployments")
    return frozenset(out & areas_for(user))


# ------------------------------------------------------------------------------- studio routes
_READ_VERBS = frozenset({
    "status", "check", "test", "usage", "logs", "metrics", "reachability", "requests", "monitor", "preview",
    "gui-check", "alert-check", "balancer-logs",
})
_DELETE_VERBS = frozenset({"remove", "forget", "gui-remove", "replicas-remove", "balancer-remove", "route-remove"})
_BROWSE_READS = frozenset({
    "buckets", "list", "head", "versions", "get", "share",
})
_MACHINE_FEATURES = {
    "onprem-services": "services",
    "onprem-servers": "servers",
    "onprem-clusters": "clusters",
    "onprem-balancers": "balancers",
}
_READS: Dict[str, Tuple[str, str]] = {
    "discover": ("resources", "r"),
    "test-guide": ("test", "r"),
    "resource-test-guide": ("resources", "r"),
    "cloud-resources": ("resources", "r"),
    "resource-guides": ("resources", "r"),
    "resource-bindings": ("resources", "r"),
    "onprem-firewall": ("network", "r"),
    "onprem-usage": ("network", "r"),
    "fs": ("settings", "r"),
}
_RESOURCE_POSTS: Dict[str, str] = {
    "resource-check": "r", "resource-usage": "r", "resource-data": "r", "resource-object": "r",
    "resource-clear": "d", "resource-message-delete": "d",
}
_JOB_COMMANDS: Dict[str, Tuple[str, str]] = {
    "validate": ("project", "r"),
    "package": ("deploy", "r"),
    "plan": ("deploy", "r"),
    "deploy": ("deploy", "c"),
    "remove": ("deploy", "d"),
    "info": ("deploy", "r"),
    "invoke": ("test", "c"),
    "workflow-run": ("test", "c"),
    "trigger": ("test", "c"),
    "resources-delete": ("resources", "d"),
    "resource-send": ("resources", "u"),
}


def job_permission(command: str) -> Tuple[str, str]:
    return _JOB_COMMANDS.get(command, ADMIN_ONLY)


def _crud(method: str) -> str:
    return {"GET": "r", "PUT": "u", "DELETE": "d", "POST": "c"}[method]


def studio_permission(method: str, parts: Sequence[str]) -> Optional[Tuple[str, str]]:
    """The (feature, action) a studio API call needs. None: decided elsewhere (any account, or per job command)."""
    if method not in ("GET", "PUT", "POST", "DELETE") or not parts:
        return ADMIN_ONLY
    head, rest = parts[0], list(parts[1:])
    if head == "meta":
        return None
    if head in _READS and method == "GET":
        return _READS[head]
    if head in _RESOURCE_POSTS and not rest and method == "POST":
        return "resources", _RESOURCE_POSTS[head]
    if head == "project":
        if rest in (["validate"], ["parse"]) and method == "POST":
            return "project", "r"
        if rest == ["init"] and method == "POST":
            return "project", "c"
        return ("project", _crud(method)) if not rest and method in ("GET", "PUT") else ADMIN_ONLY
    if head == "files":
        if rest == ["tree"] and method == "GET":
            return "code", "r"
        return ("code", _crud(method)) if not rest and method in ("GET", "PUT") else ADMIN_ONLY
    if head == "handlers":
        return ("code", "c") if rest == ["ensure"] and method == "POST" else ADMIN_ONLY
    if head == "functions":
        if rest == ["shared"] and method == "GET":
            return "code", "r"
        return ("code", "u") if len(rest) == 2 and rest[1] == "split" and method == "POST" else ADMIN_ONLY
    if head == "test-events":
        return ("test", _crud(method)) if not rest and method in ("GET", "PUT") else ADMIN_ONLY
    if head == "logs":
        if rest == ["delete"] and method == "POST":
            return "logs", "d"
        return ("logs", "r") if method == "GET" else ADMIN_ONLY
    if head == "env":
        return ("settings", "r" if method == "GET" else "u") if not rest or rest == ["setup"] else ADMIN_ONLY
    if head == "setup":
        return "settings", "r" if method == "GET" else "u"
    if head in ("vscode", "onprem-terminals"):
        return "shell", "r" if method == "GET" else "u"
    if head == "hana":
        return "hana", "r" if method == "GET" else "u"
    if head == "workflow-test":
        if method == "GET" and (not rest or len(rest) == 1):
            return "test", "r"
        if method == "POST" and not rest:
            return "test", "c"
        if method == "POST" and len(rest) == 2 and rest[1] == "cancel":
            return "test", "u"
        return ADMIN_ONLY
    if head == "jobs":
        if method == "DELETE":
            return "deploy", "d"
        if method == "POST" and len(rest) == 2 and rest[1] == "cancel":
            return "deploy", "u"
        return None if (method == "POST" and not rest) or method == "GET" else ADMIN_ONLY
    feature = _MACHINE_FEATURES.get(head)
    if feature:
        return _machine_permission(feature, method, rest)
    return ADMIN_ONLY


def _machine_permission(feature: str, method: str, rest: List[str]) -> Tuple[str, str]:
    if method != "POST":
        return feature, _crud(method)
    if not rest:
        return feature, "c"
    if len(rest) >= 3 and rest[1] == "browse":  # a data browser: reading rows or changing them
        return feature, "r" if rest[-1] in _BROWSE_READS else "u"
    verb = rest[-1]
    if verb == "shell":
        return "shell", "u"
    if verb in _READ_VERBS:
        return feature, "r"
    if verb in _DELETE_VERBS:
        return feature, "d"
    return feature, "u"


# ------------------------------------------------------------------------------- CLI commands
OPEN_COMMANDS = frozenset({"login", "logout", "whoami", "vault", "studio", "doctor", "providers"})

_CLI: Dict[str, Tuple[str, str]] = {
    "init": ("project", "c"),
    "validate": ("project", "r"),
    "package": ("deploy", "r"),
    "plan": ("deploy", "r"),
    "deploy": ("deploy", "c"),
    "remove": ("deploy", "d"),
    "trigger": ("test", "c"),
    "info": ("deploy", "r"),
    "dashboard": ("deploy", "r"),
    "dev": ("code", "r"),
    "invoke": ("test", "c"),
    "logs": ("logs", "r"),
    "tf": ("deploy", "u"),
    "firewall": ("network", "u"),
    "function split": ("code", "u"),
    "workflow run": ("test", "c"),
    "workflow start": ("test", "c"),
    "workflow show": ("test", "r"),
    "workflow executions": ("test", "r"),
    "workflow status": ("test", "r"),
    "workflow cancel": ("test", "u"),
    "settings export": ("settings", "r"),
    "settings import": ("settings", "u"),
    "client info": ("deploy", "r"),
    "client tunnel": ("deploy", "r"),
    "client install-node": ("project", "u"),
    "resources list": ("resources", "r"),
    "resources check": ("resources", "r"),
    "resources usage": ("resources", "r"),
    "resources data": ("resources", "r"),
    "dlq list": ("resources", "r"),
    "dlq inspect": ("resources", "r"),
    "dlq replay": ("resources", "u"),
    "resources send": ("resources", "u"),
    "resources clear": ("resources", "d"),
    "resources delete": ("resources", "d"),
    "resources onprem catalog": ("services", "r"),
    "resources onprem create": ("services", "c"),
    "resources onprem replicas list": ("services", "r"),
    "resources onprem replicas add": ("services", "c"),
    "resources onprem replicas remove": ("services", "d"),
    "resources onprem monitor": ("services", "r"),
    "resources onprem alerts": ("services", "r"),
    "resources onprem list": ("services", "r"),
    "resources onprem status": ("services", "r"),
    "resources onprem usage": ("services", "r"),
    "resources onprem tunnel": ("services", "r"),
    "resources onprem gui": ("services", "u"),
    "resources onprem logs": ("services", "r"),
    "resources onprem backup": ("services", "u"),
    "resources onprem remove": ("services", "d"),
    "resources onprem console": ("shell", "u"),
    "resources onprem shell": ("shell", "u"),
    "resources onprem terminal": ("shell", "u"),
    "resources onprem ssh-key": ("servers", "r"),
    "resources onprem servers list": ("servers", "r"),
    "resources onprem servers check": ("servers", "r"),
    "resources onprem servers top": ("servers", "r"),
    "resources onprem servers usage": ("servers", "r"),
    "resources onprem servers test": ("servers", "r"),
    "resources onprem servers add": ("servers", "c"),
    "resources onprem servers remove": ("servers", "d"),
    "cluster list": ("clusters", "r"),
    "cluster status": ("clusters", "r"),
    "cluster check": ("clusters", "r"),
    "cluster watch": ("clusters", "r"),
    "cluster alerts": ("clusters", "r"),
    "cluster requests": ("clusters", "r"),
    "cluster create": ("clusters", "c"),
    "cluster set": ("clusters", "u"),
    "cluster join": ("clusters", "u"),
    "cluster leave": ("clusters", "u"),
    "cluster scale": ("clusters", "u"),
    "cluster remove": ("clusters", "d"),
    "cluster balancer set": ("clusters", "u"),
    "cluster balancer sync": ("clusters", "u"),
    "cluster balancer logs": ("clusters", "r"),
    "cluster balancer remove": ("clusters", "d"),
    "lb algorithms": ("balancers", "r"),
    "lb list": ("balancers", "r"),
    "lb status": ("balancers", "r"),
    "lb logs": ("balancers", "r"),
    "lb create": ("balancers", "c"),
    "lb update": ("balancers", "u"),
    "lb attach": ("balancers", "u"),
    "lb detach": ("balancers", "u"),
    "lb sync": ("balancers", "u"),
    "lb routes remove": ("balancers", "u"),
    "lb remove": ("balancers", "d"),
    "lb forget": ("balancers", "d"),
}


def cli_permission(path: Iterable[str]) -> Tuple[str, str]:
    """The permission of a CLI command, given its words. Unknown commands are admin-only."""
    return _CLI.get(" ".join(path), ADMIN_ONLY)


def catalog() -> List[Dict[str, Any]]:
    return [{"name": name, "label": v[0], "help": v[1], "full_access": v[2]} for name, v in FEATURES.items()]
