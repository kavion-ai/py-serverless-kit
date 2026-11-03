"""``GET /api/meta``: the catalog that drives every studio form.

Everything comes from the code that validates and renders a project: the
provider registry, the pydantic models in ``config/schema.py``, the workflow
engine and the on-prem driver catalog. The UI hardcodes none of it.
"""

from __future__ import annotations

import typing
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel
from pydantic_core import PydanticUndefined

from .._version import __version__
from ..config import schema
from ..providers.onprem_catalog import DRIVER_CATALOG, field
from ..providers.onprem_spec import INSTALLS, METHODS, NODE_MODES, PYTHON_MODES, TARGET_ARCH, TARGET_OS
from .node_stubs import NODE_TEMPLATES

# --------------------------------------------------------------------- pydantic → Field

_HELP = {
    "http.path": "Path template, e.g. /users/{id} or /files/{path+}.",
    "http.cors": "Enable CORS with defaults (allow all origins).",
    "http.auth": "none, iam (cloud IAM), jwt (needs authorizer issuer/audience) or key.",
    "http.authorizer": "JWT settings, e.g. {issuer: ..., audience: [...]}.",
    "schedule.rate": "e.g. '5 minutes', '1 hour', '1 day'. Set rate or cron, not both.",
    "schedule.cron": "Standard 5-field cron: 'min hour dom month dow'.",
    "schedule.input": "JSON passed to the handler as event.data.",
    "schedule.timezone": "IANA timezone for cron schedules.",
    "queue.name": "Queue name (pskit prefixes managed names). Or pick a resource.",
    "queue.resource": "A `resources:` entry of type queue.",
    "queue.existing": "The queue already exists; pskit attaches to it and never deletes it.",
    "queue.batch_size": "Messages per invocation.",
    "queue.batch_window": "Seconds to wait to fill a batch.",
    "queue.dead_letter": "Queue receiving messages that failed max_receive times.",
    "storage.bucket": "Bucket name. Or pick a resource; on-premises, both: this bucket on the resource's service.",
    "storage.resource": "A `resources:` entry of type storage (on-premises: the storage service it connects to).",
    "storage.existing": "The bucket already exists; pskit attaches to it and never deletes it.",
    "storage.prefix": "Only keys starting with this.",
    "storage.suffix": "Only keys ending with this, e.g. .csv.",
    "topic.name": "Topic name. Or pick a resource.",
    "topic.resource": "A `resources:` entry of type topic.",
    "topic.filter": "Attribute filter, e.g. {event_type: [created]}.",
    "function.handler": "module.function, e.g. app.handlers.process.",
    "function.runtime": "Overrides provider.runtime for this function.",
    "function.concurrency": "Reserved / maximum concurrent instances.",
    "function.options": "Provider-specific settings for this function.",
    "function.iam": "Extra IAM statements, or {role: existing-role}.",
    "resource.external": "Already exists (or runs elsewhere): pskit never creates or deletes it.",
    "resource.name": "Native name. Managed default: the resource key.",
    "resource.connection": "Values exposed to handlers (PSKIT_RESOURCE_<KEY>_<NAME>). Pass secrets as ${env:VAR}.",
    "resource.functions": "Functions that get the binding (default: all).",
    "resource.options": "Provider-specific settings, e.g. the on-prem driver.",
}


_ENUMS: Dict[str, Tuple[str, ...]] = {
    "http.method": schema.HTTP_METHODS,
    "function.runtime": tuple(f"python3.{minor}" for minor in range(9, 15)),
}

_SUGGEST: Dict[str, List[Any]] = {
    "queue.batch_size": [1, 5, 10, 25, 100, 1000],
    "queue.batch_window": [0, 5, 10, 30, 60, 300],
    "queue.visibility_timeout": [30, 60, 120, 300, 900],
    "queue.max_receive": [1, 3, 5, 10],
    "storage.prefix": ["uploads/", "incoming/", "images/"],
    "storage.suffix": [".csv", ".json", ".jpg", ".png", ".pdf", ".zip"],
    "function.memory": [128, 256, 512, 1024, 2048, 4096],
    "function.timeout": [3, 10, 30, 60, 300, 900],
}


def suggest(item: Dict[str, Any], values: List[Any]) -> Dict[str, Any]:
    """Offer ``values`` in a dropdown; the user can still type another value."""
    return dict(item, suggestions=list(values))


