import { useCallback, useEffect, useState } from "react";
import { Drawer } from "../../components/Drawer";
import { Pagination } from "../../components/Pagination";
import { api, errorMessage } from "../api";
import { useStudio } from "../store";
import type { ResourcePage } from "../types";
import { useConfirm, useToast } from "./Feedback";
import { TextInput } from "./Forms";

function when(ts?: number | null): string {
  return ts ? new Date(ts * 1000).toLocaleString() : "";
}

/**
 * What an on-prem resource holds, read by the deployed host: queue / topic messages (peeked,
 * never consumed) or bucket objects with a preview. Paginated.
 */
export function ResourceData({ resourceKey, onClose }: { resourceKey: string; onClose: () => void }) {
  const { state, providerName } = useStudio();
  const target = state.target || { provider: providerName, stage: "dev" };
  const toast = useToast();
  const confirm = useConfirm();
  const [page, setPage] = useState(0);
  const [size, setSize] = useState(20);
  const [prefix, setPrefix] = useState("");
  const [data, setData] = useState<ResourcePage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const [preview, setPreview] = useState<{ key: string; text: string; note: string } | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    api
      .resourceData(target.provider, target.stage, resourceKey, page * size, size, prefix)
      .then(setData, (exc: unknown) => setError(errorMessage(exc)))
      .finally(() => setLoading(false));
  }, [target.provider, target.stage, resourceKey, page, size, prefix]);
  useEffect(load, [load]);

  const showObject = async (key: string) => {
    try {
      const obj = await api.resourceObject(target.provider, target.stage, resourceKey, key);
      const note = `${obj.size} bytes${obj.truncated ? ", first 256 KiB shown" : ""}${obj.encoding === "base64" ? ", binary (base64)" : ""}`;
      setPreview({ key, text: obj.content || "", note });
    } catch (exc) {
      toast(errorMessage(exc), "err");
    }
  };

  const remove = async (what: "object" | "message", id: string) => {
    const ok = await confirm({ title: `Delete this ${what}?`, body: id, confirmLabel: "Delete", danger: true });
    if (ok !== "confirm") return;
    try {
      if (what === "object") await api.resourceObject(target.provider, target.stage, resourceKey, id, true);
      else await api.resourceMessageDelete(target.provider, target.stage, resourceKey, id);
      toast(`Deleted ${id}`, "ok");
      load();
    } catch (exc) {
      toast(errorMessage(exc), "err");
    }
  };

  const storage = data?.type === "storage";
  return (
    <Drawer
      open
      title={`Data in ${resourceKey}`}
      onClose={onClose}
      actions={
        <button type="button" className="btn" onClick={load} disabled={loading}>
          {loading ? "Loading…" : "Refresh"}
        </button>
      }
    >
      <p className="muted small">
        Read by the deployed on-prem host ({target.provider} / {target.stage}). Messages are looked at, not consumed. Terminal:{" "}
        <code className="mono">pskit resources data {resourceKey}</code>
      </p>
      {storage && (
        <div className="row-gap">
          <TextInput mono value={prefix} placeholder="prefix, e.g. in/" onChange={(v) => { setPrefix(v); setPage(0); }} />
        </div>
      )}
      {error && <div className="form-error">{error}</div>}
      {data && !data.supported && (
        <div className="hint-box">
          {data.note}
          {data.total !== null && data.total !== undefined ? ` Waiting now: ${data.total}.` : ""}
        </div>
      )}
      {data && data.supported && (
        <>
          {!data.items.length && <p className="muted">{page ? "No more items." : "Empty."}</p>}
          {data.items.length > 0 && storage && (
            <table className="table">
              <thead>
                <tr>
                  <th>Key</th>
                  <th>Size</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.items.map((it) => (
                  <tr key={it.key}>
                    <td className="mono small">{it.key}</td>
                    <td className="small">{it.size}</td>
                    <td>
                      <span className="row-gap">
                        <button type="button" className="btn btn-sm" onClick={() => void showObject(it.key || "")}>
                          Preview
                        </button>
                        <button type="button" className="btn btn-sm btn-danger" onClick={() => void remove("object", it.key || "")}>
                          Delete
                        </button>
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {data.items.length > 0 && !storage && (
            <table className="table">
              <thead>
                <tr>
                  <th>Message</th>
                  <th>Body</th>
                  <th>Info</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.items.map((it, i) => (
                  <tr key={it.id || i}>
                    <td className="mono small">{(it.id || "").slice(0, 16)}</td>
                    <td>
                      <button type="button" className="link-btn mono small" onClick={() => setOpen(open === it.id ? null : it.id || null)}>
                        {open === it.id ? "hide" : (it.body || "").slice(0, 80) || "(empty)"}
                      </button>
                      {open === it.id && (
                        <pre className="md-code">
                          {it.body}
                          {it.truncated ? "\n…" : ""}
                          {it.attributes && Object.keys(it.attributes).length ? `\n\nattributes: ${JSON.stringify(it.attributes)}` : ""}
                        </pre>
                      )}
                    </td>
                    <td className="small muted">
                      {when(it.enqueued_at)}
                      {it.receives ? ` · ${it.receives} failed` : ""}
                      {it.leased ? " · being processed" : ""}
                      {it.delivered_to && it.delivered_to.length ? ` · delivered to ${it.delivered_to.join(", ")}` : ""}
                    </td>
                    <td>
                      {data.type === "queue" && it.id && (
                        <button type="button" className="btn btn-sm btn-danger" onClick={() => void remove("message", it.id || "")} title="Built-in queues only">
                          Delete
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <Pagination
            page={page}
            pageSize={size}
            total={data.total}
            hasNext={data.items.length === size}
            onPage={setPage}
            onPageSize={(s) => {
              setSize(s);
              setPage(0);
            }}
          />
        </>
      )}
      {preview && (
        <div className="card card-pad">
          <div className="row-between">
            <b className="mono">{preview.key}</b>
            <button type="button" className="btn btn-sm" onClick={() => setPreview(null)}>
              Close
            </button>
          </div>
          <p className="muted small">{preview.note}</p>
          <pre className="md-code console-log">{preview.text}</pre>
        </div>
      )}
    </Drawer>
  );
}
