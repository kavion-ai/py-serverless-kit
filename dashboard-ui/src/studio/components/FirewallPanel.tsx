import { useCallback, useEffect, useMemo, useState } from "react";
import { CopyButton } from "../../components/CopyButton";
import { api, errorMessage } from "../api";
import type { FirewallLevel, FirewallServer, FirewallSource, OnPremFirewall } from "../types";
import { EmptyState, ErrorBanner, Spinner } from "../../components/Feedback";

const LEVELS: Record<FirewallLevel, { label: string; className: string; title: string }> = {
  required: { label: "REQUIRED", className: "fw-level fw-required", title: "It does not work without this rule" },
  feature: { label: "NEEDED", className: "fw-level fw-feature", title: "Needed for this feature" },
  optional: { label: "optional", className: "fw-level fw-optional", title: "Optional: pskit falls back to an SSH tunnel" },
};

function sourceLabel(s: FirewallSource): string {
  if (s.name === "admin") return s.address ? `this machine (${s.address})` : "this machine";
  if (s.name === "users" || s.name === "internet") return s.name;
  return s.address && s.address !== s.name ? `${s.name} (${s.address})` : s.name || s.address;
}

function matches(server: FirewallServer, filter: Set<string>): boolean {
  return filter.has(server.server) || (!!server.address && filter.has(server.address));
}

/**
 * Which on-prem server must allow which inbound / outbound port (`GET /api/onprem-firewall`), with the `ufw` commands.
 * `servers` keeps only those servers (by name or address); leave it out for every server.
 */
export function FirewallPanel({ servers, title = "Firewall", refreshKey }: { servers?: string[]; title?: string; refreshKey?: unknown }) {
  const [data, setData] = useState<OnPremFirewall | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    api
      .firewall()
      .then((r) => {
        setData(r);
        setError(null);
      })
      .catch((exc: unknown) => setError(errorMessage(exc)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  const filterKey = servers ? servers.filter(Boolean).join("\n") : null;
  const shown = useMemo(() => {
    const all = data?.servers || [];
    if (filterKey === null) return all;
    const filter = new Set(filterKey.split("\n").filter(Boolean));
    return all.filter((s) => matches(s, filter));
  }, [data, filterKey]);

  return (
    <div className="card fw-panel">
      <div className="card-head">
        <h3>{title}</h3>
        <button type="button" className="btn btn-sm" disabled={loading} onClick={load}>
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>
      <div className="card-body">
        <p className="muted small">
          The ports each server must allow, between the servers pskit set up. <span className="fw-level fw-required">REQUIRED</span> it does not
          work without; <span className="fw-level fw-feature">NEEDED</span> for that feature; <span className="fw-level fw-optional">optional</span>{" "}
          pskit falls back to an SSH tunnel. More in <code className="mono">docs/onprem-network.md</code>.
        </p>
        {error && <ErrorBanner message={error} onRetry={load} />}
        {!data && loading && <Spinner label="Reading the firewall rules…" />}
        {data && !shown.length && (
          <EmptyState title="Nothing on premises yet" icon="◌">
            Deploy to a server, create a cluster or a load balancer, and the ports they need show up here.
          </EmptyState>
        )}
        {shown.map((s) => (
          <FirewallServerCard key={`${s.server}|${s.address}`} server={s} />
        ))}
      </div>
    </div>
  );
}

function FirewallServerCard({ server }: { server: FirewallServer }) {
  const ufw = server.ufw.join("\n");
  return (
    <section className="fw-server">
      <h4 className="fw-server-head">
        <span className="mono">{server.server}</span>
        {server.address && server.address !== server.server && <span className="muted"> ({server.address})</span>}
      </h4>
      {!server.rules.length ? (
        <p className="muted small">No ports to open on this server.</p>
      ) : (
        <div className="table-wrap">
          <table className="table fw-table">
            <thead>
              <tr>
                <th>Level</th>
                <th>Direction</th>
                <th>Port</th>
                <th>From / to</th>
                <th>Why</th>
              </tr>
            </thead>
            <tbody>
              {server.rules.map((r, i) => {
                const level = LEVELS[r.level] || LEVELS.optional;
                return (
                  <tr key={i} className={`fw-row fw-row-${r.level}`}>
                    <td>
                      <span className={level.className} title={level.title}>
                        {level.label}
                      </span>
                    </td>
                    <td className="fw-dir">{r.direction === "inbound" ? "↓ inbound" : "↑ outbound"}</td>
                    <td className="mono fw-port">
                      {r.proto} {r.port}
                    </td>
                    <td>
                      <span className="fw-sources">
                        {r.sources.map((src, j) => (
                          <span key={j} className="badge badge-off">
                            {sourceLabel(src)}
                          </span>
                        ))}
                      </span>
                    </td>
                    <td className="small">{r.why}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {server.ufw.length > 0 && (
        <div className="fw-ufw">
          <div className="fw-ufw-head">
            <span className="muted small">
              With <code className="mono">ufw</code> on {server.server}:
            </span>
            <CopyButton value={ufw} label="copy" />
          </div>
          <pre className="fw-ufw-code mono">{ufw}</pre>
        </div>
      )}
    </section>
  );
}