def _unwrap(annotation: Any) -> Tuple[Any, bool]:
    """Strip Optional[...]; return (inner, was_optional)."""
    args = typing.get_args(annotation)
    if typing.get_origin(annotation) is typing.Union and type(None) in args:
        rest = [a for a in args if a is not type(None)]
        return (rest[0] if len(rest) == 1 else typing.Union[tuple(rest)]), True
    return annotation, False


def _kind(annotation: Any) -> Tuple[str, Optional[List[Any]]]:
    origin = typing.get_origin(annotation)
    if origin is typing.Literal:
        return "enum", list(typing.get_args(annotation))
    if origin in (list, List):
        item = (typing.get_args(annotation) or (Any,))[0]
        inner = typing.get_origin(item)
        if inner is typing.Literal:
            return "list", list(typing.get_args(item))
        return "list", None
    if origin in (dict, Dict):
        return "map", None
    if origin is typing.Union:
        args = typing.get_args(annotation)
        if bool in args:
            return "bool", None  # e.g. http.cors: true or a CORS mapping
        return "json", None
    if annotation is bool:
        return "bool", None
    if annotation is int:
        return "int", None
    if annotation is float:
        return "number", None
    if annotation is str:
        return "string", None
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return "json", None
    return "json", None


def _limits(info: Any) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for item in getattr(info, "metadata", []) or []:
        for attr, key in (("ge", "min"), ("gt", "min"), ("le", "max"), ("lt", "max")):
            value = getattr(item, attr, None)
            if value is not None:
                out[key] = value
    return out


def _default(info: Any) -> Any:
    if info.default is not PydanticUndefined:
        value = info.default
    elif info.default_factory is not None:
        value = info.default_factory()
    else:
        return None
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return value


def model_fields(model: Any, scope: str, skip: Tuple[str, ...] = ()) -> List[Dict[str, Any]]:
    fields: List[Dict[str, Any]] = []
    for key, info in model.model_fields.items():
        if key in skip:
            continue
        annotation, optional = _unwrap(info.annotation)
        kind, options = _kind(annotation)
        if f"{scope}.{key}" in _ENUMS:
            kind, options = "enum", list(_ENUMS[f"{scope}.{key}"])
        default = _default(info)
        item = field(
            key,
            type=kind,
            required=info.is_required() and not optional,
            default=default,
            options=options,
            help=_HELP.get(f"{scope}.{key}") or (info.description or ""),
            **_limits(info),  # type: ignore[arg-type]
        )
        if f"{scope}.{key}" in _SUGGEST:
            item = suggest(item, _SUGGEST[f"{scope}.{key}"])
        fields.append(item)
    return fields


# --------------------------------------------------------------------- providers



MEMORY_SIZES = [128, 256, 512, 1024, 1536, 2048, 3008, 4096, 8192, 10240]
TIMEOUTS = [3, 10, 30, 60, 120, 300, 600, 900]
STAGES = ["dev", "test", "staging", "prod"]

_COMMON_PROVIDER = [
    field("region", "Region", help="Cloud region (default per provider)."),
    suggest(field("stage", "Stage", default="dev", help="dev, staging, prod... (lowercase, max 16 chars)."), STAGES),
    field("runtime", "Runtime", "enum", help="Python version (provider support varies)."),
    suggest(field("memory", "Memory (MB)", "int", default=256, min=64, max=32768), MEMORY_SIZES),
    suggest(field("timeout", "Timeout (s)", "int", default=30, min=1, max=3600), TIMEOUTS),
    field("architecture", "Architecture", "enum", default="x86_64", options=["x86_64", "arm64"]),
    field("environment", "Environment", "map", help="Variables for every function. Use ${env:VAR} for secrets."),
    field("tags", "Tags", "map"),
    field("log_retention_days", "Log retention (days)", "int", default=14, min=1),
]

