import { useCallback, useEffect, useState } from "react";
import { api, errorMessage } from "../api";
import { useJob } from "../jobs";
import { useStudio } from "../store";
import type { CloudResourceRow } from "../types";
import { JobConsole } from "./Console";
import { useConfirm, useToast } from "./Feedback";
import { Section } from "./Forms";

/** Buckets, queues and topics pskit created for the target provider/stage (deployed or kept), with delete. */
export function CloudResources() {
  const { state } = useStudio();
  const confirm = useConfirm();
  const toast = useToast();
  const target = state.target || { provider: "aws", stage: "dev" };
  const [data, setData] = useState<{ deployed: CloudResourceRow[]; kept: CloudResourceRow[]; reason?: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [jobId, setJobId] = useState<string | null>(null);
  const job = useJob(jobId);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    api
      .cloudResources(target.provider, target.stage)
      .then((r) => {
        setData(r);
        setPicked(new Set());
      })
      .catch((exc: unknown) => setError(errorMessage(exc)))
      .finally(() => setLoading(false));
  }, [target.provider, target.stage]);
  useEffect(() => {
    if (job.status === "succeeded" || job.status === "failed") load();
  }, [job.status, load]);
  useEffect(() => setData(null), [target.provider, target.stage]);

  const rows = data ? [...data.deployed, ...data.kept] : [];
  const remove = async (addresses: string[]) => {
    if (!addresses.length) return;
    const chosen = rows.filter((r) => addresses.includes(r.address));
    const deployed = chosen.filter((r) => r.status === "deployed");
    const ok = await confirm({
      title: `Delete ${addresses.length} resource${addresses.length > 1 ? "s" : ""} from ${target.provider}?`,
      body: (
        <div className="stack">
          <ul className="bullets">
            {chosen.map((r) => (
              <li key={r.address}>
                {r.kind} <b>{r.name}</b> <span className="muted mono small">{r.address}</span>
              </li>
            ))}
          </ul>
          <p>
            <b>The resources and everything in them (objects, messages) are deleted permanently.</b>
          </p>
          {deployed.length > 0 && (
            <p className="small warn-text">
              Deployed ones that are still in pskit.yml are created again by the next deploy: remove them from Resources or the
              trigger first.
            </p>
          )}
        </div>
      ),
      typed: "delete",
      confirmLabel: "Delete permanently",
      danger: true,
    });
    if (ok !== "confirm") return;
    try {
      const r = await api.startJob("resources-delete", target.provider, target.stage, { addresses });
      setJobId(r.job_id);
    } catch (exc) {
      toast(errorMessage(exc), "err");
    }
  };

  const toggle = (address: string) =>
    setPicked((s) => {
      const next = new Set(s);
      if (next.has(address)) next.delete(address);
      else next.add(address);
      return next;
    });

  return (
    <Section
      title={`In the cloud (${target.provider} / ${target.stage})`}
      hint="buckets, queues and topics pskit created"
      defaultOpen={false}
      actions={
        <button type="button" className="btn btn-sm" onClick={load} disabled={loading}>
          {loading ? "Reading state…" : data ? "Refresh" : "Load"}
        </button>
      }
    >
      <p className="muted small">
        Read from the Terraform state of this stage. <b>Kept</b> ones were left by Remove with the switch to keep buckets, queues
        and topics; pskit no longer manages them, so delete them here when you no longer need them.
      </p>
      {error && <div className="form-error block">{error}</div>}
      {!data && !loading && !error && <p className="muted">Press Load (it runs terraform init and reads the state).</p>}
      {data && !rows.length && <p className="muted">{data.reason || "No buckets, queues or topics created by pskit for this stage."}</p>}
      {rows.length > 0 && (
        <>
          <ul className="compat-list">
            {rows.map((r) => (
              <li key={r.address}>
                <input type="checkbox" checked={picked.has(r.address)} onChange={() => toggle(r.address)} aria-label={`Select ${r.address}`} />
                <span className={`badge badge-${r.status === "kept" ? "warn" : "ok"}`}>{r.status}</span>
                <span className="badge badge-accent">{r.kind}</span>
                <b>{r.name}</b>
                <span className="muted mono small grow">{r.address}</span>
                <button type="button" className="btn btn-sm btn-danger" disabled={job.status === "running"} onClick={() => void remove([r.address])}>
                  Delete
                </button>
              </li>
            ))}
          </ul>
          <div className="row-gap wrap">
            <button type="button" className="btn btn-sm" onClick={() => setPicked(picked.size === rows.length ? new Set() : new Set(rows.map((r) => r.address)))}>
              {picked.size === rows.length ? "Select none" : "Select all"}
            </button>
            <button type="button" className="btn btn-sm btn-danger" disabled={!picked.size || job.status === "running"} onClick={() => void remove(Array.from(picked))}>
              Delete selected ({picked.size})
            </button>
            {data && data.kept.length > 0 && (
              <button type="button" className="btn btn-sm btn-danger" disabled={job.status === "running"} onClick={() => void remove(data.kept.map((r) => r.address))}>
                Delete all kept ({data.kept.length})
              </button>
            )}
          </div>
        </>
      )}
      {jobId && <JobConsole job={job} />}
    </Section>
  );
}
