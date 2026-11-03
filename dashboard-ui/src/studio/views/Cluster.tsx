import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Drawer } from "../../components/Drawer";
import { api, errorMessage } from "../api";
import { AlgorithmPicker, KindBadge, WeightsEditor, algorithmLabel, weightsFor, weightsValid } from "../components/AlgorithmPicker";
import { JobConsole } from "../components/Console";
import { useConfirm, useToast } from "../components/Feedback";
import { FormRow, NumberInput, Segmented, TextInput, Toggle } from "../components/Forms";
import { PageHeader } from "../components/Misc";
import { ServerForm } from "../components/OnPremMachines";
import { FirewallPanel } from "../components/FirewallPanel";
import { useJob } from "../jobs";
import { href, navigate } from "../route";
import { useStudio } from "../store";
import type {
  BalancerAction,
  ClusterAction,
  ClusterBalance,
  ClusterBalancerStatus,
  ClusterNodeStatus,
  ClusterRequest,
  ClusterStatus,
  JsonObject,
  OnPremBalancersState,
  OnPremCluster,
  OnPremClustersState,
  OnPremServer,
  Orchestrator,
} from "../types";
import { asObject } from "../util";
import { DeployedLogs } from "./Logs";

const NAME_RE = /^[a-z][a-z0-9-]{0,30}$/;
const REFRESH_MS = 30000;

/** Scaling clusters: a master server plus joined servers running the functions (Swarm, Kubernetes, Nomad). */
export function ClusterView({ rest }: { rest: string[] }) {
  const [state, setState] = useState<OnPremClustersState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const { providerName } = useStudio();

  const load = useCallback(() => {
    api
      .clusters()
      .then((s) => {
        setState(s);
        setError(null);
      })
      .catch((exc: unknown) => setError(errorMessage(exc)));
  }, []);
  useEffect(load, [load]);

  const selected = state?.clusters.find((c) => c.name === rest[0]) || state?.clusters[0] || null;

  return (
    <div className="page">
      <PageHeader
        title="Scaling cluster"
        subtitle={
          <>
            Run this project&apos;s functions on several servers with <b>Docker Swarm</b>, <b>Kubernetes (k3s)</b> or <b>HashiCorp Nomad</b>: pick a master
            server, join more servers whenever you need (also while functions run), watch every server&apos;s CPU, memory and disk, and get an alert
            (one of your functions, e.g. a mail to DevOps, and / or a webhook) when every server is full. Without a cluster the functions run on one
            server as before. Resources (Redis, Postgres, ...) can run on one server of the cluster too: <i>Where → Scaling cluster</i> when you create
            them.
          </>
        }
        actions={
          <button type="button" className="btn btn-primary" onClick={() => setCreating(true)}>
            + New cluster
          </button>
        }
      />
      {providerName !== "onprem" && (
        <div className="hint-box warn">
          Clusters run on-prem functions. The project&apos;s provider is <b>{providerName || "not set"}</b>: switch it to <b>onprem</b> in{" "}
          <a href={href("overview")}>Overview</a> to deploy to a cluster.
        </div>
      )}
      {error && <div className="form-error">{error}</div>}
      {state && !state.clusters.length && (
        <div className="card card-pad">
          <h3>No cluster yet</h3>
          <ol className="small cluster-steps">
            <li>
              Save your servers once (<a href={href("resources")}>Resources → On-prem services → Servers</a>, or <b>Add a server</b> below).
            </li>
            <li>
              <b>+ New cluster</b>: choose the orchestrator and the master server. pskit installs it over SSH.
            </li>
            <li>
              <b>Use for this project</b>, set the replicas, then deploy. Join more servers any time.
            </li>
          </ol>
          <button type="button" className="btn btn-primary" onClick={() => setCreating(true)}>
            + New cluster
          </button>
        </div>
      )}
      {state && state.clusters.length > 1 && (
        <div className="row-gap wrap cluster-tabs">
          {state.clusters.map((c) => (
            <a key={c.name} href={href("cluster", c.name)} className={c.name === selected?.name ? "btn btn-sm btn-primary" : "btn btn-sm"}>
              {c.name} · {c.orchestrator_label}
            </a>
          ))}
        </div>
      )}
      {state && selected && <ClusterPanel key={selected.name} cluster={selected} state={state} reload={load} />}
      {creating && state && (
        <CreateClusterDrawer
          state={state}
          onClose={() => setCreating(false)}
          onCreated={(name) => {
            setCreating(false);
            load();
            navigate("cluster", name);
          }}
          onServersChanged={load}
        />
      )}
    </div>
  );
}

