"""Azure: Linux Function App (Consumption plan, Python v2 / Node.js v4 programming model).

One Function App hosts every function of a service. The bundle carries a
generated ``function_app.py`` that registers a decorated wrapper per trigger:

* ``http``     -> ``@app.route`` (``host.json`` sets ``routePrefix`` to ``""`` so the
  configured paths are served as-is, without Azure's default ``/api`` prefix);
* ``schedule`` -> ``@app.timer_trigger`` (NCRONTAB, always UTC on Linux Consumption);
* ``queue``    -> Storage Queue in the app's storage account;
* ``storage``  -> Blob trigger on a container in the app's storage account (created only);
* ``topic``    -> Service Bus topic + one subscription per function.

Node.js services get a generated ``pskit_entry.js`` (``app.http()``, ``app.timer()``, ...
of ``@azure/functions`` v4) with the same functions and routes instead.

Dependencies are installed by the remote Oryx build (``requirements.txt`` / ``package.json``).
Workflows run on the embedded engine (an ``<name>-orchestrator`` HTTP function) by
default. ``engine: native`` compiles them to an Azure Logic App (Consumption) with an
HTTP request trigger (see :mod:`py_serverless_kit.workflows.azure_logic`); its task
states call ``/_pskit/invoke/<function>`` on the Function App with the host's function key.

``azurerm`` >= 4 requires a subscription id: set ``provider.options.subscription_id``
or the ``ARM_SUBSCRIPTION_ID`` environment variable.

Options: ``subscription_id``, ``resource_group`` (existing), ``plan_sku`` (default Y1),
``app_insights`` (default true), ``storage_connection`` (app-setting name for
``existing`` queues / buckets in another account), ``servicebus_namespace_id`` and
``servicebus_connection`` (for ``existing`` topics).
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from ..config.schema import ServiceConfig, WorkflowConfig
from ..workflows import definition_dict
from ..workflows.azure_logic import HTTP_TIMEOUT, LogicAppsError, compile_logic_app
from . import schedule as sched
from .base import (
    HTTP,
    QUEUE,
    SCHEDULE,
    STORAGE,
    TOPIC,
    WORKFLOW_NATIVE,
    Issue,
    Provider,
    ProviderError,
    RenderContext,
    stable_suffix,
)
from .terraform_doc import TerraformDoc, escape, ref, tf_id

APP = "azurerm_linux_function_app"
_PER_FUNCTION_ENV = ("PSKIT_FUNCTION", "PSKIT_HANDLER")
_STORAGE_NAME = re.compile(r"^[a-z0-9](?!.*--)[a-z0-9-]{1,61}[a-z0-9]$")
DEFAULT_CONNECTION = "AzureWebJobsStorage"
SERVICEBUS_SETTING = "PSKIT_SERVICEBUS"
NODE_ENTRY = "pskit_entry.js"
NODE_HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")


def py_ident(text: str) -> str:
    ident = re.sub(r"\W", "_", text)
    return ident if re.match(r"[A-Za-z]", ident) else "f_" + ident


def azure_route(path: str) -> str:
    route = path.strip("/")
    return re.sub(r"\{(\w+)\+\}", r"{*\1}", route)


def _hms(seconds: int) -> str:
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


class AzureProvider(Provider):
    name = "azure"
    display_name = "Azure Functions"
    tier = "stable"
    terraform_source = "hashicorp/azurerm"
    terraform_version = ">= 4.9"
    terraform_local_name = "azurerm"
    default_region = "eastus"
    capabilities = frozenset({HTTP, SCHEDULE, QUEUE, STORAGE, TOPIC, WORKFLOW_NATIVE})
    max_name_length = 60
    name_pattern = r"[^a-z0-9-]"
    runtimes = {f"python3.{v}": f"3.{v}" for v in (9, 10, 11, 12)}
    # application_stack.node_version of azurerm_linux_function_app.
    node_runtimes = {f"nodejs{v}": str(v) for v in (18, 20, 22)}
    vendor_dependencies = False
    node_vendor_dependencies = False  # remote (Oryx) build runs npm install from package.json
    extra_requirements = ["azure-functions"]
    max_timeout = 600
    standalone_resources = True
    notes = (
        "Linux Consumption Function App, Python v2 model. Workflows use the embedded engine; "
        "`engine: native` compiles them to Azure Logic Apps (opt-in)."
    )

    # ------------------------------------------------------------------ workflows
    def workflow_engine(self, wf: WorkflowConfig) -> str:
        # Logic Apps are opt-in: `auto` keeps the embedded engine so existing projects don't change.
        if wf.engine == "auto":
            return "embedded"
        return super().workflow_engine(wf)

    def native_tasks(self, config: ServiceConfig) -> List[str]:
        """Functions called by Logic Apps task states (they need the invoke route)."""
        found: set = set()
        for wf in config.workflows.values():
            try:
                if self.workflow_engine(wf) == "native":
                    found.update(wf.task_functions())
            except ProviderError:
                continue
        return sorted(found)

    # ------------------------------------------------------------------ naming
    def app_name(self, service: str, stage: str) -> str:
        base = self.physical_name(service, stage, "")
        return f"{base[:51].rstrip('-')}-{stable_suffix(service, stage, 'func', length=8)}"

    # ------------------------------------------------------------------ bundle
    def node_package(self, config: ServiceConfig) -> Dict[str, Any]:
        """Fields merged into the bundled package.json of a Node.js service."""
        return {"main": NODE_ENTRY, "dependencies": {"@azure/functions": "^4.5.0"}}

    def registrations(self, config: ServiceConfig) -> List[Dict[str, Any]]:
        """One entry per Azure function to register (trigger + logical function), in a stable order."""
        opts = config.provider.options
        used: set = set()

        def unique(base: str) -> str:
            ident = py_ident(base)
            candidate, n = ident, 1
            while candidate.lower() in used:
                n += 1
                candidate = f"{ident}_{n}"
            used.add(candidate.lower())
            return candidate

        out: List[Dict[str, Any]] = []
        tasks = set(self.native_tasks(config))
        for name, fn in sorted(config.functions.items()):
            for i, ev in enumerate(fn.events):
                c = ev.config
                item: Dict[str, Any] = {"ident": unique(f"{name}_{ev.type}_{i}"), "kind": ev.type, "function": name}
                if ev.type == "http":
                    item.update(route=azure_route(c.path), method=c.method, auth="FUNCTION" if c.auth == "key" else "ANONYMOUS")
                elif ev.type == "schedule":
                    item.update(schedule=sched.ncrontab(c), input=c.input)
                elif ev.type in ("queue", "storage"):
                    conn = opts.get("storage_connection", DEFAULT_CONNECTION) if c.existing else DEFAULT_CONNECTION
                    if ev.type == "queue":
                        item.update(queue=c.name, connection=conn)
                    else:
                        path = f"{c.bucket}/{c.prefix or ''}{{name}}{c.suffix or ''}"
                        item.update(path=path, bucket=c.bucket, connection=conn)
                elif ev.type == "topic":
                    conn = opts.get("servicebus_connection", SERVICEBUS_SETTING) if c.existing else SERVICEBUS_SETTING
                    item.update(topic=c.name, subscription=self.subscription_name(name), connection=conn)
                out.append(item)
            if not fn.events or name in tasks:
                # Invoke-only functions and Logic Apps task functions get a private POST route.
                out.append(
                    {
                        "ident": unique(f"{name}_invoke"),
                        "kind": "http",
                        "function": name,
                        "route": "_pskit/invoke/" + name,
                        "method": "POST",
                        "auth": "FUNCTION",
                    }
                )
        return out

    def _host_json(self, config: ServiceConfig) -> str:
        timeout = max([config.timeout_of(fn) for fn in config.functions.values()] or [config.provider.timeout])
        host = {
            "version": "2.0",
            "extensionBundle": {"id": "Microsoft.Azure.Functions.ExtensionBundle", "version": "[4.*, 5.0.0)"},
            "extensions": {"http": {"routePrefix": ""}},
            "functionTimeout": _hms(min(timeout, self.max_timeout)),
            "logging": {"logLevel": {"default": "Information"}},
        }
        return json.dumps(host, indent=2) + "\n"

    def _node_shim(self, config: ServiceConfig) -> str:
        """Node.js v4 programming model: one ``app.<trigger>()`` registration per function."""
        js = json.dumps
        lines = [
            "// Generated by py-serverless-kit. Do not edit - regenerate with `pskit package`.",
            '"use strict";',
            'const { app } = require("@azure/functions");',
            'const pskit = require("./pskit_runtime/adapters/azure");',
            "",
        ]
        for r in self.registrations(config):
            ident, fn, kind = js(r["ident"]), js(r["function"]), r["kind"]
            if kind == "http":
                methods = list(NODE_HTTP_METHODS) if r["method"] == "ANY" else [r["method"]]
                lines.append(
                    f"app.http({ident}, {{ route: {js(r['route'])}, methods: {js(methods)}, "
                    f"authLevel: {js(r['auth'].lower())}, handler: (req, ctx) => pskit.http(req, ctx, {fn}) }});"
                )
            elif kind == "schedule":
                lines.append(
                    f"app.timer({ident}, {{ schedule: {js(r['schedule'])}, runOnStartup: false, "
                    f"handler: (timer, ctx) => pskit.timer(timer, ctx, {fn}, {js(r['input'])}) }});"
                )
            elif kind == "queue":
                lines.append(
                    f"app.storageQueue({ident}, {{ queueName: {js(r['queue'])}, connection: {js(r['connection'])}, "
                    f"handler: (msg, ctx) => pskit.queue(msg, ctx, {fn}) }});"
                )
            elif kind == "storage":
                lines.append(
                    f"app.storageBlob({ident}, {{ path: {js(r['path'])}, connection: {js(r['connection'])}, "
                    f"handler: (blob, ctx) => pskit.blob(blob, ctx, {fn}, {js(r['bucket'])}) }});"
                )
            elif kind == "topic":
                lines.append(
                    f"app.serviceBusTopic({ident}, {{ topicName: {js(r['topic'])}, "
                    f"subscriptionName: {js(r['subscription'])}, connection: {js(r['connection'])}, "
                    f"handler: (msg, ctx) => pskit.serviceBus(msg, ctx, {fn}) }});"
                )
        return "\n".join(lines) + "\n"

    def shim_files(self, config: ServiceConfig) -> Dict[str, str]:
        if config.language == "node":
            return {NODE_ENTRY: self._node_shim(config), "host.json": self._host_json(config)}
        lines = [
            "# Generated by py-serverless-kit. Do not edit - regenerate with `pskit package`.",
            "import azure.functions as func",
            "",
            "from py_serverless_kit.runtime.adapters import azure as _pskit",
            "",
            "app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)",
            "",
        ]
        for r in self.registrations(config):
            ident, name, kind = r["ident"], r["function"], r["kind"]
            lines.append("")
            lines.append(f'@app.function_name(name="{ident}")')
            if kind == "http":
                methods = "" if r["method"] == "ANY" else f", methods=[{r['method']!r}]"
                lines.append(f"@app.route(route={r['route']!r}{methods}, auth_level=func.AuthLevel.{r['auth']})")
                lines.append(f"def {ident}(req: func.HttpRequest) -> func.HttpResponse:")
                lines.append(f"    return _pskit.http(req, {name!r})")
            elif kind == "schedule":
                lines.append(
                    f"@app.timer_trigger(schedule={r['schedule']!r}, arg_name='timer', run_on_startup=False)"
                )
                lines.append(f"def {ident}(timer: func.TimerRequest) -> None:")
                lines.append(f"    _pskit.timer(timer, {name!r}, {r['input']!r})")
            elif kind == "queue":
                lines.append(
                    f"@app.queue_trigger(arg_name='msg', queue_name={r['queue']!r}, connection={r['connection']!r})"
                )
                lines.append(f"def {ident}(msg: func.QueueMessage) -> None:")
                lines.append(f"    _pskit.queue(msg, {name!r})")
            elif kind == "storage":
                lines.append(
                    f"@app.blob_trigger(arg_name='blob', path={r['path']!r}, connection={r['connection']!r})"
                )
                lines.append(f"def {ident}(blob: func.InputStream) -> None:")
                lines.append(f"    _pskit.blob(blob, {name!r}, {r['bucket']!r})")
            elif kind == "topic":
                lines.append(
                    f"@app.service_bus_topic_trigger(arg_name='msg', topic_name={r['topic']!r}, "
                    f"subscription_name={r['subscription']!r}, connection={r['connection']!r})"
                )
                lines.append(f"def {ident}(msg: func.ServiceBusMessage) -> None:")
                lines.append(f"    _pskit.service_bus(msg, {name!r})")
        return {"function_app.py": "\n".join(lines) + "\n", "host.json": self._host_json(config)}

    @staticmethod
    def subscription_name(function: str) -> str:
        return re.sub(r"[^A-Za-z0-9_.-]", "-", function)[:50]

    # ------------------------------------------------------------------ validation
    def provider_block(self, ctx: RenderContext) -> Dict[str, Any]:
        block: Dict[str, Any] = {"features": {}}
        if ctx.opt("subscription_id"):
            block["subscription_id"] = ctx.opt("subscription_id")
        return block

    def extra_validation(self, config: ServiceConfig) -> List[Issue]:
        issues: List[Issue] = []
        opts = config.provider.options
        env_seen: Dict[str, str] = {}
        if config.provider.iam.statements:
            issues.append(Issue("warning", "iam.statements are AWS-style and ignored on Azure", "provider.iam"))
        for name, fn in config.functions.items():
            where = f"functions.{name}"
            for key, value in fn.environment.items():
                if key in env_seen and env_seen[key] != value:
                    issues.append(
                        Issue(
                            "warning",
                            f"environment {key} differs between functions; Azure app "
                            "settings are shared by the whole Function App (last one wins)",
                            where,
                        )
                    )
                env_seen[key] = value
            for ev in fn.events_of("http"):
                if ev.auth in ("iam", "jwt"):
                    issues.append(
                        Issue(
                            "error",
                            f"http auth {ev.auth!r} is not supported on Azure; use none or key "
                            "(or put API Management / Easy Auth in front)",
                            where,
                        )
                    )
            for ev in fn.events_of("schedule"):
                if ev.timezone.upper() != "UTC":
                    issues.append(Issue("warning", "Linux Consumption timers run in UTC; timezone is ignored", where))
            for ev in fn.events_of("queue"):
                if not _STORAGE_NAME.match(ev.name):
                    issues.append(
                        Issue("error", f"queue name {ev.name!r} must be 3-63 lowercase letters, digits, dashes", where)
                    )
                if ev.fifo:
                    issues.append(Issue("warning", "Storage Queues are not FIFO; queue.fifo is ignored", where))
                if ev.dead_letter:
                    issues.append(
                        Issue(
                            "warning",
                            "Storage Queues move poison messages to '<queue>-poison'; dead_letter is ignored",
                            where,
                        )
                    )
            for ev in fn.events_of("storage"):
                if not _STORAGE_NAME.match(ev.bucket):
                    issues.append(
                        Issue(
                            "error",
                            f"container name {ev.bucket!r} must be 3-63 lowercase letters, digits, dashes",
                            where,
                        )
                    )
                if "deleted" in ev.events:
                    issues.append(Issue("error", "Azure blob triggers only fire on created/updated blobs", where))
            for ev in fn.events_of("topic"):
                if ev.existing and not (opts.get("servicebus_namespace_id") and opts.get("servicebus_connection")):
                    issues.append(
                        Issue(
                            "error",
                            "existing topics need options.servicebus_namespace_id and "
                            "options.servicebus_connection (name of an app setting)",
                            where,
                        )
                    )
                if ev.filter:
                    issues.append(
                        Issue("warning", "topic.filter is not applied on Azure Service Bus subscriptions", where)
                    )
        issues.extend(self._workflow_validation(config))
        return issues

    def _workflow_validation(self, config: ServiceConfig) -> List[Issue]:
        issues: List[Issue] = []
        for name, wf in sorted(config.workflows.items()):
            try:
                if self.workflow_engine(wf) != "native":
                    continue
            except ProviderError:
                continue  # reported by Provider.validate
            where = f"workflows.{name}"
            try:
                _, warnings = compile_logic_app(
                    definition_dict(wf), lambda f: f"https://example/{f}", name, key="key", timeout=wf.timeout
                )
            except LogicAppsError as exc:
                issues.append(Issue("error", str(exc), where))
                continue
            issues.extend(Issue("warning", w, where) for w in warnings)
            for fn_name in sorted(set(wf.task_functions())):
                fn = config.functions.get(fn_name)
                if fn is not None and config.timeout_of(fn) > HTTP_TIMEOUT:
                    issues.append(
                        Issue(
                            "warning",
                            f"task function {fn_name!r} may run {config.timeout_of(fn)}s but Logic Apps HTTP calls "
                            f"time out after {HTTP_TIMEOUT}s",
                            where,
                        )
                    )
        return issues

    # ------------------------------------------------------------------ render
    def render_resources(self, doc: TerraformDoc, ctx: RenderContext) -> None:
        cfg = ctx.config
        loc = ctx.region
        tags = ctx.tags()
        if ctx.opt("resource_group"):
            rg = doc.data("azurerm_resource_group", "rg", {"name": ctx.opt("resource_group")})
        else:
            rg = doc.resource(
                "azurerm_resource_group", "rg", {"name": f"{ctx.prefix}-rg", "location": loc, "tags": tags}
            )
        rg_name = ref(rg, "name")

        sa_base = re.sub(r"[^a-z0-9]", "", ctx.prefix.lower())[:16] or "pskit"
        sa = doc.resource(
            "azurerm_storage_account",
            "app",
            {
                "name": sa_base + stable_suffix(ctx.prefix, loc, length=8),
                "resource_group_name": rg_name,
                "location": loc,
                "account_tier": "Standard",
                "account_replication_type": "LRS",
                "min_tls_version": "TLS1_2",
                "tags": tags,
            },
        )
        plan = doc.resource(
            "azurerm_service_plan",
            "plan",
            {
                "name": f"{ctx.prefix}-plan",
                "resource_group_name": rg_name,
                "location": loc,
                "os_type": "Linux",
                "sku_name": ctx.opt("plan_sku", "Y1"),
                "tags": tags,
            },
        )

        site_config: Dict[str, Any] = {
            "application_stack": {
                ("node_version" if cfg.language == "node" else "python_version"): self.runtime_id(cfg.provider.runtime)
            },
        }
        if ctx.opt("app_insights", True):
            law = doc.resource(
                "azurerm_log_analytics_workspace",
                "logs",
                {
                    "name": f"{ctx.prefix}-logs",
                    "resource_group_name": rg_name,
                    "location": loc,
                    "sku": "PerGB2018",
                    "retention_in_days": max(30, cfg.provider.log_retention_days or 30),
                    "tags": tags,
                },
            )
            # Workspace (customer) GUID: `pskit logs` / the dashboard query Function App logs with it.
            doc.output(
                "log_analytics_workspace_id",
                ref(law, "workspace_id"),
                description="Log Analytics workspace GUID holding the Function App logs",
            )
            ai = doc.resource(
                "azurerm_application_insights",
                "ai",
                {
                    "name": f"{ctx.prefix}-ai",
                    "resource_group_name": rg_name,
                    "location": loc,
                    "workspace_id": ref(law, "id"),
                    "application_type": "web",
                    "tags": tags,
                },
            )
            site_config["application_insights_connection_string"] = ref(ai, "connection_string")
        cors = [ev.cors_config for fn in cfg.functions.values() for ev in fn.events_of("http") if ev.cors_config]
        if cors:
            site_config["cors"] = {
                "allowed_origins": sorted({o for c in cors for o in c.origins}),
                "support_credentials": any(c.allow_credentials for c in cors),
            }

        settings: Dict[str, str] = {
            "SCM_DO_BUILD_DURING_DEPLOYMENT": "true",
            "ENABLE_ORYX_BUILD": "true",
            "AzureWebJobsFeatureFlags": "EnableWorkerIndexing",
        }
        for name, fn in ctx.function_items():
            for key, value in ctx.environment(name, fn).items():
                if key not in _PER_FUNCTION_ENV:
                    settings[key] = escape(value)

        # queues / containers / service bus (events, then managed resources no event uses)
        queues = [ev.name for _n, fn in ctx.function_items() for ev in fn.events_of("queue") if not ev.existing]
        containers = [ev.bucket for _n, fn in ctx.function_items() for ev in fn.events_of("storage") if not ev.existing]
        topics = [ev.name for _n, fn in ctx.function_items() for ev in fn.events_of("topic") if not ev.existing]
        for key, res in self.standalone(cfg):
            {"queue": queues, "storage": containers, "topic": topics}[res.type].append(res.native_name(key))
        for qname in queues:
            if not doc.has_resource("azurerm_storage_queue", f"q-{qname}"):
                doc.resource(
                    "azurerm_storage_queue", f"q-{qname}", {"name": qname, "storage_account_id": ref(sa, "id")}
                )
        for bucket in containers:
            if not doc.has_resource("azurerm_storage_container", f"b-{bucket}"):
                doc.resource(
                    "azurerm_storage_container",
                    f"b-{bucket}",
                    {"name": bucket, "storage_account_id": ref(sa, "id"), "container_access_type": "private"},
                )
        ns: Optional[str] = None
        for tname in topics:
            if ns is None:
                ns = doc.resource(
                    "azurerm_servicebus_namespace",
                    "bus",
                    {
                        "name": f"{ctx.prefix[:40].rstrip('-')}-{stable_suffix(ctx.prefix, 'bus', length=6)}",
                        "resource_group_name": rg_name,
                        "location": loc,
                        "sku": "Standard",
                        "tags": tags,
                    },
                )
                settings[SERVICEBUS_SETTING] = ref(ns, "default_primary_connection_string")
            label = f"t-{tname}"
            if not doc.has_resource("azurerm_servicebus_topic", label):
                doc.resource("azurerm_servicebus_topic", label, {"name": tname, "namespace_id": ref(ns, "id")})
        for name, fn in ctx.function_items():
            for ev in fn.events_of("topic"):
                label = f"t-{ev.name}"
                if ev.existing:
                    topic = doc.data(
                        "azurerm_servicebus_topic",
                        label,
                        {"name": ev.name, "namespace_id": ctx.opt("servicebus_namespace_id")},
                    )
                else:
                    topic = f"azurerm_servicebus_topic.{tf_id(label)}"
                doc.resource(
                    "azurerm_servicebus_subscription",
                    f"{name}-{ev.name}",
                    {"name": self.subscription_name(name), "topic_id": ref(topic, "id"), "max_delivery_count": 10},
                )

        app_name = self.app_name(ctx.service, ctx.stage)
        body: Dict[str, Any] = {
            "name": app_name,
            "resource_group_name": rg_name,
            "location": loc,
            "service_plan_id": ref(plan, "id"),
            "storage_account_name": ref(sa, "name"),
            "storage_account_access_key": ref(sa, "primary_access_key"),
            "functions_extension_version": "~4",
            "https_only": True,
            "zip_deploy_file": "${path.module}/artifact.zip",
            "app_settings": settings,
            "site_config": site_config,
            "tags": tags,
        }
        app = doc.resource(APP, "app", body)
        host = "https://" + ref(app, "default_hostname")

        fn_out: Dict[str, Dict[str, Any]] = {}
        for name, fn in ctx.function_items():
            out: Dict[str, Any] = {
                "id": f"{app_name}/{name}",
                "console": "https://portal.azure.com/#resource" + ref(app, "id") + "/functions",
            }
            http_events = fn.events_of("http")
            if http_events:
                out["base_url"] = host
                out["url"] = host + "/" + azure_route(http_events[0].path)
            fn_out[name] = out
        wf_out: Dict[str, Any] = {}
        for name in sorted(cfg.workflows):
            if ctx.workflow_engines.get(name) == "native":
                continue
            wf_out[name] = {"id": f"{app_name}/{name}-orchestrator", "url": host + f"/workflows/{name}"}
        wf_out.update(self._logic_apps(doc, ctx, rg_name, app, host))
        doc.output(
            "pskit",
            {"functions": fn_out, "workflows": wf_out, "endpoint": host},
            description="py-serverless-kit deployment summary",
        )

    # ------------------------------------------------------------------ Logic Apps
    def _logic_apps(self, doc: TerraformDoc, ctx: RenderContext, rg_name: str, app: str, host: str) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        native = [(n, wf) for n, wf in sorted(ctx.config.workflows.items()) if ctx.workflow_engines.get(n) == "native"]
        if not native:
            return out
        keys = doc.data(
            "azurerm_function_app_host_keys", "keys", {"name": ref(app, "name"), "resource_group_name": rg_name}
        )
        url_token, key_token = "__PSKIT_HOST__", "__PSKIT_FUNCTION_KEY__"
        for name, wf in native:
            actions, warnings = compile_logic_app(
                definition_dict(wf),
                lambda f: f"{url_token}/_pskit/invoke/{f}",
                name,
                key=key_token,
                timeout=wf.timeout,
                sync=bool(wf.options.get("sync", True)),
            )
            doc.warnings.extend(warnings)
            workflow = doc.resource(
                "azurerm_logic_app_workflow",
                f"wf-{name}",
                {
                    "name": ctx.physical_name(name),
                    "location": ctx.region,
                    "resource_group_name": rg_name,
                    "tags": ctx.tags(),
                },
            )
            trigger = doc.resource(
                "azurerm_logic_app_trigger_http_request",
                f"wf-{name}-trigger",
                {"name": "manual", "logic_app_id": ref(workflow, "id"), "method": "POST", "schema": "{}"},
            )
            # Each action resource rewrites the workflow definition: create them one at a time, in run order.
            previous = trigger
            for i, (action_name, action) in enumerate(actions):
                text = escape(json.dumps(action, sort_keys=True))
                text = text.replace(url_token, host).replace(key_token, ref(keys, "default_function_key"))
                previous = doc.resource(
                    "azurerm_logic_app_action_custom",
                    f"wf-{name}-{i:03d}-{action_name}",
                    {
                        "name": action_name,
                        "logic_app_id": ref(workflow, "id"),
                        "body": text,
                        "depends_on": [previous],
                    },
                )
            out[name] = {
                "id": ref(workflow, "id"),
                "url": ref(trigger, "callback_url"),
                "console": "https://portal.azure.com/#resource" + ref(workflow, "id") + "/logicApp",
            }
        return out
