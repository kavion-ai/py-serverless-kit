/**
 * In-browser mock of the studio API (VITE_MOCK=1 npm run dev:studio).
 * Only for UI development; it is never part of the production build.
 */
import { ApiError } from "./api";
import type { Driver, Field, Issue, Job, JsonObject, Meta, ProjectState, VsCodeState } from "./types";
import { asArray, asObject, isObject, normalizeEvent, str, toYaml } from "./util";

const secret = (key: string, label: string, required = false): Field => ({ key, label, type: "secret", required, env_ok: true });
const text = (key: string, label: string, extra: Partial<Field> = {}): Field => ({ key, label, type: "string", ...extra });
const int = (key: string, label: string, extra: Partial<Field> = {}): Field => ({ key, label, type: "int", ...extra });

const ALL = ["http", "schedule", "queue", "storage", "topic"];
const PY = ["python3.9", "python3.10", "python3.11", "python3.12", "python3.13"];

const s3Fields: Field[] = [
  text("bucket", "Bucket", { help: "default: the resource's native name" }),
  text("region", "Region", { placeholder: "us-east-1" }),
  secret("access_key", "Access key"),
  secret("secret_key", "Secret key"),
  text("prefix", "Prefix", { help: "Only watch keys below this prefix" }),
];

const QUEUE_DRIVERS: Driver[] = [
  { name: "builtin", label: "Built-in folder", cloud: "any", fields: [] },
  { name: "directory", label: "Existing folder", cloud: "any", fields: [text("path", "Path", { required: true })] },
  { name: "redis", label: "Redis", cloud: "self-hosted", fields: [{ ...text("url", "URL", { required: true, placeholder: "redis://host:6379/0" }), env_ok: true }, text("key", "List key")] },
  {
    name: "sqs",
    label: "Amazon SQS",
    cloud: "aws",
    fields: [text("queue_url", "Queue URL", { required: true, placeholder: "https://sqs.eu-west-1.amazonaws.com/123456789012/jobs" }), secret("access_key", "Access key"), secret("secret_key", "Secret key"), int("wait_seconds", "Long poll (s)", { min: 0, max: 20 })],
  },
  {
    name: "azure_queue",
    label: "Azure Storage Queue",
    cloud: "azure",
    fields: [secret("connection_string", "Connection string", true), text("queue", "Queue"), { key: "message_encoding", label: "Message encoding", type: "enum", options: ["base64", "text"], default: "base64" }],
  },
  {
    name: "pubsub",
    label: "Pub/Sub subscription",
    cloud: "gcp",
    fields: [text("subscription", "Subscription", { required: true, placeholder: "projects/p/subscriptions/s" }), text("topic", "Topic (for publishing)"), { key: "token_command", label: "Token command", type: "list", placeholder: "gcloud" }],
  },
  { name: "mns", label: "Alibaba MNS", cloud: "alibaba", fields: [text("account_id", "Account ID", { required: true }), text("region", "Region", { required: true }), text("queue", "Queue"), secret("access_key", "AccessKey ID", true), secret("secret_key", "AccessKey secret", true)] },
  { name: "cloudflare_queue", label: "Cloudflare Queues", cloud: "cloudflare", fields: [text("account_id", "Account ID", { required: true }), text("queue_id", "Queue ID", { required: true }), secret("api_token", "API token", true)] },
  { name: "custom", label: "Custom class", cloud: "any", fields: [text("class", "Class", { required: true, placeholder: "app.backends:RabbitQueue", help: "package.module:ClassName from your app" })] },
];

