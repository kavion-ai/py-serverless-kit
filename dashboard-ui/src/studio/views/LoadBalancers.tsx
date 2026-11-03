import { useCallback, useEffect, useMemo, useState } from "react";
import { Drawer } from "../../components/Drawer";
import { api, errorMessage } from "../api";
import { AlgorithmPicker, KindBadge, WeightsEditor, algorithmLabel, weightsFor, weightsValid } from "../components/AlgorithmPicker";
import { JobConsole } from "../components/Console";
import { FirewallPanel } from "../components/FirewallPanel";
import { useConfirm, useToast } from "../components/Feedback";
import { FormRow, NumberInput, TextInput, Toggle } from "../components/Forms";
import { PageHeader } from "../components/Misc";
import { useJob } from "../jobs";
import { href, navigate } from "../route";
import { useStudio } from "../store";
import type { BalancerAction, BalancerRoute, JsonObject, NamedBalancer, NamedBalancerStatus, OnPremBalancersState } from "../types";
import { asObject } from "../util";
import { Meter, ServerChoice } from "./Cluster";

const NAME_RE = /^[a-z][a-z0-9-]{0,30}$/;
const REFRESH_MS = 30000;
const LIMITS = { cpu: 85, memory: 85, disk: 90 };

/** Named load balancers: OpenResty on a saved server, shared by projects and clusters by path (`pskit lb`). */
export function LoadBalancersView({ rest }: { rest: string[] }) {
  const [state, setState] = useState<OnPremBalancersState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const job = useJob(jobId);
  const toast = useToast();
  const { providerName } = useStudio();

  const load = useCallback(() => {
    api
      .balancers()
      .then((s) => {
        setState(s);
        setError(null);
      })
      .catch((exc: unknown) => setError(errorMessage(exc)));
  }, []);
  useEffect(load, [load]);

  useEffect(() => {
    if (job.status === "succeeded" || job.status === "failed") {
      load();
      setTick((t) => t + 1);
    }
  }, [job.status, load]);

  const startJob = useCallback(
    async (name: string, action: BalancerAction, body: JsonObject = {}) => {
      try {
        const { job_id } = await api.balancerAction(name, action, body);
        setJobId(job_id);
      } catch (exc) {
        toast(errorMessage(exc), "err");
      }
    },
    [toast],
  );

  const selected = state?.balancers.find((b) => b.name === rest[0]) || state?.balancers[0] || null;

  return (
    <div className="page">
      <PageHeader
        title="Load balancers"
        subtitle={
          <>
            One URL in front of many projects and clusters, by path: <code className="mono">http://lb/orders/</code>,{" "}
            <code className="mono">http://lb/billing/</code>. pskit runs OpenResty (nginx) in Docker on a saved server and keeps the routes on that server,
            so projects in other folders or on other machines share it. Attach it to a scaling cluster (every deployment there gets{" "}
            <code className="mono">/&lt;service&gt;/</code>) or name it in a project&apos;s pskit.yml (
            <code className="mono">provider.options.balancer: edge</code>). Pick how it spreads requests: a <b>static</b> rule or a <b>dynamic</b> choice
            from live load. Same as <code className="mono">pskit lb</code>.
          </>
        }
        actions={
          <button type="button" className="btn btn-primary" onClick={() => setCreating(true)}>
            + Create load balancer
          </button>
        }
      />
      {providerName !== "onprem" && (
        <div className="hint-box warn">
          Load balancers serve on-prem functions. The project&apos;s provider is <b>{providerName || "not set"}</b>: switch it to <b>onprem</b> in{" "}
          <a href={href("overview")}>Overview</a> to put its deployments on one. Clusters can use one either way.
        </div>
      )}
      {error && <div className="form-error">{error}</div>}
      {!state && !error && <p className="muted small">Loading…</p>}
      {state && !state.balancers.length && (
        <div className="card card-pad">
          <h3>No load balancer yet</h3>
          <p className="muted small">
            A load balancer is one server in front of your functions: users call its URL and it forwards every request to one of the servers that run the
            deployment, skipping a server that is down. One load balancer can serve many projects and clusters, each under its own path.
          </p>
          <ol className="small cluster-steps">
            <li>
              Save one more server for it (<a href={href("resources")}>Resources → On-prem services → Servers</a>, or <b>Add a server</b> in the form): it
              must not be part of a cluster.
            </li>
            <li>
              <b>+ Create load balancer</b>: name it, pick the server and how it spreads requests. pskit installs it over SSH.
            </li>
            <li>
              Attach a <a href={href("cluster")}>scaling cluster</a>, or put <code className="mono">balancer: NAME</code> under{" "}
              <code className="mono">provider.options</code> of a project, and deploy.
            </li>
          </ol>
          <button type="button" className="btn btn-primary" onClick={() => setCreating(true)}>
            + Create load balancer
          </button>
        </div>
      )}
      {state && state.balancers.length > 0 && <BalancerList state={state} selected={selected?.name} />}
      {state && selected && (
        <BalancerPanel
          key={selected.name}
          balancer={selected}
          state={state}
          tick={tick}
          busy={job.status === "running"}
          reload={load}
          startJob={(action, body) => void startJob(selected.name, action, body)}
        />
      )}
      {jobId && <JobConsole job={job} />}
      {creating && state && (
        <CreateBalancerDrawer
          state={state}
          onClose={() => setCreating(false)}
          onCreated={(name) => {
            setCreating(false);
            load();
            navigate("balancers", name);
          }}
          onServersChanged={load}
        />
      )}
    </div>
  );
}

