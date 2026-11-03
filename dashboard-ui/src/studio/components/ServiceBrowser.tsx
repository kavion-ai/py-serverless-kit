import { useCallback, useEffect, useState } from "react";
import { Drawer } from "../../components/Drawer";
import { api, errorMessage } from "../api";
import { useConfirm, useToast } from "./Feedback";
import { EnumSelect, Segmented, TextInput, Toggle } from "./Forms";

/** pskit's own UI for an on-prem service: object storage (S3 / Cloud Storage) and secrets (OpenBao / AWS). */
export function ServiceBrowser({ serviceKey, kinds, onClose }: { serviceKey: string; kinds: string[]; onClose: () => void }) {
  const [kind, setKind] = useState(kinds[0]);
  const label: Record<string, string> = { s3: "Buckets (S3)", gcs: "Buckets (Cloud Storage)", vault: "Secrets", "aws-secrets": "Secrets (Secrets Manager)" };
  return (
    <Drawer open title={`Browse ${serviceKey}`} onClose={onClose}>
      <div className="stack">
        {kinds.length > 1 && (
          <Segmented label="What" value={kind} onChange={setKind} options={kinds.map((k) => ({ value: k, label: label[k] || k }))} />
        )}
        {(kind === "s3" || kind === "gcs") && <StorageBrowser key={kind} serviceKey={serviceKey} kind={kind} />}
        {(kind === "vault" || kind === "aws-secrets") && <SecretsBrowser key={kind} serviceKey={serviceKey} kind={kind} />}
      </div>
    </Drawer>
  );
}

type Body = Record<string, unknown>;

const SHARE_MAX = 7 * 24 * 3600; // the longest S3 presigned URL
const SHARE_UNITS = [
  { value: "1", label: "seconds" },
  { value: "60", label: "minutes" },
  { value: "3600", label: "hours" },
  { value: "86400", label: "days" },
];

function useBrowse(serviceKey: string, kind: string) {
  return useCallback(<T,>(action: string, body: Body = {}) => api.onpremBrowse<T>(serviceKey, kind, action, body), [serviceKey, kind]);
}

function size(n: number): string {
  if (n < 1024) return `${n} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let v = n / 1024;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(v < 10 ? 1 : 0)} ${units[i]}`;
}

function when(text?: string | null): string {
  if (!text) return "";
  const d = new Date(text);
  return Number.isNaN(d.getTime()) ? text : d.toLocaleString();
}

function readFile(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1] || "");
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

