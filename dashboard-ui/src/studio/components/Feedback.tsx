import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { Modal } from "../../components/Drawer";

// --------------------------------------------------------------------- toasts

type ToastTone = "ok" | "err" | "info" | "warn";
interface Toast {
  id: number;
  tone: ToastTone;
  text: string;
}

const ToastContext = createContext<(text: string, tone?: ToastTone) => void>(() => undefined);

export function useToast() {
  return useContext(ToastContext);
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const seq = useRef(0);
  const push = useCallback((text: string, tone: ToastTone = "ok") => {
    const id = ++seq.current;
    setToasts((t) => [...t.slice(-4), { id, tone, text }]);
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), tone === "err" ? 8000 : 3500);
  }, []);
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.tone}`}>
            <span>{t.text}</span>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              aria-label="Dismiss"
              onClick={() => setToasts((all) => all.filter((x) => x.id !== t.id))}
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

// --------------------------------------------------------------------- confirm

export interface ConfirmOptions {
  title: string;
  body?: ReactNode;
  confirmLabel?: string;
  danger?: boolean;
  /** Require the user to type this text before confirming. */
  typed?: string;
  /** Extra buttons resolving to their value. */
  extra?: { label: string; value: string; danger?: boolean }[];
}

type Resolver = (value: string | false) => void;
const ConfirmContext = createContext<(opts: ConfirmOptions) => Promise<string | false>>(() => Promise.resolve(false));

/** `await confirm({...})` resolves to "confirm", an extra button's value, or false. */
export function useConfirm() {
  return useContext(ConfirmContext);
}

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [current, setCurrent] = useState<(ConfirmOptions & { resolve: Resolver }) | null>(null);
  const [typed, setTyped] = useState("");
  const confirmRef = useRef<HTMLButtonElement>(null);
  const ask = useCallback(
    (opts: ConfirmOptions) =>
      new Promise<string | false>((resolve) => {
        setTyped("");
        setCurrent({ ...opts, resolve });
      }),
    [],
  );
  useEffect(() => {
    if (current && !current.typed) confirmRef.current?.focus();
  }, [current]);
  const close = (value: string | false) => {
    if (current) current.resolve(value);
    setCurrent(null);
  };
  const blocked = !!current?.typed && typed.trim() !== current.typed;
  return (
    <ConfirmContext.Provider value={ask}>
      {children}
      <Modal
        open={!!current}
        title={current?.title || ""}
        onClose={() => close(false)}
        footer={
          <>
            <button type="button" className="btn" onClick={() => close(false)}>
              Cancel
            </button>
            {(current?.extra || []).map((x) => (
              <button
                key={x.value}
                type="button"
                className={x.danger ? "btn btn-danger" : "btn"}
                onClick={() => close(x.value)}
              >
                {x.label}
              </button>
            ))}
            <button
              ref={confirmRef}
              type="button"
              className={current?.danger ? "btn btn-danger" : "btn btn-primary"}
              disabled={blocked}
              onClick={() => close("confirm")}
            >
              {current?.confirmLabel || "Confirm"}
            </button>
          </>
        }
      >
        <div className="stack">
          {current?.body && <div>{current.body}</div>}
          {current?.typed && (
            <label className="form-row">
              <span className="form-label">
                Type <code className="mono">{current.typed}</code> to confirm
              </span>
              <input
                className="input"
                autoFocus
                value={typed}
                onChange={(e) => setTyped(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !blocked) close("confirm");
                }}
              />
            </label>
          )}
        </div>
      </Modal>
    </ConfirmContext.Provider>
  );
}
