import { useEffect, useId, useState, type ReactNode } from "react";
import { api, errorMessage } from "../api";
import { useConfirm } from "../components/Feedback";
import { useJob } from "../jobs";
import type { HanaCard, JsonObject, OnPremServer } from "../types";

/** Hana's face: a friendly AI avatar drawn in SVG (no image files: studio is a single HTML page). */
export function HanaAvatar({
  size = 32,
  thinking = false,
}: {
  size?: number;
  thinking?: boolean;
}) {
  const id = useId().replace(/:/g, "");
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      role="img"
      aria-label="Hana"
      className={thinking ? "hana-avatar thinking" : "hana-avatar"}
    >
      <defs>
        <linearGradient id={`hg-${id}`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#6d5dfc" />
          <stop offset="0.55" stopColor="#a34bf0" />
          <stop offset="1" stopColor="#f0569b" />
        </linearGradient>
        <radialGradient id={`hs-${id}`} cx="0.3" cy="0.25" r="0.8">
          <stop offset="0" stopColor="#ffffff" stopOpacity="0.45" />
          <stop offset="0.6" stopColor="#ffffff" stopOpacity="0" />
        </radialGradient>
      </defs>
      <circle cx="32" cy="32" r="30" fill={`url(#hg-${id})`} />
      <circle cx="32" cy="32" r="30" fill={`url(#hs-${id})`} />
      {/* antenna */}
      <line
        x1="32"
        y1="9"
        x2="32"
        y2="15"
        stroke="#fff"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
      <circle className="hana-antenna" cx="32" cy="8" r="3" fill="#ffe27a" />
      {/* face plate */}
      <rect
        x="13"
        y="17"
        width="38"
        height="30"
        rx="13"
        fill="#ffffff"
        fillOpacity="0.95"
      />
      {/* eyes */}
      <g className="hana-eyes" fill="#3b2a8f">
        <rect x="21" y="25" width="7" height="9" rx="3.5" />
        <rect x="36" y="25" width="7" height="9" rx="3.5" />
      </g>
      {/* cheeks + smile */}
      <circle cx="19.5" cy="37" r="2.4" fill="#f0569b" fillOpacity="0.35" />
      <circle cx="44.5" cy="37" r="2.4" fill="#f0569b" fillOpacity="0.35" />
      <path
        d="M26 38.5 Q32 43.5 38 38.5"
        stroke="#3b2a8f"
        strokeWidth="2.6"
        fill="none"
        strokeLinecap="round"
      />
      {/* sparkle */}
      <path
        d="M52 11 l1.6 3.8 3.8 1.6 -3.8 1.6 -1.6 3.8 -1.6 -3.8 -3.8 -1.6 3.8 -1.6z"
        fill="#fff"
      />
    </svg>
  );
}

type Note = (text: string) => Promise<void>;

export function ActionCard({
  card,
  onNote,
  onChanged,
}: {
  card: HanaCard;
  onNote: Note;
  onChanged: () => Promise<void>;
}) {
  // a name the user asked for is taken: say so above the card (the card already holds a free name)
  const conflict =
    "conflict" in card && card.kind !== "resource" ? card.conflict : "";
  if (conflict) {
    return (
      <>
        <div className="hana-note info">{conflict}</div>
        <CardBody card={card} onNote={onNote} onChanged={onChanged} />
      </>
    );
  }
  return <CardBody card={card} onNote={onNote} onChanged={onChanged} />;
}

function CardBody({
  card,
  onNote,
  onChanged,
}: {
  card: HanaCard;
  onNote: Note;
  onChanged: () => Promise<void>;
}) {
  switch (card.kind) {
    case "separate":
      return <SeparateCard card={card} onNote={onNote} onChanged={onChanged} />;
    case "server":
      return <ServerCard card={card} onNote={onNote} />;
    case "service":
      return <ServiceCard card={card} onNote={onNote} />;
    case "server-remove":
      return <ServerRemoveCard card={card} onNote={onNote} />;
    case "service-remove":
      return <ServiceRemoveCard card={card} onNote={onNote} />;
    case "item-remove":
      return (
        <ItemRemoveCard card={card} onNote={onNote} onChanged={onChanged} />
      );
    case "cluster":
      return <ClusterCard card={card} onNote={onNote} />;
    case "balancer":
      return <BalancerCard card={card} onNote={onNote} />;
    case "deploy":
      return <DeployCard card={card} onNote={onNote} />;
    case "workflow":
      return <WorkflowCard card={card} onNote={onNote} onChanged={onChanged} />;
    case "functions":
      return (
        <FunctionsCard card={card} onNote={onNote} onChanged={onChanged} />
      );
    case "code":
      return <CodeCard card={card} onNote={onNote} onChanged={onChanged} />;
    case "resource":
      return <ResourceCard card={card} onNote={onNote} onChanged={onChanged} />;
  }
}

/** Removes a function / workflow / resource completely: the pskit.yml entry and (for a function) its handler code. */
function ItemRemoveCard({
  card,
  onNote,
  onChanged,
}: {
  card: Extract<HanaCard, { kind: "item-remove" }>;
  onNote: Note;
  onChanged: () => Promise<void>;
}) {
  const code = card.code;
  const canDeleteCode = !!code && code.action !== "keep";
  const [deleteCode, setDeleteCode] = useState(canDeleteCode);
  const [state, setState] = useState<"idle" | "busy" | "ok" | "err" | "kept">(
    "idle",
  );
  const [message, setMessage] = useState("");
  const what =
    code?.action === "delete-file"
      ? `delete ${code.file}`
      : code?.action === "delete-function"
        ? `remove ${code.handler.split(".").pop()}() from ${code.file}`
        : "";
  const remove = async () => {
    setState("busy");
    try {
      const r = await api.hanaRemoveItem(card.item_kind, card.name, deleteCode);
      setState("ok");
      const codeText =
        r.code === "deleted"
          ? `; deleted ${code?.file}`
          : r.code === "function removed"
            ? `; removed its handler from ${code?.file}`
            : "";
      setMessage(`Removed ${card.yml} from pskit.yml${codeText}.`);
      await onNote(
        `Removed the ${card.item_kind} **${card.name}**: ${card.yml} from pskit.yml${codeText} (pskit.yml backed up in .pskit/studio/backups/).`,
      );
      await onChanged();
    } catch (exc) {
      setState("err");
      setMessage(errorMessage(exc));
    }
  };
  return (
    <div className="hana-card hana-action danger">
      <div className="hana-card-title">
        Remove {card.item_kind} {card.name}
      </div>
      <ul className="hana-steps">
        <li>
          <code className="mono">{card.yml}</code> from pskit.yml (backed up
          first)
        </li>
        {code && code.action === "keep" && (
          <li className="muted">
            Code in <code className="mono">{code.file}</code> stays: {code.why}
          </li>
        )}
      </ul>
      {card.warnings.map((w) => (
        <div key={w} className="hana-note info">
          {w}
        </div>
      ))}
      {canDeleteCode && state !== "ok" && (
        <label className="hana-check">
          <input
            type="checkbox"
            checked={deleteCode}
            onChange={(e) => setDeleteCode(e.target.checked)}
          />{" "}
          Also {what}
        </label>
      )}
      {message && (
        <div className={`hana-note ${state === "err" ? "err" : "ok"}`}>
          {message}
        </div>
      )}
      {state === "kept" && <div className="hana-note">Kept.</div>}
      {(state === "idle" || state === "err" || state === "busy") && (
        <div className="hana-actions">
          <button
            type="button"
            className="btn btn-danger btn-sm"
            disabled={state === "busy"}
            onClick={() => void remove()}
          >
            {state === "busy" ? "Removing…" : `Remove ${card.name}`}
          </button>
          <button
            type="button"
            className="btn btn-sm"
            disabled={state === "busy"}
            onClick={() => setState("kept")}
          >
            Keep it
          </button>
        </div>
      )}
    </div>
  );
}

const SERVER_NAME_RE = /^[A-Za-z][A-Za-z0-9_.-]{0,62}$/;
const pathError = (value: string) =>
  value.trim() && !/^\/[A-Za-z0-9._/-]*$/.test(value.trim())
    ? "an absolute Linux path, e.g. /srv/pskit"
    : "";

