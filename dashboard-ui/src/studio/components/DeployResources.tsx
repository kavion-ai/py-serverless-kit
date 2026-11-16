import { useEffect, useState } from "react";
import { api, errorMessage } from "../api";
import { Section } from "./Forms";
import type { DeployResource, DeployResources } from "../types";

/** Resource types grouped by category, in the order the server sent them. */
export function groupResources(rows: DeployResource[]): { label: string; rows: DeployResource[] }[] {
  const groups: { label: string; rows: DeployResource[] }[] = [];
  for (const row of rows) {
    const last = groups[groups.length - 1];
    if (last && last.label === row.category_label) last.rows.push(row);
    else groups.push({ label: row.category_label, rows: [row] });
  }
  return groups;
}

/** The functions the last deploy could not deploy, sorted by name. */
export function notDeployedOf(data: DeployResources | null): { name: string; step: string; reason: string; previous?: string }[] {
  const nd = data?.last_deploy?.not_deployed || {};
  return Object.keys(nd)
    .sort()
    .map((name) => ({ name, ...nd[name] }));
}

/** Last deploy: the functions that were not deployed and why (a partial deploy deploys the others). */
export function NotDeployedBox({ data }: { data: DeployResources | null }) {
  const items = notDeployedOf(data);
  if (!items.length) return null;
  return (
    <div className="hint-box warn stack not-deployed">
      <b>
        Last deploy{data?.last_deploy?.deployed_at ? ` (${data.last_deploy.deployed_at})` : ""}: {items.length} function{items.length === 1 ? " was" : "s were"} not deployed. The
        others were deployed.
      </b>
      <ul className="bullets small">
        {items.map((i) => (
          <li key={i.name}>
            <b className="mono">{i.name}</b> <span className="badge badge-err">{i.step}</span> {i.reason}
            {i.previous ? <span className="muted"> ({i.previous})</span> : null}
          </li>
        ))}
      </ul>
      <span className="small">Fix the reasons and deploy again. Deploy with <code className="mono">pskit deploy --all-or-nothing</code> to stop at the first one instead.</span>
    </div>
  );
}

/**
 * "What a deploy creates": every resource of the last Package / Plan / Deploy with what it is for, which ones are
 * optional (and the pskit.yml switch that removes them), and the functions with logs / metrics switched off.
 */
export function DeployResourcesPanel({
  provider,
  stage,
  refreshKey,
  busy,
  onPackage,
}: {
  provider: string;
  stage: string;
  refreshKey: unknown;
  busy: boolean;
  onPackage: () => void;
}) {
  const [data, setData] = useState<DeployResources | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let live = true;
    api.deployResources(provider, stage).then(
      (r) => live && (setData(r), setError("")),
      (exc: unknown) => live && setError(errorMessage(exc)),
    );
    return () => {
      live = false;
    };
  }, [provider, stage, refreshKey]);

  const rows = data?.resources || [];
  const total = rows.reduce((n, r) => n + r.count, 0);
  const optional = rows.filter((r) => r.optional);
  const quiet = Object.entries(data?.monitoring || {}).filter(([, m]) => !m.logs || !m.metrics);
  return (
    <Section
      title="What a deploy creates"
      hint={rows.length ? `${total} resource${total === 1 ? "" : "s"}${data?.package_type === "image" ? " · container image" : ""}` : undefined}
      defaultOpen
      actions={
        <button type="button" className="btn btn-sm" disabled={busy} onClick={onPackage} title="pskit package --skip-deps: rebuild the Terraform without installing dependencies">
          Refresh
        </button>
      }
    >
      {error && <div className="hint-box warn">{error}</div>}
      <NotDeployedBox data={data} />
      {!rows.length ? (
        <p className="muted">{data?.reason || "Run Package to see every resource a deploy creates, with what each one is for."}</p>
      ) : (
        <div className="stack">
          <p className="muted small">
            From the last Package / Plan / Deploy of <b>{provider}</b>/<b>{stage}</b>. Read it before you deploy:
            {optional.length ? " resources marked optional can be left out with the setting shown." : " everything listed is needed."} Refresh after changing pskit.yml.
          </p>
          <div className="resource-groups">
            {groupResources(rows).map((g) => (
              <div key={g.label}>
                <h4>{g.label}</h4>
                {g.rows.map((r) => (
                  <div key={r.type} className="resource-row">
                    <code className="mono small">
                      {r.type} ×{r.count}
                    </code>
                    <span className="small">
                      {r.description}
                      <span className="muted"> ({r.names.slice(0, 6).join(", ")}{r.names.length > 6 ? ", …" : ""})</span>
                      {r.optional && (
                        <>
                          {" "}
                          <span className="badge badge-info" title="Leave it out with this pskit.yml setting">
                            optional: {r.optional}
                          </span>
                        </>
                      )}
                    </span>
                  </div>
                ))}
              </div>
            ))}
          </div>
          {quiet.length > 0 && (
            <p className="small">
              Logs / metrics switched off:{" "}
              {quiet.map(([name, m], i) => (
                <span key={name}>
                  {i > 0 && ", "}
                  <b className="mono">{name}</b> ({[!m.logs && "logs", !m.metrics && "metrics"].filter(Boolean).join(", ")})
                </span>
              ))}
              . Change it per function on the Functions page (<i>Logs &amp; metrics</i>).
            </p>
          )}
        </div>
      )}
    </Section>
  );
}

/** Compact list for the Deploy confirmation: each resource type with what it is for. */
export function ResourceSummary({ data }: { data: DeployResources | null }) {
  const rows = data?.resources || [];
  if (!rows.length) return <p className="muted small">Run Package first to see every resource this deploy creates and what it is for.</p>;
  const total = rows.reduce((n, r) => n + r.count, 0);
  return (
    <div className="stack">
      <p className="small">
        Creates or updates <b>{total}</b> resource{total === 1 ? "" : "s"}
        {data?.package_type === "image" ? " (code shipped as a container image)" : ""} — from the last Package; it changes if pskit.yml changed since:
      </p>
      <ul className="bullets small">
        {rows.map((r) => (
          <li key={r.type}>
            <code className="mono">{r.type}</code> ×{r.count}: {r.description}
            {r.optional ? <span className="muted"> (optional: {r.optional})</span> : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
