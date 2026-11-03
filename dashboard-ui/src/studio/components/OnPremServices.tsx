import { useCallback, useEffect, useMemo, useState } from "react";
import { Drawer } from "../../components/Drawer";
import { api, errorMessage } from "../api";
import { useJob } from "../jobs";
import { useStudio } from "../store";
import type { JsonObject, OnPremAlert, OnPremCatalogItem, OnPremCluster, OnPremServer, OnPremService, OnPremServicesState, OnPremTarget } from "../types";
import { asObject, NAME_RE, uniqueName } from "../util";
import { JobConsole } from "./Console";
import { Markdown } from "./Markdown";
import { useConfirm, useToast } from "./Feedback";
import { EnumSelect, FilePathInput, FormRow, NumberInput, Segmented, TextInput, Toggle } from "./Forms";
import { AlertFields, AlertsPanel, EMPTY_ALERT, NEW_FUNCTION, ServiceMonitor, alertBody, alertError, alertHandler, type AlertDraft } from "./Monitoring";
import { ServersPanel, ServiceConsole, TerminalDrawer } from "./OnPremMachines";
import { ServiceBrowser } from "./ServiceBrowser";
import { ReplicasPanel, ReplicationForm } from "./Replication";
import type { GuideRef } from "./ResourceGuides";

// Services by their catalog group (one group each), then software to install on a server.
const serviceGroup = (title: string, ...groups: string[]) => ({ title, match: (c: OnPremCatalogItem) => c.kind === "service" && groups.includes(c.group || "") });
const GROUPS: { title: string; match: (c: OnPremCatalogItem) => boolean }[] = [
  serviceGroup("Queues & streams", "Queues and streams"),
  serviceGroup("Redis-compatible (cache, queue, stream)", "Caches and queues"),
  serviceGroup("Object storage", "Object storage"),
  serviceGroup("Databases", "Databases"),
  serviceGroup("Mail (receive e-mail, run functions)", "Mail"),
  serviceGroup("Secret managers", "Secrets"),
  serviceGroup("AWS emulators", "AWS emulators"),
  serviceGroup("Monitoring & tracing", "Monitoring"),
  serviceGroup("Identity & search", "Identity", "Search"),
  serviceGroup("Automation, web & tools", "Automation", "Web", "Tools"),
  { title: "Install on a server: languages & Docker", match: (c) => c.kind === "runtime" && (c.group || "").startsWith("Languages") },
  { title: "Install on a server: web servers", match: (c) => c.kind === "runtime" && c.group === "Web servers" },
  { title: "Install on a server: process managers & tools", match: (c) => c.kind === "runtime" && ["Process managers", "Tools"].includes(c.group || "") },
];
const ROLE_LABEL: Record<string, string> = {
  queue: "Queue",
  stream: "Stream (consumer group)",
  cache: "Cache",
  database: "Database",
  storage: "Bucket",
  custom: "Service",
  secrets: "Secret manager",
  smtp: "SMTP server (mail trigger)",
};
/** The pskit.yml resource type a service role becomes. */
export const ROLE_RESOURCE_TYPE: Record<string, string> = { stream: "queue", secrets: "custom" };
const roleType = (role: string) => ROLE_RESOURCE_TYPE[role] || role;
// Roles a function can be triggered by (others are only bound as connection values).
const TRIGGER_ROLES = ["queue", "stream", "storage", "smtp"];
const DOMAIN_RE = /^(?!-)[A-Za-z0-9-]{1,63}(\.(?!-)[A-Za-z0-9-]{1,63})+$/;