function saveBase64(name: string, contentType: string, b64: string) {
  const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  const url = URL.createObjectURL(new Blob([bytes], { type: contentType }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name.split("/").pop() || "download";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

// ----------------------------------------------------------------------------- object storage

interface Obj {
  key: string;
  size: number;
  modified?: string;
  etag?: string;
  storage_class?: string;
}
interface Listing {
  folders: string[];
  objects: Obj[];
  next: string | null;
}
interface Head {
  key: string;
  size: number;
  content_type?: string;
  etag?: string;
  modified?: string;
  version?: string | null;
  metadata: Record<string, string>;
}
interface Version {
  version: string;
  latest: boolean;
  modified?: string;
  size: number;
  deleted: boolean;
}

function StorageBrowser({ serviceKey, kind }: { serviceKey: string; kind: string }) {
  const call = useBrowse(serviceKey, kind);
  const toast = useToast();
  const confirm = useConfirm();
  const s3 = kind === "s3";
  const [buckets, setBuckets] = useState<{ name: string; created?: string }[] | null>(null);
  const [bucket, setBucket] = useState("");
  const [newBucket, setNewBucket] = useState("");
  const [prefix, setPrefix] = useState("");
  const [search, setSearch] = useState("");
  const [limit, setLimit] = useState("100");
  const [tokens, setTokens] = useState<(string | null)[]>([null]); // token of each page shown so far
  const [listing, setListing] = useState<Listing | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<{ head: Head; versions: Version[] } | null>(null);
  const [share, setShare] = useState<{ url: string; expires: number } | null>(null);
  const [shareFor, setShareFor] = useState<{ key: string; amount: string; unit: string } | null>(null);
  const [folderName, setFolderName] = useState("");
  const [target, setTarget] = useState<{ key: string; mode: "move" | "copy"; to: string } | null>(null);
  const [settings, setSettings] = useState(false);

  const run = async <T,>(fn: () => Promise<T>): Promise<T | undefined> => {
    setBusy(true);
    setError(null);
    try {
      return await fn();
    } catch (exc) {
      setError(errorMessage(exc));
      return undefined;
    } finally {
      setBusy(false);
    }
  };

  const loadBuckets = useCallback(() => {
    void run(async () => {
      const r = await call<{ buckets: { name: string; created?: string }[] }>("buckets");
      setBuckets(r.buckets);
      if (!bucket && r.buckets.length) setBucket(r.buckets[0].name);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [call]);
  useEffect(loadBuckets, [loadBuckets]);

  const page = tokens.length - 1;
  const list = useCallback(
    (token: string | null) =>
      run(async () => {
        const r = await call<Listing>("list", { bucket, prefix: prefix + search, limit: Number(limit), token: token || undefined });
        setListing(r);
        setSelected(new Set());
        return r;
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [call, bucket, prefix, search, limit],
  );
  useEffect(() => {
    setTokens([null]);
    if (bucket) void list(null);
  }, [bucket, prefix, search, limit, list]);

  const nextPage = () => {
    if (!listing?.next) return;
    setTokens((t) => [...t, listing.next]);
    void list(listing.next);
  };
  const prevPage = () => {
    if (page === 0) return;
    const t = tokens.slice(0, -1);
    setTokens(t);
    void list(t[t.length - 1]);
  };
  const refresh = () => void list(tokens[tokens.length - 1]);

  const upload = async (files: FileList | null) => {
    if (!files || !files.length) return;
    let done = 0;
    await run(async () => {
      for (const f of Array.from(files)) {
        if (f.size > 64 * 1024 * 1024) throw new Error(`${f.name}: files up to 64 MB go through the studio`);
        await call("put", { bucket, key: prefix + f.name, content: await readFile(f), content_type: f.type || "application/octet-stream" });
        done++;
      }
    });
    if (done) toast(`Uploaded ${done} file${done === 1 ? "" : "s"}`, "ok");
    refresh();
  };

  const remove = async (keys: string[]) => {
    if (!keys.length) return;
    const ok = await confirm({
      title: `Delete ${keys.length === 1 ? keys[0] : `${keys.length} items`}?`,
      body: keys.some((k) => k.endsWith("/")) ? <p>Folders are deleted with everything in them.</p> : undefined,
      confirmLabel: "Delete",
      danger: true,
    });
    if (ok !== "confirm") return;
    const r = await run(() => call<{ deleted: number }>("delete", { bucket, keys }));
    if (r) toast(`Deleted ${r.deleted} object${r.deleted === 1 ? "" : "s"}`, "ok");
    refresh();
  };

  const download = async (key: string, version?: string) => {
    const r = await run(() => call<{ content: string; content_type: string }>("get", { bucket, key, version }));
    if (r) saveBase64(key, r.content_type, r.content);
  };

  const openInfo = async (key: string) => {
    const head = await run(() => call<Head>("head", { bucket, key }));
    if (!head) return;
    let versions: Version[] = [];
    if (s3) versions = (await call<{ versions: Version[] }>("versions", { bucket, key }).catch(() => ({ versions: [] }))).versions;
    setInfo({ head, versions });
  };

  const makeShare = async (key: string, expires: number) => {
    if (!Number.isFinite(expires) || expires < 1 || expires > SHARE_MAX) {
      setError("A share link is valid for 1 second to 7 days.");
      return;
    }
    const r = await run(() => call<{ url: string; expires: number }>("share", { bucket, key, expires }));
    if (r) {
      setShare({ url: r.url, expires: Date.now() + r.expires * 1000 });
      setShareFor(null);
      navigator.clipboard?.writeText(r.url).then(() => toast("Share link copied", "ok"), () => undefined);
    }
  };

  const createBucket = async () => {
    const name = newBucket.trim();
    if (!(await run(() => call("bucket-create", { bucket: name })))) return;
    setNewBucket("");
    toast(`Created bucket ${name}`, "ok");
    loadBuckets();
    setBucket(name);
  };
  const deleteBucket = async () => {
    const ok = await confirm({ title: `Delete bucket ${bucket}?`, body: <p>Every object (and every old version) in it is deleted too.</p>, typed: bucket, confirmLabel: "Delete bucket", danger: true });
    if (ok !== "confirm") return;
    if (await run(() => call("bucket-delete", { bucket, force: true }))) {
      toast(`Deleted bucket ${bucket}`, "ok");
      setBucket("");
      setListing(null);
      loadBuckets();
    }
  };

  const crumbs = prefix.split("/").filter(Boolean);
  const allKeys = [...(listing?.folders || []), ...(listing?.objects || []).map((o) => o.key)];

  return (
    <div className="stack">
      {error && <div className="form-error">{error}</div>}
      <div className="row-gap wrap">
        <b>Bucket</b>
        <select className="select" value={bucket} onChange={(e) => { setBucket(e.target.value); setPrefix(""); setSearch(""); }} aria-label="Bucket">
          {!buckets?.length && <option value="">no buckets yet</option>}
          {(buckets || []).map((b) => (
            <option key={b.name} value={b.name}>
              {b.name}
            </option>
          ))}
        </select>
        <TextInput mono value={newBucket} onChange={setNewBucket} placeholder="new-bucket-name" />
        <button type="button" className="btn btn-sm" disabled={busy || newBucket.trim().length < 3} onClick={() => void createBucket()}>
          + Create bucket
        </button>
        {bucket && (
          <>
            {s3 && (
              <button type="button" className="btn btn-sm" onClick={() => setSettings((v) => !v)}>
                Bucket settings
              </button>
            )}
            <button type="button" className="btn btn-sm btn-danger" disabled={busy} onClick={() => void deleteBucket()}>
              Delete bucket
            </button>
          </>
        )}
      </div>
      {settings && bucket && s3 && <BucketSettings call={call} bucket={bucket} />}
      {bucket && (
        <>
          <div className="row-gap wrap">
            <span className="mono small">
              <button type="button" className="chip-link" onClick={() => setPrefix("")}>
                {bucket}
              </button>
              {crumbs.map((c, i) => (
                <span key={i}>
                  {" / "}
                  <button type="button" className="chip-link" onClick={() => setPrefix(crumbs.slice(0, i + 1).join("/") + "/")}>
                    {c}
                  </button>
                </span>
              ))}
            </span>
            <TextInput value={search} onChange={setSearch} placeholder="filter: name starts with…" />
            <EnumSelect value={limit} onChange={setLimit} options={["25", "50", "100", "500", "1000"].map((v) => ({ value: v, label: `${v} per page` }))} />
          </div>
          <div className="row-gap wrap">
            <label className="btn btn-sm btn-primary">
              Upload files
              <input type="file" multiple hidden onChange={(e) => { void upload(e.target.files); e.target.value = ""; }} />
            </label>
            <TextInput value={folderName} onChange={setFolderName} placeholder="new folder" />
            <button
              type="button"
              className="btn btn-sm"
              disabled={!folderName.trim() || busy}
              onClick={() => void run(() => call("folder", { bucket, prefix: prefix + folderName.trim() })).then(() => { setFolderName(""); refresh(); })}
            >
              + Folder
            </button>
            <button type="button" className="btn btn-sm btn-danger" disabled={!selected.size || busy} onClick={() => void remove([...selected])}>
              Delete selected ({selected.size})
            </button>
            <button type="button" className="btn btn-sm" disabled={busy} onClick={refresh}>
              Refresh
            </button>
            {busy && <span className="muted small">working…</span>}
          </div>
          <table className="table">
            <thead>
              <tr>
                <th>
                  <input
                    type="checkbox"
                    aria-label="Select all"
                    checked={!!allKeys.length && selected.size === allKeys.length}
                    onChange={(e) => setSelected(e.target.checked ? new Set(allKeys) : new Set())}
                  />
                </th>
                <th>Name</th>
                <th>Size</th>
                <th>Modified</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {(listing?.folders || []).map((f) => (
                <tr key={f}>
                  <td>
                    <input type="checkbox" aria-label={`Select ${f}`} checked={selected.has(f)} onChange={(e) => toggle(setSelected, f, e.target.checked)} />
                  </td>
                  <td>
                    <button type="button" className="chip-link mono" onClick={() => { setPrefix(f); setSearch(""); }}>
                      📁 {f.slice(prefix.length)}
                    </button>
                  </td>
                  <td colSpan={2} className="muted small">
                    folder
                  </td>
                  <td>
                    <button type="button" className="btn btn-sm btn-danger" onClick={() => void remove([f])}>
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
              {(listing?.objects || []).filter((o) => o.key !== prefix).map((o) => (
                <tr key={o.key}>
                  <td>
                    <input type="checkbox" aria-label={`Select ${o.key}`} checked={selected.has(o.key)} onChange={(e) => toggle(setSelected, o.key, e.target.checked)} />
                  </td>
                  <td className="mono small">{o.key.slice(prefix.length)}</td>
                  <td className="small">{size(o.size)}</td>
                  <td className="small">{when(o.modified)}</td>
                  <td>
                    <span className="row-gap">
                      <button type="button" className="btn btn-sm" onClick={() => void download(o.key)}>
                        Download
                      </button>
                      <button type="button" className="btn btn-sm" onClick={() => void openInfo(o.key)}>
                        Info
                      </button>
                      <EnumSelect
                        value=""
                        onChange={(v) =>
                          v === "custom" ? setShareFor({ key: o.key, amount: "30", unit: "60" }) : v && void makeShare(o.key, Number(v))
                        }
                        options={[
                          { value: "", label: "Share…" },
                          { value: "3600", label: "link for 1 hour" },
                          { value: "86400", label: "link for 1 day" },
                          { value: "604800", label: "link for 7 days" },
                          { value: "custom", label: "link for…" },
                        ]}
                      />
                      <button type="button" className="btn btn-sm" onClick={() => setTarget({ key: o.key, mode: "move", to: o.key })}>
                        Rename / move
                      </button>
                      <button type="button" className="btn btn-sm" onClick={() => setTarget({ key: o.key, mode: "copy", to: o.key + ".copy" })}>
                        Copy
                      </button>
                      <button type="button" className="btn btn-sm btn-danger" onClick={() => void remove([o.key])}>
                        Delete
                      </button>
                    </span>
                  </td>
                </tr>
              ))}
              {listing && !listing.folders.length && !listing.objects.filter((o) => o.key !== prefix).length && (
                <tr>
                  <td colSpan={5} className="muted">
                    Empty{search ? " (no names start with that filter)" : ""}. Upload files or create a folder.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          <div className="row-gap">
            <button type="button" className="btn btn-sm" disabled={page === 0 || busy} onClick={prevPage}>
              ← Previous
            </button>
            <span className="muted small">Page {page + 1}</span>
            <button type="button" className="btn btn-sm" disabled={!listing?.next || busy} onClick={nextPage}>
              Next →
            </button>
          </div>
        </>
      )}
      {shareFor && (
        <div className="card card-pad stack">
          <b>Share link for {shareFor.key}</b>
          <div className="row-gap">
            <span className="small">Valid for</span>
            <TextInput value={shareFor.amount} onChange={(amount) => setShareFor({ ...shareFor, amount })} />
            <EnumSelect value={shareFor.unit} onChange={(unit) => setShareFor({ ...shareFor, unit })} options={SHARE_UNITS} />
          </div>
          <div className="muted small">From 1 second to 7 days. After that the link is refused.</div>
          <div className="row-gap">
            <button
              type="button"
              className="btn btn-sm btn-primary"
              disabled={busy}
              onClick={() => void makeShare(shareFor.key, Math.round(Number(shareFor.amount) * Number(shareFor.unit)))}
            >
              Create link
            </button>
            <button type="button" className="btn btn-sm" onClick={() => setShareFor(null)}>
              Cancel
            </button>
          </div>
        </div>
      )}
      {share && (
        <div className="hint-box">
          Share link (copied):{" "}
          <a className="mono small" href={share.url} target="_blank" rel="noreferrer">
            {share.url.length > 90 ? share.url.slice(0, 90) + "…" : share.url}
          </a>{" "}
          <button type="button" className="btn btn-sm" onClick={() => setShare(null)}>
            Hide
          </button>
          {s3 ? (
            <div className="muted small">Expires {new Date(share.expires).toLocaleString()}. It works even when the bucket is private.</div>
          ) : (
            <div className="muted small">The emulator has no signed links: this URL works without a login while the port is reachable.</div>
          )}
        </div>
      )}
      {target && (
        <div className="card card-pad stack">
          <b>{target.mode === "move" ? "Rename / move" : "Copy"} {target.key}</b>
          <TextInput mono value={target.to} onChange={(to) => setTarget({ ...target, to })} />
          <div className="row-gap">
            <button
              type="button"
              className="btn btn-sm btn-primary"
              disabled={!target.to || target.to === target.key || busy}
              onClick={() =>
                void run(() => call(target.mode, { bucket, key: target.key, to_key: target.to })).then((r) => {
                  if (r) {
                    toast(target.mode === "move" ? "Moved" : "Copied", "ok");
                    setTarget(null);
                    refresh();
                  }
                })
              }
            >
              {target.mode === "move" ? "Move" : "Copy"}
            </button>
            <button type="button" className="btn btn-sm" onClick={() => setTarget(null)}>
              Cancel
            </button>
          </div>
        </div>
      )}
      {info && (
        <div className="card card-pad stack">
          <b className="mono">{info.head.key}</b>
          <div className="small">
            {size(info.head.size)} · {info.head.content_type} · modified {when(info.head.modified)} · ETag <span className="mono">{info.head.etag}</span>
          </div>
          {Object.keys(info.head.metadata || {}).length > 0 && (
            <div className="small">
              Metadata:{" "}
              {Object.entries(info.head.metadata).map(([k, v]) => (
                <span key={k} className="chip mono">
                  {k}={v}
                </span>
              ))}
            </div>
          )}
          {info.versions.length > 0 && (
            <table className="table">
              <thead>
                <tr>
                  <th>Version</th>
                  <th>Modified</th>
                  <th>Size</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {info.versions.map((v) => (
                  <tr key={v.version}>
                    <td className="mono small">
                      {v.version}
                      {v.latest ? " (latest)" : ""}
                      {v.deleted ? " (delete marker)" : ""}
                    </td>
                    <td className="small">{when(v.modified)}</td>
                    <td className="small">{v.deleted ? "" : size(v.size)}</td>
                    <td>
                      {!v.deleted && (
                        <button type="button" className="btn btn-sm" onClick={() => void download(info.head.key, v.version)}>
                          Download
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <button type="button" className="btn btn-sm" onClick={() => setInfo(null)}>
            Close
          </button>
        </div>
      )}
    </div>
  );
}

function toggle(set: (fn: (s: Set<string>) => Set<string>) => void, key: string, on: boolean) {
  set((s) => {
    const n = new Set(s);
    if (on) n.add(key);
    else n.delete(key);
    return n;
  });
}

function BucketSettings({ call, bucket }: { call: <T>(action: string, body?: Body) => Promise<T>; bucket: string }) {
  const toast = useToast();
  const [versioning, setVersioning] = useState<string | null>(null);
  const [policy, setPolicy] = useState("");
  const [blocked, setBlocked] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const show = (r: { policy: string; blocked?: boolean }) => {
    setPolicy(r.policy ? JSON.stringify(JSON.parse(r.policy), null, 2) : "");
    setBlocked(!!r.blocked);
  };
  useEffect(() => {
    call<{ status: string }>("versioning", { bucket }).then((r) => setVersioning(r.status), (e) => setError(errorMessage(e)));
    call<{ policy: string; blocked?: boolean }>("policy", { bucket }).then(show, () => undefined);
  }, [call, bucket]);
  const apply = (body: Body, done: string) =>
    call<{ policy: string; blocked?: boolean }>("policy", { bucket, ...body }).then(
      (r) => {
        show(r);
        toast(done, "ok");
      },
      (e) => setError(errorMessage(e)),
    );
  const isPublic = !blocked && /"s3:GetObject"/.test(policy) && /"\*"/.test(policy);
  return (
    <div className="card card-pad stack">
      {error && <div className="form-error">{error}</div>}
      <Toggle
        checked={versioning === "Enabled"}
        onChange={(on) =>
          call<{ status: string }>("versioning", { bucket, enabled: on }).then(
            (r) => {
              setVersioning(r.status);
              toast(`Versioning ${r.status.toLowerCase()}`, "ok");
            },
            (e) => setError(errorMessage(e)),
          )
        }
        label={`Versioning (${versioning || "…"}): keep every version of an object; Info lists and downloads old ones`}
      />
      <div className="row-gap wrap">
        <b>Access</b>
        <span className={`badge ${isPublic ? "badge-warn" : ""}`}>
          {blocked ? "private (public access blocked)" : isPublic ? "public read" : policy ? "custom policy" : "private"}
        </span>
        <button type="button" className="btn btn-sm" onClick={() => void apply({ preset: "private" }, "Bucket is private")}>
          Make private
        </button>
        <button type="button" className="btn btn-sm" onClick={() => void apply({ preset: "public-read" }, "Anyone can read objects now")}>
          Make public (read)
        </button>
      </div>
      <div className="muted small">
        Make private removes the policy, resets the bucket ACL and blocks public access, so objects uploaded with a public-read ACL
        are refused without keys too (where the service supports it). Share links keep working until they expire.
      </div>
      <label className="small">Bucket policy (JSON, the S3 format)</label>
      <textarea className="input mono" rows={8} value={policy} onChange={(e) => setPolicy(e.target.value)} placeholder="no policy: private" />
      <button type="button" className="btn btn-sm" disabled={!policy.trim()} onClick={() => void apply({ policy }, "Policy saved")}>
        Save policy
      </button>
    </div>
  );
}

// ----------------------------------------------------------------------------- secrets

interface SecretItem {
  name: string;
  folder: boolean;
  path: string;
  modified?: string;
}
interface Secret {
  path: string;
  data: Record<string, string>;
  version?: number | string | null;
  versions: { version: number; created?: string; deleted: boolean }[];
}

function SecretsBrowser({ serviceKey, kind }: { serviceKey: string; kind: string }) {
  const call = useBrowse(serviceKey, kind);
  const toast = useToast();
  const confirm = useConfirm();
  const vault = kind === "vault";
  const [folder, setFolder] = useState("");
  const [items, setItems] = useState<SecretItem[] | null>(null);
  const [tokens, setTokens] = useState<(string | null)[]>([null]);
  const [next, setNext] = useState<string | null>(null);
  const [open, setOpen] = useState<Secret | null>(null);
  const [edit, setEdit] = useState<{ path: string; rows: [string, string][]; isNew: boolean } | null>(null);
  const [reveal, setReveal] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const list = useCallback(
    (token: string | null) => {
      setError(null);
      call<{ items: SecretItem[]; next: string | null }>("list", { path: folder || undefined, token: token || undefined }).then(
        (r) => {
          setItems(r.items);
          setNext(r.next);
        },
        (e) => setError(errorMessage(e)),
      );
    },
    [call, folder],
  );
  useEffect(() => {
    setTokens([null]);
    list(null);
  }, [list]);

  const show = (path: string, version?: number) =>
    call<Secret>("get", { path, version }).then(
      (s) => {
        setOpen(s);
        setReveal(false);
      },
      (e) => setError(errorMessage(e)),
    );

  const save = async () => {
    if (!edit) return;
    const data = Object.fromEntries(edit.rows.filter(([k]) => k.trim()).map(([k, v]) => [k.trim(), v]));
    if (!Object.keys(data).length) return setError("add at least one key");
    try {
      await call("put", { path: edit.path.trim(), data });
      toast(edit.isNew ? `Created ${edit.path}` : `Saved ${edit.path} (new version)`, "ok");
      setEdit(null);
      list(tokens[tokens.length - 1]);
      void show(edit.path.trim());
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  const remove = async (path: string) => {
    const ok = await confirm({ title: `Delete secret ${path}?`, body: vault ? <p>Every version is deleted.</p> : undefined, confirmLabel: "Delete", danger: true });
    if (ok !== "confirm") return;
    try {
      await call("delete", { path });
      toast(`Deleted ${path}`, "ok");
      setOpen(null);
      list(tokens[tokens.length - 1]);
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  const crumbs = folder.split("/").filter(Boolean);
  return (
    <div className="stack">
      {error && <div className="form-error">{error}</div>}
      <div className="row-gap wrap">
        {vault && (
          <span className="mono small">
            <button type="button" className="chip-link" onClick={() => setFolder("")}>
              secret
            </button>
            {crumbs.map((c, i) => (
              <span key={i}>
                {" / "}
                <button type="button" className="chip-link" onClick={() => setFolder(crumbs.slice(0, i + 1).join("/"))}>
                  {c}
                </button>
              </span>
            ))}
          </span>
        )}
        <button type="button" className="btn btn-sm btn-primary" onClick={() => setEdit({ path: folder ? folder + "/" : "", rows: [["", ""]], isNew: true })}>
          + New secret
        </button>
        <button type="button" className="btn btn-sm" onClick={() => list(tokens[tokens.length - 1])}>
          Refresh
        </button>
      </div>
      <table className="table">
        <tbody>
          {(items || []).map((it) => (
            <tr key={it.path}>
              <td>
                {it.folder ? (
                  <button type="button" className="chip-link mono" onClick={() => setFolder(it.path)}>
                    📁 {it.name}/
                  </button>
                ) : (
                  <button type="button" className="chip-link mono" onClick={() => void show(it.path)}>
                    🔑 {it.name}
                  </button>
                )}
              </td>
              <td className="small muted">{when(it.modified)}</td>
              <td>
                {!it.folder && (
                  <button type="button" className="btn btn-sm btn-danger" onClick={() => void remove(it.path)}>
                    Delete
                  </button>
                )}
              </td>
            </tr>
          ))}
          {items && !items.length && (
            <tr>
              <td className="muted">No secrets here yet.</td>
            </tr>
          )}
        </tbody>
      </table>
      {!vault && (
        <div className="row-gap">
          <button type="button" className="btn btn-sm" disabled={tokens.length < 2} onClick={() => { const t = tokens.slice(0, -1); setTokens(t); list(t[t.length - 1]); }}>
            ← Previous
          </button>
          <button type="button" className="btn btn-sm" disabled={!next} onClick={() => { setTokens([...tokens, next]); list(next); }}>
            Next →
          </button>
        </div>
      )}
      {open && !edit && (
        <div className="card card-pad stack">
          <div className="row-gap wrap">
            <b className="mono">{open.path}</b>
            {open.version != null && <span className="badge">version {String(open.version)}</span>}
            {vault && open.versions.length > 1 && (
              <EnumSelect
                value={String(open.version ?? "")}
                onChange={(v) => void show(open.path, Number(v))}
                options={open.versions.map((v) => ({ value: String(v.version), label: `v${v.version} · ${when(v.created)}${v.deleted ? " (deleted)" : ""}` }))}
              />
            )}
            <Toggle checked={reveal} onChange={setReveal} label="Show values" />
          </div>
          <table className="table">
            <tbody>
              {Object.entries(open.data).map(([k, v]) => (
                <tr key={k}>
                  <td className="mono small">{k}</td>
                  <td className="mono small">{reveal ? v : "••••••••"}</td>
                  <td>
                    <button type="button" className="btn btn-sm" onClick={() => navigator.clipboard?.writeText(v).then(() => toast("Copied", "ok"))}>
                      Copy
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="row-gap">
            <button type="button" className="btn btn-sm btn-primary" onClick={() => setEdit({ path: open.path, rows: Object.entries(open.data), isNew: false })}>
              Edit
            </button>
            <button type="button" className="btn btn-sm btn-danger" onClick={() => void remove(open.path)}>
              Delete
            </button>
            <button type="button" className="btn btn-sm" onClick={() => setOpen(null)}>
              Close
            </button>
          </div>
          <div className="muted small">
            In handlers: <code className="mono">get_secret("{open.path}"{serviceKey === "secrets" ? "" : `, store="${serviceKey}"`})</code>
          </div>
        </div>
      )}
      {edit && (
        <div className="card card-pad stack">
          <b>{edit.isNew ? "New secret" : `Edit ${edit.path}`}</b>
          {edit.isNew && <TextInput mono value={edit.path} onChange={(path) => setEdit({ ...edit, path })} placeholder={vault ? "app/database" : "app-database"} />}
          {edit.rows.map(([k, v], i) => (
            <div key={i} className="row-gap">
              <TextInput mono value={k} placeholder="key" onChange={(nk) => setEdit({ ...edit, rows: edit.rows.map((r, j) => (j === i ? [nk, r[1]] : r)) })} />
              <TextInput mono value={v} placeholder="value" onChange={(nv) => setEdit({ ...edit, rows: edit.rows.map((r, j) => (j === i ? [r[0], nv] : r)) })} />
              <button type="button" className="btn btn-sm" aria-label="Remove key" onClick={() => setEdit({ ...edit, rows: edit.rows.filter((_r, j) => j !== i) })}>
                ✕
              </button>
            </div>
          ))}
          <div className="row-gap">
            <button type="button" className="btn btn-sm" onClick={() => setEdit({ ...edit, rows: [...edit.rows, ["", ""]] })}>
              + Key
            </button>
            <button type="button" className="btn btn-sm btn-primary" disabled={!edit.path.trim()} onClick={() => void save()}>
              Save
            </button>
            <button type="button" className="btn btn-sm" onClick={() => setEdit(null)}>
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
