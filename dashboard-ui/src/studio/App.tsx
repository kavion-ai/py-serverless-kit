import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Drawer, Modal } from "../components/Drawer";
import { ErrorBanner, Spinner } from "../components/Feedback";
import { api, ApiError, errorMessage, MOCK } from "./api";
import { ConfirmProvider, ToastProvider, useToast } from "./components/Feedback";
import { HanaAvatar } from "./hana/HanaCards";
import { HanaPanel } from "./hana/HanaPanel";
import { IssueList } from "./components/Misc";
import { href, navigate, routeForWhere, useRoute, type View } from "./route";
import { flushHandlerStubs } from "./stubs";
import { StudioProvider, useStudio } from "./store";
import type { Meta, ProjectState } from "./types";
import { asObject, str } from "./util";
import { ClusterView } from "./views/Cluster";
import { CodeView } from "./views/Code";
import { DeployView } from "./views/Deploy";
import { LoadBalancersView } from "./views/LoadBalancers";
import { NetworkView } from "./views/Network";
import { LogsView } from "./views/Logs";
import { FunctionsView } from "./views/Functions";
import { NewProject } from "./views/NewProject";
import { OverviewView } from "./views/Overview";
import { ResourcesView } from "./views/Resources";
import { SettingsTransfer, SetupView } from "./views/Setup";
import { TestView } from "./views/Test";
import { WorkflowsView } from "./views/Workflows";
import { YamlView } from "./views/Yaml";

type Theme = "light" | "dark" | "";

function readTheme(): Theme {
  try {
    const v = window.localStorage.getItem("pskit-theme");
    return v === "light" || v === "dark" ? v : "";
  } catch {
    return "";
  }
}

function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(readTheme);
  useEffect(() => {
    if (theme) document.documentElement.setAttribute("data-theme", theme);
    else document.documentElement.removeAttribute("data-theme");
  }, [theme]);
  const toggle = () => {
    const dark =
      theme === "dark" || (!theme && !!window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
    const next: Theme = dark ? "light" : "dark";
    setTheme(next);
    try {
      window.localStorage.setItem("pskit-theme", next);
    } catch {
      /* per-viewer convenience only */
    }
  };
  return (
    <button type="button" className="btn btn-ghost" onClick={toggle} title="Toggle light/dark theme" aria-label="Toggle theme">
      ◐
    </button>
  );
}

export function StudioApp() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [project, setProject] = useState<ProjectState | null>(null);
  const [error, setError] = useState<ApiError | Error | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let live = true;
    setError(null);
    Promise.all([api.meta(), api.project()])
      .then(([m, p]) => {
        if (!live) return;
        setMeta(m);
        setProject(p);
      })
      .catch((exc: unknown) => live && setError(exc instanceof Error ? exc : new Error(String(exc))));
    return () => {
      live = false;
    };
  }, [attempt]);

  let body: ReactNode;
  if (error instanceof ApiError && error.status === 401) {
    body = <TokenScreen />;
  } else if (error) {
    body = (
      <div className="center-screen">
        <ErrorBanner message={errorMessage(error)} onRetry={() => setAttempt((a) => a + 1)} />
      </div>
    );
  } else if (!meta || !project) {
    body = (
      <div className="center-screen">
        <Spinner label="Loading project…" />
      </div>
    );
  } else if (!project.exists || !project.raw) {
    body = <NewProject meta={meta} onCreated={(p) => setProject(p)} />;
  } else {
    body = (
      <StudioProvider project={project} meta={meta}>
        <Shell />
      </StudioProvider>
    );
  }
  return (
    <ToastProvider>
      <ConfirmProvider>{body}</ConfirmProvider>
    </ToastProvider>
  );
}

function TokenScreen() {
  return (
    <div className="center-screen">
      <div className="card card-pad token-card">
        <div className="logo logo-lg" aria-hidden="true">
          λ
        </div>
        <h1>This studio session needs its link</h1>
        <p className="muted">
          For safety, pskit studio only answers requests that carry the session token from the link it printed when it
          started. Open that link again, or restart:
        </p>
        <pre className="pre">pskit studio --open</pre>
        <p className="muted small">The token lives only in this browser tab and is never written to disk.</p>
      </div>
    </div>
  );
}

const NAV: { view: View; label: string; icon: string }[] = [
  { view: "overview", label: "Overview & provider", icon: "◎" },
  { view: "setup", label: "Setup & credentials", icon: "⚙" },
  { view: "functions", label: "Functions", icon: "λ" },
  { view: "workflows", label: "Workflows", icon: "⇉" },
  { view: "resources", label: "Resources", icon: "▤" },
  { view: "cluster", label: "Scaling cluster", icon: "⧉" },
  { view: "balancers", label: "Load balancers", icon: "⇆" },
  { view: "network", label: "Network map", icon: "⌘" },
  { view: "code", label: "Code", icon: "{}" },
  { view: "test", label: "Test", icon: "▶" },
  { view: "deploy", label: "Deploy", icon: "▲" },
  { view: "logs", label: "Logs", icon: "☰" },
  { view: "yaml", label: "YAML", icon: "≡" },
];

