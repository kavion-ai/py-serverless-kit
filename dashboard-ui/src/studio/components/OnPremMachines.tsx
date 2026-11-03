import { useCallback, useEffect, useRef, useState } from "react";
import { Drawer } from "../../components/Drawer";
import { api, errorMessage } from "../api";
import type { JsonObject, OnPremConsoleInfo, OnPremConsoleResult, OnPremServer, OnPremServerTest, OnPremTerminal, ServerUse } from "../types";
import { useConfirm, useToast } from "./Feedback";
import { FormRow, NumberInput, Segmented, TextInput, Toggle } from "./Forms";
import { ServerLive } from "./Monitoring";
import { ServerUsageDrawer, UsageList, UsageSummary } from "./ServerUsage";

const SERVER_NAME_RE = /^[A-Za-z][A-Za-z0-9_.-]{0,62}$/;

/** Saved SSH servers: add, test, shell, browser terminal, install software, remove. */
export function ServersPanel({ onInstall, onChanged }: { onInstall: (server: string) => void; onChanged?: (servers: OnPremServer[]) => void }) {
  const [servers, setServers] = useState<OnPremServer[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<OnPremServer | "new" | null>(null);
  const [tests, setTests] = useState<Record<string, OnPremServerTest | "running">>({});
  const [shell, setShell] = useState<string | null>(null);
  const [terminal, setTerminal] = useState<{ server?: string; key?: string; shell?: boolean } | null>(null);
  const [reach, setReach] = useState<Record<string, { ok: boolean; ms?: number; error?: string }> | null>(null);
  const [live, setLive] = useState<Record<string, boolean>>({});
  // Where each server is used (pskit.yml and .pskit only, no SSH): the "Used in" column and the Forget warning.
  const [usage, setUsage] = useState<Record<string, ServerUse[]> | null>(null);
  const [usageOf, setUsageOf] = useState<string | null>(null);
  const loadUsage = useCallback(() => {
    api.onpremServerUsage().then(
      (u) => setUsage(u.servers),
      () => setUsage({}),
    );
  }, []);
  const confirm = useConfirm();
  const toast = useToast();
  // Check marks: every server's SSH port, probed in parallel (no login) when the list loads.
  const checkAll = useCallback(() => {
    setReach(null);
    api.onpremServersReachability().then(
      (r) => setReach(r.servers),
      () => setReach({}),
    );
  }, []);
  useEffect(checkAll, [checkAll]);

  const load = useCallback(() => {
    api
      .onpremServers()
      .then((r) => {
        setServers(r.servers);
        onChanged?.(r.servers);
        setError(null);
      })
      .catch((exc: unknown) => setError(errorMessage(exc)));
    loadUsage();
  }, [onChanged, loadUsage]);
  useEffect(load, [load]);

  const test = async (name: string) => {
    setTests((t) => ({ ...t, [name]: "running" }));
    try {
      const result = await api.onpremServerTest(name);
      setTests((t) => ({ ...t, [name]: result }));
    } catch (exc) {
      setTests((t) => ({ ...t, [name]: { name, ok: false, error: errorMessage(exc) } }));
    }
  };

  const remove = async (name: string) => {
    const uses = await api.onpremServerUsage().then(
      (u) => u.servers[name] || [],
      () => null,
    );
    const inCluster = (uses || []).filter((u) => u.kind === "cluster");
    const body = (
      <div>
        <p>Services already created there keep running; pskit only forgets the connection.</p>
        {uses === null ? (
          <p className="muted small">Could not read where it is used.</p>
        ) : uses.length ? (
          <>
            <p>
              <b>
                {name} is still used in {uses.length} place{uses.length === 1 ? "" : "s"}
              </b>
              {inCluster.length ? ` — take it out of cluster ${inCluster.map((u) => u.name).join(", ")} first (forgetting is refused).` : " — point them at another server afterwards:"}
            </p>
            <UsageList uses={uses} compact />
          </>
        ) : (
          <p className="muted">Not used anywhere in this project: safe to forget.</p>
        )}
      </div>
    );
    const ok = await confirm({ title: `Forget server ${name}?`, body, confirmLabel: "Forget", danger: true });
    if (ok !== "confirm") return;
    try {
      const result = await api.onpremServerRemove(name);
      (result.warnings || []).forEach((w) => toast(w, "err"));
      load();
    } catch (exc) {
      toast(errorMessage(exc), "err");
    }
  };

  return (
    <div className="card card-pad onprem-servers">
      <div className="row-between">
        <div>
          <h3>Servers</h3>
          <p className="muted small">
            Save each machine once (key file, SSH agent or password), then create services, install software, open a shell or terminal, and deploy to it
            (<code className="mono">pskit deploy --server NAME</code> or <b>Deploy → Machine</b>).
          </p>
        </div>
        <span className="row-gap">
          <button type="button" className="btn" onClick={checkAll} disabled={!servers?.length || reach === null} title="Probe every server's SSH port again">
            {reach === null && servers?.length ? "Checking…" : "Re-check"}
          </button>
          <button type="button" className="btn btn-primary" onClick={() => setEditing("new")}>
            + Add server
          </button>
        </span>
      </div>
      {error && <div className="form-error">{error}</div>}
      {servers && !servers.length && <p className="muted">No saved servers yet.</p>}
      {servers && servers.length > 0 && (
        <table className="table">
          <thead>
            <tr>
              <th aria-label="Reachable" />
              <th>Name</th>
              <th>Connection</th>
              <th>Login</th>
              <th>Used in</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {servers.map((s) => {
              const t = tests[s.name];
              return (
                <tr key={s.name}>
                  <td>
                    {(() => {
                      const r = reach?.[s.name];
                      const tested = t && t !== "running" ? t.ok : undefined;
                      const ok = tested ?? r?.ok;
                      const title = tested !== undefined ? (tested ? "Test passed (SSH login, Docker, sudo)" : "Test failed") : r ? (r.ok ? `SSH port answers (${r.ms} ms)` : r.error) : "checking…";
                      return (
                        <span className={`status-mark ${ok === undefined ? "unknown" : ok ? "ok" : "bad"}`} title={title} aria-label={title}>
                          {ok === undefined ? "…" : ok ? "✓" : "✗"}
                        </span>
                      );
                    })()}
                  </td>
                  <td>
                    <b className="mono">{s.name}</b>
                    {s.description && <div className="muted small">{s.description}</div>}
                    {(s.home || s.bind || s.data_dir) && (
                      <div className="muted small mono">
                        {[s.home && `home ${s.home}`, s.bind && `bind ${s.bind}`, s.data_dir && `data ${s.data_dir}`].filter(Boolean).join(" · ")}
                      </div>
                    )}
                  </td>
                  <td className="mono small">{s.label}</td>
                  <td className="small">
                    {s.password_file ? "password" : s.identity_file ? `key ${s.identity_file.split(/[\\/]/).pop()}` : "agent / default key"}
                    {s.sudo ? " · sudo" : ""}
                  </td>
                  <td>
                    <UsageSummary uses={usage ? usage[s.name] || [] : undefined} onOpen={() => setUsageOf(s.name)} />
                  </td>
                  <td>
                    <span className="row-gap wrap">
                      <button type="button" className="btn btn-sm" disabled={t === "running"} onClick={() => void test(s.name)}>
                        {t === "running" ? "Testing…" : "Test"}
                      </button>
                      <button
                        type="button"
                        className={`btn btn-sm${live[s.name] ? " btn-primary" : ""}`}
                        onClick={() => setLive((l) => ({ ...l, [s.name]: !l[s.name] }))}
                        title="Live CPU, RAM and disk use (every 4 s while on)"
                        aria-pressed={!!live[s.name]}
                      >
                        {live[s.name] ? "Live ●" : "Live"}
                      </button>
                      <button type="button" className="btn btn-sm" onClick={() => setShell(s.name)} title="Run commands on the server">
                        Shell
                      </button>
                      <button type="button" className="btn btn-sm" onClick={() => setTerminal({ server: s.name })} title="A full SSH terminal in the browser (Docker)">
                        Terminal
                      </button>
                      <button type="button" className="btn btn-sm btn-primary" onClick={() => onInstall(s.name)} title="Create a service or install Node.js, nginx, ...">
                        Install / create
                      </button>
                      <button type="button" className="btn btn-sm" onClick={() => setEditing(s)}>
                        Edit
                      </button>
                      <button type="button" className="btn btn-sm btn-danger" onClick={() => void remove(s.name)}>
                        Forget
                      </button>
                    </span>
                    {t && t !== "running" && <ServerFacts result={t} />}
                    {live[s.name] && <ServerLive name={s.name} />}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      {editing && (
        <ServerForm
          initial={editing === "new" ? null : editing}
          taken={(servers || []).map((s) => s.name)}
          onClose={() => setEditing(null)}
          onSaved={(name) => {
            setEditing(null);
            load();
            void test(name);
          }}
        />
      )}
      {shell && (
        <ConsoleDrawer
          title={`Shell on ${shell}`}
          info={{
            service: "ssh",
            available: true,
            label: "sh over SSH (each line is a fresh login)",
            input: "text",
            examples: ["uname -a", "df -h", "free -m", "docker ps", "node -v", "systemctl status nginx --no-pager"],
            shell: false,
            note: "",
          }}
          run={(line) => api.onpremServerShell(shell, line)}
          onTerminal={() => setTerminal({ server: shell })}
          onClose={() => setShell(null)}
        />
      )}
      {terminal && <TerminalDrawer request={terminal} onClose={() => setTerminal(null)} />}
      {usageOf && <ServerUsageDrawer name={usageOf} uses={usage?.[usageOf] || []} onClose={() => setUsageOf(null)} />}
    </div>
  );
}

function ServerFacts({ result }: { result: OnPremServerTest }) {
  if (!result.ok) return <div className="form-error small">{result.error}</div>;
  const f = result.facts || {};
  return (
    <div className="muted small">
      {f.os} · {f.arch} · {f.cpus} CPU · {f.memory_mb} MB · {f.disk_free} free · Docker: {f.docker || "not installed"}
      {f.docker ? ` (${f.docker_access === "yes" ? "ok" : f.docker_access === "sudo" ? "via sudo" : "no access"})` : ""} · sudo: {f.sudo}
      {f.python ? ` · ${f.python}` : ""}
      {f.node ? ` · Node ${f.node}` : ""}
      {f.nginx ? ` · ${f.nginx}` : ""}
    </div>
  );
}

export function ServerForm({ initial, taken, onClose, onSaved }: { initial: OnPremServer | null; taken: string[]; onClose: () => void; onSaved: (name: string) => void }) {
  const [name, setName] = useState(initial?.name || "");
  const [host, setHost] = useState(initial?.host || "");
  const [user, setUser] = useState(initial?.user || "ubuntu");
  const [port, setPort] = useState<number | undefined>(initial?.port || 22);
  const [auth, setAuth] = useState<"key" | "agent" | "password">(initial?.auth || (initial?.password_file ? "password" : initial?.identity_file ? "key" : "agent"));
  const [pem, setPem] = useState(initial?.identity_file || "");
  const [password, setPassword] = useState("");
  const [sudo, setSudo] = useState(!!initial?.sudo);
  const [description, setDescription] = useState(initial?.description || "");
  const [home, setHome] = useState(initial?.home || "");
  const [bind, setBind] = useState(initial?.bind || "");
  const [dataDir, setDataDir] = useState(initial?.data_dir || "");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const nameError = !SERVER_NAME_RE.test(name) ? "start with a letter; letters, digits, _ . -" : !initial && taken.includes(name) ? "already saved" : null;
  const hostError = !host.trim() ? "host name or IP" : null;
  const authError = auth === "key" && !pem.trim() ? "path of the private key" : auth === "password" && !password && !initial?.password_file ? "the SSH password" : null;
  const pathError = (value: string) => (value.trim() && !/^\/[A-Za-z0-9._/-]*$/.test(value.trim()) ? "an absolute Linux path, e.g. /srv/pskit" : null);
  const homeError = pathError(home);
  const dataDirError = pathError(dataDir);
  const bindError = bind.trim() && !/^(\d{1,3}\.){3}\d{1,3}$/.test(bind.trim()) ? "an IPv4 address: 0.0.0.0, 127.0.0.1 or one of the server's IPs" : null;

  const save = async () => {
    setSaving(true);
    setError(null);
    const target: JsonObject = { host: host.trim(), user: user.trim() || "root", port: port || 22, sudo, auth };
    if (auth === "key") target.identity_file = pem.trim();
    if (auth === "password" && password) target.password = password;
    target.home = home.trim();
    target.bind = bind.trim();
    target.data_dir = dataDir.trim();
    try {
      await api.onpremServerSave(name, target, description);
      onSaved(name);
    } catch (exc) {
      setError(errorMessage(exc));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Drawer
      open
      title={initial ? `Edit server ${initial.name}` : "Add a server"}
      onClose={onClose}
      actions={
        <button
          type="button"
          className="btn btn-primary"
          disabled={!!nameError || !!hostError || !!authError || !!homeError || !!bindError || !!dataDirError || saving}
          onClick={() => void save()}
        >
          {saving ? "Saving…" : "Save and test"}
        </button>
      }
    >
      <div className="form">
        <FormRow label="Name" required error={nameError} help="How you pick it: edge1, db-box, lab ...">
          <TextInput mono value={name} onChange={setName} invalid={!!nameError} />
        </FormRow>
        <FormRow label="Host" required error={hostError}>
          <TextInput mono value={host} placeholder="13.72.87.80 or server.example.com" onChange={setHost} />
        </FormRow>
        <FormRow label="User">
          <TextInput mono value={user} placeholder="ubuntu / azureuser / root" onChange={setUser} />
        </FormRow>
        <FormRow label="SSH port">
          <NumberInput integer min={1} max={65535} value={port} onChange={setPort} />
        </FormRow>
        <FormRow label="Log in with" error={authError}>
          <Segmented
            label="Log in with"
            value={auth}
            onChange={(v) => setAuth(v as "key" | "agent" | "password")}
            options={[
              { value: "key", label: "Key file (.pem)" },
              { value: "agent", label: "SSH agent / default key" },
              { value: "password", label: "Password" },
            ]}
          />
        </FormRow>
        {auth === "key" && (
          <FormRow label="Private key (.pem)">
            <TextInput mono value={pem} placeholder="~/.ssh/server.pem" onChange={setPem} />
          </FormRow>
        )}
        {auth === "password" && (
          <FormRow
            label="SSH password"
            help="Saved in .pskit/ssh/ (owner-only, out of git) and used through sshpass (Linux / macOS). On Windows run pskit resources onprem ssh-key user@host once and use the key."
          >
            <TextInput mono type="password" value={password} placeholder={initial?.password_file ? "unchanged" : ""} onChange={setPassword} />
          </FormRow>
        )}
        <Toggle checked={sudo} onChange={setSudo} label="Use sudo (the user is not root and not in the docker group)" />
        <h4>On this server (optional)</h4>
        <FormRow
          label="Home path"
          error={homeError}
          help="Where pskit keeps files: functions deploy to <home>/<service>-<stage>, cluster scripts and image copies go to <home>/pskit-cluster. Empty: /opt/pskit for functions, the SSH user's home for cluster files."
        >
          <TextInput mono value={home} placeholder="/opt/pskit" onChange={setHome} invalid={!!homeError} />
        </FormRow>
        <FormRow
          label="Bind address"
          error={bindError}
          help="The address the functions' host and services listen on: 0.0.0.0 (every interface), 127.0.0.1 (only the server itself, reached over SSH) or one of its IPs (e.g. the private one). A specific IP is also its address in a cluster. Empty: 127.0.0.1 for functions, 0.0.0.0 for services. A host set in pskit.yml (other than 127.0.0.1) wins."
        >
          <TextInput mono value={bind} placeholder="0.0.0.0 / 10.0.0.5" onChange={setBind} invalid={!!bindError} />
        </FormRow>
        <FormRow
          label="Data directory"
          error={dataDirError}
          help="Where data lives: services keep their data in <data>/<container> (a folder you can back up, instead of a Docker volume), the functions' built-in queues / buckets go to it (provider.options.data_dir), and a cluster master keeps the main replica's data in <data>/<stack>. Applies to what you create or deploy from now on."
        >
          <TextInput mono value={dataDir} placeholder="/data/pskit" onChange={setDataDir} invalid={!!dataDirError} />
        </FormRow>
        <FormRow label="Description">
          <TextInput value={description} onChange={setDescription} placeholder="optional note" />
        </FormRow>
        {error && <div className="form-error">{error}</div>}
      </div>
    </Drawer>
  );
}

interface ConsoleEntry {
  line: string;
  shell: boolean;
  result?: OnPremConsoleResult;
  error?: string;
}

/** Type a command, see its output: a service's client (redis-cli, psql, ...), sh in its container, or a server shell. */
export function ConsoleDrawer({
  title,
  info,
  run,
  onTerminal,
  onClose,
}: {
  title: string;
  info: OnPremConsoleInfo | null;
  run: (line: string, shell: boolean) => Promise<OnPremConsoleResult>;
  onTerminal?: (shell: boolean) => void;
  onClose: () => void;
}) {
  const [entries, setEntries] = useState<ConsoleEntry[]>([]);
  const [line, setLine] = useState("");
  const [shell, setShell] = useState(false);
  const [busy, setBusy] = useState(false);
  const [historyAt, setHistoryAt] = useState(-1);
  const bottom = useRef<HTMLDivElement>(null);
  const useClient = info?.available && !shell;

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" });
  }, [entries]);

  const submit = async (text: string) => {
    const cmd = text.trim();
    if (!cmd || busy) return;
    if (cmd === "clear") {
      setEntries([]);
      setLine("");
      return;
    }
    setBusy(true);
    setLine("");
    setHistoryAt(-1);
    const asShell = !info?.available || shell;
    setEntries((e) => [...e, { line: cmd, shell: asShell }]);
    try {
      const result = await run(cmd, asShell);
      setEntries((e) => e.map((x, i) => (i === e.length - 1 ? { ...x, result } : x)));
    } catch (exc) {
      setEntries((e) => e.map((x, i) => (i === e.length - 1 ? { ...x, error: errorMessage(exc) } : x)));
    } finally {
      setBusy(false);
    }
  };

  const history = entries.map((e) => e.line);
  const onKey = (ev: React.KeyboardEvent<HTMLInputElement>) => {
    if (ev.key === "Enter") void submit(line);
    else if (ev.key === "ArrowUp" && history.length) {
      ev.preventDefault();
      const at = historyAt < 0 ? history.length - 1 : Math.max(0, historyAt - 1);
      setHistoryAt(at);
      setLine(history[at]);
    } else if (ev.key === "ArrowDown" && historyAt >= 0) {
      ev.preventDefault();
      const at = historyAt + 1;
      setHistoryAt(at >= history.length ? -1 : at);
      setLine(at >= history.length ? "" : history[at]);
    }
  };

  const prompt = useClient ? `${info?.label}>` : "$";
  return (
    <Drawer open title={title} onClose={onClose}>
      <div className="form console-drawer">
        {info && (
          <div className="row-between wrap">
            {info.available && info.shell ? (
              <Segmented
                label="Mode"
                value={shell ? "shell" : "client"}
                onChange={(v) => setShell(v === "shell")}
                options={[
                  { value: "client", label: info.label },
                  { value: "shell", label: "Shell in the container" },
                ]}
              />
            ) : (
              <span className="muted small">{info.label || info.note}</span>
            )}
            {onTerminal && (
              <button type="button" className="btn btn-sm" onClick={() => onTerminal(shell)} title="Interactive session in the browser (Docker)">
                Full terminal
              </button>
            )}
          </div>
        )}
        {useClient && info && info.examples.length > 0 && (
          <div className="chips">
            {info.examples.map((x) => (
              <button key={x} type="button" className="chip chip-btn mono" onClick={() => setLine(x)}>
                {x}
              </button>
            ))}
          </div>
        )}
        <div className="console-screen mono" onClick={() => document.getElementById("console-input")?.focus()}>
          {!entries.length && <div className="muted">Each line runs once and prints its output. ↑ / ↓ for history, "clear" to clear.</div>}
          {entries.map((e, i) => (
            <div key={i} className="console-entry">
              <div className="console-cmd">
                <span className="console-prompt">{e.shell ? "$" : `${info?.label || ""}>`}</span> {e.line}
              </div>
              {e.result && <pre className={e.result.exit_code ? "console-out console-err" : "console-out"}>{e.result.output || "(no output)"}</pre>}
              {e.result && e.result.exit_code !== 0 && <div className="console-code">exit {e.result.exit_code}</div>}
              {e.error && <pre className="console-out console-err">{e.error}</pre>}
              {!e.result && !e.error && <div className="muted">running…</div>}
            </div>
          ))}
          <div ref={bottom} />
        </div>
        <div className="console-input-row">
          <span className="console-prompt mono">{prompt}</span>
          <input
            id="console-input"
            className="input mono"
            autoFocus
            spellCheck={false}
            autoComplete="off"
            value={line}
            disabled={busy}
            placeholder={useClient ? info?.examples[0] || "" : "ls -la"}
            onChange={(e) => setLine(e.target.value)}
            onKeyDown={onKey}
          />
          <button type="button" className="btn btn-primary btn-sm" disabled={busy || !line.trim()} onClick={() => void submit(line)}>
            Run
          </button>
        </div>
        {info?.note && <p className="muted small">{info.note}</p>}
      </div>
    </Drawer>
  );
}

/** A full terminal in the browser: ttyd in Docker on 127.0.0.1 behind a secret URL. */
export function TerminalDrawer({ request, onClose }: { request: { server?: string; key?: string; shell?: boolean }; onClose: () => void }) {
  const [term, setTerm] = useState<OnPremTerminal | null>(null);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();
  useEffect(() => {
    let live = true;
    api
      .onpremTerminalStart(request)
      .then((t) => live && setTerm(t))
      .catch((exc: unknown) => live && setError(errorMessage(exc)));
    return () => {
      live = false;
    };
  }, [request.server, request.key, request.shell]); // eslint-disable-line react-hooks/exhaustive-deps

  const stop = async () => {
    if (term) await api.onpremTerminalStop(term.name).catch((exc: unknown) => toast(errorMessage(exc), "err"));
    onClose();
  };

  return (
    <Drawer
      open
      title={term ? `Terminal: ${term.title}` : "Starting a terminal…"}
      onClose={onClose}
      actions={
        <span className="row-gap">
          {term?.url && (
            <a className="btn" href={term.url} target="_blank" rel="noreferrer noopener">
              Open in a new tab
            </a>
          )}
          <button type="button" className="btn btn-danger" onClick={() => void stop()}>
            Stop terminal
          </button>
        </span>
      }
    >
      {error && (
        <div className="form-error">
          {error}
          <div className="small">The terminal needs Docker on this machine (it runs ttyd in a container).</div>
        </div>
      )}
      {!term && !error && <p className="muted">Starting ttyd in Docker (the first time builds a small image, about a minute)…</p>}
      {term?.url && <iframe className="terminal-frame" src={term.url} title={term.title} />}
      {term && (
        <p className="muted small">
          Listens on 127.0.0.1 only, behind a secret URL. Closing this panel keeps it running (reopen from the link); <b>Stop terminal</b> removes it.
        </p>
      )}
    </Drawer>
  );
}

/** Console for an on-prem service (loads which client it has). */
export function ServiceConsole({ serviceKey, onClose }: { serviceKey: string; onClose: () => void }) {
  const [info, setInfo] = useState<OnPremConsoleInfo | null>(null);
  const [terminal, setTerminal] = useState<{ key: string; shell: boolean } | null>(null);
  useEffect(() => {
    api.onpremConsoleInfo(serviceKey).then(setInfo, () => setInfo({ service: "", available: false, label: "", input: "", examples: [], shell: true, note: "" }));
  }, [serviceKey]);
  if (terminal) return <TerminalDrawer request={terminal} onClose={() => setTerminal(null)} />;
  return (
    <ConsoleDrawer
      title={`Console: ${serviceKey}`}
      info={info}
      run={(line, shell) => api.onpremConsole(serviceKey, line, shell)}
      onTerminal={(shell) => setTerminal({ key: serviceKey, shell })}
      onClose={onClose}
    />
  );
}
