"""Login and permission check for CLI commands, and the seal after them. Projects without a vault are not affected.

A session comes from, in order:

* ``PSKIT_VAULT_SESSION``: set by the studio on the jobs it starts (it logged and checked them already);
* ``PSKIT_MASTER_KEY`` + ``PSKIT_USER`` + ``PSKIT_PASSWORD``: scripts and CI, a login for this one command;
* ``pskit login``: lasts 12 hours.

This module imports ``cryptography`` only when a vault exists, so commands stay fast everywhere else.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional, Sequence

if TYPE_CHECKING:
    from .store import Vault
    from .workspace import Session

VAULT_FILE = Path(".pskit-vault") / "vault.json"
_CLI_POINTER = Path(".pskit") / ".vault" / "cli-session"
_DIR_OPTIONS = ("-d", "--dir", "--directory")
_FILE_OPTIONS = ("-c", "--config")
_WORDS = {"c": "create", "r": "read", "u": "update", "d": "delete"}


def start_dir(args: Sequence[str]) -> Path:
    """Where the command will work: the folder of ``-c file`` or ``-d dir`` when given, else the current one."""
    for index, arg in enumerate(args):
        for option in (*_DIR_OPTIONS, *_FILE_OPTIONS):
            value: Optional[str] = None
            if arg == option and index + 1 < len(args):
                value = args[index + 1]
            elif arg.startswith(option + "="):
                value = arg.split("=", 1)[1]
            if value is not None:
                return Path(value) if option in _DIR_OPTIONS else Path(value).parent
    return Path.cwd()


def find_root(start: Path) -> Optional[Path]:
    """The project at or above ``start`` with a vault."""
    current = start.resolve()
    for folder in (current, *current.parents):
        if (folder / VAULT_FILE).is_file():
            return folder
    return None


def current_session(root: Path) -> Optional[Session]:
    """The session ``pskit login`` left, if it is still valid."""
    from .store import Vault
    from .workspace import live_sessions

    try:
        wanted = (root / _CLI_POINTER).read_text("ascii").strip()
    except OSError:
        return None
    for session in live_sessions(Vault(root)):
        if session.id == wanted:
            return session
    return None


def save_current(root: Path, session_id: str) -> None:
    path = root / _CLI_POINTER
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(session_id.encode("ascii"))


def clear_current(root: Path) -> None:
    try:
        (root / _CLI_POINTER).unlink()
    except OSError:
        pass


def _env_login(vault: Vault) -> Optional[Session]:
    from . import crypto
    from .store import MASTER_PREFIX
    from .workspace import login, open_workspace

    key, user, password = (os.environ.get(n) for n in ("PSKIT_MASTER_KEY", "PSKIT_USER", "PSKIT_PASSWORD"))
    if not (key and user and password):
        return None
    session = login(vault, crypto.parse_secret(MASTER_PREFIX, key, "master key"), user, password, "cli-env", ttl=86400)
    open_workspace(vault, session)
    return session


def gate(path: Sequence[str], args: Sequence[str]) -> Optional[Callable[[], None]]:
    """Check a command. Returns what to run when it ends, or raises VaultError. None: nothing to do."""
    root = find_root(start_dir(args))
    if root is None:
        return None
    from . import permissions
    from .errors import VaultError
    from .store import Vault
    from .workspace import close_session, load_session, log, seal

    if path[0] in permissions.OPEN_COMMANDS:
        return None
    vault = Vault(root)
    job_session = os.environ.get("PSKIT_VAULT_SESSION")
    if job_session:
        loaded = load_session(root, job_session)
        if loaded is None or loaded.expires < time.time():
            raise VaultError("the studio session of this job has ended", 401, "session")
        vault.user(loaded.identity)
        return lambda: _quiet(lambda: seal(vault, loaded.identity))

    from_env = _env_login(vault)
    session = from_env or current_session(root)
    if session is None:
        raise VaultError(f"this project is protected: run `pskit login` first (in {root})", 401, "login")
    user = vault.user(session.identity)
    if user.get("must_change"):
        raise VaultError("set a new password first: pskit vault password", 403, "password_change")
    feature, action = permissions.cli_permission(path)
    name = " ".join(path)
    if not permissions.allowed(user, feature, action):
        log(vault, session, f"cli.{name}", outcome="denied")
        if from_env is not None:
            close_session(vault, from_env)
        raise VaultError(f"you do not have {_WORDS[action]} permission on {feature} (`pskit {name}`)", 403, "forbidden")
    log(vault, session, f"cli.{name}")
    active = session

    def finish() -> None:
        if from_env is not None:
            _quiet(lambda: close_session(vault, active))
        else:
            _quiet(lambda: seal(vault, active.identity))

    return finish


def _quiet(call: Callable[[], object]) -> None:
    """A failed seal at the end of a command is reported, but must not hide the command's own result."""
    from .errors import VaultError

    try:
        call()
    except (VaultError, OSError) as exc:
        print(f"warning: could not encrypt your changes: {exc}", file=sys.stderr)
