import { useEffect, useState } from "react";
import { api, errorMessage } from "../api";
import { useJob } from "../jobs";
import type { OnPremCatalogItem, OnPremReplicationInfo, OnPremServer, OnPremService } from "../types";
import { JobConsole } from "./Console";
import { useConfirm } from "./Feedback";
import { EnumSelect, FormRow, NumberInput, Segmented, Toggle } from "./Forms";
import { ReplicationDiagram, type DiagramNode } from "./ReplicationDiagram";

const THIS_MACHINE = "this machine";

/** The replicated database part of the create form: which server writes, which read, how they copy, who balances. */
export function ReplicationForm(props: {
  item: OnPremCatalogItem;
  info: OnPremReplicationInfo;
  servers: OnPremServer[];
  port: number;
  repOn: "servers" | "local";
  setRepOn: (v: "servers" | "local") => void;
  primary: string;
  setPrimary: (v: string) => void;
  replicas: string[];
  setReplicas: (fn: (r: string[]) => string[]) => void;
  localReplicas: number | undefined;
  setLocalReplicas: (v: number | undefined) => void;
  sync: "async" | "sync";
  setSync: (v: "async" | "sync") => void;
  lbServer: string;
  setLbServer: (v: string) => void;
  lbLocal: boolean;
  setLbLocal: (v: boolean) => void;
  lbPort: number | undefined;
  setLbPort: (v: number | undefined) => void;
  error: string | null;
}) {
  const { item, info, servers, port, repOn, primary, replicas, sync } = props;
  const local = repOn === "local";
  const host = (name: string) => servers.find((s) => s.name === name)?.host || "";
  const lbOn = !!info.balancer && (local ? props.lbLocal : !!props.lbServer);
  const lbPort = props.lbPort || info.balancer_port;
  const count = Math.max(1, Math.min(9, props.localReplicas || 1));

  const diagram = {
    engine: item.label,
    sync,
    primary: local
      ? { title: THIS_MACHINE, detail: `127.0.0.1:${port}` }
      : { title: primary || "pick a server", detail: primary ? `${host(primary)}:${port}` : "" },
    replicas: local
      ? Array.from({ length: count }, (_x, i): DiagramNode => ({ title: THIS_MACHINE, detail: `127.0.0.1:${port + i + 1}` }))
      : replicas.map((r): DiagramNode => ({ title: r, detail: `${host(r)}:${port}` })),
    balancer: lbOn
      ? {
          kind: info.balancer,
          title: local ? THIS_MACHINE : props.lbServer,
          detail: `${local ? "127.0.0.1" : host(props.lbServer)}:${lbPort}`,
        }
      : null,
    driverRoutes: !info.balancer,
    growable: true,
  };

  return (
    <div className="driver-box card card-pad replication-form">
      <h3>Replication · {info.method}</h3>
      <FormRow
        label="Members run on"
        help={
          local
            ? "Every member on this machine, each on its own port: to try replication. Production replicas belong on other servers."
            : "One member per saved server (Servers, below). Docker is installed on each server when missing."
        }
      >
        <Segmented
          label="Members run on"
          value={repOn}
          onChange={(v) => props.setRepOn(v as "servers" | "local")}
          options={[
            { value: "servers", label: "Saved servers" },
            { value: "local", label: "This machine (try it)", disabled: !info.local },
          ]}
        />
      </FormRow>
      {!local ? (
        <>
          <FormRow label="Primary (writes)" required help="Takes every INSERT / UPDATE / DELETE. Pick your strongest server.">
            <EnumSelect
              value={primary}
              onChange={props.setPrimary}
              options={[
                ...(primary ? [] : [{ value: "", label: "Pick the write server…" }]),
                ...servers.map((s) => ({ value: s.name, label: `${s.name} (${s.host})` })),
              ]}
            />
          </FormRow>
          <FormRow label="Read replicas" required help="Each copies the primary and answers reads. Add or remove replicas later from Details.">
            <div className="check-grid">
              {servers
                .filter((s) => s.name !== primary)
                .map((s) => (
                  <label key={s.name} className="check">
                    <input
                      type="checkbox"
                      checked={replicas.includes(s.name)}
                      onChange={(e) => props.setReplicas((r) => (e.target.checked ? [...r, s.name] : r.filter((x) => x !== s.name)))}
                    />
                    {s.name} <span className="muted small">{s.host}</span>
                  </label>
                ))}
              {servers.length < 2 && <span className="muted">Save at least two servers below (one for the primary, one per replica).</span>}
            </div>
          </FormRow>
        </>
      ) : (
        <FormRow label="Read replicas" help="Ports follow the primary's: replica 1 on port + 1, and so on.">
          <NumberInput integer min={1} max={9} value={props.localReplicas} onChange={props.setLocalReplicas} />
        </FormRow>
      )}
      <FormRow label="Primary → replicas" help={sync === "sync" ? info.sync : info.async}>
        <Segmented
          label="Primary → replicas"
          value={sync}
          onChange={(v) => props.setSync(v as "async" | "sync")}
          options={[
            { value: "async", label: "Asynchronous (fastest)" },
            { value: "sync", label: "Synchronous (no lost writes)" },
          ]}
        />
      </FormRow>
      {info.balancer ? (
        <>
          <FormRow
            label="Load balancer"
            help={`${info.routing} Without one, the functions' URL is the primary and reads can use the replicas' addresses (READ_URLS).`}
          >
            {local ? (
              <Toggle checked={props.lbLocal} onChange={props.setLbLocal} label={`Start ${info.balancer} here (one address for the functions)`} />
            ) : (
              <EnumSelect
                value={props.lbServer}
                onChange={props.setLbServer}
                options={[
                  { value: "", label: `None: connect to the primary, reads via READ_URLS` },
                  ...servers.map((s) => ({
                    value: s.name,
                    label: `${info.balancer} on ${s.name} (${s.host})${s.name === primary ? " · with the primary" : replicas.includes(s.name) ? " · with a replica" : ""}`,
                  })),
                ]}
              />
            )}
          </FormRow>
          {lbOn && (
            <FormRow label="Load balancer port" help={`What the functions connect to. Default ${info.balancer_port}, so it can share a server with a member.`}>
              <NumberInput integer min={1} max={65535} value={props.lbPort} placeholder={String(info.balancer_port)} onChange={props.setLbPort} />
            </FormRow>
          )}
        </>
      ) : (
        <div className="hint-box">{info.routing}</div>
      )}
      <ReplicationDiagram {...diagram} />
      {props.error && <div className="form-error">{props.error}</div>}
    </div>
  );
}