const STORAGE_DRIVERS: Driver[] = [
  { name: "builtin", label: "Built-in folder", cloud: "any", fields: [] },
  { name: "directory", label: "Existing folder", cloud: "any", fields: [text("path", "Path", { required: true })] },
  { name: "aws", label: "Amazon S3", cloud: "aws", fields: s3Fields },
  { name: "azure_blob", label: "Azure Blob", cloud: "azure", fields: [secret("connection_string", "Connection string", true), text("container", "Container"), text("prefix", "Prefix")] },
  { name: "gcs", label: "Cloud Storage", cloud: "gcp", fields: [text("bucket", "Bucket"), text("prefix", "Prefix"), { key: "token_command", label: "Token command", type: "list" }] },
  { name: "oss", label: "Alibaba OSS", cloud: "alibaba", fields: [text("region", "Region", { required: true }), ...s3Fields.filter((f) => f.key !== "region")] },
  { name: "cos", label: "Tencent COS", cloud: "tencent", fields: [text("region", "Region", { required: true }), ...s3Fields.filter((f) => f.key !== "region")] },
  { name: "obs", label: "Huawei OBS", cloud: "huawei", fields: [text("region", "Region", { required: true }), ...s3Fields.filter((f) => f.key !== "region")] },
  { name: "oci", label: "Oracle Object Storage", cloud: "oracle", fields: [text("region", "Region", { required: true }), text("namespace", "Namespace", { required: true }), ...s3Fields.filter((f) => f.key !== "region")] },
  { name: "ibm_cos", label: "IBM COS", cloud: "ibm", fields: [text("region", "Region", { required: true }), ...s3Fields.filter((f) => f.key !== "region")] },
  { name: "spaces", label: "DigitalOcean Spaces", cloud: "digitalocean", fields: [text("region", "Region", { required: true }), ...s3Fields.filter((f) => f.key !== "region")] },
  { name: "r2", label: "Cloudflare R2", cloud: "cloudflare", fields: [text("account_id", "Account ID", { required: true }), ...s3Fields.filter((f) => f.key !== "region")] },
  { name: "minio", label: "MinIO / Ceph", cloud: "self-hosted", fields: [text("endpoint", "Endpoint", { required: true, placeholder: "http://minio:9000" }), ...s3Fields.filter((f) => f.key !== "region")] },
  { name: "custom", label: "Custom class", cloud: "any", fields: [text("class", "Class", { required: true, placeholder: "app.backends:FolderStorage" })] },
];

