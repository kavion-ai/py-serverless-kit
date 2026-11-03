"use strict";
/**
 * Route matcher (port of runtime/routing.py). Patterns use `{name}` for one
 * segment and `{name+}` for a greedy tail.
 */

function splitPath(path) {
  return String(path).split("?")[0].split("/").filter(Boolean);
}

function isParam(seg) {
  return seg.startsWith("{") && seg.endsWith("}");
}

function matchSegments(pattern, parts) {
  const params = {};
  for (let i = 0; i < pattern.length; i++) {
    const seg = pattern[i];
    if (isParam(seg)) {
      const name = seg.slice(1, -1);
      if (name.endsWith("+")) {
        if (i !== pattern.length - 1 || i >= parts.length) return null;
        params[name.slice(0, -1)] = parts.slice(i).join("/");
        return params;
      }
      if (i >= parts.length) return null;
      params[name] = parts[i];
    } else if (i >= parts.length || seg !== parts[i]) {
      return null;
    }
  }
  return parts.length === pattern.length ? params : null;
}

/**
 * Path params if `path` matches `pattern`, else null. With `tolerant` (default)
 * a prefix the platform prepended (Azure `/api/...`) or leading static segments
 * the platform stripped (GCP `/fn-name/7` for `/users/{id}`) are accepted too.
 */
function matchPath(pattern, path, { tolerant = true } = {}) {
  const pat = splitPath(pattern);
  const parts = splitPath(path);
  const exact = matchSegments(pat, parts);
  if (exact !== null || !tolerant) return exact;
  if (pat.some((seg) => !isParam(seg))) {
    for (let drop = 1; drop < parts.length; drop++) {
      const got = matchSegments(pat, parts.slice(drop));
      if (got !== null) return got;
    }
  }
  let leadingStatic = 0;
  for (const seg of pat) {
    if (isParam(seg)) break;
    leadingStatic++;
  }
  if (leadingStatic) {
    const rest = pat.slice(leadingStatic);
    if (rest.length || !parts.length) return matchSegments(rest, parts);
  }
  return null;
}

function methodMatches(allowed, method) {
  const a = String(allowed).toUpperCase();
  return a === "ANY" || a === "*" || a === String(method).toUpperCase();
}

module.exports = { splitPath, matchPath, methodMatches };
