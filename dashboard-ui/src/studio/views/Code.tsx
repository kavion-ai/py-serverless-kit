import { useCallback, useEffect, useMemo, useState } from "react";
import { EmptyState, ErrorBanner, Spinner } from "../../components/Feedback";
import { SearchInput } from "../../components/Inputs";
import { api, ApiError, errorMessage } from "../api";
import { CodeEditor, languageOf } from "../components/CodeEditor";
import { JobConsole } from "../components/Console";
import { useConfirm, useToast } from "../components/Feedback";
import { Segmented, TextInput } from "../components/Forms";
import { PageHeader } from "../components/Misc";
import { useJob } from "../jobs";
import { useStudio } from "../store";
import { asObject, str } from "../util";
import { href, navigate } from "../route";
import type { FileEntry, VsCodeState } from "../types";
import { safeUrl } from "../../format";

interface Tab {
  path: string;
  text: string;
  saved: string;
  mtime: number | null;
  loading: boolean;
  error: string | null;
}

interface TreeNode {
  name: string;
  path: string;
  dir: boolean;
  children: TreeNode[];
}

function buildTree(entries: FileEntry[]): TreeNode[] {
  const root: TreeNode = { name: "", path: "", dir: true, children: [] };
  const sorted = [...entries].sort((a, b) => a.path.localeCompare(b.path));
  for (const e of sorted) {
    const parts = e.path.split("/").filter(Boolean);
    let node = root;
    parts.forEach((part, i) => {
      const path = parts.slice(0, i + 1).join("/");
      let child = node.children.find((c) => c.name === part);
      if (!child) {
        child = { name: part, path, dir: i < parts.length - 1 || e.type === "dir", children: [] };
        node.children.push(child);
      }
      node = child;
    });
  }
  const sort = (n: TreeNode) => {
    n.children.sort((a, b) => (a.dir === b.dir ? a.name.localeCompare(b.name) : a.dir ? -1 : 1));
    n.children.forEach(sort);
  };
  sort(root);
  return root.children;
}

export function CodeView({ rest }: { rest: string[] }) {
  const [mode, setMode] = useState<"editor" | "vscode">("editor");
  return (
    <div className="page page-wide">
      <PageHeader
        title="Code"
        subtitle="Edit handler code here, or open the whole project in VS Code (code-server in Docker)."
        actions={
          <Segmented
            label="Editor"
            value={mode}
            onChange={setMode}
            options={[
              { value: "editor", label: "Built-in editor" },
              { value: "vscode", label: "Full VS Code" },
            ]}
          />
        }
      />
      {mode === "editor" ? <Editor openPath={rest.join("/")} /> : <VsCodePanel />}
    </div>
  );
}

