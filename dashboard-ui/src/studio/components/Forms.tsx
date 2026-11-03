import { useEffect, useId, useState, type ReactNode } from "react";
import type { Field, Json, JsonObject } from "../types";
import { ENV_RE, envRef, isObject, parseEnvRef, str } from "../util";
import { FilePickerModal } from "./FilePicker";

// --------------------------------------------------------------------- rows

export function FormRow({
  label,
  help,
  error,
  required,
  children,
  htmlFor,
  inline,
}: {
  label: ReactNode;
  help?: ReactNode;
  error?: string | string[] | null;
  required?: boolean;
  children: ReactNode;
  htmlFor?: string;
  inline?: boolean;
}) {
  const errors = !error ? [] : Array.isArray(error) ? error : [error];
  return (
    <div className={`form-row${inline ? " form-row-inline" : ""}${errors.length ? " has-error" : ""}`}>
      <label className="form-label" htmlFor={htmlFor}>
        {label}
        {required && (
          <span className="req" aria-label="required">
            *
          </span>
        )}
      </label>
      <div className="form-control">
        {children}
        {help && <div className="form-help">{help}</div>}
        {errors.map((e, i) => (
          <div key={i} className="form-error" role="alert">
            {e}
          </div>
        ))}
      </div>
    </div>
  );
}

export function TextInput({
  id,
  value,
  onChange,
  placeholder,
  mono,
  invalid,
  autoFocus,
  type = "text",
  onBlur,
  disabled,
  list,
}: {
  id?: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  mono?: boolean;
  invalid?: boolean;
  autoFocus?: boolean;
  type?: "text" | "password";
  onBlur?: () => void;
  disabled?: boolean;
  list?: string;
}) {
  return (
    <input
      id={id}
      className={`input${mono ? " mono" : ""}${invalid ? " invalid" : ""}`}
      value={value}
      type={type}
      placeholder={placeholder}
      autoFocus={autoFocus}
      aria-invalid={invalid || undefined}
      onChange={(e) => onChange(e.target.value)}
      onBlur={onBlur}
      disabled={disabled}
      spellCheck={false}
      autoComplete="off"
      list={list}
    />
  );
}

