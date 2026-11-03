import { useState } from "react";
import { CopyButton } from "./CopyButton";

const MAX_CHILDREN = 200;

function Scalar({ value }: { value: unknown }) {
  if (value === null) return <span className="j-null">null</span>;
  if (typeof value === "string") return <span className="j-str">"{value}"</span>;
  if (typeof value === "number") return <span className="j-num">{String(value)}</span>;
  if (typeof value === "boolean") return <span className="j-bool">{String(value)}</span>;
  return <span className="j-null">{String(value)}</span>;
}

function Node({ name, value, depth }: { name?: string; value: unknown; depth: number }) {
  const isObj = value !== null && typeof value === "object";
  const [open, setOpen] = useState(depth < 2);
  const label = name !== undefined ? <span className="j-key">{name}: </span> : null;
  if (!isObj) {
    return (
      <div className="j-row">
        {label}
        <Scalar value={value} />
      </div>
    );
  }
  const entries: [string, unknown][] = Array.isArray(value)
    ? value.map((v, i) => [String(i), v])
    : Object.entries(value as Record<string, unknown>);
  const [l, r] = Array.isArray(value) ? ["[", "]"] : ["{", "}"];
  if (!entries.length) {
    return (
      <div className="j-row">
        {label}
        <span className="j-punct">
          {l}
          {r}
        </span>
      </div>
    );
  }
  return (
    <div className="j-row">
      <button type="button" className="j-toggle" onClick={() => setOpen(!open)} aria-expanded={open}>
        {open ? "▾" : "▸"}
      </button>
      {label}
      <span className="j-punct">{l}</span>
      {!open && (
        <button type="button" className="j-more" onClick={() => setOpen(true)}>
          {entries.length} {Array.isArray(value) ? "items" : "keys"}
        </button>
      )}
      {open && (
        <div className="j-children">
          {entries.slice(0, MAX_CHILDREN).map(([k, v]) => (
            <Node key={k} name={Array.isArray(value) ? undefined : k} value={v} depth={depth + 1} />
          ))}
          {entries.length > MAX_CHILDREN && <div className="muted">… {entries.length - MAX_CHILDREN} more</div>}
        </div>
      )}
      <span className="j-punct">{r}</span>
    </div>
  );
}

export function JsonView({ value, empty = "—" }: { value: unknown; empty?: string }) {
  if (value === undefined) return <span className="muted">{empty}</span>;
  let text = "";
  try {
    text = JSON.stringify(value, null, 2) ?? "";
  } catch {
    text = String(value);
  }
  return (
    <div className="json">
      <div className="json-tools">
        <CopyButton value={text} label="copy JSON" />
      </div>
      <Node value={value} depth={0} />
    </div>
  );
}
