import type { LogsResponse, LogStream } from "../types";
import type {
  BalancerAction,
  ClusterAction,
  ClusterAlertEntry,
  ClusterRequests,
  ClusterStatus,
  OnPremAlert,
  OnPremAlertRecord,
  OnPremCluster,
  OnPremMonitorSample,
  ServerMetrics,
  OnPremClustersState,
  SettingsImportResult,
  SettingsPreview,
  SettingsSummary,
  DiscoverResult,
  OnPremConsoleInfo,
  OnPremConsoleResult,
  OnPremDeployed, OnPremServer,
  OnPremFirewall,
  OnPremUsage,
  ResourceBinding,
  OnPremServerTest,
  OnPremTerminal,
  FileContent,
  FileEntry,
  FsListing,
  FunctionSplitResult,
  Job,
  JsonObject,
  Meta,
  NamedBalancer,
  NamedBalancerStatus,
  OnPremBalancersState,
  ProjectState,
  SetupResult,
  SavedTestEvent,
  TestGuide,
  ResourceTestGuide,
  CloudResourceRow,
  DevEnvStatus,
  GuideIndex,
  GuidePage,
  HanaEnv,
  HanaRuntime,
  HanaSessionDetail,
  HanaState,
  HanaTurn,
  OnPremService,
  OnPremServicesState,
  ResourceCheck,
  ResourcePage,
  ValidateResult,
  VsCodeState,
} from "./types";

const TOKEN_KEY = "pskit-studio-token";

export class ApiError extends Error {
  status: number;
  code?: string;
  body: Record<string, unknown>;

  constructor(status: number, message: string, body: Record<string, unknown> = {}) {
    super(message);
    this.status = status;
    this.code = typeof body.code === "string" ? body.code : undefined;
    this.body = body;
  }
}

