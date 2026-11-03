import type { ReactNode } from "react";

/**
 * Renders the resource guides: headings, paragraphs, lists, tables, code blocks, inline code,
 * bold and links. Builds React elements (never HTML strings), so guide text cannot inject markup.
 * `onLink` receives relative links (other guides); absolute ones open in a new tab.
 */
export function Markdown({ text, onLink }: { text: string; onLink?: (href: string) => void }) {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const out: ReactNode[] = [];
  let i = 0;
  let key = 0;
  const inline = (s: string) => renderInline(s, onLink);
  while (i < lines.length) {
    const line = lines[i];
    if (line.startsWith("```")) {
      const lang = line.slice(3).trim();
      const body: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) body.push(lines[i++]);
      i++;
      const code = body.join("\n");
      out.push(
        <div key={key++} className="code-block">
          <button type="button" className="btn btn-sm code-copy" onClick={() => void navigator.clipboard?.writeText(code)} title="Copy">
            Copy
          </button>
          <pre className="md-code" data-lang={lang || undefined}>
            <code>{code}</code>
          </pre>
        </div>,
      );
      continue;
    }
    const heading = /^(#{1,4})\s+(.*)$/.exec(line);
    if (heading) {
      const level = heading[1].length;
      const content = inline(heading[2]);
      out.push(level === 1 ? <h2 key={key++}>{content}</h2> : level === 2 ? <h3 key={key++}>{content}</h3> : <h4 key={key++}>{content}</h4>);
      i++;
      continue;
    }
    if (line.trim().startsWith("|") && i + 1 < lines.length && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1])) {
      const cells = (row: string) => row.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
      const head = cells(line);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) rows.push(cells(lines[i++]));
      out.push(
        <div key={key++} className="md-table-wrap">
          <table className="md-table">
            <thead>
              <tr>{head.map((c, n) => <th key={n}>{inline(c)}</th>)}</tr>
            </thead>
            <tbody>
              {rows.map((r, n) => (
                <tr key={n}>{r.map((c, m) => <td key={m}>{inline(c)}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }
    const bullet = /^(\s*)([-*]|\d+\.)\s+(.*)$/.exec(line);
    if (bullet) {
      const ordered = /\d/.test(bullet[2]);
      const items: string[] = [];
      while (i < lines.length) {
        const m = /^(\s*)([-*]|\d+\.)\s+(.*)$/.exec(lines[i]);
        if (m) {
          items.push(m[3]);
          i++;
        } else if (lines[i].startsWith("  ") && lines[i].trim() && items.length) {
          items[items.length - 1] += " " + lines[i++].trim();
        } else break;
      }
      const children = items.map((it, n) => <li key={n}>{inline(it)}</li>);
      out.push(ordered ? <ol key={key++}>{children}</ol> : <ul key={key++}>{children}</ul>);
      continue;
    }
    if (!line.trim()) {
      i++;
      continue;
    }
    const para: string[] = [];
    while (i < lines.length && lines[i].trim() && !/^(#{1,4}\s|```|\s*([-*]|\d+\.)\s|\s*\|)/.test(lines[i])) para.push(lines[i++]);
    if (!para.length) para.push(lines[i++]);
    out.push(<p key={key++}>{inline(para.join(" "))}</p>);
  }
  return <div className="markdown">{out}</div>;
}

function renderInline(text: string, onLink?: (href: string) => void): ReactNode[] {
  const parts: ReactNode[] = [];
  const re = /(`[^`]+`)|(\*\*[^*]+\*\*)|(\[([^\]]+)\]\(([^)\s]+)\))/g;
  let last = 0;
  let n = 0;
  for (let m = re.exec(text); m; m = re.exec(text)) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    if (m[1]) parts.push(<code key={n++}>{m[1].slice(1, -1)}</code>);
    else if (m[2]) parts.push(<b key={n++}>{m[2].slice(2, -2)}</b>);
    else {
      const label = m[4];
      const href = m[5];
      if (/^https?:\/\//.test(href)) {
        parts.push(
          <a key={n++} href={href} target="_blank" rel="noreferrer noopener">
            {label}
          </a>,
        );
      } else {
        parts.push(
          <a
            key={n++}
            href="#"
            onClick={(e) => {
              e.preventDefault();
              onLink?.(href);
            }}
          >
            {label}
          </a>,
        );
      }
    }
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}