PROVIDER_OPTIONS: Dict[str, List[Dict[str, Any]]] = {
    "aws": [
        field("artifact_bucket", "Artifact bucket", help="Existing bucket for code uploads (default: one is created)."),
        field("artifact_upload", "Artifact upload", "enum", default="s3", options=["s3", "direct"]),
        field("assume_role_arn", "Assume role ARN", help="Role Terraform assumes to deploy."),
    ],
    "azure": [
        field(
            "subscription_id",
            "Subscription ID",
            required=True,
            default="${env:ARM_SUBSCRIPTION_ID}",
            help="Or set ARM_SUBSCRIPTION_ID.",
        ),
        field("resource_group", "Resource group", help="Existing resource group (default: one is created)."),
        suggest(
            field("plan_sku", "Plan SKU", default="Y1", help="Y1 = consumption, EP* = elastic premium, B/S/P = dedicated."),
            ["Y1", "EP1", "EP2", "EP3", "B1", "B2", "B3", "S1", "S2", "P1v3", "P2v3"],
        ),
        field("app_insights", "Application Insights", "bool", default=True),
        field(
            "storage_connection",
            "Storage connection setting",
            help="App-setting name for existing queues / buckets in another account.",
        ),
        field("servicebus_namespace_id", "Service Bus namespace ID", help="For existing topics."),
        field("servicebus_connection", "Service Bus connection setting", help="For existing topics."),
    ],
    "gcp": [
        field("project", "Project", required=True, default="${env:GOOGLE_CLOUD_PROJECT}", help="GCP project id."),
        field("service_account", "Service account", help="Existing service account email."),
    ],
    "alibaba": [field("profile", "CLI profile", help="Alibaba Cloud CLI profile with credentials.")],
    "oracle": [
        field("compartment_id", "Compartment OCID", required=True, default="${env:OCI_COMPARTMENT_ID}"),
        field("subnet_ids", "Subnet OCIDs", "list", required=True),
        field("image", "Function image", help="Pre-built image (or set image_repository)."),
        field("image_repository", "Image repository", help="Build and push with local Docker."),
        field("gateway_subnet_id", "Gateway subnet OCID"),
        field(
            "gateway_endpoint_type", "Gateway endpoint type", "enum", default="PUBLIC", options=["PUBLIC", "PRIVATE"]
        ),
    ],
    "ibm": [
        suggest(field("resource_group", "Resource group"), ["Default"]),
        field("resource_group_id", "Resource group ID"),
        field("project_id", "Code Engine project ID", help="Existing project (default: one is created)."),
        field("code_reference", "Code reference", help="Image / bundle reference for Code Engine."),
        field("visibility", "Visibility", "enum", default="public", options=["public", "private", "project"]),
    ],
    "digitalocean": [
        field(
            "namespace",
            "Functions namespace",
            required=True,
            default="${env:DO_FUNCTIONS_NAMESPACE}",
            help="See `doctl serverless namespaces list`.",
        ),
        field("api_host", "API host"),
    ],
    "tencent": [
        suggest(field("namespace", "SCF namespace", default="default"), ["default"]),
        field("profile", "CLI profile"),
    ],
    "huawei": [
        suggest(field("app", "FunctionGraph app", default="default"), ["default"]),
        field("apig_instance_id", "APIG instance ID", help="Dedicated API Gateway instance."),
    ],
    "cloudflare": [
        field("account_id", "Account ID", required=True, default="${env:CLOUDFLARE_ACCOUNT_ID}"),
        field("zone_id", "Zone ID", help="Needed for routes."),
        field("route", "Route", placeholder="api.example.com/*"),
        field("workers_dev", "workers.dev subdomain", "bool", default=True),
        field("workers_subdomain", "workers.dev account subdomain"),
        field("compatibility_date", "Compatibility date", placeholder="2024-09-23"),
    ],
    "onprem": [
        suggest(
            field("host", "Bind address", default="127.0.0.1", help="0.0.0.0 to accept LAN traffic."),
            ["127.0.0.1", "0.0.0.0"],  # noqa: S104 - offered choices, not a bind
        ),
        suggest(field("port", "Port", "int", default=8080, min=1, max=65535), [80, 8000, 8080, 8443, 9000]),
        field("advertise", "Advertised URL", placeholder="https://fn.internal.example"),
        field("data_dir", "Data directory", placeholder=".pskit/onprem-data"),
        field("poll_seconds", "Poll interval (s)", "number", default=0.5, min=0.05),
        field(
            "admin_token",
            "Admin token",
            "secret",
            default="${env:PSKIT_ADMIN_TOKEN, }",
            help="Header x-pskit-token required on /__pskit/* (except health).",
        ),
    ],
}


