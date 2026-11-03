import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { api, errorMessage } from "../api";
import { useConfirm, useToast } from "../components/Feedback";
import { Markdown } from "../components/Markdown";
import { useJob } from "../jobs";
import { useRoute, type View } from "../route";
import { useStudio } from "../store";
import type {
  HanaCard,
  HanaDisplay,
  HanaEvent,
  HanaRuntime,
  HanaSessionSummary,
  HanaTurn,
  JsonObject,
  OnPremServer,
} from "../types";
import { ActionCard, HanaAvatar } from "./HanaCards";

/** The page names Hana was trained with (the `page=` of her Environment line). */
const PAGE: Record<View, string> = {
  overview: "Overview",
  setup: "Setup",
  functions: "Functions",
  workflows: "Workflows",
  resources: "Resources",
  cluster: "Cluster",
  balancers: "Load balancers",
  network: "Network map",
  code: "Code",
  test: "Test",
  deploy: "Deploy",
  logs: "Logs",
  yaml: "YAML",
};

const SUGGESTIONS = [
  "What can you do?",
  "Add a GET /health endpoint that returns ok",
  "Validate my project and fix the problems",
  "Add a server for me",
  "How do I add a schedule in studio?",
];

const TOOL_LABEL: Record<string, string> = {
  search_docs: "Searched the docs",
  get_project: "Read pskit.yml",
  read_file: "Read a file",
  get_validation: "Checked validation",
  validate: "Ran validate",
  set_config: "Changed pskit.yml",
  write_file: "Wrote a file",
  invoke_local: "Ran the function locally",
  run_command: "Ran a command",
};

type Mode = "ask" | "auto";

type Item =
  | { kind: "user"; text: string; index?: number }
  | { kind: "assistant"; text: string }
  | { kind: "tool"; name: string; args: JsonObject; result?: string }
  | {
      kind: "plan";
      steps: string[];
      pendingId?: string;
      decision?: string;
      note?: string;
    }
  | {
      kind: "question";
      question: string;
      options: string[];
      pendingId?: string;
      answer?: string;
    }
  | {
      kind: "step";
      tool: string;
      args: JsonObject;
      pendingId?: string;
      decision?: string;
    }
  | { kind: "note"; text: string; tone?: "err" | "ok" | "info" }
  | { kind: "action"; card: HanaCard };

type Size = "normal" | "large" | "full";
const SIZES: Size[] = ["normal", "large", "full"];

function readSize(): Size {
  try {
    const v = window.localStorage.getItem("pskit-hana-size");
    return v === "large" || v === "full" ? v : "normal";
  } catch {
    return "normal";
  }
}

interface MenuItem {
  label: string;
  run: () => void;
  disabled?: boolean;
  danger?: boolean;
}

