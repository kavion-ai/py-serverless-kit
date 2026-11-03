import { useMemo, useRef, useState, type ReactNode } from "react";
import { CopyButton } from "../../components/CopyButton";
import {
  afterStatus,
  applyStatus,
  DeployLogParser,
  doneStatus,
  hostStatus,
  stageStatus,
  type DeployLog,
  type FirewallServer,
  type HostStep,
  type StepStatus,
} from "../deployLog";
import type { JobView } from "../jobs";
import { groupOfResource, hostResource, targetLabel, type Placement } from "../placement";
import type { OnPremDeployed } from "../types";

/** Parse a job's lines incrementally: only lines newer than the last parsed `seq` are read on each poll. */
export function useDeployLog(job: JobView): DeployLog {
  const ref = useRef<{ id: string | null; parser: DeployLogParser }>({ id: null, parser: new DeployLogParser() });
  return useMemo(() => {
    if (ref.current.id !== job.id) ref.current = { id: job.id, parser: new DeployLogParser() };
    ref.current.parser.push(job.lines);
    return ref.current.parser.snapshot();
  }, [job.id, job.lines]);
}

const STATUS_LABEL: Record<StepStatus, string> = { waiting: "waiting", running: "running", done: "done", failed: "failed", cancelled: "cancelled" };
const MAX_SHOWN = 400;

function StepIcon({ status }: { status: StepStatus }) {
  if (status === "running") return <span className="spinner spinner-sm dstep-spin" role="img" aria-label="running" />;
  const glyph = { waiting: "", done: "✓", failed: "✕", cancelled: "–" }[status];
  return (
    <span className={`dstep-icon dsi-${status}`} role="img" aria-label={STATUS_LABEL[status]}>
      {glyph}
    </span>
  );
}

function LogLines({ lines, empty = "No output yet." }: { lines: string[]; empty?: string }) {
  if (!lines.length) return <p className="muted small">{empty}</p>;
  const shown = lines.length > MAX_SHOWN ? lines.slice(-MAX_SHOWN) : lines;
  return (
    <>
      {lines.length > MAX_SHOWN && (
        <p className="muted small">
          Last {MAX_SHOWN} of {lines.length} lines; the Raw log tab has all of them.
        </p>
      )}
      <pre className="dstep-log" tabIndex={0} aria-label="Output">
        {shown.join("\n")}
      </pre>
    </>
  );
}

function ErrorBox({ title, error = [], tail = [], block = [], extra = [] }: { title: string; error?: string[]; tail?: string[]; block?: string[]; extra?: string[][] }) {
  const blocks = [block, ...extra].filter((b) => b.length);
  if (!error.length && !tail.length && !blocks.length) return null;
  return (
    <div className="dstep-error" role="alert">
      <b>{title}</b>
      {error.map((e, i) => (
        <div key={i} className="mono small">
          {e}
        </div>
      ))}
      {tail.length > 0 && (
        <>
          <span className="small muted">End of the host&apos;s log:</span>
          <pre className="dstep-tail">{tail.join("\n")}</pre>
        </>
      )}
      {blocks.map((b, i) => (
        <pre key={i}>{trimBlank(b).join("\n")}</pre>
      ))}
    </div>
  );
}

function trimBlank(lines: string[]): string[] {
  let a = 0;
  let b = lines.length;
  while (a < b && !lines[a].trim()) a++;
  while (b > a && !lines[b - 1].trim()) b--;
  return lines.slice(a, b);
}

