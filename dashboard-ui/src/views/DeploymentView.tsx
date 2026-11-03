import { useState } from "react";
import { api } from "../api";
import type { Deployment, HealthResponse } from "../types";
import { formatDate, formatDuration, statusTone } from "../format";
import { usePolling } from "../hooks";
import { Badge } from "../components/Badge";
import { StatCard } from "../components/Card";
import { ExtLink } from "../components/Link";
import { Tabs } from "../components/Tabs";
import { ExecutionsTab } from "./ExecutionsTab";
import { FunctionsTab } from "./FunctionsTab";
import { LogsTab, OutputsTab, ResourcesTab } from "./MiscTabs";
import { StartDialog } from "./StartDialog";
import { WorkflowsTab } from "./WorkflowsTab";

export const TAB_IDS = ["functions", "workflows", "executions", "logs", "resources", "outputs"] as const;
export type TabId = (typeof TAB_IDS)[number];

export function DeploymentView({
  deployment,
  deploymentKey,
  live,
  tab,
  onTab,
  onBack,
}: {
  deployment: Deployment;
  deploymentKey: string;
  live: boolean;
  tab: TabId;
  onTab: (tab: TabId) => void;
  onBack: () => void;
}) {
  const [workflowFilter, setWorkflowFilter] = useState("");
  const [openExecution, setOpenExecution] = useState<{ id: string; workflow?: string } | null>(null);
  const [startFor, setStartFor] = useState<string | null>(null);
  const health = usePolling<HealthResponse>(() => api.health(deploymentKey), 10000, live, [deploymentKey]);
  const h = health.data;
  const stats = h && h.live && h.stats ? h.stats : undefined;
  const workflows = (deployment.workflows || []).map((w) => w.name);
  const art = deployment.artifact || {};

  const tabs = [
    { id: "functions", label: "Functions", count: (deployment.functions || []).length },
    { id: "workflows", label: "Workflows", count: workflows.length },
    { id: "executions", label: "Executions" },
    { id: "logs", label: "Logs" },
    { id: "resources", label: "Resources", count: (deployment.resources || []).length },
    { id: "outputs", label: "Outputs" },
  ];

  let liveBadge = null;
  if (live && h) {
    liveBadge = h.live ? (
      <Badge tone="ok" title="The host answered its health check">● live</Badge>
    ) : (
      <Badge tone="off" title={h.reason}>offline</Badge>
    );
  }

  return (
    <div className="stack">
      <div>
        <button type="button" className="btn btn-ghost btn-sm" onClick={onBack}>
          ← All deployments
        </button>
      </div>
      <header className="dep-head">
        <div className="dep-title">
          <h2>
            {deployment.service} <span className="muted">· {deployment.stage}</span>
          </h2>
          <div className="row-gap">
            <Badge>{deployment.provider_display || deployment.provider}</Badge>
            {deployment.provider_tier && deployment.provider_tier !== "stable" && <Badge tone="warn">{deployment.provider_tier}</Badge>}
            <Badge tone={statusTone(deployment.status)}>{deployment.status || "unknown"}</Badge>
            {liveBadge}
          </div>
        </div>
        <div className="meta">
          <span>
            region <code>{deployment.region || "—"}</code>
          </span>
          <span>
            updated <code>{formatDate(deployment.deployed_at)}</code>
          </span>
          {art.sha256 && (
            <span>
              artifact <code>{String(art.sha256).slice(0, 12)}</code>
            </span>
          )}
          {deployment.endpoint && (
            <span>
              endpoint <ExtLink href={deployment.endpoint} />
            </span>
          )}
          <span>
            pskit <code>{deployment.pskit_version || "?"}</code>
          </span>
        </div>
      </header>
      {stats && (
        <div className="stats">
          <StatCard label="Uptime" value={formatDuration((stats.uptime_s || 0) * 1000)} hint={stats.started_at ? `since ${formatDate(stats.started_at)}` : undefined} />
          <StatCard
            label="Invocations"
            value={Object.values(stats.functions || {}).reduce((n, s) => n + (s.invocations || 0), 0)}
          />
          <StatCard label="Errors" value={Object.values(stats.functions || {}).reduce((n, s) => n + (s.errors || 0), 0)} />
          <StatCard
            label="Queued messages"
            value={Object.values(stats.queues || {}).reduce((n, v) => n + (Number(v) || 0), 0)}
            hint={`${Object.keys(stats.queues || {}).length} queues`}
          />
        </div>
      )}
      <Tabs tabs={tabs} active={tab} onChange={(id) => onTab(id as TabId)} />
      <div role="tabpanel">
        {tab === "functions" && <FunctionsTab deployment={deployment} stats={stats ? stats.functions : undefined} />}
        {tab === "workflows" && (
          <WorkflowsTab
            deployment={deployment}
            live={live}
            onStart={(w) => setStartFor(w)}
            onShowExecutions={(w) => {
              setWorkflowFilter(w);
              onTab("executions");
            }}
          />
        )}
        {tab === "executions" && (
          <ExecutionsTab
            deployment={deployment}
            deploymentKey={deploymentKey}
            live={live}
            workflowFilter={workflowFilter}
            setWorkflowFilter={setWorkflowFilter}
            openExecution={openExecution}
            setOpenExecution={setOpenExecution}
            onStart={() => setStartFor(workflowFilter || workflows[0] || "")}
          />
        )}
        {tab === "logs" && <LogsTab deployment={deployment} deploymentKey={deploymentKey} live={live} />}
        {tab === "resources" && <ResourcesTab deployment={deployment} />}
        {tab === "outputs" && <OutputsTab deployment={deployment} />}
      </div>
      <StartDialog
        deploymentKey={deploymentKey}
        workflows={workflows}
        initialWorkflow={startFor || undefined}
        open={startFor !== null}
        onClose={() => setStartFor(null)}
        onStarted={(e) => {
          setOpenExecution({ id: e.execution_id, workflow: e.workflow });
          onTab("executions");
        }}
      />
    </div>
  );
}
