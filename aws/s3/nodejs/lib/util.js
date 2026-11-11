"use strict";
// Time, XML (a small ElementTree), escaping, URI encoding and logging helpers.

const { ValueError, asciiStrip, pyStrip } = require("./py");
const { malformed } = require("./errors");
const { NS, OWNER_ID, OWNER_NAME } = require("./config");

const SAFE = new Set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-~");

/** urllib.parse.quote(value, safe). */
function quote(value, safe = "/") {
  const bytes = Buffer.from(String(value), "utf8");
  let out = "";
  for (const b of bytes) {
    const c = String.fromCharCode(b);
    if (b < 128 && (SAFE.has(c) || safe.includes(c))) out += c;
    else out += `%${b < 16 ? "0" : ""}${b.toString(16).toUpperCase()}`;
  }
  return out;
}

const UTF8 = new TextDecoder("utf-8", { ignoreBOM: true });
const UTF8_STRICT = new TextDecoder("utf-8", { ignoreBOM: true, fatal: true });

/** urllib.parse.unquote: %XX runs decoded as UTF-8 (bad bytes become U+FFFD), "+" left alone. */
function unquote(s) {
  if (!s.includes("%")) return s;
  return s.replace(/(?:%[0-9A-Fa-f]{2})+/g, (run) => UTF8.decode(Buffer.from(run.replace(/%/g, ""), "hex")));
}

function log(...parts) {
  console.log(new Date().toISOString().replace(/\.\d+Z$/, "+00:00"), ...parts);
}

const epoch = () => Date.now() / 1000;
const now3 = () => Math.round(Date.now()) / 1000;

function iso(ts) {
  const ms = Math.round(ts * 1000);
  const secs = Math.floor(Math.round(ts * 1e6) / 1e6);
  return `${new Date(secs * 1000).toISOString().slice(0, 19)}.${String(((ms % 1000) + 1000) % 1000).padStart(3, "0")}Z`;
}

const httpDate = (ts) => new Date(Math.trunc(ts) * 1000).toUTCString();
const amzStamp = (ts) => new Date(Math.floor(ts) * 1000).toISOString().replace(/[-:]/g, "").replace(/\.\d+Z$/, "Z");
const MONTHS = { jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6, jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12 };

const ZONES = { UT: 0, UTC: 0, GMT: 0, Z: 0, AST: -400, ADT: -300, EST: -500, EDT: -400, CST: -600, CDT: -500, MST: -700,
  MDT: -600, PST: -800, PDT: -700 };

function utcSeconds(y, mo, d, h, mi, s) {
  if (mo < 1 || mo > 12 || d < 1 || h > 23 || mi > 59 || s > 59 || y < 1) return null;
  const days = new Date(Date.UTC(2000, mo, 0)).getUTCDate() - (mo === 2 && !(y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0)) ? 1 : 0);
  if (d > days) return null;
  const date = new Date(0);
  date.setUTCFullYear(y, mo - 1, d);
  date.setUTCHours(h, mi, s, 0);
  return date.getTime() / 1000;
}

/** Python's parse_time: an RFC 2822 date, an ISO 8601 date (naive means UTC) or a compact x-amz-date; else null. */
function parseTime(input) {
  const textIn = pyStrip(input || "");
  if (!textIn) return null;
  let m = /^(?:[A-Za-z]+,?\s*)?(\d{1,2})[\s-]+([A-Za-z]{3})[A-Za-z]*[\s-]+(\d{2,4})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?(?:\s*([A-Za-z]+|[+-]\d{4}))?\s*$/.exec(textIn);
  if (m && MONTHS[m[2].toLowerCase()]) {
    let year = Number(m[3]);
    if (year < 100) year += year > 68 ? 1900 : 2000;
    const base = utcSeconds(year, MONTHS[m[2].toLowerCase()], Number(m[1]), Number(m[4]), Number(m[5]), Number(m[6] || 0));
    if (base !== null) {
      let offset = 0;
      const zone = m[7] || "";
      if (/^[+-]\d{4}$/.test(zone)) offset = (zone[0] === "-" ? -1 : 1) * (Number(zone.slice(1, 3)) * 3600 + Number(zone.slice(3)) * 60);
      else if (ZONES[zone.toUpperCase()] !== undefined) offset = (ZONES[zone.toUpperCase()] / 100) * 3600;
      return base - offset;
    }
  }
  const cleaned = textIn.replace(/Z/g, "+00:00");
  m = /^(\d{4})(-?)(\d{2})\2(\d{2})(?:.(\d{2})(?::?(\d{2})(?::?(\d{2})(?:[.,](\d{1,9}))?)?)?(?:([+-])(\d{2})(?::?(\d{2})(?::?(\d{2})(?:\.(\d{1,6}))?)?)?)?)?$/.exec(cleaned);
  if (m) {
    const base = utcSeconds(Number(m[1]), Number(m[3]), Number(m[4]), Number(m[5] || 0), Number(m[6] || 0), Number(m[7] || 0));
    if (base !== null) {
      const frac = m[8] ? Number(`0.${m[8].slice(0, 6)}`) : 0;
      let offset = 0;
      if (m[9]) {
        if (Number(m[10]) > 23 || Number(m[11] || 0) > 59) return null;
        offset = (Number(m[10]) * 3600 + Number(m[11] || 0) * 60 + Number(m[12] || 0)) * (m[9] === "-" ? -1 : 1);
      }
      return base + frac - offset;
    }
  }
  return null;
}

function esc(value) {
  return String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;")
    .replace(/\r/g, "&#13;");
}