function isEditable(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false;
  return !!el.closest("input, textarea, select, [contenteditable='true'], .cm-editor");
}

function Shell() {
  const studio = useStudio();
  const { state, draft, dirty, meta, save, undo, redo, setTarget, reload, closeConflict } = studio;
  const route = useRoute();
  const toast = useToast();
  const [issuesOpen, setIssuesOpen] = useState(false);
  const [navOpen, setNavOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [hanaOpen, setHanaOpen] = useState(() => {
    try {
      return window.localStorage.getItem("pskit-hana-open") === "1";
    } catch {
      return false;
    }
  });

  useEffect(() => {
    try {
      window.localStorage.setItem("pskit-hana-open", hanaOpen ? "1" : "0");
    } catch {
      /* convenience only */
    }
  }, [hanaOpen]);

  const doSave = useCallback(
    async (force = false) => {
      try {
        const ok = await save(force);
        if (!ok) return;
        const stubs = await flushHandlerStubs();
        toast(stubs ? `Saved pskit.yml · created ${stubs} handler stub${stubs === 1 ? "" : "s"}` : "Saved pskit.yml", "ok");
      } catch (exc) {
        toast(`Save failed: ${errorMessage(exc)}`, "err");
      }
    },
    [save, toast],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.ctrlKey || e.metaKey;
      if (!mod) return;
      const key = e.key.toLowerCase();
      if (key === "i" && !e.shiftKey && !e.altKey && !(e.target instanceof HTMLElement && e.target.closest(".cm-editor"))) {
        e.preventDefault();
        setHanaOpen((o) => !o);
      } else if (key === "s" && route.view !== "code") {
        e.preventDefault();
        if (dirty && !state.saving) void doSave();
      } else if (key === "z" && !isEditable(e.target)) {
        e.preventDefault();
        if (e.shiftKey) redo();
        else undo();
      } else if (key === "y" && !isEditable(e.target)) {
        e.preventDefault();
        redo();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [dirty, state.saving, doSave, undo, redo, route.view]);

  useEffect(() => setNavOpen(false), [route.view]);

  const issues = state.validation?.issues || [];
  const errors = issues.filter((i) => i.level === "error").length;
  const warnings = issues.length - errors;
  const service = str(draft.service, "service");
  const target = state.target || { provider: "aws", stage: "dev" };
  const countFor = (view: View): number | null => {
    if (view === "functions") return Object.keys(asObject(draft.functions)).length;
    if (view === "workflows") return Object.keys(asObject(draft.workflows)).length;
    if (view === "resources") return Object.keys(asObject(draft.resources)).length;
    return null;
  };
  const issueCountFor = (view: View) => issues.filter((i) => routeForWhere(i.where).view === view).length;

  let page: ReactNode;
  switch (route.view) {
    case "functions":
      page = <FunctionsView rest={route.rest} />;
      break;
    case "workflows":
      page = <WorkflowsView rest={route.rest} />;
      break;
    case "resources":
      page = <ResourcesView rest={route.rest} />;
      break;
    case "cluster":
      page = <ClusterView rest={route.rest} />;
      break;
    case "balancers":
      page = <LoadBalancersView rest={route.rest} />;
      break;
    case "network":
      page = <NetworkView rest={route.rest} />;
      break;
    case "code":
      page = <CodeView rest={route.rest} />;
      break;
    case "deploy":
      page = <DeployView />;
      break;
    case "setup":
      page = <SetupView />;
      break;
    case "test":
      page = <TestView rest={route.rest} />;
      break;
    case "logs":
      page = <LogsView rest={route.rest} />;
      break;
    case "yaml":
      page = <YamlView />;
      break;
    default:
      page = <OverviewView />;
  }

  return (
    <div className={`studio${navOpen ? " nav-open" : ""}`}>
      <header className="studio-top">
        <button type="button" className="btn btn-ghost nav-burger" aria-label="Menu" onClick={() => setNavOpen((o) => !o)}>
          ☰
        </button>
        <a className="brand" href={href("overview")}>
          <span className="logo" aria-hidden="true">
            λ
          </span>
          <span className="brand-text">
            <b>{service}</b>
            <span className="muted small">pskit studio{MOCK ? " · mock API" : ""}</span>
          </span>
        </a>
        <div className="top-targets">
          <label className="top-select">
            <span className="muted small">validate &amp; deploy as</span>
            <select
              className="select select-sm"
              value={target.provider}
              onChange={(e) => setTarget(e.target.value)}
              aria-label="Target provider"
            >
              {meta.providers.map((p) => (
                <option key={p.name} value={p.name}>
                  {p.display_name}
                </option>
              ))}
            </select>
          </label>
          <label className="top-select">
            <span className="muted small">stage</span>
            <input
              className="input input-sm stage-input"
              value={target.stage}
              aria-label="Stage"
              onChange={(e) => setTarget(undefined, e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "").slice(0, 16))}
            />
          </label>
        </div>
        <div className="top-actions">
          <button type="button" className="btn btn-ghost" onClick={undo} disabled={!state.past.length} title="Undo (Ctrl+Z)" aria-label="Undo">
            ↶
          </button>
          <button type="button" className="btn btn-ghost" onClick={redo} disabled={!state.future.length} title="Redo (Ctrl+Shift+Z)" aria-label="Redo">
            ↷
          </button>
          <button
            type="button"
            className={`btn issues-btn${errors ? " has-errors" : ""}`}
            onClick={() => setIssuesOpen((o) => !o)}
            aria-expanded={issuesOpen}
            title="Problems"
          >
            {state.validating ? <span className="spinner spinner-sm" aria-hidden="true" /> : errors ? "⛔" : warnings ? "⚠" : "✓"}
            <span>
              {errors} error{errors === 1 ? "" : "s"} · {warnings} warning{warnings === 1 ? "" : "s"}
            </span>
          </button>
          <button type="button" className="btn" onClick={studio.validateNow} title="Validate now">
            Validate
          </button>
          <button
            type="button"
            className="btn btn-primary save-btn"
            disabled={!dirty || state.saving}
            onClick={() => void doSave()}
            title="Save pskit.yml (Ctrl+S)"
          >
            {dirty && <span className="dirty-dot" aria-label="unsaved changes" />}
            {state.saving ? "Saving…" : dirty ? "Save" : "Saved"}
          </button>
          <button type="button" className="btn" onClick={() => setSettingsOpen(true)} title="Import / export the project's settings (.pskit) and pskit.yml">
            ⇅ Settings
          </button>
          <ThemeToggle />
        </div>
      </header>
      {hanaOpen && <HanaPanel onClose={() => setHanaOpen(false)} />}
      <button
        type="button"
        className={`hana-fab${hanaOpen ? " open" : ""}`}
        onClick={() => setHanaOpen((o) => !o)}
        title={hanaOpen ? "Close Hana (Ctrl+I)" : "Ask Hana, the AI assistant (Ctrl+I)"}
        aria-label={hanaOpen ? "Close Hana" : "Open Hana, the AI assistant"}
        aria-expanded={hanaOpen}
      >
        {hanaOpen ? <span className="hana-fab-close">✕</span> : <HanaAvatar size={56} />}
        {!hanaOpen && <span className="hana-fab-label">Ask Hana</span>}
      </button>
      {settingsOpen && (
        <Drawer open title="Import / export settings and config" onClose={() => setSettingsOpen(false)}>
          <div className="settings-drawer">
            <SettingsTransfer />
          </div>
        </Drawer>
      )}
      <nav className="studio-nav" aria-label="Sections">
        {NAV.map((n) => {
          const count = countFor(n.view);
          const bad = issueCountFor(n.view);
          return (
            <a key={n.view} href={href(n.view)} className={route.view === n.view ? "nav-item active" : "nav-item"} aria-current={route.view === n.view ? "page" : undefined}>
              <span className="nav-icon" aria-hidden="true">
                {n.icon}
              </span>
              <span className="grow">{n.label}</span>
              {bad > 0 && <span className="nav-bad" title={`${bad} problem(s)`}>{bad}</span>}
              {count !== null && <span className="nav-count">{count}</span>}
            </a>
          );
        })}
        <div className="nav-foot muted small">
          {(state.project?.notices || []).map((n, i) => (
            <div key={i} className="notice">
              ⓘ {n}
            </div>
          ))}
          <div>pskit {meta.version}</div>
        </div>
      </nav>
      <main className="studio-main">
        {state.validationError && <ErrorBanner message={`Validation unavailable: ${state.validationError}`} onRetry={studio.validateNow} />}
        {page}
      </main>
      {issuesOpen && (
        <aside className="issues-panel" aria-label="Problems">
          <header className="row-gap">
            <b className="grow">Problems</b>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setIssuesOpen(false)} aria-label="Close problems">
              ✕
            </button>
          </header>
          <IssueList
            issues={issues}
            onSelect={(issue) => {
              const r = routeForWhere(issue.where);
              navigate(r.view, ...r.rest);
            }}
          />
        </aside>
      )}
      <Modal
        open={state.conflict}
        title="pskit.yml changed on disk"
        onClose={closeConflict}
        footer={
          <>
            <button type="button" className="btn" onClick={closeConflict}>
              Cancel
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => {
                closeConflict();
                reload().then(() => toast("Reloaded pskit.yml from disk", "info"), (exc: unknown) => toast(errorMessage(exc), "err"));
              }}
            >
              Reload (discard my changes)
            </button>
            <button
              type="button"
              className="btn btn-danger"
              onClick={() => {
                closeConflict();
                void doSave(true);
              }}
            >
              Overwrite
            </button>
          </>
        }
      >
        <p>
          Someone (or another editor) saved <code className="mono">pskit.yml</code> after the studio loaded it. Reload to
          see their version, or overwrite it with yours. A backup of the file on disk is kept in{" "}
          <code className="mono">.pskit/studio/backups/</code>.
        </p>
      </Modal>
    </div>
  );
}