function BalancerList({ state, selected }: { state: OnPremBalancersState; selected?: string }) {
  return (
    <div className="card card-pad">
      <table className="table">
        <thead>
          <tr>
            <th>Name</th>
            <th>URL</th>
            <th>Server</th>
            <th>Algorithm</th>
            <th>Clusters</th>
          </tr>
        </thead>
        <tbody>
          {state.balancers.map((b) => (
            <tr key={b.name} className={b.name === selected ? "lb-row-active" : undefined}>
              <td>
                <a href={href("balancers", b.name)}>
                  <b className="mono">{b.name}</b>
                </a>
              </td>
              <td className="mono small">
                <a href={b.url} target="_blank" rel="noreferrer">
                  {b.url}
                </a>
              </td>
              <td className="mono">{b.server}</td>
              <td>
                <span className="lb-chips">
                  {b.algorithm_label} <KindBadge kind={b.kind} />
                </span>
              </td>
              <td className="small">
                {b.clusters.length
                  ? b.clusters.map((c, i) => (
                      <span key={c}>
                        {i > 0 && ", "}
                        <a href={href("cluster", c)} className="mono">
                          {c}
                        </a>
                      </span>
                    ))
                  : "–"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function BalancerPanel({
  balancer,
  state,
  tick,
  busy,
  reload,
  startJob,
}: {
  balancer: NamedBalancer;
  state: OnPremBalancersState;
  tick: number;
  busy: boolean;
  reload: () => void;
  startJob: (action: BalancerAction, body?: JsonObject) => void;
}) {
  const [status, setStatus] = useState<NamedBalancerStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [attaching, setAttaching] = useState(false);
  const [logs, setLogs] = useState<string | null>(null);
  const [logsBusy, setLogsBusy] = useState(false);
  const confirm = useConfirm();
  const toast = useToast();
  const name = balancer.name;

  const refresh = useCallback(() => {
    setLoading(true);
    api
      .balancerStatus(name)
      .then((s) => {
        setStatus(s);
        setStatusError(null);
      })
      .catch((exc: unknown) => setStatusError(errorMessage(exc)))
      .finally(() => setLoading(false));
  }, [name]);

  useEffect(() => {
    refresh();
    const timer = window.setInterval(() => {
      if (!document.hidden) refresh();
    }, REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [refresh]);
  useEffect(() => {
    if (tick) refresh();
  }, [tick, refresh]);

  const loadLogs = async () => {
    setLogsBusy(true);
    try {
      setLogs((await api.balancerLogs(name, 200)).text || "(no requests yet)");
    } catch (exc) {
      toast(errorMessage(exc), "err");
    } finally {
      setLogsBusy(false);
    }
  };

  const routes = status?.routes || [];
  const foreign = routes.filter((r) => !r.mine);
  // The firewall card: this load balancer's server plus every server its routes send requests to.
  const firewallServers = useMemo(() => {
    const out = new Set<string>([balancer.server]);
    if (balancer.address) out.add(balancer.address);
    for (const r of status?.routes || []) {
      for (const b of r.backends) {
        if (b.server) out.add(b.server);
        else if (b.address) out.add(b.address);
      }
    }
    return [...out];
  }, [balancer.server, balancer.address, status]);

  const remove = async () => {
    if (foreign.length) {
      const ok = await confirm({
        title: `Remove load balancer ${name}? It also serves other projects`,
        body: (
          <>
            <p>
              {name} also serves {foreign.length} route(s) of other projects; their URLs stop answering too:
            </p>
            <ul className="small">
              {foreign.map((r) => (
                <li key={r.key} className="mono">
                  {r.url} ({r.owner})
                </li>
              ))}
            </ul>
            <p>
              To stop using it only here, choose <b>Forget</b> instead: it keeps running for the others.
            </p>
          </>
        ),
        confirmLabel: "Remove anyway",
        danger: true,
        typed: name,
      });
      if (ok === "confirm") startJob("remove", { force: true });
      return;
    }
    const ok = await confirm({
      title: `Remove load balancer ${name}?`,
      body: `OpenResty stops on ${balancer.server} and ${balancer.url} stops answering. The functions keep running on their servers.${
        status ? "" : " (Its routes could not be read: if other projects use it, pskit stops and says so.)"
      }`,
      confirmLabel: "Remove",
      danger: true,
    });
    if (ok === "confirm") startJob("remove", { force: false });
  };

  const forget = async () => {
    const ok = await confirm({
      title: `Forget load balancer ${name}?`,
      body: `Only this project stops managing it; it keeps running on ${balancer.server} for every project and cluster that uses it. Add it back with + Create load balancer (same name and server).`,
      confirmLabel: "Forget",
      danger: true,
    });
    if (ok !== "confirm") return;
    try {
      await api.balancerForget(name);
      toast(`Forgot ${name}`, "ok");
      reload();
      navigate("balancers");
    } catch (exc) {
      toast(errorMessage(exc), "err");
    }
  };

  const removeRoute = async (route: BalancerRoute) => {
    const path = route.path || route.key;
    const ok = await confirm({
      title: `Remove ${route.path ? `/${route.path}/` : route.url} from ${name}?`,
      body: route.mine
        ? `${route.url} stops answering. The deployment keeps running; deploying it again puts the route back.`
        : `This route belongs to another project (${route.owner}). ${route.url} stops answering until that project deploys again.`,
      confirmLabel: "Remove route",
      danger: true,
    });
    if (ok === "confirm") startJob("route-remove", { path });
  };

  const detach = async (cluster: string) => {
    const ok = await confirm({
      title: `Detach cluster ${cluster} from ${name}?`,
      body: `The routes of ${cluster}'s deployments are removed from ${name}. The deployments keep running on the cluster.`,
      confirmLabel: "Detach",
      danger: true,
    });
    if (ok === "confirm") startJob("detach", { cluster });
  };

  const settings = asObject(status?.server_settings);

  return (
    <>
      <div className="card card-pad">
        <div className="row-between wrap">
          <div>
            <h3>
              {name}{" "}
              <a className="mono small" href={balancer.url} target="_blank" rel="noreferrer">
                {balancer.url}
              </a>
            </h3>
            <div className="muted small lb-chips">
              <span>
                <b className="mono">{balancer.server}</b> ({balancer.address || "its SSH host"}) · port {balancer.port} ·
              </span>
              <span>{balancer.algorithm_label}</span>
              <KindBadge kind={balancer.kind} />
              <span>·</span>
              {!status ? (
                <span>{loading ? "checking…" : "–"}</span>
              ) : status.reachable === false ? (
                <span className="badge badge-err" title={status.error}>
                  offline
                </span>
              ) : (
                <span className={`badge ${status.running ? "badge-ok" : "badge-err"}`}>{status.state}</span>
              )}
            </div>
          </div>
          <span className="row-gap wrap">
            <button type="button" className="btn btn-sm" disabled={loading} onClick={refresh}>
              {loading ? "Checking…" : "Refresh"}
            </button>
            <button type="button" className="btn btn-sm" disabled={busy} onClick={() => setEditing(true)}>
              Update
            </button>
            <button type="button" className="btn btn-sm" disabled={busy} onClick={() => startJob("sync")} title="Rewrite its settings and every route now">
              Sync
            </button>
            <button type="button" className="btn btn-sm" disabled={logsBusy} onClick={() => void loadLogs()}>
              {logsBusy ? "Loading…" : logs === null ? "Logs" : "Refresh logs"}
            </button>
            <button type="button" className="btn btn-sm btn-danger" disabled={busy} onClick={() => void remove()}>
              Remove
            </button>
            <button type="button" className="btn btn-sm btn-danger" disabled={busy} onClick={() => void forget()} title="Only this project stops managing it">
              Forget
            </button>
          </span>
        </div>
        {statusError && <div className="form-error small">{statusError}</div>}
        {status?.error && <div className="form-error small">{status.error}</div>}
        {status?.reachable !== false && status && !status.running && (
          <div className="hint-box warn">OpenResty is not running on {balancer.server}. Sync starts it again (and shows why when it cannot).</div>
        )}
        {status?.drift && (
          <div className="hint-box warn">
            The server runs other settings than the saved ones
            {settings.port !== undefined && <> (port {String(settings.port)}</>}
            {settings.algorithm !== undefined && <>, {algorithmLabel(state.algorithms, String(settings.algorithm)).toLowerCase()}</>}
            {settings.port !== undefined && ")"}: another machine may have changed it. <b>Sync</b> writes this project&apos;s settings back, <b>Update</b>{" "}
            changes them.
          </div>
        )}
        {status && status.reachable !== false && (
          <div className="row-gap wrap">
            <FormRow label="CPU" inline>
              <Meter value={status.cpu} limit={LIMITS.cpu} />
            </FormRow>
            <FormRow label="Memory" inline>
              <Meter value={status.memory} limit={LIMITS.memory} />
            </FormRow>
            <FormRow label="Disk" inline>
              <Meter value={status.disk} limit={LIMITS.disk} suffix={status.disk_gb ? ` of ${status.disk_gb} GB` : ""} />
            </FormRow>
          </div>
        )}
        <ProjectBalancer balancer={balancer} state={state} />
      </div>

      <div className="card card-pad">
        <div className="row-between wrap">
          <div>
            <h3>Clusters</h3>
            <p className="muted small">
              Every deployment on an attached cluster gets <code className="mono">{balancer.url}/&lt;service&gt;/</code>, kept up to date on deploy, join and
              leave. Same as <code className="mono">pskit lb attach {name} --cluster NAME</code>.
            </p>
          </div>
          <button type="button" className="btn btn-primary" disabled={busy} onClick={() => setAttaching(true)}>
            + Attach cluster
          </button>
        </div>
        {!balancer.clusters.length ? (
          <p className="muted small">No cluster attached.</p>
        ) : (
          <div className="lb-chips">
            {balancer.clusters.map((c) => (
              <span key={c} className="row-gap">
                <a href={href("cluster", c)} className="mono">
                  {c}
                </a>
                <button type="button" className="btn btn-sm btn-danger" disabled={busy} onClick={() => void detach(c)}>
                  Detach
                </button>
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="card card-pad">
        <h3>Routes</h3>
        <p className="muted small">
          Every path on this load balancer, from every project and cluster that uses it (routes live on {balancer.server}). Refreshes every 30 s.
        </p>
        {!status ? (
          <p className="muted small">{loading ? "Reading the routes…" : "–"}</p>
        ) : !routes.length ? (
          <p className="muted small">
            No route yet. Attach a cluster above, or add <code className="mono">balancer: {name}</code> under <code className="mono">provider.options</code> of a
            project and deploy.
          </p>
        ) : (
          <table className="table lb-routes">
            <thead>
              <tr>
                <th>URL</th>
                <th>Owner</th>
                <th>Source</th>
                <th>Algorithm</th>
                <th>Backends</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {routes.map((r) => (
                <tr key={r.key}>
                  <td className="mono small">
                    <a href={r.url} target="_blank" rel="noreferrer">
                      {r.url}
                    </a>
                  </td>
                  <td>
                    <span className="mono small">{r.owner}</span>{" "}
                    {!r.mine && (
                      <span className="badge badge-off" title="A deployment of another project or machine">
                        another project
                      </span>
                    )}
                    {r.updated_at && (
                      <div className="muted small" title={r.updated_from ? `from ${r.updated_from}` : undefined}>
                        {new Date(r.updated_at).toLocaleString()}
                      </div>
                    )}
                  </td>
                  <td className="small">
                    {r.source.startsWith("cluster:") ? (
                      <>
                        cluster{" "}
                        <a href={href("cluster", r.source.slice(8))} className="mono">
                          {r.source.slice(8)}
                        </a>
                      </>
                    ) : (
                      r.source
                    )}
                  </td>
                  <td className="small">
                    {algorithmLabel(state.algorithms, r.effective_algorithm)}
                    {r.inherits && (
                      <span className="muted" title="No algorithm of its own: the load balancer's">
                        {" "}
                        (default)
                      </span>
                    )}
                  </td>
                  <td>
                    <span className="lb-backends">
                      {r.backends.map((b) => (
                        <span
                          key={`${b.address}:${b.port}`}
                          className={`badge ${b.backup ? "badge-warn" : ""}`}
                          title={`${b.address}:${b.port}${b.backup ? " · backup: answers only while every other server is down" : ""}`}
                        >
                          <span className="mono">{b.server || `${b.address}:${b.port}`}</span> ×{b.weight}
                          {b.backup && " · backup"}
                        </span>
                      ))}
                    </span>
                  </td>
                  <td>
                    <button type="button" className="btn btn-sm btn-danger" disabled={busy} onClick={() => void removeRoute(r)}>
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <FirewallPanel title={`Firewall: ${name}`} servers={firewallServers} refreshKey={tick} />

      {logs !== null && (
        <div className="card card-pad">
          <h3>Logs</h3>
          <p className="muted small">
            The last 200 requests; <code className="mono">upstream=</code> is the server that answered. Same as{" "}
            <code className="mono">pskit lb logs {name} -n 200</code>.
          </p>
          <pre className="code-block">{logs}</pre>
        </div>
      )}

      {editing && (
        <UpdateDrawer
          balancer={balancer}
          state={state}
          status={status}
          onClose={() => setEditing(false)}
          onApply={(body) => {
            setEditing(false);
            startJob("update", body);
          }}
        />
      )}
      {attaching && (
        <AttachDrawer
          balancer={balancer}
          state={state}
          onClose={() => setAttaching(false)}
          onAttach={(cluster) => {
            setAttaching(false);
            startJob("attach", { cluster });
          }}
        />
      )}
    </>
  );
}

/** `provider.options.balancer` of the open project: put its deployment on this load balancer at a path. */
function ProjectBalancer({ balancer, state }: { balancer: NamedBalancer; state: OnPremBalancersState }) {
  const { draft, edit } = useStudio();
  const options = asObject(asObject(draft.provider).options);
  const raw = options.balancer;
  const current = typeof raw === "string" ? { name: raw } : asObject(raw);
  const used = current.name === balancer.name;
  const path = used && typeof current.path === "string" ? current.path : "";
  const algorithm = used && typeof current.algorithm === "string" ? current.algorithm : "";
  const set = (next: { path?: string; algorithm?: string } | null) => {
    if (next === null) return edit(["provider", "options", "balancer"], undefined);
    const p = next.path ?? path;
    const a = next.algorithm ?? algorithm;
    edit(["provider", "options", "balancer"], p || a ? { name: balancer.name, ...(p ? { path: p } : {}), ...(a ? { algorithm: a } : {}) } : balancer.name);
  };
  const service = typeof draft.service === "string" ? draft.service : "service";
  return (
    <div className="cluster-binding">
      <Toggle
        checked={used}
        onChange={(on) => set(on ? {} : null)}
        label={
          <>
            Put this project on <b>{balancer.name}</b> (<code className="mono">provider.options.balancer</code>)
          </>
        }
      />
      {used && (
        <div className="row-gap wrap">
          <FormRow label="Path" help={`Empty: the service name, ${balancer.url}/${service}/`} inline>
            <TextInput value={path} onChange={(v) => set({ path: v.toLowerCase() })} placeholder={service} mono />
          </FormRow>
          <FormRow label="Algorithm for this route" inline>
            <select className="input" value={algorithm} onChange={(e) => set({ algorithm: e.target.value })}>
              <option value="">the load balancer&apos;s ({balancer.algorithm_label.toLowerCase()})</option>
              {state.algorithms.map((a) => (
                <option key={a.name} value={a.name}>
                  {a.label} ({a.kind})
                </option>
              ))}
            </select>
          </FormRow>
          <span className="muted small">
            Save, then <a href={href("deploy")}>Deploy</a>: the route is added on deploy and dropped on remove.
          </span>
        </div>
      )}
    </div>
  );
}

/** Servers a new load balancer cannot use: cluster members, a cluster's own load balancer, another named one. */
function takenServers(state: OnPremBalancersState): Set<string> {
  return new Set([
    ...state.clusters.flatMap((c) => [...c.nodes, ...(c.balancer ? [c.balancer] : [])]),
    ...state.balancers.map((b) => b.server),
  ]);
}

function CreateBalancerDrawer({
  state,
  onClose,
  onCreated,
  onServersChanged,
}: {
  state: OnPremBalancersState;
  onClose: () => void;
  onCreated: (name: string) => void;
  onServersChanged: () => void;
}) {
  const [name, setName] = useState(() => {
    const used = new Set(state.balancers.map((b) => b.name));
    if (!used.has("edge")) return "edge";
    let n = 2;
    while (used.has(`edge-${n}`)) n += 1;
    return `edge-${n}`;
  });
  const [server, setServer] = useState("");
  const [port, setPort] = useState<number | undefined>(80);
  const [address, setAddress] = useState("");
  const [algorithm, setAlgorithm] = useState(state.default_algorithm);
  const [weights, setWeights] = useState<Record<string, number>>({});
  const [clusters, setClusters] = useState<string[]>([]);
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const job = useJob(jobId);
  const nameError = name && !NAME_RE.test(name) ? "lowercase letter first; lowercase letters, digits and - (up to 31)" : null;
  const taken = state.balancers.some((b) => b.name === name);
  const exclude = useMemo(() => takenServers(state), [state]);
  const weighable = state.servers.map((s) => s.name).filter((s) => s !== server && !state.balancers.some((b) => b.server === s));

  useEffect(() => {
    if (job.status === "succeeded") onCreated(name);
  }, [job.status, name, onCreated]);

  const create = async () => {
    setError(null);
    try {
      const { job_id } = await api.balancerCreate({
        name,
        server,
        port: port ?? 80,
        ...(address ? { address } : {}),
        algorithm,
        ...(weightsFor(algorithm, weights, weighable) ? { weights: weightsFor(algorithm, weights, weighable) } : {}),
        ...(clusters.length ? { clusters } : {}),
      });
      setJobId(job_id);
    } catch (exc) {
      setError(errorMessage(exc));
    }
  };

  return (
    <Drawer
      open
      title="New load balancer"
      onClose={onClose}
      actions={
        <button
          type="button"
          className="btn btn-primary"
          disabled={!name || !!nameError || taken || !server || !port || !weightsValid(weights) || job.status === "running"}
          onClick={() => void create()}
        >
          {job.status === "running" ? "Installing…" : "Create"}
        </button>
      }
    >
      <p className="muted small">
        pskit installs Docker on the server over SSH and runs OpenResty there. The server must not be part of a cluster, and must reach the functions&apos;
        port on every server behind it. Users call its port: <code className="mono">http://ADDRESS{port && port !== 80 ? `:${port}` : ""}/PATH/</code>.
      </p>
      <FormRow
        label="Name"
        required
        error={nameError || (taken ? "already used" : null)}
        help={
          <>
            How projects refer to it: <code className="mono">provider.options.balancer: {name || "NAME"}</code>, <code className="mono">pskit lb status {name || "NAME"}</code>.
          </>
        }
      >
        <TextInput value={name} onChange={(v) => setName(v.toLowerCase())} placeholder="edge" mono autoFocus invalid={!!nameError || taken} />
      </FormRow>
      <FormRow label="Server" required help="A saved server outside every cluster, not used by another load balancer. Root or passwordless sudo.">
        <ServerChoice state={state} value={server} onChange={setServer} exclude={exclude} onServersChanged={onServersChanged} />
      </FormRow>
      <div className="row-gap wrap">
        <FormRow label="Port" help="80: http://its-address/" inline>
          <NumberInput value={port} min={1} max={65535} integer onChange={setPort} />
        </FormRow>
        <FormRow label="Address in the URL (optional)" help="The IP or name users reach it at. Default: its SSH host.">
          <TextInput value={address} onChange={setAddress} placeholder="10.0.0.9" mono />
        </FormRow>
      </div>
      <FormRow label="How it spreads requests" help="Change it any time with Update; a project can pick another one for its own route.">
        <AlgorithmPicker algorithms={state.algorithms} value={algorithm} onChange={setAlgorithm} defaultAlgorithm={state.default_algorithm} />
      </FormRow>
      <WeightsEditor algorithm={algorithm} servers={weighable} value={weights} onChange={setWeights} />
      {state.clusters.length > 0 && (
        <FormRow label="Attach clusters now (optional)" help="Every deployment on them gets /<service>/ on this load balancer.">
          <div className="lb-chips">
            {state.clusters.map((c) => {
              const member = c.nodes.includes(server);
              return (
                <Toggle
                  key={c.name}
                  checked={clusters.includes(c.name)}
                  onChange={(on) => setClusters((all) => (on ? [...all, c.name] : all.filter((x) => x !== c.name)))}
                  label={
                    <span className="mono" title={member ? `${server} is a server of ${c.name}` : undefined}>
                      {c.name}
                      {member && " (contains this server)"}
                    </span>
                  }
                />
              );
            })}
          </div>
        </FormRow>
      )}
      {error && <div className="form-error">{error}</div>}
      {jobId && <JobConsole job={job} />}
    </Drawer>
  );
}

function UpdateDrawer({
  balancer,
  state,
  status,
  onClose,
  onApply,
}: {
  balancer: NamedBalancer;
  state: OnPremBalancersState;
  status: NamedBalancerStatus | null;
  onClose: () => void;
  onApply: (body: JsonObject) => void;
}) {
  const [port, setPort] = useState<number | undefined>(balancer.port);
  const [address, setAddress] = useState(balancer.address || "");
  const [algorithm, setAlgorithm] = useState(balancer.algorithm);
  const [weights, setWeights] = useState<Record<string, number>>(balancer.weights || {});
  const servers = useMemo(() => {
    const all = new Set<string>(Object.keys(balancer.weights || {}));
    for (const c of state.clusters) if (balancer.clusters.includes(c.name)) c.nodes.forEach((n) => all.add(n));
    for (const r of status?.routes || []) for (const b of r.backends) if (b.server) all.add(b.server);
    return [...all].sort();
  }, [balancer, state.clusters, status]);
  const w = weightsFor(algorithm, weights, servers);
  return (
    <Drawer
      open
      title={`Update load balancer ${balancer.name}`}
      onClose={onClose}
      actions={
        <button
          type="button"
          className="btn btn-primary"
          disabled={!port || !weightsValid(weights)}
          onClick={() => onApply({ port: port ?? balancer.port, algorithm, ...(address ? { address } : {}), ...(w ? { weights: w } : {}) })}
        >
          Apply
        </button>
      }
    >
      <p className="muted small">
        Rewrites its settings on {balancer.server} and reloads OpenResty without dropping requests. Routes that chose their own algorithm keep it. Same as{" "}
        <code className="mono">pskit lb update {balancer.name}</code>.
      </p>
      <div className="row-gap wrap">
        <FormRow label="Port" inline>
          <NumberInput value={port} min={1} max={65535} integer onChange={setPort} />
        </FormRow>
        <FormRow label="Address in the URL" help="Empty: unchanged.">
          <TextInput value={address} onChange={setAddress} placeholder="10.0.0.9" mono />
        </FormRow>
      </div>
      <FormRow label="How it spreads requests">
        <AlgorithmPicker algorithms={state.algorithms} value={algorithm} onChange={setAlgorithm} defaultAlgorithm={state.default_algorithm} />
      </FormRow>
      <WeightsEditor algorithm={algorithm} servers={servers} value={weights} onChange={setWeights} />
      {port !== balancer.port && <div className="hint-box warn">Every URL on it changes to port {port}: tell the users of the other projects too.</div>}
    </Drawer>
  );
}

function AttachDrawer({
  balancer,
  state,
  onClose,
  onAttach,
}: {
  balancer: NamedBalancer;
  state: OnPremBalancersState;
  onClose: () => void;
  onAttach: (cluster: string) => void;
}) {
  const free = state.clusters.filter((c) => !balancer.clusters.includes(c.name));
  const [cluster, setCluster] = useState(free[0]?.name || "");
  return (
    <Drawer
      open
      title={`Attach a cluster to ${balancer.name}`}
      onClose={onClose}
      actions={
        <button type="button" className="btn btn-primary" disabled={!cluster} onClick={() => onAttach(cluster)}>
          Attach
        </button>
      }
    >
      {!free.length ? (
        <p className="muted small">
          Every cluster is attached already{state.clusters.length ? "" : " (there is none yet)"}. Create one under <a href={href("cluster")}>Scaling cluster</a>.
        </p>
      ) : (
        <>
          <p className="muted small">
            Each deployment on the cluster gets <code className="mono">{balancer.url}/&lt;service&gt;/</code> (with the stage when two stages of one service run
            there), spread over the cluster&apos;s servers with {balancer.algorithm_label.toLowerCase()}.
          </p>
          <FormRow label="Cluster" required>
            <select className="input" value={cluster} onChange={(e) => setCluster(e.target.value)}>
              {free.map((c) => (
                <option key={c.name} value={c.name} disabled={c.nodes.includes(balancer.server)}>
                  {c.name} · {c.nodes.length} server(s){c.nodes.includes(balancer.server) ? ` (contains ${balancer.server})` : ""}
                </option>
              ))}
            </select>
          </FormRow>
        </>
      )}
    </Drawer>
  );
}