function Field({
  label,
  focus,
  wide,
  children,
}: {
  label: string;
  focus?: boolean;
  wide?: boolean;
  children: ReactNode;
}) {
  return (
    <label className={`${wide ? "wide " : ""}${focus ? "focus" : ""}`}>
      <span>{label}</span>
      {children}
    </label>
  );
}

function ServerCard({
  card,
  onNote,
}: {
  card: Extract<HanaCard, { kind: "server" }>;
  onNote: Note;
}) {
  const edit = card.mode === "edit";
  const focus = new Set(card.focus || []);
  const [name, setName] = useState(card.name);
  const [host, setHost] = useState(card.host);
  const [user, setUser] = useState(card.user || "ubuntu");
  const [port, setPort] = useState(String(card.port || 22));
  const [pem, setPem] = useState(card.identity_file);
  const [home, setHome] = useState(card.home || "");
  const [dataDir, setDataDir] = useState(card.data_dir || "");
  const [bind, setBind] = useState(card.bind || "");
  const [auth, setAuth] = useState<"key" | "agent" | "password">(
    card.auth === "password" || card.auth === "agent" ? card.auth : "key",
  );
  const [password, setPassword] = useState("");
  const [sudo, setSudo] = useState(!!card.sudo);
  const [description, setDescription] = useState(card.description || "");
  const optional = ["home", "data_dir", "bind", "description", "sudo"];
  const [more, setMore] = useState(
    edit ||
      !!(
        card.home ||
        card.data_dir ||
        card.bind ||
        card.description ||
        card.sudo
      ) ||
      optional.some((f) => focus.has(f)),
  );
  const [state, setState] = useState<"idle" | "busy" | "ok" | "err">("idle");
  const [message, setMessage] = useState("");

  // the same checks as the Servers form
  const errors: Record<string, string> = {
    name: !SERVER_NAME_RE.test(name.trim())
      ? "start with a letter; letters, digits, _ . -"
      : "",
    host: !host.trim() ? "host name or IP" : "",
    auth:
      auth === "password" && !password && !card.has_password
        ? "type the SSH password here"
        : "",
    pem:
      auth === "key" && !pem.trim()
        ? "the key file's path, or pick SSH agent"
        : "",
    home: pathError(home),
    data_dir: pathError(dataDir),
    bind:
      bind.trim() && !/^(\d{1,3}\.){3}\d{1,3}$/.test(bind.trim())
        ? "an IPv4 address: 0.0.0.0, 127.0.0.1 or one of its IPs"
        : "",
  };
  const firstError = Object.values(errors).find(Boolean) || "";

  const save = async () => {
    setState("busy");
    setMessage("Saving…");
    const target: JsonObject = {
      host: host.trim(),
      user: user.trim() || "root",
      port: Number(port) || 22,
      sudo,
      auth,
    };
    if (auth === "key" && pem.trim()) target.identity_file = pem.trim();
    if (auth === "password" && password) target.password = password;
    target.home = home.trim();
    target.data_dir = dataDir.trim();
    target.bind = bind.trim();
    try {
      await api.onpremServerSave(name.trim(), target, description.trim());
    } catch (exc) {
      setState("err");
      setMessage(errorMessage(exc));
      return;
    }
    const folders = [
      home.trim() && `home ${home.trim()}`,
      dataDir.trim() && `data ${dataDir.trim()}`,
    ]
      .filter(Boolean)
      .join(", ");
    const what = `${edit ? "Updated" : "Saved"} server **${name.trim()}** (${user.trim()}@${host.trim()}:${port}${folders ? `; ${folders}` : ""})`;
    setMessage("Saved. Testing the SSH login…");
    try {
      const test = await api.onpremServerTest(name.trim());
      const facts = test.facts
        ? Object.entries(test.facts)
            .map(([k, v]) => `${k}: ${v}`)
            .join(", ")
        : "";
      if (test.ok) {
        setState("ok");
        setMessage(`Saved and reachable${facts ? ` (${facts})` : ""}.`);
        await onNote(`${what}. SSH test passed${facts ? `: ${facts}` : ""}.`);
      } else {
        setState("err");
        setMessage(
          `Saved, but the SSH test failed: ${test.error || "unknown error"}`,
        );
        await onNote(
          `${what}, but the SSH test failed: ${test.error || "unknown error"}`,
        );
      }
    } catch (exc) {
      setState("err");
      setMessage(`Saved, but the test could not run: ${errorMessage(exc)}`);
    }
  };

  const done = state === "ok";
  const err = (key: string) =>
    errors[key] ? <em className="hana-err">{errors[key]}</em> : null;
  return (
    <div className="hana-card hana-action">
      <div className="hana-card-title">
        {edit ? `Update server ${card.name}` : "Add server"}
      </div>
      <div className="hana-form">
        <Field label="Name" focus={!!errors.name}>
          <input
            className="input input-sm mono"
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={done || edit}
          />
          {err("name")}
        </Field>
        <Field label="IP or host" focus={focus.has("host") || !!errors.host}>
          <input
            className="input input-sm mono"
            value={host}
            onChange={(e) => setHost(e.target.value)}
            placeholder="e.g. 203.0.113.10"
            disabled={done}
          />
        </Field>
        <Field label="SSH user" focus={focus.has("user")}>
          <input
            className="input input-sm mono"
            value={user}
            onChange={(e) => setUser(e.target.value)}
            placeholder="e.g. ubuntu"
            disabled={done}
          />
        </Field>
        <Field label="SSH port" focus={focus.has("port")}>
          <input
            className="input input-sm mono"
            value={port}
            onChange={(e) => setPort(e.target.value.replace(/\D/g, ""))}
            disabled={done}
          />
        </Field>
        <Field
          label="Log in with"
          wide
          focus={focus.has("auth") || !!errors.auth}
        >
          <div className="hana-seg" role="radiogroup" aria-label="Log in with">
            {(
              [
                ["key", "Key file (.pem)"],
                ["agent", "SSH agent / default key"],
                ["password", "Password"],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                role="radio"
                aria-checked={auth === value}
                className={auth === value ? "on" : ""}
                onClick={() => setAuth(value)}
                disabled={done}
              >
                {label}
              </button>
            ))}
          </div>
        </Field>
        {auth === "key" && (
          <Field
            label="Key file (.pem) on this machine"
            wide
            focus={focus.has("identity_file") || !pem}
          >
            <input
              className="input input-sm mono"
              value={pem}
              onChange={(e) => setPem(e.target.value)}
              placeholder="e.g. C:\keys\server.pem"
              disabled={done}
            />
          </Field>
        )}
        {auth === "password" && (
          <Field
            label="SSH password (saved in .pskit/ssh/, owner-only)"
            wide
            focus
          >
            <input
              className="input input-sm mono"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={
                card.has_password
                  ? "unchanged"
                  : "type it here, not in the chat"
              }
              disabled={done}
            />
            {err("auth")}
          </Field>
        )}
        <label
          className={`hana-check wide${focus.has("sudo") ? " focus" : ""}`}
        >
          <input
            type="checkbox"
            checked={sudo}
            onChange={(e) => setSudo(e.target.checked)}
            disabled={done}
          />{" "}
          Use sudo (the user isn&apos;t root and not in the docker group)
        </label>
        {more ? (
          <>
            <Field
              label="Home folder on the server"
              focus={focus.has("home") || !!errors.home}
            >
              <input
                className="input input-sm mono"
                value={home}
                onChange={(e) => setHome(e.target.value)}
                placeholder="default /opt/pskit"
                disabled={done}
              />
              {err("home")}
            </Field>
            <Field
              label="Data folder on the server"
              focus={focus.has("data_dir") || !!errors.data_dir}
            >
              <input
                className="input input-sm mono"
                value={dataDir}
                onChange={(e) => setDataDir(e.target.value)}
                placeholder="e.g. /data/pskit"
                disabled={done}
              />
              {err("data_dir")}
            </Field>
            <Field
              label="Listen address (bind)"
              focus={focus.has("bind") || !!errors.bind}
            >
              <input
                className="input input-sm mono"
                value={bind}
                onChange={(e) => setBind(e.target.value)}
                placeholder="0.0.0.0 / 10.0.0.5"
                disabled={done}
              />
              {err("bind")}
            </Field>
            <Field label="Description" focus={focus.has("description")}>
              <input
                className="input input-sm"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="optional note"
                disabled={done}
              />
            </Field>
          </>
        ) : (
          <button
            type="button"
            className="link-btn small wide-btn"
            onClick={() => setMore(true)}
          >
            + Home folder, data folder, listen address, description
          </button>
        )}
      </div>
      {message && (
        <div
          className={`hana-note ${state === "err" ? "err" : state === "ok" ? "ok" : "info"}`}
        >
          {message}
        </div>
      )}
      {!done && (
        <div className="hana-actions">
          <button
            type="button"
            className="btn btn-primary btn-sm"
            disabled={!!firstError || state === "busy"}
            onClick={() => void save()}
          >
            {state === "busy" ? "Working…" : "Save & test"}
          </button>
          {firstError && (
            <span className="muted small">Fill in the highlighted fields.</span>
          )}
        </div>
      )}
    </div>
  );
}

