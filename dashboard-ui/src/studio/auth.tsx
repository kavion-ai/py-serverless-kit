// First-run admin, login with the master key, forced password change, and what the logged-in account may do.
import { createContext, useCallback, useContext, useEffect, useState, type FormEvent, type ReactNode } from "react";
import { ErrorBanner, Spinner } from "../components/Feedback";
import { api, ApiError, errorMessage, MOCK, setSession, type AuthStatus, type VaultSetupResult } from "./api";

export const MIN_PASSWORD = 12;

interface AuthValue {
  status: AuthStatus;
  /** Does this account have this letter of crud on this feature? */
  can: (feature: string, action: "c" | "r" | "u" | "d") => boolean;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const FULL: AuthStatus = { state: "ready", user: "mock", role: "admin", permissions: {}, areas: [] };
const AuthContext = createContext<AuthValue>({ status: FULL, can: () => true, logout: async () => {}, refresh: async () => {} });

export function useAuth(): AuthValue {
  return useContext(AuthContext);
}

function Screen({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="center-screen">
      <div className="card card-pad auth-card">
        <div className="logo logo-lg" aria-hidden="true">
          λ
        </div>
        <h1>{title}</h1>
        {children}
      </div>
    </div>
  );
}

function Field(props: { label: string; value: string; onChange: (v: string) => void; type?: string; hint?: string; autoComplete?: string; autoFocus?: boolean }) {
  return (
    <label className="field">
      <span className="field-label">{props.label}</span>
      <input
        className="input"
        type={props.type || "text"}
        value={props.value}
        autoComplete={props.autoComplete}
        autoFocus={props.autoFocus}
        spellCheck={false}
        onChange={(e) => props.onChange(e.target.value)}
      />
      {props.hint && <span className="muted small">{props.hint}</span>}
    </label>
  );
}

function passwordProblem(password: string, again: string): string | null {
  if (password.length < MIN_PASSWORD) return `The password needs at least ${MIN_PASSWORD} characters.`;
  if (password !== again) return "The two passwords are different.";
  return null;
}

function ChoiceScreen({ onSolo, onTeam }: { onSolo: () => void; onTeam: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const solo = () => {
    api.authMode("none").then(onSolo, (exc: unknown) => setError(errorMessage(exc)));
  };
  return (
    <Screen title="Who will use this project?">
      {error && <ErrorBanner message={error} />}
      <button type="button" className="auth-choice" onClick={solo}>
        <b>Just me, on this computer</b>
        <span className="muted small">
          No login and no master key. Nothing is encrypted, and <code className="mono">.env</code> and <code className="mono">.pskit</code> stay on this computer, out of git.
        </span>
      </button>
      <button type="button" className="auth-choice" onClick={onTeam}>
        <b>A team, sharing through git</b>
        <span className="muted small">
          An admin account, users with permissions and an audit log. <code className="mono">.env</code> and <code className="mono">.pskit</code> data is encrypted, so it can be committed.
        </span>
      </button>
      <p className="muted small">You can turn accounts on later.</p>
    </Screen>
  );
}

function SetupScreen({ onCreated }: { onCreated: (r: VaultSetupResult) => void }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [again, setAgain] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const problem = passwordProblem(password, again);
    if (problem) return setError(problem);
    setBusy(true);
    setError(null);
    try {
      onCreated(await api.authSetup(username, password));
    } catch (exc) {
      setError(errorMessage(exc));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Screen title="Create the admin account">
      <p className="muted">
        This is the first start of this project. The admin account manages users and permissions. <code className="mono">.env</code> files and{" "}
        <code className="mono">.pskit</code> settings get encrypted into <code className="mono">.pskit-vault/</code>, which is safe to commit.
      </p>
      {error && <ErrorBanner message={error} />}
      <form onSubmit={(e) => void submit(e)} className="stack">
        <Field label="Username" value={username} onChange={setUsername} autoComplete="username" autoFocus />
        <Field label="Password" type="password" value={password} onChange={setPassword} autoComplete="new-password" hint={`At least ${MIN_PASSWORD} characters.`} />
        <Field label="Password again" type="password" value={again} onChange={setAgain} autoComplete="new-password" />
        <button type="submit" className="btn btn-primary" disabled={busy || !username || !password}>
          {busy ? "Creating…" : "Create admin"}
        </button>
      </form>
    </Screen>
  );
}

function Secret({ label, value, help }: { label: string; value: string; help: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    void navigator.clipboard?.writeText(value).then(() => setCopied(true));
  };
  return (
    <div className="auth-secret">
      <div className="row-gap">
        <b className="grow">{label}</b>
        <button type="button" className="btn btn-sm" onClick={copy}>
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <code className="mono auth-secret-value">{value}</code>
      <p className="muted small">{help}</p>
    </div>
  );
}

function KeysScreen({ result, onDone }: { result: VaultSetupResult; onDone: () => void }) {
  const [saved, setSaved] = useState(false);
  return (
    <Screen title="Copy these now">
      <p>
        <b>They are shown only this once and cannot be recovered.</b>
      </p>
      <Secret
        label="Master key"
        value={result.master_key}
        help="Needed at every login, and pskit does not save it, so keep it in a password manager. Give it to each developer of this project over a safe channel. Do not commit it."
      />
      <Secret
        label="Recovery code"
        value={result.recovery_code}
        help="Keep this offline and to yourself. Together with the master key, it sets a new admin password if every admin password is lost. It cannot replace a lost master key."
      />
      {result.tracked_plaintext.length > 0 && (
        <div className="notice notice-warn">
          Git already tracks these files, so their plaintext is still pushed and is in your history. Run{" "}
          <code className="mono">git rm --cached</code> on them and change those secrets: {result.tracked_plaintext.join(", ")}
        </div>
      )}
      <p className="muted small">
        Encrypted {result.sealed.length} existing file{result.sealed.length === 1 ? "" : "s"}. Commit the <code className="mono">.pskit-vault/</code> folder.
      </p>
      <label className="row-gap">
        <input type="checkbox" checked={saved} onChange={(e) => setSaved(e.target.checked)} />
        <span>I saved the master key and the recovery code.</span>
      </label>
      <button type="button" className="btn btn-primary" disabled={!saved} onClick={onDone}>
        Continue
      </button>
    </Screen>
  );
}

function RecoverForm({ onDone }: { onDone: () => void }) {
  const [masterKey, setMasterKey] = useState("");
  const [code, setCode] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [again, setAgain] = useState("");
  const [error, setError] = useState<string | null>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const problem = passwordProblem(password, again);
    if (problem) return setError(problem);
    try {
      await api.authRecover(masterKey, code, username, password);
      onDone();
    } catch (exc) {
      setError(errorMessage(exc));
    }
  };
  return (
    <form onSubmit={(e) => void submit(e)} className="stack">
      {error && <ErrorBanner message={error} />}
      <Field label="Master key" type="password" value={masterKey} onChange={setMasterKey} autoComplete="off" />
      <Field label="Recovery code" type="password" value={code} onChange={setCode} />
      <Field label="Admin username" value={username} onChange={setUsername} />
      <Field label="New password" type="password" value={password} onChange={setPassword} autoComplete="new-password" />
      <Field label="New password again" type="password" value={again} onChange={setAgain} autoComplete="new-password" />
      <button type="submit" className="btn btn-primary">
        Set the new password
      </button>
    </form>
  );
}

function LoginScreen({ onIn }: { onIn: (conflicts: string[]) => void }) {
  const [masterKey, setMasterKey] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [recovering, setRecovering] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await api.authLogin(masterKey, username, password);
      onIn(result.conflicts || []);
    } catch (exc) {
      setError(errorMessage(exc));
    } finally {
      setBusy(false);
    }
  };
  if (recovering) {
    return (
      <Screen title="Recover an admin account">
        <RecoverForm onDone={() => setRecovering(false)} />
        <button type="button" className="btn btn-ghost" onClick={() => setRecovering(false)}>
          Back to log in
        </button>
      </Screen>
    );
  }
  return (
    <Screen title="Log in">
      {error && <ErrorBanner message={error} />}
      <form onSubmit={(e) => void submit(e)} className="stack">
        <Field label="Master key" type="password" value={masterKey} onChange={setMasterKey} autoComplete="off" autoFocus hint="Ask your admin if you do not have it." />
        <Field label="Username" value={username} onChange={setUsername} autoComplete="username" />
        <Field label="Password" type="password" value={password} onChange={setPassword} autoComplete="current-password" />
        <button type="submit" className="btn btn-primary" disabled={busy || !masterKey || !username || !password}>
          {busy ? "Unlocking…" : "Log in"}
        </button>
      </form>
      <button type="button" className="btn btn-ghost btn-sm" onClick={() => setRecovering(true)}>
        Lost every admin password?
      </button>
    </Screen>
  );
}