function StepRow({
  id,
  title,
  meta,
  status,
  open,
  onToggle,
  children,
}: {
  id: string;
  title: ReactNode;
  meta?: ReactNode;
  status: StepStatus;
  open: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  const bodyId = `dstep-${id.replace(/[^\w-]/g, "-")}`;
  return (
    <li className={`dstep dstep-${status}`}>
      <button type="button" className="dstep-head" aria-expanded={open} aria-controls={bodyId} onClick={onToggle}>
        <StepIcon status={status} />
        <span className="dstep-title">{title}</span>
        {meta ? <span className="dstep-meta small">{meta}</span> : null}
        <span className="grow" />
        <span className="dstep-state small">{STATUS_LABEL[status]}</span>
        <span className="caret" aria-hidden="true">
          {open ? "▾" : "▸"}
        </span>
      </button>
      {open && (
        <div className="dstep-body" id={bodyId}>
          {children}
        </div>
      )}
    </li>
  );
}

function FirewallServers({ servers }: { servers: FirewallServer[] }) {
  return (
    <div className="dfw">
      <p className="muted small">
        <span className="fw-level fw-required">REQUIRED</span> it does not work without; <span className="fw-level fw-feature">NEEDED</span> for that
        feature; <span className="fw-level fw-optional">optional</span> pskit falls back to an SSH tunnel.
      </p>
      {servers.map((s) => {
        const rules = s.sections.flatMap((sec) => sec.rules);
        const required = rules.filter((r) => r.level === "required").length;
        const ufw = Array.from(new Set(s.sections.flatMap((sec) => sec.ufw)));
        return (
          <details key={s.server} className="dfw-server">
            <summary>
              <span className="mono">{s.server}</span>
              <span className="muted small">
                {rules.length} rule{rules.length === 1 ? "" : "s"}
              </span>
              {required > 0 && <span className="fw-level fw-required">{required} REQUIRED</span>}
            </summary>
            <div className="dfw-body">
              {s.sections.map((sec, i) => (
                <div key={i} className="stack-xs">
                  <span className="small muted">For {sec.title}</span>
                  <div className="table-wrap">
                    <table className="table fw-table">
                      <thead>
                        <tr>
                          <th>Level</th>
                          <th>Direction</th>
                          <th>Port</th>
                          <th>From / to</th>
                          <th>Why</th>
                        </tr>
                      </thead>
                      <tbody>
                        {sec.rules.map((r, j) => (
                          <tr key={j} className={`fw-row fw-row-${r.level}`}>
                            <td>
                              <span className={`fw-level fw-${r.level}`}>{r.level === "required" ? "REQUIRED" : r.level === "feature" ? "NEEDED" : "optional"}</span>
                            </td>
                            {r.direction ? (
                              <>
                                <td className="fw-dir">{r.direction === "inbound" ? "↓ inbound" : "↑ outbound"}</td>
                                <td className="mono fw-port">{r.port}</td>
                                <td className="small">{r.peer}</td>
                                <td className="small">{r.why}</td>
                              </>
                            ) : (
                              <td colSpan={4} className="mono small">
                                {r.text}
                              </td>
                            )}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ))}
              {ufw.length > 0 && (
                <div className="fw-ufw">
                  <div className="fw-ufw-head">
                    <span className="muted small">
                      With <code className="mono">ufw</code> on {s.server}:
                    </span>
                    <CopyButton value={ufw.join("\n")} label="copy" />
                  </div>
                  <pre className="fw-ufw-code mono">{ufw.join("\n")}</pre>
                </div>
              )}
            </div>
          </details>
        );
      })}
    </div>
  );
}

interface HostInfo {
  key: string;
  group: string;
  where: string;
  endpoint: string;
}

/** One card per host: the placement's groups (resources host / host_<group>), plus any other host the log names. */
function hostInfos(log: DeployLog, placement: Placement | null, deployed: OnPremDeployed | null): HostInfo[] {
  const keys = placement ? placement.groups.map((g) => hostResource(g.name, placement.default)) : ["host"];
  for (const h of log.hosts) if (!keys.includes(h.key)) keys.push(h.key);
  return keys.map((key) => {
    const group = groupOfResource(key, placement);
    const body = placement?.groups.find((g) => g.name === group)?.body || {};
    const isDefault = key === "host";
    const recorded = deployed?.groups?.[group];
    const where =
      (recorded?.cluster ? `cluster ${recorded.cluster}` : recorded?.server || "") ||
      targetLabel(body) ||
      (isDefault ? deployed?.label || "the deploy target" : "");
    const port = typeof body.port === "number" ? `:${body.port}` : "";
    const endpoint = recorded?.endpoint || (isDefault ? deployed?.endpoint || "" : "");
    return { key, group: placement || !isDefault ? group : "host", where: where && !endpoint ? `${where}${port}` : where, endpoint };
  });
}

const ACTION_LABEL = { create: "creating", modify: "updating", destroy: "removing", "": "" };

/**
 * Structured view of an on-prem deploy / remove job: check & build, terraform plan, one card per host,
 * load balancer, firewall and the endpoints. Failed steps open by themselves.
 */
export function DeploySteps({
  job,
  command,
  placement,
  deployed,
  onCancel,
}: {
  job: JobView;
  command: string;
  placement: Placement | null;
  deployed: OnPremDeployed | null;
  onCancel?: () => void;
}) {
  const log = useDeployLog(job);
  const state = job.status;
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const isOpen = (id: string, status: StepStatus) => open[id] ?? status === "failed";
  const toggle = (id: string, status: StepStatus) => setOpen((o) => ({ ...o, [id]: !isOpen(id, status) }));
  const removing = command === "remove";

  const hosts = hostInfos(log, placement, deployed);
  const byKey = new Map<string, HostStep>(log.hosts.map((h) => [h.key, h]));
  const anyHostFailed = hosts.some((h) => hostStatus(byKey.get(h.key), log, state) === "failed");
  const ended = state !== "running" && state !== "idle";
  const failedJob = state === "failed" || state === "cancelled";
  // Errors no host claims belong to the step the job stopped in.
  const loose = log.errors;
  const stoppedAt = failedJob ? log.stage : -1;

  const steps: { id: string; title: ReactNode; meta?: ReactNode; status: StepStatus; body: ReactNode }[] = [];
  const build = stageStatus(log, 0, state);
  steps.push({
    id: "build",
    title: "Check & build",
    meta: removing ? "the Terraform configuration" : "validate, package the code, write main.tf.json",
    status: build,
    body: (
      <>
        {stoppedAt === 0 && <ErrorBox title="Stopped here" extra={loose} />}
        <LogLines lines={log.build} empty={removing ? "Nothing to build (the configuration exists)." : "No output yet."} />
      </>
    ),
  });
  const plan = stageStatus(log, 1, state);
  steps.push({
    id: "plan",
    title: "Terraform plan",
    meta: log.planSummary || "terraform init, then what changes",
    status: plan,
    body: (
      <>
        {stoppedAt === 1 && <ErrorBox title="Stopped here" extra={loose} />}
        <LogLines lines={log.plan} />
      </>
    ),
  });
  for (const info of hosts) {
    const h = byKey.get(info.key);
    const status = hostStatus(h, log, state);
    const detail = h?.detail || (h?.action && status === "running" ? ACTION_LABEL[h.action] : "") || (status === "done" && !h ? "no changes" : "");
    steps.push({
      id: `host:${info.key}`,
      title: (
        <>
          <span className="mono">{info.group}</span>
          {info.group === placement?.default && <span className="badge badge-accent">default</span>}
        </>
      ),
      meta: (
        <>
          {info.where && <span>{info.where}</span>}
          {info.endpoint && <span className="mono"> · {info.endpoint}</span>}
          {detail && <span className="muted"> · {detail}</span>}
        </>
      ),
      status,
      body: (
        <>
          {status === "failed" && (
            <ErrorBox
              title={`${removing ? "Removing" : "Deploying"} ${info.group} failed`}
              error={h?.error}
              tail={h?.tail}
              block={h?.errorBlock}
              extra={stoppedAt === 2 && !h?.errorBlock.length ? loose : []}
            />
          )}
          <LogLines lines={h?.lines || []} empty={status === "done" ? "Terraform had nothing to change here." : "No output yet."} />
          <p className="muted small">
            Terraform resource <code className="mono">terraform_data.{info.key}</code>
          </p>
        </>
      ),
    });
  }
  if (log.apply.length || (stoppedAt === 2 && !anyHostFailed)) {
    const status = applyStatus(log, state);
    steps.push({
      id: "apply",
      title: removing ? "Terraform destroy" : "Terraform apply",
      meta: log.applySummary || "other resources and outputs",
      status: status === "failed" && anyHostFailed ? "done" : status,
      body: (
        <>
          {stoppedAt === 2 && !anyHostFailed && <ErrorBox title="Stopped here" extra={loose} />}
          <LogLines lines={log.apply} />
        </>
      ),
    });
  }
  if (log.balancer.length) {
    steps.push({
      id: "balancer",
      title: "Load balancer",
      meta: log.balancerWarnings ? (
        <span className="warn-text">
          {log.balancerWarnings} warning{log.balancerWarnings === 1 ? "" : "s"}
        </span>
      ) : (
        "routes to this deployment"
      ),
      status: afterStatus(log, "balancer", state),
      body: <LogLines lines={log.balancer} />,
    });
  }
  if (log.firewall.length) {
    const required = log.firewall.reduce((n, s) => n + s.sections.reduce((m, sec) => m + sec.rules.filter((r) => r.level === "required").length, 0), 0);
    steps.push({
      id: "firewall",
      title: "Firewall",
      meta: `${log.firewall.length} server${log.firewall.length === 1 ? "" : "s"}${required ? ` · ${required} required rule${required === 1 ? "" : "s"}` : ""}`,
      status: afterStatus(log, "firewall", state),
      body: <FirewallServers servers={log.firewall} />,
    });
  }
  // After the apply: a failure belongs to the load balancer / firewall step when there is one, else to "Done".
  const last = steps[steps.length - 1];
  const late = last.id === "balancer" || last.id === "firewall";
  if (stoppedAt === 3 && late && loose.length) {
    last.status = "failed";
    const body = last.body;
    last.body = (
      <>
        <ErrorBox title="Stopped here" extra={loose} />
        {body}
      </>
    );
  }
  const doneHasError = stoppedAt === 4 || (stoppedAt === 3 && !late && loose.length > 0);
  const done = doneHasError && state === "failed" ? "failed" : doneStatus(log, state);
  steps.push({
    id: "done",
    title: "Done",
    meta: removing ? "removed" : log.endpoints[0] || "the endpoints",
    status: done,
    body: (
      <>
        {doneHasError && <ErrorBox title="Stopped here" extra={loose} />}
        {log.endpoints.length > 0 && (
          <ul className="dsteps-endpoints">
            {log.endpoints.map((u) => (
              <li key={u}>
                {/\{|\}/.test(u) ? (
                  <code className="mono small">{u}</code>
                ) : (
                  <a className="mono small" href={u} target="_blank" rel="noreferrer">
                    {u}
                  </a>
                )}
              </li>
            ))}
          </ul>
        )}
        <LogLines lines={log.done} empty={ended ? "The job ended before this step." : "Not there yet."} />
      </>
    ),
  });

  const statusText =
    state === "idle" ? "" : state === "running" ? "running…" : `${state}${job.exitCode !== null && job.exitCode !== undefined ? ` (exit ${job.exitCode})` : ""}`;
  const summary = steps.filter((s) => s.status === "done").length;
  return (
    <div className="console-wrap dsteps-wrap">
      <div className="console-bar">
        <span className={`console-status cs-${state}`} aria-live="polite">
          {state === "running" && <span className="spinner spinner-sm" aria-hidden="true" />}
          {job.command ? <code className="mono">pskit {job.command}</code> : null} {statusText}
        </span>
        <span className="grow" />
        <span className="muted small">
          {summary}/{steps.length} steps done
        </span>
        {onCancel && state === "running" && (
          <button type="button" className="btn btn-sm btn-danger" onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>
      {job.error && <div className="hint-box warn">{job.error}</div>}
      <ol className="dsteps" aria-label={`${command || "deploy"} steps`}>
        {steps.map((s) => (
          <StepRow key={s.id} id={s.id} title={s.title} meta={s.meta} status={s.status} open={isOpen(s.id, s.status)} onToggle={() => toggle(s.id, s.status)}>
            {s.body}
          </StepRow>
        ))}
      </ol>
    </div>
  );
}
