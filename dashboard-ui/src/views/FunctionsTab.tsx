import { useMemo, useState } from "react";
import type { Deployment, FunctionRecord, FunctionStats } from "../types";
import { formatDuration, relative } from "../format";
import { Badge, Chip } from "../components/Badge";
import { CopyButton } from "../components/CopyButton";
import { DataTable, type Column } from "../components/DataTable";
import { Drawer } from "../components/Drawer";
import { SearchInput, Select } from "../components/Inputs";
import { ExtLink } from "../components/Link";

function Endpoints({ f }: { f: FunctionRecord }) {
  const urls = f.urls || [];
  if (urls.length)
    return (
      <div className="stack-xs">
        {urls.map((u) => (
          <div key={`${u.method} ${u.url}`} className="row-gap">
            <Chip accent>{u.method}</Chip>
            <ExtLink href={u.url} />
          </div>
        ))}
      </div>
    );
  if (f.url) return <ExtLink href={f.url} />;
  return <span className="muted">—</span>;
}

export function FunctionsTab({ deployment, stats }: { deployment: Deployment; stats?: Record<string, FunctionStats> }) {
  const [q, setQ] = useState("");
  const [kind, setKind] = useState("");
  const [open, setOpen] = useState<FunctionRecord | null>(null);
  const fns = deployment.functions || [];
  const kinds = useMemo(() => Array.from(new Set(fns.map((f) => f.kind))).sort(), [fns]);
  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return fns.filter((f) => {
      if (kind && f.kind !== kind) return false;
      if (!needle) return true;
      return [f.name, f.resource_name, f.handler, f.url, f.id, f.arn, f.description, ...(f.events || []).map((e) => e.summary)]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(needle);
    });
  }, [fns, q, kind]);

  const columns: Column<FunctionRecord>[] = [
    {
      key: "name",
      header: "Function",
      sortValue: (f) => f.name,
      render: (f) => (
        <div className="cell-name">
          <b>
            {f.name} {f.generated && <Badge tone="off">generated</Badge>}
          </b>
          <small className="mono">{f.resource_name || ""}</small>
        </div>
      ),
    },
    { key: "kind", header: "Type", sortValue: (f) => f.kind, render: (f) => <Badge tone={f.kind === "invoke-only" ? "off" : "accent"}>{f.kind}</Badge> },
    {
      key: "triggers",
      header: "Triggers",
      render: (f) =>
        (f.events || []).length ? (
          <div className="chips">
            {(f.events || []).map((e, i) => (
              <Chip key={i} accent={e.type === "http"} title={e.type}>
                {e.summary}
              </Chip>
            ))}
          </div>
        ) : (
          <span className="muted">direct invoke</span>
        ),
    },
    {
      key: "runtime",
      header: "Runtime",
      sortValue: (f) => f.memory,
      render: (f) => (
        <div className="mono nowrap">
          <div>{f.runtime}</div>
          <div className="muted">
            {f.memory} MB · {f.timeout} s
          </div>
        </div>
      ),
    },
  ];
  if (stats) {
    columns.push({
      key: "inv",
      header: "Invocations",
      sortValue: (f) => (stats[f.name] && stats[f.name].invocations) || 0,
      render: (f) => {
        const s = stats[f.name];
        if (!s) return <span className="muted">0</span>;
        return (
          <div className="nowrap">
            <b>{s.invocations || 0}</b>
            {s.errors ? <Badge tone="err">{s.errors} err</Badge> : null}
            <div className="muted">avg {formatDuration(s.avg_duration_ms)}</div>
          </div>
        );
      },
    });
  }
  columns.push({ key: "endpoint", header: "Endpoint", render: (f) => <span onClick={(e) => e.stopPropagation()}><Endpoints f={f} /></span> });

  const ident = open ? open.arn || open.id : null;
  const s = open && stats ? stats[open.name] : undefined;

  return (
    <div className="stack">
      <div className="toolbar">
        <SearchInput value={q} onChange={setQ} placeholder="Filter functions…" />
        <Select label="Type" allLabel="All types" value={kind} onChange={setKind} options={kinds} />
      </div>
      <div className="card">
        <DataTable
          columns={columns}
          rows={rows}
          rowKey={(f) => f.name}
          onRowClick={setOpen}
          selectedKey={open ? open.name : null}
          emptyTitle="No functions match"
        />
      </div>
      <Drawer open={!!open} title={open ? open.name : ""} onClose={() => setOpen(null)}>
        {open && (
          <dl className="props">
            <dt>Handler</dt>
            <dd className="mono">{open.handler}</dd>
            {open.description && (
              <>
                <dt>Description</dt>
                <dd>{open.description}</dd>
              </>
            )}
            <dt>Resource</dt>
            <dd>
              {ident ? (
                <>
                  <span className="mono">{ident}</span> <CopyButton value={ident} />
                </>
              ) : (
                <span className="muted">not deployed</span>
              )}
            </dd>
            {open.console && (
              <>
                <dt>Console</dt>
                <dd>
                  <ExtLink href={open.console}>Open in console ↗</ExtLink>
                </dd>
              </>
            )}
            <dt>Runtime</dt>
            <dd className="mono">
              {open.runtime} · {open.architecture} · {open.memory} MB · {open.timeout} s
            </dd>
            <dt>Endpoints</dt>
            <dd>
              <Endpoints f={open} />
            </dd>
            <dt>Triggers</dt>
            <dd className="chips">
              {(open.events || []).length ? (open.events || []).map((e, i) => <Chip key={i}>{e.summary}</Chip>) : <span className="muted">direct invoke</span>}
            </dd>
            <dt>Environment</dt>
            <dd className="chips">
              {(open.environment_keys || []).length ? (open.environment_keys || []).map((k) => <Chip key={k}>{k}</Chip>) : <span className="muted">—</span>}
            </dd>
            {s && (
              <>
                <dt>Activity</dt>
                <dd>
                  {s.invocations || 0} invocations · {s.errors || 0} errors · avg {formatDuration(s.avg_duration_ms)} · last{" "}
                  {formatDuration(s.last_duration_ms)} {s.last_at ? `(${relative(s.last_at)})` : ""}
                  {s.last_error && <div className="text-err mono">{s.last_error}</div>}
                </dd>
              </>
            )}
          </dl>
        )}
      </Drawer>
    </div>
  );
}
