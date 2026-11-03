import { useCallback, useEffect, useState } from "react";
import { ErrorBanner, Spinner } from "../../components/Feedback";
import { api, errorMessage } from "../api";
import { JobConsole } from "../components/Console";
import { useConfirm, useToast } from "../components/Feedback";
import { ComboInput, FieldForm, FormRow, Section, Segmented, TextInput, Toggle } from "../components/Forms";
import { PageHeader } from "../components/Misc";
import { useJob } from "../jobs";
import { href } from "../route";
import { useStudio } from "../store";
import type { DevEnvStatus, EnvHint, JsonObject, SettingsPreview, SettingsSummary, SetupCheck, SetupResult } from "../types";
import { asObject, getIn, str } from "../util";

type Os = "windows" | "macos" | "linux";
const OS_LABEL: Record<Os, string> = { windows: "Windows", macos: "macOS", linux: "Linux" };
const STATUS: Record<string, { icon: string; tone: string; label: string }> = {
  ok: { icon: "✓", tone: "ok", label: "ready" },
  missing: { icon: "✗", tone: "err", label: "missing" },
  warning: { icon: "!", tone: "warn", label: "check" },
  info: { icon: "i", tone: "info", label: "optional" },
};

const ACTION_LABEL: Record<string, string> = {
  "ssh-test": "Test connection",
  "aws-profile": "Add credentials",
  env: "Set variables",
  "az-login": "Sign in (az login)",
  "gcloud-login": "Sign in (gcloud)",
  "gcloud-adc": "Sign in (gcloud ADC)",
  "aws-sso-login": "Sign in (aws sso)",
};

function guessOs(): Os {
  const ua = navigator.userAgent;
  if (/Windows/i.test(ua)) return "windows";
  if (/Mac/i.test(ua)) return "macos";
  return "linux";
}

function copy(text: string, toast: ReturnType<typeof useToast>) {
  navigator.clipboard.writeText(text).then(
    () => toast("Copied", "ok"),
    () => toast("Copy failed: select the text instead", "warn"),
  );
}

