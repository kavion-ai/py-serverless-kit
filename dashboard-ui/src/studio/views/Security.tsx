// Accounts, permissions per feature, the audit log and the account's own password.
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ErrorBanner, Spinner } from "../../components/Feedback";
import { api, errorMessage, type AuditEntry, type FeatureInfo, type VaultUser } from "../api";
import { MIN_PASSWORD, useAuth } from "../auth";
import { useConfirm, useToast } from "../components/Feedback";

const LETTERS: { letter: string; label: string }[] = [
  { letter: "c", label: "Create" },
  { letter: "r", label: "Read" },
  { letter: "u", label: "Update" },
  { letter: "d", label: "Delete" },
];

type Perms = Record<string, string>;

function toggled(letters: string, letter: string): string {
  const next = letters.includes(letter) ? letters.replace(letter, "") : letters + letter;
  return "crud".split("").filter((c) => next.includes(c)).join("");
}

function PermissionGrid({ features, value, onChange, disabled }: { features: FeatureInfo[]; value: Perms; onChange: (p: Perms) => void; disabled?: boolean }) {
  return (
    <table className="table perm-grid">
      <thead>
        <tr>
          <th>Feature</th>
          {LETTERS.map((l) => (
            <th key={l.letter}>{l.label}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {features.map((f) => (
          <tr key={f.name}>
            <td>
              <b>{f.label}</b>
              {f.full_access && <span className="badge badge-warn"> full access</span>}
              <div className="muted small">{f.help}</div>
            </td>
            {LETTERS.map((l) => {
              const on = (value[f.name] || "").includes(l.letter);
              return (
                <td key={l.letter}>
                  <input
                    type="checkbox"
                    aria-label={`${l.label} on ${f.label}`}
                    checked={on}
                    disabled={disabled}
                    onChange={() => onChange({ ...value, [f.name]: toggled(value[f.name] || "", l.letter) })}
                  />
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** The account's permissions in words, always visible, so an admin sees what it can really do. */
function PermissionSummary({ features, value }: { features: FeatureInfo[]; value: Perms }) {
  const parts = features
    .filter((f) => value[f.name])
    .map((f) => `${f.label}: ${LETTERS.filter((l) => value[f.name].includes(l.letter)).map((l) => l.label.toLowerCase()).join(", ")}`);
  return (
    <div className="small">
      <b>Can do:</b> {parts.length ? parts.join(" · ") : "read pskit.yml only"}
    </div>
  );
}

function UserEditor(props: { user: VaultUser; features: FeatureInfo[]; presets: Record<string, Perms>; me: string; onChanged: () => void }) {
  const { user, features, presets, me, onChanged } = props;
  const toast = useToast();
  const confirm = useConfirm();
  const [perms, setPerms] = useState<Perms>(user.permissions);
  const [newPassword, setNewPassword] = useState("");
  useEffect(() => setPerms(user.permissions), [user]);
  const run = async (what: string, call: () => Promise<unknown>) => {
    try {
      await call();
      toast(what, "ok");
      onChanged();
    } catch (exc) {
      toast(errorMessage(exc), "err");
    }
  };
  const changed = JSON.stringify(sorted(perms)) !== JSON.stringify(sorted(user.permissions));
  return (
    <div className="card card-pad stack">
      <div className="row-gap">
        <b className="grow">
          {user.username}
          {user.disabled && <span className="badge"> disabled</span>}
          {user.must_change && <span className="badge"> must set password</span>}
        </b>
        <select
          className="input"
          aria-label={`Role of ${user.username}`}
          value={user.role}
          onChange={(e) => void run("Role changed", () => api.authUpdateUser(user.username, { role: e.target.value }))}
        >
          <option value="user">user</option>
          <option value="admin">admin</option>
        </select>
        <button
          type="button"
          className="btn btn-sm"
          disabled={user.username === me}
          onClick={() => void run(user.disabled ? "Enabled" : "Disabled", () => api.authUpdateUser(user.username, { disabled: !user.disabled }))}
        >
          {user.disabled ? "Enable" : "Disable"}
        </button>
        <button
          type="button"
          className="btn btn-sm btn-danger"
          disabled={user.username === me}
          onClick={() => {
            void confirm({
              title: `Remove ${user.username}?`,
              body: "The data this account could read gets new keys. It may already have copies, so change those secrets too.",
              danger: true,
              confirmLabel: "Remove",
            }).then((yes) => {
              if (yes) void run("Removed", () => api.authRemoveUser(user.username));
            });
          }}
        >
          Remove
        </button>
      </div>
      {user.role !== "admin" && <PermissionSummary features={features} value={user.permissions} />}
      <div className="muted small">Holds keys for: {user.areas.join(", ") || "nothing"}. Created by {user.created_by}.</div>
      {user.role === "admin" ? (
        <p className="muted small">Admins can do everything.</p>
      ) : (
        <details>
          <summary>Permissions</summary>
          <div className="row-gap">
            <span className="muted small">Start from:</span>
            {Object.keys(presets).map((name) => (
              <button key={name} type="button" className="btn btn-sm" onClick={() => setPerms(presets[name])}>
                {name}
              </button>
            ))}
            <button type="button" className="btn btn-sm" onClick={() => setPerms({})}>
              none
            </button>
          </div>
          <PermissionGrid features={features} value={perms} onChange={setPerms} />
          <p className="muted small">
            Removing read from a feature that decrypts data re-encrypts that data with a new key. Anything with write or deploy access to code or secrets can reach
            more than its grid says: treat <b>deploy</b> as trusted.
          </p>
          <button type="button" className="btn btn-primary btn-sm" disabled={!changed} onClick={() => void run("Permissions saved", () => api.authUpdateUser(user.username, { permissions: perms }))}>
            Save permissions
          </button>
        </details>
      )}
      <form
        className="row-gap"
        onSubmit={(e) => {
          e.preventDefault();
          void run("Password reset; they must choose a new one at login", () => api.authResetPassword(user.username, newPassword)).then(() => setNewPassword(""));
        }}
      >
        <input
          className="input grow"
          type="password"
          placeholder={`New first password (at least ${MIN_PASSWORD} characters)`}
          aria-label={`New password for ${user.username}`}
          autoComplete="new-password"
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
        />
        <button type="submit" className="btn btn-sm" disabled={newPassword.length < MIN_PASSWORD}>
          Reset password
        </button>
      </form>
    </div>
  );
}

function sorted(p: Perms): [string, string][] {
  return Object.entries(p)
    .filter(([, v]) => v)
    .sort(([a], [b]) => a.localeCompare(b));
}

function NewUser({ features, presets, onCreated }: { features: FeatureInfo[]; presets: Record<string, Perms>; onCreated: () => void }) {
  const toast = useToast();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("user");
  // Nothing ticked: an account gets only what the admin chose, never a preset by surprise.
  const [perms, setPerms] = useState<Perms>({});
  const [error, setError] = useState<string | null>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await api.authAddUser(username, password, role, perms);
      toast(`Added ${username}. Give them the master key and this first password.`, "ok");
      setUsername("");
      setPassword("");
      setError(null);
      onCreated();
    } catch (exc) {
      setError(errorMessage(exc));
    }
  };
  return (
    <details className="card card-pad">
      <summary>
        <b>Add a user</b>
      </summary>
      {error && <ErrorBanner message={error} />}
      <form className="stack" onSubmit={(e) => void submit(e)}>
        <div className="row-gap">
          <input className="input" placeholder="Username" aria-label="Username" autoComplete="off" value={username} onChange={(e) => setUsername(e.target.value)} />
          <input
            className="input grow"
            type="password"
            placeholder={`First password (at least ${MIN_PASSWORD} characters)`}
            aria-label="First password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <select className="input" aria-label="Role" value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="user">user</option>
            <option value="admin">admin</option>
          </select>
        </div>
        {role === "user" && (
          <>
            <div className="row-gap">
              <span className="muted small">Start from:</span>
              {Object.keys(presets).map((name) => (
                <button key={name} type="button" className="btn btn-sm" onClick={() => setPerms(presets[name])}>
                  {name}
                </button>
              ))}
              <button type="button" className="btn btn-sm" onClick={() => setPerms({})}>
                none
              </button>
            </div>
            <PermissionGrid features={features} value={perms} onChange={setPerms} />
            <PermissionSummary features={features} value={perms} />
          </>
        )}
        <button type="submit" className="btn btn-primary" disabled={!username || password.length < MIN_PASSWORD}>
          Add user
        </button>
      </form>
    </details>
  );
}

function Users() {
  const { status } = useAuth();
  const toast = useToast();
  const confirm = useConfirm();
  const [users, setUsers] = useState<VaultUser[] | null>(null);
  const [features, setFeatures] = useState<FeatureInfo[]>([]);
  const [presets, setPresets] = useState<Record<string, Perms>>({});
  const [error, setError] = useState<string | null>(null);
  const [newKey, setNewKey] = useState<string | null>(null);
  const [newCode, setNewCode] = useState<string | null>(null);
  const load = useCallback(() => {
    Promise.all([api.authUsers(), api.authFeatures()]).then(
      ([u, f]) => {
        setUsers(u.users);
        setFeatures(f.features);
        setPresets(f.presets);
        setError(null);
      },
      (exc: unknown) => setError(errorMessage(exc)),
    );
  }, []);
  useEffect(load, [load]);
  if (error) return <ErrorBanner message={error} onRetry={load} />;
  if (!users) return <Spinner />;
  const rotate = () => {
    void confirm({
      title: "Replace the master key?",
      body: "Every developer needs the new key after they pull. Do this when someone with the key has left.",
      danger: true,
      confirmLabel: "Replace it",
    }).then((yes) => {
      if (!yes) return;
      api.authRotateMaster().then((r) => setNewKey(r.master_key), (exc: unknown) => toast(errorMessage(exc), "err"));
    });
  };
  const rotateRecovery = () => {
    void confirm({
      title: "Replace the recovery code?",
      body: "The old code stops working and all encrypted data gets new keys. Do this when the code leaked or was lost. Teammates keep their passwords and the master key.",
      danger: true,
      confirmLabel: "Replace it",
    }).then((yes) => {
      if (!yes) return;
      api.authRotateRecovery().then((r) => setNewCode(r.recovery_code), (exc: unknown) => toast(errorMessage(exc), "err"));
    });
  };
  return (
    <div className="stack">
      <NewUser features={features} presets={presets} onCreated={load} />
      {users.map((u) => (
        <UserEditor key={u.username} user={u} features={features} presets={presets} me={status.user || ""} onChanged={load} />
      ))}
      <div className="card card-pad stack">
        <b>Master key</b>
        {newKey ? (
          <>
            <p>
              <b>Copy the new key now, it is shown only once.</b> Commit <code className="mono">.pskit-vault/</code> and give it to the developers.
            </p>
            <code className="mono auth-secret-value">{newKey}</code>
          </>
        ) : (
          <button type="button" className="btn btn-danger btn-sm" onClick={rotate}>
            Replace the master key
          </button>
        )}
      </div>
      <div className="card card-pad stack">
        <b>Recovery code</b>
        {newCode ? (
          <>
            <p>
              <b>Copy the new code now, it is shown only once.</b> Keep it offline, then commit and push <code className="mono">.pskit-vault/</code>.
            </p>
            <code className="mono auth-secret-value">{newCode}</code>
          </>
        ) : (
          <button type="button" className="btn btn-danger btn-sm" onClick={rotateRecovery}>
            Replace the recovery code
          </button>
        )}
      </div>
    </div>
  );
}

function Audit() {
  const [entries, setEntries] = useState<AuditEntry[] | null>(null);
  const [tampered, setTampered] = useState<string[]>([]);
  const [user, setUser] = useState("");
  const [action, setAction] = useState("");
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => {
    api.authAudit(user, action).then(
      (r) => {
        setEntries(r.entries);
        setTampered(r.tampered);
        setError(null);
      },
      (exc: unknown) => setError(errorMessage(exc)),
    );
  }, [user, action]);
  useEffect(load, [load]);
  if (error) return <ErrorBanner message={error} onRetry={load} />;
  return (
    <div className="stack">
      {tampered.length > 0 && <div className="notice notice-warn">These audit files were changed after they were written: {tampered.join(", ")}</div>}
      <div className="row-gap">
        <input className="input" placeholder="User" aria-label="Filter by user" value={user} onChange={(e) => setUser(e.target.value)} />
        <input className="input" placeholder="Action, like deploy" aria-label="Filter by action" value={action} onChange={(e) => setAction(e.target.value)} />
        <button type="button" className="btn btn-sm" onClick={load}>
          Refresh
        </button>
      </div>
      {!entries ? (
        <Spinner />
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>When (UTC)</th>
              <th>User</th>
              <th>From</th>
              <th>Action</th>
              <th>Target</th>
              <th>Result</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((e, i) => (
              <tr key={i} title={JSON.stringify(e.details)}>
                <td className="mono small">{e.ts}</td>
                <td>{e.user}</td>
                <td className="muted small">{e.source}</td>
                <td className="mono small">{e.action}</td>
                <td className="mono small">{String(e.details.path || e.target || "")}</td>
                <td className={e.outcome === "ok" ? "muted small" : "small text-danger"}>{e.outcome}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function MyAccount() {
  const { status, logout } = useAuth();
  const toast = useToast();
  const [old, setOld] = useState("");
  const [next, setNext] = useState("");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    api.authPassword(old, next).then(
      () => {
        toast("Password changed", "ok");
        setOld("");
        setNext("");
      },
      (exc: unknown) => toast(errorMessage(exc), "err"),
    );
  };
  const sync = () => {
    api.authSync().then(
      (r) => toast(`${r.written.length} file(s) updated from the vault${r.conflicts.length ? `, ${r.conflicts.length} conflict(s) kept as *.vault-conflict` : ""}`, "ok"),
      (exc: unknown) => toast(errorMessage(exc), "err"),
    );
  };
  return (
    <div className="card card-pad stack">
      <div className="row-gap">
        <b className="grow">
          {status.user} ({status.role})
        </b>
        <button type="button" className="btn btn-sm" onClick={sync} title="After a git pull">
          Sync from vault
        </button>
        <button type="button" className="btn btn-sm" onClick={() => void logout()}>
          Log out
        </button>
      </div>
      <div className="muted small">Holds keys for: {(status.areas || []).join(", ") || "nothing"}.</div>
      <form className="row-gap" onSubmit={submit}>
        <input className="input" type="password" placeholder="Current password" aria-label="Current password" autoComplete="current-password" value={old} onChange={(e) => setOld(e.target.value)} />
        <input className="input" type="password" placeholder="New password" aria-label="New password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} />
        <button type="submit" className="btn btn-sm" disabled={!old || next.length < MIN_PASSWORD}>
          Change password
        </button>
      </form>
    </div>
  );
}

function AccountsOff() {
  const { refresh } = useAuth();
  const toast = useToast();
  const turnOn = () => {
    api.authMode("accounts").then(() => refresh(), (exc: unknown) => toast(errorMessage(exc), "err"));
  };
  return (
    <div className="stack">
      <h2>Users &amp; audit</h2>
      <div className="card card-pad stack">
        <b>Accounts are off</b>
        <p className="muted">
          This project has no login. Nothing is encrypted or logged, and <code className="mono">.env</code> and <code className="mono">.pskit</code> stay on this computer. Turn accounts on to share them with a team through git.
        </p>
        <div>
          <button type="button" className="btn btn-primary" onClick={turnOn}>
            Turn on accounts
          </button>
        </div>
      </div>
    </div>
  );
}

export function SecurityView() {
  const { status, can } = useAuth();
  const [tab, setTab] = useState<"account" | "users" | "audit">("account");
  if (status.state === "open") return <AccountsOff />;
  return (
    <div className="stack">
      <h2>Users &amp; audit</h2>
      <div className="row-gap" role="tablist">
        <button type="button" role="tab" aria-selected={tab === "account"} className={tab === "account" ? "btn btn-primary btn-sm" : "btn btn-sm"} onClick={() => setTab("account")}>
          My account
        </button>
        {status.role === "admin" && (
          <button type="button" role="tab" aria-selected={tab === "users"} className={tab === "users" ? "btn btn-primary btn-sm" : "btn btn-sm"} onClick={() => setTab("users")}>
            Users &amp; permissions
          </button>
        )}
        {can("audit", "r") && (
          <button type="button" role="tab" aria-selected={tab === "audit"} className={tab === "audit" ? "btn btn-primary btn-sm" : "btn btn-sm"} onClick={() => setTab("audit")}>
            Audit log
          </button>
        )}
      </div>
      {tab === "account" && <MyAccount />}
      {tab === "users" && <Users />}
      {tab === "audit" && <Audit />}
    </div>
  );
}