function Editor({ openPath }: { openPath: string }) {
  const toast = useToast();
  const confirm = useConfirm();
  const [entries, setEntries] = useState<FileEntry[] | null>(null);
  const [treeError, setTreeError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [tabs, setTabs] = useState<Tab[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [newPath, setNewPath] = useState<string | null>(null);

  const loadTree = useCallback(() => {
    setTreeError(null);
    api.tree().then((r) => setEntries(r.entries), (exc: unknown) => setTreeError(errorMessage(exc)));
  }, []);
  useEffect(loadTree, [loadTree]);

  const open = useCallback((path: string, create = false) => {
    setActive(path);
    setTabs((ts) => {
      if (ts.some((t) => t.path === path)) return ts;
      return [...ts, { path, text: "", saved: "", mtime: null, loading: !create, error: null }];
    });
    if (create) return;
    api.file(path).then(
      (f) => setTabs((ts) => ts.map((t) => (t.path === path ? { ...t, text: f.text, saved: f.text, mtime: f.mtime ?? null, loading: false } : t))),
      (exc: unknown) => setTabs((ts) => ts.map((t) => (t.path === path ? { ...t, loading: false, error: errorMessage(exc) } : t))),
    );
  }, []);

  useEffect(() => {
    if (openPath) open(openPath);
  }, [openPath, open]);

  const tab = tabs.find((t) => t.path === active) || null;

  const save = useCallback(
    async (path: string, force = false) => {
      const t = tabs.find((x) => x.path === path);
      if (!t) return;
      try {
        const res = await api.writeFile(path, t.text, force ? null : t.mtime);
        setTabs((ts) => ts.map((x) => (x.path === path ? { ...x, saved: t.text, mtime: res.mtime } : x)));
        toast(`Saved ${path}`, "ok");
        if (!entries?.some((e) => e.path === path)) loadTree();
      } catch (exc) {
        if (exc instanceof ApiError && exc.status === 409) {
          const answer = await confirm({
            title: `${path} changed on disk`,
            body: "Another editor saved this file after you opened it.",
            confirmLabel: "Overwrite",
            danger: true,
            extra: [{ label: "Reload theirs", value: "reload" }],
          });
          if (answer === "confirm") await save(path, true);
          else if (answer === "reload") {
            const f = await api.file(path);
            setTabs((ts) => ts.map((x) => (x.path === path ? { ...x, text: f.text, saved: f.text, mtime: f.mtime ?? null } : x)));
          }
        } else {
          toast(`Couldn't save ${path}: ${errorMessage(exc)}`, "err");
        }
      }
    },
    [tabs, toast, confirm, entries, loadTree],
  );

  const close = async (path: string) => {
    const t = tabs.find((x) => x.path === path);
    if (t && t.text !== t.saved) {
      const ok = await confirm({ title: `Close ${path}?`, body: "It has unsaved changes.", confirmLabel: "Discard changes", danger: true });
      if (ok !== "confirm") return;
    }
    const remaining = tabs.filter((x) => x.path !== path);
    setTabs(remaining);
    if (active === path) setActive(remaining.length ? remaining[remaining.length - 1].path : null);
  };

  // Warn before leaving with unsaved files.
  const dirty = tabs.some((t) => t.text !== t.saved);
  useEffect(() => {
    if (!dirty) return undefined;
    const on = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", on);
    return () => window.removeEventListener("beforeunload", on);
  }, [dirty]);

  const tree = useMemo(() => {
    const f = filter.trim().toLowerCase();
    return buildTree((entries || []).filter((e) => !f || e.path.toLowerCase().includes(f)));
  }, [entries, filter]);

  const renderNode = (n: TreeNode, depth: number) => {
    if (n.dir) {
      const isCollapsed = collapsed.has(n.path) && !filter;
      return (
        <li key={n.path}>
          <button
            type="button"
            className="tree-item tree-dir"
            style={{ paddingLeft: 8 + depth * 14 }}
            aria-expanded={!isCollapsed}
            onClick={() =>
              setCollapsed((c) => {
                const next = new Set(c);
                if (next.has(n.path)) next.delete(n.path);
                else next.add(n.path);
                return next;
              })
            }
          >
            <span aria-hidden="true">{isCollapsed ? "▸" : "▾"}</span> {n.name}
          </button>
          {!isCollapsed && <ul>{n.children.map((c) => renderNode(c, depth + 1))}</ul>}
        </li>
      );
    }
    const t = tabs.find((x) => x.path === n.path);
    return (
      <li key={n.path}>
        <a
          href={href("code", n.path)}
          className={`tree-item${active === n.path ? " active" : ""}`}
          style={{ paddingLeft: 22 + depth * 14 }}
          onClick={(e) => {
            e.preventDefault();
            open(n.path);
          }}
        >
          <span className={`file-ic fi-${languageOf(n.path)}`} aria-hidden="true" />
          {n.name}
          {t && t.text !== t.saved && <span className="dirty-dot" aria-label="unsaved" />}
        </a>
      </li>
    );
  };

  return (
    <div className="ide card">
      <aside className="ide-tree">
        <div className="ide-tree-head">
          <SearchInput value={filter} onChange={setFilter} placeholder="Find file…" />
          <button type="button" className="btn btn-sm" title="New file" onClick={() => setNewPath("app/")}>
            +
          </button>
          <button type="button" className="btn btn-sm" title="Refresh" onClick={loadTree}>
            ↻
          </button>
        </div>
        {newPath !== null && (
          <form
            className="new-file"
            onSubmit={(e) => {
              e.preventDefault();
              const p = newPath.trim().replace(/^\/+/, "");
              if (!p || p.endsWith("/") || p.includes("..")) {
                toast("Enter a relative file path, e.g. app/utils.py", "err");
                return;
              }
              open(p, true);
              navigate("code", p);
              setNewPath(null);
            }}
          >
            <TextInput mono autoFocus value={newPath} onChange={setNewPath} placeholder="app/new_module.py" />
            <button type="submit" className="btn btn-sm btn-primary">
              Create
            </button>
            <button type="button" className="btn btn-sm" onClick={() => setNewPath(null)}>
              ✕
            </button>
          </form>
        )}
        {treeError && <ErrorBanner message={treeError} onRetry={loadTree} />}
        {!entries && !treeError && <Spinner label="Loading files…" />}
        {entries && <ul className="tree">{tree.map((n) => renderNode(n, 0))}</ul>}
      </aside>
      <section className="ide-main">
        <div className="ide-tabs" role="tablist">
          {tabs.map((t) => (
            <div key={t.path} className={`ide-tab${t.path === active ? " active" : ""}`} role="tab" aria-selected={t.path === active}>
              <button type="button" className="ide-tab-name" onClick={() => setActive(t.path)} title={t.path}>
                {t.path.split("/").pop()}
                {t.text !== t.saved && <span className="dirty-dot" aria-label="unsaved" />}
              </button>
              <button type="button" className="ide-tab-close" aria-label={`Close ${t.path}`} onClick={() => void close(t.path)}>
                ✕
              </button>
            </div>
          ))}
        </div>
        {!tab ? (
          <EmptyState title="No file open" icon="{}">
            Pick a file on the left, or open a function's handler from the Functions page.
          </EmptyState>
        ) : tab.loading ? (
          <div className="pad">
            <Spinner label={`Opening ${tab.path}…`} />
          </div>
        ) : tab.error ? (
          <ErrorBanner message={tab.error} onRetry={() => open(tab.path)} />
        ) : (
          <>
            <div className="ide-pathbar">
              <span className="mono small">{tab.path}</span>
              <span className="grow" />
              <span className="muted small">{languageOf(tab.path)}</span>
              <button type="button" className="btn btn-sm btn-primary" disabled={tab.text === tab.saved} onClick={() => void save(tab.path)}>
                Save (Ctrl+S)
              </button>
            </div>
            <div className="ide-editor">
              <CodeEditor
                key={tab.path}
                value={tab.text}
                language={languageOf(tab.path)}
                ariaLabel={`Editing ${tab.path}`}
                onChange={(text) => setTabs((ts) => ts.map((x) => (x.path === tab.path ? { ...x, text } : x)))}
                onSave={() => void save(tab.path)}
                minHeight={480}
              />
            </div>
          </>
        )}
      </section>
    </div>
  );
}

// --------------------------------------------------------------------- VS Code (code-server)

function VsCodePanel() {
  const toast = useToast();
  const [state, setState] = useState<VsCodeState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [image, setImage] = useState("");
  const [busy, setBusy] = useState(false);
  const { draft } = useStudio();
  const runtime = str(asObject(draft.provider).runtime);
  // Default: the project's own runtime (python3.12 -> 3.12, nodejs20 -> 20).
  const [python, setPython] = useState<string>(() => (runtime.startsWith("python") ? runtime.slice(6) : ""));
  const [node, setNode] = useState<string>(() => (runtime.startsWith("nodejs") ? runtime.slice(6) : ""));
  const job = useJob(jobId);

  const refresh = useCallback(() => {
    api.vscode().then(
      (s) => {
        setState(s);
        setError(null);
        setImage((i) => i || s.image);
        if (s.running && (s.python || s.node)) {
          setPython(s.python || "");
          setNode(s.node || "");
        }
        if (s.log_job && !jobId) setJobId(s.log_job);
      },
      (exc: unknown) => setError(errorMessage(exc)),
    );
  }, [jobId]);
  useEffect(refresh, [refresh]);
  // Refresh while starting so the iframe appears as soon as the container answers.
  useEffect(() => {
    if (job.status === "running") return undefined;
    if (job.status === "succeeded" || job.status === "failed") refresh();
    return undefined;
  }, [job.status, refresh]);
  useEffect(() => {
    if (!state || state.running || job.status !== "running") return undefined;
    const t = window.setInterval(refresh, 2500);
    return () => window.clearInterval(t);
  }, [state, job.status, refresh]);

  const start = async () => {
    setBusy(true);
    try {
      const r = await api.vscodeStart(image && image !== state?.image ? image : undefined, python || undefined, node || undefined);
      setJobId(r.job_id);
    } catch (exc) {
      toast(errorMessage(exc), "err");
    } finally {
      setBusy(false);
    }
  };
  const stop = async () => {
    setBusy(true);
    try {
      setState(await api.vscodeStop());
      setJobId(null);
      toast("VS Code stopped", "info");
    } catch (exc) {
      toast(errorMessage(exc), "err");
    } finally {
      setBusy(false);
    }
  };

  if (error) return <ErrorBanner message={error} onRetry={refresh} />;
  if (!state) return <Spinner label="Checking Docker…" />;
  const url = safeUrl(state.url);

  if (!state.docker.available) {
    return (
      <div className="card card-pad stack vscode-help">
        <h2>Docker is needed for full VS Code</h2>
        <p className="muted">
          Studio runs <code className="mono">{state.image}</code> (code-server, VS Code in the browser) in a container with this project mounted.
          {state.docker.error ? ` Docker said: ${state.docker.error}` : ""}
        </p>
        <ol className="bullets">
          <li>
            Install Docker Desktop (Windows/macOS) or Docker Engine (Linux) and make sure <code className="mono">docker version</code> works in a terminal.
          </li>
          <li>Come back here and press "Pull &amp; start". The image is downloaded once (~600 MB).</li>
          <li>
            Running studio itself in a container? Mount the Docker socket (<code className="mono">-v /var/run/docker.sock:/var/run/docker.sock</code>) and set{" "}
            <code className="mono">PSKIT_STUDIO_HOST_ROOT</code> to the project's path <i>on the host</i>, so the editor container mounts the right folder.
          </li>
        </ol>
        <p className="muted">The built-in editor works without Docker.</p>
        <button type="button" className="btn" onClick={refresh}>
          Check again
        </button>
      </div>
    );
  }

  return (
    <div className="stack">
      <div className="card card-pad vscode-bar">
        <span className="badge badge-ok">Docker {state.docker.version || "available"}</span>
        <span className={`badge ${state.running ? "badge-ok" : "badge-off"}`}>{state.running ? "running" : "stopped"}</span>
        {state.image_present === false && !state.running && <span className="badge badge-warn">image not pulled yet</span>}
        <label className="row-gap grow">
          <span className="muted small">image</span>
          <TextInput mono value={image} onChange={setImage} disabled={state.running} />
        </label>
        <label className="row-gap" title="CPython installed in the editor container (uv python install)">
          <span className="muted small">Python</span>
          <select className="select select-sm" value={python} onChange={(e) => setPython(e.target.value)}>
            <option value="">image default</option>
            {(state.python_versions || ["3.13", "3.12", "3.11", "3.10", "3.9"]).map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <label className="row-gap" title="Official Node.js build installed in the editor container">
          <span className="muted small">Node.js</span>
          <select className="select select-sm" value={node} onChange={(e) => setNode(e.target.value)}>
            <option value="">none</option>
            {(state.node_versions || ["24", "22", "20", "18"]).map((v) => (
              <option key={v} value={v}>
                {v}.x
              </option>
            ))}
          </select>
        </label>
        {state.running ? (
          <>
            {url && (
              <a className="btn" href={url} target="_blank" rel="noopener noreferrer">
                Open in new tab ↗
              </a>
            )}
            {((state.python || "") !== python || (state.node || "") !== node) && (
              <button type="button" className="btn btn-primary" disabled={busy || job.status === "running"} onClick={() => void start()} title="Recreate the editor container with the runtimes picked here (your files are kept)">
                Restart with these runtimes
              </button>
            )}
            <button type="button" className="btn btn-danger" disabled={busy} onClick={() => void stop()}>
              Stop
            </button>
          </>
        ) : (
          <button type="button" className="btn btn-primary" disabled={busy || job.status === "running"} onClick={() => void start()}>
            {job.status === "running" ? "Starting…" : state.image_present === false ? "Pull & start" : "Start"}
          </button>
        )}
      </div>
      {state.running && url ? (
        <div className="vscode-frame card">
          <iframe title="VS Code" src={url} allow="clipboard-read; clipboard-write" referrerPolicy="no-referrer" />
        </div>
      ) : (
        <JobConsole
          job={job}
          emptyText={
            python || node
              ? `Press start. Docker pulls the image, then builds it once with ${[python && `Python ${python}`, node && `Node.js ${node}`].filter(Boolean).join(" and ")} (a few minutes); progress shows here.`
              : "Press start. Docker pulls the image the first time; progress shows here."
          }
        />
      )}
      {state.running && <p className="muted small">The container only listens on 127.0.0.1. Files you save in VS Code are the project files; the built-in editor sees them on reload.</p>}
    </div>
  );
}
