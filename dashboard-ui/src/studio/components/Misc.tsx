import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Modal } from "../../components/Drawer";
import { EmptyState, ErrorBanner, Spinner } from "../../components/Feedback";
import { SearchInput } from "../../components/Inputs";
import { api, errorMessage } from "../api";
import type { DiscoverItem, DiscoverResult, Issue } from "../types";
import { diffLines } from "../util";

// --------------------------------------------------------------------- diff

export function DiffView({ before, after, context = 3 }: { before: string; after: string; context?: number }) {
  const lines = useMemo(() => diffLines(before, after), [before, after]);
  const changed = lines.some((l) => l.kind !== "same");
  if (!changed) return <div className="muted pad">No changes.</div>;
  // Collapse long unchanged runs to `context` lines around each change.
  const keep = lines.map((l, i) => {
    if (l.kind !== "same") return true;
    for (let d = -context; d <= context; d++) {
      const o = lines[i + d];
      if (o && o.kind !== "same") return true;
    }
    return false;
  });
  const out: ReactNode[] = [];
  let skipped = 0;
  lines.forEach((l, i) => {
    if (!keep[i]) {
      skipped++;
      return;
    }
    if (skipped) {
      out.push(
        <div key={`s${i}`} className="diff-line diff-skip">
          ⋯ {skipped} unchanged line{skipped === 1 ? "" : "s"}
        </div>,
      );
      skipped = 0;
    }
    out.push(
      <div key={i} className={`diff-line diff-${l.kind}`}>
        <span className="diff-mark" aria-hidden="true">
          {l.kind === "add" ? "+" : l.kind === "del" ? "−" : " "}
        </span>
        {l.text || " "}
      </div>,
    );
  });
  if (skipped) out.push(<div key="end" className="diff-line diff-skip">⋯ {skipped} unchanged</div>);
  return (
    <pre className="diff" aria-label="Changes">
      {out}
    </pre>
  );
}

// --------------------------------------------------------------------- discover

/** "Browse account": list existing queues / buckets / topics through GET /api/discover. */
export function DiscoverModal({
  open,
  provider,
  kind,
  region,
  onClose,
  onPick,
}: {
  open: boolean;
  provider: string;
  kind: "queue" | "storage" | "topic" | "workflow";
  region?: string;
  onClose: () => void;
  onPick: (item: DiscoverItem) => void;
}) {
  const [result, setResult] = useState<DiscoverResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [q, setQ] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!open) return undefined;
    let live = true;
    setLoading(true);
    setError(null);
    setResult(null);
    api
      .discover(provider, kind, region)
      .then((r) => live && setResult(r))
      .catch((exc: unknown) => live && setError(errorMessage(exc)))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [open, provider, kind, region, attempt]);

  const items = (result?.items || []).filter((i) =>
    [i.name, i.id, i.arn, i.region, i.detail].join(" ").toLowerCase().includes(q.trim().toLowerCase()),
  );
  const noun = kind === "storage" ? "buckets" : `${kind}s`;
  return (
    <Modal open={open} title={`Existing ${noun} in ${provider}${region ? ` (${region})` : ""}`} onClose={onClose}>
      <div className="stack">
        {loading && <Spinner label={`Listing ${noun}…`} />}
        {error && <ErrorBanner message={error} onRetry={() => setAttempt((a) => a + 1)} />}
        {result && !result.supported && (
          <EmptyState title="Listing isn't available here" icon="ⓘ">
            {result.reason || "Type the name instead."}
          </EmptyState>
        )}
        {result?.error && <ErrorBanner message={result.error} onRetry={() => setAttempt((a) => a + 1)} />}
        {result?.supported && !result.error && (
          <>
            <SearchInput value={q} onChange={setQ} placeholder={`Filter ${noun}…`} />
            {!items.length ? (
              <EmptyState title={result.items.length ? "No match" : `No ${noun} found`}>
                {result.items.length ? "Try another filter." : "Create one, or type a name in the form."}
              </EmptyState>
            ) : (
              <ul className="pick-list" role="listbox" aria-label={`Existing ${noun}`}>
                {items.map((item) => (
                  <li key={item.arn || item.id || item.name}>
                    <button
                      type="button"
                      className="pick"
                      onClick={() => {
                        onPick(item);
                        onClose();
                      }}
                    >
                      <b>{item.name}</b>
                      <span className="muted mono small">{item.arn || item.id || ""}</span>
                      {(item.region || item.detail) && (
                        <span className="muted small">{[item.region, item.detail].filter(Boolean).join(" · ")}</span>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {result.items.length >= 200 && <div className="muted small">Showing the first 200.</div>}
          </>
        )}
      </div>
    </Modal>
  );
}

// --------------------------------------------------------------------- issues

export function IssueList({ issues, onSelect }: { issues: Issue[]; onSelect?: (issue: Issue) => void }) {
  if (!issues.length) return <div className="muted pad">No problems found.</div>;
  return (
    <ul className="issues">
      {issues.map((issue, i) => (
        <li key={i}>
          <button
            type="button"
            className={`issue issue-${issue.level}`}
            onClick={onSelect ? () => onSelect(issue) : undefined}
            disabled={!onSelect || !issue.where}
          >
            <span className="issue-icon" aria-hidden="true">
              {issue.level === "error" ? "⛔" : "⚠"}
            </span>
            <span className="issue-text">
              {issue.message}
              {issue.where && <span className="muted mono small"> {issue.where}</span>}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="page-head">
      <div>
        <h1>{title}</h1>
        {subtitle && <p className="muted">{subtitle}</p>}
      </div>
      {actions && <div className="row-gap">{actions}</div>}
    </header>
  );
}

export function InlineIssues({ issues }: { issues: Issue[] }) {
  if (!issues.length) return null;
  return (
    <div className="inline-issues">
      {issues.map((i, n) => (
        <div key={n} className={i.level === "error" ? "form-error" : "form-warn"}>
          {i.message}
        </div>
      ))}
    </div>
  );
}