/** Prerequisites and credentials for the target provider, with install steps and ways to fix them in place. */
export function SetupView() {
  const { state, meta, draft } = useStudio();
  const toast = useToast();
  const target = state.target?.provider || str(getIn(draft, ["provider", "name"]), "aws");
  const [provider, setProvider] = useState(target);
  const [result, setResult] = useState<SetupResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [os, setOs] = useState<Os>(guessOs);
  const [jobId, setJobId] = useState<string | null>(null);
  const job = useJob(jobId);

  useEffect(() => setProvider(target), [target]);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    api
      .setup(provider)
      .then((r) => {
        setResult(r);
        if (r.platform) setOs(r.platform);
      })
      .catch((exc: unknown) => setError(errorMessage(exc)))
      .finally(() => setLoading(false));
  }, [provider]);
  useEffect(load, [load]);
  // A login or SSH test finished: check again.
  useEffect(() => {
    if (job.status === "succeeded") load();
  }, [job.status, load]);

  const deploy = (() => {
    const raw = asObject(getIn(draft, ["provider", "options"])).deploy;
    return typeof raw === "string" ? { method: raw } : asObject(raw);
  })();

  const runAction = (action: string) => {
    // Some fixes are forms on this page rather than commands.
    const form = action === "aws-profile" ? "setup-aws" : action === "env" ? "setup-env" : null;
    if (form) {
      const el = document.getElementById(form);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "start" });
        const toggle = el.querySelector<HTMLButtonElement>(".section-toggle[aria-expanded='false']");
        toggle?.click();
      }
      return;
    }
    const call = action === "ssh-test" ? api.sshTest(deploy) : api.login(action);
    call.then(
      (r) => setJobId(r.job_id),
      (exc: unknown) => toast(errorMessage(exc), "err"),
    );
  };

  const checks = result?.checks || [];
  const missing = checks.filter((c) => c.status === "missing").length;
  const warnings = checks.filter((c) => c.status === "warning").length;
  const name = meta.providers.find((p) => p.name === provider)?.display_name || provider;

  return (
    <div className="page">
      <PageHeader
        title="Setup & credentials"
        subtitle="What this machine needs to deploy: tools, credentials and provider settings. Everything runs where pskit studio runs."
        actions={
          <button type="button" className="btn" onClick={load} disabled={loading}>
            {loading ? "Checking…" : "Check again"}
          </button>
        }
      />
      <div className="row-gap wrap setup-bar">
        <label className="row-gap">
          <span className="muted small">Provider</span>
          <select className="select" value={provider} onChange={(e) => setProvider(e.target.value)}>
            {meta.providers.map((p) => (
              <option key={p.name} value={p.name}>
                {p.display_name}
              </option>
            ))}
          </select>
        </label>
        <Segmented label="Operating system" value={os} onChange={setOs} options={(Object.keys(OS_LABEL) as Os[]).map((o) => ({ value: o, label: OS_LABEL[o] }))} />
        {result && (
          <span className={`badge badge-${missing ? "err" : warnings ? "warn" : "ok"}`}>
            {missing ? `${missing} missing` : warnings ? `${warnings} to check` : `ready to deploy to ${name}`}
          </span>
        )}
      </div>
      {error && <ErrorBanner message={error} onRetry={load} />}
      {loading && !result && <Spinner label="Checking this machine…" />}
      {jobId && (
        <Section title={`Running: ${job.command || "command"}`} hint="the output of the last login / test">
          <JobConsole job={job} onCancel={() => void api.cancelJob(jobId).catch(() => undefined)} />
        </Section>
      )}
      {checks.length > 0 && (
        <Section title="Checks" hint={`${checks.length} for ${name}`}>
          <ul className="check-list">
            {checks.map((c) => (
              <CheckRow key={c.id} check={c} os={os} onAction={runAction} busy={job.status === "running"} />
            ))}
          </ul>
        </Section>
      )}
      {provider === "aws" && (
        <div id="setup-aws">
          <AwsProfileForm regions={meta.providers.find((p) => p.name === "aws")?.regions || []} onSaved={load} />
        </div>
      )}
      {result?.env && result.env.length > 0 && (
        <div id="setup-env">
          <EnvForm hints={result.env} onSaved={load} />
        </div>
      )}
      <ProjectEnv />
      {provider === "onprem" && <OnPremConnection />}
      <SettingsTransfer />
    </div>
  );
}

const MIN_PASSPHRASE = 8;