function readSession(key: string): string | null {
  try {
    return window.sessionStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeSession(key: string, value: string): void {
  try {
    window.sessionStorage.setItem(key, value);
  } catch {
    /* private mode: the token stays in memory for this page */
  }
}

let memoryToken: string | null = null;

/** Take `#token=...` from the URL (once), keep it in sessionStorage, and remove it from the address bar. */
export function captureToken(): string | null {
  const match = /(?:^#|[#&])token=([A-Za-z0-9_\-.~%]+)/.exec(window.location.hash);
  if (match) {
    memoryToken = decodeURIComponent(match[1]);
    writeSession(TOKEN_KEY, memoryToken);
    // Keep any route in the hash (e.g. `#/functions&token=...`) so links can point at a page.
    let rest = window.location.hash.replace(/[#&]token=[^&]*/, "").replace(/^#?&/, "#");
    if (!rest || rest === "#") rest = "#/";
    const url = window.location.pathname + window.location.search + rest;
    window.history.replaceState(null, "", url);
  }
  return token();
}

export function token(): string | null {
  return memoryToken || readSession(TOKEN_KEY);
}

export const MOCK = import.meta.env.VITE_MOCK === "1";

type Method = "GET" | "POST" | "PUT" | "DELETE";

export interface RequestOptions {
  signal?: AbortSignal;
  query?: Record<string, string | number | undefined | null>;
}

async function request<T>(method: Method, path: string, body?: unknown, opts: RequestOptions = {}): Promise<T> {
  if (MOCK) {
    const { mockRequest } = await import("./mock");
    return mockRequest<T>(method, path, body, opts.query);
  }
  let url = path;
  if (opts.query) {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(opts.query)) {
      if (v !== undefined && v !== null && v !== "") params.set(k, String(v));
    }
    const qs = params.toString();
    if (qs) url += "?" + qs;
  }
  const headers: Record<string, string> = { accept: "application/json" };
  const t = token();
  if (t) headers["x-studio-token"] = t;
  if (body !== undefined) headers["content-type"] = "application/json";
  let resp: Response;
  try {
    resp = await fetch(url, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: opts.signal,
      cache: "no-store",
      credentials: "same-origin",
    });
  } catch (exc) {
    if (exc instanceof DOMException && exc.name === "AbortError") throw exc;
    throw new ApiError(0, "pskit studio is not reachable. Is `pskit studio` still running?");
  }
  const text = await resp.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { error: text.slice(0, 300) };
    }
  }
  if (!resp.ok) {
    const obj = (data && typeof data === "object" ? data : {}) as Record<string, unknown>;
    const msg = typeof obj.error === "string" ? obj.error : `HTTP ${resp.status}`;
    throw new ApiError(resp.status, msg, obj);
  }
  return data as T;
}

export const api = {
  health: () => request<{ ok: boolean; version: string; root: string }>("GET", "/api/health"),
  meta: () => request<Meta>("GET", "/api/meta"),
  project: () => request<ProjectState>("GET", "/api/project"),
  validate: (raw: JsonObject, provider?: string, stage?: string, signal?: AbortSignal) =>
    request<ValidateResult>("POST", "/api/project/validate", { raw, provider, stage }, { signal }),
  parse: (text: string) => request<{ raw: JsonObject | null; issues: ValidateResult["issues"] }>("POST", "/api/project/parse", { text }),
  save: (raw: JsonObject, mtime?: number | null, force?: boolean) =>
    request<ProjectState>("PUT", "/api/project", { raw, mtime, force }),
  init: (service: string, provider: string, template: string, force?: boolean, language?: string) =>
    request<ProjectState>("POST", "/api/project/init", { service, provider, template, force, language }),
  tree: () => request<{ entries: FileEntry[] }>("GET", "/api/files/tree"),
  file: (path: string) => request<FileContent>("GET", "/api/files", undefined, { query: { path } }),
  writeFile: (path: string, text: string, mtime?: number | null) =>
    request<{ path: string; mtime: number }>("PUT", "/api/files", { path, text, mtime }),
  /** `subproject`: the handler's folder (functions/<name>/) gets its own requirements.txt / package.json. */
  ensureHandler: (handler: string, events: string[], subproject = false) =>
    request<{ path: string; created: boolean; line?: number }>("POST", "/api/handlers/ensure", { handler, events, ...(subproject ? { subproject: true } : {}) }),
  /** Code files holding the handlers of more than one function (pskit.yml on disk): `{module: [functions]}`. */
  functionsShared: () => request<{ shared: Record<string, string[]> }>("GET", "/api/functions/shared"),
  /** Move a function into functions/<name>/ (pskit function split). `dryRun`: only the plan; nothing is written. */
  splitFunction: (name: string, dryRun = false) =>
    request<FunctionSplitResult>("POST", `/api/functions/${encodeURIComponent(name)}/split`, dryRun ? { dry_run: true } : {}),
  discover: (provider: string, kind: string, region?: string) =>
    request<DiscoverResult>("GET", "/api/discover", undefined, { query: { provider, kind, region } }),
  startJob: (command: string, provider?: string, stage?: string, args?: Record<string, unknown>) =>
    request<{ job_id: string }>("POST", "/api/jobs", { command, provider, stage, args }),
  job: (id: string, since: number) =>
    request<Job>("GET", `/api/jobs/${encodeURIComponent(id)}`, undefined, { query: { since } }),
  jobs: () => request<{ jobs: Job[] }>("GET", "/api/jobs"),
  cancelJob: (id: string) => request<Job>("POST", `/api/jobs/${encodeURIComponent(id)}/cancel`, {}),
  clearJobs: () => request<{ removed: number }>("DELETE", "/api/jobs"),
  deleteJob: (id: string) => request<{ removed: number }>("DELETE", `/api/jobs/${encodeURIComponent(id)}`),
  cloudResources: (provider: string, stage: string) =>
    request<{ deployed: CloudResourceRow[]; kept: CloudResourceRow[]; reason?: string }>("GET", "/api/cloud-resources", undefined, {
      query: { provider, stage },
    }),
  testGuide: (provider: string, stage: string) => request<TestGuide>("GET", "/api/test-guide", undefined, { query: { provider, stage } }),
  resourceTestGuide: (provider: string, stage: string) =>
    request<ResourceTestGuide>("GET", "/api/resource-test-guide", undefined, { query: { provider, stage } }),
  testEvents: () => request<Record<string, SavedTestEvent[]>>("GET", "/api/test-events"),
  saveTestEvents: (events: Record<string, SavedTestEvent[]>) => request<Record<string, SavedTestEvent[]>>("PUT", "/api/test-events", { events }),
  browse: (path?: string) => request<FsListing>("GET", "/api/fs", undefined, { query: { path } }),
  setup: (provider: string) => request<SetupResult>("GET", "/api/setup", undefined, { query: { provider } }),
  setEnv: (name: string, value: string) => request<{ name: string; set: boolean }>("POST", "/api/setup/env", { name, value }),
  awsProfile: (body: { profile: string; access_key_id: string; secret_access_key: string; region?: string; session_token?: string }) =>
    request<Record<string, unknown>>("POST", "/api/setup/aws-profile", body),
  login: (action: string) => request<{ job_id: string }>("POST", "/api/setup/login", { action }),
  sshTest: (deploy: JsonObject) => request<{ job_id: string }>("POST", "/api/setup/ssh-test", { deploy }),
  settingsExport: (passphrase: string, includeConfig = false) =>
    request<{ filename: string; content: string; summary: SettingsSummary }>("POST", "/api/settings-bundle/export", {
      passphrase,
      include_config: includeConfig,
    }),
  settingsPreview: (content: string, passphrase: string, replace: boolean) =>
    request<SettingsPreview>("POST", "/api/settings-bundle/preview", { content, passphrase, replace }),
  settingsImport: (content: string, passphrase: string, replace: boolean) =>
    request<SettingsImportResult>("POST", "/api/settings-bundle/import", { content, passphrase, replace }),
  logs: (
    provider: string,
    stage: string,
    p: { since?: number; limit?: number; level?: string; function?: string; q?: string; source?: string },
    server?: string,
  ) => request<LogsResponse>("GET", "/api/logs", undefined, { query: { provider, stage, server, ...p } }),
  logStreams: (provider: string, stage: string, fn?: string, server?: string) =>
    request<{ supported: boolean; reason?: string; can_delete?: boolean; items: LogStream[] }>("GET", "/api/logs/streams", undefined, {
      query: { provider, stage, function: fn, server },
    }),
  deleteLogs: (provider: string, stage: string, body: { ids?: string[]; all?: boolean; function?: string }, server?: string) =>
    request<{ deleted: number; errors?: string[] }>("POST", "/api/logs/delete", body, { query: { provider, stage, server } }),
  vscode: () => request<VsCodeState>("GET", "/api/vscode"),
  vscodeStart: (image?: string, python?: string, node?: string) => request<{ job_id: string }>("POST", "/api/vscode/start", { image, python, node }),
  env: () => request<DevEnvStatus>("GET", "/api/env"),
  envSetup: (body: { python?: string; recreate?: boolean; language?: string }) => request<{ job_id: string }>("POST", "/api/env/setup", body),
  vscodeStop: () => request<VsCodeState>("POST", "/api/vscode/stop", {}),
  onpremServices: () => request<OnPremServicesState>("GET", "/api/onprem-services"),
  onpremCreate: (body: JsonObject) => request<{ job_id: string }>("POST", "/api/onprem-services", body),
  onpremStatus: (key: string, reveal = false) =>
    request<OnPremService>("GET", `/api/onprem-services/${encodeURIComponent(key)}`, undefined, { query: { reveal: reveal ? "1" : undefined } }),
  onpremGui: (key: string, opts: { port?: number; login?: "password" | "none"; password?: string } = {}) =>
    request<{ job_id: string }>("POST", `/api/onprem-services/${encodeURIComponent(key)}/gui`, opts),
  onpremGuiCheck: (key: string) => request<{ job_id: string }>("POST", `/api/onprem-services/${encodeURIComponent(key)}/gui-check`, {}),
  onpremGuiRemove: (key: string) => request<{ job_id: string }>("POST", `/api/onprem-services/${encodeURIComponent(key)}/gui-remove`, {}),
  onpremLogs: (key: string) => request<{ text: string }>("GET", `/api/onprem-services/${encodeURIComponent(key)}/logs`),
  onpremBackup: (key: string, folder?: string) =>
    request<{ job_id: string }>("POST", `/api/onprem-services/${encodeURIComponent(key)}/backup`, folder ? { folder } : {}),
  onpremMonitor: (key: string) => request<OnPremMonitorSample>("GET", `/api/onprem-services/${encodeURIComponent(key)}/monitor`),
  onpremAlert: (key: string) =>
    request<{ alert: OnPremAlert; history: OnPremAlertRecord[]; last?: { checked_at: string; reasons?: string[]; error?: string } | null }>(
      "GET",
      `/api/onprem-services/${encodeURIComponent(key)}/alert`,
    ),
  onpremAlertSave: (key: string, alert: Partial<OnPremAlert>) =>
    request<{ alert: OnPremAlert; history: OnPremAlertRecord[] }>("PUT", `/api/onprem-services/${encodeURIComponent(key)}/alert`, alert as JsonObject),
  onpremAlertTest: (key: string) => request<OnPremAlertRecord>("POST", `/api/onprem-services/${encodeURIComponent(key)}/alert-test`, {}),
  onpremAlertCheck: (key: string) =>
    request<{ reasons: string[]; checked_at: string; alert?: JsonObject }>("POST", `/api/onprem-services/${encodeURIComponent(key)}/alert-check`, {}),
  onpremAlertFunction: (handler: string) =>
    request<{ path: string; created: boolean }>("POST", "/api/onprem-services/alert-function", { handler }),
  onpremServersReachability: () => request<{ servers: Record<string, { ok: boolean; ms?: number; error?: string }> }>("GET", "/api/onprem-servers/reachability"),
  onpremServerMetrics: (name: string) => request<ServerMetrics>("GET", `/api/onprem-servers/${encodeURIComponent(name)}/metrics`),
  onpremRemove: (key: string, deleteData: boolean) =>
    request<{ job_id: string }>("POST", `/api/onprem-services/${encodeURIComponent(key)}/remove`, { delete_data: deleteData }),
  onpremReplicaAdd: (key: string, server: string) =>
    request<{ job_id: string }>("POST", `/api/onprem-services/${encodeURIComponent(key)}/replicas`, { server }),
  onpremReplicaRemove: (key: string, name: string, deleteData: boolean) =>
    request<{ job_id: string }>("POST", `/api/onprem-services/${encodeURIComponent(key)}/replicas-remove`, { name, delete_data: deleteData }),
  onpremConsoleInfo: (key: string) => request<OnPremConsoleInfo>("GET", `/api/onprem-services/${encodeURIComponent(key)}/console`),
  onpremConsole: (key: string, line: string, shell = false) =>
    request<OnPremConsoleResult>("POST", `/api/onprem-services/${encodeURIComponent(key)}/console`, { line, shell }),
  onpremBrowse: <T>(key: string, kind: string, action: string, body: Record<string, unknown> = {}) =>
    request<T>("POST", `/api/onprem-services/${encodeURIComponent(key)}/browse/${encodeURIComponent(kind)}/${encodeURIComponent(action)}`, body),
  onpremServers: (stage?: string) =>
    request<{ servers: OnPremServer[]; deployed?: OnPremDeployed | null }>("GET", "/api/onprem-servers", undefined, { query: { stage } }),
  onpremServerSave: (name: string, target: JsonObject, description?: string) =>
    request<{ name: string }>("POST", "/api/onprem-servers", { name, target, description }),
  onpremServerTest: (name: string) => request<OnPremServerTest>("POST", `/api/onprem-servers/${encodeURIComponent(name)}/test`, {}),
  onpremServerRemove: (name: string) => request<{ removed: string; warnings?: string[] }>("POST", `/api/onprem-servers/${encodeURIComponent(name)}/remove`, {}),
  onpremServerShell: (name: string, line: string) =>
    request<OnPremConsoleResult>("POST", `/api/onprem-servers/${encodeURIComponent(name)}/shell`, { line }),
  onpremTerminals: () => request<{ terminals: OnPremTerminal[] }>("GET", "/api/onprem-terminals"),
  onpremTerminalStart: (body: { server?: string; key?: string; shell?: boolean }) => request<OnPremTerminal>("POST", "/api/onprem-terminals", body),
  onpremTerminalStop: (name: string) => request<{ stopped: string }>("POST", `/api/onprem-terminals/${encodeURIComponent(name)}/stop`, {}),
  firewall: () => request<OnPremFirewall>("GET", "/api/onprem-firewall"),
  onpremServerUsage: () => request<OnPremUsage>("GET", "/api/onprem-usage"),
  resourceBindings: () => request<{ resources: Record<string, ResourceBinding> }>("GET", "/api/resource-bindings"),
  clusters: () => request<OnPremClustersState>("GET", "/api/onprem-clusters"),
  clusterCreate: (body: { name: string; orchestrator: string; master: string; advertise?: string; master_serves?: boolean }) =>
    request<{ job_id: string }>("POST", "/api/onprem-clusters", body),
  clusterRequests: (name: string, stack: string, since: number) =>
    request<ClusterRequests>(
      "GET",
      `/api/onprem-clusters/${encodeURIComponent(name)}/requests?${new URLSearchParams({ stack, since: String(since), limit: since ? "500" : "100" })}`,
    ),
  clusterStatus: (name: string) => request<ClusterStatus>("GET", `/api/onprem-clusters/${encodeURIComponent(name)}/status`),
  clusterCheck: (name: string) => request<ClusterStatus>("POST", `/api/onprem-clusters/${encodeURIComponent(name)}/check`, {}),
  clusterTestAlert: (name: string) => request<ClusterAlertEntry>("POST", `/api/onprem-clusters/${encodeURIComponent(name)}/test-alert`, {}),
  clusterSettings: (name: string, body: JsonObject) => request<OnPremCluster>("PUT", `/api/onprem-clusters/${encodeURIComponent(name)}/settings`, body),
  clusterAction: (name: string, action: ClusterAction, body: JsonObject = {}) =>
    request<{ job_id: string }>("POST", `/api/onprem-clusters/${encodeURIComponent(name)}/${action}`, body),
  clusterBalancerLogs: (name: string, lines: number) =>
    request<{ text: string }>("GET", `/api/onprem-clusters/${encodeURIComponent(name)}/balancer-logs?lines=${lines}`),
  balancers: () => request<OnPremBalancersState>("GET", "/api/onprem-balancers"),
  balancerCreate: (body: {
    name: string;
    server: string;
    port?: number;
    address?: string;
    algorithm?: string;
    weights?: Record<string, number>;
    clusters?: string[];
  }) => request<{ job_id: string }>("POST", "/api/onprem-balancers", body),
  balancer: (name: string) => request<NamedBalancer>("GET", `/api/onprem-balancers/${encodeURIComponent(name)}`),
  balancerStatus: (name: string) => request<NamedBalancerStatus>("GET", `/api/onprem-balancers/${encodeURIComponent(name)}/status`),
  balancerLogs: (name: string, lines: number) =>
    request<{ text: string }>("GET", `/api/onprem-balancers/${encodeURIComponent(name)}/logs`, undefined, { query: { lines } }),
  balancerForget: (name: string) => request<{ forgotten: string }>("POST", `/api/onprem-balancers/${encodeURIComponent(name)}/forget`, {}),
  balancerAction: (name: string, action: BalancerAction, body: JsonObject = {}) =>
    request<{ job_id: string }>("POST", `/api/onprem-balancers/${encodeURIComponent(name)}/${action}`, body),
  onpremApply: (raw: JsonObject, key: string, attach?: string[]) =>
    request<{ raw: JsonObject }>("POST", "/api/onprem-services/apply", { raw, key, attach }),
  onpremUnapply: (raw: JsonObject, key: string) => request<{ raw: JsonObject }>("POST", "/api/onprem-services/unapply", { raw, key }),
  resourceCheck: (provider: string, stage: string, key: string) =>
    request<ResourceCheck>("POST", "/api/resource-check", { provider, stage, key }),
  resourceClear: (provider: string, stage: string, key: string) =>
    request<{ key: string; deleted: number; path: string }>("POST", "/api/resource-clear", { provider, stage, key }),
  resourceUsage: (provider: string, stage: string, key: string) =>
    request<{ key: string; title: string; markdown: string }>("POST", "/api/resource-usage", { provider, stage, key }),
  resourceData: (provider: string, stage: string, key: string, offset: number, limit: number, prefix?: string) =>
    request<ResourcePage>("POST", "/api/resource-data", { provider, stage, key, offset, limit, prefix }),
  resourceObject: (provider: string, stage: string, key: string, object: string, del = false) =>
    request<{ key?: string; size?: number; encoding?: string; content?: string; truncated?: boolean; deleted?: boolean }>(
      "POST", "/api/resource-object", { provider, stage, key, object, delete: del }),
  resourceMessageDelete: (provider: string, stage: string, key: string, id: string) =>
    request<{ deleted: boolean }>("POST", "/api/resource-message-delete", { provider, stage, key, id }),
  onpremUsage: (key: string, reveal = false) =>
    request<{ key: string; markdown: string }>("GET", `/api/onprem-services/${encodeURIComponent(key)}/usage`, undefined, {
      query: { reveal: reveal ? "1" : undefined },
    }),
  guides: () => request<GuideIndex>("GET", "/api/resource-guides"),
  guide: (cloud: string, page: string) =>
    request<GuidePage>("GET", `/api/resource-guides/${encodeURIComponent(cloud)}/${encodeURIComponent(page)}`),
  hana: () => request<HanaState>("GET", "/api/hana"),
  hanaInstall: (target: "local" | "server" | "huggingface", opts: { server?: string; image?: string; file?: string } = {}) =>
    request<{ job_id: string }>("POST", "/api/hana/install", { target, ...opts }),
  hanaRemoveItem: (kind: string, name: string, deleteCode: boolean) =>
    request<{ removed: string; changed: string[]; code: string }>("POST", "/api/hana/remove-item", { kind, name, delete_code: deleteCode }),
  hanaDeleteAll: () => request<{ deleted: number }>("DELETE", "/api/hana/sessions"),
  /** `placement`: "separate" (each function its own app with its own requirements.txt) or "module" (into `module`).
   * `existing`: for names already in pskit.yml, "update" | "rename" | "skip". */
  hanaFunctions: (
    names: string[],
    trigger: string,
    schedule: string,
    opts: { placement: "separate" | "module"; module?: string; existing?: Record<string, string> },
  ) =>
    request<{
      created: string[];
      updated: string[];
      renamed: Record<string, string>;
      skipped: string[];
      code: { function: string; handler: string; file: string; written: boolean }[];
      moved: { function: string; from: string; to: string }[];
      move_errors: string[];
      deleted: string[];
      validate: string;
    }>("POST", "/api/hana/functions", { names, trigger, schedule, ...opts }),
  /** Existing functions into their own apps (functions/<name>/ with its own requirements.txt). */
  hanaSeparate: (functions: string[]) =>
    request<{ moved: { function: string; from: string; to: string; requirements: string[] }[]; already: string[]; errors: string[]; deleted: string[]; validate: string }>(
      "POST",
      "/api/hana/separate",
      { functions },
    ),
  hanaResources: (items: JsonObject[]) =>
    request<{ created: string[]; replaced?: string[]; validate: string }>("POST", "/api/hana/resources", { items }),
  hanaCode: (functions: string[]) =>
    request<{ written: { function: string; handler: string; file: string; written: boolean }[] }>("POST", "/api/hana/code", { functions }),
  hanaWorkflow: (name: string, steps: string[], description = "", waitSeconds = 0, createFunctions: string[] = []) =>
    request<{ created: string; states: string[]; functions: string[]; stubs: string[]; validate: string }>("POST", "/api/hana/workflow", {
      name,
      steps,
      description,
      wait_seconds: waitSeconds,
      create_functions: createFunctions,
    }),
  hanaEndpoint: (url: string, apiKeyEnv?: string) =>
    request<HanaRuntime>("POST", "/api/hana/endpoint", { url, api_key_env: apiKeyEnv }),
  hanaStop: (removeData = false) => request<HanaRuntime & { removed?: string[] }>("POST", "/api/hana/stop", { remove_data: removeData }),
  hanaEdit: (session: string, index: number, text: string, env: HanaEnv) =>
    request<{ session_id: string; turn_id: string }>("POST", `/api/hana/sessions/${encodeURIComponent(session)}/edit`, { index, text, env }),
  hanaSend: (session: string | null, text: string, env: HanaEnv) =>
    request<{ session_id: string; turn_id: string }>("POST", "/api/hana/messages", { session, text, env }),
  hanaSession: (id: string) => request<HanaSessionDetail>("GET", `/api/hana/sessions/${encodeURIComponent(id)}`),
  hanaNote: (id: string, text: string) => request<{ ok: boolean }>("POST", `/api/hana/sessions/${encodeURIComponent(id)}/note`, { text }),
  hanaDeleteSession: (id: string) => request<{ deleted: string }>("DELETE", `/api/hana/sessions/${encodeURIComponent(id)}`),
  hanaTurn: (id: string, since: number) =>
    request<HanaTurn>("GET", `/api/hana/turns/${encodeURIComponent(id)}`, undefined, { query: { since } }),
  hanaAnswer: (turn: string, pendingId: string, decision: "approve" | "reject" | "answer", text = "") =>
    request<{ ok: boolean }>("POST", `/api/hana/turns/${encodeURIComponent(turn)}/answer`, { pending_id: pendingId, decision, text }),
  hanaStopTurn: (turn: string) => request<{ ok: boolean }>("POST", `/api/hana/turns/${encodeURIComponent(turn)}/stop`, {}),
};

export function errorMessage(exc: unknown): string {
  if (exc instanceof ApiError) return exc.message;
  if (exc instanceof Error) return exc.message;
  return String(exc);
}
