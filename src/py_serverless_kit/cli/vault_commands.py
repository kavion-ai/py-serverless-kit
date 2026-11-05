"""``pskit login``, ``logout``, ``whoami`` and ``pskit vault ...``: accounts and encrypted project data."""

from __future__ import annotations

import json
import os
import sys
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Optional

import click


def _guarded(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Vault errors become one clean error line."""

    @wraps(fn)
    def inner(*args: Any, **kwargs: Any) -> Any:
        from ..vault.errors import VaultError

        try:
            return fn(*args, **kwargs)
        except VaultError as exc:
            raise click.ClickException(exc.message) from None

    return inner


def _hidden(label: str, confirm: bool = False) -> str:
    """A prompt that does not echo. Piped input is read as lines: Windows' hidden prompt ignores it and waits forever."""
    if sys.stdin is not None and sys.stdin.isatty():
        return str(click.prompt(label, hide_input=True, confirmation_prompt=confirm))
    first = sys.stdin.readline().rstrip("\r\n")
    if not first:
        raise click.ClickException(f"{label}: nothing on standard input")
    if confirm and sys.stdin.readline().rstrip("\r\n") != first:
        raise click.ClickException(f"{label}: the two values are different")
    return first


def _vault(directory: str) -> Any:
    from ..vault.cli_gate import find_root
    from ..vault.store import Vault

    root = find_root(Path(directory))
    if root is None:
        raise click.ClickException("no vault here. Create one with `pskit vault init` or by opening `pskit studio`.")
    return Vault(root)


def _session(vault: Any) -> Any:
    from ..vault.cli_gate import current_session

    session = current_session(vault.root)
    if session is None:
        raise click.ClickException("you are not logged in: run `pskit login`")
    return session


def _admin(vault: Any) -> Any:
    session = _session(vault)
    if vault.user(session.identity).get("role") != "admin":
        raise click.ClickException("only an admin can do this")
    return session


def _master_from_prompt(vault: Any) -> bytes:
    from ..vault import crypto
    from ..vault.store import MASTER_PREFIX

    typed = os.environ.get("PSKIT_MASTER_KEY")
    if not typed:
        click.echo("Enter the project's master key. If you do not have it, ask your admin.")
        typed = _hidden("Master key")
    master = crypto.parse_secret(MASTER_PREFIX, typed, "master key")
    vault.check_master(master)
    return master


_DIR = click.option("-d", "--dir", "directory", default=".", type=click.Path(file_okay=False), help="Project folder.")


@click.command("login", short_help="Unlock the project: master key, username, password.")
@click.option("-u", "--username", default=None)
@_DIR
@_guarded
def login(username: Optional[str], directory: str) -> None:
    """Unlock the project: asks for the master key, then your username and password.

    \b
    Decrypts what your account may read to the normal gitignored paths. `pskit logout` encrypts and removes them.

    \b
    Examples:
      pskit login
      pskit login -u priya
    """
    from ..vault import audit
    from ..vault import workspace as ws
    from ..vault.cli_gate import save_current
    from ..vault.errors import VaultError

    vault = _vault(directory)
    master = _master_from_prompt(vault)
    name = username or os.environ.get("PSKIT_USER") or click.prompt("Username")
    password = os.environ.get("PSKIT_PASSWORD") or _hidden("Password")
    try:
        session = ws.login(vault, master, name, password, "cli")
    except VaultError as exc:
        if exc.code == "bad_login":
            audit.record(vault, master, name[:64], "cli", "auth.login", outcome="failed")
        raise
    opened = ws.open_workspace(vault, session)
    save_current(vault.root, session.id)
    ws.log(vault, session, "auth.login", details={"conflicts": len(opened["conflicts"])})
    click.echo(f"Logged in as {name}. Decrypted {len(opened['written'])} changed file(s).")
    for rel in opened["conflicts"]:
        click.echo(f"  CONFLICT {rel}: your local copy is in {rel}{ws.CONFLICT_SUFFIX}")
    if vault.user(session.identity).get("must_change"):
        click.echo("Your password was set by an admin. Choose your own: pskit vault password")


@click.command("logout", short_help="Encrypt your changes and remove the plaintext.")
@_DIR
@_guarded
def logout(directory: str) -> None:
    """Encrypt your changes and remove the plaintext files of this project.

    \b
    Examples:
      pskit logout
    """
    from ..vault import workspace as ws
    from ..vault.cli_gate import clear_current, current_session

    vault = _vault(directory)
    session = current_session(vault.root)
    clear_current(vault.root)
    if session is None:
        click.echo("You were not logged in.")
        return
    ws.log(vault, session, "auth.logout")
    removed = ws.close_session(vault, session)
    click.echo(f"Logged out. Removed {len(removed)} plaintext file(s).")


@click.command("whoami")
@_DIR
@_guarded
def whoami(directory: str) -> None:
    """Show the logged-in account and what it may do.

    \b
    Examples:
      pskit whoami
    """
    vault = _vault(directory)
    session = _session(vault)
    user = vault.user(session.identity)
    click.echo(f"{session.username} ({user.get('role')})")
    click.echo(f"holds keys for: {', '.join(sorted(vault.area_keys(session.identity))) or 'nothing'}")
    if user.get("role") != "admin":
        click.echo(f"permissions: {json.dumps(user.get('permissions') or {}, sort_keys=True)}")


@click.group("vault", short_help="Encrypted project data, accounts, permissions and the audit log.")
def vault_group() -> None:
    """Encrypted project data, accounts, permissions and the audit log. See docs/security-vault.md.

    \b
    Examples:
      pskit vault init
      pskit vault users add priya --preset developer
      pskit vault audit --user priya
    """


@vault_group.command("init")
@click.option("-u", "--username", prompt="Admin username")
@_DIR
@_guarded
def vault_init(username: str, directory: str) -> None:
    """Create the vault and its first admin. Shows the master key and recovery code once."""
    import secrets
    import time

    from ..vault import workspace as ws
    from ..vault.cli_gate import save_current
    from ..vault.store import Vault

    password = os.environ.get("PSKIT_PASSWORD") or _hidden("Admin password", confirm=True)
    vault, identity, master_key, recovery = Vault.create(Path(directory).resolve(), username, password)
    ws.ensure_gitignore(vault.root)
    session = ws.Session(secrets.token_urlsafe(32), identity, "cli", time.time() + ws.SESSION_SECONDS)
    ws.write_session(vault.root, session)
    save_current(vault.root, session.id)
    sealed = ws.seal(vault, identity)
    ws.log(vault, session, "vault.create", details={"sealed": len(sealed["sealed"])})
    click.echo(f"Encrypted {len(sealed['sealed'])} existing file(s) into .pskit-vault/ (commit that folder).\n")
    click.echo(f"MASTER KEY     {master_key}")
    click.echo("  Needed at every login. Give it to the developers of this project. It is shown only once.\n")
    click.echo(f"RECOVERY CODE  {recovery}")
    click.echo("  Keep this offline and to yourself. With the master key, it resets an admin password if all are lost.\n")
    for rel in ws.tracked_plaintext(vault.root):
        click.echo(f"WARNING: git tracks {rel}; run `git rm --cached {rel}` and change that secret")


@vault_group.command("status")
@_DIR
@_guarded
def vault_status(directory: str) -> None:
    """Show the vault's id, sessions and any protected file git still tracks."""
    from ..vault import workspace as ws

    vault = _vault(directory)
    click.echo(f"vault {vault.id} at {vault.dir}")
    for session in ws.live_sessions(vault):
        click.echo(f"  logged in: {session.username} ({session.source})")
    for rel in ws.tracked_plaintext(vault.root):
        click.echo(f"  WARNING: git tracks {rel}; run `git rm --cached {rel}` and change that secret")


@vault_group.command("sync")
@_DIR
@_guarded
def vault_sync(directory: str) -> None:
    """After a `git pull`: bring the vault's newer content to the working files."""
    from ..vault import workspace as ws

    vault = _vault(directory)
    session = _session(vault)
    result = ws.unseal(vault, session.identity)
    ws.log(vault, session, "vault.sync", details={"conflicts": len(result["conflicts"])})
    click.echo(f"{len(result['written'])} file(s) updated, {len(result['removed'])} removed")
    for rel in result["conflicts"]:
        click.echo(f"  CONFLICT {rel}: your local copy is in {rel}{ws.CONFLICT_SUFFIX}")


@vault_group.command("password")
@_DIR
@_guarded
def vault_password(directory: str) -> None:
    """Change your password."""
    from ..vault import workspace as ws

    vault = _vault(directory)
    session = _session(vault)
    old = _hidden("Current password")
    new = _hidden("New password", confirm=True)
    vault.change_password(session.identity, old, new)
    ws.log(vault, session, "auth.password")
    click.echo("Password changed. Commit and push .pskit-vault/ now: this file cannot be merged if someone else changes accounts.")


@vault_group.command("rotate-master-key")
@_DIR
@_guarded
def vault_rotate(directory: str) -> None:
    """Replace the master key, e.g. after someone left. Everyone then needs the new one."""
    from ..vault import workspace as ws

    vault = _vault(directory)
    session = _admin(vault)
    key = vault.rotate_master(session.identity)
    ws.write_session(vault.root, session)
    ws.log(vault, session, "vault.rotate-master-key")
    click.echo(f"NEW MASTER KEY  {key}\nCommit .pskit-vault/ and give the key to the developers. Shown only once.")


@vault_group.command("recover")
@click.option("-u", "--username", prompt="Admin account to recover")
@_DIR
@_guarded
def vault_recover(username: str, directory: str) -> None:
    """All admin passwords are lost: use the recovery code to set a new password on an admin account."""
    from ..vault import audit

    vault = _vault(directory)
    master = _master_from_prompt(vault)
    code = _hidden("Recovery code")
    password = _hidden("New password", confirm=True)
    vault.recover(master, code, username, password)
    audit.record(vault, master, username, "cli", "auth.recover")
    click.echo(f"{username} has a new password. Log in with `pskit login`.")


@vault_group.command("audit")
@click.option("--user", default=None, help="Only this account.")
@click.option("--action", default=None, help="Only actions containing this text, like deploy or users.")
@click.option("-n", "--limit", default=100, show_default=True)
@click.option("--json", "as_json", is_flag=True)
@_DIR
@_guarded
def vault_audit(user: Optional[str], action: Optional[str], limit: int, as_json: bool, directory: str) -> None:
    """Show who did what, newest first."""
    from ..vault import audit, permissions

    vault = _vault(directory)
    session = _session(vault)
    if not permissions.allowed(vault.user(session.identity), "audit", "r"):
        raise click.ClickException("you do not have read permission on audit")
    result = audit.read(vault, session.identity.master, user=user, action=action, limit=limit)
    if as_json:
        click.echo(json.dumps(result, indent=2))
        return
    for entry in result["entries"]:
        click.echo(
            f"{entry['ts']}  {entry['user']:<16} {entry['source']:<8} {entry['action']:<28} "
            f"{entry.get('target') or '-'}  {entry['outcome']}"
        )
    for name in result["tampered"]:
        click.echo(f"WARNING: {name} was changed after it was written", err=True)


@vault_group.group("users")
def users_group() -> None:
    """Accounts: list, add, set permissions, reset a password, remove."""


@users_group.command("list")
@_DIR
@_guarded
def users_list(directory: str) -> None:
    """List the accounts and their permissions."""
    vault = _vault(directory)
    session = _admin(vault)
    for user in vault.list_users(session.identity):
        off = "  (disabled)" if user["disabled"] else ""
        perms = "all" if user["role"] == "admin" else json.dumps(user["permissions"], sort_keys=True)
        click.echo(f"{user['username']:<20} {user['role']:<6} {perms}{off}")


def _permissions(preset: Optional[str], allow: Any) -> Any:
    from ..vault import permissions

    if preset and preset not in permissions.PRESETS:
        raise click.ClickException(f"preset must be one of {', '.join(permissions.PRESETS)}")
    out = dict(permissions.PRESETS[preset]) if preset else {}
    for item in allow or ():
        feature, _, letters = str(item).partition("=")
        out[feature] = letters
    return out


_ALLOW = click.option("--allow", multiple=True, help="Permission as feature=letters, like --allow code=cru. Repeatable.")
_PRESET = click.option("--preset", default=None, help="Start from viewer, developer or operator.")


@users_group.command("add")
@click.argument("username")
@click.option("--admin", "make_admin", is_flag=True, help="Full access.")
@_PRESET
@_ALLOW
@_DIR
@_guarded
def users_add(username: str, make_admin: bool, preset: Optional[str], allow: Any, directory: str) -> None:
    """Add an account. Its first password is asked here, and it must choose a new one at first login."""
    from ..vault import workspace as ws

    vault = _vault(directory)
    session = _admin(vault)
    password = _hidden("First password", confirm=True)
    created = vault.add_user(session.identity, username, password, "admin" if make_admin else "user",
                             _permissions(preset, allow))
    ws.log(vault, session, "users.c", username, details={"role": created["role"]})
    click.echo(f"Added {username}. Holds keys for: {', '.join(created['areas']) or 'nothing'}")


@users_group.command("set")
@click.argument("username")
@click.option("--role", type=click.Choice(["admin", "user"]), default=None)
@click.option("--disable/--enable", "disabled", default=None)
@_PRESET
@_ALLOW
@_DIR
@_guarded
def users_set(
    username: str, role: Optional[str], disabled: Optional[bool], preset: Optional[str], allow: Any, directory: str,
) -> None:
    """Change an account. --preset or --allow replace all its permissions. Taking access away re-encrypts that data."""
    from ..vault import workspace as ws

    vault = _vault(directory)
    session = _admin(vault)
    changes: dict = {}
    if role:
        changes["role"] = role
    if disabled is not None:
        changes["disabled"] = disabled
    if preset or allow:
        changes["permissions"] = _permissions(preset, allow)
    updated = vault.update_user(session.identity, username, changes)
    ws.log(vault, session, "users.u", username, details={
        "role": str(updated["role"]), "permissions": str(updated["permissions"])[:300],
        "disabled": bool(updated["disabled"]),
    })
    click.echo(f"{username}: holds keys for {', '.join(updated['areas']) or 'nothing'}")
    click.echo("Commit and push .pskit-vault/ now: this file cannot be merged if someone else changes accounts.")


@users_group.command("reset-password")
@click.argument("username")
@_DIR
@_guarded
def users_reset(username: str, directory: str) -> None:
    """Set a new first password for an account that forgot its own."""
    from ..vault import workspace as ws

    vault = _vault(directory)
    session = _admin(vault)
    password = _hidden("New first password", confirm=True)
    vault.reset_password(session.identity, username, password)
    ws.log(vault, session, "users.reset-password", username)
    click.echo(f"{username} must choose a new password at the next login.")


@users_group.command("remove")
@click.argument("username")
@click.option("--yes", is_flag=True, help="Do not ask.")
@_DIR
@_guarded
def users_remove(username: str, yes: bool, directory: str) -> None:
    """Remove an account and re-encrypt what it could read. Change the real secrets too: it may have copies."""
    from ..vault import workspace as ws

    vault = _vault(directory)
    session = _admin(vault)
    if username == session.username:
        raise click.ClickException("you cannot remove your own account")
    if not yes:
        click.confirm(f"Remove {username}?", abort=True)
    vault.remove_user(session.identity, username)
    ws.log(vault, session, "users.d", username)
    click.echo(f"Removed {username}. Commit .pskit-vault/, and consider `pskit vault rotate-master-key`.")


def register(cli: click.Group) -> None:
    for command in (login, logout, whoami, vault_group):
        cli.add_command(command)
