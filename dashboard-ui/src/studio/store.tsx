import { createContext, useCallback, useContext, useEffect, useMemo, useReducer, useRef, type ReactNode } from "react";
import { api, ApiError, errorMessage } from "./api";
import type { Issue, Json, JsonObject, Meta, ProjectState, ProviderMeta, ValidateResult } from "./types";
import { clearShadow } from "./shadow";
import { asObject, deepEqual, getIn, isObject, parseWhere, pathKey, setIn, str, type Path } from "./util";

const HISTORY_CAP = 100;
const COALESCE_MS = 800;
const VALIDATE_DEBOUNCE_MS = 600;

interface State {
  meta: Meta | null;
  project: ProjectState | null;
  saved: JsonObject | null;
  draft: JsonObject | null;
  past: JsonObject[];
  future: JsonObject[];
  lastEdit: { key: string; at: number } | null;
  mtime: number | null;
  validation: ValidateResult | null;
  validating: boolean;
  validationError: string | null;
  /** Provider/stage used for validation and deploy. Defaults to the draft's provider. */
  target: { provider: string; stage: string } | null;
  conflict: boolean;
  saving: boolean;
}

type Action =
  | { type: "loaded"; project: ProjectState; meta: Meta }
  | { type: "project"; project: ProjectState }
  | { type: "edit"; path: Path; value: Json | undefined; coalesce?: boolean }
  | { type: "replace"; raw: JsonObject }
  | { type: "undo" }
  | { type: "redo" }
  | { type: "validating" }
  | { type: "validated"; result: ValidateResult }
  | { type: "validationFailed"; error: string }
  | { type: "target"; provider?: string; stage?: string }
  | { type: "conflict"; open: boolean }
  | { type: "saving"; on: boolean };

const initial: State = {
  meta: null,
  project: null,
  saved: null,
  draft: null,
  past: [],
  future: [],
  lastEdit: null,
  mtime: null,
  validation: null,
  validating: false,
  validationError: null,
  target: null,
  conflict: false,
  saving: false,
};

function push(state: State, next: JsonObject, key: string | null): State {
  if (state.draft && deepEqual(state.draft, next)) return state;
  const now = Date.now();
  const coalesce =
    key !== null && state.lastEdit && state.lastEdit.key === key && now - state.lastEdit.at < COALESCE_MS && state.past.length;
  const past = coalesce || !state.draft ? state.past : [...state.past, state.draft].slice(-HISTORY_CAP);
  return { ...state, draft: next, past, future: [], lastEdit: key === null ? null : { key, at: now } };
}

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "loaded":
    case "project": {
      const raw = action.project.raw ? (JSON.parse(JSON.stringify(action.project.raw)) as JsonObject) : null;
      const meta = action.type === "loaded" ? action.meta : state.meta;
      const provider = str(getIn(raw ?? undefined, ["provider", "name"]), "aws");
      const stage = str(getIn(raw ?? undefined, ["provider", "stage"]), "dev");
      return {
        ...state,
        meta,
        project: action.project,
        saved: raw,
        draft: raw,
        past: [],
        future: [],
        lastEdit: null,
        mtime: action.project.mtime ?? null,
        validation: action.project.issues ? { ok: !action.project.issues.some((i) => i.level === "error"), issues: action.project.issues } : null,
        target: state.target && action.type === "project" ? state.target : { provider, stage },
        conflict: false,
      };
    }
    case "edit": {
      if (!state.draft) return state;
      // A provider setting edited here must not lose to a stale copy under providers.<active provider>.
      const next = clearShadow(setIn(state.draft, action.path, action.value) as JsonObject, action.path);
      return push(state, next, action.coalesce === false ? null : pathKey(action.path));
    }
    case "replace":
      return push(state, action.raw, null);
    case "undo": {
      if (!state.past.length || !state.draft) return state;
      const prev = state.past[state.past.length - 1];
      return { ...state, draft: prev, past: state.past.slice(0, -1), future: [state.draft, ...state.future], lastEdit: null };
    }
    case "redo": {
      if (!state.future.length || !state.draft) return state;
      const [next, ...rest] = state.future;
      return { ...state, draft: next, past: [...state.past, state.draft], future: rest, lastEdit: null };
    }
    case "validating":
      return { ...state, validating: true };
    case "validated":
      return { ...state, validating: false, validation: action.result, validationError: null };
    case "validationFailed":
      return { ...state, validating: false, validationError: action.error };
    case "target": {
      const cur = state.target || { provider: "aws", stage: "dev" };
      return { ...state, target: { provider: action.provider ?? cur.provider, stage: action.stage ?? cur.stage } };
    }
    case "conflict":
      return { ...state, conflict: action.open };
    case "saving":
      return { ...state, saving: action.on };
    default:
      return state;
  }
}

export interface Studio {
  state: State;
  meta: Meta;
  draft: JsonObject;
  dirty: boolean;
  provider: ProviderMeta | undefined;
  providerName: string;
  edit: (path: Path, value: Json | undefined, opts?: { coalesce?: boolean }) => void;
  replace: (raw: JsonObject) => void;
  undo: () => void;
  redo: () => void;
  /** Save the draft (or `raw`, which also becomes the draft). */
  save: (force?: boolean, raw?: JsonObject) => Promise<boolean>;
  reload: () => Promise<void>;
  setProject: (project: ProjectState) => void;
  setTarget: (provider?: string, stage?: string) => void;
  closeConflict: () => void;
  validateNow: () => void;
  issuesAt: (path: Path, exact?: boolean) => Issue[];
  supports: (capability: string, provider?: string) => boolean;
}

