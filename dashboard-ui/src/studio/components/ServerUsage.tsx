import { Drawer } from "../../components/Drawer";
import { href, VIEWS, type View } from "../route";
import type { ServerUse, ServerUseKind } from "../types";

/** Where a saved server is used: deploy target, function groups, clusters, load balancers, services, software. */

const KIND_LABEL: Record<ServerUseKind, string> = {
  deploy: "Deploy target",
  deployed: "Deployed",
  placement: "Function group",
  cluster: "Cluster",
  "cluster-balancer": "Cluster load balancer",
  balancer: "Load balancer",
  service: "Service / database",
  runtime: "Installed software",
};

const KIND_BADGE: Record<ServerUseKind, string> = {
  deploy: "badge-accent",
  deployed: "badge-ok",
  placement: "badge-accent",
  cluster: "badge-info",
  "cluster-balancer": "badge-info",
  balancer: "badge-info",
  service: "badge-warn",
  runtime: "badge-off",
};

function viewHref(view: string, name: string, kind: ServerUseKind): string {
  const v: View = (VIEWS as string[]).includes(view) ? (view as View) : "overview";
  // Resources and functions open the item itself; the other pages show every item at once.
  if (v === "resources" && kind === "service") return href(v, name);
  return href(v);
}

/** One line per kind of use: "3 places" or "not used anywhere". */
export function UsageSummary({ uses, onOpen }: { uses: ServerUse[] | undefined; onOpen: () => void }) {
  if (uses === undefined) return <span className="muted small">…</span>;
  if (!uses.length)
    return (
      <button type="button" className="btn btn-sm btn-ghost muted" onClick={onOpen} title="Nothing in this project names this server">
        not used anywhere
      </button>
    );
  const kinds = Array.from(new Set(uses.map((u) => u.kind)));
  return (
    <button type="button" className="btn btn-sm" onClick={onOpen} title={uses.map((u) => `${KIND_LABEL[u.kind]} ${u.name}: ${u.role}`).join("\n")}>
      Used in {uses.length} place{uses.length === 1 ? "" : "s"}
      <span className="muted small"> · {kinds.map((k) => KIND_LABEL[k].toLowerCase()).join(", ")}</span>
    </button>
  );
}

/** The table of uses, shared by the drawer, the Forget confirmation and the network map. */
export function UsageList({ uses, compact }: { uses: ServerUse[]; compact?: boolean }) {
  if (!uses.length) return <p className="muted">Not used anywhere in this project: no deploy target, function group, cluster, load balancer or service names it.</p>;
  return (
    <table className="table usage-table">
      <thead>
        <tr>
          <th>Where</th>
          <th>As</th>
          {!compact && <th>Functions</th>}
        </tr>
      </thead>
      <tbody>
        {uses.map((u, i) => (
          <tr key={`${u.kind}-${u.name}-${u.role}-${i}`}>
            <td>
              <span className={`badge ${KIND_BADGE[u.kind]}`}>{KIND_LABEL[u.kind]}</span>{" "}
              <a href={viewHref(u.view, u.name, u.kind)} className="mono">
                <b>{u.name}</b>
              </a>
              {u.detail && <div className="muted small">{u.detail}</div>}
            </td>
            <td className="small">{u.role}</td>
            {!compact && (
              <td>
                {u.functions.length ? (
                  <span className="chips">
                    {u.functions.map((f) => (
                      <a key={f} className="chip" href={href("functions", f)}>
                        {f}
                      </a>
                    ))}
                  </span>
                ) : (
                  <span className="muted small">none</span>
                )}
              </td>
            )}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Functions that end up on (or depend on) the server, from every use. */
export function usageFunctions(uses: ServerUse[]): string[] {
  return Array.from(new Set(uses.flatMap((u) => u.functions))).sort();
}

export function ServerUsageDrawer({ name, uses, onClose }: { name: string; uses: ServerUse[]; onClose: () => void }) {
  const fns = usageFunctions(uses);
  return (
    <Drawer open title={`Where ${name} is used`} onClose={onClose}>
      <p className="muted small">
        From pskit.yml and what pskit created (.pskit): deploy target, function groups, clusters, load balancers, services and software. Its connections are on the{" "}
        <a href={href("network", name)}>Network map</a>.
      </p>
      {fns.length > 0 && (
        <p>
          <b>Functions relying on it:</b>{" "}
          <span className="chips">
            {fns.map((f) => (
              <a key={f} className="chip" href={href("functions", f)}>
                {f}
              </a>
            ))}
          </span>
        </p>
      )}
      <UsageList uses={uses} />
    </Drawer>
  );
}