def _tuning() -> List[Dict[str, Any]]:
    from ..providers.onprem import _TUNING

    defaults = {
        "execution_retention": 500,
        "workflow_workers": 8,
        "log_buffer": 5000,
        "log_level": "INFO",
        "capture_output": True,
    }
    out = []
    for key, (kind, low) in _TUNING.items():
        if kind == "int":
            out.append(field(key, type="int", default=defaults.get(key), min=low))
        elif kind == "bool":
            out.append(field(key, type="bool", default=defaults.get(key)))
        else:
            out.append(
                field(
                    key,
                    type="enum",
                    default=defaults.get(key),
                    options=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                )
            )
    return out


def _deploy_fields() -> Dict[str, List[Dict[str, Any]]]:
    python = field(
        "python",
        "Python",
        "enum",
        default="auto",
        options=list(PYTHON_MODES),
        help="bundle ships a portable CPython for hosts without Python.",
    )
    node = [
        field(
            "node",
            "Node.js",
            "enum",
            default="auto",
            options=list(NODE_MODES),
            help="Node.js services only: system = node on the server, bundle = ship an official Node.js build.",
        ),
        field("node_url", "Node.js archive URL", help="Mirror of a nodejs.org archive (bundle)."),
        field("node_sha256", "Node.js archive SHA-256"),
        suggest(
            field("host_python", "Host Python", default="python3.12", help="Interpreter of the host process (Node.js services)."),
            [f"python3.{m}" for m in range(14, 8, -1)],
        ),
    ]
    target = [
        field("target_os", "Target OS", "enum", default="auto", options=list(TARGET_OS)),
        field("target_arch", "Target arch", "enum", default="auto", options=list(TARGET_ARCH)),
    ]
    ssh_common = [
        field("host", "SSH host", required=True, placeholder="10.0.1.12"),
        suggest(field("user", "SSH user", default="pskit"), ["pskit", "ubuntu", "ec2-user", "admin", "opc", "root"]),
        suggest(field("port", "SSH port", "int", default=22, min=1, max=65535), [22, 2222]),
        field(
            "pem",
            "Private key",
            "file",
            placeholder="~/.ssh/server.pem",
            help="Pick the key file (.pem, id_rsa, id_ed25519...). Empty: your SSH agent / default keys.",
        ),
        suggest(
            field("known_hosts", "Known hosts", default="accept-new", help="accept-new, ignore, or a file path."),
            ["accept-new", "ignore"],
        ),
        field("sudo", "Use sudo", "bool", default=False),
    ]
    return {
        "local": [python, *target, *node],
        "ssh": [
            *ssh_common,
            field("path", "Remote path", placeholder="/opt/pskit/<service>-<stage>"),
            field("install", "Install as", "enum", default="process", options=list(INSTALLS)),
            python,
            *target,
            field("python_url", "CPython archive URL"),
            field("python_sha256", "CPython archive SHA-256"),
            *node,
        ],
        "docker": [
            field("image", "Image", placeholder="pskit-<service>-<stage>:<stage>"),
            field("container", "Container name"),
            field("docker_host", "Docker host", placeholder="ssh://user@server or tcp://..."),
            suggest(
                field("restart", "Restart policy", default="unless-stopped"),
                ["no", "always", "unless-stopped", "on-failure"],
            ),
            suggest(field("publish", "Publish", placeholder="8080:8080"), ["8080:8080", "80:8080", "443:8443"]),
            field("docker_args", "Extra docker args", "list"),
            *[dict(f, required=False) for f in ssh_common],
            field("install_docker", "Install Docker on the server", "bool", default=True),
            *target,
        ],
    }


