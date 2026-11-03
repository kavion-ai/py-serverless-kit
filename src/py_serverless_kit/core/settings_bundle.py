"""Move a project's local settings to another machine: one passphrase-encrypted file.

``.pskit`` stays out of git, so a fresh clone has no saved servers, clusters, on-prem services or SSH logins. An
export packs them into one ``.pskit-settings`` file; an import on the other machine writes them back:

* ``.pskit/onprem-servers.json``, ``onprem-clusters.json``, ``onprem-balancers.json``, ``onprem-services.json``
  (including service passwords and tokens);
* ``.pskit/ssh/`` (SSH passwords typed in the studio);
* SSH private keys the saved servers and services point to, also outside the project (``~/.ssh/edge.pem``):
  copied into ``.pskit/ssh/keys/`` on import, and the settings point there;
* where each on-prem stage was last deployed (``.pskit/onprem-<stage>/onprem_deployed.json``, ``deployment.json``),
  so ``pskit logs``, ``test``, ``info`` and the studio reach it right away;
* the studio's saved test events, and env files named by ``env_file`` in ``pskit.yml`` (when inside the project).

Paths inside the project are stored relative to it, so the project can live in another folder (or OS) there.
Terraform state is not included: on-prem deploys do not need it, and a cloud stage's state belongs in a remote
backend.

The file holds secrets, so it is always encrypted: scrypt (N=2^15, r=8) derives two keys from the passphrase; the
payload is zlib-compressed, XORed with an HMAC-SHA256 counter-mode keystream and authenticated with HMAC-SHA256
over the header and ciphertext (encrypt-then-MAC). A wrong passphrase or a changed file is refused before anything
is written. Standard library only.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
import zlib
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

FORMAT = "pskit-settings"
VERSION = 1
SUFFIX = ".pskit-settings"
ROOT_MARK = "${PSKIT_ROOT}"
KEYS_DIR = Path(".pskit") / "ssh" / "keys"
BACKUP_DIR = Path(".pskit") / "backups"
MIN_PASSPHRASE = 8
# Stores merged entry by entry on import (top-level maps of name -> entry); other files are replaced whole.
STORES = ("onprem-servers.json", "onprem-clusters.json", "onprem-balancers.json", "onprem-services.json")
# Keys whose value is an SSH key / known_hosts file: its content travels in the export.
_KEY_FIELDS = re.compile(r"^(identity_file|identity|pem|key_file|private_key|known_hosts|password_file)$")
_SCRYPT = {"n": 2**15, "r": 8, "p": 1}
_MAX_FILE = 5 * 1024 * 1024  # a settings file is small; anything bigger is skipped with a warning


class SettingsError(ValueError):
    pass


# ----------------------------------------------------------------------------------------------- collect
def _pskit(root: Path) -> Path:
    return Path(root) / ".pskit"


def _files(root: Path, env_files: Iterable[str] = (), *, config: bool = False) -> List[Path]:
    """Every settings file of the project that exists, as paths under ``root``. ``config``: also the project's
    configuration (``pskit.yml``), so the other machine gets the functions and resources too."""
    work = _pskit(root)
    found = [work / name for name in STORES]
    if config:
        from ..config.loader import DEFAULT_FILES

        found += [Path(root) / name for name in DEFAULT_FILES]
    ssh = work / "ssh"
    if ssh.is_dir():
        found += [p for p in sorted(ssh.rglob("*")) if p.is_file()]
    if work.is_dir():
        for stage in sorted(work.glob("onprem-*")):
            if stage.is_dir():
                found += [stage / "onprem_deployed.json", stage / "deployment.json"]
    found.append(work / "studio" / "test-events.json")
    base = Path(root).resolve()
    for name in env_files:
        path = (Path(root) / name).resolve()
        try:
            path.relative_to(base)
        except ValueError:
            continue  # outside the project: not ours to carry
        found.append(path)
    seen = set()
    out = []
    for path in found:
        if path.is_file() and path.resolve() not in seen:
            seen.add(path.resolve())
            out.append(path)
    return out


def env_files_of(raw: Any) -> List[str]:
    """``env_file`` values anywhere in a ``pskit.yml`` (``provider.options``, ``providers:``, ``stages:``)."""
    out: List[str] = []
    if isinstance(raw, dict):
        for key, value in raw.items():
            if key == "env_file" and isinstance(value, str) and value.strip() and "${" not in value:
                out.append(value.strip())
            else:
                out += env_files_of(value)
    elif isinstance(raw, list):
        for value in raw:
            out += env_files_of(value)
    return sorted(set(out))


def _norm(path: str) -> str:
    return os.path.normcase(os.path.normpath(path))


def _relative(value: str, root: str) -> Optional[str]:
    """``value`` as ``${PSKIT_ROOT}/a/b`` when it is a path inside ``root``, else None."""
    if not value or len(value) > 4096 or "\n" in value:
        return None
    try:
        if not os.path.isabs(value):
            return None
        norm, base = _norm(value), _norm(root)
    except (TypeError, ValueError):
        return None
    if norm == base:
        return ROOT_MARK
    if norm.startswith(base + os.sep):
        rest = os.path.normpath(value)[len(os.path.normpath(root)) + 1:]
        return ROOT_MARK + "/" + rest.replace("\\", "/")
    return None


class _Packer:
    """Rewrites paths in the settings JSON and collects the key files they point to."""

    def __init__(self, root: Path) -> None:
        self.root = str(Path(root).resolve())
        self.keys: Dict[str, Dict[str, str]] = {}  # stored name -> {source, b64}
        self.by_source: Dict[str, str] = {}
        self.warnings: List[str] = []

    def walk(self, value: Any, key: str = "") -> Any:
        if isinstance(value, dict):
            return {k: self.walk(v, str(k)) for k, v in value.items()}
        if isinstance(value, list):
            return [self.walk(v, key) for v in value]
        if not isinstance(value, str):
            return value
        inside = _relative(value, self.root)
        if inside is not None:
            return inside
        if _KEY_FIELDS.match(key) and value and value not in ("accept-new", "yes", "no", "off", "strict"):
            return self.key_file(value)
        return value

    def key_file(self, value: str) -> str:
        path = Path(os.path.expanduser(value))
        if not path.is_absolute() or not path.is_file():
            if path.is_absolute():
                self.warnings.append(f"{value}: not found on this machine, the import keeps the path as it is")
            return value
        source = _norm(str(path))
        if source not in self.by_source:
            data = path.read_bytes()
            if len(data) > 1024 * 1024:
                self.warnings.append(f"{value}: larger than 1 MB, not an SSH key; the path is kept as it is")
                return value
            stem = re.sub(r"[^A-Za-z0-9._-]+", "_", path.name)[:60] or "key"
            name = f"{stem}-{hashlib.sha256(source.encode('utf-8')).hexdigest()[:8]}"
            self.by_source[source] = name
            self.keys[name] = {"source": value, "b64": base64.b64encode(data).decode("ascii")}
        return f"{ROOT_MARK}/{KEYS_DIR.as_posix()}/{self.by_source[source]}"


def collect(root: Path, *, env_files: Iterable[str] = (), pskit_version: str = "",
            config: bool = False) -> Dict[str, Any]:
    """The plain payload of an export (what :func:`encrypt` locks)."""
    packer = _Packer(root)
    base = Path(root).resolve()
    files: Dict[str, Dict[str, str]] = {}
    for path in _files(root, env_files, config=config):
        rel = path.resolve().relative_to(base).as_posix()
        if path.stat().st_size > _MAX_FILE:
            packer.warnings.append(f"{rel}: larger than {_MAX_FILE // 1024 // 1024} MB, left out")
            continue
        data = path.read_bytes()
        if rel.endswith(".json"):
            try:
                doc = json.loads(data.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                files[rel] = {"b64": base64.b64encode(data).decode("ascii")}
                continue
            files[rel] = {"json": json.dumps(packer.walk(doc), sort_keys=True)}
        else:
            files[rel] = {"b64": base64.b64encode(data).decode("ascii")}
    return {
        "format": FORMAT,
        "version": VERSION,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "pskit_version": pskit_version,
        "source_root": str(base),
        "files": files,
        "keys": packer.keys,
        "warnings": packer.warnings,
    }


# ----------------------------------------------------------------------------------------------- crypto
def _derive(passphrase: str, salt: bytes, params: Dict[str, int]) -> Tuple[bytes, bytes]:
    n, r, p = int(params["n"]), int(params["r"]), int(params["p"])
    if not (2**10 <= n <= 2**20 and 1 <= r <= 32 and 1 <= p <= 16):
        raise SettingsError("the settings file has unsupported key parameters")
    if not hasattr(hashlib, "scrypt"):  # pragma: no cover - Python built without OpenSSL scrypt
        raise SettingsError("this Python has no hashlib.scrypt (it needs OpenSSL 1.1+); use another Python")
    key = hashlib.scrypt(passphrase.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=256 * 1024 * 1024, dklen=64)
    return key[:32], key[32:]


def _keystream_xor(key: bytes, nonce: bytes, data: bytes) -> bytes:
    pad = b"".join(hmac.new(key, nonce + i.to_bytes(8, "big"), hashlib.sha256).digest()
                   for i in range((len(data) + 31) // 32))[:len(data)]
    return (int.from_bytes(data, "big") ^ int.from_bytes(pad, "big")).to_bytes(len(data), "big")


def _header_bytes(header: Dict[str, Any]) -> bytes:
    return json.dumps(header, sort_keys=True, separators=(",", ":")).encode("utf-8")


def check_passphrase(passphrase: str) -> None:
    if not isinstance(passphrase, str) or len(passphrase) < MIN_PASSPHRASE:
        raise SettingsError(f"the passphrase must have at least {MIN_PASSPHRASE} characters")


def encrypt(payload: Dict[str, Any], passphrase: str) -> str:
    """The ``.pskit-settings`` file text: a small JSON header plus the encrypted, authenticated payload."""
    check_passphrase(passphrase)
    salt, nonce = os.urandom(16), os.urandom(16)
    header = {
        "format": FORMAT, "version": VERSION, "created_at": payload.get("created_at"),
        "pskit_version": payload.get("pskit_version"), "kdf": "scrypt", **_SCRYPT,
        "salt": base64.b64encode(salt).decode("ascii"), "nonce": base64.b64encode(nonce).decode("ascii"),
        "cipher": "hmac-sha256-ctr", "mac": "hmac-sha256",
    }
    enc_key, mac_key = _derive(passphrase, salt, _SCRYPT)
    body = zlib.compress(json.dumps(payload, sort_keys=True).encode("utf-8"), 9)
    cipher = _keystream_xor(enc_key, nonce, body)
    tag = hmac.new(mac_key, _header_bytes(header) + cipher, hashlib.sha256).digest()
    doc = {**header, "ciphertext": base64.b64encode(cipher).decode("ascii"),
           "tag": base64.b64encode(tag).decode("ascii")}
    return json.dumps(doc, indent=1) + "\n"


def decrypt(text: str, passphrase: str) -> Dict[str, Any]:
    try:
        doc = json.loads(text)
    except ValueError:
        raise SettingsError("not a pskit settings file (it is not JSON)") from None
    if not isinstance(doc, dict) or doc.get("format") != FORMAT:
        raise SettingsError("not a pskit settings file")
    if int(doc.get("version") or 0) > VERSION:
        raise SettingsError(f"this settings file needs a newer pskit (format {doc.get('version')}); upgrade pskit")
    try:
        header = {k: v for k, v in doc.items() if k not in ("ciphertext", "tag")}
        salt = base64.b64decode(str(doc["salt"]))
        nonce = base64.b64decode(str(doc["nonce"]))
        cipher = base64.b64decode(str(doc["ciphertext"]))
        tag = base64.b64decode(str(doc["tag"]))
        enc_key, mac_key = _derive(str(passphrase or ""), salt, {k: doc[k] for k in ("n", "r", "p")})
    except (KeyError, ValueError, TypeError):
        raise SettingsError("the settings file is damaged") from None
    expected = hmac.new(mac_key, _header_bytes(header) + cipher, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, tag):
        raise SettingsError("wrong passphrase, or the settings file was changed")
    try:
        payload = json.loads(zlib.decompress(_keystream_xor(enc_key, nonce, cipher)).decode("utf-8"))
    except (zlib.error, UnicodeDecodeError, ValueError):
        raise SettingsError("the settings file is damaged") from None
    if not isinstance(payload, dict) or not isinstance(payload.get("files"), dict):
        raise SettingsError("the settings file is damaged")
    return payload


def export_settings(root: Path, passphrase: str, *, env_files: Iterable[str] = (),
                    pskit_version: str = "", config: bool = False) -> Tuple[str, Dict[str, Any]]:
    """``(file text, summary)``. The summary lists what is inside (no secrets). ``config``: include pskit.yml."""
    check_passphrase(passphrase)
    payload = collect(root, env_files=env_files, pskit_version=pskit_version, config=config)
    return encrypt(payload, passphrase), summarize(payload)


# ----------------------------------------------------------------------------------------------- import
def _unpack(value: Any, root: Path) -> Any:
    if isinstance(value, dict):
        return {k: _unpack(v, root) for k, v in value.items()}
    if isinstance(value, list):
        return [_unpack(v, root) for v in value]
    if isinstance(value, str) and (value == ROOT_MARK or value.startswith(ROOT_MARK + "/")):
        rest = value[len(ROOT_MARK) + 1:]
        return str(Path(root).resolve().joinpath(*rest.split("/"))) if rest else str(Path(root).resolve())
    return value


def _safe_rel(rel: str) -> Path:
    """A relative path inside the project; refuses absolute paths and ``..`` (a crafted file cannot escape)."""
    parts = rel.replace("\\", "/").split("/")
    if not rel or rel.startswith("/") or re.match(r"^[A-Za-z]:", rel) or any(p in ("", ".", "..") for p in parts):
        raise SettingsError(f"the settings file has an unsafe path: {rel!r}")
    return Path(*parts)


def _entries(doc: Any) -> Dict[str, Dict[str, Any]]:
    """The name -> entry maps of a store (``{"servers": {...}}`` -> ``{"servers": {...}}``)."""
    return {k: v for k, v in (doc or {}).items() if isinstance(v, dict)} if isinstance(doc, dict) else {}


def summarize(payload: Dict[str, Any]) -> Dict[str, Any]:
    """What a payload holds, for the export result and the import preview (names only, no secrets)."""
    out: Dict[str, Any] = {"created_at": payload.get("created_at"), "pskit_version": payload.get("pskit_version"),
                           "source_root": payload.get("source_root"), "files": sorted(payload.get("files") or {}),
                           "keys": sorted((v.get("source") for v in (payload.get("keys") or {}).values()), key=str),
                           "warnings": list(payload.get("warnings") or [])}
    for rel, item in (payload.get("files") or {}).items():
        name = rel.rsplit("/", 1)[-1]
        if name in STORES and "json" in item:
            for group, entries in _entries(json.loads(item["json"])).items():
                out.setdefault("entries", {})[f"{name[:-5]}.{group}"] = sorted(entries)
    return out


def preview(root: Path, payload: Dict[str, Any], *, replace: bool = False) -> Dict[str, Any]:
    """What an import would change: files added / replaced, and store entries added / replaced / kept."""
    files = []
    stores: Dict[str, Dict[str, List[str]]] = {}
    for rel, item in sorted((payload.get("files") or {}).items()):
        path = Path(root) / _safe_rel(rel)
        name = rel.rsplit("/", 1)[-1]
        if rel.startswith(".pskit/") and name in STORES and "json" in item:
            incoming = _entries(json.loads(item["json"]))
            current = _entries(_read_json(path))
            for group in sorted(set(incoming) | set(current)):
                new, old = incoming.get(group, {}), current.get(group, {})
                stores[f"{name[:-5]}.{group}"] = {
                    "add": sorted(set(new) - set(old)), "replace": sorted(set(new) & set(old)),
                    ("remove" if replace else "keep"): sorted(set(old) - set(new)),
                }
        files.append({"path": rel, "action": "replace" if path.exists() else "add"})
    keys = [{"source": v.get("source"), "path": (KEYS_DIR / name).as_posix()}
            for name, v in sorted((payload.get("keys") or {}).items())]
    return {**summarize(payload), "mode": "replace" if replace else "merge", "changes": files, "stores": stores,
            "key_files": keys}


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None


def _secret(rel: str) -> bool:
    return rel.startswith(".pskit/ssh/") or rel.rsplit("/", 1)[-1] in STORES


def _write(path: Path, data: bytes, *, secret: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".pskit-tmp")
    tmp.write_bytes(data)
    if secret:
        try:
            os.chmod(tmp, 0o600)
        except OSError:  # pragma: no cover - Windows ACLs
            pass
    os.replace(tmp, path)


def backup(root: Path) -> Optional[Path]:
    """The current settings as an unencrypted payload in ``.pskit/backups/`` (they are on this disk already)."""
    payload = collect(root, config=True)  # an import may replace pskit.yml too
    if not payload["files"]:
        return None
    path = Path(root) / BACKUP_DIR / f"settings-{time.strftime('%Y%m%d-%H%M%S')}.json"
    _write(path, (json.dumps(payload, indent=1, sort_keys=True) + "\n").encode("utf-8"), secret=True)
    return path


def import_settings(root: Path, payload: Dict[str, Any], *, replace: bool = False) -> Dict[str, Any]:
    """Write a decrypted payload into ``root``. Stores merge entry by entry (imported entries win; ``replace``
    drops the ones it does not have); other files are replaced. The current settings are backed up first."""
    plan = preview(root, payload, replace=replace)  # also checks every path before anything is written
    saved = backup(root)
    root = Path(root)
    for name, item in sorted((payload.get("keys") or {}).items()):
        _write(root / KEYS_DIR / _safe_rel(name), base64.b64decode(str(item["b64"])), secret=True)
    written = []
    for rel, item in sorted((payload.get("files") or {}).items()):
        path = root / _safe_rel(rel)
        if "json" in item:
            doc = _unpack(json.loads(item["json"]), root)
            name = rel.rsplit("/", 1)[-1]
            if name in STORES and not replace and rel.startswith(".pskit/"):
                current = _read_json(path)
                if isinstance(current, dict) and isinstance(doc, dict):
                    merged = dict(current)
                    for key, value in doc.items():
                        if isinstance(value, dict) and isinstance(current.get(key), dict):
                            merged[key] = {**current[key], **value}
                        else:
                            merged[key] = value
                    doc = merged
            data = (json.dumps(doc, indent=2, sort_keys=True) + "\n").encode("utf-8")
        else:
            data = base64.b64decode(str(item["b64"]))
        _write(path, data, secret=_secret(rel))
        written.append(rel)
    return {**plan, "written": written, "backup": str(saved) if saved else None}
