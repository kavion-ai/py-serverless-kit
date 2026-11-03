"""Project scaffolds for ``pskit init``."""

from __future__ import annotations

from typing import Dict

DEFAULT_REGIONS = {
    "aws": "us-east-1",
    "azure": "eastus",
    "gcp": "us-central1",
    "alibaba": "cn-hangzhou",
    "oracle": "us-ashburn-1",
    "ibm": "us-south",
    "digitalocean": "nyc1",
    "tencent": "ap-guangzhou",
    "huawei": "cn-north-4",
    "cloudflare": "global",
    "onprem": "local",
}

PROVIDER_OPTIONS = {
    "gcp": "  options:\n    project: ${env:GOOGLE_CLOUD_PROJECT}\n",
    "azure": "  options:\n    subscription_id: ${env:ARM_SUBSCRIPTION_ID}\n",
    "oracle": (
        '  options:\n    compartment_id: ${env:OCI_COMPARTMENT_ID}\n    subnet_ids: ["${env:OCI_SUBNET_ID}"]\n'
        "    image: ${env:OCI_FUNCTION_IMAGE}\n"
    ),
    "digitalocean": "  options:\n    namespace: ${env:DO_FUNCTIONS_NAMESPACE}\n",
    "cloudflare": "  options:\n    account_id: ${env:CLOUDFLARE_ACCOUNT_ID}\n",
    "onprem": (
        "  options:\n"
        "    host: 127.0.0.1\n"
        "    port: 8080\n"
        "    # deploy.method: local (this machine) | ssh | docker\n"
        "    # ssh: {host: 10.0.1.12, user: pskit, python: bundle, install: systemd}\n"
        "    # docker on a server: {method: docker, host: 10.0.1.12, user: pskit, pem: ./server.pem}\n"
        "    # python: bundle ships a portable CPython when the server has none\n"
        "    # builtin services are created on deploy. To use a directory you already\n"
        "    # have: storage: {use: directory, path: /var/pskit/buckets}\n"
    ),
}

HANDLERS_HTTP = '''"""HTTP handlers. This code runs unchanged on every supported cloud."""

from py_serverless_kit import Context, Event, NotFound, Response

_ITEMS = {"1": {"id": "1", "name": "first item"}}


def hello(event: Event, ctx: Context):
    name = event.http.query.get("name", "world")
    ctx.logger.info("saying hello", extra={"name": name})
    return {"message": f"Hello, {name}!", "provider": event.provider, "stage": ctx.stage}


def get_item(event: Event, ctx: Context):
    item = _ITEMS.get(event.http.path_params["id"])
    if item is None:
        raise NotFound(f"item {event.http.path_params['id']} does not exist")
    return item


def create_item(event: Event, ctx: Context):
    body = event.http.json()
    item = {"id": str(len(_ITEMS) + 1), **body}
    _ITEMS[item["id"]] = item
    return Response.json(item, status=201)
'''

HANDLERS_EVENTS = '''

def nightly_report(event: Event, ctx: Context):
    """Runs on a schedule; ``event.data`` is the optional ``input`` from the YAML."""
    ctx.logger.info("nightly report", extra={"input": event.data})
    return {"ok": True}


def process_jobs(event: Event, ctx: Context):
    """Queue consumer: only failed records are retried where the cloud supports it."""
    from py_serverless_kit import BatchResult

    result = BatchResult()
    for record in event.records:
        try:
            job = record.json()
            ctx.logger.info("processing job", extra={"job": job})
        except Exception:  # noqa: BLE001
            result.fail(record)
    return result


def on_upload(event: Event, ctx: Context):
    for record in event.records:
        ctx.logger.info("object event", extra={"bucket": record.bucket, "key": record.key, "action": record.action})
'''

