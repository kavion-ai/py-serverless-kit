"""Accounts in the studio: first-run admin, login, per-feature permissions, sealing and the audit log.

The session token printed at start still has to be on every call, so nothing else on this machine can win the race to
create the first admin. On top of it, each browser has its own ``x-pskit-session`` after login.
"""

from __future__ import annotations

import secrets
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..config.loader import DEFAULT_FILES
from ..vault import audit, crypto, permissions
from ..vault import workspace as ws
from ..vault.errors import VaultError
from ..vault.store import MASTER_PREFIX, Vault
from . import files
from . import project as project_file
from .project import StudioError

SWEEP_SECONDS = 3.0
MAX_FAILURES = 5
LOCK_SECONDS = 30.0


def open_mode_file(root: Any) -> Path:
    """In ``.pskit/``, so the choice stays on this computer and is not committed."""
    return Path(root) / ".pskit" / "studio" / "no-accounts"


def choose_no_accounts(root: Any) -> None:
    """One person, no login, nothing encrypted: the studio works as it did before accounts existed."""
    if Vault(root).exists():
        raise VaultError("this project has accounts, so it needs a login", 409, "exists")
    path = open_mode_file(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"chosen in pskit studio\n")


class _Throttle:
    """Slows down password guessing, and keeps login's memory-hungry key derivation to one at a time."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.one_at_a_time = threading.Semaphore(1)
        self.failures: Dict[str, Tuple[int, float]] = {}

    def check(self, key: str) -> None:
        with self.lock:
            count, until = self.failures.get(key, (0, 0.0))
        left = until - time.time()
        if count >= MAX_FAILURES and left > 0:
            raise StudioError(429, f"too many failed logins; try again in {int(left) + 1} seconds", code="locked")

    def failed(self, key: str) -> None:
        with self.lock:
            count = self.failures.get(key, (0, 0.0))[0] + 1
            delay = LOCK_SECONDS * (2 ** max(0, count - MAX_FAILURES))
            self.failures[key] = (count, time.time() + min(delay, 3600.0))

    def passed(self, key: str) -> None:
        with self.lock:
            self.failures.pop(key, None)


def _error(exc: VaultError) -> StudioError:
    return StudioError(exc.status, exc.message, **({"code": exc.code} if exc.code else {}))


class Auth:
    def __init__(self, root: Any, jobs_running: Optional[Callable[[], bool]] = None) -> None:
        self.vault = Vault(root)
        self.root = self.vault.root
        self.sessions: Dict[str, ws.Session] = {}
        self.throttle = _Throttle()
        self.jobs_running = jobs_running or (lambda: False)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._closing: List[ws.Session] = []
        self._setup_lock = threading.Lock()
        if self.vault.exists():
            try:
                ws.live_sessions(self.vault)  # seal and clean up after a studio that died
            except VaultError:
                pass

    # ------------------------------------------------------------------ background sealing
    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._sweep, name="pskit-vault-sweep", daemon=True)
            self._thread.start()

    def _sweep(self) -> None:
        while not self._stop.wait(SWEEP_SECONDS):
            try:
                self.sweep_once()
            except (VaultError, OSError):
                pass

    def sweep_once(self) -> None:
        """Catches what no request saved (a deploy's output, a watcher). Keeps sessions alive and ends expired ones."""
        for token, session in list(self.sessions.items()):
            if session.expires < time.time():
                self.sessions.pop(token, None)
                self._closing.append(session)
                ws.log(self.vault, session, "auth.expired")
                continue
            ws.touch_session(self.root, session.id)
            self._seal(session)
        if self._closing and not self.jobs_running():  # a running deploy still needs the plaintext
            closing, self._closing = self._closing, []
            for session in closing:
                ws.close_session(self.vault, session)

    def shutdown(self) -> None:
        self._stop.set()
        for session in [*self.sessions.values(), *self._closing]:
            ws.log(self.vault, session, "auth.logout", outcome="studio stopped")
            ws.close_session(self.vault, session)
        self.sessions.clear()
        self._closing = []

    def _seal(self, session: ws.Session) -> None:
        try:
            changed = ws.seal(self.vault, session.identity)
        except VaultError:
            return
        if changed["sealed"] or changed["removed"]:
            ws.log(self.vault, session, "vault.seal", details={
                "files": ", ".join(changed["sealed"] + changed["removed"])[:500],
            })

    # ------------------------------------------------------------------ gate
    def is_open(self) -> bool:
        """No accounts here. A vault always wins: nobody can turn off a team's login by choosing this."""
        return not self.vault.exists() and open_mode_file(self.root).is_file()

    def session_of(self, token: str) -> Optional[ws.Session]:
        session = self.sessions.get(token or "")
        if session is None or session.expires < time.time():
            return None
        return session

    def require(self, token: str) -> ws.Session:
        if not self.vault.exists():
            raise StudioError(401, "create the first admin account", code="setup")
        session = self.session_of(token)
        if session is None:
            raise StudioError(401, "please log in", code="login")
        return session

    def _user(self, session: ws.Session) -> Dict[str, Any]:
        try:
            return self.vault.user(session.identity)
        except VaultError as exc:
            self.sessions = {k: v for k, v in self.sessions.items() if v is not session}
            self._closing.append(session)
            raise StudioError(401, "your session ended; please log in again", code="login") from exc

    def _saved_config(self) -> Any:
        path = project_file.config_path(self.root)
        return project_file.parse_text(path.read_text("utf-8"))[0] if path is not None else {}

    def _is_config_file(self, path: str) -> bool:
        try:
            real = files.resolve(self.root, path, must_exist=False)
        except StudioError:
            return False  # the route refuses it too
        return real.relative_to(self.root).as_posix().lower().rstrip(". ") in {n.lower() for n in DEFAULT_FILES}

    def _content_needs(self, parts: List[str], body: Any, path: Optional[str]) -> Optional[Tuple[List[Any], List[str]]]:
        """Calls that change pskit.yml are judged by what they change. Saving it as a file counts the same, or the Code
        permission would get around the rest."""
        if parts == ["project"]:
            return permissions.project_needs(self._saved_config(), body.get("raw"))
        if parts == ["files"] and path and self._is_config_file(path):
            raw = project_file.parse_text(str(body.get("text") or ""))[0]
            return permissions.project_needs(self._saved_config(), raw)
        if parts == ["project", "init"] and self._saved_config():
            return permissions.project_needs(self._saved_config(), {})  # replacing the project deletes what it holds
        if len(parts) == 3 and parts[0] == "functions" and parts[2] == "split":
            return [("functions", "u")], [f"changed functions.{parts[1]}"]
        return None

    def authorize(
        self, session: ws.Session, method: str, parts: List[str], body: Any, path: Optional[str],
    ) -> Dict[str, Any]:
        """Raises when the account may not make this call. Returns what to add to its audit entry."""
        user = self._user(session)
        if user.get("must_change"):
            raise StudioError(403, "set a new password first", code="password_change")
        needed = permissions.studio_permission(method, parts)
        if parts[:1] == ["jobs"] and method == "GET":
            if not any(permissions.allowed(user, f, "r") for f in ("deploy", "test", "resources")):
                self._deny("jobs", "r")
            return {}
        if parts == ["jobs"] and method == "POST":
            needed = permissions.job_permission(str((body or {}).get("command") or ""))
        if parts == ["files"] and needed is not None and path and self._is_secret_file(path):
            needed = ("env", needed[1])
        if parts == ["project"] and method == "PUT":
            needed = None  # judged by what it changes
        if needed is not None and not permissions.allowed(user, *needed):
            self._deny(*needed)
        content = self._content_needs(parts, body, path) if method in ("PUT", "POST") else None
        if content is None:
            return {}
        for feature, action in content[0]:
            if not permissions.allowed(user, feature, action):
                self._deny(feature, action)
        return {"changes": ", ".join(content[1])[:500]} if content[1] else {}

    def _is_secret_file(self, path: str) -> bool:
        """Judged on where the path really leads, so `sub/../.env`, `.ENV` and symlinks do not get around it."""
        try:
            real = files.resolve(self.root, path, must_exist=False)
        except StudioError:
            return False  # the route refuses it too
        rel = real.relative_to(self.root).as_posix()
        return ws.is_env_file(rel) or rel in ws.declared_env_files(self.root)

    @staticmethod
    def _deny(feature: str, action: str) -> None:
        words = {"c": "create", "r": "read", "u": "update", "d": "delete"}
        raise StudioError(
            403, f"you do not have {words[action]} permission on {feature}", code="forbidden",
            feature=feature, action=action,
        )

    def visible_tree(self, session: ws.Session, entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Env files stay out of the tree for an account that may not read them."""
        if permissions.allowed(self._user(session), "env", "r"):
            return entries
        return [e for e in entries if not ws.is_env_file(str(e.get("path") or ""))]

    def job_env(self, session: ws.Session) -> Dict[str, str]:
        return {"PSKIT_VAULT_SESSION": session.id}

    def after_call(
        self, session: Optional[ws.Session], method: str, parts: List[str], body: Any, status: int,
        extra: Optional[Dict[str, Any]] = None, denied_action: Optional[str] = None,
    ) -> None:
        """Mutations and refusals are logged; every successful mutation is sealed before the response is final."""
        if session is None:
            return
        denied = status in (401, 403)
        if method == "GET" and not denied:
            return
        details = {**audit.safe_details(body), **(extra or {})}
        needed = permissions.studio_permission(method, parts)
        if parts == ["jobs"] and method == "POST":
            needed = permissions.job_permission(str(details.get("command") or ""))
        action = denied_action or (f"{needed[0]}.{needed[1]}" if needed else "/".join(parts[:1]) or "api")
        outcome = "denied" if denied else ("ok" if status < 400 else f"error {status}")
        ws.log(self.vault, session, action, "/".join(parts), outcome, details)
        if status < 400 and method != "GET":
            self._seal(session)

    def on_job_finish(self, session: ws.Session, command: str) -> Callable[[Any], None]:
        def finished(job: Any) -> None:
            outcome = "ok" if job.exit_code == 0 else f"exit {job.exit_code}"
            ws.log(self.vault, session, f"job.{command}", job.id, outcome)
            self._seal(session)

        return finished

    # ------------------------------------------------------------------ /api/auth
    def api(self, method: str, rest: List[str], body: Dict[str, Any], token: str, params: Dict[str, str]) -> Tuple[int, Any]:
        try:
            return self._api(method, rest, body, token, params)
        except VaultError as exc:
            raise _error(exc) from None

    def _status(self, token: str) -> Dict[str, Any]:
        if self.is_open():
            return {"state": "open"}
        if not self.vault.exists():
            return {"state": "setup"}
        session = self.session_of(token)
        if session is None:
            return {"state": "login"}
        user = self._user(session)
        keys = self.vault.area_keys(session.identity)
        return {
            "state": "password_change" if user.get("must_change") else "ready",
            "user": session.username,
            "role": user.get("role"),
            "permissions": {
                f: "".join(a for a in permissions.ACTIONS if permissions.allowed(user, f, a))
                for f in permissions.FEATURES
            },
            "areas": sorted(keys),
        }

    def _api(self, method: str, rest: List[str], body: Dict[str, Any], token: str, params: Dict[str, str]) -> Tuple[int, Any]:
        if rest == ["status"] and method == "GET":
            return 200, self._status(token)
        if rest == ["mode"] and method == "POST":
            return self._mode(body, token)
        if rest == ["setup"] and method == "POST":
            return self._setup(body)
        if rest == ["login"] and method == "POST":
            return self._login(body)
        if rest == ["recover"] and method == "POST":
            return self._recover(body)
        session = self.require(token)
        if rest == ["logout"] and method == "POST":
            self.sessions.pop(token, None)
            ws.log(self.vault, session, "auth.logout")
            if self.jobs_running():
                self._closing.append(session)
            else:
                ws.close_session(self.vault, session)
            return 200, {"state": "login"}
        if rest == ["password"] and method == "POST":
            self.vault.change_password(session.identity, str(body.get("old") or ""), str(body.get("new") or ""))
            ws.log(self.vault, session, "auth.password")
            return 200, self._status(token)
        user = self._user(session)
        if user.get("must_change"):
            raise StudioError(403, "set a new password first", code="password_change")
        if rest == ["sync"] and method == "POST":
            result = ws.unseal(self.vault, session.identity)
            ws.log(self.vault, session, "vault.sync", details={"conflicts": len(result["conflicts"])})
            return 200, result
        if rest == ["features"] and method == "GET":
            return 200, {"features": permissions.catalog(), "presets": permissions.PRESETS, "areas": permissions.AREAS}
        if rest == ["audit"] and method == "GET":
            if not permissions.allowed(user, "audit", "r"):
                self._deny("audit", "r")
            limit, offset = params.get("limit") or "", params.get("offset") or ""
            return 200, audit.read(
                self.vault, session.identity.master, user=params.get("user") or None,
                action=params.get("action") or None, limit=min(int(limit), 500) if limit.isdigit() else 500,
                offset=int(offset) if offset.isdigit() else 0,
            )
        if rest and rest[0] == "users":
            return self._users(session, user, method, rest[1:], body)
        if rest == ["master-key", "rotate"] and method == "POST":
            if user.get("role") != "admin":
                self._deny("users", "u")
            key = self.vault.rotate_master(session.identity)
            ws.write_session(self.root, session)
            ws.log(self.vault, session, "vault.rotate-master-key")
            return 200, {"master_key": key}
        if rest == ["recovery-code", "rotate"] and method == "POST":
            if user.get("role") != "admin":
                self._deny("users", "u")
            code = ws.rotate_recovery(self.vault, session.identity)
            ws.log(self.vault, session, "vault.rotate-recovery-code")
            return 200, {"recovery_code": code}
        raise StudioError(404 if method == "GET" else 405, "unknown auth endpoint")

    def _mode(self, body: Dict[str, Any], token: str) -> Tuple[int, Any]:
        """The first-start choice, and turning accounts on later."""
        mode = str(body.get("mode") or "")
        if mode == "none":
            choose_no_accounts(self.root)
        elif mode == "accounts":
            open_mode_file(self.root).unlink(missing_ok=True)
        else:
            raise StudioError(400, "mode must be none or accounts")
        return 200, self._status(token)

    def _users(
        self, session: ws.Session, user: Dict[str, Any], method: str, rest: List[str], body: Dict[str, Any],
    ) -> Tuple[int, Any]:
        action = {"GET": "r", "POST": "c", "PUT": "u", "DELETE": "d"}.get(method, "u")
        if len(rest) == 2 and rest[1] == "reset-password":
            action = "u"
        if not permissions.allowed(user, "users", action):
            self._deny("users", action)
        if user.get("role") != "admin" and method != "GET":
            # Whoever edits accounts could give themselves anything, so that takes an admin whatever the grid says.
            raise StudioError(403, "only an admin can change accounts", code="forbidden")
        vault, identity = self.vault, session.identity
        if not rest and method == "GET":
            return 200, {"users": vault.list_users(identity)}
        if not rest and method == "POST":
            name = str(body.get("username") or "")
            created = vault.add_user(
                identity, name, str(body.get("password") or ""), str(body.get("role") or "user"), body.get("permissions"),
            )
            ws.log(vault, session, "users.c", name, details={"role": created["role"]})
            return 201, created
        if len(rest) == 1 and method == "PUT":
            changes: Dict[str, Any] = {k: body[k] for k in ("role", "permissions", "disabled") if k in body}
            updated = vault.update_user(identity, rest[0], changes)
            ws.log(vault, session, "users.u", rest[0], details={
                "role": str(updated["role"]), "permissions": str(updated["permissions"])[:300],
                "disabled": bool(updated["disabled"]),
            })
            return 200, updated
        if len(rest) == 1 and method == "DELETE":
            if rest[0] == session.username:
                raise StudioError(409, "you cannot remove your own account")
            vault.remove_user(identity, rest[0])
            ws.log(vault, session, "users.d", rest[0])
            return 200, {"removed": rest[0]}
        if len(rest) == 2 and rest[1] == "reset-password" and method == "POST":
            vault.reset_password(identity, rest[0], str(body.get("password") or ""))
            ws.log(vault, session, "users.reset-password", rest[0])
            return 200, {"reset": rest[0]}
        raise StudioError(404 if method == "GET" else 405, "unknown users endpoint")

    def _new_session(self, session: ws.Session) -> Dict[str, Any]:
        self.sessions[session.id] = session
        self.start()
        return {"session": session.id, **self._status(session.id)}

    def _setup(self, body: Dict[str, Any]) -> Tuple[int, Any]:
        with self._setup_lock:
            open_mode_file(self.root).unlink(missing_ok=True)
            username, password = str(body.get("username") or ""), str(body.get("password") or "")
            vault, identity, master_key, recovery = Vault.create(self.root, username, password)
            ignored = ws.ensure_gitignore(self.root)
            session = ws.Session(secrets.token_urlsafe(32), identity, "studio", time.time() + ws.SESSION_SECONDS)
            ws.write_session(self.root, session)
            sealed = ws.seal(vault, identity)  # whatever plaintext the project already has
            ws.log(vault, session, "vault.create", details={"sealed": len(sealed["sealed"])})
            return 201, {
                **self._new_session(session), "master_key": master_key, "recovery_code": recovery,
                "sealed": sealed["sealed"], "gitignore_added": ignored,
                "tracked_plaintext": ws.tracked_plaintext(self.root),
            }

    def _master(self, body: Dict[str, Any]) -> bytes:
        typed = str(body.get("master_key") or "").strip()
        if not typed:
            raise StudioError(401, "enter the master key", code="bad_master_key")
        return crypto.parse_secret(MASTER_PREFIX, typed, "master key")

    def _login(self, body: Dict[str, Any]) -> Tuple[int, Any]:
        if not self.vault.exists():
            raise StudioError(401, "create the first admin account", code="setup")
        username, password = str(body.get("username") or ""), str(body.get("password") or "")
        self.throttle.check(username)
        self.throttle.check("master")
        master = self._master(body)
        try:
            self.vault.check_master(master)
        except VaultError as exc:
            self.throttle.failed("master")
            raise _error(exc) from None
        with self.throttle.one_at_a_time:
            try:
                session = ws.login(self.vault, master, username, password, "studio")
            except VaultError as exc:
                if exc.code == "bad_login":
                    self.throttle.failed(username)
                    audit.record(self.vault, master, username[:64], "studio", "auth.login", outcome="failed")
                raise _error(exc) from None
        self.throttle.passed(username)
        self.throttle.passed("master")
        opened = ws.open_workspace(self.vault, session)
        ws.log(self.vault, session, "auth.login", details={"conflicts": len(opened["conflicts"])})
        return 200, {**self._new_session(session), "conflicts": opened["conflicts"]}

    def _recover(self, body: Dict[str, Any]) -> Tuple[int, Any]:
        self.throttle.check("recovery")
        master = self._master(body)
        username = str(body.get("username") or "")
        try:
            self.vault.recover(master, str(body.get("recovery_code") or ""), username, str(body.get("password") or ""))
        except VaultError as exc:
            if exc.code == "bad_key":
                self.throttle.failed("recovery")
            raise
        audit.record(self.vault, master, username, "studio", "auth.recover")
        return 200, {"recovered": username}