HANDLER_TEMPLATES: Dict[str, str] = {
    "http": '''

def {func}(event: Event, ctx: Context):
    """HTTP handler: event.http has method, path, query, path_params, headers and json().

    Also called from a workflow step or invoke(): then event.http is None and event.data is the input."""
    if event.http is None:
        return {{"message": "Hello, world!", "input": event.data}}
    name = event.http.query.get("name", "world")
    return {{"message": f"Hello, {{name}}!"}}
''',
    "schedule": '''

def {func}(event: Event, ctx: Context):
    """Scheduled job: event.data is the schedule's `input`."""
    ctx.logger.info("tick", extra={{"input": event.data}})
''',
    "queue": '''

def {func}(event: Event, ctx: Context) -> BatchResult:
    """Queue consumer: failed records are retried, then dead-lettered."""
    result = BatchResult()
    for record in event.records:
        try:
            ctx.logger.info("message", extra={{"id": record.id, "body": record.text()}})
        except Exception:  # noqa: BLE001 - retry only this record
            result.fail(record)
    return result
''',
    "storage": '''

def {func}(event: Event, ctx: Context):
    """Storage trigger: one record per created / deleted object."""
    for record in event.records:
        ctx.logger.info("object", extra={{"bucket": record.bucket, "key": record.key, "action": record.action}})
''',
    "topic": '''

def {func}(event: Event, ctx: Context):
    """Topic subscriber: record.attributes holds the message attributes."""
    for record in event.records:
        ctx.logger.info("published", extra={{"id": record.id, "body": record.text()}})
''',
    "invoke": '''

def {func}(event: Event, ctx: Context):
    """Called with invoke("<name>", data) or from a workflow: event.data is the payload."""
    return {{"ok": True, "input": event.data}}
''',
    "workflow": '''

def {func}(event: Event, ctx: Context):
    """Workflow task: return the state's output (it becomes the next state's input)."""
    data = dict(event.data or {{}})
    data["{func}"] = "done"
    return data
''',
}
# Stored as format strings above for readability; served with a literal __FUNC__ placeholder.
HANDLER_TEMPLATES = {
    kind: text.replace("{func}", "__FUNC__").replace("{{", "{").replace("}}", "}").lstrip()
    for kind, text in HANDLER_TEMPLATES.items()
}
TEMPLATE_IMPORTS: Dict[str, Tuple[str, ...]] = {
    "queue": ("BatchResult", "Context", "Event"),
}


# --------------------------------------------------------------------- trigger support per provider

# (field, value shown in the UI, event config) tried against every provider's own validation.
_BASE_EVENTS: Dict[str, Dict[str, Any]] = {
    "http": {"path": "/probe"},
    "schedule": {"rate": "5 minutes"},
    "queue": {"name": "probe-jobs"},
    "storage": {"bucket": "probe-uploads"},
    "topic": {"name": "probe-events"},
}
_PROBES: Dict[str, List[Tuple[str, Any, Dict[str, Any]]]] = {
    "http": [
        ("auth", "iam", {"auth": "iam"}),
        ("auth", "jwt", {"auth": "jwt", "authorizer": {"issuer": "https://issuer.example", "audience": ["api"]}}),
        ("auth", "key", {"auth": "key"}),
        ("cors", True, {"cors": True}),
        ("method", "ANY", {"method": "ANY"}),
    ],
    "schedule": [
        ("cron", "0 9 * * *", {"rate": None, "cron": "0 9 * * *"}),
        ("timezone", "Europe/Berlin", {"rate": None, "cron": "0 9 * * *", "timezone": "Europe/Berlin"}),
        ("enabled", False, {"enabled": False}),
    ],
    "queue": [
        ("fifo", True, {"fifo": True}),
        ("dead_letter", "probe-dlq", {"dead_letter": "probe-dlq"}),
        ("batch_window", 5, {"batch_window": 5}),
        ("batch_size", 100, {"batch_size": 100}),
        ("visibility_timeout", 60, {"visibility_timeout": 60}),
        ("existing", True, {"existing": True}),
    ],
    "storage": [
        ("events", "deleted", {"events": ["created", "deleted"]}),
        ("prefix", "uploads/", {"prefix": "uploads/"}),
        ("suffix", ".csv", {"suffix": ".csv"}),
        ("existing", True, {"existing": True}),
    ],
    "topic": [
        ("filter", {"kind": ["created"]}, {"filter": {"kind": ["created"]}}),
        ("existing", True, {"existing": True}),
    ],
}


def _probe_issues(provider: Any, name: str, event: str, config: Dict[str, Any]) -> List[Tuple[str, str]]:
    options = {f["key"]: "probe" for f in PROVIDER_OPTIONS.get(name, []) if f.get("required") and f["type"] != "list"}
    options.update({f["key"]: ["probe"] for f in PROVIDER_OPTIONS.get(name, []) if f.get("required") and f["type"] == "list"})
    raw = {
        "service": "probe",
        "provider": {"name": name, "runtime": provider.default_runtime, "options": options},
        "functions": {"probe": {"handler": "app.probe", "events": [{event: {k: v for k, v in config.items() if v is not None}}]}},
    }
    try:
        cfg = schema.ServiceConfig.model_validate(raw)
        issues = provider.validate(cfg)
    except Exception as exc:  # noqa: BLE001 - a rejected value is itself the answer
        return [("error", str(exc).splitlines()[-1] if str(exc) else type(exc).__name__)]
    return [(i.level, i.message) for i in issues if i.where.startswith("functions.probe")]