HANDLERS_WORKFLOW = """

def validate_order(event: Event, ctx: Context):
    order = dict(event.data or {})
    if order.get("amount", 0) <= 0:
        raise ValueError("amount must be positive")
    order["valid"] = True
    return order


def charge_order(event: Event, ctx: Context):
    order = dict(event.data)
    order["charged"] = True
    return order
"""

CONFIG_HTTP = """service: {service}

provider:
  name: {provider}
  region: {region}
  stage: dev
  runtime: python3.12
  memory: 256
  timeout: 15
  environment:
    LOG_LEVEL: INFO
{options}
functions:
  hello:
    handler: app.handlers.hello
    description: Says hello
    events:
      - http: GET /hello

  get-item:
    handler: app.handlers.get_item
    events:
      - http: GET /items/{{id}}

  create-item:
    handler: app.handlers.create_item
    events:
      - http:
          method: POST
          path: /items
          cors: true
"""

CONFIG_EVENTS = """
  nightly-report:
    handler: app.handlers.nightly_report
    events:
      - schedule:
          cron: "0 2 * * *"
          input: {{report: daily}}

  process-jobs:
    handler: app.handlers.process_jobs
    events:
      - queue: {{name: {service}-jobs, batch_size: 10}}

  on-upload:
    handler: app.handlers.on_upload
    events:
      - storage: {{bucket: {service}-uploads-change-me, events: [created], suffix: .csv}}
"""

CONFIG_WORKFLOW = """
  validate-order:
    handler: app.handlers.validate_order

  charge-order:
    handler: app.handlers.charge_order

workflows:
  order-pipeline:
    description: Validate then charge an order
    start_at: Validate
    states:
      Validate:
        type: task
        function: validate-order
        retry: [{{errors: ["*"], max_attempts: 2}}]
        catch: [{{errors: ["ValueError"], next: Rejected}}]
        next: Charge
      Charge:
        type: task
        function: charge-order
        end: true
      Rejected:
        type: fail
        error: OrderRejected
"""

TEST_FILE = """from py_serverless_kit.local import LocalRunner, http_event
from py_serverless_kit.core.project import Project


def test_hello():
    runner = LocalRunner(Project.load())
    resp = runner.invoke("hello", http_event("GET", "/hello?name=test"))
    assert resp.status == 200
"""

GITIGNORE = ".pskit/\n.venv/\n__pycache__/\n*.pyc\n.env\n"


# --------------------------------------------------------------------- Node.js / TypeScript

NODE_CONFIG_HTTP = """service: {service}

provider:
  name: {provider}
  region: {region}
  stage: dev
  runtime: {runtime}
  memory: 256
  timeout: 15
  environment:
    LOG_LEVEL: INFO
{options}
functions:
  hello:
    handler: src.handlers.hello
    description: Says hello
    events:
      - http: GET /hello

  get-item:
    handler: src.handlers.getItem
    events:
      - http: GET /items/{{id}}

  create-item:
    handler: src.handlers.createItem
    events:
      - http:
          method: POST
          path: /items
          cors: true
"""

NODE_CONFIG_EVENTS = """
  nightly-report:
    handler: src.handlers.nightlyReport
    events:
      - schedule:
          cron: "0 2 * * *"
          input: {{report: daily}}

  process-jobs:
    handler: src.handlers.processJobs
    events:
      - queue: {{name: {service}-jobs, batch_size: 10}}

  on-upload:
    handler: src.handlers.onUpload
    events:
      - storage: {{bucket: {service}-uploads-change-me, events: [created], suffix: .csv}}
"""

NODE_CONFIG_WORKFLOW = """
  validate-order:
    handler: src.handlers.validateOrder

  charge-order:
    handler: src.handlers.chargeOrder

workflows:
  order-pipeline:
    description: Validate then charge an order
    start_at: Validate
    states:
      Validate:
        type: task
        function: validate-order
        retry: [{{errors: ["*"], max_attempts: 2}}]
        catch: [{{errors: ["ValidationError"], next: Rejected}}]
        next: Charge
      Charge:
        type: task
        function: charge-order
        end: true
      Rejected:
        type: fail
        error: OrderRejected
"""