function PasswordScreen({ onDone }: { onDone: () => void }) {
  const [old, setOld] = useState("");
  const [password, setPassword] = useState("");
  const [again, setAgain] = useState("");
  const [error, setError] = useState<string | null>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const problem = passwordProblem(password, again);
    if (problem) return setError(problem);
    try {
      await api.authPassword(old, password);
      onDone();
    } catch (exc) {
      setError(errorMessage(exc));
    }
  };
  return (
    <Screen title="Choose your own password">
      <p className="muted">Your admin set your first password. Replace it to continue.</p>
      {error && <ErrorBanner message={error} />}
      <form onSubmit={(e) => void submit(e)} className="stack">
        <Field label="Password from your admin" type="password" value={old} onChange={setOld} autoComplete="current-password" autoFocus />
        <Field label="New password" type="password" value={password} onChange={setPassword} autoComplete="new-password" hint={`At least ${MIN_PASSWORD} characters.`} />
        <Field label="New password again" type="password" value={again} onChange={setAgain} autoComplete="new-password" />
        <button type="submit" className="btn btn-primary">
          Save
        </button>
      </form>
    </Screen>
  );
}

/** Nothing of the studio renders, or is requested, before this account is ready. */
export function AuthGate({ children, onTokenMissing }: { children: ReactNode; onTokenMissing: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus | null>(MOCK ? FULL : null);
  const [keys, setKeys] = useState<VaultSetupResult | null>(null);
  const [conflicts, setConflicts] = useState<string[]>([]);
  const [failed, setFailed] = useState<string | null>(null);
  const [needsToken, setNeedsToken] = useState(false);
  const [teamChosen, setTeamChosen] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setStatus(await api.authStatus());
      setFailed(null);
    } catch (exc) {
      if (exc instanceof ApiError && exc.status === 401 && exc.code === "token") setNeedsToken(true);
      else setFailed(errorMessage(exc));
    }
  }, []);

  useEffect(() => {
    if (MOCK) return;
    void refresh();
    const onLost = () => void refresh();
    window.addEventListener("pskit-auth-lost", onLost);
    return () => window.removeEventListener("pskit-auth-lost", onLost);
  }, [refresh]);

  const logout = useCallback(async () => {
    await api.authLogout().catch(() => undefined);
    setSession(null);
    await refresh();
  }, [refresh]);

  if (needsToken) return <>{onTokenMissing}</>;
  if (failed) return <div className="center-screen"><ErrorBanner message={failed} onRetry={() => void refresh()} /></div>;
  if (!status) return <div className="center-screen"><Spinner /></div>;
  if (keys) {
    return (
      <KeysScreen
        result={keys}
        onDone={() => {
          setKeys(null);
          void refresh();
        }}
      />
    );
  }
  if (status.state === "setup") {
    if (!teamChosen) return <ChoiceScreen onSolo={() => void refresh()} onTeam={() => setTeamChosen(true)} />;
    return <SetupScreen onCreated={setKeys} />;
  }
  if (status.state === "login") {
    return (
      <LoginScreen
        onIn={(found) => {
          setConflicts(found);
          void refresh();
        }}
      />
    );
  }
  if (status.state === "password_change") return <PasswordScreen onDone={() => void refresh()} />;
  const can: AuthValue["can"] = (feature, action) => MOCK || status.state === "open" || (status.permissions?.[feature] || "").includes(action);
  return (
    <AuthContext.Provider value={{ status, can, logout, refresh }}>
      {conflicts.length > 0 && (
        <div className="notice notice-warn">
          Your local copy and the vault both changed. The vault's version is in place, and yours is kept next to it as <code className="mono">*.vault-conflict</code>: {conflicts.join(", ")}
        </div>
      )}
      {children}
    </AuthContext.Provider>
  );
}