export function OnPremServices({ onGuide }: { onGuide: (ref: GuideRef) => void }) {
  const [state, setState] = useState<OnPremServicesState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState<OnPremCatalogItem | null | "pick">(null);
  const [details, setDetails] = useState<string | null>(null);
  const [usage, setUsage] = useState<string | null>(null);
  const [consoleKey, setConsoleKey] = useState<string | null>(null);
  const [terminalKey, setTerminalKey] = useState<string | null>(null);
  const [browse, setBrowse] = useState<{ key: string; kinds: string[] } | null>(null);
  const browsersOf = (service: string) => state?.catalog.find((c) => c.id === service)?.browsers || [];
  const [createServer, setCreateServer] = useState<string | undefined>(undefined);
  const [jobId, setJobId] = useState<string | null>(null);
  const job = useJob(jobId);
  const { draft, replace } = useStudio();
  const confirm = useConfirm();
  const toast = useToast();

  const load = useCallback(() => {
    api
      .onpremServices()
      .then((s) => {
        setState(s);
        setError(null);
      })
      .catch((exc: unknown) => setError(errorMessage(exc)));
  }, []);
  useEffect(load, [load]);
  useEffect(() => {
    if (job.status === "succeeded" || job.status === "failed") load();
  }, [job.status, load]);

  const inProject = (key: string) => key in asObject(draft.resources) || key in asObject(asObject(asObject(draft.providers).onprem).resources);

  const addToProject = async (svc: OnPremService, attach?: string[]) => {
    try {
      const { raw } = await api.onpremApply(draft, svc.key, attach);
      replace(raw);
      toast(`Added ${svc.key} to pskit.yml${attach && attach.length ? ` with triggers on ${attach.join(", ")}` : ""} (not saved yet)`, "ok");
    } catch (exc) {
      toast(errorMessage(exc), "err");
    }
  };

  const [backupFor, setBackupFor] = useState<OnPremService | null>(null);
  const backup = async (svc: OnPremService, folder: string) => {
    try {
      setJobId((await api.onpremBackup(svc.key, folder || undefined)).job_id);
      setBackupFor(null);
    } catch (exc) {
      toast(errorMessage(exc), "err");
    }
  };

  const remove = async (svc: OnPremService) => {
    const runtime = svc.kind === "runtime";
    const answer = await confirm({
      title: `Remove ${svc.key}?`,
      body: runtime
        ? `${svc.service} stays installed on ${svc.target_label}; pskit only forgets it.`
        : `Stops and deletes the ${svc.service} container on ${svc.target_label}. Its data volume is kept unless you choose "Delete data too". The resource and its triggers are removed from pskit.yml (not saved yet).`,
      confirmLabel: runtime ? "Forget" : "Remove, keep data",
      extra: runtime || !svc.volume ? undefined : [{ label: "Delete data too", value: "delete-data", danger: true }],
      danger: true,
    });
    if (answer !== "confirm" && answer !== "delete-data") return;
    try {
      setJobId((await api.onpremRemove(svc.key, answer === "delete-data")).job_id);
      if (!runtime && inProject(svc.key)) replace((await api.onpremUnapply(draft, svc.key)).raw);
    } catch (exc) {
      toast(errorMessage(exc), "err");
    }
  };

  return (
    <div className="card card-pad onprem-services">
      <div className="row-between">
        <div>
          <h3>On-prem services</h3>
          <p className="muted small">
            One click starts Redis, Kafka, RabbitMQ, NATS, PostgreSQL, MinIO and more with Docker, on this machine or any SSH server (the
            functions' server or another one), and adds it as a resource. Passwords go to <code className="mono">{state?.env_file || ".env.onprem"}</code>,
            which the host loads; never into pskit.yml.
          </p>
        </div>
        <span className="row-gap">
          <button type="button" className="btn" onClick={() => onGuide({ cloud: "onprem", page: "services" })}>
            Guide
          </button>
          <button type="button" className="btn btn-primary" onClick={() => setCreating("pick")} disabled={!state}>
            + Create service
          </button>
        </span>
      </div>
      {error && <div className="form-error">{error}</div>}
      {state && !state.services.length && <p className="muted">Nothing created yet.</p>}
      {state && state.services.length > 0 && (
        <table className="table">
          <thead>
            <tr>
              <th>Key</th>
              <th>Service</th>
              <th>Used as</th>
              <th>Where</th>
              <th>Endpoint</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {state.services.map((svc) => (
              <tr key={svc.key}>
                <td>
                  <b className="mono">{svc.key}</b>
                </td>
                <td>{state.catalog.find((c) => c.id === svc.service)?.label || svc.service}</td>
                <td>{svc.role ? ROLE_LABEL[svc.role] || svc.role : "runtime"}</td>
                <td className="small">
                  {svc.topology
                    ? `primary + ${svc.topology.members.length - 1} replica${svc.topology.members.length === 2 ? "" : "s"} (${svc.topology.sync}${svc.topology.local ? ", this machine" : ""})`
                    : svc.target_label}
                </td>
                <td className="mono small">{svc.port ? `${svc.address}:${svc.port}` : "—"}</td>
                <td>
                  <span className="row-gap">
                    <button
                      type="button"
                      className="btn btn-sm btn-primary"
                      onClick={() => setUsage(svc.key)}
                      title={svc.service === "smtp" ? "DNS records to add at your domain provider, the port, and the mail fields handlers get" : "Connect from any program: code, terminal, security"}
                    >
                      {svc.service === "smtp" ? "DNS guide" : "How to use"}
                    </button>
                    <button type="button" className="btn btn-sm" onClick={() => setDetails(svc.key)}>
                      Details
                    </button>
                    {svc.kind === "service" && browsersOf(svc.service).length > 0 && (
                      <button
                        type="button"
                        className="btn btn-sm btn-primary"
                        onClick={() => setBrowse({ key: svc.key, kinds: browsersOf(svc.service) })}
                        title="pskit's own UI: buckets and objects, or secrets"
                      >
                        {browsersOf(svc.service).some((b) => b === "s3" || b === "gcs") ? "Browse" : "Browse secrets"}
                      </button>
                    )}
                    {svc.kind === "service" && (
                      <button type="button" className="btn btn-sm" onClick={() => setConsoleKey(svc.key)} title="Run commands: redis-cli, psql, mongosh, rpk, bao, ... or sh in the container">
                        Console
                      </button>
                    )}
                    {svc.kind === "service" && (
                      <button type="button" className="btn btn-sm" onClick={() => setTerminalKey(svc.key)} title="Interactive client in a browser terminal (Docker)">
                        Terminal
                      </button>
                    )}
                    {svc.kind === "service" && !inProject(svc.key) && (
                      <button type="button" className="btn btn-sm" onClick={() => void addToProject(svc)} title="Add the resource (and its triggers) to pskit.yml">
                        Add to pskit.yml
                      </button>
                    )}
                    {state.catalog.find((c) => c.id === svc.service)?.backup && (
                      <button type="button" className="btn btn-sm" onClick={() => setBackupFor(svc)}>
                        Backup
                      </button>
                    )}
                    <button type="button" className="btn btn-sm btn-danger" onClick={() => void remove(svc)}>
                      Remove
                    </button>
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {jobId && !creating && <JobConsole job={job} onCancel={() => setJobId(null)} />}
      {creating && state && (
        <CreateDrawer
          state={state}
          initial={creating === "pick" ? null : creating}
          server={createServer}
          onClose={() => {
            setCreating(null);
            setCreateServer(undefined);
          }}
          onCreated={(svc, attach) => {
            load();
            void addToProject(svc, attach);
            if (svc.service === "smtp") setUsage(svc.key); // the DNS records to add come next
          }}
        />
      )}
      {details && <DetailsDrawer serviceKey={details} onClose={() => setDetails(null)} />}
      {backupFor && <BackupDialog svc={backupFor} onClose={() => setBackupFor(null)} onStart={(folder) => void backup(backupFor, folder)} />}
      {usage && <ServiceUsageDrawer serviceKey={usage} onClose={() => setUsage(null)} />}
      {browse && <ServiceBrowser serviceKey={browse.key} kinds={browse.kinds} onClose={() => setBrowse(null)} />}
      {consoleKey && <ServiceConsole serviceKey={consoleKey} onClose={() => setConsoleKey(null)} />}
      {terminalKey && <TerminalDrawer request={{ key: terminalKey }} onClose={() => setTerminalKey(null)} />}
      <ServersPanel
        onInstall={(name) => {
          setCreateServer(name);
          setCreating("pick");
        }}
      />
    </div>
  );
}

export function CreateDrawer({
  state,
  initial,
  server,
  resourceType,
  onClose,
  onCreated,
}: {
  state: OnPremServicesState;
  initial: OnPremCatalogItem | null;
  server?: string;
  /** Only services that can back this resource type (queue, storage, database, cache, custom). */
  resourceType?: string;
  onClose: () => void;
  onCreated: (svc: OnPremService, attach: string[]) => void;
}) {
  const { draft } = useStudio();
  const toast = useToast();
  const [item, setItem] = useState<OnPremCatalogItem | null>(initial);
  const taken = useMemo(
    () => [...Object.keys(asObject(draft.resources)), ...state.services.map((s) => s.key)],
    [draft.resources, state.services],
  );
  const [key, setKey] = useState("");
  const [role, setRole] = useState("");
  const defaultCluster = !server && state.default_target.cluster ? state.default_target.cluster : "";
  // Where: this machine, one SSH server, or a server of a scaling cluster (the functions' cluster by default).
  const [where, setWhere] = useState<"local" | "ssh" | "cluster">(defaultCluster ? "cluster" : server || state.default_target.method === "ssh" ? "ssh" : "local");
  const [target, setTarget] = useState<OnPremTarget>(where !== "local" ? { method: "ssh" } : { method: "local" });
  const [servers, setServers] = useState<OnPremServer[]>([]);
  const [savedServer, setSavedServer] = useState<string>(server || (defaultCluster ? "" : state.default_target.server || ""));
  const [clusters, setClusters] = useState<OnPremCluster[]>([]);
  const [clusterName, setClusterName] = useState(defaultCluster);
  const [clusterNode, setClusterNode] = useState("");
  const [version, setVersion] = useState("");
  useEffect(() => {
    api.onpremServers().then(
      (r) => {
        setServers(r.servers);
        // pskit.yml may name a server that was removed or renamed: never send a name the picker cannot show.
        setSavedServer((cur) => (cur && !r.servers.some((s) => s.name === cur) ? (r.servers.length === 1 ? r.servers[0].name : "") : cur));
      },
      () => undefined,
    );
    api.clusters().then(
      (r) => {
        setClusters(r.clusters);
        if (!defaultCluster && r.clusters.length === 1) setClusterName(r.clusters[0].name);
      },
      () => undefined,
    );
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const cluster = clusters.find((c) => c.name === clusterName);
  const [ssh, setSsh] = useState<OnPremTarget>({ method: "ssh", user: "root", port: 22, ...(state.default_target.method === "ssh" ? state.default_target : {}) });
  const [port, setPort] = useState<number | undefined>(undefined);
  const [address, setAddress] = useState("");
  const [image, setImage] = useState("");
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [bind, setBind] = useState("");
  const [withGui, setWithGui] = useState(true);
  const [guiLogin, setGuiLogin] = useState<"password" | "none">("password");
  const [guiPassword, setGuiPassword] = useState("");
  const [sshAuth, setSshAuth] = useState<"key" | "agent" | "password">(
    state.default_target.auth || (state.default_target.password_file ? "password" : state.default_target.identity_file ? "key" : "agent"),
  );
  const [sshPassword, setSshPassword] = useState("");
  const [attach, setAttach] = useState<string[]>([]);
  const [domains, setDomains] = useState("");
  const [functionsUrl, setFunctionsUrl] = useState("");
  const [maxSize, setMaxSize] = useState<number | undefined>(undefined);
  // Database scaling: one server, or a primary (writes) with read replicas and an optional load balancer.
  const [scale, setScale] = useState<"single" | "replicated">("single");
  const [repOn, setRepOn] = useState<"servers" | "local">("servers");
  const [primaryServer, setPrimaryServer] = useState(server || state.default_target.server || "");
  const [replicaServers, setReplicaServers] = useState<string[]>([]);
  const [localReplicas, setLocalReplicas] = useState<number | undefined>(2);
  const [sync, setSync] = useState<"async" | "sync">("async");
  const [lbServer, setLbServer] = useState("");
  const [lbLocal, setLbLocal] = useState(true);
  const [lbPort, setLbPort] = useState<number | undefined>(undefined);
  // Optional for databases: a dump to start from, and alerts.
  const [dataImport, setDataImport] = useState("");
  const [alert, setAlert] = useState<AlertDraft>(EMPTY_ALERT);
  const [jobId, setJobId] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const job = useJob(jobId);
  const functions = Object.keys(asObject(draft.functions));

  const choose = (c: OnPremCatalogItem) => {
    setItem(c);
    setRole((resourceType && c.roles.find((r) => roleType(r) === resourceType)) || c.roles[0] || "");
    setPort(undefined);
    setImage("");
    setKey(
      uniqueName(
        c.kind === "runtime"
          ? c.id
          : c.roles[0] === "database"
            ? `${c.id}-db`
            : c.roles[0] === "storage"
              ? "files"
              : c.roles[0] === "secrets"
                ? "secrets"
                : c.roles[0] === "smtp"
                  ? "inbound-mail"
                  : c.id === "kafka"
                    ? "events"
                    : "jobs",
        taken,
      ),
    );
    setVersion("");
    setScale("single");
    setDataImport("");
    setAlert(EMPTY_ALERT);
    setRepOn("servers");
    setLbPort(undefined);
    if (c.kind === "runtime") {
      setTarget(ssh);
      setWhere((w) => (w === "local" ? "ssh" : w));
    }
  };
  useEffect(() => {
    if (initial) choose(initial);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (job.status !== "succeeded" || !item) return;
    api
      .onpremServices()
      .then((s) => {
        const svc = s.services.find((x) => x.key === key);
        if (svc && svc.kind === "service" && alert.on && alert.function === NEW_FUNCTION) {
          // pskit.yml gets the function with the resource; its handler stub is written here.
          api.onpremAlertFunction(alertHandler(key)).then(
            (r) => toast(`Alert function ${key}-alert: handler in ${r.path}`, "ok"),
            (exc: unknown) => toast(errorMessage(exc), "err"),
          );
        }
        if (svc && svc.kind === "service") onCreated(svc, TRIGGER_ROLES.includes(role) ? attach : []);
        else toast(`${item.label} is installed`, "ok");
      })
      .catch((exc: unknown) => toast(errorMessage(exc), "err"));
  }, [job.status]); // eslint-disable-line react-hooks/exhaustive-deps

  const passwordError =
    password && !/^[A-Za-z0-9!#%*+,.:=?@^_~-]{8,128}$/.test(password) ? "8-128 characters: letters, digits and !#%*+,.:=?@^_~-" : null;
  const loginError = login && !/^[A-Za-z][A-Za-z0-9_.-]{2,63}$/.test(login) ? "3-64 characters, starting with a letter" : null;
  const keyError = !NAME_RE.test(key) ? "letters, digits, - and _; start with a letter" : taken.includes(key) ? "already used" : null;
  const repInfo = item?.kind === "service" && role === "database" ? item.replication || null : null;
  const importTypes = item?.kind === "service" ? item.import_types || [] : [];
  const importError =
    dataImport.trim() && importTypes.length && !importTypes.some((t) => dataImport.trim().toLowerCase().endsWith(t)) ? `a ${importTypes.join(", ")} file` : null;
  const alertProblem = item?.kind === "service" && role === "database" ? alertError(alert) : null;
  const replicated = !!repInfo && scale === "replicated";
  const repLocal = replicated && repOn === "local";
  const topologyError = !replicated
    ? null
    : repLocal
      ? !localReplicas || localReplicas < 1 || localReplicas > 9
        ? "1 to 9 replicas"
        : null
      : servers.length < 2
        ? "save at least two servers first (Servers, below): one for the primary, one per replica"
        : !primaryServer
          ? "pick the server that takes the writes"
          : !replicaServers.length
            ? "pick at least one server for a read replica"
            : null;
  const sshError =
    replicated
      ? null
      : where === "cluster"
      ? clusterName
        ? null
        : "pick a cluster (Scaling cluster page)"
      : target.method === "ssh" && savedServer
      ? null
      : target.method === "ssh" && !(ssh.host || "").trim()
      ? "the server's host name or IP"
      : target.method === "ssh" && sshAuth === "key" && !(ssh.identity_file || "").trim()
        ? "the path of the private key, or pick SSH agent / default key"
        : target.method === "ssh" && sshAuth === "password" && !sshPassword && !ssh.password_file
          ? "the SSH password"
          : null;
  const guiPasswordError =
    guiPassword && !/^[A-Za-z0-9!#%*+,.:=?@^_~-]{8,128}$/.test(guiPassword) ? "8-128 characters: letters, digits and !#%*+,.:=?@^_~-" : null;
  const isSmtp = item?.id === "smtp";
  const domainList = domains.split(/[\s,]+/).filter(Boolean);
  const badDomain = domainList.find((d) => !DOMAIN_RE.test(d));
  const domainsError = !isSmtp
    ? null
    : !domainList.length
      ? "the domain mail is sent to, e.g. inbound.example.com"
      : badDomain
        ? `${badDomain} is not a domain name`
        : null;
  const functionsUrlError = isSmtp && functionsUrl.trim() && !/^https?:\/\/\S+$/.test(functionsUrl.trim()) ? "http://host:port of the pskit host" : null;

  const submit = async () => {
    if (!item || keyError || sshError || topologyError || importError || alertProblem || passwordError || loginError || guiPasswordError || domainsError || functionsUrlError) return;
    setSubmitError(null);
    const sshTarget: OnPremTarget = { ...ssh, method: "ssh", auth: sshAuth };
    if (sshAuth !== "key") delete sshTarget.identity_file;
    if (sshAuth === "password" && sshPassword) sshTarget.password = sshPassword;
    if (sshAuth !== "password") delete sshTarget.password_file;
    const chosen: OnPremTarget =
      where === "cluster"
        ? { cluster: clusterName, ...(clusterNode ? { server: clusterNode } : {}) }
        : target.method !== "ssh"
          ? { method: "local" }
          : savedServer
            ? { method: "ssh", server: savedServer }
            : sshTarget;
    const body: JsonObject = { key, service: item.id, target: chosen as unknown as JsonObject };
    if (item.kind === "runtime" && version) body.version = version;
    if (role) body.role = role;
    if (port) body.port = port;
    if (address.trim() && !replicated) body.address = address.trim();
    if (image.trim()) body.image = image.trim();
    if (login.trim()) body.user = login.trim();
    if (password) body.password = password;
    if (bind && !replicated) body.bind = bind;
    if (dataImport.trim() && importTypes.length) body.import = { path: dataImport.trim() };
    if (role === "database") {
      const a = alertBody(alert, key);
      if (a) body.alert = a as JsonObject;
    }
    if (replicated && repInfo) {
      delete body.target;
      const topology: JsonObject = {
        mode: "replicated",
        sync,
        primary: repLocal ? "local" : primaryServer,
        replicas: repLocal ? Array.from({ length: localReplicas || 1 }, () => "local") : replicaServers,
        balancer: !repInfo.balancer ? "" : repLocal ? (lbLocal ? "local" : "") : lbServer,
      };
      if (topology.balancer && lbPort) topology.balancer_port = lbPort;
      body.topology = topology;
    }
    if (item.companion && withGui) {
      body.gui = true;
      body.gui_login = guiLogin;
      if (guiLogin === "password" && guiPassword) body.gui_password = guiPassword;
    }
    if (TRIGGER_ROLES.includes(role)) body.attach = attach;
    if (isSmtp) {
      body.domains = domainList;
      if (functionsUrl.trim()) body.functions_url = functionsUrl.trim();
      if (maxSize) body.max_size_mb = maxSize;
    }
    try {
      setJobId((await api.onpremCreate(body)).job_id);
    } catch (exc) {
      setSubmitError(errorMessage(exc));
    }
  };

  const running = job.status === "running";
  return (
    <Drawer
      open
      title={item ? `Create ${item.label}` : "Create a service"}
      onClose={onClose}
      actions={
        item && (
          <button
            type="button"
            className="btn btn-primary"
            disabled={
              !!keyError ||
              !!sshError ||
              !!topologyError ||
              !!importError ||
              !!alertProblem ||
              !!passwordError ||
              !!loginError ||
              !!guiPasswordError ||
              !!domainsError ||
              !!functionsUrlError ||
              running ||
              job.status === "succeeded"
            }
            onClick={() => void submit()}
          >
            {running ? "Creating…" : job.status === "succeeded" ? "Created" : item.kind === "runtime" ? "Install" : "Create"}
          </button>
        )
      }
    >
      {!item && resourceType && !state.catalog.some((c) => c.kind === "service" && c.roles.some((r) => roleType(r) === resourceType)) && (
        <p className="muted">No one-click service for {resourceType} resources yet; add it as an existing service instead.</p>
      )}
      {!item && (
        <div className="catalog">
          {GROUPS.map((g) => {
            const items = state.catalog.filter(
              (c) => g.match(c) && (!resourceType || (c.kind === "service" && c.roles.some((r) => roleType(r) === resourceType))),
            );
            return (
              items.length > 0 && (
                <div key={g.title} className="catalog-group">
                  <h4>{g.title}</h4>
                  <div className="catalog-grid">
                    {items.map((c) => (
                      <button key={c.id} type="button" className="catalog-card" onClick={() => choose(c)}>
                        <b>{c.label}</b>
                        <span className="muted small">{c.notes || c.image}</span>
                        {c.port && <span className="mono small">port {c.port}</span>}
                        {(c.companion || (c.gui && c.gui.length > 0)) && (
                          <span className="small">web UI: {c.companion || (c.gui || []).join(", ")}</span>
                        )}
                      </button>
                    ))}
                  </div>
                </div>
              )
            );
          })}
        </div>
      )}
      {item && (
        <div className="form">
          <p className="muted small">
            {item.notes}{" "}
            <button type="button" className="btn btn-sm" onClick={() => setItem(null)}>
              Pick another
            </button>
          </p>
          {item.kind === "service" && (
            <FormRow label="Resource key" required error={keyError} help="How handlers and triggers refer to it: resource(&quot;key&quot;).">
              <TextInput mono value={key} onChange={setKey} invalid={!!keyError} />
            </FormRow>
          )}
          {isSmtp && (
            <FormRow
              label="Domains"
              required
              error={domainsError}
              help="Mail to any address at these domains (and their subdomains) runs the functions. Everything else is refused, so it is never an open relay. Already have mailboxes on your root domain (Microsoft 365, Google)? Use a subdomain such as inbound.example.com."
            >
              <TextInput mono value={domains} onChange={setDomains} placeholder="inbound.example.com" invalid={!!domainsError} />
            </FormRow>
          )}
          {item.roles.length > 1 && (
            <FormRow label="Use as">
              <Segmented label="Use as" value={role} onChange={setRole} options={item.roles.map((r) => ({ value: r, label: ROLE_LABEL[r] || r }))} />
            </FormRow>
          )}
          {item.kind === "service" && role === "database" && (
            <FormRow
              label="Scaling"
              help={
                !repInfo
                  ? `${item.label} runs on one server here.`
                  : replicated
                    ? "Horizontal: the primary takes every write, read replicas copy it and serve reads. Add replicas later as reads grow."
                    : "One server holds the database. To scale it up, give that server more CPU and memory."
              }
            >
              <Segmented
                label="Scaling"
                value={replicated ? "replicated" : "single"}
                onChange={(v) => setScale(v as "single" | "replicated")}
                options={[
                  { value: "single", label: "Single server" },
                  { value: "replicated", label: "Primary + read replicas", disabled: !repInfo },
                ]}
              />
            </FormRow>
          )}
          {replicated && repInfo && (
            <ReplicationForm
              item={item}
              info={repInfo}
              servers={servers}
              port={port || item.port || 0}
              repOn={repOn}
              setRepOn={setRepOn}
              primary={primaryServer}
              setPrimary={(v) => {
                setPrimaryServer(v);
                setReplicaServers((r) => r.filter((x) => x !== v));
              }}
              replicas={replicaServers}
              setReplicas={setReplicaServers}
              localReplicas={localReplicas}
              setLocalReplicas={setLocalReplicas}
              sync={sync}
              setSync={setSync}
              lbServer={lbServer}
              setLbServer={setLbServer}
              lbLocal={lbLocal}
              setLbLocal={setLbLocal}
              lbPort={lbPort}
              setLbPort={setLbPort}
              error={topologyError}
            />
          )}
          {!replicated && (
          <FormRow
            label="Where"
            help={
              where === "cluster"
                ? "One server of a scaling cluster runs it (with its data volume), and the function replicas on every server of the cluster reach it at that server's cluster address. Not replicated: one instance, like on a single server."
                : target.method === "ssh"
                ? "Any server you can reach with OpenSSH: the functions' server or a different one. Docker is installed there when missing."
                : "Docker on this machine. Functions deployed elsewhere cannot reach 127.0.0.1; use an SSH server for them."
            }
          >
            <Segmented
              label="Where"
              value={where}
              onChange={(m) => {
                const next = m as "local" | "ssh" | "cluster";
                setWhere(next);
                setTarget(next === "local" ? { method: "local" } : ssh);
              }}
              options={[
                { value: "local", label: "This machine", disabled: item.kind === "runtime" },
                { value: "ssh", label: "One SSH server" },
                // A database scales with replicas (Scaling above), not by running on a function cluster.
                ...(role === "database" && where !== "cluster"
                  ? []
                  : [{ value: "cluster", label: "Scaling cluster", disabled: !clusters.length && !defaultCluster }]),
              ]}
            />
          </FormRow>
          )}
          {!replicated && where === "cluster" && (
            <>
              <FormRow label="Cluster" error={clusterName ? null : sshError} help={!clusters.length ? "Create one on the Scaling cluster page first." : undefined}>
                <EnumSelect
                  value={clusterName}
                  onChange={(v) => {
                    setClusterName(v);
                    setClusterNode("");
                  }}
                  options={[
                    ...(clusterName ? [] : [{ value: "", label: "Pick a cluster…" }]),
                    ...clusters.map((c) => ({ value: c.name, label: `${c.name} (${c.orchestrator_label}, ${c.nodes.length} server${c.nodes.length === 1 ? "" : "s"})` })),
                    ...(clusterName && !cluster ? [{ value: clusterName, label: `${clusterName} (not found)` }] : []),
                  ]}
                />
              </FormRow>
              <FormRow
                label="Server in the cluster"
                help="Auto picks the reachable server with the most free memory that is under every capacity limit, when the job starts. Pick one to keep it next to other services."
              >
                <EnumSelect
                  value={clusterNode}
                  onChange={setClusterNode}
                  options={[
                    { value: "", label: "Auto: the server with the most free memory" },
                    ...(cluster?.nodes || []).map((n) => ({ value: n.server, label: `${n.server} (${n.role}, ${n.address})` })),
                  ]}
                />
              </FormRow>
            </>
          )}
          {!replicated && where === "ssh" && (
            <FormRow label="Server" help="A saved server (Servers below), or a new connection typed here.">
              <EnumSelect
                value={savedServer}
                onChange={setSavedServer}
                options={[{ value: "", label: "New connection…" }, ...servers.map((s) => ({ value: s.name, label: `${s.name} (${s.label})` }))]}
              />
            </FormRow>
          )}
          {!replicated && where === "ssh" && state.default_target_problem && (
            <div className="hint-box">{state.default_target_problem}</div>
          )}
          {item.kind === "runtime" && (item.versions || []).length > 0 && (
            <FormRow label="Version" help={`Default ${(item.versions || [])[0]}. Any version number works (e.g. 1.23.4 for Go).`}>
              <div className="row-gap">
                <Segmented
                  label="Version"
                  value={(item.versions || []).includes(version) ? version : version ? "other" : (item.versions || [])[0]}
                  onChange={(v) => setVersion(v === "other" ? "" : v)}
                  options={(item.versions || []).map((v) => ({ value: v, label: v }))}
                />
                <TextInput mono value={version} placeholder="other version" onChange={setVersion} />
              </div>
            </FormRow>
          )}
          {!replicated && where === "ssh" && !savedServer && (
            <div className="driver-box card card-pad">
              <FormRow label="Host" required error={sshError}>
                <TextInput mono value={ssh.host || ""} placeholder="10.0.0.5" onChange={(v) => setSsh((s) => ({ ...s, host: v }))} />
              </FormRow>
              <FormRow label="User">
                <TextInput mono value={ssh.user || ""} placeholder="ubuntu" onChange={(v) => setSsh((s) => ({ ...s, user: v }))} />
              </FormRow>
              <FormRow label="SSH port">
                <NumberInput integer min={1} max={65535} value={ssh.port} onChange={(v) => setSsh((s) => ({ ...s, port: v }))} />
              </FormRow>
              <FormRow label="Log in with">
                <Segmented
                  label="Log in with"
                  value={sshAuth}
                  onChange={(v) => setSshAuth(v as "key" | "agent" | "password")}
                  options={[
                    { value: "key", label: "Key file (.pem)" },
                    { value: "agent", label: "SSH agent / default key" },
                    { value: "password", label: "Password" },
                  ]}
                />
              </FormRow>
              {sshAuth === "key" && (
                <FormRow label="Private key (.pem)" help="The key file you log in with (AWS .pem, Azure .pem, id_ed25519, ...).">
                  <TextInput mono value={ssh.identity_file || ""} placeholder="~/.ssh/server.pem" onChange={(v) => setSsh((s) => ({ ...s, identity_file: v }))} />
                </FormRow>
              )}
              {sshAuth === "agent" && (
                <p className="muted small">
                  No file: OpenSSH uses your SSH agent, <code className="mono">~/.ssh/id_*</code> and <code className="mono">~/.ssh/config</code>, exactly
                  like <code className="mono">ssh {ssh.user || "user"}@{ssh.host || "host"}</code> in a terminal.
                </p>
              )}
              {sshAuth === "password" && (
                <FormRow
                  label="SSH password"
                  help="Saved in .pskit/ssh/ (out of git, owner-only) and sent with sshpass, which must be installed here (Linux / macOS). On Windows, install a key once instead: pskit resources onprem ssh-key user@host, then pick Key file."
                >
                  <TextInput mono type="password" value={sshPassword} placeholder={ssh.password_file ? "saved: " + ssh.password_file : ""} onChange={setSshPassword} />
                </FormRow>
              )}
              <Toggle checked={!!ssh.sudo} onChange={(b) => setSsh((s) => ({ ...s, sudo: b }))} label="Use sudo (the SSH user is not root and not in the docker group)" />
            </div>
          )}
          {item.kind === "service" && (
            <>
              <FormRow
                label="Port"
                help={
                  isSmtp
                    ? "Other mail servers always connect to 25: keep 25 unless something else uses it (then forward 25 to this port; the DNS guide shows how)."
                    : replicated
                      ? `The database port on every member${repLocal ? " (on this machine: the primary's; each replica takes the next one)" : ""}. Default ${item.port}.`
                      : `Published on the server. Default ${item.port}${item.extra_ports?.length ? ` (also ${item.extra_ports.join(", ")})` : ""}.`
                }
              >
                <NumberInput integer min={1} max={65535} value={port} placeholder={String(item.port || "")} onChange={setPort} />
              </FormRow>
              <div className="driver-box card card-pad">
                <h3>Security</h3>
                {isSmtp ? (
                  <p className="muted small">
                    Receive only: senders do not log in (that is how mail between servers works) and only mail for the domains above is accepted, so nobody can
                    send mail through it. Mail goes to the pskit host with its admin token when the host has one.
                  </p>
                ) : item.auth === false ? (
                  <p className="muted small">
                    {item.label} runs without authentication in this setup. Keep it on 127.0.0.1 (this machine only) or a private network, and open the
                    port only to the servers that need it.
                  </p>
                ) : (
                  <>
                    <FormRow label="User" error={loginError} help={`Created in the service. Default: ${item.default_user || "pskit"}.`}>
                      <TextInput mono value={login} placeholder={item.default_user || "pskit"} onChange={setLogin} invalid={!!loginError} />
                    </FormRow>
                    <FormRow label="Password" error={passwordError} help="Empty: a strong random one. Stored only in the env file and .pskit/, never in pskit.yml.">
                      <div className="row-gap">
                        <TextInput mono type={showPassword ? "text" : "password"} value={password} placeholder="generated" onChange={setPassword} invalid={!!passwordError} />
                        <button type="button" className="btn btn-sm" onClick={() => setPassword(generatePassword())}>
                          Generate
                        </button>
                        <Toggle checked={showPassword} onChange={setShowPassword} label="Show" />
                      </div>
                    </FormRow>
                  </>
                )}
                {replicated ? (
                  <p className="muted small">
                    {repLocal
                      ? "Members listen on 127.0.0.1 and talk to each other on a private Docker network."
                      : "Members listen on the network (0.0.0.0) so replicas reach the primary; the job prints the firewall rules: replicas → primary, load balancer → members, functions → load balancer."}{" "}
                    Replication uses its own user and password, generated and kept in .pskit/.
                  </p>
                ) : (
                <FormRow label="Listen on" help="127.0.0.1: only programs on that machine can connect. 0.0.0.0: other servers too (limit it with the firewall).">
                  <Segmented
                    label="Listen on"
                    value={bind || (target.method === "ssh" ? "0.0.0.0" : "127.0.0.1")}
                    onChange={setBind}
                    options={[
                      { value: "127.0.0.1", label: "This machine only (127.0.0.1)" },
                      { value: "0.0.0.0", label: "Network (0.0.0.0)" },
                    ]}
                  />
                </FormRow>
                )}
              </div>
              {importTypes.length > 0 && (
                <FormRow
                  label="Import data"
                  error={importError}
                  help={`Optional. A dump on this machine (${importTypes.join(", ")}), loaded once it is up${replicated ? ", into the primary before the replicas copy it" : ""}. A pskit backup works too.`}
                >
                  <FilePathInput value={dataImport} onChange={setDataImport} startAt="~" placeholder="none: start empty" title="Pick a dump to import" />
                </FormRow>
              )}
              {role === "database" && (
                <div className="driver-box card card-pad">
                  <h3>Alerts</h3>
                  <AlertFields value={alert} onChange={setAlert} functions={functions} serviceKey={key} replicated={replicated} />
                  {alertProblem && <div className="form-error small">{alertProblem}</div>}
                </div>
              )}
              {(item.companion || (item.gui && item.gui.length > 0)) && (
                <FormRow
                  label="Web UI"
                  help={
                    item.companion
                      ? `${item.companion} runs next to it on a private Docker network, on the same interface as the service.`
                      : "Built in; How to use shows its address and login."
                  }
                >
                  {item.companion ? (
                    <Toggle checked={withGui} onChange={setWithGui} label={`Also start ${item.companion}`} />
                  ) : (
                    <span className="muted small">{(item.gui || []).join(", ")}</span>
                  )}
                </FormRow>
              )}
              {item.companion && withGui && (item.gui_logins || []).includes("none") && (
                <div className="driver-box card card-pad">
                  <FormRow label="Web UI login" help="A password protects the UI on an open port. No login is fine on 127.0.0.1, a private network or behind an SSH tunnel.">
                    <Segmented
                      label="Web UI login"
                      value={guiLogin}
                      onChange={(v) => setGuiLogin(v as "password" | "none")}
                      options={[
                        { value: "password", label: "With password" },
                        { value: "none", label: "Without password" },
                      ]}
                    />
                  </FormRow>
                  {guiLogin === "password" ? (
                    <FormRow label="Web UI password" error={guiPasswordError} help="Empty: generated (shown in How to use and the env file).">
                      <div className="row-gap">
                        <TextInput mono type={showPassword ? "text" : "password"} value={guiPassword} placeholder="generated" onChange={setGuiPassword} invalid={!!guiPasswordError} />
                        <button type="button" className="btn btn-sm" onClick={() => setGuiPassword(generatePassword())}>
                          Generate
                        </button>
                      </div>
                    </FormRow>
                  ) : (
                    (bind || (target.method === "ssh" ? "0.0.0.0" : "127.0.0.1")) !== "127.0.0.1" && (
                      <div className="hint-box">
                        Anyone who can reach the UI's port can use it, and the UI holds the service's credentials. Open the port only to your IP, or keep it closed and use{" "}
                        <code className="mono">pskit resources onprem tunnel {key || "<key>"} --remote-port &lt;ui port&gt;</code>.
                      </div>
                    )
                  )}
                </div>
              )}
              {item.companion && withGui && !(item.gui_logins || []).includes("none") && (
                <p className="muted small">{item.companion} has no login of its own: it asks for the service's user and password.</p>
              )}
              {TRIGGER_ROLES.includes(role) && (
                <FormRow
                  label="Trigger functions"
                  help={
                    isSmtp
                      ? "Each selected function runs for every mail, with from, to, cc, subject, text, html, headers and attachments (an smtp event on this resource)."
                      : "Adds a queue / storage event on resource: key to each selected function."
                  }
                >
                  <div className="check-grid">
                    {functions.map((f) => (
                      <label key={f} className="check">
                        <input type="checkbox" checked={attach.includes(f)} onChange={(e) => setAttach((a) => (e.target.checked ? [...a, f] : a.filter((x) => x !== f)))} />
                        {f}
                      </label>
                    ))}
                    {!functions.length && <span className="muted">No functions yet.</span>}
                  </div>
                </FormRow>
              )}
              <details className="advanced">
                <summary>Advanced</summary>
                {!replicated && (
                  <FormRow label="Address functions use" help="Default: the SSH host, or 127.0.0.1 here. Set a private IP or DNS name if different.">
                    <TextInput mono value={address} onChange={setAddress} placeholder={where === "cluster" ? "the server's cluster address" : target.method === "ssh" ? ssh.host || "" : "127.0.0.1"} />
                  </FormRow>
                )}
                <FormRow label="Docker image">
                  <TextInput mono value={image} onChange={setImage} placeholder={item.image || ""} />
                </FormRow>
                {isSmtp && (
                  <>
                    <FormRow
                      label="pskit host URL"
                      error={functionsUrlError}
                      help="Where the SMTP server sends each mail. Default: the functions' host on the same server (127.0.0.1), on the deploy server, or host.docker.internal here."
                    >
                      <TextInput mono value={functionsUrl} onChange={setFunctionsUrl} placeholder="http://10.0.0.5:8080" invalid={!!functionsUrlError} />
                    </FormRow>
                    <FormRow label="Largest mail (MB)" help="Bigger mail is refused. Default 25.">
                      <NumberInput min={1} max={100} value={maxSize} placeholder="25" onChange={setMaxSize} />
                    </FormRow>
                  </>
                )}
              </details>
            </>
          )}
          {submitError && <div className="form-error">{submitError}</div>}
          {jobId && <JobConsole job={job} />}
        </div>
      )}
    </Drawer>
  );
}

const BACKUP_FOLDER = "pskit.studio.backup-folder";

/** Where a backup goes: .pskit/backups (default) or a folder picked on this machine (remembered). */
function BackupDialog({ svc, onClose, onStart }: { svc: OnPremService; onClose: () => void; onStart: (folder: string) => void }) {
  const [folder, setFolder] = useState(() => window.localStorage.getItem(BACKUP_FOLDER) || "");
  return (
    <Drawer
      open
      title={`Back up ${svc.key}`}
      onClose={onClose}
      actions={
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => {
            window.localStorage.setItem(BACKUP_FOLDER, folder.trim());
            onStart(folder.trim());
          }}
        >
          Back up now
        </button>
      }
    >
      <div className="form">
        <p className="muted small">
          Streams a dump out of {svc.service} on {svc.target_label}
          {svc.topology ? " (from the primary)" : ""} into a file named <code className="mono">{svc.key}-&lt;time&gt;</code>. Import it into a new database
          later with <b>Import data</b> when you create one.
        </p>
        <FormRow label="Save to folder" help="Empty: .pskit/backups in the project. Browse… opens any folder on this machine.">
          <FilePathInput folder value={folder} onChange={setFolder} placeholder=".pskit/backups" title="Folder for the backup" />
        </FormRow>
      </div>
    </Drawer>
  );
}

function generatePassword(): string {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789_-.";
  const bytes = new Uint32Array(24);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => chars[b % chars.length]).join("");
}

/** Connect to a service from any program: details, Python / Node.js clients, terminal, security. */
export function ServiceUsageDrawer({ serviceKey, onClose }: { serviceKey: string; onClose: () => void }) {
  const [doc, setDoc] = useState<string | null>(null);
  const [reveal, setReveal] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setError(null);
    api
      .onpremUsage(serviceKey, reveal)
      .then((d) => setDoc(d.markdown))
      .catch((exc: unknown) => setError(errorMessage(exc)));
  }, [serviceKey, reveal]);
  return (
    <Drawer
      open
      title={`How to use ${serviceKey}`}
      onClose={onClose}
      actions={
        doc ? (
          <button type="button" className="btn" onClick={() => void navigator.clipboard?.writeText(doc)}>
            Copy guide
          </button>
        ) : undefined
      }
    >
      <div className="row-gap">
        <Toggle checked={reveal} onChange={setReveal} label="Show passwords and URLs" />
        <span className="muted small">
          Terminal: <code className="mono">pskit resources onprem usage {serviceKey}</code>
        </span>
      </div>
      {error && <div className="form-error">{error}</div>}
      {!doc && !error && <p className="muted">Loading…</p>}
      {doc && <Markdown text={doc} />}
    </Drawer>
  );
}

function DetailsDrawer({ serviceKey, onClose }: { serviceKey: string; onClose: () => void }) {
  const [info, setInfo] = useState<OnPremService | null>(null);
  const [alertSettings, setAlertSettings] = useState<OnPremAlert | null>(null);
  const { draft } = useStudio();
  const projectFunctions = Object.keys(asObject(draft.functions));
  const [reveal, setReveal] = useState(false);
  const [logs, setLogs] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [guiJob, setGuiJob] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const job = useJob(guiJob);
  useEffect(() => {
    setError(null);
    api
      .onpremStatus(serviceKey, reveal)
      .then(setInfo)
      .catch((exc: unknown) => setError(errorMessage(exc)));
  }, [serviceKey, reveal, attempt]);
  useEffect(() => {
    if (job.status === "succeeded" || job.status === "failed") setAttempt((a) => a + 1);
  }, [job.status]);
  const links = Array.isArray(info?.gui) ? info.gui : [];
  const hasCompanion = links.some((g) => g.kind === "companion");
  const [addLogin, setAddLogin] = useState<"password" | "none">("password");
  const startGui = async (action: "add" | "remove" | "check") => {
    try {
      const started =
        action === "remove" ? api.onpremGuiRemove(serviceKey) : action === "check" ? api.onpremGuiCheck(serviceKey) : api.onpremGui(serviceKey, { login: addLogin });
      setGuiJob((await started).job_id);
    } catch (exc) {
      setError(errorMessage(exc));
    }
  };
  const ok = info?.state === "running" || info?.state === "installed";
  return (
    <Drawer open title={`Service ${serviceKey}`} onClose={onClose}>
      {error && <div className="form-error">{error}</div>}
      {!info && !error && <p className="muted">Checking…</p>}
      {info && (
        <div className="form">
          <p>
            <span className={`badge ${ok ? (info.ready === false ? "badge-warn" : "badge-ok") : "badge-err"}`}>
              {info.state}
              {info.ready === false ? " · not ready" : info.ready ? " · ready" : ""}
            </span>{" "}
            <span className="muted small">
              {info.service} on {info.target_label}
              {info.started_at ? ` · started ${info.started_at.slice(0, 19).replace("T", " ")}` : ""}
            </span>
          </p>
          {info.error && <div className="form-error">{info.error}</div>}
          {info.reachable_from_here === false && (
            <div className="hint-box">
              This machine cannot reach {info.address}:{info.port} (the server's firewall probably blocks it). Scripts here would time out. Run{" "}
              <code className="mono">pskit resources onprem tunnel {serviceKey}</code> to reach it through SSH, open the port to your IP, or go through
              the pskit host with the pskit client (<b>Resources → How to use</b> on the resource, section 7).
            </div>
          )}
          {info.port && (
            <FormRow label="Endpoint">
              <code className="mono">
                {info.address}:{info.port}
              </code>
            </FormRow>
          )}
          {info.topology && <ReplicasPanel info={info} onChanged={() => setAttempt((a) => a + 1)} />}
          {info.kind === "service" && info.container && <ServiceMonitor serviceKey={serviceKey} alert={alertSettings} />}
          {info.kind === "service" && info.container && (
            <AlertsPanel serviceKey={serviceKey} functions={projectFunctions} replicated={!!info.topology} onLoaded={setAlertSettings} />
          )}
          {(links.length > 0 || info.companion) && (
            <FormRow label="Web UI" help="Does not open? Check web UI tests the container, the port, the server and this machine, and names the fix (firewall / NSG, bind, tunnel).">
              <div className="stack-xs">
                {links.map((g) => (
                  <div key={g.url} className="row-gap wrap">
                    <a className="btn btn-sm btn-primary" href={g.url} target="_blank" rel="noreferrer noopener">
                      Open {g.label}
                    </a>
                    <code className="mono small">{g.url}</code>
                    <span className="muted small">login: {g.login}</span>
                  </div>
                ))}
                <div className="row-gap wrap">
                  {links.length > 0 && (
                    <button type="button" className="btn btn-sm" disabled={job.status === "running"} onClick={() => void startGui("check")}>
                      Check web UI
                    </button>
                  )}
                  {info.companion &&
                    (!hasCompanion ? (
                      <>
                        {(info.gui_logins || []).includes("none") && (
                          <Segmented
                            label="Login"
                            value={addLogin}
                            onChange={(v) => setAddLogin(v as "password" | "none")}
                            options={[
                              { value: "password", label: "With password" },
                              { value: "none", label: "Without password" },
                            ]}
                          />
                        )}
                        <button type="button" className="btn btn-sm" disabled={job.status === "running"} onClick={() => void startGui("add")}>
                          Add web UI
                        </button>
                      </>
                    ) : (
                      <button type="button" className="btn btn-sm btn-danger" disabled={job.status === "running"} onClick={() => void startGui("remove")}>
                        Remove web UI
                      </button>
                    ))}
                </div>
                {guiJob && <JobConsole job={job} />}
              </div>
            </FormRow>
          )}
          {info.env && Object.keys(info.env).length > 0 && (
            <FormRow label={`Credentials (${info.env_file})`} help="Handlers and drivers read these variables; the host loads the file at start.">
              <div className="stack-xs">
                {Object.entries(info.env).map(([k, v]) => (
                  <code key={k} className="mono small">
                    {k}={v}
                  </code>
                ))}
                <Toggle checked={reveal} onChange={setReveal} label="Show values" />
              </div>
            </FormRow>
          )}
          {info.resource && (
            <FormRow label="Resource in pskit.yml">
              <pre className="md-code">{JSON.stringify(info.resource, null, 2)}</pre>
            </FormRow>
          )}
          {info.backups && info.backups.length > 0 && (
            <FormRow label="Backups">
              <ul className="small">
                {info.backups
                  .slice()
                  .reverse()
                  .map((b) => (
                    <li key={b.path} className="mono">
                      {b.path} ({b.size} bytes, {b.at})
                    </li>
                  ))}
              </ul>
            </FormRow>
          )}
          {info.container && (
            <FormRow label="Container logs">
              <div className="stack-xs">
                <button type="button" className="btn btn-sm" onClick={() => api.onpremLogs(serviceKey).then((r) => setLogs(r.text)).catch((exc: unknown) => setError(errorMessage(exc)))}>
                  {logs === null ? "Show logs" : "Refresh"}
                </button>
                {logs !== null && <pre className="md-code console-log">{logs || "(empty)"}</pre>}
              </div>
            </FormRow>
          )}
        </div>
      )}
    </Drawer>
  );
}