/** Export / import the settings `.pskit` keeps out of git (servers, clusters, services, SSH logins) as one encrypted file. */
export function SettingsTransfer() {
  const toast = useToast();
  const confirm = useConfirm();
  const [passphrase, setPassphrase] = useState("");
  const [again, setAgain] = useState("");
  const [exporting, setExporting] = useState(false);
  const [exported, setExported] = useState<SettingsSummary | null>(null);
  const [includeConfig, setIncludeConfig] = useState(true);
  const [file, setFile] = useState<{ name: string; content: string } | null>(null);
  const [importPass, setImportPass] = useState("");
  const [replace, setReplace] = useState(false);
  const [plan, setPlan] = useState<SettingsPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const doExport = async () => {
    setExporting(true);
    try {
      const r = await api.settingsExport(passphrase, includeConfig);
      const url = URL.createObjectURL(new Blob([r.content], { type: "application/json" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = r.filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setExported(r.summary);
      setPassphrase("");
      setAgain("");
      toast(`Downloaded ${r.filename}`, "ok");
    } catch (exc) {
      toast(errorMessage(exc), "err");
    } finally {
      setExporting(false);
    }
  };

  const pick = (picked: File | undefined) => {
    setPlan(null);
    setError(null);
    if (!picked) return setFile(null);
    picked.text().then(
      (content) => setFile({ name: picked.name, content }),
      () => setError("could not read that file"),
    );
  };

  const doPreview = async (mode = replace) => {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      setPlan(await api.settingsPreview(file.content, importPass, mode));
    } catch (exc) {
      setPlan(null);
      setError(errorMessage(exc));
    } finally {
      setBusy(false);
    }
  };

  const doImport = async () => {
    if (!file || !plan) return;
    const removed = Object.values(plan.stores).reduce((n, s) => n + (s.remove?.length || 0), 0);
    const ok = await confirm({
      title: "Import these settings?",
      body: `${plan.changes.length} file(s) are written into this project${removed ? `, and ${removed} saved entr${removed === 1 ? "y" : "ies"} not in the file are removed` : ""}. The current settings are backed up to .pskit/backups first.`,
      confirmLabel: "Import",
      danger: removed > 0,
    });
    if (ok !== "confirm") return;
    setBusy(true);
    try {
      const r = await api.settingsImport(file.content, importPass, replace);
      toast(`Imported ${r.written.length} file(s)${r.backup ? `; previous settings in ${r.backup}` : ""}`, "ok");
      // pskit.yml came with it: show the imported project, not the old draft.
      if (r.written.some((w) => /^pskit\.ya?ml$/.test(w))) window.setTimeout(() => window.location.reload(), 1200);
      setPlan(null);
      setFile(null);
      setImportPass("");
    } catch (exc) {
      setError(errorMessage(exc));
    } finally {
      setBusy(false);
    }
  };

  const tooShort = passphrase.length > 0 && passphrase.length < MIN_PASSPHRASE;
  const mismatch = again.length > 0 && again !== passphrase;
  return (
    <Section title="Move settings to another machine" hint="export / import .pskit, encrypted">
      <p className="muted small">
        <code className="mono">.pskit</code> stays out of git, so a fresh clone has no saved servers, clusters, load balancers, on-prem services or SSH
        logins. Export them here, then import the file on the other machine (also from a shell: <code className="mono">pskit settings export</code> /{" "}
        <code className="mono">import</code>). The file holds <b>secrets</b>: SSH passwords and keys (also those in <code className="mono">~/.ssh</code>),
        service passwords and tokens, admin tokens and env files named in <code className="mono">pskit.yml</code>. It is always encrypted with your
        passphrase; send the passphrase another way. Terraform state is not included.
      </p>
      <h4>Export</h4>
      <div className="row-gap wrap">
        <FormRow label="Passphrase" error={tooShort ? `at least ${MIN_PASSPHRASE} characters` : null}>
          <TextInput type="password" value={passphrase} onChange={setPassphrase} invalid={tooShort} />
        </FormRow>
        <FormRow label="Again" error={mismatch ? "does not match" : null}>
          <TextInput type="password" value={again} onChange={setAgain} invalid={mismatch} />
        </FormRow>
        <Toggle checked={includeConfig} onChange={setIncludeConfig} label="Include pskit.yml (functions, resources, providers)" />
        <button
          type="button"
          className="btn btn-primary"
          disabled={exporting || passphrase.length < MIN_PASSPHRASE || again !== passphrase}
          onClick={() => void doExport()}
        >
          {exporting ? "Exporting…" : "Export settings"}
        </button>
      </div>
      {exported && <SettingsContents summary={exported} />}

      <h4>Import</h4>
      <div className="row-gap wrap">
        <FormRow label="Settings file">
          <input type="file" accept=".pskit-settings,.json" onChange={(e) => pick(e.target.files?.[0])} />
        </FormRow>
        <FormRow label="Passphrase">
          <TextInput type="password" value={importPass} onChange={setImportPass} />
        </FormRow>
        <button type="button" className="btn" disabled={!file || !importPass || busy} onClick={() => void doPreview()}>
          {busy && !plan ? "Checking…" : "Preview"}
        </button>
      </div>
      <Toggle
        checked={replace}
        onChange={(on) => {
          setReplace(on);
          if (plan) void doPreview(on);
        }}
        label="Replace: remove saved servers, clusters and services that are not in the file (default: merge, the file's entries win)"
      />
      {error && <div className="form-error">{error}</div>}
      {plan && (
        <>
          <p className="muted small">
            Exported {plan.created_at ? new Date(plan.created_at).toLocaleString() : ""} with pskit {plan.pskit_version || "?"} from{" "}
            <span className="mono">{plan.source_root}</span>.
          </p>
          <table className="table">
            <thead>
              <tr>
                <th>Settings</th>
                <th>Added</th>
                <th>Replaced</th>
                <th>{plan.mode === "replace" ? "Removed" : "Kept"}</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(plan.stores).map(([group, s]) => (
                <tr key={group}>
                  <td className="mono small">{group}</td>
                  <td className="small">{s.add.join(", ") || "–"}</td>
                  <td className="small">{s.replace.join(", ") || "–"}</td>
                  <td className={`small${s.remove?.length ? " warn-text" : ""}`}>{(s.remove || s.keep || []).join(", ") || "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <ul className="small mono">
            {plan.changes.map((c) => (
              <li key={c.path}>
                {c.action === "add" ? "+" : "~"} {c.path}
              </li>
            ))}
            {plan.key_files.map((k) => (
              <li key={k.path}>
                + {k.path} <span className="muted">(SSH key from {k.source})</span>
              </li>
            ))}
          </ul>
          {plan.warnings.map((w) => (
            <div key={w} className="hint-box warn small">
              {w}
            </div>
          ))}
          <button type="button" className="btn btn-primary" disabled={busy} onClick={() => void doImport()}>
            {busy ? "Importing…" : `Import into this project`}
          </button>
        </>
      )}
    </Section>
  );
}

function SettingsContents({ summary }: { summary: SettingsSummary }) {
  return (
    <div className="hint-box small">
      <b>In the file:</b>{" "}
      {Object.entries(summary.entries || {})
        .map(([group, names]) => `${group.replace(/^onprem-/, "")}: ${names.join(", ") || "–"}`)
        .join(" · ") || "no saved servers, clusters or services"}
      {" · "}
      {summary.files.length} file(s){summary.keys.length > 0 && `, ${summary.keys.length} SSH key(s) from outside the project`}
      {summary.warnings.map((w) => (
        <div key={w} className="warn-text">
          {w}
        </div>
      ))}
    </div>
  );
}

function CheckRow({ check, os, onAction, busy }: { check: SetupCheck; os: Os; onAction: (a: string) => void; busy: boolean }) {
  const toast = useToast();
  const s = STATUS[check.status] || STATUS.info;
  const fix = check.fix;
  const [open, setOpen] = useState(check.status === "missing");
  const steps = fix?.steps?.[os] || [];
  const hasFix = !!fix && (!!fix.summary || !!fix.links?.length || steps.length > 0 || !!fix.commands?.length || !!fix.action);
  return (
    <li className={`check-row check-${check.status}`}>
      <div className="row-gap">
        <span className={`check-icon badge badge-${s.tone}`} aria-label={s.label}>
          {s.icon}
        </span>
        <div className="grow">
          <b>{check.title}</b>
          {check.detail && <div className="muted small">{check.detail}</div>}
        </div>
        {fix?.action && check.status !== "ok" && (
          <button type="button" className="btn btn-sm btn-primary" disabled={busy} onClick={() => onAction(fix.action as string)}>
            {ACTION_LABEL[fix.action as string] || "Run"}
          </button>
        )}
        {hasFix && (
          <button type="button" className="btn btn-sm" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
            {open ? "Hide" : check.status === "ok" ? "Details" : "How to fix"}
          </button>
        )}
      </div>
      {open && fix && (
        <div className="check-fix">
          {fix.summary && <p>{fix.summary}</p>}
          {fix.links && fix.links.length > 0 && (
            <div className="chips">
              {fix.links.map((l) => (
                <a key={l.url} className="chip chip-btn" href={l.url} target="_blank" rel="noreferrer noopener">
                  {l.label} ↗
                </a>
              ))}
            </div>
          )}
          {steps.length > 0 && (
            <ol className="steps">
              {steps.map((st, i) => (
                <li key={i}>{st}</li>
              ))}
            </ol>
          )}
          {!steps.length && fix.steps && Object.keys(fix.steps).length > 0 && (
            <p className="muted small">No {OS_LABEL[os]}-specific steps; pick another operating system above.</p>
          )}
          {fix.commands && fix.commands.length > 0 && (
            <div className="stack-xs">
              {fix.commands.map((c) => (
                <div key={c} className="cmd-row">
                  <code className="mono pre-inline">{c}</code>
                  <button type="button" className="btn btn-sm" onClick={() => copy(c, toast)}>
                    Copy
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </li>
  );
}

function AwsProfileForm({ regions, onSaved }: { regions: { id: string; label: string }[]; onSaved: () => void }) {
  const toast = useToast();
  const [profile, setProfile] = useState("default");
  const [keyId, setKeyId] = useState("");
  const [secret, setSecret] = useState("");
  const [region, setRegion] = useState("us-east-1");
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const ok = /^[A-Za-z0-9_.-]{1,64}$/.test(profile) && keyId.trim().length >= 16 && secret.trim().length >= 16;
  const submit = () => {
    setBusy(true);
    api
      .awsProfile({ profile, access_key_id: keyId.trim(), secret_access_key: secret.trim(), region: region || undefined, session_token: token.trim() || undefined })
      .then(
        () => {
          toast(`Saved AWS profile ${profile} in ~/.aws`, "ok");
          setSecret("");
          setToken("");
          onSaved();
        },
        (exc: unknown) => toast(errorMessage(exc), "err"),
      )
      .finally(() => setBusy(false));
  };
  return (
    <Section title="AWS credentials (aws configure)" hint="~/.aws/credentials" defaultOpen={false}>
      <p className="muted small">
        Writes the same files as <code className="mono">aws configure</code>, on this machine. Other profiles are kept. Use the
        profile with <code className="mono">AWS_PROFILE</code> below, or name it <b>default</b>.
      </p>
      <div className="form">
        <FormRow label="Profile" required>
          <ComboInput value={profile} options={["default", "pskit", "dev", "prod"]} onChange={setProfile} />
        </FormRow>
        <FormRow label="Access key ID" required>
          <TextInput mono value={keyId} placeholder="AKIA…" onChange={setKeyId} />
        </FormRow>
        <FormRow label="Secret access key" required>
          <TextInput mono type="password" value={secret} onChange={setSecret} />
        </FormRow>
        <FormRow label="Default region">
          <ComboInput value={region} options={regions.map((r) => ({ value: r.id, label: r.label }))} onChange={setRegion} emptyLabel="none" />
        </FormRow>
        <FormRow label="Session token" help="Only for temporary credentials (STS / SSO).">
          <TextInput mono type="password" value={token} onChange={setToken} />
        </FormRow>
        <div>
          <button type="button" className="btn btn-primary" disabled={!ok || busy} onClick={submit}>
            {busy ? "Saving…" : "Save profile"}
          </button>
        </div>
      </div>
    </Section>
  );
}

function EnvForm({ hints, onSaved }: { hints: EnvHint[]; onSaved: () => void }) {
  return (
    <Section title="Environment variables" hint="read by Terraform and the provider" defaultOpen={hints.some((h) => !h.set)}>
      <p className="muted small">
        <b>Set for this session</b> applies to deploys started from this studio until it stops; nothing is written to disk. To keep
        a value, set it in your shell profile (<code className="mono">export NAME=value</code>, or{" "}
        <code className="mono">setx NAME value</code> on Windows) before starting <code className="mono">pskit studio</code>.
      </p>
      <ul className="check-list">
        {hints.map((h) => (
          <EnvRow key={h.name} hint={h} onSaved={onSaved} />
        ))}
      </ul>
    </Section>
  );
}

function EnvRow({ hint, onSaved }: { hint: EnvHint; onSaved: () => void }) {
  const toast = useToast();
  const [value, setValue] = useState(hint.value || "");
  const save = (v: string) =>
    api.setEnv(hint.name, v).then(
      (r) => {
        toast(r.set ? `${hint.name} set for this session` : `${hint.name} cleared`, "ok");
        if (hint.secret) setValue("");
        onSaved();
      },
      (exc: unknown) => toast(errorMessage(exc), "err"),
    );
  return (
    <li className="check-row">
      <div className="row-gap wrap">
        <span className={`check-icon badge badge-${hint.set ? "ok" : "off"}`}>{hint.set ? "✓" : "–"}</span>
        <div className="grow">
          <code className="mono">{hint.name}</code>
          {hint.help && <div className="muted small">{hint.help}</div>}
        </div>
        <div className="row-gap env-input">
          <TextInput mono type={hint.secret ? "password" : "text"} value={value} placeholder={hint.set && hint.secret ? "•••• (set)" : "value"} onChange={setValue} />
          <button type="button" className="btn btn-sm" disabled={!value} onClick={() => void save(value)}>
            Set for this session
          </button>
          {hint.set && (
            <button type="button" className="btn btn-sm btn-ghost" onClick={() => void save("")}>
              Clear
            </button>
          )}
        </div>
      </div>
    </li>
  );
}

/** The SSH / Docker connection of an on-premises deploy, editable here as well as on Overview. */
function OnPremConnection() {
  const { draft, meta, edit, issuesAt } = useStudio();
  const options = asObject(getIn(draft, ["provider", "options"]));
  const raw = options.deploy;
  const deploy: JsonObject = typeof raw === "string" ? { method: raw } : asObject(raw);
  const method = str(deploy.method, "local");
  const fields = (meta.onprem.deploy_fields[method] || []).filter((f) => ["host", "user", "port", "pem", "known_hosts", "sudo", "docker_host"].includes(f.key));
  const setDeploy = (next: JsonObject) => {
    const clean: JsonObject = {};
    for (const [k, v] of Object.entries(next)) if (v !== undefined && v !== "" && v !== null) clean[k] = v;
    const keys = Object.keys(clean);
    if (!keys.length || (keys.length === 1 && keys[0] === "method")) edit(["provider", "options", "deploy"], !clean.method || clean.method === "local" ? undefined : clean.method);
    else edit(["provider", "options", "deploy"], clean);
  };
  return (
    <Section title="On-premises connection" hint="provider.options.deploy">
      <FormRow label="Where the host runs">
        <Segmented
          label="Deploy method"
          value={method}
          onChange={(m) => setDeploy({ ...deploy, method: m })}
          options={(meta.onprem.deploy_methods.length ? meta.onprem.deploy_methods : ["local", "ssh", "docker"]).map((m) => ({
            value: m,
            label: m === "local" ? "This machine" : m === "ssh" ? "SSH server" : "Docker",
          }))}
        />
      </FormRow>
      {method === "local" ? (
        <p className="muted small">The host runs on this machine: no SSH or Docker needed.</p>
      ) : (
        <FieldForm
          fields={fields}
          value={deploy}
          idPrefix="setup-dep"
          errorsFor={(k) => issuesAt(["provider", "options", "deploy", k]).map((i) => i.message)}
          onChange={(k, v) => setDeploy({ ...deploy, [k]: v === undefined ? "" : v, method })}
        />
      )}
      <p className="muted small">
        More deploy settings (remote path, install mode, image…) are on <a href={href("overview")}>Overview &amp; provider</a>. Save
        pskit.yml after changing them.
      </p>
    </Section>
  );
}

/** The project's own environment: `.venv` + requirements.txt (Python) or `npm install` (Node.js). */
function ProjectEnv() {
  const { draft } = useStudio();
  const toast = useToast();
  const [env, setEnv] = useState<DevEnvStatus | null>(null);
  const [python, setPython] = useState("");
  const [recreate, setRecreate] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const job = useJob(jobId);
  const node = str(asObject(draft.provider).runtime).startsWith("nodejs");
  const load = useCallback(() => {
    api.env().then(
      (r) => {
        setEnv(r);
        setPython((p) => p || r.interpreters[0]?.path || "");
      },
      (exc: unknown) => toast(errorMessage(exc), "err"),
    );
  }, [toast]);
  useEffect(load, [load]);
  useEffect(() => {
    if (job.status === "succeeded" || job.status === "failed") load();
  }, [job.status, load]);
  const run = (language: "python" | "node") =>
    api.envSetup({ language, python: language === "python" ? python || undefined : undefined, recreate }).then(
      (r) => setJobId(r.job_id),
      (exc: unknown) => toast(errorMessage(exc), "err"),
    );
  return (
    <Section title="Project environment" hint={node ? "npm install" : ".venv + requirements"}>
      {!env ? (
        <Spinner label="Looking at the project…" />
      ) : (
        <div className="form">
          {!node && (
            <>
              <FormRow label="Virtual environment" help={env.venv.path}>
                {env.venv.exists ? (
                  <span className="badge badge-ok">Python {env.venv.python || "?"}</span>
                ) : (
                  <span className="badge badge-off">not created</span>
                )}
              </FormRow>
              <FormRow label="Requirements" help={env.requirements.exists ? `${env.requirements.path} is installed into the venv.` : `No ${env.requirements.path}: only pip is updated.`}>
                <span className={`badge badge-${env.requirements.exists ? "ok" : "off"}`}>{env.requirements.exists ? "found" : "missing"}</span>
              </FormRow>
              <FormRow label="Python" help="Interpreters found on this machine.">
                <select className="select select-full" value={python} onChange={(e) => setPython(e.target.value)}>
                  {env.interpreters.map((i) => (
                    <option key={i.path} value={i.path}>
                      Python {i.version} · {i.path}
                    </option>
                  ))}
                </select>
              </FormRow>
              <FormRow label="Recreate">
                <Toggle checked={recreate} onChange={setRecreate} label={recreate ? "delete and recreate .venv" : "reuse .venv if it exists"} />
              </FormRow>
              <div className="row-gap">
                <button type="button" className="btn btn-primary" disabled={job.status === "running" || !env.interpreters.length} onClick={() => void run("python")}>
                  {env.venv.exists && !recreate ? "Install requirements" : "Create .venv and install"}
                </button>
                {env.venv.exists && <span className="muted small">VS Code / your editor: select {env.venv.path} as the interpreter.</span>}
              </div>
            </>
          )}
          {(node || env.package_json) && (
            <>
              <FormRow label="Node.js" help={env.node.path || "not on PATH: install it from https://nodejs.org/"}>
                <span className={`badge badge-${env.node.version ? "ok" : "err"}`}>{env.node.version ? `v${env.node.version}` : "missing"}</span>
              </FormRow>
              <FormRow label="Dependencies" help={env.package_json ? "npm ci when package-lock.json exists, else npm install." : "No package.json in the project."}>
                <span className={`badge badge-${env.node_modules ? "ok" : "off"}`}>{env.node_modules ? "node_modules present" : "not installed"}</span>
              </FormRow>
              <div>
                <button type="button" className="btn btn-primary" disabled={job.status === "running" || !env.node.npm || !env.package_json} onClick={() => void run("node")}>
                  npm install
                </button>
              </div>
            </>
          )}
          {jobId && <JobConsole job={job} />}
        </div>
      )}
    </Section>
  );
}