TS_HTTP = """// HTTP handlers. This code runs unchanged on every supported cloud.
import { NotFound, Response } from "pskit";
import type { Context, Event } from "pskit";

const items: Record<string, { id: string; [key: string]: unknown }> = { "1": { id: "1", name: "first item" } };

export async function hello(event: Event, ctx: Context) {
  const name = event.http?.query.name ?? "world";
  ctx.logger.info("saying hello", { name });
  return { message: `Hello, ${name}!`, provider: event.provider, stage: ctx.stage };
}

export async function getItem(event: Event) {
  const id = event.http!.pathParams.id;
  const item = items[id];
  if (!item) throw new NotFound(`item ${id} does not exist`);
  return item;
}

export async function createItem(event: Event) {
  const body = event.http!.json() as Record<string, unknown>;
  const item = { ...body, id: String(Object.keys(items).length + 1) };
  items[item.id] = item;
  return Response.json(item, 201);
}
"""

TS_EVENTS = """
/** Runs on a schedule; `event.data` is the optional `input` from the YAML. */
export async function nightlyReport(event: Event, ctx: Context) {
  ctx.logger.info("nightly report", { input: event.data });
  return { ok: true };
}

/** Queue consumer: only failed records are retried where the cloud supports it. */
export async function processJobs(event: Event, ctx: Context) {
  const result = new BatchResult();
  for (const record of event.records) {
    try {
      ctx.logger.info("processing job", { job: record.json() });
    } catch {
      result.fail(record);
    }
  }
  return result;
}

export async function onUpload(event: Event, ctx: Context) {
  for (const record of event.records) {
    ctx.logger.info("object event", { bucket: record.bucket, key: record.key, action: record.action });
  }
}
"""

TS_WORKFLOW = """
export class ValidationError extends Error {}

export async function validateOrder(event: Event) {
  const order = { ...((event.data as Record<string, unknown>) ?? {}) };
  if (!(Number(order.amount) > 0)) throw new ValidationError("amount must be positive");
  return { ...order, valid: true };
}

export async function chargeOrder(event: Event) {
  return { ...(event.data as Record<string, unknown>), charged: true };
}
"""

JS_HTTP = """// HTTP handlers. This code runs unchanged on every supported cloud.
const { NotFound, Response } = require("pskit");

const items = { 1: { id: "1", name: "first item" } };

/** @param {import("pskit").Event} event @param {import("pskit").Context} ctx */
async function hello(event, ctx) {
  const name = (event.http && event.http.query.name) || "world";
  ctx.logger.info("saying hello", { name });
  return { message: `Hello, ${name}!`, provider: event.provider, stage: ctx.stage };
}

async function getItem(event) {
  const id = event.http.pathParams.id;
  const item = items[id];
  if (!item) throw new NotFound(`item ${id} does not exist`);
  return item;
}

async function createItem(event) {
  const item = { ...event.http.json(), id: String(Object.keys(items).length + 1) };
  items[item.id] = item;
  return Response.json(item, 201);
}
"""

JS_EVENTS = """
/** Runs on a schedule; `event.data` is the optional `input` from the YAML. */
async function nightlyReport(event, ctx) {
  ctx.logger.info("nightly report", { input: event.data });
  return { ok: true };
}

/** Queue consumer: only failed records are retried where the cloud supports it. */
async function processJobs(event, ctx) {
  const result = new BatchResult();
  for (const record of event.records) {
    try {
      ctx.logger.info("processing job", { job: record.json() });
    } catch {
      result.fail(record);
    }
  }
  return result;
}

async function onUpload(event, ctx) {
  for (const record of event.records) {
    ctx.logger.info("object event", { bucket: record.bucket, key: record.key, action: record.action });
  }
}
"""

