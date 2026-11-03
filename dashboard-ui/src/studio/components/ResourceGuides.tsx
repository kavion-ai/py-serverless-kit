import { useEffect, useState } from "react";
import { Drawer } from "../../components/Drawer";
import { api, errorMessage } from "../api";
import type { GuideIndex, GuidePage } from "../types";
import { Markdown } from "./Markdown";

export interface GuideRef {
  cloud: string;
  page: string;
}

/** Resolve a relative link inside a guide (`queue.md`, `../azure/queue.md#x`) to another guide. */
function resolve(from: GuideRef, href: string): GuideRef | null {
  const path = href.split("#")[0];
  if (!path.endsWith(".md")) return null;
  const parts = (from.cloud === "index" ? [] : [from.cloud]).concat(path.split("/"));
  const stack: string[] = [];
  for (const part of parts) {
    if (part === "..") {
      if (!stack.length) return null; // above docs/resource-guides: not shown here
      stack.pop();
    } else if (part && part !== ".") stack.push(part);
  }
  const file = (stack.pop() || "").replace(/\.md$/, "").toLowerCase();
  if (stack.length > 1) return null;
  return { cloud: stack[0] || "index", page: file === "readme" ? "readme" : file };
}

export function ResourceGuides({ open, start, onClose }: { open: boolean; start?: GuideRef; onClose: () => void }) {
  const [index, setIndex] = useState<GuideIndex | null>(null);
  const [current, setCurrent] = useState<GuideRef>(start || { cloud: "onprem", page: "readme" });
  const [page, setPage] = useState<GuidePage | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (start) setCurrent(start);
  }, [start?.cloud, start?.page]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!open || index) return;
    api.guides().then(setIndex).catch((exc: unknown) => setError(errorMessage(exc)));
  }, [open, index]);

  useEffect(() => {
    if (!open) return undefined;
    let live = true;
    setError(null);
    api
      .guide(current.cloud, current.page)
      .then((p) => live && setPage(p))
      .catch((exc: unknown) => live && setError(errorMessage(exc)));
    return () => {
      live = false;
    };
  }, [open, current.cloud, current.page]);

  const cloud = index?.clouds.find((c) => c.id === current.cloud);
  return (
    <Drawer open={open} title="Resource guides" onClose={onClose}>
      <div className="guides">
        {index && !index.available && <div className="hint-box">The guides are not installed with this copy of pskit.</div>}
        {index?.available && (
          <div className="guide-nav">
            <select value={current.cloud} aria-label="Cloud" onChange={(e) => setCurrent({ cloud: e.target.value, page: "readme" })}>
              {index.clouds.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.id === "index" ? "General (all clouds, compatibility)" : c.id === "onprem" ? "On premises" : c.title.replace(/^Adding resources:\s*/i, "").replace(/ resources$/i, "")}
                </option>
              ))}
            </select>
            {cloud && (
              <span className="chips">
                {cloud.pages.map((p) => (
                  <button
                    key={p.id}
                    type="button"
                    className={p.id === current.page ? "chip chip-accent chip-btn" : "chip chip-btn"}
                    onClick={() => setCurrent({ cloud: cloud.id, page: p.id })}
                  >
                    {p.id === "readme" ? "Overview" : p.id === "compatibility" ? "Existing cloud code" : p.id}
                  </button>
                ))}
              </span>
            )}
          </div>
        )}
        {error && <div className="form-error">{error}</div>}
        {page && (
          <Markdown
            text={page.markdown}
            onLink={(href) => {
              const next = resolve(current, href);
              if (next) setCurrent(next);
            }}
          />
        )}
      </div>
    </Drawer>
  );
}
