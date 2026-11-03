import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { Deployment, ExecutionDetail, ExecutionList, ExecutionSummary } from "../types";
import { formatDate, formatDuration, relative, statusTone } from "../format";
import { usePolling } from "../hooks";
import { Badge } from "../components/Badge";
import { CopyButton } from "../components/CopyButton";
import { DataTable, type Column } from "../components/DataTable";
import { Drawer } from "../components/Drawer";
import { EmptyState, ErrorBanner, Spinner } from "../components/Feedback";
import { Select } from "../components/Inputs";
import { JsonView } from "../components/JsonView";
import { ExtLink } from "../components/Link";
import { Pagination } from "../components/Pagination";
import { Timeline } from "../components/Timeline";

const STATUSES = ["RUNNING", "SUCCEEDED", "FAILED", "CANCELLED", "ABORTED", "TIMED_OUT"];

function ExecutionDrawer({
  deploymentKey,
  target,
  onClose,
  onChanged,
}: {
  deploymentKey: string;
  target: { id: string; workflow?: string } | null;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [running, setRunning] = useState(true);
  const [cancelError, setCancelError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const detail = usePolling<ExecutionDetail>(
    () => api.execution(deploymentKey, target ? target.id : "", target ? target.workflow : undefined),
    running ? 1500 : 0,
    !!target,
    [deploymentKey, target && target.id],
  );
  const d = detail.data;
  useEffect(() => {
    setRunning(true);
    setCancelError(null);
  }, [target && target.id]);
  useEffect(() => {
    if (d && d.status !== "RUNNING") {
      if (running) onChanged();
      setRunning(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [d && d.status]);

  const cancel = async () => {
    if (!target) return;
    setCancelling(true);
    setCancelError(null);
    try {
      await api.cancel(deploymentKey, target.id, target.workflow);
      setRunning(true);
      detail.refresh();
      onChanged();
    } catch (err) {
      setCancelError(err instanceof Error ? err.message : String(err));
    } finally {
      setCancelling(false);
    }
  };

  return (
    <Drawer
      open={!!target}
      onClose={onClose}
      title={
        <span className="row-gap">
          Execution
          {d && <Badge tone={statusTone(d.status)}>{d.status}</Badge>}
        </span>
      }
      actions={
        d && d.status === "RUNNING" ? (
          <button type="button" className="btn btn-danger btn-sm" onClick={cancel} disabled={cancelling}>
            {cancelling ? "Cancelling…" : "Cancel"}
          </button>
        ) : null
      }
    >
      {detail.error && !d && <ErrorBanner message={detail.error} onRetry={detail.refresh} />}
      {!d && !detail.error && <Spinner label="Loading execution…" />}
      {cancelError && <ErrorBanner message={cancelError} />}
      {d && (
        <div className="stack">
          <dl className="props">
            <dt>Execution id</dt>
            <dd>
              <span className="mono">{d.execution_id}</span> <CopyButton value={d.execution_id} />
            </dd>
            <dt>Workflow</dt>
            <dd>{d.workflow}</dd>
            <dt>Current state</dt>
            <dd className="mono">{d.current_state || "—"}</dd>
            <dt>Started</dt>
            <dd>{formatDate(d.started_at)}</dd>
            <dt>Stopped</dt>
            <dd>{formatDate(d.stopped_at)}</dd>
            <dt>Duration</dt>
            <dd>{formatDuration(d.duration_ms)}</dd>
            {d.source && (
              <>
                <dt>Engine</dt>
                <dd>{d.source}</dd>
              </>
            )}
            {d.console && (
              <>
                <dt>Console</dt>
                <dd>
                  <ExtLink href={d.console}>Open in console ↗</ExtLink>
                </dd>
              </>
            )}
          </dl>
          {(d.error || d.cause) && (
            <div className="error-banner" role="alert">
              <div>
                <b>{d.error || "Error"}</b>
                {d.cause && <div className="mono pre">{d.cause}</div>}
              </div>
            </div>
          )}
          <section>
            <h4>History</h4>
            <Timeline events={d.history || []} current={d.current_state} running={d.status === "RUNNING"} />
          </section>
          <section>
            <h4>Input</h4>
            <JsonView value={d.input} />
          </section>
          <section>
            <h4>Output</h4>
            <JsonView value={d.output} empty={d.status === "RUNNING" ? "Still running…" : "—"} />
          </section>
        </div>
      )}
    </Drawer>
  );
}

export function ExecutionsTab({
  deployment,
  deploymentKey,
  live,
  workflowFilter,
  setWorkflowFilter,
  openExecution,
  setOpenExecution,
  onStart,
}: {
  deployment: Deployment;
  deploymentKey: string;
  live: boolean;
  workflowFilter: string;
  setWorkflowFilter: (w: string) => void;
  openExecution: { id: string; workflow?: string } | null;
  setOpenExecution: (e: { id: string; workflow?: string } | null) => void;
  onStart: () => void;
}) {
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(20);
  // Token pagination: tokens[i] is the token that loads page i.
  const [tokens, setTokens] = useState<(string | null)[]>([null]);
  const workflows = useMemo(() => (deployment.workflows || []).map((w) => w.name), [deployment]);

  useEffect(() => {
    setPage(0);
    setTokens([null]);
  }, [workflowFilter, status, pageSize, deploymentKey]);

  const [anyRunning, setAnyRunning] = useState(false);
  const list = usePolling<ExecutionList>(
    () =>
      api.executions(deploymentKey, {
        workflow: workflowFilter || undefined,
        status: status || undefined,
        limit: pageSize,
        offset: page * pageSize,
        token: tokens[page] || undefined,
      }),
    anyRunning ? 3000 : 15000,
    live,
    [deploymentKey, workflowFilter, status, page, pageSize],
  );
  const data = list.data;
  useEffect(() => {
    setAnyRunning(!!data && data.items.some((e) => e.status === "RUNNING"));
    if (data && data.next_token) {
      setTokens((t) => {
        const copy = t.slice(0, page + 1);
        copy[page + 1] = data.next_token as string;
        return copy;
      });
    }
  }, [data, page]);

  if (!live)
    return (
      <EmptyState title="Live data needs the dashboard server" icon="⚡">
        Run <code>pskit dashboard --serve</code> to list, start and inspect workflow executions.
      </EmptyState>
    );
  if (!workflows.length) return <EmptyState title="No workflows in this deployment" />;

  const columns: Column<ExecutionSummary>[] = [
    {
      key: "id",
      header: "Execution",
      render: (e) => (
        <div className="cell-name">
          <b className="mono">{e.execution_id.length > 24 ? `${e.execution_id.slice(0, 24)}…` : e.execution_id}</b>
          <small>{e.workflow}</small>
        </div>
      ),
    },
    { key: "status", header: "Status", render: (e) => <Badge tone={statusTone(e.status)}>{e.status}</Badge> },
    { key: "state", header: "Current state", render: (e) => <span className="mono">{e.current_state || "—"}</span> },
    { key: "started", header: "Started", render: (e) => <span title={formatDate(e.started_at)}>{relative(e.started_at)}</span> },
    { key: "duration", header: "Duration", render: (e) => formatDuration(e.duration_ms) },
  ];

  return (
    <div className="stack">
      <div className="toolbar">
        <Select label="Workflow" allLabel="All workflows" value={workflowFilter} onChange={setWorkflowFilter} options={workflows} />
        <Select label="Status" allLabel="Any status" value={status} onChange={setStatus} options={STATUSES} />
        <button type="button" className="btn" onClick={list.refresh} disabled={list.loading}>
          ↻ Refresh
        </button>
        <span className="grow" />
        <button type="button" className="btn btn-primary" onClick={onStart}>
          ▶ Start execution
        </button>
      </div>
      {list.error && <ErrorBanner message={list.error} onRetry={list.refresh} />}
      {data && !data.supported ? (
        <EmptyState title="Execution history unavailable">{data.reason}</EmptyState>
      ) : !data ? (
        <Spinner label="Loading executions…" />
      ) : (
        <div className="card">
          <DataTable
            columns={columns}
            rows={data.items}
            rowKey={(e) => e.execution_id}
            onRowClick={(e) => setOpenExecution({ id: e.execution_id, workflow: e.workflow })}
            selectedKey={openExecution ? openExecution.id : null}
            paginate={false}
            emptyTitle="No executions yet"
            emptyHint="Start one with the button above."
          />
          {(data.items.length > 0 || page > 0) && (
            <Pagination
              page={page}
              pageSize={pageSize}
              total={typeof data.total === "number" ? data.total : null}
              hasNext={!!data.next_token || data.items.length === pageSize}
              onPage={setPage}
              onPageSize={setPageSize}
            />
          )}
        </div>
      )}
      <ExecutionDrawer
        deploymentKey={deploymentKey}
        target={openExecution}
        onClose={() => setOpenExecution(null)}
        onChanged={list.refresh}
      />
    </div>
  );
}
