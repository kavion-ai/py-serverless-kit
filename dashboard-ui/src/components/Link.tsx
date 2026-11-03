import { safeUrl } from "../format";

/** Links only http(s) URLs; anything else is shown as plain text. */
export function ExtLink({ href, children }: { href?: string | null; children?: string }) {
  const url = safeUrl(href);
  if (!url) return <span className="mono">{href || "—"}</span>;
  return (
    <a href={url} target="_blank" rel="noopener noreferrer">
      {children || url}
    </a>
  );
}
