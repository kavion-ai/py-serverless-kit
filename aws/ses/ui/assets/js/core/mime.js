// A small MIME reader for TestRenderEmailTemplate's RenderedTemplate: headers (unfolded, RFC 2047 words decoded),
// and the text/plain and text/html parts of a (nested) multipart message, with 7bit / 8bit / quoted-printable /
// base64 transfer encodings. Enough for showing a rendered template; not a general mail parser.

const decoderFor = (charset) => {
  try {
    return new TextDecoder(charset || "utf-8");
  } catch {
    return new TextDecoder("utf-8");
  }
};

function bytesOfBinaryString(s) {
  const out = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i += 1) out[i] = s.charCodeAt(i) & 0xff;
  return out;
}

function qpBytes(text, header = false) {
  const src = header ? text.replace(/_/g, " ") : text.replace(/=\r?\n/g, "");
  const out = [];
  const utf8 = new TextEncoder();
  for (let i = 0; i < src.length; i += 1) {
    const c = src[i];
    if (c === "=" && /^[0-9A-Fa-f]{2}$/.test(src.slice(i + 1, i + 3))) {
      out.push(parseInt(src.slice(i + 1, i + 3), 16));
      i += 2;
    } else {
      out.push(...utf8.encode(c));
    }
  }
  return new Uint8Array(out);
}

function b64Bytes(text) {
  try {
    return bytesOfBinaryString(atob(text.replace(/\s+/g, "")));
  } catch {
    return new Uint8Array();
  }
}

/** "=?utf-8?q?H=C3=A9llo?= world" -> "Héllo world". */
export function decodeWords(value) {
  return String(value || "")
    .replace(/\?=\s+=\?/g, "?==?")
    .replace(/=\?([^?]+)\?([QqBb])\?([^?]*)\?=/g, (_m, charset, enc, text) => {
      const data = enc.toUpperCase() === "B" ? b64Bytes(text) : qpBytes(text, true);
      return decoderFor(charset.split("*")[0]).decode(data);
    });
}

function splitHead(text) {
  const m = /\r?\n\r?\n/.exec(text);
  if (!m) return [text, ""];
  return [text.slice(0, m.index), text.slice(m.index + m[0].length)];
}

/** "Name: value" lines (folded lines joined) -> [{ Name, Value }]. */
export function parseHeaders(head) {
  const out = [];
  for (const line of head.split(/\r?\n/)) {
    if (/^[ \t]/.test(line) && out.length) out[out.length - 1].Value += ` ${line.trim()}`;
    else {
      const at = line.indexOf(":");
      if (at > 0) out.push({ Name: line.slice(0, at).trim(), Value: line.slice(at + 1).trim() });
    }
  }
  return out.map((x) => ({ Name: x.Name, Value: decodeWords(x.Value) }));
}

function header(headers, name) {
  const found = headers.find((x) => x.Name.toLowerCase() === name.toLowerCase());
  return found ? found.Value : "";
}

function param(value, name) {
  const m = new RegExp(`${name}\\s*=\\s*("([^"]*)"|[^;\\s]+)`, "i").exec(value || "");
  return m ? (m[2] !== undefined ? m[2] : m[1]) : "";
}

function bodyText(body, headers) {
  const cte = header(headers, "Content-Transfer-Encoding").toLowerCase();
  const charset = param(header(headers, "Content-Type"), "charset") || "utf-8";
  if (cte === "base64") return decoderFor(charset).decode(b64Bytes(body));
  if (cte === "quoted-printable") return decoderFor(charset).decode(qpBytes(body));
  return body.replace(/\r?\n$/, "");
}

/** { headers, subject, text, html } of a MIME message given as text. */
export function readMime(raw) {
  const out = { headers: [], subject: "", text: "", html: "" };
  const walk = (part, top) => {
    const [head, body] = splitHead(part);
    const headers = parseHeaders(head);
    if (top) out.headers = headers;
    const ctype = (header(headers, "Content-Type") || "text/plain").toLowerCase();
    if (ctype.startsWith("multipart/")) {
      const boundary = param(header(headers, "Content-Type"), "boundary");
      if (!boundary) return;
      const pieces = body.split(`--${boundary}`);
      for (const piece of pieces.slice(1)) {
        if (piece.startsWith("--")) break;
        walk(piece.replace(/^\r?\n/, ""), false);
      }
    } else if (ctype.startsWith("text/html") && !out.html) {
      out.html = bodyText(body, headers);
    } else if (ctype.startsWith("text/plain") && !out.text) {
      out.text = bodyText(body, headers);
    }
  };
  walk(String(raw || ""), true);
  out.subject = header(out.headers, "Subject");
  return out;
}