function ServerRemoveCard({
  card,
  onNote,
}: {
  card: Extract<HanaCard, { kind: "server-remove" }>;
  onNote: Note;
}) {
  const [state, setState] = useState<"idle" | "busy" | "ok" | "err" | "kept">(
    "idle",
  );
  const [message, setMessage] = useState("");
  const remove = async () => {
    setState("busy");
    try {
      const r = await api.onpremServerRemove(card.name);
      const warn =
        r.warnings && r.warnings.length
          ? ` Still named in: ${r.warnings.join("; ")}.`
          : "";
      setState("ok");
      setMessage(`Removed.${warn}`);
      await onNote(
        `Removed saved server **${card.name}** (${card.label}).${warn}`,
      );
    } catch (exc) {
      setState("err");
      setMessage(errorMessage(exc));
    }
  };
  return (
    <div className="hana-card hana-action danger">
      <div className="hana-card-title">Remove server {card.name}</div>
      <div className="muted small mono">{card.label}</div>
      {message && (
        <div className={`hana-note ${state === "err" ? "err" : "ok"}`}>
          {message}
        </div>
      )}
      {state === "kept" && <div className="hana-note">Kept.</div>}
      {(state === "idle" || state === "err" || state === "busy") && (
        <div className="hana-actions">
          <button
            type="button"
            className="btn btn-danger btn-sm"
            disabled={state === "busy"}
            onClick={() => void remove()}
          >
            {state === "busy" ? "Removing…" : `Remove ${card.name}`}
          </button>
          <button
            type="button"
            className="btn btn-sm"
            disabled={state === "busy"}
            onClick={() => setState("kept")}
          >
            Keep it
          </button>
        </div>
      )}
    </div>
  );
}

