"""Typed model of ``pskit.yml``.

The model is intentionally provider-neutral. Anything that only makes sense
for one cloud goes under an ``options:`` mapping, which the matching provider
renderer reads and the others ignore.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple, Type, Union

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_validator

PROVIDERS = (
    "aws",
    "azure",
    "gcp",
    "alibaba",
    "oracle",
    "ibm",
    "digitalocean",
    "tencent",
    "huawei",
    "cloudflare",
    "onprem",
)
EVENT_TYPES = ("http", "schedule", "queue", "storage", "topic", "smtp")
RESOURCE_TYPES = ("storage", "queue", "topic", "database", "cache", "custom", "smtp")
# Resource types an event of the same name can consume.
EVENT_RESOURCE_TYPES = ("queue", "storage", "topic", "smtp")
_CONN_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,62}$")
_RESERVED_CONN_KEYS = ("type", "name", "external")
HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "ANY")
_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,62}$")
_HANDLER_RE = re.compile(r"^[A-Za-z_][\w]*(\.[A-Za-z_][\w]*)*[.:][A-Za-z_][\w]*$")
_RATE_RE = re.compile(r"^\s*(\d+)\s+(minute|minutes|hour|hours|day|days)\s*$", re.I)
PYTHON_RUNTIMES = tuple(f"python3.{minor}" for minor in range(9, 15))
NODE_RUNTIMES = ("nodejs18", "nodejs20", "nodejs22", "nodejs24")
LANGUAGES = ("python", "node")


def runtime_language(runtime: str) -> str:
    """``python`` for ``python3.x``, ``node`` for ``nodejsNN`` (JavaScript and TypeScript)."""
    return "node" if str(runtime).startswith("nodejs") else "python"


def _check_runtime(v: str) -> str:
    if v not in PYTHON_RUNTIMES and v not in NODE_RUNTIMES:
        raise ValueError(
            f"runtime must be python3.9 .. python3.14 or {', '.join(NODE_RUNTIMES)} (provider support varies)"
        )
    return v


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


# ------------------------------------------------------------------ events


class CorsConfig(_Model):
    origins: List[str] = Field(default_factory=lambda: ["*"])
    methods: Optional[List[str]] = None
    headers: Optional[List[str]] = None
    expose_headers: List[str] = Field(default_factory=list)
    allow_credentials: bool = False
    max_age: int = 600


class HttpEvent(_Model):
    path: str = "/"
    method: str = "GET"
    cors: Union[bool, CorsConfig] = False
    auth: Literal["none", "iam", "jwt", "key"] = "none"
    authorizer: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("method")
    @classmethod
    def _method(cls, v: str) -> str:
        v = v.upper()
        if v == "*":
            v = "ANY"
        if v not in HTTP_METHODS:
            raise ValueError(f"method must be one of {', '.join(HTTP_METHODS)}")
        return v

    @field_validator("path")
    @classmethod
    def _path(cls, v: str) -> str:
        v = "/" + v.strip().lstrip("/")
        if "{" in v and not re.fullmatch(r"(/([\w.~-]+|\{[A-Za-z_]\w*\}))*(/\{[A-Za-z_]\w*\+\})?/?", v):
            raise ValueError(f"invalid path template {v!r}; use /users/{{id}} or /files/{{path+}}")
        return v

    @property
    def cors_config(self) -> Optional[CorsConfig]:
        if self.cors is True:
            return CorsConfig()
        if isinstance(self.cors, CorsConfig):
            return self.cors
        return None


class ScheduleEvent(_Model):
    rate: Optional[str] = None
    cron: Optional[str] = None
    input: Any = None
    enabled: bool = True
    timezone: str = "UTC"
    name: Optional[str] = None

    @model_validator(mode="after")
    def _one_of(self) -> ScheduleEvent:
        if bool(self.rate) == bool(self.cron):
            raise ValueError("schedule needs exactly one of `rate` (e.g. '5 minutes') or `cron` (5 fields)")
        if self.rate and not _RATE_RE.match(self.rate):
            raise ValueError("rate must look like '<n> minutes|hours|days'")
        if self.cron and len(self.cron.split()) != 5:
            raise ValueError("cron must be a standard 5-field expression: 'min hour dom month dow'")
        return self


class QueueEvent(_Model):
    name: str = ""
    resource: Optional[str] = Field(None, description="key of a `resources:` entry of type queue")
    existing: bool = False
    batch_size: int = Field(10, ge=1, le=10000)
    batch_window: int = Field(0, ge=0, le=300, description="seconds to wait to fill a batch")
    visibility_timeout: Optional[int] = None
    dead_letter: Optional[str] = Field(None, description="queue name receiving messages after max_receive")
    max_receive: int = 5
    fifo: bool = False

    @model_validator(mode="after")
    def _source(self) -> QueueEvent:
        if not self.name and not self.resource:
            raise ValueError("queue event needs `name` or `resource`")
        return self


class StorageEvent(_Model):
    """``bucket`` alone, ``resource`` alone, or both: the bucket ``bucket`` on the storage service (endpoint,
    keys, driver) of resource ``resource``. Combining them is on-premises only."""

    bucket: str = ""
    resource: Optional[str] = Field(None, description="key of a `resources:` entry of type storage")
    existing: bool = False
    events: List[Literal["created", "deleted"]] = Field(default=["created"])
    prefix: Optional[str] = None
    suffix: Optional[str] = None

    @model_validator(mode="after")
    def _source(self) -> StorageEvent:
        if not self.bucket and not self.resource:
            raise ValueError("storage event needs `bucket` or `resource`")
        return self


class TopicEvent(_Model):
    name: str = ""
    resource: Optional[str] = Field(None, description="key of a `resources:` entry of type topic")
    existing: bool = False
    filter: Optional[Dict[str, Any]] = None

    @model_validator(mode="after")
    def _source(self) -> TopicEvent:
        if not self.name and not self.resource:
            raise ValueError("topic event needs `name` or `resource`")
        return self


class SmtpEvent(_Model):
    """Mail received by an ``smtp`` resource: the SMTP on-prem service, which posts every mail to the host."""

    resource: str = Field("", description="key of a `resources:` entry of type smtp")
    name: str = ""

    @model_validator(mode="after")
    def _source(self) -> SmtpEvent:
        if not self.resource:
            raise ValueError("smtp event needs `resource` (an smtp resource: the SMTP server that receives the mail)")
        return self


EventConfig = Union[HttpEvent, ScheduleEvent, QueueEvent, StorageEvent, TopicEvent, SmtpEvent]
_EVENT_MODELS: Dict[str, Type[BaseModel]] = {
    "http": HttpEvent,
    "schedule": ScheduleEvent,
    "queue": QueueEvent,
    "storage": StorageEvent,
    "topic": TopicEvent,
    "smtp": SmtpEvent,
}


class EventSpec(_Model):
    """One trigger. Written in YAML as a single-key mapping, e.g. ``- http: {path: /x}``."""

    type: Literal["http", "schedule", "queue", "storage", "topic", "smtp"]
    config: Any

    @model_validator(mode="before")
    @classmethod
    def _from_yaml(cls, raw: Any) -> Any:
        if isinstance(raw, dict) and set(raw) == {"type", "config"}:
            if isinstance(raw["config"], dict) and raw["type"] in _EVENT_MODELS:  # a dumped config
                return {"type": raw["type"], "config": _EVENT_MODELS[raw["type"]].model_validate(raw["config"])}
            return raw
        if not isinstance(raw, dict) or len(raw) != 1:
            raise ValueError(
                "each event must be a single-key mapping such as `- http: {path: /hello}`; got " + repr(raw)
            )
        ((kind, body),) = raw.items()
        if kind not in _EVENT_MODELS:
            raise ValueError(f"unknown event type {kind!r}; expected one of {', '.join(EVENT_TYPES)}")
        if kind == "http" and isinstance(body, str):  # shorthand: `- http: GET /users/{id}`
            method, _, path = body.strip().partition(" ")
            body = {"method": method, "path": path or "/"} if path else {"path": method}
        if kind == "schedule" and isinstance(body, str):  # shorthand: `- schedule: 5 minutes`
            body = {"rate": body} if _RATE_RE.match(body) else {"cron": body}
        if kind in ("queue", "topic") and isinstance(body, str):
            body = {"name": body}
        if kind == "storage" and isinstance(body, str):
            body = {"bucket": body}
        if kind == "smtp" and isinstance(body, str):  # shorthand: `- smtp: inbound-mail` (the resource key)
            body = {"resource": body}
        return {"type": kind, "config": _EVENT_MODELS[kind].model_validate(body or {})}


# ------------------------------------------------------------------ function / provider


class IamStatement(_Model):
    effect: Literal["Allow", "Deny"] = "Allow"
    actions: List[str]
    resources: List[str] = Field(default_factory=lambda: ["*"])


class IamConfig(_Model):
    statements: List[IamStatement] = Field(default_factory=list)
    role: Optional[str] = Field(None, description="use an existing role / service account instead of creating one")


class FunctionConfig(_Model):
    handler: str
    description: str = ""
    enabled: bool = Field(True, description="false keeps the function in pskit.yml but skips it on deploy")
    runtime: Optional[str] = None
    memory: Optional[int] = Field(None, ge=64, le=32768)
    timeout: Optional[int] = Field(None, ge=1, le=3600)
    environment: Dict[str, str] = Field(default_factory=dict)
    tags: Dict[str, str] = Field(default_factory=dict)
    events: List[EventSpec] = Field(default_factory=list)
    concurrency: Optional[int] = Field(None, ge=0, description="reserved / max instances")
    architecture: Optional[Literal["x86_64", "arm64"]] = None
    iam: IamConfig = Field(default_factory=IamConfig)
    options: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("runtime")
    @classmethod
    def _runtime(cls, v: Optional[str]) -> Optional[str]:
        return None if v is None else _check_runtime(v)

    @field_validator("handler")
    @classmethod
    def _handler(cls, v: str) -> str:
        if not _HANDLER_RE.match(v):
            raise ValueError(f"handler {v!r} must be 'package.module.function' (or 'module:function')")
        return v

    @field_validator("environment", mode="before")
    @classmethod
    def _env(cls, v: Any) -> Any:
        return {str(k): "" if val is None else str(val) for k, val in (v or {}).items()}

    def events_of(self, kind: str) -> List[Any]:
        return [e.config for e in self.events if e.type == kind]

    @property
    def kind(self) -> str:
        """Human label used by the dashboard: http / scheduled / event-driven / invoke-only."""
        types = {e.type for e in self.events}
        if not types:
            return "invoke-only"
        if types == {"http"}:
            return "http"
        if types == {"schedule"}:
            return "scheduled"
        if "http" in types:
            return "http+event"
        return "event-driven"


class StateBackend(_Model):
    backend: Optional[str] = Field(None, description="terraform backend type, e.g. s3, gcs, azurerm, http")
    config: Dict[str, Any] = Field(default_factory=dict)


class TerraformSettings(_Model):
    binary: Optional[str] = Field(None, description="terraform or tofu; default autodetect")
    required_version: str = ">= 1.5.0"
    provider_version: Optional[str] = None
    extra: Dict[str, Any] = Field(
        default_factory=dict, description="raw Terraform JSON deep-merged into the generated config"
    )


class ProviderConfig(_Model):
    # Built-in names are listed in PROVIDERS; third-party providers registered through the
    # `py_serverless_kit.providers` entry point are accepted too (checked by the loader).
    name: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,31}$")
    region: Optional[str] = None
    stage: str = "dev"
    runtime: str = "python3.12"
    memory: int = Field(256, ge=64, le=32768)
    timeout: int = Field(30, ge=1, le=3600)
    architecture: Literal["x86_64", "arm64"] = "x86_64"
    environment: Dict[str, str] = Field(default_factory=dict)
    tags: Dict[str, str] = Field(default_factory=dict)
    iam: IamConfig = Field(default_factory=IamConfig)
    log_retention_days: Optional[int] = 14
    options: Dict[str, Any] = Field(default_factory=dict)
    state: StateBackend = Field(default_factory=StateBackend)
    terraform: TerraformSettings = Field(default_factory=TerraformSettings)

    @field_validator("environment", mode="before")
    @classmethod
    def _env(cls, v: Any) -> Any:
        return {str(k): "" if val is None else str(val) for k, val in (v or {}).items()}

    @field_validator("runtime")
    @classmethod
    def _runtime(cls, v: str) -> str:
        return _check_runtime(v)

    @property
    def language(self) -> str:
        return runtime_language(self.runtime)

    @field_validator("stage")
    @classmethod
    def _stage(cls, v: str) -> str:
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,15}", v):
            raise ValueError("stage must be lowercase alphanumeric/dash, max 16 chars, e.g. dev, prod")
        return v


class NodePackageConfig(_Model):
    """How a Node.js / TypeScript service is built (``package.node``)."""

    install: Optional[bool] = Field(
        None, description="npm install production dependencies into the bundle (default: the provider decides)"
    )
    typescript: Optional[bool] = Field(
        None, description="compile .ts sources with tsc (default: when tsconfig.json or a .ts handler exists)"
    )
    build: Optional[List[str]] = Field(None, description="custom build command run before packaging, e.g. [npm, run, build]")
    out_dir: Optional[str] = Field(None, description="folder the build writes; bundled instead of package.source")
    bundle: Optional[bool] = Field(
        None, description="bundle each entry into one file with esbuild (default: only where the platform needs it)"
    )
    npm_args: List[str] = Field(default_factory=list)


class PackageConfig(_Model):
    source: str = "."
    include: List[str] = Field(default_factory=lambda: ["**/*"])
    exclude: List[str] = Field(default_factory=list)
    requirements: Optional[str] = "requirements.txt"
    pip_args: List[str] = Field(default_factory=list)
    vendor: Optional[bool] = Field(None, description="force (true) or skip (false) pip install into the bundle")
    node: NodePackageConfig = Field(default_factory=NodePackageConfig)


# ------------------------------------------------------------------ workflows

StateType = Literal["task", "choice", "wait", "pass", "parallel", "map", "succeed", "fail"]


class RetryRule(_Model):
    errors: List[str] = Field(default_factory=lambda: ["*"])
    max_attempts: int = Field(3, ge=0, le=99)
    interval_seconds: float = Field(1, ge=0)
    backoff_rate: float = Field(2.0, ge=1)
    max_delay_seconds: Optional[float] = None


class CatchRule(_Model):
    errors: List[str] = Field(default_factory=lambda: ["*"])
    next: str
    result_path: Optional[str] = "$.error"


class WorkflowState(_Model):
    model_config = ConfigDict(extra="forbid")

    type: StateType
    function: Optional[str] = None
    next: Optional[str] = None
    end: bool = False
    comment: Optional[str] = None
    input_path: Optional[str] = None
    result_path: Optional[str] = "$"
    retry: List[RetryRule] = Field(default_factory=list)
    catch: List[CatchRule] = Field(default_factory=list)
    timeout_seconds: Optional[int] = None
    # choice
    choices: List[Dict[str, Any]] = Field(default_factory=list)
    default: Optional[str] = None
    # wait
    seconds: Optional[float] = None
    seconds_path: Optional[str] = None
    # pass
    result: Any = None
    # parallel / map
    branches: List[WorkflowDefinition] = Field(default_factory=list)
    items_path: Optional[str] = None
    iterator: Optional[WorkflowDefinition] = None
    max_concurrency: Optional[int] = None
    # fail
    error: Optional[str] = None
    cause: Optional[str] = None

    @model_validator(mode="after")
    def _shape(self) -> WorkflowState:
        t = self.type
        if t == "task" and not self.function:
            raise ValueError("task state needs `function`")
        if t == "choice" and not self.choices:
            raise ValueError("choice state needs `choices`")
        if t == "wait" and self.seconds is None and not self.seconds_path:
            raise ValueError("wait state needs `seconds` or `seconds_path`")
        if t == "parallel" and not self.branches:
            raise ValueError("parallel state needs `branches`")
        if t == "map" and self.iterator is None:
            raise ValueError("map state needs `iterator`")
        if t in ("task", "wait", "pass", "parallel", "map") and not (self.next or self.end):
            self.end = True
        return self


class WorkflowDefinition(_Model):
    start_at: str
    states: Dict[str, WorkflowState]

    @model_validator(mode="after")
    def _graph(self) -> WorkflowDefinition:
        names = set(self.states)
        if self.start_at not in names:
            raise ValueError(f"start_at {self.start_at!r} is not a defined state")
        for name, st in self.states.items():
            targets = [st.next, st.default] + [c.next for c in st.catch] + [r.get("next") for r in st.choices]
            for target in targets:
                if target and target not in names:
                    raise ValueError(f"state {name!r} points to unknown state {target!r}")
            for rule in st.choices:
                if "next" not in rule:
                    raise ValueError(f"choice rule in {name!r} has no `next`: {rule}")
        return self

    def task_functions(self) -> List[str]:
        found: List[str] = []
        for st in self.states.values():
            if st.function:
                found.append(st.function)
            for branch in st.branches:
                found.extend(branch.task_functions())
            if st.iterator is not None:
                found.extend(st.iterator.task_functions())
        return found


class WorkflowConfig(WorkflowDefinition):
    description: str = ""
    enabled: bool = Field(True, description="false keeps the workflow in pskit.yml but skips it on deploy")
    engine: Literal["auto", "native", "embedded"] = "auto"
    timeout: Optional[int] = None
    options: Dict[str, Any] = Field(default_factory=dict)


WorkflowState.model_rebuild()


# ------------------------------------------------------------------ resources


GENERATED_HANDLER_PREFIXES = ("py_serverless_kit.", "pskit_runtime.")


def is_generated_handler(handler: str) -> bool:
    """Handlers pskit adds itself (embedded workflow orchestrators, Python or Node.js)."""
    return handler.startswith(GENERATED_HANDLER_PREFIXES)


def env_key(text: str) -> str:
    """``my-bucket`` -> ``MY_BUCKET`` (the form used in ``PSKIT_RESOURCE_<KEY>_*`` variables)."""
    return re.sub(r"[^A-Za-z0-9]", "_", text).upper()


class ResourceConfig(_Model):
    """A storage bucket, queue, topic, database, cache or any other service functions use.

    ``external: true`` means it already exists (or runs outside pskit): pskit never
    creates or destroys it and only hands its connection details to handlers.
    """

    type: Literal["storage", "queue", "topic", "database", "cache", "custom", "smtp"]
    external: bool = False
    name: Optional[str] = Field(None, description="native name; defaults to the resource key")
    connection: Dict[str, Any] = Field(default_factory=dict, description="values exposed to handlers")
    functions: Optional[List[str]] = Field(None, description="functions that get the binding (default: all)")
    options: Dict[str, Any] = Field(default_factory=dict, description="provider-specific settings")

    @field_validator("connection", mode="before")
    @classmethod
    def _connection(cls, v: Any) -> Any:
        if v is None:
            return {}
        if not isinstance(v, dict):
            raise ValueError("connection must be a mapping of names to scalar values")
        out: Dict[str, str] = {}
        for raw_key, val in v.items():
            key = str(raw_key)
            if not _CONN_KEY_RE.match(key):
                raise ValueError(f"connection key {key!r} must start with a letter and use letters, digits or _")
            if key.lower() in _RESERVED_CONN_KEYS:
                raise ValueError(f"connection key {key!r} is reserved (set `{key.lower()}` on the resource itself)")
            if isinstance(val, (dict, list)):
                raise ValueError(f"connection.{key} must be a scalar (string, number or boolean)")
            if isinstance(val, bool):
                out[key] = "true" if val else "false"
            else:
                out[key] = "" if val is None else str(val)
        lowered = [k.lower() for k in out]
        if len(set(lowered)) != len(lowered):
            raise ValueError("connection keys must be unique ignoring case")
        return out

    @model_validator(mode="after")
    def _managed(self) -> ResourceConfig:
        if self.type not in EVENT_RESOURCE_TYPES and not self.external:
            raise ValueError(
                f"pskit does not create `{self.type}` resources; set `external: true` and describe it in `connection`"
            )
        return self

    def conn(self, key: str, default: str = "") -> str:
        """Connection value by case-insensitive key."""
        for k, v in self.connection.items():
            if k.lower() == key.lower():
                return str(v)
        return default

    def native_name(self, key: str) -> str:
        """Bucket / queue / topic name in the cloud: ``name``, else the tail of ``connection.arn``, else the key."""
        if self.name:
            return self.name
        arn = self.conn("arn")
        if arn:
            return arn.rsplit(":", 1)[-1]
        return key


# ------------------------------------------------------------------ root


class ServiceConfig(_Model):
    service: str
    provider: ProviderConfig
    package: PackageConfig = Field(default_factory=PackageConfig)
    functions: Dict[str, FunctionConfig] = Field(default_factory=dict)
    workflows: Dict[str, WorkflowConfig] = Field(default_factory=dict)
    resources: Dict[str, ResourceConfig] = Field(default_factory=dict)
    hooks: Dict[str, List[str]] = Field(default_factory=dict)
    custom: Dict[str, Any] = Field(default_factory=dict, description="free-form values for ${self:custom.x}")
    _disabled: Dict[str, List[str]] = PrivateAttr(default_factory=dict)

    @field_validator("service")
    @classmethod
    def _service(cls, v: str) -> str:
        if not re.fullmatch(r"[a-z][a-z0-9-]{1,31}", v):
            raise ValueError("service must be 2-32 chars of lowercase letters, digits and dashes")
        return v

    @field_validator("functions", "workflows", "resources")
    @classmethod
    def _names(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        for name in v:
            if not _NAME_RE.match(name):
                raise ValueError(f"name {name!r} must start with a letter and use letters, digits, - or _")
        return v

    @field_validator("hooks")
    @classmethod
    def _hooks(cls, v: Dict[str, List[str]]) -> Dict[str, List[str]]:
        allowed = {"before_package", "after_package", "before_deploy", "after_deploy", "before_remove", "after_remove"}
        unknown = set(v) - allowed
        if unknown:
            raise ValueError(f"unknown hooks {sorted(unknown)}; allowed: {sorted(allowed)}")
        return v

    @field_validator("resources")
    @classmethod
    def _resource_keys(cls, v: Dict[str, ResourceConfig]) -> Dict[str, ResourceConfig]:
        seen: Dict[str, str] = {}
        for name in v:
            key = env_key(name)
            if key in seen:
                raise ValueError(f"resources {seen[key]!r} and {name!r} map to the same variable prefix {key}")
            seen[key] = name
        return v

    @property
    def language(self) -> str:
        """``python`` or ``node``: one language per service (from ``provider.runtime``)."""
        return self.provider.language

    @model_validator(mode="after")
    def _one_language(self) -> ServiceConfig:
        for name, fn in self.functions.items():
            if fn.runtime and runtime_language(fn.runtime) != self.provider.language:
                raise ValueError(
                    f"function {name!r} uses {fn.runtime} but the service runtime is {self.provider.runtime}; "
                    "a service is either Python or Node.js"
                )
        return self

    @model_validator(mode="after")
    def _drop_disabled(self) -> ServiceConfig:
        """Leave out functions and workflows with ``enabled: false`` (e.g. under ``providers.<cloud>``)."""
        functions = [name for name, fn in self.functions.items() if not fn.enabled]
        workflows = [name for name, wf in self.workflows.items() if not wf.enabled]
        self._disabled = {"functions": functions, "workflows": workflows}
        if functions:
            self.functions = {k: v for k, v in self.functions.items() if v.enabled}
            for res in self.resources.values():
                if res.functions is not None:
                    res.functions = [f for f in res.functions if f not in functions]
        if workflows:
            self.workflows = {k: v for k, v in self.workflows.items() if v.enabled}
        return self

    @property
    def disabled(self) -> Dict[str, List[str]]:
        """``{"functions": [...], "workflows": [...]}`` left out with ``enabled: false``."""
        return {key: list(self._disabled.get(key, [])) for key in ("functions", "workflows")}

    @model_validator(mode="after")
    def _cross_refs(self) -> ServiceConfig:
        self._resolve_resources()
        off = set(self._disabled.get("functions", []))
        for wf_name, wf in self.workflows.items():
            for fn in wf.task_functions():
                if fn in off:
                    raise ValueError(
                        f"workflow {wf_name!r} calls function {fn!r}, which is disabled; disable the workflow too"
                    )
                if fn not in self.functions:
                    raise ValueError(f"workflow {wf_name!r} references unknown function {fn!r}")
        seen: Dict[str, str] = {}
        for fn_name, fn_cfg in self.functions.items():
            for ev in fn_cfg.events_of("http"):
                key = f"{ev.method} {ev.path.rstrip('/') or '/'}"
                if key in seen:
                    raise ValueError(f"route {key} is used by both {seen[key]!r} and {fn_name!r}")
                seen[key] = fn_name
        return self

    def _resolve_resources(self) -> None:
        orchestrators = {f"{w}-orchestrator" for w in self.workflows}
        for res_name, declared in self.resources.items():
            for fn in declared.functions or []:
                if fn not in self.functions and fn not in orchestrators:
                    raise ValueError(f"resource {res_name!r} lists unknown function {fn!r}")
        for fn_name, fn_cfg in self.functions.items():
            for ev in fn_cfg.events:
                if ev.type not in EVENT_RESOURCE_TYPES or not ev.config.resource:
                    continue
                key = ev.config.resource
                res = self.resources.get(key)
                if res is None:
                    known = ", ".join(sorted(self.resources)) or "<none>"
                    raise ValueError(f"function {fn_name!r} uses unknown resource {key!r}; known: {known}")
                if res.type != ev.type:
                    raise ValueError(
                        f"function {fn_name!r} has a {ev.type} event on resource {key!r}, which is a {res.type}"
                    )
                if ev.type == "smtp":  # the server is the resource; nothing is "existing" about it
                    ev.config.name = res.native_name(key)
                    continue
                attr = "bucket" if ev.type == "storage" else "name"
                native = res.native_name(key)
                current = getattr(ev.config, attr)
                if ev.type == "storage" and current and current != native:
                    # Another bucket on the resource's storage service (providers that cannot say so reject it).
                    ev.config.existing = res.external
                    continue
                if current and current != native:
                    raise ValueError(
                        f"function {fn_name!r}: set either `{attr}` or `resource` on the {ev.type} event, not both"
                    )
                setattr(ev.config, attr, native)
                ev.config.existing = res.external

    def resources_for(self, fn_name: str) -> List[Tuple[str, ResourceConfig]]:
        """``[(key, resource)]`` bound to function ``fn_name``, sorted by key.

        Without ``functions:`` a resource is bound to every user function but not to
        generated ones (embedded workflow orchestrators).
        """
        fn = self.functions.get(fn_name)
        generated = fn is not None and is_generated_handler(fn.handler)
        out: List[Tuple[str, ResourceConfig]] = []
        for key, res in sorted(self.resources.items()):
            if res.functions is None:
                if not generated:
                    out.append((key, res))
            elif fn_name in res.functions:
                out.append((key, res))
        return out

    def binding_environment(
        self,
        fn_name: str,
        refs: Optional[Callable[[str, ResourceConfig], Dict[str, str]]] = None,
    ) -> Dict[str, str]:
        """``PSKIT_RESOURCES`` and ``PSKIT_RESOURCE_<KEY>_*`` variables for function ``fn_name``.

        ``refs`` adds provider-known values (``ARN``, ``URL``, ``ID``); connection
        entries with the same key win.
        """
        bound = self.resources_for(fn_name)
        if not bound:
            return {}
        env = {"PSKIT_RESOURCES": ",".join(key for key, _ in bound)}
        for key, res in bound:
            prefix = f"PSKIT_RESOURCE_{env_key(key)}_"
            env[prefix + "TYPE"] = res.type
            env[prefix + "NAME"] = res.native_name(key)
            env[prefix + "EXTERNAL"] = "true" if res.external else "false"
            for ckey, value in res.connection.items():
                env[prefix + env_key(ckey)] = str(value)
            for field_name, value in (refs(key, res) if refs else {}).items():
                env.setdefault(prefix + env_key(field_name), value)
        return env

    def resource_functions(self, key: str) -> List[str]:
        """Functions bound to resource ``key``."""
        return [name for name in sorted(self.functions) if any(k == key for k, _ in self.resources_for(name))]

    def event_resources(self) -> Dict[str, List[str]]:
        """``{resource key: [function names]}`` for resources consumed by an event."""
        used: Dict[str, List[str]] = {}
        for fn_name, fn_cfg in sorted(self.functions.items()):
            for ev in fn_cfg.events:
                if ev.type in EVENT_RESOURCE_TYPES and ev.config.resource:
                    used.setdefault(ev.config.resource, []).append(fn_name)
        return used

    # convenience -----------------------------------------------------
    def memory_of(self, fn: FunctionConfig) -> int:
        return fn.memory or self.provider.memory

    def timeout_of(self, fn: FunctionConfig) -> int:
        return fn.timeout or self.provider.timeout

    def runtime_of(self, fn: FunctionConfig) -> str:
        return fn.runtime or self.provider.runtime

    def architecture_of(self, fn: FunctionConfig) -> str:
        return fn.architecture or self.provider.architecture
