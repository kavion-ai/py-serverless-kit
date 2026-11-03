"""Tiny route matcher used where the provider has no API gateway in front of the
function (GCP, IBM, DigitalOcean, Cloudflare, ...) and by the local dev server.

Patterns use ``{name}`` for one segment and ``{name+}`` for a greedy tail,
the same syntax as AWS API Gateway, Azure Functions and the YAML config.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence


def split_path(path: str) -> List[str]:
    return [seg for seg in path.split("?")[0].split("/") if seg]


def _is_param(seg: str) -> bool:
    return seg.startswith("{") and seg.endswith("}")


def _match_segments(pattern: Sequence[str], parts: Sequence[str]) -> Optional[Dict[str, str]]:
    params: Dict[str, str] = {}
    for i, seg in enumerate(pattern):
        if _is_param(seg):
            name = seg[1:-1]
            if name.endswith("+"):
                if i != len(pattern) - 1 or i >= len(parts):
                    return None
                params[name[:-1]] = "/".join(parts[i:])
                return params
            if i >= len(parts):
                return None
            params[name] = parts[i]
        elif i >= len(parts) or seg != parts[i]:
            return None
    return params if len(parts) == len(pattern) else None


def match_path(pattern: str, path: str, *, tolerant: bool = True) -> Optional[Dict[str, str]]:
    """Return path params if ``path`` matches ``pattern`` else ``None``.

    With ``tolerant=True`` two platform quirks are accepted as well:

    * the platform *prepended* a fixed prefix (Azure ``/api/users/7``) - the
      whole pattern must then match the tail of the path;
    * the platform *stripped* the pattern's leading static segments (GCP serves
      ``/users/{id}`` at ``https://.../fn-name/7``) - the remaining
      pattern must then match the whole path.
    """
    pat = split_path(pattern)
    parts = split_path(path)
    exact = _match_segments(pat, parts)
    if exact is not None or not tolerant:
        return exact
    if any(not _is_param(seg) for seg in pat):
        for drop in range(1, len(parts)):
            got = _match_segments(pat, parts[drop:])
            if got is not None:
                return got
    leading_static = 0
    for seg in pat:
        if _is_param(seg):
            break
        leading_static += 1
    if leading_static:
        rest = pat[leading_static:]
        if rest or not parts:
            return _match_segments(rest, parts)
    return None


def method_matches(allowed: str, method: str) -> bool:
    allowed = allowed.upper()
    return allowed in ("ANY", "*") or allowed == method.upper()