function ServiceRemoveCard({
  card,
  onNote,
}: {
  card: Extract<HanaCard, { kind: "service-remove" }>;
  onNote: Note;
}) {
  const [deleteData, setDeleteData] = useState(false);
  const [typed, setTyped] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [kept, setKept] = useState(false);
  const job = useJob(jobId);
  useEffect(() => {
    if (job.status === "succeeded") {
      void onNote(
        `Removed on-prem service **${card.key}** (${card.service})${deleteData ? " and its data" : "; its data is kept"}.`,
      );
    } else if (job.status === "failed") {
      void onNote(
        `Removing ${card.key} failed: ${job.lines
          .slice(-2)
          .map((l) => l.text)
          .join(" ")}`,
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job.status]);
  const remove = async () => {
    setError("");
    try {
      setJobId((await api.onpremRemove(card.key, deleteData)).job_id);
    } catch (exc) {
      setError(errorMessage(exc));
    }
  };
  return (
    <div className="hana-card hana-action danger">
      <div className="hana-card-title">Remove service {card.key}</div>
      <div className="muted small">
        {card.service}
        {card.where ? ` on ${card.where}` : ""}
      </div>
      {!jobId && !kept && (
        <>
          <label className="hana-check">
            <input
              type="checkbox"
              checked={deleteData}
              onChange={(e) => setDeleteData(e.target.checked)}
            />{" "}
            Also delete its data (can&apos;t be undone)
          </label>
          {deleteData && (
            <input
              className="input input-sm mono"
              placeholder={`type ${card.key} to confirm`}
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
            />
          )}
          <div className="hana-actions">
            <button
              type="button"
              className="btn btn-danger btn-sm"
              disabled={deleteData && typed !== card.key}
              onClick={() => void remove()}
            >
              Remove {card.key}
            </button>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => setKept(true)}
            >
              Keep it
            </button>
          </div>
        </>
      )}
      {kept && <div className="hana-note">Kept.</div>}
      {error && <div className="hana-note err">{error}</div>}
      {jobId && (
        <pre className="hana-pre hana-log">
          {job.lines.map((l) => l.text).join("\n") || "starting…"}
          {job.status === "running"
            ? ""
            : job.status === "failed"
              ? "\n\nFailed."
              : "\n\nDone."}
        </pre>
      )}
    </div>
  );
}

interface CatalogItem {
  id: string;
  label: string;
  roles: string[];
  kind: string;
  port: number;
  replication?: {
    method: string;
    balancer: string;
    balancer_port: number;
    async: string;
    sync: string;
  } | null;
}

function ServiceCard({
  card,
  onNote,
}: {
  card: Extract<HanaCard, { kind: "service" }>;
  onNote: Note;
}) {
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [servers, setServers] = useState<OnPremServer[]>([]);
  const [service, setService] = useState(card.service);
  const [key, setKey] = useState(card.key);
  const [role, setRole] = useState(card.role);
  // where it runs: "" = this machine, "server:NAME" = a saved server, "cluster:NAME" = a scaling cluster
  const [where, setWhere] = useState(
    card.cluster
      ? `cluster:${card.cluster}`
      : card.server
        ? `server:${card.server}`
        : "",
  );
  const [clusters, setClusters] = useState<string[]>([]);
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const job = useJob(jobId);
  // Scaling (databases): one server, or a primary + read replicas (+ the engine's load balancer)
  const [scale, setScale] = useState<"single" | "replicated">(
    card.scaling === "replicated" ? "replicated" : "single",
  );
  const [primary, setPrimary] = useState(card.primary || card.server || "");
  const [replicas, setReplicas] = useState<string[]>(card.replicas || []);
  const [sync, setSync] = useState<"async" | "sync">(
    card.sync === "sync" ? "sync" : "async",
  );
  const [lbServer, setLbServer] = useState(card.primary || card.server || "");
  const server = where.startsWith("server:") ? where.slice(7) : "";
  const cluster = where.startsWith("cluster:") ? where.slice(8) : "";
  const whereLabel = cluster
    ? `scaling cluster ${cluster}`
    : server || "this machine";

  useEffect(() => {
    api.onpremServices().then(
      (s) =>
        setCatalog(
          (s.catalog as unknown as CatalogItem[]).filter(
            (c) => c.kind === "service",
          ),
        ),
      () => undefined,
    );
    api.onpremServers().then(
      (s) => setServers(s.servers),
      () => undefined,
    );
    api.clusters().then(
      (c) => setClusters(c.clusters.map((x) => x.name)),
      () => undefined,
    );
  }, []);

  const spec = catalog.find((c) => c.id === service);
  const rep = role === "database" ? spec?.replication || null : null;
  const replicated = !!rep && scale === "replicated";
  const scaleError = !replicated
    ? ""
    : servers.length < 2
      ? "save at least two servers first: one for the primary, one per replica"
      : !primary
        ? "pick the primary"
        : !replicas.length
          ? "pick at least one replica server"
          : "";
  useEffect(() => {
    if (spec && !spec.roles.includes(role)) setRole(spec.roles[0]);
  }, [spec, role]);

  useEffect(() => {
    if (job.status === "succeeded") {
      const placed = replicated
        ? `primary ${primary}, replicas ${replicas.join(", ")}${rep?.balancer && lbServer ? `, ${rep.balancer} on ${lbServer}` : ""}`
        : whereLabel;
      void onNote(
        `Created on-prem service **${key}** (${spec?.label || service}, ${role}) on ${placed}. It is on the Resources > On-prem services page.`,
      );
    } else if (job.status === "failed") {
      const last = job.lines
        .slice(-3)
        .map((l) => l.text)
        .join(" ");
      void onNote(
        `Creating ${key} (${service}) on ${whereLabel} failed: ${last}`,
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job.status]);

  const create = async () => {
    setError("");
    const body: JsonObject = {
      key: key.trim(),
      service,
      role,
      target: cluster
        ? { cluster }
        : server
          ? { method: "ssh", server }
          : { method: "local" },
    };
    if (replicated && rep) {
      delete body.target;
      body.topology = {
        mode: "replicated",
        sync,
        primary,
        replicas,
        balancer: rep.balancer ? lbServer : "",
        ...(rep.balancer && lbServer && rep.balancer_port
          ? { balancer_port: rep.balancer_port }
          : {}),
      };
    }
    try {
      setJobId((await api.onpremCreate(body)).job_id);
    } catch (exc) {
      setError(errorMessage(exc));
    }
  };

  const busy = job.status === "running";
  const done = job.status === "succeeded";
  return (
    <div className="hana-card hana-action">
      <div className="hana-card-title">Create on-prem service</div>
      <div className="hana-form">
        <label>
          <span>Service</span>
          <select
            className="select select-sm"
            value={service}
            onChange={(e) => setService(e.target.value)}
            disabled={busy || done}
          >
            {(catalog.length
              ? catalog
              : [
                  {
                    id: card.service,
                    label: card.service,
                    roles: [card.role],
                    kind: "service",
                    port: 0,
                  },
                ]
            ).map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Name (key)</span>
          <input
            className="input input-sm mono"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            disabled={busy || done}
          />
        </label>
        <label>
          <span>Used as</span>
          <select
            className="select select-sm"
            value={role}
            onChange={(e) => setRole(e.target.value)}
            disabled={busy || done}
          >
            {(spec?.roles || [role]).map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </label>
        {rep && (
          <label className="wide">
            <span>Scaling</span>
            <div className="hana-seg" role="radiogroup" aria-label="Scaling">
              {(
                [
                  ["single", "Single server"],
                  ["replicated", "Primary + read replicas"],
                ] as const
              ).map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  role="radio"
                  aria-checked={scale === value}
                  className={scale === value ? "on" : ""}
                  onClick={() => setScale(value)}
                  disabled={busy || done}
                >
                  {label}
                </button>
              ))}
            </div>
            <em className="muted small" style={{ fontStyle: "normal" }}>
              {replicated
                ? `${rep.method}: the primary takes every write, the replicas serve reads${rep.balancer ? `; ${rep.balancer} gives your functions one address` : ""}.`
                : "One server holds the database. To scale it up, give that server more CPU and memory."}
            </em>
          </label>
        )}
        {replicated && rep && (
          <>
            <label>
              <span>Primary (writes)</span>
              <select
                className="select select-sm"
                value={primary}
                onChange={(e) => {
                  setPrimary(e.target.value);
                  setReplicas((r) => r.filter((x) => x !== e.target.value));
                }}
                disabled={busy || done}
              >
                <option value="">pick a server</option>
                {servers.map((s) => (
                  <option key={s.name} value={s.name}>
                    {s.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Replication</span>
              <select
                className="select select-sm"
                value={sync}
                onChange={(e) => setSync(e.target.value as "async" | "sync")}
                disabled={busy || done}
                title={sync === "sync" ? rep.sync : rep.async}
              >
                <option value="async">async (fastest)</option>
                <option value="sync">sync (no lost writes)</option>
              </select>
            </label>
            <div className="wide hana-checks">
              <span className="muted small">
                Read replicas ({replicas.length})
              </span>
              {servers
                .filter((s) => s.name !== primary)
                .map((s) => (
                  <label key={s.name} className="hana-check">
                    <input
                      type="checkbox"
                      checked={replicas.includes(s.name)}
                      disabled={busy || done}
                      onChange={(e) =>
                        setReplicas((r) =>
                          e.target.checked
                            ? [...r, s.name]
                            : r.filter((x) => x !== s.name),
                        )
                      }
                    />{" "}
                    {s.name}
                  </label>
                ))}
            </div>
            {rep.balancer && (
              <label className="wide">
                <span>
                  {rep.balancer} (one address for your functions) runs on
                </span>
                <select
                  className="select select-sm"
                  value={lbServer}
                  onChange={(e) => setLbServer(e.target.value)}
                  disabled={busy || done}
                >
                  <option value="">no load balancer</option>
                  {servers.map((s) => (
                    <option key={s.name} value={s.name}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
            {scaleError && <span className="wide hana-err">{scaleError}</span>}
          </>
        )}
        {!replicated && (
          <label>
            <span>Runs on</span>
            <select
              className="select select-sm"
              value={where}
              onChange={(e) => setWhere(e.target.value)}
              disabled={busy || done}
            >
              <option value="">This machine (Docker)</option>
              {servers.length > 0 && (
                <optgroup label="Saved servers">
                  {servers.map((s) => (
                    <option key={s.name} value={`server:${s.name}`}>
                      {s.name} ({s.user ? `${s.user}@` : ""}
                      {s.host})
                    </option>
                  ))}
                </optgroup>
              )}
              {clusters.length > 0 && (
                <optgroup label="Scaling clusters (placed on the server with the most free memory)">
                  {clusters.map((c) => (
                    <option key={c} value={`cluster:${c}`}>
                      {c}
                    </option>
                  ))}
                </optgroup>
              )}
            </select>
          </label>
        )}
      </div>
      {error && <div className="hana-note err">{error}</div>}
      {!done && (
        <div className="hana-actions">
          <button
            type="button"
            className="btn btn-primary btn-sm"
            disabled={!key.trim() || busy || !!scaleError}
            onClick={() => void create()}
          >
            {busy ? "Creating…" : "Create"}
          </button>
          <span className="muted small">
            Starts it with Docker. Details: Resources &gt; On-prem services.
          </span>
        </div>
      )}
      {jobId && (
        <pre className="hana-pre hana-log">
          {job.lines.map((l) => l.text).join("\n") || "starting…"}
          {job.status === "failed"
            ? "\n\nFailed."
            : job.status === "succeeded"
              ? "\n\nDone."
              : ""}
        </pre>
      )}
    </div>
  );
}

/** Poll a studio job until it ends, passing each new log line on. Resolves to its final status. */
async function waitJob(
  id: string,
  onLine: (text: string) => void,
): Promise<string> {
  let since = 0;
  for (;;) {
    const job = await api.job(id, since);
    for (const line of job.lines || []) onLine(line.text);
    since = job.next ?? since;
    if (job.status !== "running") return job.status;
    await new Promise((r) => window.setTimeout(r, 800));
  }
}

function ClusterCard({
  card,
  onNote,
}: {
  card: Extract<HanaCard, { kind: "cluster" }>;
  onNote: Note;
}) {
  const [name, setName] = useState(card.name);
  const [orchestrator, setOrchestrator] = useState(
    card.orchestrator || "swarm",
  );
  const [master, setMaster] = useState(card.master);
  const [workers, setWorkers] = useState<string[]>(card.workers);
  const [state, setState] = useState<"idle" | "busy" | "ok" | "err">("idle");
  const [log, setLog] = useState<string[]>([]);
  const [step, setStep] = useState("");
  const others = card.servers.filter((s) => s !== master);
  const total = 1 + workers.length;

  const create = async () => {
    setState("busy");
    setLog([]);
    const add = (t: string) => setLog((l) => [...l.slice(-400), t]);
    try {
      setStep(`Creating ${name} on ${master}`);
      const created = await api.clusterCreate({
        name: name.trim(),
        orchestrator,
        master,
      });
      if ((await waitJob(created.job_id, add)) !== "succeeded")
        throw new Error(`creating ${name} failed (see the log)`);
      for (const [i, server] of workers.entries()) {
        setStep(`Joining ${server} (${i + 2} of ${total})`);
        const joined = await api.clusterAction(name.trim(), "join", { server });
        if ((await waitJob(joined.job_id, add)) !== "succeeded")
          throw new Error(`${server} could not join (see the log)`);
      }
      setState("ok");
      setStep("");
      await onNote(
        `Created scaling cluster **${name}** (${orchestrator}) with ${[master, ...workers].join(", ")}; master **${master}**. It is on the Scaling cluster page.`,
      );
    } catch (exc) {
      setState("err");
      setStep(errorMessage(exc));
      await onNote(`Creating cluster ${name} stopped: ${errorMessage(exc)}`);
    }
  };

  const busy = state === "busy";
  const done = state === "ok";
  return (
    <div className="hana-card hana-action">
      <div className="hana-card-title">Create scaling cluster</div>
      <div className="hana-form">
        <Field label="Name">
          <input
            className="input input-sm mono"
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={busy || done}
          />
        </Field>
        <Field label="Orchestrator">
          <select
            className="select select-sm"
            value={orchestrator}
            onChange={(e) => setOrchestrator(e.target.value)}
            disabled={busy || done}
          >
            <option value="swarm">Docker Swarm</option>
            <option value="kubernetes">Kubernetes (k3s)</option>
            <option value="nomad">HashiCorp Nomad</option>
          </select>
        </Field>
        <Field label="Master server" wide focus={!master}>
          <select
            className="select select-sm"
            value={master}
            onChange={(e) => {
              setMaster(e.target.value);
              setWorkers((w) => w.filter((x) => x !== e.target.value));
            }}
            disabled={busy || done}
          >
            <option value="">pick a server</option>
            {card.servers.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </Field>
        <div className="wide hana-checks">
          <span className="muted small">
            Servers that join it ({workers.length})
          </span>
          {others.length === 0 && (
            <span className="muted small">
              No other saved servers: paste more servers to add them.
            </span>
          )}
          {others.map((s) => (
            <label key={s} className="hana-check">
              <input
                type="checkbox"
                checked={workers.includes(s)}
                disabled={busy || done}
                onChange={(e) =>
                  setWorkers((w) =>
                    e.target.checked ? [...w, s] : w.filter((x) => x !== s),
                  )
                }
              />{" "}
              {s}
            </label>
          ))}
        </div>
      </div>
      {step && (
        <div className={`hana-note ${state === "err" ? "err" : "info"}`}>
          {step}
        </div>
      )}
      {done && (
        <div className="hana-note ok">
          Cluster {name} is ready with {total} server{total === 1 ? "" : "s"}.
        </div>
      )}
      {!done && (
        <div className="hana-actions">
          <button
            type="button"
            className="btn btn-primary btn-sm"
            disabled={busy || !master || !name.trim()}
            onClick={() => void create()}
          >
            {busy
              ? "Creating…"
              : `Create (${total} server${total === 1 ? "" : "s"})`}
          </button>
          <span className="muted small">
            Installs the orchestrator over SSH; takes a few minutes.
          </span>
        </div>
      )}
      {log.length > 0 && (
        <pre className="hana-pre hana-log">{log.join("\n")}</pre>
      )}
    </div>
  );
}

function BalancerCard({
  card,
  onNote,
}: {
  card: Extract<HanaCard, { kind: "balancer" }>;
  onNote: Note;
}) {
  const [name, setName] = useState(card.name);
  const [server, setServer] = useState(card.server);
  const [port, setPort] = useState(String(card.port || 80));
  const [algorithm, setAlgorithm] = useState(card.algorithm);
  const [clusters, setClusters] = useState<string[]>(card.clusters);
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const job = useJob(jobId);
  useEffect(() => {
    if (job.status === "succeeded") {
      void onNote(
        `Created load balancer **${name}** on ${server}:${port} (${algorithm})${clusters.length ? ` for ${clusters.join(", ")}` : ""}. To route this project through it, set provider.options.balancer: ${name}.`,
      );
    } else if (job.status === "failed") {
      void onNote(
        `Creating load balancer ${name} failed: ${job.lines
          .slice(-2)
          .map((l) => l.text)
          .join(" ")}`,
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job.status]);
  const create = async () => {
    setError("");
    try {
      setJobId(
        (
          await api.balancerCreate({
            name: name.trim(),
            server,
            port: Number(port) || 80,
            algorithm,
            clusters,
          })
        ).job_id,
      );
    } catch (exc) {
      setError(errorMessage(exc));
    }
  };
  const busy = job.status === "running";
  const done = job.status === "succeeded";
  const summary = card.algorithms.find((a) => a.name === algorithm)?.summary;
  return (
    <div className="hana-card hana-action">
      <div className="hana-card-title">Create load balancer</div>
      <div className="hana-form">
        <Field label="Name">
          <input
            className="input input-sm mono"
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={busy || done}
          />
        </Field>
        <Field label="Runs on (server)">
          <select
            className="select select-sm"
            value={server}
            onChange={(e) => setServer(e.target.value)}
            disabled={busy || done}
          >
            {card.servers.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Port">
          <input
            className="input input-sm mono"
            value={port}
            onChange={(e) => setPort(e.target.value.replace(/\D/g, ""))}
            disabled={busy || done}
          />
        </Field>
        <Field label="Algorithm">
          <select
            className="select select-sm"
            value={algorithm}
            onChange={(e) => setAlgorithm(e.target.value)}
            disabled={busy || done}
          >
            {card.algorithms.map((a) => (
              <option key={a.name} value={a.name}>
                {a.label}
              </option>
            ))}
          </select>
        </Field>
        {summary && <span className="wide muted small">{summary}</span>}
        <div className="wide hana-checks">
          <span className="muted small">Clusters it sends requests to</span>
          {card.cluster_names.length === 0 && (
            <span className="muted small">
              No clusters yet: create one first, or attach it later on the Load
              balancers page.
            </span>
          )}
          {card.cluster_names.map((c) => (
            <label key={c} className="hana-check">
              <input
                type="checkbox"
                checked={clusters.includes(c)}
                disabled={busy || done}
                onChange={(e) =>
                  setClusters((l) =>
                    e.target.checked ? [...l, c] : l.filter((x) => x !== c),
                  )
                }
              />{" "}
              {c}
            </label>
          ))}
        </div>
      </div>
      {error && <div className="hana-note err">{error}</div>}
      {!done && (
        <div className="hana-actions">
          <button
            type="button"
            className="btn btn-primary btn-sm"
            disabled={busy || !name.trim() || !server}
            onClick={() => void create()}
          >
            {busy ? "Creating…" : "Create"}
          </button>
          <span className="muted small">
            Starts nginx in Docker on {server || "the server"}.
          </span>
        </div>
      )}
      {jobId && (
        <pre className="hana-pre hana-log">
          {job.lines.map((l) => l.text).join("\n") || "starting…"}
          {job.status === "running"
            ? ""
            : job.status === "failed"
              ? "\n\nFailed."
              : "\n\nDone."}
        </pre>
      )}
    </div>
  );
}

/** Deploy this project with studio's own deploy job, after the same confirmation as the Deploy page. */
function DeployCard({
  card,
  onNote,
}: {
  card: Extract<HanaCard, { kind: "deploy" }>;
  onNote: Note;
}) {
  const confirm = useConfirm();
  const [stage, setStage] = useState(card.stage || "dev");
  const [where, setWhere] = useState(
    card.cluster
      ? `cluster:${card.cluster}`
      : card.server
        ? `server:${card.server}`
        : "",
  );
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const job = useJob(jobId);
  const onprem = card.provider === "onprem";
  const label = where.startsWith("cluster:")
    ? `cluster ${where.slice(8)}`
    : where.startsWith("server:")
      ? where.slice(7)
      : "this machine";

  useEffect(() => {
    if (job.status === "succeeded") {
      void onNote(
        `Deployed this project (${card.provider}, stage ${stage}${onprem ? `, ${label}` : ""}). The URLs are on the Deploy page.`,
      );
    } else if (job.status === "failed") {
      void onNote(
        `The deploy (${card.provider}, stage ${stage}) failed: ${job.lines
          .slice(-3)
          .map((l) => l.text)
          .join(" ")} Ask me to look at the error.`,
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job.status]);

  const deploy = async () => {
    setError("");
    const prod = /^prod/.test(stage);
    const ok = await confirm({
      title: `Deploy to ${card.provider} / ${stage}?`,
      body: `This builds the project and applies it${onprem ? ` on ${label}` : ` to your ${card.provider} account`}. Running functions are replaced by this version.`,
      confirmLabel: "Deploy",
      danger: prod,
      typed: prod ? stage : undefined,
    });
    if (!ok) return;
    const args: JsonObject = {};
    if (where.startsWith("server:")) args.server = where.slice(7);
    if (where.startsWith("cluster:")) args.cluster = where.slice(8);
    try {
      setJobId(
        (await api.startJob("deploy", card.provider, stage, args)).job_id,
      );
    } catch (exc) {
      setError(errorMessage(exc));
    }
  };

  const busy = job.status === "running";
  const done = job.status === "succeeded";
  return (
    <div className="hana-card hana-action">
      <div className="hana-card-title">Deploy this project</div>
      <div className="hana-form">
        <Field label="Provider">
          <input
            className="input input-sm mono"
            value={card.provider || "(pick it in the top bar)"}
            disabled
          />
        </Field>
        <Field label="Stage" focus={/^prod/.test(stage)}>
          <input
            className="input input-sm mono"
            value={stage}
            onChange={(e) =>
              setStage(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""))
            }
            disabled={busy || done}
          />
        </Field>
        {onprem && (
          <Field label="Run on" wide>
            <select
              className="select select-sm"
              value={where}
              onChange={(e) => setWhere(e.target.value)}
              disabled={busy || done}
            >
              <option value="">This machine</option>
              {card.servers.map((s) => (
                <option key={s} value={`server:${s}`}>
                  Server {s}
                </option>
              ))}
              {card.clusters.map((c) => (
                <option key={c} value={`cluster:${c}`}>
                  Scaling cluster {c}
                </option>
              ))}
            </select>
          </Field>
        )}
      </div>
      {error && <div className="hana-note err">{error}</div>}
      {!done && (
        <div className="hana-actions">
          <button
            type="button"
            className="btn btn-primary btn-sm"
            disabled={busy || !card.provider || !stage}
            onClick={() => void deploy()}
          >
            {busy ? "Deploying…" : "Deploy"}
          </button>
          <span className="muted small">
            Asks you to confirm first
            {/^prod/.test(stage) ? "; type the stage name for prod" : ""}.
          </span>
        </div>
      )}
      {jobId && (
        <pre className="hana-pre hana-log">
          {job.lines.map((l) => l.text).join("\n") || "starting…"}
          {job.status === "running"
            ? ""
            : job.status === "failed"
              ? "\n\nFailed."
              : "\n\nDone."}
        </pre>
      )}
    </div>
  );
}

/** A workflow that runs the project's functions one after the other (written to pskit.yml, then validated). */
function WorkflowCard({
  card,
  onNote,
  onChanged,
}: {
  card: Extract<HanaCard, { kind: "workflow" }>;
  onNote: Note;
  onChanged: () => Promise<void>;
}) {
  const [name, setName] = useState(card.name);
  const [steps, setSteps] = useState<string[]>(card.steps);
  const [description, setDescription] = useState("");
  const [wait, setWait] = useState(String(card.wait || 0));
  const toCreate = (card.create || []).filter((f) => steps.includes(f));
  const [state, setState] = useState<"idle" | "busy" | "ok" | "err">("idle");
  const [message, setMessage] = useState("");
  const nameError = /^[a-z][a-z0-9-]{0,62}$/.test(name)
    ? ""
    : "lowercase letters, digits and -";
  const move = (i: number, by: number) =>
    setSteps((s) => {
      const out = [...s];
      const j = i + by;
      if (j < 0 || j >= out.length) return s;
      [out[i], out[j]] = [out[j], out[i]];
      return out;
    });
  const create = async () => {
    setState("busy");
    try {
      const r = await api.hanaWorkflow(
        name,
        steps,
        description,
        Number(wait) || 0,
        toCreate,
      );
      const ok = /Configuration is valid/.test(r.validate);
      setState(ok ? "ok" : "err");
      setMessage(r.validate);
      const made = r.functions.length
        ? `Created the function${r.functions.length > 1 ? "s" : ""} ${r.functions.join(", ")} (stubs in ${[...new Set(r.stubs)].join(", ")}) and the `
        : "Created the ";
      await onNote(
        `${made}workflow **${name}**: ${r.states.join(" → ")} (pskit.yml backed up first). Validate: ${ok ? "valid" : "see the problems below the card"}.`,
      );
      await onChanged();
    } catch (exc) {
      setState("err");
      setMessage(errorMessage(exc));
    }
  };
  const done = state === "ok";
  return (
    <div className="hana-card hana-action">
      <div className="hana-card-title">Create workflow</div>
      <div className="hana-form">
        <Field label="Name" focus={!!nameError}>
          <input
            className="input input-sm mono"
            value={name}
            onChange={(e) => setName(e.target.value.toLowerCase())}
            disabled={done}
          />
          {nameError && <em className="hana-err">{nameError}</em>}
        </Field>
        <Field
          label="Wait between steps (seconds, 0 = none)"
          focus={!!card.wait}
        >
          <input
            className="input input-sm mono"
            value={wait}
            onChange={(e) => setWait(e.target.value.replace(/[^\d.]/g, ""))}
            disabled={done}
          />
        </Field>
        {toCreate.length > 0 && (
          <span className="wide hana-note info">
            New functions created first (no trigger, a handler stub each):{" "}
            {toCreate.join(", ")}
          </span>
        )}
        <Field label="Description (optional)">
          <input
            className="input input-sm"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            disabled={done}
          />
        </Field>
        <div className="wide hana-checks">
          <span className="muted small">
            Steps, in order (each gets the previous step's result)
          </span>
          {steps.length === 0 && (
            <span className="muted small">Add functions below.</span>
          )}
          <ol className="hana-steps wide">
            {steps.map((s, i) => (
              <li key={`${s}-${i}`}>
                <code className="mono">{s}</code>{" "}
                {!done && (
                  <>
                    <button
                      type="button"
                      className="link-btn small"
                      onClick={() => move(i, -1)}
                      disabled={i === 0}
                      aria-label={`Move ${s} up`}
                    >
                      ↑
                    </button>{" "}
                    <button
                      type="button"
                      className="link-btn small"
                      onClick={() => move(i, 1)}
                      disabled={i === steps.length - 1}
                      aria-label={`Move ${s} down`}
                    >
                      ↓
                    </button>{" "}
                    <button
                      type="button"
                      className="link-btn small"
                      onClick={() =>
                        setSteps((l) => l.filter((_x, k) => k !== i))
                      }
                      aria-label={`Remove ${s}`}
                    >
                      ✕
                    </button>
                  </>
                )}
              </li>
            ))}
          </ol>
          {!done && (
            <div className="hana-suggest">
              {card.functions.map((f) => (
                <button
                  key={f}
                  type="button"
                  className="chip chip-btn"
                  onClick={() => setSteps((l) => [...l, f])}
                >
                  + {f}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
      {message && (
        <pre className={`hana-pre${state === "err" ? " bad" : ""}`}>
          {message}
        </pre>
      )}
      {!done && (
        <div className="hana-actions">
          <button
            type="button"
            className="btn btn-primary btn-sm"
            disabled={state === "busy" || !!nameError || steps.length === 0}
            onClick={() => void create()}
          >
            {state === "busy"
              ? "Creating…"
              : `Create (${steps.length} step${steps.length === 1 ? "" : "s"})`}
          </button>
        </div>
      )}
    </div>
  );
}

const EXISTING_CHOICES: [string, string][] = [
  ["update", "Update it (keep its code, apply the trigger / placement)"],
  ["rename", "Create it under another name"],
  ["skip", "Skip it"],
];

/** `step-01` -> `functions/step_01/` (the folder of a function that is its own app). */
const appFolder = (name: string) => {
  const folder = name.replace(/-/g, "_").replace(/\W/g, "_").toLowerCase();
  return `functions/${/^\d/.test(folder) ? `fn_${folder}` : folder}/`;
};

/** New functions: the pskit.yml entry AND the handler code, in one step. Asks where the code goes (each function
 * its own app with its own requirements.txt, or an existing module) and what to do with names already taken. */
function FunctionsCard({
  card,
  onNote,
  onChanged,
}: {
  card: Extract<HanaCard, { kind: "functions" }>;
  onNote: Note;
  onChanged: () => Promise<void>;
}) {
  const [names, setNames] = useState(card.names.join(", "));
  const [trigger, setTrigger] = useState(card.trigger || "none");
  const [schedule, setSchedule] = useState(card.schedule || "5 minutes");
  const [placement, setPlacement] = useState<"" | "separate" | "module">(
    (card.placement as "" | "separate" | "module") || "",
  );
  const modules = card.modules?.length ? card.modules : [card.module];
  const [module, setModule] = useState(card.module || modules[0]);
  const [decisions, setDecisions] = useState<Record<string, string>>(
    card.decisions || {},
  );
  const [state, setState] = useState<"idle" | "busy" | "ok" | "err">("idle");
  const [message, setMessage] = useState("");
  const list = names
    .split(/[\s,]+/)
    .map((n) => n.trim().toLowerCase())
    .filter(Boolean);
  const bad = list.filter((n) => !/^[a-z][a-z0-9-]{0,62}$/.test(n));
  const taken = (card.existing || []).filter((n) => list.includes(n));
  const undecided = taken.filter((n) => !decisions[n]);
  const create = async () => {
    if (!placement) return;
    setState("busy");
    try {
      const existing: Record<string, string> = {};
      for (const n of taken) existing[n] = decisions[n];
      const r = await api.hanaFunctions(list, trigger, schedule, {
        placement,
        module,
        existing,
      });
      const ok =
        /Configuration is valid/.test(r.validate) ||
        (!r.created.length && !r.updated.length);
      setState(ok ? "ok" : "err");
      const extra = [
        ...Object.entries(r.renamed).map(
          ([a, b]) => `${a} exists: created ${b}`,
        ),
        ...r.skipped.map((n) => `${n}: skipped`),
        ...r.moved.map((m) => `${m.function}: ${m.from} → ${m.to}`),
        ...r.deleted.map((f) => `deleted ${f} (nothing left in it)`),
        ...r.move_errors,
      ];
      setMessage([...extra, r.validate].filter(Boolean).join("\n"));
      const files = [...new Set(r.code.map((c) => c.file))].join(", ");
      const parts = [
        r.created.length
          ? `Created ${r.created.map((n) => `**${n}**`).join(", ")}: in pskit.yml with handler code in ${files}`
          : "",
        placement === "separate" && r.created.length
          ? "each in its own app with its own requirements.txt"
          : "",
        r.updated.length
          ? `updated ${r.updated.map((n) => `**${n}**`).join(", ")}`
          : "",
        r.skipped.length ? `skipped ${r.skipped.join(", ")}` : "",
      ].filter(Boolean);
      await onNote(
        `${parts.join("; ") || "Nothing created"}. Validate: ${ok ? "valid" : "see the card"}.`,
      );
      await onChanged();
    } catch (exc) {
      setState("err");
      setMessage(errorMessage(exc));
    }
  };
  const done = state === "ok";
  return (
    <div className="hana-card hana-action">
      <div className="hana-card-title">Create functions</div>
      <div className="hana-form">
        <Field
          label="Names (comma or space separated)"
          wide
          focus={bad.length > 0}
        >
          <input
            className="input input-sm mono"
            value={names}
            onChange={(e) => setNames(e.target.value)}
            disabled={done}
          />
          {bad.length > 0 && (
            <em className="hana-err">
              lowercase letters, digits and -: {bad.join(", ")}
            </em>
          )}
        </Field>
        <Field label="Where does the code go?" wide focus={!placement}>
          <label className="hana-check">
            <input
              type="radio"
              name={`placement-${card.names.join("-")}`}
              checked={placement === "separate"}
              onChange={() => setPlacement("separate")}
              disabled={done}
            />{" "}
            Each function is <b>its own app</b>:{" "}
            <code className="mono small">
              {list[0] ? appFolder(list[0]) : "functions/<name>/"}
            </code>{" "}
            with its own requirements.txt
          </label>
          <label className="hana-check">
            <input
              type="radio"
              name={`placement-${card.names.join("-")}`}
              checked={placement === "module"}
              onChange={() => setPlacement("module")}
              disabled={done}
            />{" "}
            Add to an <b>existing app</b>:{" "}
            <select
              className="select select-sm mono"
              value={module}
              onChange={(e) => {
                setModule(e.target.value);
                setPlacement("module");
              }}
              disabled={done}
            >
              {modules.map((m) => (
                <option key={m} value={m}>
                  {m.replace(/\./g, "/")}.py
                </option>
              ))}
            </select>
          </label>
          {!placement && <em className="hana-err">pick one</em>}
        </Field>
        {taken.map((n) => (
          <Field
            key={n}
            label={`${n} already exists`}
            wide
            focus={!decisions[n]}
          >
            <select
              className="select select-sm"
              value={decisions[n] || ""}
              onChange={(e) =>
                setDecisions((d) => ({ ...d, [n]: e.target.value }))
              }
              disabled={done}
            >
              <option value="">Choose…</option>
              {EXISTING_CHOICES.map(([value, label]) => (
                <option key={value} value={value}>
                  {value === "rename"
                    ? `${label} (${card.suggested?.[n] || `${n}-2`})`
                    : label}
                </option>
              ))}
            </select>
          </Field>
        ))}
        <Field label="Trigger">
          <select
            className="select select-sm"
            value={trigger}
            onChange={(e) => setTrigger(e.target.value)}
            disabled={done}
          >
            <option value="none">
              None (called directly or by a workflow)
            </option>
            <option value="http">HTTP: GET /&lt;name&gt;</option>
            <option value="schedule">Schedule</option>
          </select>
        </Field>
        {trigger === "schedule" && (
          <Field label="Every">
            <input
              className="input input-sm mono"
              value={schedule}
              onChange={(e) => setSchedule(e.target.value)}
              disabled={done}
            />
          </Field>
        )}
      </div>
      {message && (
        <pre className={`hana-pre${state === "err" ? " bad" : ""}`}>
          {message}
        </pre>
      )}
      {!done && (
        <div className="hana-actions">
          <button
            type="button"
            className="btn btn-primary btn-sm"
            disabled={
              state === "busy" ||
              !list.length ||
              bad.length > 0 ||
              !placement ||
              undecided.length > 0
            }
            title={
              !placement
                ? "Choose where the code goes"
                : undecided.length
                  ? `Choose what to do with ${undecided.join(", ")}`
                  : undefined
            }
            onClick={() => void create()}
          >
            {state === "busy"
              ? "Creating…"
              : `Create ${list.length} function${list.length === 1 ? "" : "s"}`}
          </button>
        </div>
      )}
    </div>
  );
}

/** Existing functions into their own apps: code to functions/<name>/handler.py with its own requirements.txt. */
function SeparateCard({
  card,
  onNote,
  onChanged,
}: {
  card: Extract<HanaCard, { kind: "separate" }>;
  onNote: Note;
  onChanged: () => Promise<void>;
}) {
  const [pick, setPick] = useState<string[]>(card.functions);
  const [state, setState] = useState<"idle" | "busy" | "ok" | "err" | "kept">(
    "idle",
  );
  const [message, setMessage] = useState("");
  const move = async () => {
    setState("busy");
    try {
      const r = await api.hanaSeparate(pick);
      const ok = /Configuration is valid/.test(r.validate) && !r.errors.length;
      setState(ok ? "ok" : "err");
      const lines = [
        ...r.moved.map((m) => `${m.function}: ${m.from} → ${m.to}`),
        ...r.deleted.map((f) => `deleted ${f} (nothing left in it)`),
        ...r.already.map((f) => `${f}: already its own app`),
        ...r.errors,
        r.validate,
      ];
      setMessage(lines.filter(Boolean).join("\n"));
      await onNote(
        `Moved ${r.moved.map((m) => `**${m.function}**`).join(", ") || "nothing"} into ${r.moved.length === 1 ? "its own app" : "their own apps"} (${r.moved
          .map((m) => m.to.replace(/\/handler\.py$/, "/"))
          .join(
            ", ",
          )}), each with its own requirements.txt${r.deleted.length ? `; deleted ${r.deleted.join(", ")}` : ""}. Validate: ${ok ? "valid" : "see the card"}.`,
      );
      await onChanged();
    } catch (exc) {
      setState("err");
      setMessage(errorMessage(exc));
    }
  };
  const done = state === "ok" || state === "kept";
  return (
    <div className="hana-card hana-action">
      <div className="hana-card-title">Move into separate apps</div>
      <div className="hana-checks">
        {card.plans.map((p) => (
          <label key={p.function} className="hana-check">
            <input
              type="checkbox"
              checked={pick.includes(p.function)}
              disabled={done}
              onChange={(e) =>
                setPick((l) =>
                  e.target.checked
                    ? [...l, p.function]
                    : l.filter((x) => x !== p.function),
                )
              }
            />{" "}
            <b>{p.function}</b>: <code className="mono small">{p.from}</code> →{" "}
            <code className="mono small">{p.to}</code>
            {p.requirements.length > 0 && (
              <span className="muted small">
                {" "}
                (requirements: {p.requirements.join(", ")})
              </span>
            )}
          </label>
        ))}
      </div>
      {message && (
        <pre className={`hana-pre${state === "err" ? " bad" : ""}`}>
          {message}
        </pre>
      )}
      {state === "kept" && <div className="hana-note">Left as it is.</div>}
      {!done && (
        <div className="hana-actions">
          <button
            type="button"
            className="btn btn-primary btn-sm"
            disabled={state === "busy" || !pick.length}
            onClick={() => void move()}
          >
            {state === "busy" ? "Moving…" : `Move ${pick.length}`}
          </button>
          <button
            type="button"
            className="btn btn-sm"
            disabled={state === "busy"}
            onClick={() => setState("kept")}
          >
            Keep as is
          </button>
        </div>
      )}
    </div>
  );
}

/** Handler code that is missing: one stub per function (existing code is never changed). */
function CodeCard({
  card,
  onNote,
  onChanged,
}: {
  card: Extract<HanaCard, { kind: "code" }>;
  onNote: Note;
  onChanged: () => Promise<void>;
}) {
  const [pick, setPick] = useState<string[]>(card.items.map((i) => i.function));
  const [state, setState] = useState<"idle" | "busy" | "ok" | "err">("idle");
  const [message, setMessage] = useState("");
  const write = async () => {
    setState("busy");
    try {
      const r = await api.hanaCode(pick);
      setState("ok");
      const lines = r.written.map((w) => `${w.function} → ${w.file}`);
      setMessage(lines.join("\n") || "nothing was missing");
      await onNote(
        `Wrote the handler code for ${r.written.map((w) => `**${w.function}**`).join(", ")} (${[...new Set(r.written.map((w) => w.file))].join(", ")}). Ask me what each function should do and I'll fill it in.`,
      );
      await onChanged();
    } catch (exc) {
      setState("err");
      setMessage(errorMessage(exc));
    }
  };
  const done = state === "ok";
  return (
    <div className="hana-card hana-action">
      <div className="hana-card-title">Write the missing code</div>
      <div className="hana-checks">
        {card.items.map((i) => (
          <label key={i.function} className="hana-check">
            <input
              type="checkbox"
              checked={pick.includes(i.function)}
              disabled={done}
              onChange={(e) =>
                setPick((l) =>
                  e.target.checked
                    ? [...l, i.function]
                    : l.filter((x) => x !== i.function),
                )
              }
            />{" "}
            <b>{i.function}</b> <code className="mono small">{i.handler}</code>
          </label>
        ))}
      </div>
      {message && (
        <pre className={`hana-pre${state === "err" ? " bad" : ""}`}>
          {message}
        </pre>
      )}
      {!done && (
        <div className="hana-actions">
          <button
            type="button"
            className="btn btn-primary btn-sm"
            disabled={state === "busy" || !pick.length}
            onClick={() => void write()}
          >
            {state === "busy" ? "Writing…" : "Write the code"}
          </button>
        </div>
      )}
    </div>
  );
}

const RESOURCE_LABEL: Record<string, string> = {
  queue: "Queue (pskit creates it)",
  storage: "Bucket / storage (pskit creates it)",
  topic: "Topic (pskit creates it)",
  smtp: "Mail inbox, smtp (pskit creates it)",
  database: "Database (existing: host / port)",
  cache: "Cache (existing: host / port)",
  custom: "Other service (existing: host / port)",
};

/** One resource in pskit.yml: created by pskit (queue, bucket, topic, smtp) or an existing one (database, cache). */
function ResourceCard({
  card,
  onNote,
  onChanged,
}: {
  card: Extract<HanaCard, { kind: "resource" }>;
  onNote: Note;
  onChanged: () => Promise<void>;
}) {
  const [key, setKey] = useState(card.key);
  const [type, setType] = useState(card.type);
  const [host, setHost] = useState("");
  const [port, setPort] = useState("");
  // the name is already a resource: replace it, or add this one under another name (picked by the user)
  const [replace, setReplace] = useState<"" | "replace" | "rename">("");
  const [state, setState] = useState<"idle" | "busy" | "ok" | "err">("idle");
  const [message, setMessage] = useState("");
  const external = ["database", "cache", "custom"].includes(type);
  const keyError = /^[a-z][a-z0-9-]{0,62}$/.test(key)
    ? ""
    : "lowercase letters, digits and -";
  const clash = !!card.exists && key === card.key;
  const add = async () => {
    setState("busy");
    try {
      const item: JsonObject = { key, type };
      if (clash && replace === "replace") item.replace = true;
      if (external && host.trim()) item.host = host.trim();
      if (external && port.trim()) item.port = Number(port);
      const r = await api.hanaResources([item]);
      const ok = /Configuration is valid/.test(r.validate);
      setState(ok ? "ok" : "err");
      setMessage(r.validate);
      const verb = r.replaced?.length ? "Replaced" : "Added";
      await onNote(
        `${verb} the resource **${key}** (${type}${external ? ", existing" : ""}) in pskit.yml. Validate: ${ok ? "valid" : "see the card"}.`,
      );
      await onChanged();
    } catch (exc) {
      setState("err");
      setMessage(errorMessage(exc));
    }
  };
  const done = state === "ok";
  return (
    <div className="hana-card hana-action">
      <div className="hana-card-title">
        {clash && replace === "replace"
          ? `Replace resource ${key}`
          : "Add resource"}
      </div>
      <div className="hana-form">
        <Field label="Name" focus={!!keyError}>
          <input
            className="input input-sm mono"
            value={key}
            onChange={(e) => setKey(e.target.value.toLowerCase())}
            disabled={done}
          />
          {keyError && <em className="hana-err">{keyError}</em>}
        </Field>
        {clash && (
          <Field
            label={`${card.key} already exists${card.existing_type ? ` (a ${card.existing_type})` : ""}`}
            wide
            focus={!replace}
          >
            <label className="hana-check">
              <input
                type="radio"
                name={`res-${card.key}`}
                checked={replace === "replace"}
                onChange={() => setReplace("replace")}
                disabled={done}
              />{" "}
              Replace it (pskit.yml is backed up first)
            </label>
            <label className="hana-check">
              <input
                type="radio"
                name={`res-${card.key}`}
                checked={replace === "rename"}
                onChange={() => {
                  setReplace("rename");
                  setKey(card.suggested || `${card.key}-2`);
                }}
                disabled={done}
              />{" "}
              Add it as{" "}
              <code className="mono">{card.suggested || `${card.key}-2`}</code>
            </label>
          </Field>
        )}
        <Field label="Type">
          <select
            className="select select-sm"
            value={type}
            onChange={(e) => setType(e.target.value)}
            disabled={done}
          >
            {Object.entries(RESOURCE_LABEL).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </Field>
        {external && (
          <>
            <Field label="Host (empty: an env variable, localhost by default)">
              <input
                className="input input-sm mono"
                value={host}
                onChange={(e) => setHost(e.target.value)}
                placeholder="e.g. db.internal"
                disabled={done}
              />
            </Field>
            <Field label="Port">
              <input
                className="input input-sm mono"
                value={port}
                onChange={(e) => setPort(e.target.value.replace(/\D/g, ""))}
                placeholder={
                  type === "cache"
                    ? "6379"
                    : type === "database"
                      ? "5432"
                      : "8080"
                }
                disabled={done}
              />
            </Field>
            <span className="wide muted small">
              The password is never written to pskit.yml: functions get the NAME
              of an environment variable that holds it.
            </span>
          </>
        )}
      </div>
      {message && (
        <pre className={`hana-pre${state === "err" ? " bad" : ""}`}>
          {message}
        </pre>
      )}
      {!done && (
        <div className="hana-actions">
          <button
            type="button"
            className="btn btn-primary btn-sm"
            disabled={
              state === "busy" || !!keyError || (clash && replace !== "replace")
            }
            onClick={() => void add()}
          >
            {state === "busy" ? "Adding…" : clash ? "Replace" : "Add"}
          </button>
        </div>
      )}
    </div>
  );
}
