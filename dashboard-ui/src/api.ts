import type {
  DashboardData,
  Deployment,
  ExecutionDetail,
  ExecutionList,
  HealthResponse,
  LogDeleteRequest,
  LogDeleteResult,
  LogsResponse,
  LogStreamsResponse,
} from "./types";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

/** The data embedded by the generator. Empty when opened from the Vite dev server. */
export function embeddedData(): DashboardData {
  const el = document.getElementById("data");
  const text = (el && el.textContent) || "";
  if (!text.trim() || text.trim().startsWith("{{")) return { deployments: [] };
  try {
    const parsed = JSON.parse(text) as DashboardData;
    return { ...parsed, deployments: Array.isArray(parsed.deployments) ? parsed.deployments : [] };
  } catch {
    return { deployments: [] };
  }
}

export function deploymentKey(d: Deployment): string {
  return d.key || `${d.provider}-${d.stage}`;
}

function query(params: Record<string, string | number | null | undefined>): string {
  const parts: string[] = [];
  for (const [k, v] of Object.entries(params)) {
    if (v === null || v === undefined || v === "") continue;
    parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  }
  return parts.length ? `?${parts.join("&")}` : "";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(path, {
      ...init,
      headers: { accept: "application/json", ...(init && init.body ? { "content-type": "application/json" } : {}) },
      credentials: "same-origin",
    });
  } catch (err) {
    throw new ApiError(err instanceof Error ? err.message : "network error", 0);
  }
  const text = await resp.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = null;
    }
  }
  if (!resp.ok) {
    const msg =
      body && typeof body === "object" && "error" in body ? String((body as { error: unknown }).error) : resp.statusText;
    throw new ApiError(msg || `HTTP ${resp.status}`, resp.status);
  }
  if (body === null || typeof body !== "object") throw new ApiError("unexpected response", resp.status);
  return body as T;
}

const base = (key: string) => `/api/deployments/${encodeURIComponent(key)}`;

export const api = {
  /** Resolves only when the page is served by `pskit dashboard --serve`. */
  async probe(): Promise<DashboardData | null> {
    if (!/^https?:$/.test(window.location.protocol)) return null;
    try {
      const data = await request<DashboardData>("/api/deployments");
      return Array.isArray(data.deployments) ? data : null;
    } catch {
      return null;
    }
  },
  deployments: () => request<DashboardData>("/api/deployments"),
  health: (key: string) => request<HealthResponse>(`${base(key)}/health`),
  logs: (
    key: string,
    p: { since?: number; limit?: number; level?: string; function?: string; q?: string; source?: string },
  ) => request<LogsResponse>(`${base(key)}/logs${query(p)}`),
  logStreams: (key: string, fn?: string) =>
    request<LogStreamsResponse>(`${base(key)}/logs/streams${query({ function: fn })}`),
  deleteLogs: (key: string, body: LogDeleteRequest) =>
    request<LogDeleteResult>(`${base(key)}/logs/delete`, { method: "POST", body: JSON.stringify(body) }),
  executions: (
    key: string,
    p: { workflow?: string; status?: string; limit?: number; offset?: number; token?: string | null },
  ) => request<ExecutionList>(`${base(key)}/executions${query(p)}`),
  execution: (key: string, id: string, workflow?: string) =>
    request<ExecutionDetail>(`${base(key)}/executions/${encodeURIComponent(id)}${query({ workflow })}`),
  start: (key: string, workflow: string, input: unknown) =>
    request<ExecutionDetail>(`${base(key)}/workflows/${encodeURIComponent(workflow)}/start`, {
      method: "POST",
      body: JSON.stringify(input === undefined ? null : input),
    }),
  cancel: (key: string, id: string, workflow?: string) =>
    request<ExecutionDetail>(`${base(key)}/executions/${encodeURIComponent(id)}/cancel${query({ workflow })}`, {
      method: "POST",
      body: "{}",
    }),
};