/** A small drop-down of actions (closes on pick, Escape or a click outside). */
function Menu({
  label,
  title,
  items,
  disabled,
}: {
  label: string;
  title?: string;
  items: MenuItem[];
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return undefined;
    const close = (e: MouseEvent | globalThis.KeyboardEvent) => {
      if (e instanceof MouseEvent && ref.current?.contains(e.target as Node))
        return;
      if (!(e instanceof MouseEvent) && e.key !== "Escape") return;
      setOpen(false);
    };
    window.addEventListener("mousedown", close);
    window.addEventListener("keydown", close);
    return () => {
      window.removeEventListener("mousedown", close);
      window.removeEventListener("keydown", close);
    };
  }, [open]);
  return (
    <div className="hana-menu" ref={ref}>
      <button
        type="button"
        className="btn btn-sm"
        aria-haspopup="menu"
        aria-expanded={open}
        title={title}
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
      >
        {label}
      </button>
      {open && (
        <div className="hana-menu-list" role="menu">
          {items.map((it) => (
            <button
              key={it.label}
              type="button"
              role="menuitem"
              className={it.danger ? "danger" : ""}
              disabled={it.disabled}
              onClick={() => {
                setOpen(false);
                it.run();
              }}
            >
              {it.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function readMode(): Mode {
  try {
    return window.localStorage.getItem("pskit-hana-mode") === "auto"
      ? "auto"
      : "ask";
  } catch {
    return "ask";
  }
}

function fromDisplay(display: HanaDisplay[]): Item[] {
  return display.map((d, i): Item => {
    if (d.role === "tool")
      return { kind: "tool", name: d.name, args: d.args, result: d.result };
    if (d.role === "action") return { kind: "action", card: d.card };
    if (d.role === "note") return { kind: "note", text: d.text, tone: "ok" };
    if (d.role === "user") return { kind: "user", text: d.text, index: i };
    return { kind: d.role, text: d.text };
  });
}

/** Fold a turn's events into the chat items. */
function applyEvents(items: Item[], events: HanaEvent[]): Item[] {
  const out = [...items];
  for (const e of events) {
    const s = (k: string) => (typeof e[k] === "string" ? (e[k] as string) : "");
    if (e.type === "tool_call") {
      if (s("text")) out.push({ kind: "assistant", text: s("text") });
      const name = s("name");
      if (name !== "propose_plan" && name !== "ask_user")
        out.push({ kind: "tool", name, args: (e.args as JsonObject) || {} });
    } else if (e.type === "tool_result") {
      const name = s("name");
      for (let i = out.length - 1; i >= 0; i--) {
        const it = out[i];
        if (it.kind === "tool" && it.name === name && it.result === undefined) {
          out[i] = { ...it, result: s("result") };
          break;
        }
      }
    } else if (e.type === "plan") {
      out.push({
        kind: "plan",
        steps: (e.steps as string[]) || [],
        decision: s("decision") || "auto_approved",
      });
    } else if (e.type === "waiting") {
      const kind = s("kind");
      const pendingId = s("pending_id");
      if (kind === "plan")
        out.push({
          kind: "plan",
          steps: (e.steps as string[]) || [],
          pendingId,
        });
      else if (kind === "question")
        out.push({
          kind: "question",
          question: s("question"),
          options: (e.options as string[]) || [],
          pendingId,
        });
      else
        out.push({
          kind: "step",
          tool: s("tool"),
          args: (e.args as JsonObject) || {},
          pendingId,
        });
    } else if (e.type === "answered") {
      const pid = s("pending_id");
      for (let i = out.length - 1; i >= 0; i--) {
        const it = out[i];
        if (
          (it.kind === "plan" ||
            it.kind === "question" ||
            it.kind === "step") &&
          it.pendingId === pid
        ) {
          if (it.kind === "question")
            out[i] = { ...it, pendingId: undefined, answer: s("text") };
          else
            out[i] = {
              ...it,
              pendingId: undefined,
              decision: s("decision"),
              ...(it.kind === "plan" ? { note: s("text") } : {}),
            };
          break;
        }
      }
    } else if (e.type === "answer") {
      out.push({ kind: "assistant", text: s("text") });
    } else if (e.type === "action") {
      out.push({ kind: "action", card: e.card as HanaCard });
    } else if (e.type === "changed") {
      out.push({
        kind: "note",
        text: `Changed ${((e.files as string[]) || []).join(", ")}`,
        tone: "info",
      });
    } else if (e.type === "error") {
      out.push({ kind: "note", text: s("text"), tone: "err" });
    } else if (e.type === "stopped") {
      out.push({ kind: "note", text: "Stopped." });
    }
  }
  return out;
}

export function HanaPanel({ onClose }: { onClose: () => void }) {
  const studio = useStudio();
  const toast = useToast();
  const route = useRoute();
  const [runtime, setRuntime] = useState<HanaRuntime | null>(null);
  const [sessions, setSessions] = useState<HanaSessionSummary[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [setupOpen, setSetupOpen] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [items, setItems] = useState<Item[]>([]);
  const [turn, setTurn] = useState<HanaTurn | null>(null);
  const [text, setText] = useState("");
  const [mode, setMode] = useState<Mode>(readMode);
  const [size, setSize] = useState<Size>(readSize);
  const [first, setFirst] = useState<"model" | "studio">(() => {
    try {
      return window.localStorage.getItem("pskit-hana-first") === "studio"
        ? "studio"
        : "model";
    } catch {
      return "model";
    }
  });
  useEffect(() => {
    try {
      window.localStorage.setItem("pskit-hana-first", first);
    } catch {
      /* convenience only */
    }
  }, [first]);
  const confirm = useConfirm();

  useEffect(() => {
    try {
      window.localStorage.setItem("pskit-hana-size", size);
    } catch {
      /* convenience only */
    }
  }, [size]);
  const [sending, setSending] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const cursor = useRef(0);

  const refresh = useCallback(async () => {
    try {
      const state = await api.hana();
      setRuntime(state.runtime);
      setSessions(state.sessions);
      setLoadError(null);
    } catch (exc) {
      setLoadError(errorMessage(exc));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    try {
      window.localStorage.setItem("pskit-hana-mode", mode);
    } catch {
      /* convenience only */
    }
  }, [mode]);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [items, turn?.status]);

  // Poll the running turn.
  const turnId = turn?.turn_id ?? null;
  const running =
    !!turn && (turn.status === "running" || turn.status === "waiting");
  useEffect(() => {
    if (!turnId || !running) return undefined;
    let live = true;
    let timer = 0;
    const tick = async () => {
      try {
        const t = await api.hanaTurn(turnId, cursor.current);
        if (!live) return;
        cursor.current = t.next;
        if (t.events.length) setItems((cur) => applyEvents(cur, t.events));
        setTurn(t);
        if (t.status === "running" || t.status === "waiting") {
          timer = window.setTimeout(tick, document.hidden ? 2500 : 600);
        } else {
          void refresh();
          // the k-th message you wrote = the k-th user entry of the saved chat: that is what "edit" needs
          api.hanaSession(t.session_id).then(
            (sess) => {
              const idx = sess.display
                .map((d, i) => (d.role === "user" ? i : -1))
                .filter((i) => i >= 0);
              setItems((cur) => {
                let k = 0;
                return cur.map((it) =>
                  it.kind === "user" ? { ...it, index: idx[k++] } : it,
                );
              });
            },
            () => undefined,
          );
          if (t.changed.length) {
            if (!studio.dirty) {
              await studio.reload();
              toast(`Hana changed ${t.changed.join(", ")}`, "ok");
            } else {
              toast(
                `Hana changed ${t.changed.join(", ")} on disk; you have unsaved edits (Save will ask)`,
                "info",
              );
            }
          }
        }
      } catch (exc) {
        if (!live) return;
        timer = window.setTimeout(tick, 2000);
        setLoadError(errorMessage(exc));
      }
    };
    void tick();
    return () => {
      live = false;
      window.clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [turnId, running]);

  const openSession = async (id: string | null) => {
    setSessionId(id);
    setTurn(null);
    cursor.current = 0;
    if (!id) {
      setItems([]);
      return;
    }
    try {
      const s = await api.hanaSession(id);
      setItems(fromDisplay(s.display));
      if (s.turn_id) {
        // A turn is still running: the history up to its user message, then its events from the start.
        const t = await api.hanaTurn(s.turn_id, 0);
        let lastUser = -1;
        s.display.forEach((d, i) => {
          if (d.role === "user") lastUser = i;
        });
        setItems(
          applyEvents(fromDisplay(s.display.slice(0, lastUser + 1)), t.events),
        );
        cursor.current = t.next;
        setTurn(t);
      }
    } catch (exc) {
      toast(errorMessage(exc), "err");
    }
  };

  const editMessage = async (index: number, newText: string) => {
    if (!sessionId || running) return;
    try {
      const target = studio.state.target || { provider: "aws", stage: "dev" };
      const r = await api.hanaEdit(sessionId, index, newText, {
        provider: target.provider,
        stage: target.stage,
        mode,
        page: PAGE[route.view] || "none",
        first,
      });
      setItems((cur) => {
        const at = cur.findIndex(
          (it) => it.kind === "user" && it.index === index,
        );
        return [
          ...(at >= 0 ? cur.slice(0, at) : cur),
          { kind: "user", text: newText },
        ];
      });
      cursor.current = 1;
      setTurn({
        turn_id: r.turn_id,
        session_id: r.session_id,
        status: "running",
        pending: null,
        events: [],
        next: 1,
        changed: [],
      });
    } catch (exc) {
      toast(errorMessage(exc), "err");
    }
  };

  const send = async (message?: string) => {
    const q = (message ?? text).trim();
    if (!q || running || sending) return;
    setSending(true);
    try {
      const target = studio.state.target || { provider: "aws", stage: "dev" };
      const r = await api.hanaSend(sessionId, q, {
        provider: target.provider,
        stage: target.stage,
        mode,
        page: PAGE[route.view] || "none",
        first,
      });
      setText("");
      setSessionId(r.session_id);
      setItems((cur) => [...cur, { kind: "user", text: q }]);
      cursor.current = 1; // the "user" event is already shown
      setTurn({
        turn_id: r.turn_id,
        session_id: r.session_id,
        status: "running",
        pending: null,
        events: [],
        next: 1,
        changed: [],
      });
    } catch (exc) {
      const msg = errorMessage(exc);
      if (msg.includes("not set up")) setSetupOpen(true);
      toast(msg, "err");
    } finally {
      setSending(false);
    }
  };

  const answer = async (
    pendingId: string,
    decision: "approve" | "reject" | "answer",
    value = "",
  ) => {
    if (!turn) return;
    try {
      await api.hanaAnswer(turn.turn_id, pendingId, decision, value);
    } catch (exc) {
      toast(errorMessage(exc), "err");
    }
  };

  const note = useCallback(
    async (message: string) => {
      setItems((cur) => [...cur, { kind: "note", text: message, tone: "ok" }]);
      if (!sessionId) return;
      try {
        await api.hanaNote(sessionId, message);
      } catch (exc) {
        toast(errorMessage(exc), "err");
      }
    },
    [sessionId, toast],
  );

  const stop = async () => {
    if (!turn) return;
    try {
      await api.hanaStopTurn(turn.turn_id);
    } catch (exc) {
      toast(errorMessage(exc), "err");
    }
  };

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void send();
    }
  };

  const clearChat = async () => {
    if (!sessionId) return;
    try {
      await api.hanaDeleteSession(sessionId);
      await openSession(null);
      await refresh();
      toast("Chat cleared", "info");
    } catch (exc) {
      toast(errorMessage(exc), "err");
    }
  };

  const deleteAll = async () => {
    const ok = await confirm({
      title: "Delete all chats?",
      body: `All ${sessions.length} saved chat${sessions.length === 1 ? "" : "s"} of this project are deleted from .pskit/studio/hana/. Your project files are not touched.`,
      confirmLabel: "Delete all",
      danger: true,
    });
    if (!ok) return;
    try {
      await api.hanaDeleteAll();
      await openSession(null);
      await refresh();
      toast("All chats deleted", "info");
    } catch (exc) {
      toast(errorMessage(exc), "err");
    }
  };

  const projectChanged = useCallback(async () => {
    if (!studio.dirty) await studio.reload();
    else
      toast(
        "pskit.yml changed on disk; you have unsaved edits (Save will ask)",
        "info",
      );
  }, [studio, toast]);

  const problems = (studio.state.validation?.issues || []).length;
  const showSetup = setupOpen || (runtime !== null && !runtime.configured);
  const status = !runtime
    ? "…"
    : !runtime.configured
      ? "not set up"
      : runtime.ready
        ? "ready"
        : "not answering";

  return (
    <aside
      className={`hana-panel hana-size-${size}`}
      aria-label="Hana, the AI assistant"
    >
      <header className="hana-head">
        <HanaAvatar size={30} thinking={running} />
        <div className="grow">
          <b>Hana</b>
          <span
            className={`hana-dot ${runtime?.ready ? "ok" : runtime?.configured ? "err" : "off"}`}
            title={runtime?.error || status}
          />
          <span className="muted small"> {status}</span>
        </div>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={() =>
            setSize(SIZES[(SIZES.indexOf(size) + 1) % SIZES.length])
          }
          title={`Window size: ${size} (click for ${SIZES[(SIZES.indexOf(size) + 1) % SIZES.length]})`}
          aria-label="Change the chat window size"
        >
          {size === "full" ? "🗗" : "⤢"}
        </button>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={() => setSetupOpen((o) => !o)}
          title="Where Hana runs"
          aria-label="Hana settings"
        >
          ⚙
        </button>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={onClose}
          aria-label="Close Hana"
          title="Close (Ctrl+I)"
        >
          ✕
        </button>
      </header>
      <div className="hana-sessions">
        <select
          className="select select-sm grow"
          value={sessionId || ""}
          onChange={(e) => void openSession(e.target.value || null)}
          aria-label="Chat"
          disabled={running}
        >
          <option value="">New chat</option>
          {sessions.map((s) => (
            <option key={s.id} value={s.id}>
              {s.title}
            </option>
          ))}
        </select>
        <select
          className="select select-sm"
          value={mode}
          onChange={(e) => setMode(e.target.value as Mode)}
          aria-label="Approval mode"
          title="Ask: you approve each plan before Hana changes anything. Auto: plans run at once."
        >
          <option value="ask">Ask first</option>
          <option value="auto">Auto-approve</option>
        </select>
        <Menu
          label="Explain"
          disabled={running || !runtime?.configured}
          items={[
            {
              label: `Explain the ${PAGE[route.view] || "current"} page`,
              run: () =>
                void send(
                  `Explain the ${PAGE[route.view]} page in studio: what is it for and what can I do there?`,
                ),
            },
            {
              label: "Explain my project",
              run: () =>
                void send(
                  "Explain my project: what does each function do and how do they connect?",
                ),
            },
            {
              label: problems
                ? `Explain the ${problems} validation problem${problems === 1 ? "" : "s"}`
                : "Explain validation (no problems now)",
              run: () =>
                void send(
                  "Explain the validation problems in my project and how to fix them.",
                ),
            },
            {
              label: "Explain your last answer more simply",
              run: () =>
                void send(
                  "Explain your last answer more simply, step by step.",
                ),
            },
          ]}
        />
        <Menu
          label="⋯"
          title="Chat options"
          disabled={running}
          items={[
            { label: "New chat", run: () => void openSession(null) },
            {
              label: "Clear this chat",
              run: () => void clearChat(),
              disabled: !sessionId,
            },
            {
              label: "Delete all chats…",
              run: () => void deleteAll(),
              danger: true,
              disabled: !sessions.length,
            },
            {
              label:
                first === "model"
                  ? "✓ Hana's model answers first (then studio actions)"
                  : "Hana's model answers first (then studio actions)",
              run: () => setFirst("model"),
            },
            {
              label:
                first === "studio"
                  ? "✓ Studio actions answer first (then the model)"
                  : "Studio actions answer first (then the model)",
              run: () => setFirst("studio"),
            },
          ]}
        />
      </div>
      {loadError && <div className="hana-note err">{loadError}</div>}
      {showSetup && runtime && (
        <HanaSetup
          runtime={runtime}
          onDone={() => {
            setSetupOpen(false);
            void refresh();
          }}
          onRefresh={refresh}
        />
      )}
      {runtime?.configured && !runtime.ready && !showSetup && (
        <div className="hana-note err">
          The model at <code className="mono">{runtime.url}</code> is not
          answering{runtime.error ? `: ${runtime.error}` : ""}.{" "}
          <button
            type="button"
            className="link-btn"
            onClick={() => void refresh()}
          >
            Check again
          </button>{" "}
          ·{" "}
          <button
            type="button"
            className="link-btn"
            onClick={() => setSetupOpen(true)}
          >
            Set up
          </button>
        </div>
      )}
      <div className="hana-list" ref={listRef} aria-live="polite">
        {items.length === 0 && !showSetup && (
          <div className="hana-empty">
            <HanaAvatar size={56} />
            <p>
              Hi, I&apos;m <b>Hana</b>. Ask me how to do something in pskit, or
              ask me to change this project: I&apos;ll show a plan first
              {mode === "auto" ? " (auto-approve is on)" : ""}, then validate
              the result.
            </p>
            <div className="hana-suggest">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  type="button"
                  className="chip chip-btn"
                  onClick={() => void send(s)}
                  disabled={!runtime?.configured}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {items.map((it, i) => (
          <ChatItem
            key={i}
            item={it}
            onAnswer={answer}
            onNote={note}
            onChanged={projectChanged}
            onEdit={running ? undefined : editMessage}
          />
        ))}
        {running && turn?.status === "running" && (
          <div className="hana-thinking muted small">
            <span className="hana-typing" aria-hidden="true">
              <i />
              <i />
              <i />
            </span>{" "}
            Hana is working…
          </div>
        )}
      </div>
      <footer className="hana-input">
        <textarea
          className="input"
          rows={2}
          placeholder={
            runtime?.configured
              ? "Ask Hana… (Enter to send, Shift+Enter for a new line)"
              : "Set up Hana first"
          }
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKey}
          disabled={!runtime?.configured}
          aria-label="Message to Hana"
        />
        {running ? (
          <button
            type="button"
            className="btn btn-danger"
            onClick={() => void stop()}
          >
            Stop
          </button>
        ) : (
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => void send()}
            disabled={!text.trim() || sending || !runtime?.configured}
          >
            Send
          </button>
        )}
      </footer>
      <div className="hana-foot muted small">
        Hana can make mistakes. She never deploys; changes are validated, and
        pskit.yml is backed up first.
      </div>
    </aside>
  );
}

/** Your message, with ✎ to change it: the chat goes back to that point and Hana answers the new text. */
function UserMessage({
  text,
  onEdit,
}: {
  text: string;
  onEdit?: (text: string) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(text);
  if (editing && onEdit) {
    return (
      <div className="hana-edit">
        <textarea
          className="input"
          rows={Math.min(
            8,
            Math.max(2, value.split(String.fromCharCode(10)).length),
          )}
          value={value}
          autoFocus
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape") setEditing(false);
            if (e.key === "Enter" && !e.shiftKey && value.trim()) {
              e.preventDefault();
              setEditing(false);
              void onEdit(value.trim());
            }
          }}
          aria-label="Edit your message"
        />
        <div className="hana-actions">
          <button
            type="button"
            className="btn btn-primary btn-sm"
            disabled={!value.trim()}
            onClick={() => {
              setEditing(false);
              void onEdit(value.trim());
            }}
          >
            Save &amp; send
          </button>
          <button
            type="button"
            className="btn btn-sm"
            onClick={() => {
              setEditing(false);
              setValue(text);
            }}
          >
            Cancel
          </button>
          <span className="muted small">
            Hana answers again from here; later messages in this chat are
            replaced.
          </span>
        </div>
      </div>
    );
  }
  return (
    <div className="hana-user-row">
      {onEdit && (
        <button
          type="button"
          className="hana-edit-btn"
          title="Edit this message"
          aria-label="Edit this message"
          onClick={() => {
            setValue(text);
            setEditing(true);
          }}
        >
          ✎
        </button>
      )}
      <div className="hana-msg hana-user">{text}</div>
    </div>
  );
}

function ChatItem({
  item,
  onAnswer,
  onNote,
  onChanged,
  onEdit,
}: {
  item: Item;
  onAnswer: (
    pid: string,
    d: "approve" | "reject" | "answer",
    t?: string,
  ) => Promise<void>;
  onNote: (text: string) => Promise<void>;
  onChanged: () => Promise<void>;
  onEdit?: (index: number, text: string) => Promise<void>;
}) {
  const [note, setNote] = useState("");
  switch (item.kind) {
    case "user":
      return (
        <UserMessage
          text={item.text}
          onEdit={
            onEdit && item.index !== undefined
              ? (t) => onEdit(item.index as number, t)
              : undefined
          }
        />
      );
    case "assistant":
      return (
        <div className="hana-bot-row">
          <HanaAvatar size={26} />
          <div className="hana-msg hana-bot">
            <Markdown text={item.text} />
          </div>
        </div>
      );
    case "note":
      return (
        <div className={`hana-note ${item.tone || ""}`}>
          <Markdown text={item.text} />
        </div>
      );
    case "action":
      return (
        <ActionCard card={item.card} onNote={onNote} onChanged={onChanged} />
      );
    case "tool":
      return <ToolRow name={item.name} args={item.args} result={item.result} />;
    case "plan":
      return (
        <div className="hana-card">
          <div className="hana-card-title">
            Plan
            {item.decision && <Decision decision={item.decision} />}
          </div>
          <ol className="hana-steps">
            {item.steps.map((s, i) => (
              <li key={i}>
                <Markdown text={s} />
              </li>
            ))}
          </ol>
          {item.note && (
            <div className="muted small">Your note: {item.note}</div>
          )}
          {item.pendingId && (
            <div className="hana-actions">
              <input
                className="input input-sm grow"
                placeholder="Optional note (e.g. use 4 workers)"
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
              <button
                type="button"
                className="btn btn-primary btn-sm"
                onClick={() => void onAnswer(item.pendingId!, "approve", note)}
              >
                Approve
              </button>
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => void onAnswer(item.pendingId!, "reject", note)}
              >
                Reject
              </button>
            </div>
          )}
        </div>
      );
    case "question":
      return (
        <div className="hana-card">
          <div className="hana-card-title">Hana asks</div>
          <Markdown text={item.question} />
          {item.answer !== undefined ? (
            <div className="muted small">You answered: {item.answer}</div>
          ) : item.pendingId ? (
            <>
              {item.options.length > 0 && (
                <div className="hana-suggest">
                  {item.options.map((o) => (
                    <button
                      key={o}
                      type="button"
                      className="chip chip-btn"
                      onClick={() =>
                        void onAnswer(item.pendingId!, "answer", o)
                      }
                    >
                      {o}
                    </button>
                  ))}
                </div>
              )}
              <div className="hana-actions">
                <input
                  className="input input-sm grow"
                  placeholder="Your answer"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && note.trim())
                      void onAnswer(item.pendingId!, "answer", note.trim());
                  }}
                />
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  disabled={!note.trim()}
                  onClick={() =>
                    void onAnswer(item.pendingId!, "answer", note.trim())
                  }
                >
                  Answer
                </button>
              </div>
            </>
          ) : null}
        </div>
      );
    case "step":
      return (
        <div className="hana-card">
          <div className="hana-card-title">
            Hana wants to:{" "}
            {item.tool === "run_command"
              ? item.args.server
                ? `run a command on ${String(item.args.server)}`
                : "run a command in the project folder"
              : TOOL_LABEL[item.tool]?.toLowerCase() || item.tool}
            {item.decision && <Decision decision={item.decision} />}
          </div>
          <StepDetail tool={item.tool} args={item.args} />
          {item.pendingId && (
            <div className="hana-actions">
              <button
                type="button"
                className="btn btn-primary btn-sm"
                onClick={() => void onAnswer(item.pendingId!, "approve")}
              >
                {item.tool === "run_command" ? "Run" : "Allow"}
              </button>
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => void onAnswer(item.pendingId!, "reject")}
              >
                Don&apos;t allow
              </button>
            </div>
          )}
        </div>
      );
  }
}

function Decision({ decision }: { decision: string }) {
  const ok = decision === "approve" || decision === "auto_approved";
  return (
    <span className={`badge ${ok ? "badge-ok" : "badge-err"}`}>
      {decision === "auto_approved"
        ? "auto-approved"
        : ok
          ? "approved"
          : "rejected"}
    </span>
  );
}

function StepDetail({ tool, args }: { tool: string; args: JsonObject }) {
  if (tool === "run_command") {
    return (
      <>
        <pre className="hana-pre">$ {String(args.command ?? "")}</pre>
        <div className="muted small">
          Nothing runs until you click Run. The output goes back to Hana, who
          answers from it.
        </div>
      </>
    );
  }
  if (tool === "write_file") {
    return (
      <>
        <div className="mono small">{String(args.path ?? "")}</div>
        <pre className="hana-pre">{String(args.content ?? "")}</pre>
      </>
    );
  }
  if (tool === "set_config") {
    return (
      <pre className="hana-pre">
        {String(args.path ?? "")}: {JSON.stringify(args.value ?? null, null, 2)}
      </pre>
    );
  }
  return <pre className="hana-pre">{JSON.stringify(args, null, 2)}</pre>;
}

function ToolRow({
  name,
  args,
  result,
}: {
  name: string;
  args: JsonObject;
  result?: string;
}) {
  const summary = useMemo(() => {
    if (name === "search_docs") return String(args.query ?? "");
    if (name === "read_file" || name === "write_file")
      return String(args.path ?? "");
    if (name === "set_config")
      return `${String(args.path ?? "")} = ${JSON.stringify(args.value ?? null)}`.slice(
        0,
        120,
      );
    if (name === "invoke_local")
      return [args.function, args.method, args.path].filter(Boolean).join(" ");
    if (name === "validate" || name === "get_validation")
      return String(args.provider ?? "");
    if (name === "run_command")
      return `${String(args.command ?? "")}${args.server ? ` (on ${String(args.server)})` : ""}`.slice(
        0,
        120,
      );
    return "";
  }, [name, args]);
  const failed =
    !!result &&
    /(^error|Error:|invalid|Traceback|rejected)/m.test(result) &&
    !/Configuration is valid/.test(result);
  const icon: ReactNode =
    result === undefined ? (
      <span className="spinner spinner-sm" aria-hidden="true" />
    ) : failed ? (
      "⚠"
    ) : (
      "✓"
    );
  return (
    <details className={`hana-tool${failed ? " bad" : ""}`}>
      <summary>
        <span className="hana-tool-icon">{icon}</span>{" "}
        {TOOL_LABEL[name] || name}
        {summary && <span className="mono muted"> {summary}</span>}
      </summary>
      {result !== undefined && <pre className="hana-pre">{result}</pre>}
    </details>
  );
}

type Target = "local" | "huggingface" | "server" | "endpoint";

const CHOICES: { value: Target; title: string; text: string }[] = [
  {
    value: "local",
    title: "Docker on this machine",
    text: "Pulls the hana-pskit image and runs it in a container. The tested setup.",
  },
  {
    value: "huggingface",
    title: "Hugging Face (no Docker)",
    text: "Downloads the model file from Hugging Face and runs it inside studio with llama-cpp-python.",
  },
  {
    value: "server",
    title: "A saved server",
    text: "Runs the Docker image on one of your servers and connects through SSH.",
  },
  {
    value: "endpoint",
    title: "A model server I already run",
    text: "Any OpenAI-compatible URL: llama-server, Ollama, vLLM, LM Studio.",
  },
];

function HanaSetup({
  runtime,
  onDone,
  onRefresh,
}: {
  runtime: HanaRuntime;
  onDone: () => void;
  onRefresh: () => Promise<void>;
}) {
  const toast = useToast();
  const confirm = useConfirm();
  const recommended: Target = runtime.recommended || "huggingface";
  const [target, setTarget] = useState<Target>(runtime.target || recommended);
  const [image, setImage] = useState(runtime.image || runtime.default_image);
  const [file, setFile] = useState(
    runtime.hf_file || runtime.hf_files[0]?.file || "",
  );
  const [servers, setServers] = useState<OnPremServer[]>([]);
  const [server, setServer] = useState(runtime.server || "");
  const [url, setUrl] = useState(
    runtime.target === "endpoint" ? runtime.url || "" : "http://127.0.0.1:8080",
  );
  const [keyEnv, setKeyEnv] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const job = useJob(jobId);

  useEffect(() => {
    if (target !== "server") return;
    api.onpremServers().then(
      (r) => {
        setServers(r.servers);
        if (!server && r.servers.length) setServer(r.servers[0].name);
      },
      () => setServers([]),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target]);

  useEffect(() => {
    if (job.status === "succeeded") {
      toast("Hana is ready", "ok");
      onDone();
    } else if (job.status === "failed") {
      void onRefresh();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job.status]);

  const install = async () => {
    try {
      const r =
        target === "huggingface"
          ? await api.hanaInstall("huggingface", { file })
          : await api.hanaInstall(target === "server" ? "server" : "local", {
              server: target === "server" ? server : undefined,
              image,
            });
      setJobId(r.job_id);
    } catch (exc) {
      toast(errorMessage(exc), "err");
    }
  };

  const connect = async () => {
    try {
      const r = await api.hanaEndpoint(url, keyEnv || undefined);
      if (r.ready) toast("Connected to Hana", "ok");
      else
        toast(
          `Saved, but the model is not answering: ${r.error || "unknown error"}`,
          "info",
        );
      onDone();
    } catch (exc) {
      toast(errorMessage(exc), "err");
    }
  };

  const stop = async () => {
    const where =
      runtime.target === "server"
        ? `on ${runtime.server}`
        : runtime.target === "huggingface"
          ? "in studio"
          : runtime.target === "local"
            ? "on this machine"
            : "";
    const data =
      runtime.target === "huggingface"
        ? "the downloaded model file"
        : runtime.target === "endpoint"
          ? ""
          : `the image ${runtime.image}`;
    const answer = await confirm({
      title:
        runtime.target === "endpoint"
          ? "Forget this model server?"
          : `Stop Hana ${where}?`,
      body:
        runtime.target === "endpoint"
          ? "Studio stops using this URL; the server itself keeps running."
          : `The ${runtime.target === "huggingface" ? "model is unloaded" : "pskit-hana container is removed"}${runtime.target === "server" ? " and the SSH tunnel closed" : ""}. ${data ? `Keep ${data} to start again quickly, or delete it to free the disk space.` : ""}`,
      confirmLabel:
        runtime.target === "endpoint"
          ? "Forget"
          : `Stop, keep ${runtime.target === "huggingface" ? "the file" : "the image"}`,
      danger: true,
      extra: data
        ? [
            {
              label: `Stop and delete ${runtime.target === "huggingface" ? "the file" : "the image"}`,
              value: "data",
              danger: true,
            },
          ]
        : [],
    });
    if (!answer) return;
    try {
      const r = await api.hanaStop(answer === "data");
      await onRefresh();
      toast(
        r.removed && r.removed.length
          ? `Hana stopped; removed ${r.removed.join(", ")}`
          : "Hana stopped",
        "info",
      );
    } catch (exc) {
      toast(errorMessage(exc), "err");
    }
  };

  const busy = job.status === "running";
  const dockerDown = runtime.docker && runtime.docker.available === false;
  return (
    <div className="hana-setup">
      <b>{busy ? "Installing Hana…" : "Where should Hana run?"}</b>
      {jobId && (
        <InstallProgress
          lines={job.lines.map((l) => l.text)}
          status={job.status}
        />
      )}
      {!busy && (
        <>
          <p className="muted small">
            The model runs on a CPU (no GPU needed) and stays private: nothing
            you type is sent to a cloud.
          </p>
          <div
            className="hana-choices"
            role="radiogroup"
            aria-label="Where Hana runs"
          >
            {CHOICES.map((c) => (
              <label
                key={c.value}
                className={`hana-choice${target === c.value ? " on" : ""}`}
              >
                <input
                  type="radio"
                  name="hana-target"
                  checked={target === c.value}
                  onChange={() => setTarget(c.value)}
                  disabled={busy}
                />
                <span>
                  <b>{c.title}</b>
                  {c.value === recommended && (
                    <span className="badge badge-ok hana-rec">Recommended</span>
                  )}
                  {runtime.configured && runtime.target === c.value && (
                    <span className="badge badge-accent hana-rec">In use</span>
                  )}
                  <span className="muted small">{c.text}</span>
                </span>
              </label>
            ))}
          </div>
          {target === "local" && dockerDown && (
            <div className="hana-note err">
              {runtime.docker?.error} Or pick <b>Hugging Face (no Docker)</b>.
            </div>
          )}
          {target === "huggingface" && (
            <>
              <span className="muted small">Model size</span>
              <div className="hana-choices">
                {runtime.hf_files.map((f, i) => (
                  <label
                    key={f.file}
                    className={`hana-choice small${file === f.file ? " on" : ""}`}
                  >
                    <input
                      type="radio"
                      name="hana-file"
                      checked={file === f.file}
                      onChange={() => setFile(f.file)}
                      disabled={busy}
                    />
                    <span>
                      <b>{f.label}</b>
                      {i === 0 && (
                        <span className="badge badge-ok hana-rec">
                          Recommended
                        </span>
                      )}
                      <span className="muted small mono">{f.file}</span>
                    </span>
                  </label>
                ))}
              </div>
              <span className="muted small">
                From{" "}
                <code className="mono">huggingface.co/{runtime.hf_repo}</code>,
                saved in <code className="mono">~/.cache/pskit/hana/</code>.
                {runtime.llama_cpp
                  ? " llama-cpp-python is installed."
                  : " llama-cpp-python is installed first (a prebuilt CPU package)."}
              </span>
            </>
          )}
          {target === "server" && (
            <label className="hana-field">
              <span className="muted small">Server</span>
              {servers.length ? (
                <select
                  className="select select-sm"
                  value={server}
                  onChange={(e) => setServer(e.target.value)}
                  disabled={busy}
                >
                  {servers.map((s) => (
                    <option key={s.name} value={s.name}>
                      {s.name} ({s.user ? `${s.user}@` : ""}
                      {s.host})
                    </option>
                  ))}
                </select>
              ) : (
                <span className="muted small">
                  No saved servers yet: ask Hana to add one, or add it on the
                  Overview page (on-premises).
                </span>
              )}
            </label>
          )}
          {(target === "local" || target === "server") && (
            <label className="hana-field">
              <span className="muted small">Docker image</span>
              <input
                className="input input-sm mono"
                value={image}
                onChange={(e) => setImage(e.target.value)}
                disabled={busy}
              />
            </label>
          )}
          {target === "endpoint" && (
            <>
              <label className="hana-field">
                <span className="muted small">OpenAI-compatible URL</span>
                <input
                  className="input input-sm mono"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="http://127.0.0.1:8080"
                />
              </label>
              <label className="hana-field">
                <span className="muted small">
                  API key environment variable (optional; the key itself is
                  never stored)
                </span>
                <input
                  className="input input-sm mono"
                  value={keyEnv}
                  onChange={(e) => setKeyEnv(e.target.value.toUpperCase())}
                  placeholder="HANA_API_KEY"
                />
              </label>
            </>
          )}
          <div className="hana-actions">
            {target === "endpoint" ? (
              <button
                type="button"
                className="btn btn-primary btn-sm"
                onClick={() => void connect()}
                disabled={!url.trim()}
              >
                Connect
              </button>
            ) : (
              <button
                type="button"
                className="btn btn-primary btn-sm"
                onClick={() => void install()}
                disabled={
                  busy ||
                  (target === "server" && !server) ||
                  (target === "local" && !!dockerDown)
                }
              >
                {busy
                  ? "Installing…"
                  : target === "huggingface"
                    ? "Download & start"
                    : runtime.configured && runtime.target === target
                      ? "Reinstall & start"
                      : "Install & start"}
              </button>
            )}
            {runtime.configured && (
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => void stop()}
                disabled={busy}
              >
                {runtime.target === "endpoint"
                  ? "Forget"
                  : runtime.target === "huggingface"
                    ? "Stop"
                    : "Stop & remove"}
              </button>
            )}
            {runtime.configured && (
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={onDone}
                disabled={busy}
              >
                Close
              </button>
            )}
          </div>
        </>
      )}
    </div>
  );
}

/** The install job as a step label, a progress bar (download %) and the full log, always visible and scrolled. */
function InstallProgress({
  lines,
  status,
}: {
  lines: string[];
  status: string;
}) {
  const logRef = useRef<HTMLPreElement>(null);
  const [showLog, setShowLog] = useState(true);
  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [lines.length, showLog]);
  const steps = lines.filter((l) => l.startsWith("▶ ")).map((l) => l.slice(2));
  const step = steps[steps.length - 1] || "Starting…";
  let pct: number | null = null;
  let amount = "";
  for (let i = lines.length - 1; i >= 0; i--) {
    if (lines[i].startsWith("▶ ")) break; // only the current step's progress
    const m = /([\d.]+) \/ ([\d.]+) GB \((\d+)%\)/.exec(lines[i]);
    if (m) {
      pct = Number(m[3]);
      amount = `${m[1]} of ${m[2]} GB`;
      break;
    }
  }
  const done = status === "succeeded";
  const failed = status === "failed" || status === "cancelled";
  const width = done ? 100 : (pct ?? 0);
  return (
    <div
      className={`hana-progress${failed ? " failed" : ""}`}
      aria-live="polite"
    >
      <div className="hana-progress-head">
        <b>{done ? "Done" : failed ? "Install failed" : step}</b>
        <span className="muted small">
          {done
            ? ""
            : failed
              ? "see the log"
              : pct !== null
                ? `${amount} · ${pct}%`
                : `step ${Math.max(steps.length, 1)}`}
        </span>
      </div>
      <div
        className={`hana-bar${pct === null && !done && !failed ? " indeterminate" : ""}`}
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct ?? undefined}
        aria-label={step}
      >
        <span style={{ width: `${width}%` }} />
      </div>
      {steps.length > 1 && (
        <ol className="hana-steps-done small muted">
          {steps.map((s, i) => (
            <li
              key={i}
              className={
                i < steps.length - 1 || done ? "ok" : failed ? "bad" : "now"
              }
            >
              {s}
            </li>
          ))}
        </ol>
      )}
      <button
        type="button"
        className="link-btn small"
        onClick={() => setShowLog((v) => !v)}
      >
        {showLog ? "Hide" : "Show"} the log ({lines.length} lines)
      </button>
      {showLog && (
        <pre className="hana-pre hana-log" ref={logRef}>
          {lines.join("\n") || "starting…"}
        </pre>
      )}
    </div>
  );
}