/** Number input that keeps partial text while typing and reports `undefined` when empty. */
export function NumberInput({
  id,
  value,
  onChange,
  min,
  max,
  step,
  integer,
  placeholder,
}: {
  id?: string;
  value: number | undefined | null;
  onChange: (v: number | undefined) => void;
  min?: number;
  max?: number;
  step?: number;
  integer?: boolean;
  placeholder?: string;
}) {
  const [text, setText] = useState(value === undefined || value === null ? "" : String(value));
  useEffect(() => {
    const parsed = text === "" ? undefined : Number(text);
    if (parsed !== value && !(parsed === undefined && (value === null || value === undefined))) {
      setText(value === undefined || value === null ? "" : String(value));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);
  const n = text === "" ? undefined : Number(text);
  const bad =
    n !== undefined &&
    (isNaN(n) || (integer && !Number.isInteger(n)) || (min !== undefined && n < min) || (max !== undefined && n > max));
  return (
    <input
      id={id}
      className={`input input-num${bad ? " invalid" : ""}`}
      inputMode={integer ? "numeric" : "decimal"}
      value={text}
      placeholder={placeholder}
      aria-invalid={bad || undefined}
      title={bad ? `must be ${integer ? "an integer " : "a number "}${min !== undefined ? `≥ ${min} ` : ""}${max !== undefined ? `≤ ${max}` : ""}` : undefined}
      onChange={(e) => {
        const t = e.target.value.trim();
        setText(t);
        if (t === "") return onChange(undefined);
        const v = Number(t);
        if (!isNaN(v)) onChange(v);
      }}
      step={step}
    />
  );
}

export function Toggle({
  checked,
  onChange,
  label,
  id,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label?: ReactNode;
  id?: string;
}) {
  return (
    <label className="toggle">
      <input id={id} type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span className="toggle-track" aria-hidden="true">
        <span className="toggle-thumb" />
      </span>
      {label && <span>{label}</span>}
    </label>
  );
}

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: { value: T; label: ReactNode; disabled?: boolean; title?: string }[];
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div className="segmented" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={o.value === value}
          className={o.value === value ? "seg active" : "seg"}
          disabled={o.disabled}
          title={o.title}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function EnumSelect({
  id,
  value,
  options,
  onChange,
  allowEmpty,
  emptyLabel = "—",
}: {
  id?: string;
  value: string;
  options: (string | { value: string; label: string; disabled?: boolean })[];
  onChange: (v: string) => void;
  allowEmpty?: boolean;
  emptyLabel?: string;
}) {
  return (
    <select id={id} className="select select-full" value={value} onChange={(e) => onChange(e.target.value)}>
      {allowEmpty && <option value="">{emptyLabel}</option>}
      {options.map((o) => {
        const opt = typeof o === "string" ? { value: o, label: o } : o;
        return (
          <option key={opt.value} value={opt.value} disabled={"disabled" in opt ? opt.disabled : false}>
            {opt.label}
          </option>
        );
      })}
    </select>
  );
}

// --------------------------------------------------------------------- dropdown with a custom value

export interface ComboOption {
  value: string;
  label?: string;
}

const CUSTOM = "__pskit_custom__";

/**
 * A dropdown of known values (regions, sizes, ...) that still accepts any other value:
 * "Custom…" reveals a text field. Unknown current values show up as custom.
 */
export function ComboInput({
  id,
  value,
  options,
  onChange,
  emptyLabel,
  placeholder,
  mono = true,
  numeric,
  invalid,
}: {
  id?: string;
  value: string;
  options: (string | number | ComboOption)[];
  onChange: (v: string) => void;
  /** Label of the empty choice (e.g. "default (us-east-1)"); omit to require a value. */
  emptyLabel?: string;
  placeholder?: string;
  mono?: boolean;
  numeric?: boolean;
  invalid?: boolean;
}) {
  const opts: ComboOption[] = options.map((o) => (typeof o === "object" ? o : { value: String(o) }));
  const known = value === "" || opts.some((o) => o.value === value);
  const [custom, setCustom] = useState(!known);
  useEffect(() => {
    if (!known) setCustom(true);
  }, [known]);
  return (
    <div className="combo">
      <select
        id={id}
        className={`select select-full${invalid ? " invalid" : ""}`}
        value={custom ? CUSTOM : value}
        onChange={(e) => {
          const v = e.target.value;
          if (v === CUSTOM) {
            setCustom(true);
            return;
          }
          setCustom(false);
          onChange(v);
        }}
      >
        {(emptyLabel !== undefined || value === "") && <option value="">{emptyLabel ?? "— choose —"}</option>}
        {opts.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label && o.label !== o.value ? `${o.label} · ${o.value}` : o.value}
          </option>
        ))}
        <option value={CUSTOM}>Custom…</option>
      </select>
      {custom && (
        <input
          className={`input${mono ? " mono" : ""}${invalid ? " invalid" : ""}`}
          value={value}
          autoFocus={!value}
          placeholder={placeholder || "type a value"}
          inputMode={numeric ? "numeric" : undefined}
          spellCheck={false}
          autoComplete="off"
          aria-label="Custom value"
          onChange={(e) => onChange(numeric ? e.target.value.replace(/[^0-9.]/g, "") : e.target.value)}
        />
      )}
    </div>
  );
}

/** A local file path with a "Browse…" picker served by the studio (e.g. an SSH key). */
export function FilePathInput({
  id,
  value,
  onChange,
  placeholder,
  keysOnly,
  folder,
  startAt,
  title,
}: {
  id?: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  keysOnly?: boolean;
  /** Choose a folder instead of a file. */
  folder?: boolean;
  /** Where the picker opens while the value is empty (default: ~/.ssh, for keys). */
  startAt?: string;
  title?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="row-gap grow">
      <TextInput id={id} mono value={value} placeholder={placeholder} onChange={onChange} />
      <button type="button" className="btn btn-sm" onClick={() => setOpen(true)}>
        Browse…
      </button>
      {value && (
        <button type="button" className="btn btn-ghost btn-sm" aria-label="Clear" onClick={() => onChange("")}>
          ✕
        </button>
      )}
      <FilePickerModal open={open} title={title} start={value || startAt || undefined} keysOnly={keysOnly} folder={folder} onClose={() => setOpen(false)} onPick={onChange} />
    </div>
  );
}

