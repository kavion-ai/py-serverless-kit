"""GCP: Cloud Functions (2nd gen) + Cloud Scheduler + Pub/Sub + Cloud Storage + Cloud Workflows.

Cloud Functions gen2 allows a single ``event_trigger`` per function and an
event-triggered function cannot serve plain HTTP. To keep "change only the
provider in YAML" true, each *logical* function is deployed as one or more
Cloud Functions sharing the same bundle and handler (``PSKIT_FUNCTION`` is the
logical name in all of them):

* ``<name>``             - HTTP deployment (entry ``pskit_http``). Created when the
  function has ``http`` events, no event triggers at all, is a workflow task (Cloud
  Workflows needs a URL), or has schedules but no Pub/Sub trigger to publish to.
* ``<name>-<kind><i>``   - one per event trigger (entry ``pskit_event``), e.g.
  ``worker-queue0``, ``worker-storage0``, ``worker-topic0``. A storage event listing
  both ``created`` and ``deleted`` becomes two deployments. When a function has
  exactly one trigger and needs no HTTP deployment it is simply named ``<name>``.

Triggers:

* ``queue`` / ``topic``  -> Pub/Sub ``messagePublished`` (GCP has no push queue like SQS,
  so a queue is a Pub/Sub topic too).
* ``storage``            -> Cloud Storage ``finalized`` / ``deleted``. Prefix / suffix
  filters are not supported by Eventarc, so the runtime applies them.
* ``schedule``           -> Cloud Scheduler: POSTs the ``__pskit`` envelope to the HTTP
  deployment with an OIDC token, or - when there is no HTTP deployment - publishes the
  envelope to the function's first Pub/Sub topic.

A dedicated *invoker* service account is created and granted ``roles/run.invoker`` on
every deployment; Cloud Scheduler, Eventarc and Cloud Workflows all authenticate with it.
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from ..config.schema import FunctionConfig, ResourceConfig, ServiceConfig
from ..runtime.adapters.base import envelope
from ..workflows import definition_dict
from ..workflows.gcp import compile_gcp
from . import schedule as sched
from .base import HTTP, QUEUE, SCHEDULE, STORAGE, TOPIC, WORKFLOW_NATIVE, Issue, Provider, RenderContext, stable_suffix
from .terraform_doc import TerraformDoc, escape, ref, tf_id

FN = "google_cloudfunctions2_function"
PUBSUB_EVENT = "google.cloud.pubsub.topic.v1.messagePublished"
STORAGE_EVENTS = {
    "created": "google.cloud.storage.object.v1.finalized",
    "deleted": "google.cloud.storage.object.v1.deleted",
}
EVENT_MAX_TIMEOUT = 540
TRIGGERS = ("queue", "topic", "storage")
NODE_ENTRY = "pskit_entry.js"


def _label(text: str) -> str:
    value = re.sub(r"[^a-z0-9_-]", "_", str(text).lower())[:63]
    return value


def labels(tags: Dict[str, str]) -> Dict[str, str]:
    out = {}
    for key, value in tags.items():
        k = _label(key)
        if not k or not k[0].isalpha():
            k = "k" + k
        out[k[:63]] = _label(value)
    return out


def _sa_id(prefix: str, suffix: str) -> str:
    base = re.sub(r"[^a-z0-9-]", "-", prefix.lower())
    base = base[: 30 - len(suffix) - 1].strip("-")
    if not base or not base[0].isalpha():
        base = "p" + base
    return f"{base}-{suffix}"[:30]


@dataclass
class Deployment:
    """One Cloud Function backing (part of) a logical function."""

    key: str  # logical name or "<name>-<kind><i>"; also the terraform label
    kind: str  # "http" | "queue" | "topic" | "storage"
    config: Any = None  # trigger event config
    action: Optional[str] = None  # storage: created | deleted
    schedules: List[Any] = field(default_factory=list)
    pubsub_schedules: bool = False  # schedules publish to this deployment's topic


def plan_deployments(name: str, fn: FunctionConfig, needs_http: bool = False) -> List[Deployment]:
    """Split a logical function into Cloud Functions (see module docstring)."""
    triggers: List[Deployment] = []
    counters: Dict[str, int] = {}
    for ev in fn.events:
        if ev.type not in TRIGGERS:
            continue
        actions = list(ev.config.events) if ev.type == "storage" else [None]
        for action in actions:
            i = counters.get(ev.type, 0)
            counters[ev.type] = i + 1
            triggers.append(Deployment(f"{name}-{ev.type}{i}", ev.type, ev.config, action))
    schedules = fn.events_of("schedule")
    pubsub = next((d for d in triggers if d.kind in ("queue", "topic")), None)
    want_http = bool(fn.events_of("http")) or not triggers or needs_http or bool(schedules and pubsub is None)
    out: List[Deployment] = []
    if want_http:
        out.append(Deployment(name, "http", schedules=schedules))
    elif schedules and pubsub is not None:
        pubsub.schedules = schedules
        pubsub.pubsub_schedules = True
    if len(triggers) == 1 and not want_http:
        triggers[0].key = name
    return out + triggers


def task_functions(config: ServiceConfig) -> Set[str]:
    return {f for wf in config.workflows.values() for f in wf.task_functions()}


class GcpProvider(Provider):
    name = "gcp"
    display_name = "Google Cloud Functions"
    tier = "stable"
    terraform_source = "hashicorp/google"
    terraform_version = ">= 5.20"
    terraform_local_name = "google"
    default_region = "us-central1"
    capabilities = frozenset({HTTP, SCHEDULE, QUEUE, STORAGE, TOPIC, WORKFLOW_NATIVE})
    max_name_length = 63
    name_pattern = r"[^a-z0-9-]"
    runtimes = {f"python3.{v}": f"python3{v}" for v in (9, 10, 11, 12, 13)}
    node_runtimes = {f"nodejs{v}": f"nodejs{v}" for v in (18, 20, 22)}
    vendor_dependencies = False
    node_vendor_dependencies = False  # Cloud Build runs npm install from package.json
    extra_requirements = ["functions-framework>=3.5"]
    max_timeout = 3600
    standalone_resources = True
    notes = "Cloud Functions gen2 (Cloud Run). Requires options.project. Queues map to Pub/Sub topics."

    # ------------------------------------------------------------------ bundle
    def node_package(self, config: ServiceConfig) -> Dict[str, Any]:
        """Fields merged into the bundled package.json of a Node.js service."""
        return {"main": NODE_ENTRY, "dependencies": {"@google-cloud/functions-framework": "^3.4.0"}}

    def shim_files(self, config: ServiceConfig) -> Dict[str, str]:
        if getattr(config, "language", "python") == "node":
            return {
                NODE_ENTRY: (
                    "// Generated by py-serverless-kit. Entry points: pskit_http, pskit_event\n"
                    '"use strict";\n'
                    'const functions = require("@google-cloud/functions-framework");\n'
                    'const pskit = require("./pskit_runtime/adapters/gcp");\n\n'
                    'functions.http("pskit_http", pskit.http);\n'
                    'functions.cloudEvent("pskit_event", pskit.cloudEvent);\n'
                )
            }
        return {
            "main.py": (
                "# Generated by py-serverless-kit. Entry points: pskit_http, pskit_event\n"
                "import functions_framework\n\n"
                "from py_serverless_kit.runtime.adapters import gcp as _pskit\n\n\n"
                "@functions_framework.http\n"
                "def pskit_http(request):\n"
                "    return _pskit.http(request)\n\n\n"
                "@functions_framework.cloud_event\n"
                "def pskit_event(cloud_event):\n"
                "    _pskit.cloud_event(cloud_event)\n"
            )
        }

    def provider_block(self, ctx: RenderContext) -> Dict[str, Any]:
        block: Dict[str, Any] = {"region": ctx.region}
        if ctx.opt("project"):
            block["project"] = ctx.opt("project")
        return block

    def extra_validation(self, config: ServiceConfig) -> List[Issue]:
        issues: List[Issue] = []
        if not config.provider.options.get("project"):
            issues.append(Issue("error", "GCP needs provider.options.project (the GCP project id)", "provider.options"))
        if config.provider.iam.statements:
            issues.append(
                Issue(
                    "warning",
                    "iam.statements are AWS-style and ignored on GCP; grant roles to options.service_account instead",
                    "provider.iam",
                )
            )
        for name, fn in config.functions.items():
            where = f"functions.{name}"
            triggers = [e for e in fn.events if e.type in TRIGGERS]
            for ev in fn.events_of("queue"):
                if ev.dead_letter:
                    issues.append(
                        Issue(
                            "warning",
                            "queue.dead_letter is not applied on GCP (Eventarc manages the subscription)",
                            where,
                        )
                    )
                if ev.fifo:
                    issues.append(
                        Issue("warning", "queue.fifo is not supported by Pub/Sub triggers and is ignored", where)
                    )
            for ev in fn.events_of("http"):
                if ev.auth in ("jwt", "key"):
                    issues.append(
                        Issue("error", f"http auth {ev.auth!r} is not supported on GCP; use none or iam", where)
                    )
            if triggers and config.timeout_of(fn) > EVENT_MAX_TIMEOUT:
                issues.append(
                    Issue("error", f"event-triggered functions are limited to {EVENT_MAX_TIMEOUT}s on GCP", where)
                )
        return issues

    # ------------------------------------------------------------------ render
    def render_resources(self, doc: TerraformDoc, ctx: RenderContext) -> None:
        cfg = ctx.config
        project = ctx.opt("project", "")
        region = ctx.region

        src_bucket = doc.resource(
            "google_storage_bucket",
            "source",
            {
                "name": f"{ctx.prefix[:45]}-src-{stable_suffix(project, ctx.prefix, length=8)}",
                "location": region.upper(),
                "uniform_bucket_level_access": True,
                "force_destroy": True,
                "labels": labels(ctx.tags()),
            },
        )
        src_obj = doc.resource(
            "google_storage_bucket_object",
            "source",
            {
                "name": f"source-{ctx.artifact.sha256[:16]}.zip",
                "bucket": ref(src_bucket, "name"),
                "source": "${path.module}/artifact.zip",
            },
        )
        invoker = doc.resource(
            "google_service_account",
            "invoker",
            {
                "account_id": _sa_id(ctx.prefix, "inv"),
                "display_name": f"pskit invoker for {ctx.prefix}",
            },
        )
        invoker_email = ref(invoker, "email")
        has_storage = any(fn.events_of("storage") for fn in cfg.functions.values())
        tasks = task_functions(cfg)
        plans = {name: plan_deployments(name, fn, name in tasks) for name, fn in ctx.function_items()}
        has_trigger = any(d.kind != "http" for deps in plans.values() for d in deps)
        depends: List[str] = []
        if has_storage:
            gcs = doc.data("google_storage_project_service_account", "gcs", {"project": project} if project else {})
            depends.append(
                doc.resource(
                    "google_project_iam_member",
                    "gcs-pubsub",
                    {
                        "project": project,
                        "role": "roles/pubsub.publisher",
                        "member": "serviceAccount:" + ref(gcs, "email_address"),
                    },
                )
            )
        if has_trigger:
            depends.append(
                doc.resource(
                    "google_project_iam_member",
                    "invoker-eventarc",
                    {
                        "project": project,
                        "role": "roles/eventarc.eventReceiver",
                        "member": "serviceAccount:" + invoker_email,
                    },
                )
            )

        self._resources(doc, ctx)
        fn_out: Dict[str, Dict[str, Any]] = {}
        urls: Dict[str, str] = {}
        for name, fn in ctx.function_items():
            deployments = plans[name]
            for ev in fn.events_of("topic"):
                if ev.filter:
                    doc.warnings.append(
                        f"GCP: topic filter on {name!r} ({ev.name}) is not applied by Pub/Sub push "
                        "triggers; filter the records in your handler"
                    )
            if len(deployments) > 1:
                doc.warnings.append(
                    f"GCP: function {name!r} is deployed as {len(deployments)} Cloud Functions: "
                    + ", ".join(ctx.physical_name(d.key) for d in deployments)
                )
            ids: List[str] = []
            out: Dict[str, Any] = {}
            for dep in deployments:
                res = self._function(doc, ctx, name, fn, dep, src_bucket, src_obj, invoker_email, depends)
                ids.append(ref(res, "name"))
                service = ref(res, "service_config[0].service")
                doc.resource(
                    "google_cloud_run_service_iam_member",
                    f"{dep.key}-invoker",
                    {
                        "location": region,
                        "service": service,
                        "role": "roles/run.invoker",
                        "member": "serviceAccount:" + invoker_email,
                    },
                )
                if dep.kind == "http":
                    urls[name] = ref(res, "url")
                    if any(ev.auth == "none" for ev in fn.events_of("http")):
                        doc.resource(
                            "google_cloud_run_service_iam_member",
                            f"{dep.key}-public",
                            {"location": region, "service": service, "role": "roles/run.invoker", "member": "allUsers"},
                        )
                    if fn.events_of("http"):
                        out["url"] = ref(res, "url")
                        out["base_url"] = ref(res, "url")
                for i, ev in enumerate(dep.schedules):
                    self._schedule(doc, ctx, name, fn, dep, i, ev, ref(res, "url"), invoker_email)
            primary = deployments[0]
            out["id"] = ids[0]
            out["console"] = (
                f"https://console.cloud.google.com/functions/details/{region}/"
                f"{ctx.physical_name(primary.key)}?project={project}"
            )
            if len(ids) > 1:
                out["extra"] = ids[1:]
            fn_out[name] = out

        wf_out = self._workflows(doc, ctx, urls, invoker_email)
        doc.output(
            "pskit",
            {"functions": fn_out, "workflows": wf_out, "endpoint": None},
            description="py-serverless-kit deployment summary",
        )

    # ------------------------------------------------------------------ pieces
    def _bucket(self, doc: TerraformDoc, ctx: RenderContext, name: str) -> str:
        label = f"b-{name}"
        if not doc.has_resource("google_storage_bucket", label):
            doc.resource(
                "google_storage_bucket",
                label,
                {
                    "name": name,
                    "location": ctx.region.upper(),
                    "uniform_bucket_level_access": True,
                    "labels": labels(ctx.tags()),
                },
            )
        return f"google_storage_bucket.{tf_id(label)}"

    def _resources(self, doc: TerraformDoc, ctx: RenderContext) -> None:
        """Managed resources no event creates: a bucket, or a Pub/Sub topic for queues and topics."""
        for key, res in self.standalone(ctx.config):
            if res.type == "storage":
                self._bucket(doc, ctx, res.native_name(key))
            else:
                self._topic(doc, ctx, res.native_name(key), False)

    def resource_refs(self, ctx: RenderContext, key: str, res: ResourceConfig) -> Dict[str, str]:
        if res.external or res.type not in ("queue", "topic"):
            return {}
        # Queues are Pub/Sub topics on GCP; the event or _resources creates t-<name>.
        return {"ID": "${tf:google_pubsub_topic." + tf_id(f"t-{res.native_name(key)}") + ".id}"}

    def _topic(self, doc: TerraformDoc, ctx: RenderContext, name: str, existing: bool) -> str:
        label = f"t-{name}"
        if existing:
            return doc.data("google_pubsub_topic", label, {"name": name})
        if not doc.has_resource("google_pubsub_topic", label):
            doc.resource("google_pubsub_topic", label, {"name": name, "labels": labels(ctx.tags())})
        return f"google_pubsub_topic.{tf_id(label)}"

    def _function(
        self,
        doc: TerraformDoc,
        ctx: RenderContext,
        name: str,
        fn: FunctionConfig,
        dep: Deployment,
        src_bucket: str,
        src_obj: str,
        invoker_email: str,
        depends: List[str],
    ) -> str:
        cfg = ctx.config
        env = ctx.environment(name, fn)  # PSKIT_FUNCTION stays the logical name
        env["PSKIT_GCP_PROJECT"] = ctx.opt("project", "")
        service_config: Dict[str, Any] = {
            "available_memory": f"{cfg.memory_of(fn)}M",
            "timeout_seconds": cfg.timeout_of(fn),
            "ingress_settings": "ALLOW_ALL",
            "all_traffic_on_latest_revision": True,
        }
        if fn.concurrency:
            service_config["max_instance_count"] = fn.concurrency
        if ctx.opt("service_account"):
            service_config["service_account_email"] = ctx.opt("service_account")
        body: Dict[str, Any] = {
            "name": ctx.physical_name(dep.key),
            "location": ctx.region,
            "description": fn.description[:256],
            "labels": labels(dict(ctx.tags(fn), **{"pskit-function": name})),
            "build_config": {
                "runtime": self.runtime_id(cfg.runtime_of(fn)),
                "entry_point": "pskit_http" if dep.kind == "http" else "pskit_event",
                "source": {"storage_source": {"bucket": ref(src_bucket, "name"), "object": ref(src_obj, "name")}},
            },
            "service_config": service_config,
        }
        if dep.kind != "http":
            ev = dep.config
            et: Dict[str, Any] = {
                "trigger_region": ctx.region,
                "retry_policy": "RETRY_POLICY_RETRY",
                "service_account_email": invoker_email,
            }
            if dep.kind in ("queue", "topic"):
                env["PSKIT_TRIGGER_KIND"] = dep.kind
                et["event_type"] = PUBSUB_EVENT
                et["pubsub_topic"] = ref(self._topic(doc, ctx, ev.name, ev.existing), "id")
            else:
                if ev.prefix:
                    env["PSKIT_STORAGE_PREFIX"] = ev.prefix
                if ev.suffix:
                    env["PSKIT_STORAGE_SUFFIX"] = ev.suffix
                bucket_name = ev.bucket
                if not ev.existing:
                    bucket_name = ref(self._bucket(doc, ctx, ev.bucket), "name")
                et["event_type"] = STORAGE_EVENTS[dep.action or "created"]
                et["event_filters"] = [{"attribute": "bucket", "value": bucket_name}]
            body["event_trigger"] = et
        service_config["environment_variables"] = {k: escape(v) for k, v in env.items()}
        if depends:
            body["depends_on"] = list(depends)
        body.update(fn.options)
        return doc.resource(FN, dep.key, body)

    def _schedule(
        self,
        doc: TerraformDoc,
        ctx: RenderContext,
        name: str,
        fn: FunctionConfig,
        dep: Deployment,
        i: int,
        ev: Any,
        url: str,
        invoker_email: str,
    ) -> None:
        payload = base64.b64encode(
            json.dumps(envelope("schedule", ev.input, source="gcp.scheduler")).encode("utf-8")
        ).decode("ascii")
        body: Dict[str, Any] = {
            "name": ctx.physical_name(f"{name}-{ev.name or i}"),
            "region": ctx.region,
            "schedule": sched.to_cron5(ev),
            "time_zone": ev.timezone,
            "paused": not ev.enabled,
        }
        if dep.pubsub_schedules:  # no HTTP deployment: publish the envelope to the function's topic
            topic = self._topic(doc, ctx, dep.config.name, dep.config.existing)
            body["pubsub_target"] = {"topic_name": ref(topic, "id"), "data": payload}
        else:
            body["attempt_deadline"] = f"{min(1800, max(15, ctx.config.timeout_of(fn)))}s"
            body["http_target"] = {
                "http_method": "POST",
                "uri": url,
                "body": payload,
                "headers": {"Content-Type": "application/json"},
                "oidc_token": {"service_account_email": invoker_email, "audience": url},
            }
        doc.resource("google_cloud_scheduler_job", f"{name}-{i}", body)

    def _workflows(
        self, doc: TerraformDoc, ctx: RenderContext, urls: Dict[str, str], invoker_email: str
    ) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        project = ctx.opt("project", "")
        for name, wf in sorted(ctx.config.workflows.items()):
            if ctx.workflow_engines.get(name) != "native":
                out[name] = {"id": ref(FN, tf_id(f"{name}-orchestrator"), "name")}
                continue
            placeholders = {f: f"__PSKIT_URL_{i}__" for i, f in enumerate(sorted(urls))}
            source, warnings = compile_gcp(definition_dict(wf), placeholders.__getitem__, name)
            doc.warnings.extend(warnings)
            text = escape(json.dumps(source, indent=2))
            for f, token in placeholders.items():
                text = text.replace(token, urls[f])
            res = doc.resource(
                "google_workflows_workflow",
                f"wf-{name}",
                {
                    "name": ctx.physical_name(name),
                    "region": ctx.region,
                    "description": wf.description[:256],
                    "service_account": invoker_email,
                    "labels": labels(ctx.tags()),
                    "source_contents": text,
                },
            )
            out[name] = {
                "id": ref(res, "id"),
                "console": f"https://console.cloud.google.com/workflows/workflow/{ctx.region}/{ctx.physical_name(name)}?project={project}",
            }
        return out
