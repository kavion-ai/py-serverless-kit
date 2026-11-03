import { useMemo, useState } from "react";
import type { Deployment } from "../types";
import { deploymentKey } from "../api";
import { formatDate, relative, statusTone } from "../format";
import { Badge } from "../components/Badge";
import { StatCard } from "../components/Card";
import { DataTable, type Column } from "../components/DataTable";
import { SearchInput, Select } from "../components/Inputs";
import { ExtLink } from "../components/Link";

export function Overview({ deployments, onOpen }: { deployments: Deployment[]; onOpen: (key: string) => void }) {
  const [q, setQ] = useState("");
  const [provider, setProvider] = useState("");
  const [stage, setStage] = useState("");

  const providers = useMemo(() => {
    const seen = new Map<string, string>();
    deployments.forEach((d) => seen.set(d.provider, d.provider_display || d.provider));
    return Array.from(seen, ([value, label]) => ({ value, label })).sort((a, b) => a.label.localeCompare(b.label));
  }, [deployments]);
  const stages = useMemo(() => Array.from(new Set(deployments.map((d) => d.stage))).sort(), [deployments]);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return deployments.filter((d) => {
      if (provider && d.provider !== provider) return false;
      if (stage && d.stage !== stage) return false;
      if (!needle) return true;
      const hay = [
        d.service,
        d.stage,
        d.provider,
        d.endpoint,
        d.region,
        ...(d.functions || []).flatMap((f) => [f.name, f.handler, f.url, ...(f.events || []).map((e) => e.summary)]),
        ...(d.workflows || []).map((w) => w.name),
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return hay.includes(needle);
    });
  }, [deployments, q, provider, stage]);

  const totals = useMemo(() => {
    let fns = 0;
    let http = 0;
    let wfs = 0;
    let res = 0;
    filtered.forEach((d) => {
      wfs += (d.workflows || []).length;
      res += (d.resources || []).length;
      (d.functions || []).forEach((f) => {
        fns += 1;
        if ((f.events || []).some((e) => e.type === "http")) http += 1;
      });
    });
    return { fns, http, wfs, res, providers: new Set(filtered.map((d) => d.provider)).size };
  }, [filtered]);

  const columns: Column<Deployment>[] = [
    {
      key: "service",
      header: "Deployment",
      sortValue: (d) => `${d.service} ${d.stage}`,
      render: (d) => (
        <div className="cell-name">
          <b>
            {d.service} · {d.stage}
          </b>
          <small className="mono">{deploymentKey(d)}</small>
        </div>
      ),
    },
    {
      key: "provider",
      header: "Provider",
      sortValue: (d) => d.provider_display || d.provider,
      render: (d) => (
        <span className="row-gap">
          <Badge>{d.provider_display || d.provider}</Badge>
          {d.provider_tier && d.provider_tier !== "stable" && <Badge tone="warn">{d.provider_tier}</Badge>}
        </span>
      ),
    },
    { key: "status", header: "Status", sortValue: (d) => d.status, render: (d) => <Badge tone={statusTone(d.status)}>{d.status || "unknown"}</Badge> },
    { key: "region", header: "Region", sortValue: (d) => d.region, render: (d) => <span className="mono">{d.region || "—"}</span> },
    { key: "fns", header: "Functions", sortValue: (d) => (d.functions || []).length, render: (d) => (d.functions || []).length },
    { key: "wfs", header: "Workflows", sortValue: (d) => (d.workflows || []).length, render: (d) => (d.workflows || []).length },
    {
      key: "endpoint",
      header: "Endpoint",
      render: (d) => (d.endpoint ? <span onClick={(e) => e.stopPropagation()}><ExtLink href={d.endpoint} /></span> : <span className="muted">—</span>),
    },
    {
      key: "updated",
      header: "Updated",
      sortValue: (d) => d.deployed_at,
      render: (d) => <span title={formatDate(d.deployed_at)}>{relative(d.deployed_at)}</span>,
    },
  ];

  return (
    <div className="stack">
      <div className="stats">
        <StatCard label="Deployments" value={filtered.length} />
        <StatCard label="Functions" value={totals.fns} hint={`${totals.http} HTTP`} />
        <StatCard label="Workflows" value={totals.wfs} />
        <StatCard label="Resources" value={totals.res} />
        <StatCard label="Providers" value={totals.providers} />
      </div>
      <div className="toolbar">
        <SearchInput value={q} onChange={setQ} placeholder="Filter by service, function, trigger, URL…" />
        <Select label="Provider" allLabel="All providers" value={provider} onChange={setProvider} options={providers} />
        <Select label="Stage" allLabel="All stages" value={stage} onChange={setStage} options={stages} />
      </div>
      <div className="card">
        <DataTable
          columns={columns}
          rows={filtered}
          rowKey={deploymentKey}
          onRowClick={(d) => onOpen(deploymentKey(d))}
          emptyTitle={deployments.length ? "No deployments match the filters" : "No deployments found"}
          emptyHint={
            deployments.length ? undefined : (
              <>
                Run <code>pskit deploy</code> and then <code>pskit dashboard</code>.
              </>
            )
          }
        />
      </div>
    </div>
  );
}