// --------------------------------------------------------------------- secret / env values

/**
 * A value that can be literal or read from an environment variable.
 * `mode="ref"` stores `${env:VAR}` in the same key (pskit.yml variables, resolved at deploy).
 * `mode="key"` stores `<key>_env: VAR` (on-prem drivers, resolved by the host at start).
 */
export function SecretValue({
  id,
  value,
  envVar,
  onLiteral,
  onEnv,
  secret,
  placeholder,
}: {
  id?: string;
  value: string;
  envVar: string | null;
  onLiteral: (v: string) => void;
  onEnv: (variable: string) => void;
  secret?: boolean;
  placeholder?: string;
}) {
  const [useEnv, setUseEnv] = useState(envVar !== null || !!secret);
  const [show, setShow] = useState(false);
  useEffect(() => {
    if (envVar !== null) setUseEnv(true);
  }, [envVar]);
  const badVar = useEnv && !!envVar && !ENV_RE.test(envVar);
  return (
    <div className="secret">
      <Segmented
        label="Value source"
        value={useEnv ? "env" : "value"}
        onChange={(v) => {
          setUseEnv(v === "env");
          if (v === "env") onEnv(envVar || "");
          else onLiteral("");
        }}
        options={[
          { value: "value", label: "Value" },
          { value: "env", label: "From env var", title: "Read from an environment variable instead of writing the value" },
        ]}
      />
      {useEnv ? (
        <TextInput
          id={id}
          mono
          value={envVar || ""}
          invalid={badVar}
          placeholder="ENV_VARIABLE_NAME"
          onChange={(v) => onEnv(v.replace(/[^A-Za-z0-9_]/g, "_").toUpperCase())}
        />
      ) : (
        <div className="row-gap grow">
          <TextInput
            id={id}
            value={value}
            type={secret && !show ? "password" : "text"}
            placeholder={placeholder}
            onChange={onLiteral}
          />
          {secret && (
            <button type="button" className="btn btn-sm" onClick={() => setShow((s) => !s)}>
              {show ? "Hide" : "Show"}
            </button>
          )}
        </div>
      )}
      {secret && !useEnv && value && (
        <div className="form-help warn-text">
          Literal secrets are written to pskit.yml and the deployed config. Prefer an environment variable.
        </div>
      )}
    </div>
  );
}

// --------------------------------------------------------------------- key/value + list