export const MOCK_META: Meta = {
  version: "0.8.0-mock",
  providers: [
    { name: "aws", display_name: "AWS Lambda", tier: "stable", default_region: "us-east-1", capabilities: [...ALL, "workflow_native"], runtimes: PY, default_runtime: "python3.12", max_timeout: 900, options: [text("artifact_bucket", "Artifact bucket"), { key: "api_type", label: "API type", type: "enum", options: ["http", "rest"], default: "http" }] },
    { name: "gcp", display_name: "Google Cloud Functions", tier: "stable", default_region: "us-central1", capabilities: [...ALL, "workflow_native"], runtimes: PY, max_timeout: 3600, options: [text("project", "Project ID", { required: true, env_ok: true })] },
    { name: "azure", display_name: "Azure Functions", tier: "stable", default_region: "eastus", capabilities: ALL, runtimes: PY, max_timeout: 600, options: [text("subscription_id", "Subscription ID", { required: true, env_ok: true }), text("resource_group", "Resource group")] },
    { name: "alibaba", display_name: "Alibaba Cloud FC", tier: "beta", default_region: "cn-hangzhou", capabilities: ["http", "schedule", "queue", "storage", "topic"], runtimes: ["python3.9", "python3.10"], max_timeout: 600, options: [] },
    { name: "oracle", display_name: "OCI Functions", tier: "experimental", default_region: "us-ashburn-1", capabilities: ["http", "schedule"], runtimes: ["python3.11"], max_timeout: 300, options: [text("compartment_id", "Compartment OCID", { required: true, env_ok: true }), { key: "subnet_ids", label: "Subnet IDs", type: "list", required: true }, text("image", "Function image", { required: true })] },
    { name: "ibm", display_name: "IBM Code Engine", tier: "experimental", default_region: "us-south", capabilities: ["http", "schedule"], runtimes: ["python3.11"], max_timeout: 600, options: [] },
    { name: "digitalocean", display_name: "DigitalOcean Functions", tier: "experimental", default_region: "nyc1", capabilities: ["http", "schedule"], runtimes: ["python3.11"], max_timeout: 900, options: [text("namespace", "Namespace", { required: true, env_ok: true })] },
    { name: "tencent", display_name: "Tencent SCF", tier: "beta", default_region: "ap-guangzhou", capabilities: ["http", "schedule", "queue", "storage", "topic"], runtimes: ["python3.9", "python3.10"], max_timeout: 900, options: [] },
    { name: "huawei", display_name: "Huawei FunctionGraph", tier: "beta", default_region: "cn-north-4", capabilities: ["http", "schedule", "storage", "topic"], runtimes: ["python3.9", "python3.10"], max_timeout: 900, options: [] },
    { name: "cloudflare", display_name: "Cloudflare Workers", tier: "experimental", default_region: "global", capabilities: ["http", "schedule", "queue"], runtimes: ["python3.12"], max_timeout: 30, options: [text("account_id", "Account ID", { required: true, env_ok: true })] },
    {
      name: "onprem",
      display_name: "On-premises",
      tier: "experimental",
      default_region: "local",
      capabilities: ALL,
      runtimes: PY,
      max_timeout: 3600,
      notes: "Runs a long-lived Python process on this machine, a server over SSH, or Docker.",
      options: [text("host", "Bind address", { default: "127.0.0.1" }), int("port", "Port", { default: 8080, min: 1, max: 65535 }), text("advertise", "Advertised URL"), secret("admin_token", "Admin token"), { key: "poll_seconds", label: "Poll interval (s)", type: "number", default: 0.5 }],
    },
  ],
  events: {
    http: [],
    schedule: [],
    queue: [int("batch_size", "Batch size", { default: 10, min: 1, max: 10000 }), int("batch_window", "Batch window (s)", { default: 0, min: 0, max: 300 }), int("visibility_timeout", "Visibility timeout (s)"), text("dead_letter", "Dead-letter queue"), int("max_receive", "Max receives", { default: 5 }), { key: "fifo", label: "FIFO", type: "bool", default: false }],
    storage: [text("prefix", "Prefix"), text("suffix", "Suffix")],
    topic: [{ key: "filter", label: "Filter", type: "json", help: '{"event_type": ["created"]}' }],
  },
  function_fields: [],
  resource_types: ["storage", "queue", "topic", "database", "cache", "custom"],
  http_methods: ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "ANY"],
  auth_modes: ["none", "iam", "jwt", "key"],
  workflow: {
    state_types: ["task", "choice", "wait", "pass", "parallel", "map", "succeed", "fail"],
    choice_operators: ["equals", "not_equals", "gt", "gte", "lt", "lte", "in", "contains", "matches", "is_null", "is_present"],
    engines: ["auto", "native", "embedded"],
  },
  onprem: {
    deploy_methods: ["local", "ssh", "docker"],
    deploy_fields: {
      local: [{ key: "python", label: "Python", type: "enum", options: ["auto", "system", "bundle"], default: "auto" }],
      ssh: [text("host", "SSH host", { required: true }), text("user", "User"), int("port", "Port", { default: 22 }), text("pem", "Private key (.pem)"), text("path", "Remote path"), { key: "install", label: "Install as", type: "enum", options: ["process", "systemd"], default: "process" }, { key: "sudo", label: "Use sudo", type: "bool" }],
      docker: [text("host", "SSH host (remote Docker)"), text("pem", "Private key (.pem)"), text("image", "Image"), text("publish", "Publish"), { key: "docker_args", label: "Extra docker args", type: "list" }],
    },
    tuning: [int("execution_retention", "Executions kept", { default: 500, min: 1 }), int("workflow_workers", "Concurrent workflow runs", { default: 8, min: 1 }), int("log_buffer", "Log entries in memory", { default: 5000, min: 100 }), { key: "log_level", label: "Log level", type: "enum", options: ["DEBUG", "INFO", "WARNING", "ERROR"], default: "INFO" }, { key: "capture_output", label: "Capture print()", type: "bool", default: true }],
    services: ["queue", "storage", "topic"],
    drivers: { queue: QUEUE_DRIVERS, storage: STORAGE_DRIVERS, topic: QUEUE_DRIVERS.filter((d) => ["builtin", "directory"].includes(d.name)) },
  },
  handler_templates: {
    http: "def {name}(event, ctx):\n    return {\"ok\": True}\n",
  },
};