const x = (tag, value) => `<${tag}>${esc(value)}</${tag}>`;
const doc = (root, inner) => Buffer.from(`<?xml version="1.0" encoding="UTF-8"?>\n<${root} xmlns="${NS}">${inner}</${root}>`, "utf8");
const stripDecl = (xmlText) => xmlText.replace(/^\s*<\?xml[^>]*\?>\s*/, "");
const urlEnc = (value, enabled) => (enabled ? quote(value, "/") : value);
const ownerXml = () => `<Owner>${x("ID", OWNER_ID)}${x("DisplayName", OWNER_NAME)}</Owner>`;

class XmlElement {
  constructor(tag) {
    this.tag = tag;
    this.text = null; // null when there is no character data before the first child, as ElementTree
    this.children = [];
  }

  findall(pathText) {
    let nodes = [this];
    for (const part of pathText.split("/")) {
      const next = [];
      for (const node of nodes) for (const child of node.children) if (child.tag === part) next.push(child);
      nodes = next;
    }
    return nodes;
  }

  find(pathText) {
    return this.findall(pathText)[0] || null;
  }

  *iter(tag) {
    if (tag === undefined || this.tag === tag) yield this;
    for (const child of this.children) yield* child.iter(tag);
  }
}

const XML_START = /<([^\s<>/=!?"']+)((?:\s+[^\s=/>"'<]+\s*=\s*(?:"[^"<]*"|'[^'<]*'))*)\s*(\/?)>/y;
const XML_END = /<\/([^\s<>/=!?"']+)\s*>/y;

function xmlEntities(raw) {
  if (!raw.includes("&")) return raw;
  return raw.replace(/&([^;&<]*);?/g, (whole, name) => {
    if (!whole.endsWith(";")) throw new ValueError("not well-formed");
    const named = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'" }[name];
    if (named) return named;
    const ref = /^#(?:x([0-9a-fA-F]+)|([0-9]+))$/.exec(name);
    if (!ref) throw new ValueError("undefined entity");
    const cp = ref[1] ? parseInt(ref[1], 16) : parseInt(ref[2], 10);
    const ok = cp === 0x9 || cp === 0xa || cp === 0xd || (cp >= 0x20 && cp <= 0xd7ff) || (cp >= 0xe000 && cp <= 0xfffd) ||
      (cp >= 0x10000 && cp <= 0x10ffff);
    if (!ok) throw new ValueError("reference to invalid character number");
    return String.fromCodePoint(cp);
  });
}

function parseXmlText(input) {
  const src = input.replace(/\r\n?/g, "\n");
  let i = src.charCodeAt(0) === 0xfeff ? 1 : 0;
  const stack = [];
  let root = null;
  const addText = (t) => {
    if (!t) return;
    if (!stack.length) {
      if (/[^ \t\n]/.test(t)) throw new ValueError("junk outside the root element");
      return;
    }
    const top = stack[stack.length - 1];
    if (!top.children.length) top.text = (top.text || "") + t;
  };
  while (i < src.length) {
    const lt = src.indexOf("<", i);
    const end = lt < 0 ? src.length : lt;
    if (end > i) addText(xmlEntities(src.slice(i, end)));
    if (lt < 0) break;
    i = lt;
    if (src.startsWith("<?", i)) {
      const e = src.indexOf("?>", i + 2);
      if (e < 0) throw new ValueError("unclosed processing instruction");
      i = e + 2;
    } else if (src.startsWith("<!--", i)) {
      const e = src.indexOf("-->", i + 4);
      if (e < 0) throw new ValueError("unclosed comment");
      i = e + 3;
    } else if (src.startsWith("<![CDATA[", i)) {
      const e = src.indexOf("]]>", i + 9);
      if (e < 0 || !stack.length) throw new ValueError("bad CDATA");
      addText(src.slice(i + 9, e));
      i = e + 3;
    } else if (src.startsWith("</", i)) {
      XML_END.lastIndex = i;
      const m = XML_END.exec(src);
      if (!m || !stack.length || stack[stack.length - 1].raw !== m[1]) throw new ValueError("mismatched tag");
      stack.pop();
      i = XML_END.lastIndex;
    } else {
      XML_START.lastIndex = i;
      const m = XML_START.exec(src);
      if (!m) throw new ValueError("not well-formed");
      if (!stack.length && root) throw new ValueError("junk after document element");
      const colon = m[1].indexOf(":");
      const el = new XmlElement(colon >= 0 ? m[1].slice(colon + 1) : m[1]);
      el.raw = m[1];
      if (m[2]) xmlEntities(m[2]);
      if (stack.length) stack[stack.length - 1].children.push(el);
      else root = el;
      if (!m[3]) stack.push(el);
      i = XML_START.lastIndex;
    }
  }
  if (!root || stack.length) throw new ValueError("no element found");
  return root;
}

function parseXml(body) {
  if (!asciiStrip(body.toString("latin1"))) throw malformed();
  if (body.includes("<!DOCTYPE") || body.includes("<!ENTITY")) throw malformed();
  try {
    return parseXmlText(UTF8_STRICT.decode(body));
  } catch {
    throw malformed();
  }
}

/** ElementTree's findtext with Python's strip: the default when the element or its text is missing. */
function text(el, pathText, def = "") {
  if (!el) return def;
  const found = el.find(pathText);
  return found && found.text !== null ? pyStrip(found.text) : def;
}

function splitQuery(rawQuery) {
  const pairs = [];
  for (const part of rawQuery.split("&")) {
    if (!part) continue;
    const at = part.indexOf("=");
    pairs.push(at < 0 ? [unquote(part), ""] : [unquote(part.slice(0, at)), unquote(part.slice(at + 1))]);
  }
  return pairs;
}

module.exports = {
  x, log, quote, UTF8, UTF8_STRICT, unquote, doc, epoch, now3, iso, httpDate, amzStamp, parseTime, text, esc,
  stripDecl, urlEnc, ownerXml, parseXml, splitQuery,
};