export function KeyValueEditor({
  value,
  onChange,
  keyPlaceholder = "KEY",
  valuePlaceholder = "value",
  secrets = true,
  keyPattern,
  addLabel = "Add variable",
}: {
  value: JsonObject;
  onChange: (next: JsonObject | undefined) => void;
  keyPlaceholder?: string;
  valuePlaceholder?: string;
  /** Offer "from env var" per row (stores ${env:VAR}). */
  secrets?: boolean;
  keyPattern?: RegExp;
  addLabel?: string;
}) {
  // Rows are kept locally so a half-typed (or duplicate) key doesn't lose its value.
  const toRows = (v: JsonObject) => Object.entries(v).map(([k, val]) => ({ k, v: str(val) }));
  const [rows, setRows] = useState(() => toRows(value));
  useEffect(() => {
    const current: JsonObject = {};
    for (const r of rows) if (r.k) current[r.k] = r.v;
    if (JSON.stringify(current) !== JSON.stringify(value)) setRows(toRows(value));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);
  const commit = (next: { k: string; v: string }[]) => {
    setRows(next);
    const out: JsonObject = {};
    for (const r of next) if (r.k.trim()) out[r.k.trim()] = r.v;
    onChange(Object.keys(out).length ? out : undefined);
  };
  const keys = rows.map((r) => r.k.trim());
  return (
    <div className="kv">
      {rows.map((row, i) => {
        const dup = row.k.trim() !== "" && keys.indexOf(row.k.trim()) !== i;
        const badKey = !!row.k && !!keyPattern && !keyPattern.test(row.k.trim());
        const envVar = parseEnvRef(row.v);
        return (
          <div className="kv-row" key={i}>
            <TextInput
              mono
              value={row.k}
              placeholder={keyPlaceholder}
              invalid={dup || badKey}
              onChange={(k) => commit(rows.map((r, j) => (j === i ? { ...r, k } : r)))}
            />
            {envVar !== null ? (
              <div className="kv-env">
                <span className="chip">env</span>
                <TextInput
                  mono
                  value={envVar}
                  onChange={(v) =>
                    commit(rows.map((r, j) => (j === i ? { ...r, v: envRef(v.replace(/[^A-Za-z0-9_]/g, "_").toUpperCase()) } : r)))
                  }
                />
              </div>
            ) : (
              <TextInput
                value={row.v}
                placeholder={valuePlaceholder}
                onChange={(v) => commit(rows.map((r, j) => (j === i ? { ...r, v } : r)))}
              />
            )}
            {secrets && (
              <button
                type="button"
                className="btn btn-sm"
                title={envVar !== null ? "Use a literal value" : "Read the value from an environment variable at deploy time"}
                onClick={() =>
                  commit(
                    rows.map((r, j) =>
                      j === i ? { ...r, v: envVar !== null ? "" : envRef(r.k.trim().toUpperCase().replace(/[^A-Z0-9_]/g, "_") || "VAR") } : r,
                    ),
                  )
                }
              >
                {envVar !== null ? "literal" : "${env}"}
              </button>
            )}
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              aria-label={`Remove ${row.k || "row"}`}
              onClick={() => commit(rows.filter((_, j) => j !== i))}
            >
              ✕
            </button>
            {(dup || badKey) && <div className="form-error kv-err">{dup ? "duplicate key" : "invalid key"}</div>}
          </div>
        );
      })}
      <button type="button" className="btn btn-sm" onClick={() => setRows([...rows, { k: "", v: "" }])}>
        + {addLabel}
      </button>
    </div>
  );
}

export function ListEditor({
  value,
  onChange,
  placeholder,
  addLabel = "Add",
  suggestions,
}: {
  value: string[];
  onChange: (next: string[] | undefined) => void;
  placeholder?: string;
  addLabel?: string;
  suggestions?: string[];
}) {
  const listId = useId();
  const [rows, setRows] = useState(value);
  useEffect(() => {
    if (JSON.stringify(rows.filter(Boolean)) !== JSON.stringify(value)) setRows(value);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);
  const commit = (next: string[]) => {
    setRows(next);
    const clean = next.map((s) => s.trim()).filter(Boolean);
    onChange(clean.length ? clean : undefined);
  };
  return (
    <div className="kv">
      {suggestions && (
        <datalist id={listId}>
          {suggestions.map((s) => (
            <option key={s} value={s} />
          ))}
        </datalist>
      )}
      {rows.map((v, i) => (
        <div className="kv-row kv-row-single" key={i}>
          <TextInput
            value={v}
            placeholder={placeholder}
            list={suggestions ? listId : undefined}
            onChange={(t) => commit(rows.map((r, j) => (j === i ? t : r)))}
          />
          <button type="button" className="btn btn-ghost btn-sm" aria-label="Remove" onClick={() => commit(rows.filter((_, j) => j !== i))}>
            ✕
          </button>
        </div>
      ))}
      <button type="button" className="btn btn-sm" onClick={() => setRows([...rows, ""])}>
        + {addLabel}
      </button>
    </div>
  );
}

/** JSON editor (textarea) that only reports valid JSON. */
export function JsonInput({
  id,
  value,
  onChange,
  rows = 6,
  placeholder,
}: {
  id?: string;
  value: Json | undefined;
  onChange: (v: Json | undefined) => void;
  rows?: number;
  placeholder?: string;
}) {
  const [text, setText] = useState(value === undefined ? "" : JSON.stringify(value, null, 2));
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let current: Json | undefined;
    try {
      current = text.trim() ? (JSON.parse(text) as Json) : undefined;
    } catch {
      return;
    }
    if (JSON.stringify(current) !== JSON.stringify(value)) setText(value === undefined ? "" : JSON.stringify(value, null, 2));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);
  return (
    <div>
      <textarea
        id={id}
        className={`input code-area${error ? " invalid" : ""}`}
        rows={rows}
        value={text}
        placeholder={placeholder}
        spellCheck={false}
        onChange={(e) => {
          const t = e.target.value;
          setText(t);
          if (!t.trim()) {
            setError(null);
            onChange(undefined);
            return;
          }
          try {
            const parsed = JSON.parse(t) as Json;
            setError(null);
            onChange(parsed);
          } catch (exc) {
            setError(exc instanceof Error ? exc.message : "invalid JSON");
          }
        }}
      />
      {error && <div className="form-error">{error}</div>}
    </div>
  );
}

// --------------------------------------------------------------------- generic form

export interface FieldFormProps {
  fields: Field[];
  value: JsonObject;
  /** `undefined` removes the key. */
  onChange: (key: string, value: Json | undefined) => void;
  /** How env-capable fields store an env var: `<key>_env` (on-prem drivers) or `${env:VAR}`. */
  envStyle?: "key" | "ref";
  skip?: string[];
  errorsFor?: (key: string) => string[];
  idPrefix?: string;
  compact?: boolean;
}

export function fieldError(field: Field, value: JsonObject, envStyle: "key" | "ref"): string | null {
  const v = value[field.key];
  const env = envStyle === "key" ? value[`${field.key}_env`] : null;
  const empty = (v === undefined || v === null || v === "") && (env === undefined || env === null || env === "");
  if (field.required && empty) return `${field.label} is required`;
  if (empty) return null;
  if ((field.type === "int" || field.type === "number") && typeof v === "number") {
    if (field.type === "int" && !Number.isInteger(v)) return "must be a whole number";
    if (field.min !== undefined && v < field.min) return `must be ≥ ${field.min}`;
    if (field.max !== undefined && v > field.max) return `must be ≤ ${field.max}`;
  }
  if (field.type === "enum" && field.options && v !== undefined && !field.options.map(String).includes(String(v))) {
    return `must be one of ${field.options.join(", ")}`;
  }
  return null;
}

export function FieldForm({ fields, value, onChange, envStyle = "ref", skip, errorsFor, idPrefix = "f", compact }: FieldFormProps) {
  const base = useId();
  return (
    <div className={compact ? "form form-compact" : "form"}>
      {fields
        .filter((f) => !skip || !skip.includes(f.key))
        .map((field) => {
          const id = `${base}-${idPrefix}-${field.key}`;
          const errs = [...(errorsFor ? errorsFor(field.key) : [])];
          const local = fieldError(field, value, envStyle);
          if (local) errs.unshift(local);
          return (
            <FormRow key={field.key} label={field.label} help={field.help} required={field.required} error={errs} htmlFor={id}>
              <FieldControl id={id} field={field} value={value} onChange={onChange} envStyle={envStyle} />
            </FormRow>
          );
        })}
    </div>
  );
}

function FieldControl({
  id,
  field,
  value,
  onChange,
  envStyle,
}: {
  id: string;
  field: Field;
  value: JsonObject;
  onChange: (key: string, v: Json | undefined) => void;
  envStyle: "key" | "ref";
}) {
  const v = value[field.key];
  const placeholder = field.placeholder ?? (field.default !== undefined && field.default !== null ? `default: ${String(field.default)}` : undefined);
  const set = (x: Json | undefined) => onChange(field.key, x === "" ? undefined : x);

  if (field.type === "secret" || field.env_ok) {
    const envVar =
      envStyle === "key"
        ? typeof value[`${field.key}_env`] === "string"
          ? (value[`${field.key}_env`] as string)
          : null
        : parseEnvRef(v);
    if (field.type === "secret" || field.type === "string") {
      return (
        <SecretValue
          id={id}
          secret={field.type === "secret"}
          value={envVar === null ? str(v) : ""}
          envVar={envVar}
          placeholder={placeholder}
          onLiteral={(t) => {
            if (envStyle === "key") onChange(`${field.key}_env`, undefined);
            set(t);
          }}
          onEnv={(variable) => {
            if (envStyle === "key") {
              onChange(field.key, undefined);
              onChange(`${field.key}_env`, variable);
            } else {
              set(envRef(variable));
            }
          }}
        />
      );
    }
  }
  if (field.type === "file") {
    return (
      <FilePathInput
        id={id}
        value={str(v)}
        placeholder={placeholder}
        keysOnly={/pem|key|identity/i.test(field.key)}
        title={`Choose: ${field.label}`}
        onChange={(t) => set(t)}
      />
    );
  }
  if (field.suggestions && field.suggestions.length && (field.type === "string" || field.type === "int" || field.type === "number")) {
    const numeric = field.type !== "string";
    return (
      <ComboInput
        id={id}
        value={v === undefined || v === null ? "" : String(v)}
        options={field.suggestions.map((s) => String(s))}
        numeric={numeric}
        placeholder={placeholder}
        emptyLabel={field.default !== undefined && field.default !== null ? `default (${String(field.default)})` : field.required ? undefined : "—"}
        onChange={(s) => {
          if (!numeric) return set(s);
          const n = s === "" ? undefined : Number(s);
          set(n === undefined || isNaN(n) ? undefined : n);
        }}
      />
    );
  }
  switch (field.type) {
    case "bool":
      return (
        <Toggle
          id={id}
          checked={v === undefined || v === null ? field.default === true : v === true}
          onChange={(b) => set(b === (field.default === true) && v === undefined ? undefined : b)}
        />
      );
    case "int":
    case "number":
      return (
        <NumberInput
          id={id}
          value={typeof v === "number" ? v : undefined}
          integer={field.type === "int"}
          min={field.min}
          max={field.max}
          placeholder={placeholder}
          onChange={set}
        />
      );
    case "enum":
      return (
        <EnumSelect
          id={id}
          value={v === undefined || v === null ? "" : String(v)}
          options={(field.options || []).map((o) => String(o))}
          allowEmpty={!field.required}
          emptyLabel={field.default !== undefined && field.default !== null ? `default (${String(field.default)})` : "—"}
          onChange={(s) => {
            const opt = (field.options || []).find((o) => String(o) === s);
            set(s === "" ? undefined : opt === undefined ? s : opt);
          }}
        />
      );
    case "list":
      return (
        <ListEditor
          value={Array.isArray(v) ? v.map((x) => str(x)) : typeof v === "string" && v ? [v] : []}
          placeholder={placeholder}
          onChange={(l) => set(l)}
        />
      );
    case "map":
      return <KeyValueEditor value={isObject(v) ? v : {}} onChange={(m) => set(m)} addLabel="Add entry" />;
    case "json":
      return <JsonInput id={id} value={v} onChange={set} placeholder={placeholder} />;
    case "code":
      return (
        <textarea
          id={id}
          className="input code-area"
          rows={6}
          spellCheck={false}
          value={str(v)}
          placeholder={placeholder}
          onChange={(e) => set(e.target.value)}
        />
      );
    default:
      return <TextInput id={id} value={str(v)} placeholder={placeholder} onChange={(t) => set(t)} />;
  }
}

/** Collapsible section. */
export function Section({
  title,
  children,
  defaultOpen = true,
  actions,
  hint,
}: {
  title: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
  actions?: ReactNode;
  hint?: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className="section card">
      <header className="section-head">
        <button type="button" className="section-toggle" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          <span className="caret" aria-hidden="true">
            {open ? "▾" : "▸"}
          </span>
          <span className="section-title">{title}</span>
          {hint && <span className="muted section-hint">{hint}</span>}
        </button>
        {actions && <div className="row-gap">{actions}</div>}
      </header>
      {open && <div className="section-body">{children}</div>}
    </section>
  );
}
