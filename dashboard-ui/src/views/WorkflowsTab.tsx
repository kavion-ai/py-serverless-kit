import type { Deployment, WorkflowRecord } from "../types";
import { Badge, Chip } from "../components/Badge";
import { Card } from "../components/Card";
import { CopyButton } from "../components/CopyButton";
import { EmptyState } from "../components/Feedback";
import { ExtLink } from "../components/Link";

function orderedStates(w: WorkflowRecord): [string, string][] {
  const states = Object.entries(w.states || {});
  if (!w.start_at) return states;
  return states.sort(([a], [b]) => (a === w.start_at ? -1 : b === w.start_at ? 1 : 0));
}

export function WorkflowsTab({
  deployment,
  live,
  onStart,
  onShowExecutions,
}: {
  deployment: Deployment;
  live: boolean;
  onStart: (workflow: string) => void;
  onShowExecutions: (workflow: string) => void;
}) {
  const wfs = deployment.workflows || [];
  if (!wfs.length)
    return (
      <EmptyState title="No workflows">
        Define <code>workflows:</code> in pskit.yml to orchestrate functions as a state machine.
      </EmptyState>
    );
  return (
    <div className="grid-cards">
      {wfs.map((w) => (
        <Card
          key={w.name}
          title={
            <span className="row-gap">
              {w.name}
              <Badge tone={w.engine === "native" ? "ok" : "warn"}>{w.engine}</Badge>
            </span>
          }
          actions={
            <>
              <button type="button" className="btn btn-sm" onClick={() => onShowExecutions(w.name)} disabled={!live}>
                Executions
              </button>
              <button
                type="button"
                className="btn btn-sm btn-primary"
                onClick={() => onStart(w.name)}
                disabled={!live}
                title={live ? "Start an execution" : "Run `pskit dashboard --serve` to start executions"}
              >
                ▶ Start
              </button>
            </>
          }
        >
          {w.description && <p className="muted">{w.description}</p>}
          <div className="flow" aria-label="States">
            {orderedStates(w).map(([name, type], i) => (
              <span key={name} className="flow-step">
                {i > 0 && <span className="flow-arrow" aria-hidden="true">→</span>}
                <span className={`flow-node flow-${type}`}>
                  <b>{name}</b>
                  <small>{type}</small>
                </span>
              </span>
            ))}
          </div>
          {(w.functions || []).length > 0 && (
            <div className="chips">
              {(w.functions || []).map((f) => (
                <Chip key={f}>{f}</Chip>
              ))}
            </div>
          )}
          <div className="meta">
            {w.id ? (
              <span>
                <span className="mono">{w.id}</span> <CopyButton value={w.id} />
              </span>
            ) : (
              <span className="muted">not deployed</span>
            )}
            {w.url && <ExtLink href={w.url} />}
            {w.console && <ExtLink href={w.console}>Open in console ↗</ExtLink>}
          </div>
        </Card>
      ))}
    </div>
  );
}
