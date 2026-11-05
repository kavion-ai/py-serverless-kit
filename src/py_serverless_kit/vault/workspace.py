"""Plaintext working files <-> sealed vault files, and login sessions.

While someone is logged in, protected files sit at their normal gitignored paths, so Terraform, SSH and the rest of
pskit work unchanged. Every change is sealed into ``.pskit-vault/`` right away. When the last session ends, the
plaintext copies are removed.

``.pskit/.vault/`` (never committed) holds the manifest of what is unpacked, and the sessions. A session file holds
key material for as long as the login lasts: it is as sensitive as the plaintext files next to it.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import secrets
import stat
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

from . import audit, crypto, permissions
from .errors import VaultError
from .store import Identity, Vault, atomic_write

STATE_DIR = Path(".pskit") / ".vault"
MANIFEST = "manifest.json"
MAX_FILE = 32 * 1024 * 1024
CONFLICT_SUFFIX = ".vault-conflict"
SESSION_SECONDS = 12 * 3600
STALE_STUDIO_SECONDS = 60
GITIGNORE_LINES = (".pskit/", ".env", ".env.*", "!.env.example", "*" + CONFLICT_SUFFIX)
_ENV_NOT_SECRET = (".example", ".sample", ".template", CONFLICT_SUFFIX)

_AREA_FILES: Dict[str, List[str]] = {
    "servers": [".pskit/onprem-servers.json", ".pskit/ssh/**", ".pskit/terminal/known_hosts"],
    "services": [".pskit/onprem-services.json"],
    "clusters": [".pskit/onprem-clusters.json", ".pskit/onprem-balancers.json"],
    "deployments": [
        ".pskit/*/deployment.json", ".pskit/*/onprem_deployed.json", ".pskit/*/admin-token", ".pskit/*/peer-token",
        ".pskit/*/terraform.tfstate",
    ],
    "studio": [".pskit/studio/test-events.json", ".pskit/studio/hana.json"],
}
_LOCKS: Dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


def is_env_file(rel: str) -> bool:
    name = rel.replace("\\", "/").rstrip("/. ").rsplit("/", 1)[-1].split(":")[0].lower()
    return (name == ".env" or name.startswith(".env.")) and not name.endswith(_ENV_NOT_SECRET)


class _FileLock:
    """Between processes (a CLI command and the studio) as well as threads."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.path = root / STATE_DIR / "lock"
        with _LOCKS_GUARD:
            self.thread_lock = _LOCKS.setdefault(str(root), threading.RLock())

    def __enter__(self) -> _FileLock:
        self.thread_lock.acquire()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.time() + 30
        while True:
            try:
                os.close(os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                return self
            except (FileExistsError, PermissionError):
                try:
                    if time.time() - self.path.stat().st_mtime > 60:  # left by a killed process
                        self.path.unlink()
                        continue
                except OSError:
                    continue
                if time.time() > deadline:
                    self.thread_lock.release()
                    raise VaultError("the vault is busy (another pskit is saving); try again", 409, "busy") from None
                time.sleep(0.05)

    def __exit__(self, *_exc: Any) -> None:
        try:
            self.path.unlink()
        except OSError:
            pass
        self.thread_lock.release()


# ------------------------------------------------------------------------------- which files
def declared_env_files(root: Path) -> Set[str]:
    """``env_file`` in pskit.yml can have any name, like config/prod.secrets."""
    try:
        import yaml

        from ..config.loader import DEFAULT_FILES
        from ..core.settings_bundle import env_files_of

        for candidate in DEFAULT_FILES:
            path = root / candidate
            if path.is_file():
                names = set()
                for name in env_files_of(yaml.safe_load(path.read_text("utf-8"))):
                    try:
                        names.add((root / name).resolve().relative_to(root).as_posix())
                    except ValueError:
                        pass  # outside the project: not ours to carry
                return names
    except Exception:  # noqa: BLE001, S110 - a broken pskit.yml must not stop sealing the rest
        pass
    return set()


def scan_area(root: Path, area: str) -> List[str]:
    """Relative POSIX paths of the protected files of an area that exist now."""
    found: Set[str] = set()
    if area == "env":
        found.update(p.name for p in root.glob(".env*") if p.is_file() and is_env_file(p.name))
        found.update(rel for rel in declared_env_files(root) if (root / rel).is_file())
    for pattern in _AREA_FILES.get(area, []):
        if pattern.endswith("/**"):
            base = root / pattern[:-3]
            if base.is_dir():
                found.update(p.relative_to(root).as_posix() for p in base.rglob("*") if p.is_file())
        elif "*" in pattern:
            found.update(p.relative_to(root).as_posix() for p in root.glob(pattern) if p.is_file())
        elif (root / pattern).is_file():
            found.add(pattern)
    return sorted(p for p in found if not p.endswith(CONFLICT_SUFFIX) and not Path(p).name.endswith(".tmp"))


def area_of(rel: str) -> Optional[str]:
    if is_env_file(rel):
        return "env"
    for area, patterns in _AREA_FILES.items():
        for pattern in patterns:
            if fnmatch.fnmatch(rel, pattern.replace("/**", "/*")):
                return area
    return None


def _safe_target(root: Path, rel: str) -> Path:
    """A vault file names its own path; it must not be able to write outside the project or over its code."""
    target = (root / rel).resolve()
    try:
        inside = target.relative_to(root).as_posix()
    except ValueError:
        raise VaultError(f"the vault names a path outside the project: {rel}", 500, "damaged") from None
    if area_of(inside) is None and inside not in declared_env_files(root):
        raise VaultError(f"the vault names a path it may not write: {rel}", 500, "damaged")
    return target


# ------------------------------------------------------------------------------- manifest
def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_manifest(root: Path) -> Dict[str, Dict[str, str]]:
    try:
        doc = json.loads((root / STATE_DIR / MANIFEST).read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def _save_manifest(root: Path, doc: Dict[str, Dict[str, str]]) -> None:
    atomic_write(root / STATE_DIR / MANIFEST, (json.dumps(doc, indent=1, sort_keys=True) + "\n").encode("utf-8"))


def _write_private(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    fd = os.open(str(tmp), os.O_CREAT | os.O_WRONLY | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
    os.replace(tmp, path)
    if sys.platform == "win32" and ".pskit/ssh/" in path.as_posix():  # OpenSSH refuses a key others can read
        from ..core.ssh_keys import restrict_to_owner

        restrict_to_owner(path)


# ------------------------------------------------------------------------------- seal / unseal
def seal(vault: Vault, identity: Identity) -> Dict[str, List[str]]:
    """Encrypt every protected file that changed, into the areas this account may write."""
    root = vault.root
    out: Dict[str, List[str]] = {"sealed": [], "removed": [], "skipped": []}
    with _FileLock(root):
        doc = vault.accounts(identity.master)
        user = doc["users"].get(identity.username)
        if not isinstance(user, dict):
            return out
        keys = vault.area_keys(identity)
        writable = permissions.writable_areas(user)
        manifest = _load_manifest(root)
        for area, key in keys.items():
            generation = int(doc["areas"][area]["generation"])
            present = set(scan_area(root, area))
            for rel in sorted(present):
                try:
                    data = (root / rel).read_bytes()
                except OSError:
                    continue
                digest = _sha(data)
                known = manifest.get(rel)
                if known and known.get("sha") == digest:
                    continue
                if area not in writable or len(data) > MAX_FILE:
                    out["skipped"].append(rel)
                    continue
                vault.seal_file(area, key, generation, rel, data)
                manifest[rel] = {"area": area, "sha": digest}
                out["sealed"].append(rel)
            for rel, known in list(manifest.items()):
                if known.get("area") == area and rel not in present and area in writable:
                    vault.remove_file(area, key, rel)
                    del manifest[rel]
                    out["removed"].append(rel)
        _save_manifest(root, manifest)
    return out


def unseal(vault: Vault, identity: Identity) -> Dict[str, List[str]]:
    """Write the areas this account holds to their working paths. Local edits are never lost: when both the local file
    and the vault changed (a ``git pull``), the vault wins and the local one is kept as ``*.vault-conflict``."""
    root = vault.root
    out: Dict[str, List[str]] = {"written": [], "removed": [], "conflicts": [], "kept": []}
    with _FileLock(root):
        doc = vault.accounts(identity.master)
        keys = vault.area_keys(identity)
        manifest = _load_manifest(root)
        for area, key in keys.items():
            generation = int(doc["areas"][area]["generation"])
            seen: Set[str] = set()
            for rel, data in vault.read_area(area, key, generation):
                target = _safe_target(root, rel)
                seen.add(rel)
                sealed_sha = _sha(data)
                known = manifest.get(rel) or {}
                local = target.read_bytes() if target.is_file() else None
                local_sha = _sha(local) if local is not None else None
                if local_sha == sealed_sha:
                    manifest[rel] = {"area": area, "sha": sealed_sha}
                    continue
                if local is not None and local_sha != known.get("sha"):
                    if known.get("sha") == sealed_sha:
                        out["kept"].append(rel)  # only the local file changed: the next seal takes it
                        continue
                    _write_private(target.with_name(target.name + CONFLICT_SUFFIX), local)
                    out["conflicts"].append(rel)
                _write_private(target, data)
                manifest[rel] = {"area": area, "sha": sealed_sha}
                out["written"].append(rel)
            for rel, known in list(manifest.items()):  # removed from the vault by someone else
                if known.get("area") == area and rel not in seen:
                    target = _safe_target(root, rel)
                    if target.is_file() and _sha(target.read_bytes()) == known.get("sha"):
                        target.unlink()
                        out["removed"].append(rel)
                    if not target.is_file():
                        del manifest[rel]
        _save_manifest(root, manifest)
    return out


def wipe(root: Path, keep_areas: Iterable[str] = ()) -> List[str]:
    """Remove the plaintext of areas nobody is logged in to. A file with unsealed edits stays: deleting it loses them."""
    keep = set(keep_areas)
    removed = []
    with _FileLock(root):
        manifest = _load_manifest(root)
        for rel, known in list(manifest.items()):
            if known.get("area") in keep:
                continue
            target = root / rel
            if not target.is_file():
                del manifest[rel]
            elif _sha(target.read_bytes()) == known.get("sha"):
                target.unlink()
                removed.append(rel)
                del manifest[rel]
        _save_manifest(root, manifest)
    return removed


# ------------------------------------------------------------------------------- git
def ensure_gitignore(root: Path) -> List[str]:
    """Plaintext must never reach git; the vault itself stays committable."""
    path = root / ".gitignore"
    text = path.read_text("utf-8") if path.is_file() else ""
    have = {line.strip() for line in text.splitlines()}
    added = [line for line in GITIGNORE_LINES if line not in have]
    if added:
        head = text if not text or text.endswith("\n") else text + "\n"
        block = "# py-serverless-kit: plaintext stays out of git; .pskit-vault/ (encrypted) is committed\n"
        path.write_bytes((head + block + "\n".join(added) + "\n").encode("utf-8"))
    return added


def tracked_plaintext(root: Path) -> List[str]:
    """Protected files git already tracks: ignoring does not untrack them, so their plaintext is still pushed."""
    try:
        result = subprocess.run(  # noqa: S603 - fixed argv
            ["git", "ls-files"], cwd=str(root), capture_output=True, text=True, timeout=20, check=False,  # noqa: S607
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line.startswith(".pskit/") or area_of(line) == "env"]


# ------------------------------------------------------------------------------- sessions
@dataclass
class Session:
    id: str
    identity: Identity
    source: str
    expires: float

    @property
    def username(self) -> str:
        return self.identity.username


def _sessions(root: Path) -> Path:
    return root / STATE_DIR / "sessions"


def _session_path(root: Path, session_id: str) -> Path:
    return _sessions(root) / f"{hashlib.sha256(session_id.encode('utf-8')).hexdigest()}.json"


def write_session(root: Path, session: Session) -> None:
    doc = {
        "id": session.id, "user": session.username, "source": session.source, "expires": session.expires,
        "master": crypto.b64(session.identity.master), "private": crypto.b64(session.identity.private),
    }
    _write_private(_session_path(root, session.id), json.dumps(doc).encode("utf-8"))


def _parse_session(path: Path) -> Optional[Session]:
    try:
        doc = json.loads(path.read_text("utf-8"))
        identity = Identity(str(doc["user"]), crypto.unb64(doc["master"]), crypto.unb64(doc["private"]))
        return Session(str(doc["id"]), identity, str(doc["source"]), float(doc["expires"]))
    except (OSError, ValueError, KeyError, TypeError, VaultError):
        return None


def load_session(root: Path, session_id: str) -> Optional[Session]:
    return _parse_session(_session_path(root, session_id))


def touch_session(root: Path, session_id: str) -> None:
    try:
        os.utime(_session_path(root, session_id))
    except OSError:
        pass


def login(
    vault: Vault, master: bytes, username: str, password: str, source: str, ttl: int = SESSION_SECONDS,
    session_id: Optional[str] = None,
) -> Session:
    identity = vault.authenticate(master, username, password)
    forget_saved_master(vault)  # this person just proved they have the key, so the old copy can safely go
    session = Session(session_id or secrets.token_urlsafe(32), identity, source, time.time() + ttl)
    write_session(vault.root, session)
    return session


def open_workspace(vault: Vault, session: Session) -> Dict[str, List[str]]:
    """Unseal first: what a crash left behind then counts as a local edit and is merged, not overwritten."""
    result = unseal(vault, session.identity)
    seal(vault, session.identity)
    return result


def _held_areas(vault: Vault, sessions: Iterable[Session]) -> Set[str]:
    held: Set[str] = set()
    for session in sessions:
        try:
            held |= set(vault.area_keys(session.identity))
        except VaultError:
            pass
    return held


def close_session(vault: Vault, session: Session, *, remove_plaintext: bool = True) -> List[str]:
    try:
        seal(vault, session.identity)
    except VaultError:
        pass  # e.g. the master key was rotated: what is unsealed stays, the next login merges it
    try:
        _session_path(vault.root, session.id).unlink()
    except OSError:
        pass
    if not remove_plaintext:
        return []
    return wipe(vault.root, _held_areas(vault, live_sessions(vault)))


def live_sessions(vault: Vault) -> List[Session]:
    """Valid sessions. Expired ones, and those of a studio that died, are closed here."""
    folder = _sessions(vault.root)
    if not folder.is_dir():
        return []
    live: List[Session] = []
    ended: List[Session] = []
    now = time.time()
    for path in sorted(folder.glob("*.json")):
        session = _parse_session(path)
        if session is None:
            continue
        stale = session.source == "studio" and now - path.stat().st_mtime > STALE_STUDIO_SECONDS
        (ended if session.expires < now or stale else live).append(session)
    for session in ended:
        close_session(vault, session, remove_plaintext=False)
    if ended:
        wipe(vault.root, _held_areas(vault, live))
    return live


def rotate_recovery(vault: Vault, identity: Identity) -> str:
    """Under the lock, so the background seal cannot write files with the keys being replaced."""
    with _FileLock(vault.root):
        return vault.rotate_recovery(identity)


# ------------------------------------------------------------------------------- saved master key (no longer used)
def saved_master_path(vault: Vault) -> Path:
    """Where earlier versions kept the master key in plaintext. It is never read: a key on disk next to the vault would
    leave only the password protecting the data."""
    return Path(os.environ.get("PSKIT_HOME") or Path.home() / ".pskit") / "vault-keys" / vault.id


def forget_saved_master(vault: Vault) -> None:
    try:
        saved_master_path(vault).unlink()
    except OSError:
        pass


def log(
    vault: Vault, session: Session, action: str, target: str = "", outcome: str = "ok",
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """The audit log must not take a request down with it."""
    try:
        audit.record(vault, session.identity.master, session.username, session.source, action, target, outcome, details)
    except (VaultError, OSError):
        pass
