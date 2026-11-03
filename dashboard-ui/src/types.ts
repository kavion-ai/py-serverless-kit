// Shapes written by core/describe.py (deployment.json) and returned by dashboard/server.py.

export interface EventSummary {
  type: string;
  summary: string;
  [key: string]: unknown;
}

export interface FunctionRecord {
  name: string;
  resource_name?: string;
  handler: string;
  description?: string;
  kind: string;
  generated?: boolean;
  runtime: string;
  memory: number;
  timeout: number;
  architecture: string;
  events: EventSummary[];
  environment_keys?: string[];
  id?: string | null;
  arn?: string | null;
  url?: string | null;
  urls?: { method: string; url: string }[];
  console?: string | null;
}

export interface WorkflowRecord {
  name: string;
  description?: string;
  engine: string;
  start_at?: string;
  states?: Record<string, string>;
  functions?: string[];
  id?: string | null;
  url?: string | null;
  console?: string | null;
}

export interface ResourceRecord {
  name: string;
  type: string;
  external?: boolean;
  native_name?: string | null;
  functions?: string[];
  connection_keys?: string[];
  [key: string]: unknown;
}

export interface Deployment {
  key?: string;
  schema?: number;
  status?: string;
  service: string;
  stage: string;
  provider: string;
  provider_display?: string;
  provider_tier?: string;
  region?: string | null;
  endpoint?: string | null;
  deployed_at?: string;
  pskit_version?: string;
  config_file?: string;
  artifact?: { sha256?: string; size?: number; [key: string]: unknown };
  functions?: FunctionRecord[];
  workflows?: WorkflowRecord[];
  resources?: ResourceRecord[];
  outputs?: Record<string, unknown>;
}

export interface DashboardData {
  generated_at?: string;
  deployments: Deployment[];
}

export interface LogEntry {
  seq: number;
  ts: string;
  level: string;
  source: string;
  function?: string | null;
  request_id?: string | null;
  message: string;
  fields?: Record<string, unknown>;
}

export interface LogsResponse {
  supported: boolean;
  reason?: string;
  entries: LogEntry[];
  next: number;
  oldest?: number;
  /** "seq": on-prem host sequence numbers; "time": cloud logs, `since`/`next` are millisecond timestamps. */
  mode?: "seq" | "time";
  can_delete?: boolean;
  /** Provider console link, shown when logs can't be read here. */
  console?: string | null;
}

/** One log stream: a CloudWatch stream, or one function's entries on an on-prem host. */
export interface LogStream {
  id: string;
  function?: string | null;
  name?: string | null;
  group?: string;
  first?: string | null;
  last?: string | null;
  bytes?: number | null;
  count?: number | null;
}

export interface LogStreamsResponse {
  supported: boolean;
  reason?: string;
  can_delete?: boolean;
  mode?: "seq" | "time";
  console?: string | null;
  items: LogStream[];
}

export interface LogDeleteRequest {
  ids?: string[];
  function?: string;
  all?: boolean;
}

export interface LogDeleteResult {
  deleted: number;
  errors?: string[];
}

export type ExecutionStatus = "RUNNING" | "SUCCEEDED" | "FAILED" | "ABORTED" | "CANCELLED" | "TIMED_OUT" | string;

export interface ExecutionSummary {
  execution_id: string;
  workflow: string;
  status: ExecutionStatus;
  started_at?: string | null;
  stopped_at?: string | null;
  duration_ms?: number | null;
  current_state?: string | null;
  source?: string;
  console?: string | null;
}

export interface HistoryEvent {
  ts?: string;
  state?: string;
  type?: string;
  event?: string;
  [key: string]: unknown;
}

export interface ExecutionDetail extends ExecutionSummary {
  input?: unknown;
  output?: unknown;
  error?: string | null;
  cause?: string | null;
  history?: HistoryEvent[];
}

export interface ExecutionList {
  items: ExecutionSummary[];
  total?: number | null;
  next_token?: string | null;
  supported: boolean;
  reason?: string;
}

export interface FunctionStats {
  invocations?: number;
  errors?: number;
  avg_duration_ms?: number | null;
  last_duration_ms?: number | null;
  last_at?: string | null;
  last_error?: string | null;
}

export interface HealthResponse {
  live: boolean;
  reason?: string;
  health?: Record<string, unknown>;
  stats?: {
    started_at?: string;
    uptime_s?: number;
    functions?: Record<string, FunctionStats>;
    queues?: Record<string, number>;
  };
}