let project: JsonObject | null = {
  service: "orders",
  provider: { name: "aws", region: "eu-west-1", memory: 512, environment: { TABLE: "orders", API_KEY: "${env:ORDERS_API_KEY}" } },
  functions: {
    api: { handler: "app.handlers.api", description: "Public REST API", events: [{ http: "GET /orders/{id}" }, { http: { method: "POST", path: "/orders", cors: true } }] },
    worker: { handler: "app.handlers.work", events: [{ queue: { resource: "jobs", batch_size: 10 } }] },
    nightly: { handler: "app.handlers.nightly", events: [{ schedule: { cron: "0 2 * * *", timezone: "Europe/Berlin" } }] },
    charge: { handler: "app.payments.charge" },
    ship: { handler: "app.payments.ship" },
  },
  resources: {
    jobs: { type: "queue" },
    "orders-db": { type: "database", external: true, connection: { host: "db.internal", password_env: "ORDERS_DB_PASSWORD" } },
  },
  workflows: {
    fulfil: {
      description: "Charge, then ship or refund",
      start_at: "Charge",
      states: {
        Charge: { type: "task", function: "charge", next: "Paid?", retry: [{ errors: ["TimeoutError"], max_attempts: 3 }], catch: [{ errors: ["*"], next: "Failed" }] },
        "Paid?": { type: "choice", choices: [{ variable: "$.paid", equals: true, next: "Ship" }], default: "Failed" },
        Ship: { type: "task", function: "ship", end: true },
        Failed: { type: "fail", error: "Payment.Failed" },
      },
    },
  },
};
let mtime = 1;
const files: Record<string, string> = {
  "app/__init__.py": "",
  "app/handlers.py": 'from py_serverless_kit import Context, Event\n\n\ndef api(event: Event, ctx: Context):\n    return {"id": event.http.path_params.get("id")}\n\n\ndef work(event: Event, ctx: Context):\n    for record in event.records:\n        ctx.logger.info("job", extra={"id": record.id})\n\n\ndef nightly(event: Event, ctx: Context):\n    return {"ok": True}\n',
  "app/payments.py": "def charge(event, ctx):\n    return {**event.data, \"paid\": True}\n\n\ndef ship(event, ctx):\n    return event.data\n",
  "requirements.txt": "",
  "tests/test_handlers.py": "def test_ok():\n    assert True\n",
};
const fileTimes: Record<string, number> = {};
const jobs: Record<string, Job & { all: Job["lines"] }> = {};
let jobSeq = 0;
const vscode: VsCodeState = { docker: { available: true, version: "27.3.1" }, image: "codercom/code-server:4.96.4", image_present: false, running: false, url: null };

function validate(raw: JsonObject, provider?: string): Issue[] {
  const issues: Issue[] = [];
  if (!/^[a-z][a-z0-9-]{1,31}$/.test(str(raw.service))) issues.push({ level: "error", message: "service must be 2-32 lowercase letters, digits and dashes", where: "service" });
  const pname = provider || str(asObject(raw.provider).name, "aws");
  const meta = MOCK_META.providers.find((p) => p.name === pname);
  for (const [fn, cfg] of Object.entries(asObject(raw.functions))) {
    asArray(asObject(cfg).events).forEach((ev, i) => {
      const t = normalizeEvent(ev)?.type;
      if (t && meta && !meta.capabilities.includes(t)) issues.push({ level: "error", message: `${meta.display_name} does not support \`${t}\` events`, where: `functions.${fn}.events[${i}]` });
      const c = normalizeEvent(ev)?.config || {};
      if (c.resource && !(str(c.resource) in asObject(raw.resources))) issues.push({ level: "error", message: `unknown resource ${str(c.resource)}`, where: `functions.${fn}.events[${i}]` });
    });
  }
  for (const [wf, def] of Object.entries(asObject(raw.workflows))) {
    for (const [s, st] of Object.entries(asObject(asObject(def).states))) {
      const fn = asObject(st).function;
      if (fn && !(str(fn) in asObject(raw.functions))) issues.push({ level: "error", message: `workflow references unknown function ${str(fn)}`, where: `workflows.${wf}.states.${s}` });
    }
  }
  if (pname === "gcp" && !asObject(asObject(raw.provider).options).project) issues.push({ level: "error", message: "options.project is required", where: "provider.options.project" });
  if (Object.keys(asObject(raw.workflows)).length && meta && !meta.capabilities.includes("workflow_native")) {
    issues.push({ level: "warning", message: "runs on the embedded engine inside one function", where: `workflows.${Object.keys(asObject(raw.workflows))[0]}` });
  }
  return issues;
}

function state(): ProjectState {
  return { exists: !!project, path: "pskit.yml", raw: project, text: project ? toYaml(project) + "\n" : "", mtime, issues: project ? validate(project) : [], notices: ["Comments in pskit.yml are not preserved when the studio saves."] };
}

const sleep = (ms: number) => new Promise((r) => window.setTimeout(r, ms));

