import { useEffect, useState } from "react";
import { Modal } from "../../components/Drawer";
import { EmptyState, ErrorBanner, Spinner } from "../../components/Feedback";
import { api, errorMessage } from "../api";
import type { FsListing } from "../types";
import { TextInput, Toggle } from "./Forms";

/**
 * Pick a file on the machine running pskit studio (e.g. an SSH private key).
 * The browser can't reveal local paths, so the studio server lists folders.
 */
export function FilePickerModal({
  open,
  title = "Choose a file",
  start,
  keysOnly = false,
  folder = false,
  onClose,
  onPick,
}: {
  open: boolean;
  title?: string;
  start?: string;
  keysOnly?: boolean;
  /** Pick a folder (the one shown, with "Use this folder") instead of a file. */
  folder?: boolean;
  onClose: () => void;
  onPick: (path: string) => void;
}) {
  const [listing, setListing] = useState<FsListing | null>(null);
  const [path, setPath] = useState<string | undefined>(start);
  const [typed, setTyped] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [onlyKeys, setOnlyKeys] = useState(keysOnly);

  useEffect(() => {
    if (open) setPath(start || (folder ? "~" : undefined));
  }, [open, start, folder]);

  useEffect(() => {
    if (!open) return undefined;
    let live = true;
    setLoading(true);
    setError(null);
    api
      .browse(path)
      .then((r) => {
        if (!live) return;
        setListing(r);
        setTyped(r.path);
      })
      .catch((exc: unknown) => live && setError(errorMessage(exc)))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [open, path]);

  const entries = (listing?.entries || []).filter((e) => e.type === "dir" || (!folder && (!onlyKeys || e.key)));
  const sep = listing?.path.includes("\\") ? "\\" : "/";
  return (
    <Modal open={open} title={title} onClose={onClose}>
      <div className="stack">
        <div className="row-gap wrap">
          <button type="button" className="btn btn-sm" disabled={!listing?.parent} onClick={() => listing?.parent && setPath(listing.parent)}>
            ↑ Up
          </button>
          {listing && (
            <>
              <button type="button" className="btn btn-sm" onClick={() => setPath(listing.home)}>
                Home
              </button>
              <button type="button" className="btn btn-sm" onClick={() => setPath(`${listing.home}${sep}.ssh`)}>
                ~/.ssh
              </button>
              {listing.roots.length > 1 &&
                listing.roots.map((r) => (
                  <button key={r} type="button" className="btn btn-sm" onClick={() => setPath(r)}>
                    {r}
                  </button>
                ))}
            </>
          )}
          <span className="grow" />
          {folder ? (
            <button
              type="button"
              className="btn btn-sm btn-primary"
              disabled={!listing}
              onClick={() => {
                if (!listing) return;
                onPick(listing.path);
                onClose();
              }}
            >
              Use this folder
            </button>
          ) : (
            <Toggle checked={onlyKeys} onChange={setOnlyKeys} label="Key files only" />
          )}
        </div>
        <form
          className="row-gap"
          onSubmit={(e) => {
            e.preventDefault();
            if (typed.trim()) setPath(typed.trim());
          }}
        >
          <TextInput mono value={typed} onChange={setTyped} placeholder="/home/me/.ssh" />
          <button type="submit" className="btn btn-sm">
            Go
          </button>
        </form>
        {loading && <Spinner label="Listing…" />}
        {error && <ErrorBanner message={error} />}
        {listing && !loading && !error && (
          <>
            {!entries.length ? (
              <EmptyState title="Nothing here">{folder ? "No folders inside. Use this folder, or go up." : onlyKeys ? "No key files in this folder. Turn off “Key files only” to see everything." : "This folder is empty."}</EmptyState>
            ) : (
              <ul className="pick-list file-list" role="listbox" aria-label="Files">
                {entries.map((e) => (
                  <li key={e.path}>
                    <button
                      type="button"
                      className="pick"
                      onClick={() => {
                        if (e.type === "dir") setPath(e.path);
                        else {
                          onPick(e.path);
                          onClose();
                        }
                      }}
                    >
                      <b>
                        {e.type === "dir" ? "📁 " : e.key ? "🔑 " : "📄 "}
                        {e.name}
                      </b>
                      {e.type === "file" && <span className="muted small">{e.size === null || e.size === undefined ? "" : `${e.size} bytes`}</span>}
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {listing.truncated && <div className="muted small">Showing the first 1000 entries. Type a path to go elsewhere.</div>}
          </>
        )}
      </div>
    </Modal>
  );
}