/** A created replicated database in Details: the picture with live states, each member's lag, add / remove. */
export function ReplicasPanel({ info, onChanged }: { info: OnPremService; onChanged: () => void }) {
  const topo = info.topology;
  const [servers, setServers] = useState<OnPremServer[]>([]);
  const [server, setServer] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const job = useJob(jobId);
  const confirm = useConfirm();
  useEffect(() => {
    api.onpremServers().then((r) => setServers(r.servers), () => undefined);
  }, []);
  useEffect(() => {
    if (job.status === "succeeded" || job.status === "failed") onChanged();
  }, [job.status]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!topo) return null;
  const used = new Set(topo.members.map((m) => m.server));
  const free = servers.filter((s) => !used.has(s.name));
  const primary = topo.members.find((m) => m.role === "primary") || topo.members[0];
  const replicas = topo.members.filter((m) => m.role === "replica");
  const node = (m: { server: string; address: string; port: number; state?: string }): DiagramNode => ({
    title: m.server || THIS_MACHINE,
    detail: `${m.address}:${m.port}`,
    state: m.state,
  });
  const busy = job.status === "running";

  const add = async () => {
    setError(null);
    try {
      setJobId((await api.onpremReplicaAdd(info.key, topo.local ? "local" : server)).job_id);
    } catch (exc) {
      setError(errorMessage(exc));
    }
  };
  const remove = async (name: string) => {
    const answer = await confirm({
      title: `Remove replica ${name}?`,
      body: "Its container stops and the load balancer stops sending reads to it. Keep its data volume, or delete it.",
      confirmLabel: "Remove, keep data",
      extra: [{ label: "Delete data too", value: "delete-data", danger: true }],
      danger: true,
    });
    if (answer !== "confirm" && answer !== "delete-data") return;
    setError(null);
    try {
      setJobId((await api.onpremReplicaRemove(info.key, name, answer === "delete-data")).job_id);
    } catch (exc) {
      setError(errorMessage(exc));
    }
  };

  return (
    <div className="replicas-panel stack-xs">
      <h4>
        Replication · {topo.sync === "sync" ? "synchronous" : "asynchronous"}
        {topo.balancer ? ` · ${topo.balancer.kind} splits reads and writes` : info.service === "mongodb" ? " · the driver routes" : " · no load balancer"}
      </h4>
      <ReplicationDiagram
        engine={info.service}
        sync={topo.sync}
        primary={node(primary)}
        replicas={replicas.map(node)}
        balancer={topo.balancer ? { ...node(topo.balancer), kind: topo.balancer.kind } : null}
        driverRoutes={info.service === "mongodb"}
      />
      <div style={{ overflowX: "auto" }}>
        <table className="table">
          <thead>
            <tr>
              <th>Member</th>
              <th>Address</th>
              <th>State</th>
              <th>Replication</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {[...topo.members, ...(topo.balancer ? [topo.balancer] : [])].map((m) => (
              <tr key={m.name}>
                <td>
                  <b className="mono">{m.name}</b>
                  <div className="muted small">{m.role === "balancer" ? "load balancer" : m.role}{m.server ? ` · ${m.server}` : ""}</div>
                </td>
                <td className="mono small">
                  {m.address}:{m.port}
                </td>
                <td>
                  <span className={`badge ${m.state === "running" ? "badge-ok" : m.state ? "badge-err" : ""}`}>{m.state || "?"}</span>
                </td>
                <td className="mono small" style={{ whiteSpace: "pre-wrap" }}>
                  {m.replication || ""}
                </td>
                <td>
                  {m.role === "replica" && replicas.length > 1 && (
                    <button type="button" className="btn btn-sm btn-danger" disabled={busy} onClick={() => void remove(m.name)}>
                      Remove
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {topo.report && <pre className="md-code console-log">{topo.report}</pre>}
      <div className="row-gap wrap">
        {!topo.local && (
          <EnumSelect
            value={server}
            onChange={setServer}
            options={[{ value: "", label: free.length ? "Server for a new replica…" : "No free saved server (add one below)" }, ...free.map((s) => ({ value: s.name, label: `${s.name} (${s.host})` }))]}
          />
        )}
        <button type="button" className="btn btn-sm btn-primary" disabled={busy || (!topo.local && !server)} onClick={() => void add()}>
          + Add read replica
        </button>
        <span className="muted small">It copies the current data, then follows the primary; the load balancer starts sending it reads.</span>
      </div>
      {error && <div className="form-error">{error}</div>}
      {jobId && <JobConsole job={job} />}
    </div>
  );
}