function startJob(command: string, lines: string[], fail = false): string {
  const id = `job${++jobSeq}`;
  const job = { job_id: id, command, status: "running" as Job["status"], exit_code: null as number | null, lines: [], all: [] as Job["lines"], next: 0, started_at: new Date().toISOString() };
  jobs[id] = job;
  lines.forEach((text, i) =>
    window.setTimeout(() => {
      job.all.push({ seq: i + 1, text, stream: text.startsWith("ERROR") ? "stderr" : "stdout" });
      if (i === lines.length - 1) {
        job.status = fail ? "failed" : "succeeded";
        job.exit_code = fail ? 1 : 0;
      }
    }, 250 * (i + 1)),
  );
  return id;
}

export async function mockRequest<T>(method: string, path: string, body?: unknown, query?: Record<string, string | number | undefined | null>): Promise<T> {
  await sleep(120 + Math.random() * 150);
  const b = (isObject(body as never) ? body : {}) as JsonObject;
  const q = query || {};
  const r = (v: unknown) => v as T;
  if (path === "/api/health") return r({ ok: true, version: MOCK_META.version, root: "/home/dev/orders" });
  if (path === "/api/meta") return r(MOCK_META);
  if (path === "/api/project" && method === "GET") return r(state());
  if (path === "/api/project" && method === "PUT") {
    if (!b.force && b.mtime !== mtime) throw new ApiError(409, "pskit.yml changed on disk", { code: "conflict", mtime });
    project = asObject(b.raw);
    mtime++;
    return r(state());
  }
  if (path === "/api/project/validate") {
    const raw = asObject(b.raw);
    const issues = validate(raw, str(b.provider) || undefined);
    const fns = Object.keys(asObject(raw.functions)).map((name) => ({ name, generated: false, kind: "http" }));
    const pname = str(b.provider) || str(asObject(raw.provider).name);
    const native = MOCK_META.providers.find((p) => p.name === pname)?.capabilities.includes("workflow_native");
    const engines: Record<string, string> = {};
    for (const wf of Object.keys(asObject(raw.workflows))) {
      engines[wf] = native ? "native" : "embedded";
      if (!native) fns.push({ name: `${wf}-orchestrator`, generated: true, kind: "http" });
    }
    return r({ ok: !issues.some((i) => i.level === "error"), issues, yaml: `# Managed by pskit studio\n${toYaml(raw)}\n`, functions: fns, engines });
  }
  if (path === "/api/project/parse") {
    const t = str(b.text);
    if (!t.includes("service:")) return r({ raw: null, issues: [{ level: "error", message: "mock parser: needs a service: key" }] });
    return r({ raw: project, issues: [{ level: "warning", message: "the mock parser returns the current project unchanged" }] });
  }
  if (path === "/api/project/init") {
    project = { service: str(b.service), provider: { name: str(b.provider) }, functions: { hello: { handler: "app.handlers.hello", events: [{ http: "GET /hello" }] } } };
    mtime++;
    return r(state());
  }
  if (path === "/api/files/tree") {
    const dirs = new Set<string>();
    Object.keys(files).forEach((f) => f.split("/").slice(0, -1).forEach((_, i, a) => dirs.add(a.slice(0, i + 1).join("/"))));
    return r({ entries: [...Array.from(dirs).map((d) => ({ path: d, type: "dir" })), ...Object.entries(files).map(([p, t]) => ({ path: p, type: "file", size: t.length }))] });
  }
  if (path === "/api/files" && method === "GET") {
    const p = str(q.path);
    if (!(p in files)) throw new ApiError(404, `no such file ${p}`);
    return r({ path: p, text: files[p], mtime: fileTimes[p] || 1, language: p.endsWith(".py") ? "python" : "text" });
  }
  if (path === "/api/files" && method === "PUT") {
    const p = str(b.path);
    if (b.mtime !== null && b.mtime !== undefined && p in files && b.mtime !== (fileTimes[p] || 1)) throw new ApiError(409, "file changed on disk", { code: "conflict" });
    files[p] = str(b.text);
    fileTimes[p] = (fileTimes[p] || 1) + 1;
    return r({ path: p, mtime: fileTimes[p] });
  }
  if (path === "/api/handlers/ensure") {
    const handler = str(b.handler);
    const parts = handler.split(".");
    const fn = parts.pop() || "handler";
    const file = `${parts.join("/")}.py`;
    const current = files[file] || "";
    if (new RegExp(`def ${fn}\\(`).test(current)) return r({ path: file, created: false });
    files[file] = `${current}\n\ndef ${fn}(event, ctx):\n    return {"ok": True}\n`;
    return r({ path: file, created: true, line: files[file].split("\n").length - 2 });
  }
  if (path === "/api/functions/shared") {
    const byModule: Record<string, string[]> = {};
    for (const [name, fn] of Object.entries(asObject(project?.functions))) {
      const handler = str(asObject(fn).handler);
      if (!handler || handler.startsWith("functions.")) continue;
      const module = handler.replace(":", ".").split(".").slice(0, -1).join(".");
      (byModule[module] = byModule[module] || []).push(name);
    }
    return r({ shared: Object.fromEntries(Object.entries(byModule).filter(([, names]) => names.length > 1).map(([m, names]) => [m, names.sort()])) });
  }
  const sm = /^\/api\/functions\/([^/]+)\/split$/.exec(path);
  if (sm && method === "POST") {
    const name = decodeURIComponent(sm[1]);
    const fn = asObject(asObject(project?.functions)[name]);
    if (!project || !fn.handler) throw new ApiError(400, `no function '${name}' in pskit.yml`);
    const parts = str(fn.handler).replace(":", ".").split(".");
    const func = parts.pop() || "main";
    const folder = name.replace(/-/g, "_");
    const result = { function: name, from: `${parts.join("/")}.py`, to: `functions/${folder}/handler.py`, handler: `functions.${folder}.handler.${func}`, requirements: [], unknown_imports: [], helpers: [], kept_in_source: false };
    if (!b.dry_run) {
      project = { ...project, functions: { ...asObject(project.functions), [name]: { ...fn, handler: result.handler } } };
      files[result.to] = `from py_serverless_kit import Context, Event\n\n\ndef ${func}(event: Event, ctx: Context):\n    return {"ok": True}\n`;
      files[`functions/${folder}/requirements.txt`] = "";
      mtime++;
    }
    return r({ ...result, lines: [`${name}: ${result.from} -> ${result.to} (handler ${result.handler})`], project: state() });
  }
  if (path === "/api/discover") {
    const provider = str(q.provider);
    if (!["aws", "gcp", "azure", "onprem"].includes(provider)) return r({ supported: false, reason: `Listing isn't available for ${provider}; type the name.`, items: [] });
    if (provider === "azure") return r({ supported: false, reason: "pip install azure-identity azure-mgmt-storage to list Azure resources.", items: [] });
    const kind = str(q.kind);
    const names = kind === "storage" ? ["company-media", "invoices-prod", "logs-archive"] : kind === "queue" ? ["orders-jobs", "emails", "orders-jobs-dlq"] : ["order-events", "audit"];
    return r({ supported: true, items: names.map((n) => ({ name: n, arn: provider === "aws" ? `arn:aws:${kind === "storage" ? "s3" : kind === "queue" ? "sqs" : "sns"}:eu-west-1:123456789012:${n}` : undefined, region: "eu-west-1" })) });
  }
  if (path === "/api/jobs" && method === "POST") {
    const command = str(b.command);
    if (Object.values(jobs).some((j) => j.status === "running" && ["deploy", "remove", "package", "plan"].includes(j.command)) && ["deploy", "remove", "package", "plan"].includes(command)) {
      throw new ApiError(409, "another deploy-type job is running", { code: "busy" });
    }
    const lines = command === "deploy"
      ? ["Packaging orders (aws/dev)…", "  artifact: 182 KiB, 41 files", "terraform init", "terraform apply -auto-approve", "  aws_lambda_function.api: Creating...", "  aws_lambda_function.api: Creation complete after 9s", "Apply complete! Resources: 14 added, 0 changed, 0 destroyed.", "endpoint: https://abc123.execute-api.eu-west-1.amazonaws.com"]
      : command === "validate"
        ? ["orders -> AWS Lambda [stable] stage=dev region=eu-west-1", "  5 function(s), 1 workflow(s)", "Configuration is valid."]
        : [`pskit ${command} …`, "\u001b[32mdone\u001b[0m"];
    return r({ job_id: startJob(command, lines, command === "remove") });
  }
  if (path === "/api/jobs" && method === "GET") return r({ jobs: Object.values(jobs).reverse().map(({ all, ...j }) => ({ ...j, lines: [], next: all.length })) });
  const jm = /^\/api\/jobs\/([^/]+)(\/cancel)?$/.exec(path);
  if (jm) {
    const job = jobs[decodeURIComponent(jm[1])];
    if (!job) throw new ApiError(404, "unknown job");
    if (jm[2]) {
      job.status = "cancelled";
      return r({ ...job, lines: [], next: job.all.length });
    }
    const since = Number(q.since || 0);
    const lines = job.all.filter((l) => l.seq > since);
    return r({ job_id: job.job_id, command: job.command, status: job.status, exit_code: job.exit_code, lines, next: job.all.length, started_at: job.started_at });
  }
  if (path === "/api/jobs" && method === "DELETE") {
    const done = Object.keys(jobs).filter((k) => jobs[k].status !== "running");
    done.forEach((k) => delete jobs[k]);
    return r({ removed: done.length });
  }
  if (path.startsWith("/api/jobs/") && method === "DELETE") {
    const id = decodeURIComponent(path.split("/")[3]);
    if (!jobs[id]) throw new ApiError(404, "unknown job");
    delete jobs[id];
    return r({ removed: 1 });
  }
  if (path === "/api/fs") {
    const dir = String(query?.path || "/home/dev/.ssh");
    return r({
      path: dir,
      parent: dir === "/" ? null : dir.replace(/\/[^/]+$/, "") || "/",
      home: "/home/dev",
      roots: ["/"],
      entries: [
        { name: "config", path: `${dir}/config`, type: "file", size: 120, key: false },
        { name: "id_ed25519", path: `${dir}/id_ed25519`, type: "file", size: 411, key: true },
        { name: "id_ed25519.pub", path: `${dir}/id_ed25519.pub`, type: "file", size: 98, key: false },
        { name: "server.pem", path: `${dir}/server.pem`, type: "file", size: 1675, key: true },
      ],
    });
  }
  if (path === "/api/setup") {
    return r({
      provider: String(query?.provider || "aws"),
      ok: false,
      platform: "linux",
      checks: [
        { id: "terraform", title: "Terraform", status: "ok", detail: "Terraform v1.9.8", fix: null },
        {
          id: "cli",
          title: "AWS CLI",
          status: "missing",
          detail: "aws is not on PATH (optional, used for SSO logins)",
          fix: {
            summary: "Install the AWS CLI v2.",
            links: [{ label: "Install guide", url: "https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html" }],
            steps: { linux: ["curl -o awscliv2.zip https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip", "unzip awscliv2.zip && sudo ./aws/install"] },
            commands: ["aws --version"],
          },
        },
        { id: "credentials", title: "AWS credentials", status: "missing", detail: "No credentials found", fix: { summary: "Add an access key.", action: "aws-profile" } },
      ],
      env: [{ name: "AWS_PROFILE", help: "Profile in ~/.aws to use", secret: false, set: false, value: null }],
    });
  }
  if (path === "/api/setup/env") return r({ name: b.name, set: !!b.value });
  if (path === "/api/setup/aws-profile") return r({ profile: b.profile, path: "~/.aws/credentials" });
  if (path === "/api/logs") return r({ supported: false, reason: "mock: deploy first", entries: [], next: 0 });
  if (path === "/api/logs/streams") return r({ supported: false, reason: "mock: deploy first", items: [] });
  if (path === "/api/vscode" && method === "GET") return r({ ...vscode });
  if (path === "/api/vscode/start") {
    const id = startJob("vscode", vscode.image_present ? ["docker run -d … codercom/code-server:4.96.4", "waiting for code-server…", "ready"] : ["Pulling codercom/code-server:4.96.4", "4.96.4: Pulling from codercom/code-server", "Downloading  312MB/598MB", "Downloading  598MB/598MB", "Status: Downloaded newer image", "docker run -d …", "ready"]);
    window.setTimeout(() => {
      vscode.image_present = true;
      vscode.running = true;
      vscode.url = "http://127.0.0.1:18080/?folder=/home/coder/project";
    }, 2200);
    return r({ job_id: id });
  }
  if (path === "/api/vscode/stop") {
    vscode.running = false;
    vscode.url = null;
    return r({ ...vscode });
  }
  throw new ApiError(404, `mock: no route for ${method} ${path}`);
}