function ClusterPanel({ cluster, state, reload }: { cluster: OnPremCluster; state: OnPremClustersState; reload: () => void }) {
  const [status, setStatus] = useState<ClusterStatus | null>(state.last[cluster.name] || null);
  const [loading, setLoading] = useState(false);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [joining, setJoining] = useState(false);
  const [balancing, setBalancing] = useState(false);
  const [lbState, setLbState] = useState<OnPremBalancersState | null>(null);
  const job = useJob(jobId);
  const confirm = useConfirm();
  const toast = useToast();
  // The firewall card: the cluster's nodes plus the server(s) of its load balancers.
  const firewallServers = useMemo(() => {
    const out = new Set<string>();
    for (const n of cluster.nodes) {
      out.add(n.server);
      if (n.address) out.add(n.address);
    }
    if (cluster.balancer?.server) out.add(cluster.balancer.server);
    for (const b of cluster.balancers || []) if (b.server) out.add(b.server);
    return [...out];
  }, [cluster]);

  const refresh = useCallback(
    (check = false) => {
      setLoading(true);
      (check ? api.clusterCheck(cluster.name) : api.clusterStatus(cluster.name))
        .then((s) => {
          setStatus(s);
          setStatusError(null);
          if (check && s.alert) {
            const a = s.alert;
            if ("skipped" in a) toast(`Alert skipped: cooldown (next in ${a.next_after_minutes} min)`, "info");
            else if (a.errors.length) toast(`Alert: ${a.errors.join("; ")}`, "err");
            else toast(`Alert sent to ${a.sent.join(", ")}`, "ok");
            reload();
          }
        })
        .catch((exc: unknown) => setStatusError(errorMessage(exc)))
        .finally(() => setLoading(false));
    },
    [cluster.name, reload, toast],
  );

  useEffect(() => {
    refresh();
    const timer = window.setInterval(() => {
      if (!document.hidden) refresh();
    }, REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [refresh]);

  // Named load balancers and the algorithm catalog (labels, pros and cons for the load balancer form).
  const loadBalancers = useCallback(() => {
    api
      .balancers()
      .then(setLbState)
      .catch(() => setLbState(null));
  }, []);
  useEffect(loadBalancers, [loadBalancers]);

  useEffect(() => {
    if (job.status === "succeeded" || job.status === "failed") {
      reload();
      refresh();
      loadBalancers();
    }
  }, [job.status, reload, refresh, loadBalancers]);

  const startJob = async (action: ClusterAction, body: JsonObject = {}) => {
    try {
      const { job_id } = await api.clusterAction(cluster.name, action, body);
      setJobId(job_id);
    } catch (exc) {
      toast(errorMessage(exc), "err");
    }
  };

  const startBalancerJob = async (name: string, action: BalancerAction, body: JsonObject) => {
    try {
      const { job_id } = await api.balancerAction(name, action, body);
      setJobId(job_id);
    } catch (exc) {
      toast(errorMessage(exc), "err");
    }
  };

  const detachNamed = async (name: string) => {
    const ok = await confirm({
      title: `Detach ${cluster.name} from load balancer ${name}?`,
      body: `The routes of ${cluster.name}'s deployments are removed from ${name}. The deployments keep running on the cluster.`,
      confirmLabel: "Detach",
      danger: true,
    });
    if (ok === "confirm") void startBalancerJob(name, "detach", { cluster: cluster.name });
  };

  const leave = async (server: string) => {
    const ok = await confirm({
      title: `Remove ${server} from ${cluster.name}?`,
      body: "Its replicas move to the other servers first, then its agent stops. The saved server is kept.",
      confirmLabel: "Remove server",
      danger: true,
    });
    if (ok === "confirm") void startJob("leave", { server });
  };

  const forget = async () => {
    const ok = await confirm({
      title: `Forget cluster ${cluster.name}?`,
      body: "pskit stops managing it. The servers and anything running on them are left as they are (remove the deployments first with Deploy → Remove). To uninstall it from the servers instead, use Remove on the master's row.",
      confirmLabel: "Forget",
      danger: true,
    });
    if (ok === "confirm") void startJob("remove");
  };

  const uninstall = async () => {
    const ok = await confirm({
      title: `Uninstall cluster ${cluster.name}?`,
      body: (
        <>
          The master <b className="mono">{cluster.master}</b> cannot leave on its own, so this removes the whole cluster: its deployments stop, its load
          balancer is removed, {cluster.orchestrator_label} is uninstalled from the master and every joined server, then pskit forgets the cluster.
          Docker and the saved servers stay. The main replicas' data stays on the master unless you also delete it.
        </>
      ),
      confirmLabel: "Uninstall",
      danger: true,
      typed: cluster.name,
      extra: [{ label: "Uninstall and delete data", value: "delete-data", danger: true }],
    });
    if (ok === "confirm" || ok === "delete-data") void startJob("remove", { uninstall: true, delete_data: ok === "delete-data" });
  };

  const removeBalancer = async () => {
    const ok = await confirm({
      title: `Remove the load balancer of ${cluster.name}?`,
      body: `nginx stops on ${cluster.balancer?.server}, so its URL stops answering. The functions keep running on the cluster and users reach the servers on their own ports again.`,
      confirmLabel: "Remove load balancer",
      danger: true,
    });
    if (ok === "confirm") void startJob("balancer-remove");
  };

  const nodes: ClusterNodeStatus[] =
    status?.nodes ||
    cluster.nodes.map((n) => ({ ...n, reachable: false, ready: false, state: "…", availability: "", over: [], full: false }) as ClusterNodeStatus);

  return (
    <>
      <div className="card card-pad">
        <div className="row-between wrap">
          <div>
            <h3>
              {cluster.name} <span className="muted small">· {cluster.orchestrator_label}</span>
            </h3>
            <div className="muted small">
              master <b className="mono">{cluster.master}</b> ({cluster.advertise}) · {cluster.nodes.length} server(s)
              {status && <> · checked {new Date(status.checked_at).toLocaleTimeString()}</>}
            </div>
          </div>
          <span className="row-gap wrap">
            <button type="button" className="btn btn-sm" disabled={loading} onClick={() => refresh()}>
              {loading ? "Checking…" : "Refresh"}
            </button>
            <button type="button" className="btn btn-sm" disabled={loading} onClick={() => refresh(true)} title="Check now and send the alert if every server is full">
              Check &amp; alert
            </button>
            <button type="button" className="btn btn-sm btn-danger" onClick={() => void forget()}>
              Forget
            </button>
          </span>
        </div>
        <div className="cluster-binding">
          <Toggle
            checked={cluster.master_serves}
            onChange={(on) => void startJob("master-serves", { enabled: on })}
            label={
              <>
                Send requests to the master <b className="mono">{cluster.master}</b> too
              </>
            }
          />
          <MasterServesNote orchestrator={cluster.orchestrator} on={cluster.master_serves} joined={cluster.nodes.length > 1} />
        </div>
        <ProjectBinding cluster={cluster} />
      </div>

      {statusError && <div className="form-error">{statusError}</div>}
      {status && <CapacityBanner status={status} onJoin={() => setJoining(true)} />}

      <div className="card card-pad">
        <div className="row-between">
          <div>
            <h3>Servers</h3>
            <p className="muted small">
              A server is <b>full</b> at {cluster.capacity.cpu}% CPU, {cluster.capacity.memory}% memory or {cluster.capacity.disk}% disk (change below). Refreshes
              every 30 s.
            </p>
          </div>
          <button type="button" className="btn btn-primary" onClick={() => setJoining(true)}>
            + Join server
          </button>
        </div>
        <table className="table cluster-nodes">
          <thead>
            <tr>
              <th>Server</th>
              <th>State</th>
              <th>CPU</th>
              <th>Memory</th>
              <th>Disk</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {nodes.map((n) => (
              <tr key={n.server} className={n.full ? "node-full" : undefined}>
                <td>
                  <b className="mono">{n.server}</b> {n.role === "master" && <span className="badge badge-accent">master</span>}
                  <div className="muted small mono">
                    {n.node} · {n.address}
                    {n.cpus ? ` · ${n.cpus} CPU` : ""}
                    {n.memory_mb ? ` · ${Math.round(n.memory_mb / 1024)} GB` : ""}
                    {n.load ? ` · load ${n.load}` : ""}
                  </div>
                </td>
                <td>
                  {!n.reachable ? (
                    <span className="badge badge-err" title={n.error}>
                      offline
                    </span>
                  ) : n.availability && n.availability !== "Active" ? (
                    <span className="badge badge-warn">{n.availability.toLowerCase()}</span>
                  ) : (
                    <span className={`badge ${n.ready ? "badge-ok" : "badge-warn"}`}>{(n.state || "").toLowerCase()}</span>
                  )}
                  {n.full && <span className="badge badge-err">full</span>}
                  {!n.reachable && n.error && <div className="form-error small">{n.error}</div>}
                </td>
                <td>
                  <Meter value={n.cpu} limit={cluster.capacity.cpu} />
                </td>
                <td>
                  <Meter value={n.memory} limit={cluster.capacity.memory} />
                </td>
                <td>
                  <Meter value={n.disk} limit={cluster.capacity.disk} suffix={n.disk_gb ? ` of ${n.disk_gb} GB` : ""} />
                </td>
                <td>
                  {n.role !== "master" ? (
                    <button type="button" className="btn btn-sm btn-danger" onClick={() => void leave(n.server)}>
                      Remove
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="btn btn-sm btn-danger"
                      onClick={() => void uninstall()}
                      title="Uninstall the orchestrator from the master and every joined server, then forget the cluster"
                    >
                      Remove
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {status?.orchestrator_error && <div className="form-error small">Master: {status.orchestrator_error}</div>}
      </div>

      <LoadBalancer
        cluster={cluster}
        status={status?.balancer ?? null}
        lbState={lbState}
        busy={job.status === "running"}
        onSetUp={() => setBalancing(true)}
        onSync={() => void startJob("balancer-sync")}
        onRemove={() => void removeBalancer()}
      />
      <NamedBalancers
        cluster={cluster}
        lbState={lbState}
        busy={job.status === "running"}
        onAttach={(name) => void startBalancerJob(name, "attach", { cluster: cluster.name })}
        onDetach={(name) => void detachNamed(name)}
      />

      <Workloads cluster={cluster} status={status} onScale={(stack, replicas) => void startJob("scale", { stack, replicas })} />
      <LiveRequests cluster={cluster} />
      <ClusterLogs cluster={cluster} />
      <ClusterResources status={status} />
      {jobId && <JobConsole job={job} />}
      <AlertSettings cluster={cluster} onSaved={reload} />
      <FirewallPanel
        title={`Firewall: ${cluster.name}`}
        servers={firewallServers}
        refreshKey={job.status !== "running" && job.status !== "idle" ? jobId : null}
      />
      {joining && (
        <JoinDrawer
          cluster={cluster}
          state={state}
          onClose={() => setJoining(false)}
          onJoin={(server, advertise) => {
            setJoining(false);
            void startJob("join", { server, advertise });
          }}
          onServersChanged={reload}
        />
      )}
      {balancing && (
        <BalancerDrawer
          cluster={cluster}
          state={state}
          lbState={lbState}
          onClose={() => setBalancing(false)}
          onSet={(body) => {
            setBalancing(false);
            void startJob("balancer-set", body);
          }}
          onServersChanged={reload}
        />
      )}
    </>
  );
}

/** The load balancer card: nginx on a server outside the cluster, its health, each deployment's URL, its log. */
function LoadBalancer({
  cluster,
  status,
  lbState,
  busy,
  onSetUp,
  onSync,
  onRemove,
}: {
  cluster: OnPremCluster;
  status: ClusterBalancerStatus | null;
  lbState: OnPremBalancersState | null;
  busy: boolean;
  onSetUp: () => void;
  onSync: () => void;
  onRemove: () => void;
}) {
  const balancer = cluster.balancer;
  const [logs, setLogs] = useState<string | null>(null);
  const [logsBusy, setLogsBusy] = useState(false);
  const toast = useToast();

  const loadLogs = async () => {
    setLogsBusy(true);
    try {
      setLogs((await api.clusterBalancerLogs(cluster.name, 200)).text || "(no requests yet)");
    } catch (exc) {
      toast(errorMessage(exc), "err");
    } finally {
      setLogsBusy(false);
    }
  };

  if (!balancer)
    return (
      <div className="card card-pad">
        <div className="row-between wrap">
          <div>
            <h3>Load balancer</h3>
            <p className="muted small">
              Optional: one URL for the whole cluster. pskit runs nginx in Docker on one more saved server <b>outside</b> the cluster and spreads each
              deployment&apos;s HTTP over the servers
              {!cluster.master_serves
                ? " (the joined servers share the requests; the master is only a backup while they are down — turn on “Send requests to the master too” above to change that)"
                : cluster.orchestrator === "nomad"
                  ? " (the web replicas and the master's main replica share the requests)"
                  : " (each server's port already reaches every replica; the load balancer adds one URL and skips a server that is down)"}
              . Deploy, remove, join and leave keep it up to date. Same as <code className="mono">pskit cluster balancer set {cluster.name} SERVER</code>.
            </p>
          </div>
          <button type="button" className="btn btn-primary" disabled={busy} onClick={onSetUp}>
            + Set up load balancer
          </button>
        </div>
      </div>
    );

  const urls = Object.entries(status?.urls || balancer.urls || {});
  const algorithm = balancer.algorithm || lbState?.default_algorithm || "";
  const info = lbState?.algorithms.find((a) => a.name === algorithm);
  return (
    <div className="card card-pad">
      <div className="row-between wrap">
        <div>
          <h3>Load balancer</h3>
          <div className="muted small">
            <b className="mono">{balancer.server}</b> ({balancer.address}) · nginx on port {balancer.port} ·{" "}
            {algorithm && (
              <>
                {algorithmLabel(lbState?.algorithms, algorithm)} {info && <KindBadge kind={info.kind} />} ·{" "}
              </>
            )}
            {!status ? (
              "…"
            ) : !status.reachable ? (
              <span className="badge badge-err" title={status.error}>
                offline
              </span>
            ) : (
              <span className={`badge ${status.running ? "badge-ok" : "badge-err"}`}>nginx {status.state}</span>
            )}
          </div>
        </div>
        <span className="row-gap wrap">
          <button type="button" className="btn btn-sm" disabled={busy} onClick={onSync} title="Rewrite its config from the servers and deployments now">
            Sync now
          </button>
          <button type="button" className="btn btn-sm" disabled={logsBusy} onClick={() => void loadLogs()}>
            {logsBusy ? "Loading…" : logs === null ? "Show log" : "Refresh log"}
          </button>
          <button type="button" className="btn btn-sm" disabled={busy} onClick={onSetUp}>
            Change
          </button>
          <button type="button" className="btn btn-sm btn-danger" disabled={busy} onClick={onRemove}>
            Remove
          </button>
        </span>
      </div>
      {status && !status.reachable && status.error && <div className="form-error small">{status.error}</div>}
      {status?.reachable && !status.running && (
        <div className="hint-box warn">nginx is not running on {balancer.server}. Sync now starts it again (and shows why when it cannot).</div>
      )}
      {status?.reachable && (
        <div className="row-gap wrap">
          <FormRow label="CPU" inline>
            <Meter value={status.cpu} limit={cluster.capacity.cpu} />
          </FormRow>
          <FormRow label="Memory" inline>
            <Meter value={status.memory} limit={cluster.capacity.memory} />
          </FormRow>
          <FormRow label="Disk" inline>
            <Meter value={status.disk} limit={cluster.capacity.disk} suffix={status.disk_gb ? ` of ${status.disk_gb} GB` : ""} />
          </FormRow>
        </div>
      )}
      {!urls.length ? (
        <p className="muted small">Nothing deployed yet: each deployment gets its URL here when you deploy to the cluster.</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Deployment</th>
              <th>Public URL</th>
            </tr>
          </thead>
          <tbody>
            {urls.map(([stack, url]) => (
              <tr key={stack}>
                <td className="mono">{stack}</td>
                <td className="mono small">
                  <a href={url} target="_blank" rel="noreferrer">
                    {url}
                  </a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="muted small">
        Logs, tests and the admin API keep using the master&apos;s address. A second deployment on this cluster needs its own port here: <i>Port on the load
        balancer</i> above.
      </p>
      {logs !== null && (
        <>
          <p className="muted small">
            One line per request; <code className="mono">upstream=</code> is the server that answered. Same as{" "}
            <code className="mono">pskit cluster balancer logs {cluster.name}</code>.
          </p>
          <pre className="code-block">{logs}</pre>
        </>
      )}
    </div>
  );
}

/** Named load balancers (Load balancers page) attached to this cluster: every deployment gets /<service>/ there. */
function NamedBalancers({
  cluster,
  lbState,
  busy,
  onAttach,
  onDetach,
}: {
  cluster: OnPremCluster;
  lbState: OnPremBalancersState | null;
  busy: boolean;
  onAttach: (name: string) => void;
  onDetach: (name: string) => void;
}) {
  const [attaching, setAttaching] = useState(false);
  const [pick, setPick] = useState("");
  const attached = cluster.balancers || [];
  const members = new Set(cluster.nodes.map((n) => n.server));
  const free = (lbState?.balancers || []).filter((b) => !b.clusters.includes(cluster.name) && !members.has(b.server));
  const chosen = free.some((b) => b.name === pick) ? pick : free[0]?.name || "";
  return (
    <div className="card card-pad">
      <div className="row-between wrap">
        <div>
          <h3>Shared load balancers</h3>
          <p className="muted small">
            Named load balancers that also serve other projects and clusters, each by path. Attached here, every deployment on {cluster.name} gets{" "}
            <code className="mono">http://LB/&lt;service&gt;/</code>. Manage them under <a href={href("balancers")}>Load balancers</a>.
          </p>
        </div>
        <button type="button" className="btn btn-primary" disabled={busy || !lbState} onClick={() => setAttaching(true)}>
          + Attach a load balancer
        </button>
      </div>
      {!attached.length ? (
        <p className="muted small">None attached.</p>
      ) : (
        attached.map((b) => {
          const urls = Object.entries(b.urls || {});
          return (
            <div key={b.name} className="cluster-binding">
              <div className="row-between wrap">
                <span className="lb-chips">
                  <a href={href("balancers", b.name)}>
                    <b className="mono">{b.name}</b>
                  </a>
                  <a className="mono small" href={b.url} target="_blank" rel="noreferrer">
                    {b.url}
                  </a>
                  <span className="muted small">on {b.server} ·</span>
                  <span className="small">{b.algorithm_label}</span>
                  <KindBadge kind={b.kind} />
                </span>
                <button type="button" className="btn btn-sm btn-danger" disabled={busy} onClick={() => onDetach(b.name)}>
                  Detach
                </button>
              </div>
              {!urls.length ? (
                <p className="muted small">Nothing deployed on {cluster.name} yet: each deployment gets its URL here when you deploy.</p>
              ) : (
                <table className="table">
                  <thead>
                    <tr>
                      <th>Deployment</th>
                      <th>URL on {b.name}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {urls.map(([stack, url]) => (
                      <tr key={stack}>
                        <td className="mono">{stack}</td>
                        <td className="mono small">
                          <a href={url} target="_blank" rel="noreferrer">
                            {url}
                          </a>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          );
        })
      )}
      {attaching && lbState && (
        <Drawer
          open
          title={`Attach a load balancer to ${cluster.name}`}
          onClose={() => setAttaching(false)}
          actions={
            <button
              type="button"
              className="btn btn-primary"
              disabled={!chosen}
              onClick={() => {
                setAttaching(false);
                onAttach(chosen);
              }}
            >
              Attach
            </button>
          }
        >
          {!free.length ? (
            <p className="muted small">
              {lbState.balancers.length ? "Every load balancer is attached already, or runs on a server of this cluster." : "No load balancer yet."} Create one
              under <a href={href("balancers")}>Load balancers</a>.
            </p>
          ) : (
            <>
              <p className="muted small">
                Each deployment on {cluster.name} gets <code className="mono">http://LB/&lt;service&gt;/</code>, spread over the cluster&apos;s servers with the
                load balancer&apos;s algorithm. Same as <code className="mono">pskit lb attach NAME --cluster {cluster.name}</code>.
              </p>
              <FormRow label="Load balancer" required>
                <select className="input" value={chosen} onChange={(e) => setPick(e.target.value)}>
                  {free.map((b) => (
                    <option key={b.name} value={b.name}>
                      {b.name} · {b.url} · {b.algorithm_label} ({b.kind})
                    </option>
                  ))}
                </select>
              </FormRow>
            </>
          )}
        </Drawer>
      )}
    </div>
  );
}

function BalancerDrawer({
  cluster,
  state,
  lbState,
  onClose,
  onSet,
  onServersChanged,
}: {
  cluster: OnPremCluster;
  state: OnPremClustersState;
  lbState: OnPremBalancersState | null;
  onClose: () => void;
  onSet: (body: JsonObject) => void;
  onServersChanged: () => void;
}) {
  const current = cluster.balancer;
  const [server, setServer] = useState(current?.server || "");
  const [port, setPort] = useState<number | undefined>(current?.port ?? 80);
  const [address, setAddress] = useState(current?.address || "");
  const [algorithm, setAlgorithm] = useState(current?.algorithm || "");
  const [weights, setWeights] = useState<Record<string, number>>(current?.weights || {});
  const chosen = algorithm || lbState?.default_algorithm || "";
  const nodes = cluster.nodes.map((n) => n.server);
  const w = chosen ? weightsFor(chosen, weights, nodes) : undefined;
  const exclude = inCluster(state);
  for (const b of lbState?.balancers || []) exclude.add(b.server);
  if (current) exclude.delete(current.server);
  const moving = !!current && !!server && server !== current.server;
  return (
    <Drawer
      open
      title={current ? `Load balancer of ${cluster.name}` : `Set up a load balancer for ${cluster.name}`}
      onClose={onClose}
      actions={
        <button
          type="button"
          className="btn btn-primary"
          disabled={!server || !port || !weightsValid(weights)}
          onClick={() =>
            onSet({ server, port: port ?? 80, ...(address ? { address } : {}), ...(chosen ? { algorithm: chosen } : {}), ...(w ? { weights: w } : {}) })
          }
        >
          {current ? "Apply" : "Set up"}
        </button>
      }
    >
      <p className="muted small">
        pskit installs Docker on the server over SSH and runs nginx there (container <code className="mono">pskit-lb</code>). The server must not be part of
        a cluster, and must reach the functions&apos; port on every server of {cluster.name}. Users call its port.
      </p>
      <FormRow label="Server" required help="A saved server outside the cluster. Root or passwordless sudo.">
        <ServerChoice
          state={state}
          value={server}
          onChange={(name) => {
            setServer(name);
            setAddress(current && name === current.server ? current.address : "");
          }}
          exclude={exclude}
          onServersChanged={onServersChanged}
        />
      </FormRow>
      <FormRow label="Port" help="The port users call on the load balancer (80 for http://its-address/).">
        <NumberInput value={port} min={1} max={65535} integer onChange={setPort} />
      </FormRow>
      <FormRow label="Address in the URL (optional)" help="The IP or name users reach it at. Default: its SSH host.">
        <TextInput value={address} onChange={setAddress} placeholder="10.0.0.9" mono />
      </FormRow>
      {lbState?.algorithms.length ? (
        <>
          <FormRow label="How it spreads requests" help={`Over the servers of ${cluster.name}. Change it any time here.`}>
            <AlgorithmPicker algorithms={lbState.algorithms} value={chosen} onChange={setAlgorithm} defaultAlgorithm={lbState.default_algorithm} />
          </FormRow>
          {chosen && <WeightsEditor algorithm={chosen} servers={nodes} value={weights} onChange={setWeights} />}
        </>
      ) : (
        <p className="muted small">The load balancing algorithms did not load: the current one (or the default) is kept.</p>
      )}
      {moving && <div className="hint-box">The load balancer moves to {server}; nginx on {current?.server} is removed once the new one runs.</div>}
    </Drawer>
  );
}

export function Meter({ value, limit, suffix = "" }: { value?: number | null; limit: number; suffix?: string }) {
  if (value === undefined || value === null) return <span className="muted">–</span>;
  const tone = value >= limit ? "meter-err" : value >= limit * 0.8 ? "meter-warn" : "meter-ok";
  return (
    <div className={`meter ${tone}`} title={`${value}% (full at ${limit}%)${suffix}`}>
      <div className="meter-bar">
        <div className="meter-fill" style={{ width: `${Math.min(100, Math.max(0, value))}%` }} />
        <div className="meter-limit" style={{ left: `${limit}%` }} />
      </div>
      <span className="meter-text mono small">
        {Math.round(value)}%{suffix}
      </span>
    </div>
  );
}

function CapacityBanner({ status, onJoin }: { status: ClusterStatus; onJoin: () => void }) {
  if (!status.full)
    return (
      <div className="hint-box">
        ✓ Capacity left on {status.nodes.filter((n) => n.reachable && !n.full).length} of {status.nodes.length} server(s).
      </div>
    );
  return (
    <div className="hint-box warn cluster-full">
      <b>⚠ The cluster is full:</b> {status.reasons.join("; ")}.
      {status.pending.length > 0 && (
        <ul className="small">
          {status.pending.slice(0, 5).map((p) => (
            <li key={p} className="mono">
              {p}
            </li>
          ))}
        </ul>
      )}
      <button type="button" className="btn btn-sm btn-primary" onClick={onJoin}>
        + Join a server now
      </button>
    </div>
  );
}

/** `provider.options.cluster` of the open project: deploy its functions here, with how many replicas. */
function ProjectBinding({ cluster }: { cluster: OnPremCluster }) {
  const { draft, edit } = useStudio();
  const options = asObject(asObject(draft.provider).options);
  const raw = options.cluster;
  const current = typeof raw === "string" ? { name: raw } : asObject(raw);
  const used = current.name === cluster.name;
  const set = (patch: JsonObject | null) => {
    if (patch === null) edit(["provider", "options", "cluster"], undefined);
    else edit(["provider", "options", "cluster"], { ...(used ? current : {}), name: cluster.name, ...patch });
  };
  const num = (key: string, fallback: number) => (typeof current[key] === "number" ? (current[key] as number) : fallback);
  return (
    <div className="cluster-binding">
      <Toggle
        checked={used}
        onChange={(on) => set(on ? { replicas: num("replicas", 2) } : null)}
        label={
          <>
            Deploy this project&apos;s functions to <b>{cluster.name}</b> (<code className="mono">provider.options.cluster</code>)
          </>
        }
      />
      {used && (
        <div className="row-gap wrap">
          <FormRow label="Web replicas" help="Copies behind the load balancer (plus 1 main replica on the master)." inline>
            <NumberInput value={num("replicas", 2)} min={1} max={500} integer onChange={(v) => set({ replicas: v ?? 2 })} />
          </FormRow>
          <FormRow label="CPU per replica" help="Cores each replica reserves." inline>
            <NumberInput value={num("cpu", 0.25)} min={0.05} max={64} step={0.05} onChange={(v) => set({ cpu: v ?? 0.25 })} />
          </FormRow>
          <FormRow label="Memory per replica (MB)" inline>
            <NumberInput value={num("memory", 256)} min={32} max={262144} integer onChange={(v) => set({ memory: v ?? 256 })} />
          </FormRow>
          {cluster.balancer && (
            <FormRow
              label="Port on the load balancer"
              help={`Empty: ${cluster.balancer.port}. Each deployment on this cluster needs its own (options.cluster.balancer_port).`}
              inline
            >
              <NumberInput
                value={typeof current.balancer_port === "number" ? current.balancer_port : undefined}
                min={1}
                max={65535}
                integer
                placeholder={String(cluster.balancer.port)}
                onChange={(v) => set({ balancer_port: v === undefined ? undefined : v } as JsonObject)}
              />
            </FormRow>
          )}
          <span className="muted small">
            Save, then <a href={href("deploy")}>Deploy</a>. Reservations decide how many replicas fit on a server; when none fit, the cluster counts as full.
          </span>
        </div>
      )}
    </div>
  );
}

const LIVE_MAX = 300;

/**
 * Requests as they happen and the server / replica that handled each one. Polls the main replica every 2 s, only
 * while Live is on, the card is on screen and the browser tab is visible.
 */
function LiveRequests({ cluster }: { cluster: OnPremCluster }) {
  const stacks = Object.keys(cluster.deployments).sort();
  const [stack, setStack] = useState(stacks[0] || "");
  const [live, setLive] = useState(true);
  const [items, setItems] = useState<ClusterRequest[]>([]);
  const [shape, setShape] = useState<ClusterBalance | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [onScreen, setOnScreen] = useState(false);
  const [tabVisible, setTabVisible] = useState(() => document.visibilityState === "visible");
  const [filter, setFilter] = useState("");
  const since = useRef(0);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = box.current;
    if (!el || typeof IntersectionObserver === "undefined") {
      setOnScreen(true);
      return undefined;
    }
    const seen = new IntersectionObserver(([entry]) => setOnScreen(entry.isIntersecting));
    seen.observe(el);
    return () => seen.disconnect();
  }, []);
  useEffect(() => {
    const onChange = () => setTabVisible(document.visibilityState === "visible");
    document.addEventListener("visibilitychange", onChange);
    return () => document.removeEventListener("visibilitychange", onChange);
  }, []);
  useEffect(() => {
    since.current = 0;
    setItems([]);
    setShape(null);
  }, [stack]);

  const active = live && onScreen && tabVisible && !!stack;
  useEffect(() => {
    if (!active) return undefined;
    let stopped = false;
    let timer: number | undefined;
    const tick = async () => {
      try {
        const page = await api.clusterRequests(cluster.name, stack, since.current);
        if (stopped) return;
        since.current = page.next || since.current;
        if (page.balance) setShape(page.balance);
        if (page.items.length) setItems((old) => [...old, ...page.items].slice(-LIVE_MAX));
        setError(null);
      } catch (exc) {
        if (!stopped) setError(errorMessage(exc));
      }
      if (!stopped) timer = window.setTimeout(() => void tick(), 2000);
    };
    void tick();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, [active, cluster.name, stack]);

  const shown = filter ? items.filter((r) => r.server === filter) : items;
  const httpCounts: Record<string, number> = {};
  for (const r of items) if (r.method) httpCounts[r.server || "?"] = (httpCounts[r.server || "?"] || 0) + 1;
  const balanceRows = (shape?.servers || []).map((row) => ({ ...row, requests: httpCounts[row.server] || 0 }));
  const httpTotal = balanceRows.reduce((sum, row) => sum + row.requests, 0) || Object.values(httpCounts).reduce((sum, n) => sum + n, 0);
  const top = Math.max(1, ...balanceRows.map((row) => row.requests), ...Object.values(httpCounts));

  return (
    <div className="card card-pad" ref={box}>
      <div className="row-gap wrap">
        <h3>Live requests</h3>
        <span className={`badge ${active ? "badge-ok" : ""}`}>{active ? "● live" : live ? "paused (off screen)" : "stopped"}</span>
        {stacks.length > 1 && (
          <select className="select" value={stack} onChange={(e) => setStack(e.target.value)} aria-label="Deployment">
            {stacks.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        )}
        <Toggle checked={live} onChange={setLive} label="Live" />
        <button type="button" className="btn btn-sm" disabled={!items.length} onClick={() => setItems([])}>
          Clear
        </button>
      </div>
      {!stacks.length ? (
        <p className="muted small">Nothing deployed on this cluster yet: deploy with Run on → Scaling cluster, then requests show here as they happen.</p>
      ) : (
        <>
          <p className="muted small">
            Every request to <span className="mono">{cluster.balancer?.urls?.[stack] || cluster.deployments[stack]?.endpoint}</span> and which server and replica handled it (the main replica
            on the master runs schedules, queue / storage / topic triggers and workflows). The table lists every server, including ones with no traffic yet.
            Updates every 2 s while this card is on screen; the same as <code className="mono">pskit cluster requests {cluster.name} --follow</code>.
          </p>
          {shape && <p className="muted small">{shape.note}</p>}
          {balanceRows.length > 0 && (
            <div className="live-table">
              <table className="table">
                <thead>
                  <tr>
                    <th>Server</th>
                    <th>Answers</th>
                    {shape?.mode === "balancer" && <th>Load balancer</th>}
                    <th>HTTP</th>
                    <th>Share</th>
                    <th>URL</th>
                  </tr>
                </thead>
                <tbody>
                  {balanceRows.map((row) => {
                    const share = httpTotal ? (100 * row.requests) / httpTotal : 0;
                    return (
                      <tr key={row.server}>
                        <td>
                          <button
                            type="button"
                            className={`btn btn-sm${filter === row.server ? " btn-primary" : ""}`}
                            onClick={() => setFilter(filter === row.server ? "" : row.server)}
                          >
                            {row.server}
                          </button>
                        </td>
                        <td>{row.serves === "main" ? "main replica" : "web replica"}</td>
                        {shape?.mode === "balancer" && (
                          <td>
                            {row.balancer === "primary" ? (
                              <span className="badge badge-ok">shares</span>
                            ) : row.balancer === "backup" ? (
                              <span className="badge" title="Answers only while every other server is down">
                                backup
                              </span>
                            ) : (
                              "–"
                            )}
                          </td>
                        )}
                        <td>
                          <span className="live-bar" style={{ display: "inline-block", width: 80, verticalAlign: "middle" }}>
                            <span style={{ width: `${(100 * row.requests) / top}%` }} />
                          </span>{" "}
                          {row.requests}
                        </td>
                        <td className="small">{share.toFixed(1)}%</td>
                        <td className="mono small">{row.url}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          {error && <div className="form-error small">{error}</div>}
          {!shown.length ? (
            <p className="muted small">{active ? "Waiting for requests…" : "No requests yet."}</p>
          ) : (
            <div className="live-table">
              <table className="table">
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Server</th>
                    <th>Replica</th>
                    <th>Request</th>
                    <th>Status</th>
                    <th>ms</th>
                    <th>Function</th>
                  </tr>
                </thead>
                <tbody>
                  {[...shown].reverse().map((r) => (
                    <tr key={`${r.seq}-${r.replica}`} className={r.level === "ERROR" ? "row-error" : undefined}>
                      <td className="mono small">{r.ts ? new Date(r.ts).toLocaleTimeString() : ""}</td>
                      <td className="mono">{r.server || "–"}</td>
                      <td className="mono small muted">{r.replica || ""}</td>
                      <td className="mono small" title={r.error || undefined}>
                        {r.method ? `${r.method} ${r.path}` : r.event_type}
                      </td>
                      <td className={r.status && r.status >= 500 ? "warn-text" : undefined}>{r.status ?? (r.level === "ERROR" ? "error" : "ok")}</td>
                      <td className="small">{r.duration_ms ?? ""}</td>
                      <td className="mono small">{r.function}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}

/** Live logs of one deployment on this cluster, the same tail as the Logs page and `pskit logs -f`. */
function ClusterLogs({ cluster }: { cluster: OnPremCluster }) {
  const { draft } = useStudio();
  const stacks = Object.keys(cluster.deployments).sort();
  const stackKey = stacks.join("\n");
  const [stack, setStack] = useState(stacks[0] || "");
  useEffect(() => {
    const names = stackKey.split("\n").filter(Boolean);
    setStack((current) => (names.includes(current) ? current : names[0] || ""));
  }, [stackKey]);
  const dep = stack ? cluster.deployments[stack] : undefined;
  const functions = Object.keys(asObject(draft.functions));
  return (
    <div className="card card-pad">
      <div className="row-gap wrap">
        <h3>Live logs</h3>
        {stacks.length > 1 && (
          <select className="select" value={stack} onChange={(e) => setStack(e.target.value)} aria-label="Deployment logs">
            {stacks.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        )}
      </div>
      {!dep ? (
        <p className="muted small">Nothing deployed on this cluster yet. Deploy with Run on → Scaling cluster and the log tail shows here, the same as on one machine.</p>
      ) : (
        <>
          <p className="muted small">
            Logs of every replica of <span className="mono">{stack}</span>
            {cluster.orchestrator === "nomad"
              ? ", read from each server so a web replica's lines show with the main replica."
              : ". Web replicas send their lines to the main replica, and this tail reads them there."}{" "}
            Same as <code className="mono">pskit logs -f</code>.
          </p>
          <DeployedLogs provider="onprem" stage={dep.stage || "dev"} functions={functions} />
        </>
      )}
    </div>
  );
}

/** On-prem services placed on a server of this cluster (one instance each, with its data on that server). */
function ClusterResources({ status }: { status: ClusterStatus | null }) {
  const items = status?.resources || [];
  return (
    <div className="card card-pad">
      <h3>Resources on this cluster</h3>
      {!items.length ? (
        <p className="muted small">
          None yet. Create one under <a href={href("resources")}>Resources → On-prem services</a> with <i>Where → Scaling cluster</i> (or{" "}
          <code className="mono">pskit resources onprem create cache --service redis --cluster {status?.name || "NAME"}</code>): it runs on the server with the
          most free memory, or the one you pick.
        </p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Resource</th>
              <th>Service</th>
              <th>Server</th>
              <th>Address</th>
            </tr>
          </thead>
          <tbody>
            {items.map((r) => (
              <tr key={r.key}>
                <td className="mono">{r.key}</td>
                <td>{r.service}</td>
                <td className="mono">{r.server}</td>
                <td className="mono small">{r.address && r.port ? `${r.address}:${r.port}` : r.address || "–"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="muted small">
        A resource is one instance on one server, not replicated; every function replica reaches it at that server&apos;s cluster address. When its server
        leaves the cluster it keeps running there as a one-server resource.
      </p>
    </div>
  );
}

function Workloads({ cluster, status, onScale }: { cluster: OnPremCluster; status: ClusterStatus | null; onScale: (stack: string, replicas: number) => void }) {
  const [scale, setScale] = useState<Record<string, number>>({});
  const deployments = Object.entries(cluster.deployments);
  return (
    <div className="card card-pad">
      <h3>Deployed functions</h3>
      {!deployments.length && <p className="muted small">Nothing deployed here yet: turn on “Deploy this project&apos;s functions” above, save and deploy.</p>}
      {deployments.length > 0 && (
        <table className="table">
          <thead>
            <tr>
              <th>Deployment</th>
              <th>Endpoint</th>
              <th>Running</th>
              <th>Web replicas</th>
            </tr>
          </thead>
          <tbody>
            {deployments.map(([stack, dep]) => {
              const live = (status?.workloads || []).filter((w) => w.name.startsWith(stack));
              return (
                <tr key={stack}>
                  <td>
                    <b className="mono">{stack}</b>
                    <div className="muted small mono">{dep.image}</div>
                  </td>
                  <td className="mono small">
                    {cluster.balancer?.urls?.[stack] ? (
                      <>
                        <a href={cluster.balancer.urls[stack]} target="_blank" rel="noreferrer" title="Public URL on the load balancer">
                          {cluster.balancer.urls[stack]}
                        </a>
                        <div className="muted" title="The master: logs, tests and the admin API">
                          {dep.endpoint}
                        </div>
                      </>
                    ) : (
                      <a href={dep.endpoint} target="_blank" rel="noreferrer">
                        {dep.endpoint}
                      </a>
                    )}
                  </td>
                  <td className="small">
                    {live.length
                      ? live.map((w) => (
                          <div key={w.name} className={w.running < w.desired ? "warn-text" : undefined}>
                            {w.name.slice(stack.length).replace(/^[_/-]/, "") || "web"}: {w.running}/{w.desired}
                          </div>
                        ))
                      : "–"}
                  </td>
                  <td>
                    <span className="row-gap">
                      <NumberInput value={scale[stack] ?? dep.replicas} min={0} max={500} integer onChange={(v) => setScale((s) => ({ ...s, [stack]: v ?? 0 }))} />
                      <button
                        type="button"
                        className="btn btn-sm"
                        disabled={(scale[stack] ?? dep.replicas) === dep.replicas}
                        onClick={() => onScale(stack, scale[stack] ?? dep.replicas)}
                        title="Until the next deploy; keep it in Web replicas above"
                      >
                        Scale
                      </button>
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}

function AlertSettings({ cluster, onSaved }: { cluster: OnPremCluster; onSaved: () => void }) {
  const { draft } = useStudio();
  const functions = Object.keys(asObject(draft.functions));
  const [capacity, setCapacity] = useState(cluster.capacity);
  const [alert, setAlert] = useState(cluster.alert);
  const [watch, setWatch] = useState(cluster.watch);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const dirty = useMemo(
    () => JSON.stringify([capacity, alert, watch]) !== JSON.stringify([cluster.capacity, cluster.alert, cluster.watch]),
    [capacity, alert, watch, cluster],
  );

  const save = async () => {
    setBusy(true);
    try {
      await api.clusterSettings(cluster.name, { capacity, alert, watch } as unknown as JsonObject);
      toast("Saved", "ok");
      onSaved();
    } catch (exc) {
      toast(errorMessage(exc), "err");
    } finally {
      setBusy(false);
    }
  };

  const test = async () => {
    setBusy(true);
    try {
      const r = await api.clusterTestAlert(cluster.name);
      if (r.errors.length) toast(r.errors.join("; "), "err");
      else toast(`Test alert sent to ${r.sent.join(", ")}`, "ok");
      onSaved();
    } catch (exc) {
      toast(errorMessage(exc), "err");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card card-pad">
      <h3>When every server is full</h3>
      <p className="muted small">
        Optional. pskit calls your function with <code className="mono">event.data</code> = <code className="mono">{"{type: \"pskit.cluster.capacity\", cluster, message, subject, reasons, nodes, ...}"}</code>{" "}
        (send a mail to DevOps from it) and / or POSTs the same JSON to a webhook (Slack, Teams, ...). At most once per cooldown.
      </p>
      <div className="row-gap wrap">
        <FormRow label="CPU full at %" inline>
          <NumberInput value={capacity.cpu} min={10} max={100} integer onChange={(v) => setCapacity({ ...capacity, cpu: v ?? 85 })} />
        </FormRow>
        <FormRow label="Memory full at %" inline>
          <NumberInput value={capacity.memory} min={10} max={100} integer onChange={(v) => setCapacity({ ...capacity, memory: v ?? 85 })} />
        </FormRow>
        <FormRow label="Disk full at %" inline>
          <NumberInput value={capacity.disk} min={10} max={100} integer onChange={(v) => setCapacity({ ...capacity, disk: v ?? 90 })} />
        </FormRow>
      </div>
      <div className="row-gap wrap">
        <FormRow label="Alert function" help="A function of this project, deployed (any on-prem stage).">
          <select className="input" value={alert.function} onChange={(e) => setAlert({ ...alert, function: e.target.value })}>
            <option value="">— none —</option>
            {functions.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </select>
        </FormRow>
        <FormRow label="Stage" help="Where that function is deployed (empty: any).">
          <TextInput value={alert.stage} onChange={(v) => setAlert({ ...alert, stage: v })} placeholder="any" mono />
        </FormRow>
        <FormRow label="Webhook (optional)">
          <TextInput value={alert.webhook} onChange={(v) => setAlert({ ...alert, webhook: v })} placeholder="https://hooks.slack.com/services/…" mono />
        </FormRow>
        <FormRow label="Cooldown (minutes)" inline>
          <NumberInput value={alert.cooldown_minutes} min={1} max={10080} integer onChange={(v) => setAlert({ ...alert, cooldown_minutes: v ?? 30 })} />
        </FormRow>
      </div>
      <div className="row-gap wrap">
        <Toggle checked={watch.enabled} onChange={(on) => setWatch({ ...watch, enabled: on })} label="Watch while the studio runs" />
        {watch.enabled && (
          <FormRow label="every (seconds)" inline>
            <NumberInput value={watch.interval_seconds} min={15} max={86400} integer onChange={(v) => setWatch({ ...watch, interval_seconds: v ?? 60 })} />
          </FormRow>
        )}
        <span className="muted small">
          Around the clock: <code className="mono">pskit cluster watch {cluster.name}</code> on an always-on machine (cron / systemd).
        </span>
      </div>
      <div className="row-gap">
        <button type="button" className="btn btn-primary" disabled={!dirty || busy} onClick={() => void save()}>
          Save
        </button>
        <button type="button" className="btn" disabled={busy || dirty || (!cluster.alert.function && !cluster.alert.webhook)} onClick={() => void test()}>
          Send test alert
        </button>
      </div>
      {cluster.alerts.length > 0 && (
        <>
          <h4>Recent alerts</h4>
          <ul className="cluster-alerts small">
            {[...cluster.alerts].reverse().map((a) => (
              <li key={a.at + a.message}>
                <span className="mono muted">{new Date(a.at).toLocaleString()}</span> {a.test && <span className="badge badge-info">test</span>} {a.message}
                {a.sent.length > 0 && <span className="muted"> → {a.sent.join(", ")}</span>}
                {a.errors.length > 0 && <div className="form-error">{a.errors.join("; ")}</div>}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

/** A saved server (minus `exclude`), with "+ Add a server" to save one on the spot. */
export function ServerChoice({
  state,
  value,
  onChange,
  exclude,
  onServersChanged,
}: {
  state: { servers: OnPremServer[] };
  value: string;
  onChange: (v: string) => void;
  exclude: Set<string>;
  onServersChanged: () => void;
}) {
  const [adding, setAdding] = useState(false);
  const free = state.servers.filter((s) => !exclude.has(s.name));
  return (
    <>
      <span className="row-gap wrap">
        <select className="input" value={value} onChange={(e) => onChange(e.target.value)}>
          <option value="">— pick a saved server —</option>
          {free.map((s) => (
            <option key={s.name} value={s.name}>
              {s.name} · {s.label}
            </option>
          ))}
        </select>
        <button type="button" className="btn btn-sm" onClick={() => setAdding(true)}>
          + Add a server
        </button>
      </span>
      {adding && (
        <ServerForm
          initial={null}
          taken={state.servers.map((s) => s.name)}
          onClose={() => setAdding(false)}
          onSaved={(name) => {
            setAdding(false);
            onServersChanged();
            onChange(name);
          }}
        />
      )}
    </>
  );
}

/** Servers already taken: members of a cluster, or a cluster's load balancer. */
/** What "Send requests to the master too" does, for the create form and the cluster card. */
function MasterServesNote({ orchestrator, on, joined }: { orchestrator: Orchestrator; on: boolean; joined: boolean }) {
  const moves = orchestrator !== "nomad";
  return (
    <div className="muted small">
      {on ? (
        <>
          <b>On:</b> load balancers spread requests over every server, the master included
          {orchestrator === "nomad" ? " (its main replica answers them next to the web replicas)" : " (web replicas may also run on it)"}. Uses the
          master&apos;s spare CPU, but heavy traffic competes with the control plane, schedules, queues and data that also live there.
        </>
      ) : (
        <>
          <b>Off:</b> the master stays idle for requests while a joined server is up: load balancers list it only as a <b>backup</b> and send it
          traffic when every other server is down{moves ? ", and web replicas run on the other servers" : ""}. Keeps the master free for the control
          plane, schedules, queues and data. {!joined && "Until a server joins, the master still serves everything."}
        </>
      )}{" "}
      Turning this on or off updates the load balancers at once
      {moves ? "; web replicas move on or off the master at the next deploy" : ""}. Same as{" "}
      <code className="mono">pskit cluster set NAME --{on ? "" : "no-"}master-serves</code>.
    </div>
  );
}

function inCluster(state: OnPremClustersState): Set<string> {
  return new Set(state.clusters.flatMap((c) => [...c.nodes.map((n) => n.server), ...(c.balancer ? [c.balancer.server] : [])]));
}

function CreateClusterDrawer({
  state,
  onClose,
  onCreated,
  onServersChanged,
}: {
  state: OnPremClustersState;
  onClose: () => void;
  onCreated: (name: string) => void;
  onServersChanged: () => void;
}) {
  const [name, setName] = useState(() => {
    const used = new Set(state.clusters.map((c) => c.name));
    if (!used.has("prod")) return "prod";
    let n = 2;
    while (used.has(`prod-${n}`)) n += 1;
    return `prod-${n}`;
  });
  const [orchestrator, setOrchestrator] = useState<Orchestrator>("swarm");
  const [master, setMaster] = useState("");
  const [advertise, setAdvertise] = useState("");
  // null: the orchestrator's default (Nomad keeps the master as a backup; Swarm and k3s send it requests).
  const [masterServesChoice, setMasterServes] = useState<boolean | null>(null);
  const masterServes = masterServesChoice ?? orchestrator !== "nomad";
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const job = useJob(jobId);
  const info = state.orchestrators.find((o) => o.id === orchestrator);
  const nameError = name && !NAME_RE.test(name) ? "lowercase letter first; lowercase letters, digits and -" : null;
  const taken = state.clusters.some((c) => c.name === name);

  useEffect(() => {
    if (job.status === "succeeded") onCreated(name);
  }, [job.status, name, onCreated]);

  const create = async () => {
    setError(null);
    try {
      const { job_id } = await api.clusterCreate({ name, orchestrator, master, advertise: advertise || undefined, master_serves: masterServes });
      setJobId(job_id);
    } catch (exc) {
      setError(errorMessage(exc));
    }
  };

  return (
    <Drawer
      open
      title="New scaling cluster"
      onClose={onClose}
      actions={
        <button
          type="button"
          className="btn btn-primary"
          disabled={!name || !!nameError || taken || !master || job.status === "running"}
          onClick={() => void create()}
        >
          {job.status === "running" ? "Installing…" : "Create"}
        </button>
      }
    >
      <FormRow
        label="Cluster name"
        required
        error={nameError || (taken ? "already used" : null)}
        help={
          <>
            How you refer to it: <code className="mono">pskit deploy --cluster {name || "NAME"}</code>, <code className="mono">provider.options.cluster: {name || "NAME"}</code>. Lowercase
            letters, digits and -.
          </>
        }
      >
        <TextInput value={name} onChange={(v) => setName(v.toLowerCase())} placeholder="prod" mono autoFocus invalid={!!nameError || taken} />
      </FormRow>
      <FormRow label="Orchestrator" help={info ? `${info.summary} Open between servers: ${info.ports}.` : undefined}>
        <Segmented
          label="Orchestrator"
          value={orchestrator}
          onChange={setOrchestrator}
          options={state.orchestrators.map((o) => ({ value: o.id, label: o.label }))}
        />
      </FormRow>
      <FormRow label="Master server" required help="Runs the control plane and the main replica (schedules, queues, logs, data). Root or passwordless sudo.">
        <ServerChoice state={state} value={master} onChange={setMaster} exclude={inCluster(state)} onServersChanged={onServersChanged} />
      </FormRow>
      <FormRow label="Cluster address (optional)" help="The master's IP the other servers reach (e.g. its private IP). Default: its SSH host.">
        <TextInput value={advertise} onChange={setAdvertise} placeholder="10.0.0.5" mono />
      </FormRow>
      <FormRow label="Master serves requests" help={<MasterServesNote orchestrator={orchestrator} on={masterServes} joined={false} />}>
        <Toggle checked={masterServes} onChange={setMasterServes} label="Send requests to the master too, not only to the joined servers" />
      </FormRow>
      {error && <div className="form-error">{error}</div>}
      {jobId && <JobConsole job={job} />}
    </Drawer>
  );
}

function JoinDrawer({
  cluster,
  state,
  onClose,
  onJoin,
  onServersChanged,
}: {
  cluster: OnPremCluster;
  state: OnPremClustersState;
  onClose: () => void;
  onJoin: (server: string, advertise: string) => void;
  onServersChanged: () => void;
}) {
  const [server, setServer] = useState("");
  const [advertise, setAdvertise] = useState("");
  return (
    <Drawer
      open
      title={`Join a server to ${cluster.name}`}
      onClose={onClose}
      actions={
        <button type="button" className="btn btn-primary" disabled={!server} onClick={() => onJoin(server, advertise)}>
          Join
        </button>
      }
    >
      <p className="muted small">
        pskit installs {cluster.orchestrator_label} on the server over SSH, joins it to the master, and copies the deployed function images to it. Running
        functions keep running; new replicas can start there right away.
      </p>
      <FormRow label="Server" required>
        <ServerChoice state={state} value={server} onChange={setServer} exclude={inCluster(state)} onServersChanged={onServersChanged} />
      </FormRow>
      <FormRow label="Cluster address (optional)" help="This server's IP in the cluster network. Default: its SSH host.">
        <TextInput value={advertise} onChange={setAdvertise} placeholder="10.0.0.6" mono />
      </FormRow>
    </Drawer>
  );
}