JS_WORKFLOW = """
class ValidationError extends Error {}

async function validateOrder(event) {
  const order = { ...(event.data || {}) };
  if (!(Number(order.amount) > 0)) throw new ValidationError("amount must be positive");
  return { ...order, valid: true };
}

async function chargeOrder(event) {
  return { ...event.data, charged: true };
}
"""

TSCONFIG = """{
  "compilerOptions": {
    "target": "es2022",
    "module": "commonjs",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "noEmit": true,
    "paths": {
      "pskit": ["./.pskit/types/pskit/index.d.ts"]
    }
  },
  "include": ["src/**/*.ts"]
}
"""

NODE_GITIGNORE = ".pskit/\nnode_modules/\ndist/\n.env\n"


def _package_json(service: str, typescript: bool) -> str:
    import json

    scripts = {"dev": "pskit dev", "deploy": "pskit deploy"}
    if typescript:
        scripts["typecheck"] = "npx --yes -p typescript@5 tsc --noEmit"
    data = {"name": service, "version": "0.1.0", "private": True, "scripts": scripts, "dependencies": {}}
    return json.dumps(data, indent=2) + "\n"


def render_node(template: str, service: str, provider: str, runtime: str, typescript: bool) -> Dict[str, str]:
    """A JavaScript or TypeScript project: handlers in ``src/``, types for ``pskit`` in ``.pskit/types``."""
    config = NODE_CONFIG_HTTP
    code = TS_HTTP if typescript else JS_HTTP
    names = ["hello", "getItem", "createItem"]
    if template in ("events", "full"):
        config += NODE_CONFIG_EVENTS
        code += TS_EVENTS if typescript else JS_EVENTS
        names += ["nightlyReport", "processJobs", "onUpload"]
        code = code.replace('import { NotFound, Response } from "pskit";', 'import { BatchResult, NotFound, Response } from "pskit";')
        code = code.replace('const { NotFound, Response } = require("pskit");', 'const { BatchResult, NotFound, Response } = require("pskit");')
    if template in ("workflow", "full"):
        config += NODE_CONFIG_WORKFLOW
        code += TS_WORKFLOW if typescript else JS_WORKFLOW
        names += ["ValidationError", "validateOrder", "chargeOrder"]
    if not typescript:
        code += "\nmodule.exports = { " + ", ".join(names) + " };\n"
    files = {
        "pskit.yml": config.format(
            service=service,
            provider=provider,
            region=DEFAULT_REGIONS.get(provider, ""),
            options=PROVIDER_OPTIONS.get(provider, ""),
            runtime=runtime,
        ),
        f"src/handlers.{'ts' if typescript else 'js'}": code,
        "package.json": _package_json(service, typescript),
        ".gitignore": NODE_GITIGNORE,
    }
    if typescript:
        files["tsconfig.json"] = TSCONFIG
    return files


def render(
    template: str, service: str, provider: str, runtime: str = "python3.12", typescript: bool = False
) -> Dict[str, str]:
    if runtime.startswith("nodejs") or typescript:
        return render_node(template, service, provider, runtime if runtime.startswith("nodejs") else "nodejs20", typescript)
    region = DEFAULT_REGIONS.get(provider, "")
    config = CONFIG_HTTP
    handlers = HANDLERS_HTTP
    if template in ("events", "full"):
        config += CONFIG_EVENTS
        handlers += HANDLERS_EVENTS
    if template in ("workflow", "full"):
        config += CONFIG_WORKFLOW
        handlers += HANDLERS_WORKFLOW
    return {
        "pskit.yml": config.format(
            service=service, provider=provider, region=region, options=PROVIDER_OPTIONS.get(provider, "")
        ),
        "app/__init__.py": "",
        "app/handlers.py": handlers,
        "requirements.txt": "# Runtime dependencies of your functions (py-serverless-kit's runtime is vendored automatically)\n",
        "tests/test_handlers.py": TEST_FILE,
        ".gitignore": GITIGNORE,
    }