const StudioContext = createContext<Studio | null>(null);

export function useStudio(): Studio {
  const ctx = useContext(StudioContext);
  if (!ctx) throw new Error("useStudio outside <StudioProvider>");
  return ctx;
}

export function StudioProvider({
  project,
  meta,
  children,
}: {
  project: ProjectState;
  meta: Meta;
  children: ReactNode;
}) {
  const [state, dispatch] = useReducer(reducer, initial, (s) => reducer(s, { type: "loaded", project, meta }));
  const abort = useRef<AbortController | null>(null);
  const tick = useRef(0);

  const runValidation = useCallback(
    (draft: JsonObject, provider?: string, stage?: string) => {
      if (abort.current) abort.current.abort();
      const controller = new AbortController();
      abort.current = controller;
      const mine = ++tick.current;
      dispatch({ type: "validating" });
      api
        .validate(draft, provider, stage, controller.signal)
        .then((result) => {
          if (mine === tick.current) dispatch({ type: "validated", result });
        })
        .catch((exc: unknown) => {
          if (exc instanceof DOMException && exc.name === "AbortError") return;
          if (mine === tick.current) dispatch({ type: "validationFailed", error: errorMessage(exc) });
        });
    },
    [],
  );

  // Live validation of the draft (debounced; stale requests are aborted).
  useEffect(() => {
    if (!state.draft) return undefined;
    const draft = state.draft;
    const t = state.target;
    const timer = window.setTimeout(() => runValidation(draft, t?.provider, t?.stage), VALIDATE_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [state.draft, state.target, runValidation]);

  useEffect(() => () => abort.current?.abort(), []);

  const dirty = !!state.draft && !deepEqual(state.draft, state.saved);

  // Unsaved-changes guard.
  useEffect(() => {
    if (!dirty) return undefined;
    const onBefore = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", onBefore);
    return () => window.removeEventListener("beforeunload", onBefore);
  }, [dirty]);

  const save = useCallback(
    async (force = false, raw?: JsonObject): Promise<boolean> => {
      const draft = raw ?? state.draft;
      if (!draft) return false;
      if (raw) dispatch({ type: "replace", raw });
      dispatch({ type: "saving", on: true });
      try {
        const saved = await api.save(draft, state.mtime, force);
        dispatch({ type: "project", project: saved });
        return true;
      } catch (exc) {
        if (exc instanceof ApiError && exc.status === 409) {
          dispatch({ type: "conflict", open: true });
          return false;
        }
        throw exc;
      } finally {
        dispatch({ type: "saving", on: false });
      }
    },
    [state.draft, state.mtime],
  );

  const reload = useCallback(async () => {
    const fresh = await api.project();
    dispatch({ type: "project", project: fresh });
  }, []);

  const issues = state.validation?.issues || [];
  const providerName = str(getIn(state.draft ?? undefined, ["provider", "name"]), "aws");
  const metaValue = state.meta as Meta;

  const value = useMemo<Studio>(
    () => ({
      state,
      meta: metaValue,
      draft: state.draft || {},
      dirty,
      providerName,
      provider: metaValue.providers.find((p) => p.name === providerName),
      edit: (path, v, opts) => dispatch({ type: "edit", path, value: v, coalesce: opts?.coalesce }),
      replace: (raw) => dispatch({ type: "replace", raw }),
      undo: () => dispatch({ type: "undo" }),
      redo: () => dispatch({ type: "redo" }),
      save,
      reload,
      setProject: (p) => dispatch({ type: "project", project: p }),
      setTarget: (provider, stage) => dispatch({ type: "target", provider, stage }),
      closeConflict: () => dispatch({ type: "conflict", open: false }),
      validateNow: () => {
        if (state.draft) runValidation(state.draft, state.target?.provider, state.target?.stage);
      },
      issuesAt: (path, exact = false) => {
        const want = pathKey(path);
        return issues.filter((i) => {
          if (!i.where) return false;
          const got = pathKey(parseWhere(i.where));
          return exact ? got === want : got === want || got.startsWith(want + ".") || got.startsWith(want + "[");
        });
      },
      supports: (capability, provider) => {
        const p = metaValue.providers.find((x) => x.name === (provider || providerName));
        return !!p && p.capabilities.includes(capability);
      },
    }),
    [state, metaValue, dirty, providerName, save, reload, issues, runValidation],
  );

  return <StudioContext.Provider value={value}>{children}</StudioContext.Provider>;
}

/** Section of the draft as an object (never undefined). */
export function useSection(path: Path): JsonObject {
  const { draft } = useStudio();
  return asObject(getIn(draft, path));
}

export function providersSupporting(meta: Meta, capability: string): string[] {
  return meta.providers.filter((p) => p.capabilities.includes(capability)).map((p) => p.display_name);
}

export function isObj(v: unknown): v is JsonObject {
  return isObject(v);
}