def trigger_support(provider: Any, name: str) -> Dict[str, List[Dict[str, Any]]]:
    """Which trigger options this provider rejects (error) or ignores (warning), from its own validation."""
    out: Dict[str, List[Dict[str, Any]]] = {}
    for event, probes in _PROBES.items():
        if event not in provider.capabilities:
            continue
        base = dict(_BASE_EVENTS[event])
        baseline = set(_probe_issues(provider, name, event, base))
        rules: List[Dict[str, Any]] = []
        for key, value, change in probes:
            found = [i for i in _probe_issues(provider, name, event, {**base, **change}) if i not in baseline]
            if not found:
                continue
            level, message = next((i for i in found if i[0] == "error"), found[0])
            rules.append({"key": key, "value": value, "level": level, "message": message})
        out[event] = rules
    return out


def build_meta() -> Dict[str, Any]:
    from ..cli.templates import DEFAULT_REGIONS
    from ..providers.regions import REGIONS
    from ..providers.registry import available, get_provider
    from ..runtime.workflow import CHOICE_OPERATORS

    providers = []
    for name in available():
        try:
            prov = get_provider(name)
        except Exception:  # noqa: BLE001, S112 - a broken plug-in must not break the studio
            continue
        desc = prov.describe()
        providers.append(
            {
                "name": name,
                "display_name": desc["display_name"],
                "tier": desc["tier"],
                "default_region": DEFAULT_REGIONS.get(name) or desc.get("default_region") or "",
                "capabilities": desc["capabilities"],
                "runtimes": desc["runtimes"] or [f"python3.{m}" for m in range(9, 15)],
                "node_runtimes": list(desc.get("node_runtimes") or []),
                "default_runtime": prov.default_runtime,
                "max_timeout": desc["max_timeout"],
                "storage_service_buckets": bool(desc.get("storage_service_buckets")),
                "notes": desc["notes"],
                "options": PROVIDER_OPTIONS.get(name, []),
                "regions": REGIONS.get(name, []),
                "trigger_support": trigger_support(prov, name),
            }
        )
    events = {
        "http": model_fields(schema.HttpEvent, "http"),
        "schedule": model_fields(schema.ScheduleEvent, "schedule"),
        "queue": model_fields(schema.QueueEvent, "queue"),
        "storage": model_fields(schema.StorageEvent, "storage"),
        "topic": model_fields(schema.TopicEvent, "topic"),
        "smtp": model_fields(schema.SmtpEvent, "smtp"),
    }
    state_types = list(typing.get_args(schema.StateType))
    return {
        "version": __version__,
        "providers": providers,
        "provider_fields": _COMMON_PROVIDER,
        "events": events,
        "function_fields": model_fields(schema.FunctionConfig, "function", skip=("events",)),
        "resource_fields": model_fields(schema.ResourceConfig, "resource"),
        "resource_types": list(schema.RESOURCE_TYPES),
        "event_resource_types": list(schema.EVENT_RESOURCE_TYPES),
        "http_methods": list(schema.HTTP_METHODS),
        "auth_modes": list(typing.get_args(schema.HttpEvent.model_fields["auth"].annotation)),
        "workflow": {
            "state_types": state_types,
            "choice_operators": list(CHOICE_OPERATORS),
            "engines": list(typing.get_args(schema.WorkflowConfig.model_fields["engine"].annotation)),
            "state_fields": model_fields(schema.WorkflowState, "state", skip=("branches", "iterator")),
            "retry_fields": model_fields(schema.RetryRule, "retry"),
            "catch_fields": model_fields(schema.CatchRule, "catch"),
        },
        "onprem": {
            "deploy_methods": list(METHODS),
            "deploy_fields": _deploy_fields(),
            "tuning": _tuning(),
            "services": ["schedule", "queue", "storage", "topic", "workflow"],
            "drivers": DRIVER_CATALOG,
        },
        "handler_templates": dict(HANDLER_TEMPLATES),
        "node_handler_templates": {k: v.lstrip("\n") for k, v in NODE_TEMPLATES.items()},
    }
