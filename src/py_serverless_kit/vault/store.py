"""The committed vault: accounts, master key, per-area data keys.

Layout (safe to commit, ciphertext only)::

    .pskit-vault/vault.json              id, master key check, the encrypted accounts document
    .pskit-vault/data/<area>/<mac>.enc   one encrypted file per protected file
    .pskit-vault/audit/*.log             encrypted audit entries (see audit.py)

Key hierarchy:

* The **master key** (shown once, shared with developers) decrypts the accounts document. Alone it opens no data.
* Each account has an X25519 key pair; its private key is encrypted with a key derived (scrypt) from its password.
* Each **area** (env, servers, ...) has a random data key, wrapped to the public key of every account with access,
  and to the **recovery key** (shown once, kept by the admin). So decrypting data takes the master key AND the password
  of an account that holds that area, and an admin can grant access without knowing the user's password.
* Taking access away gives the area a new data key and re-encrypts it. Copies in git history stay readable with the
  old key: rotate the real secrets too.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import struct
import time
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Collection, Dict, Iterator, List, Optional, Set, Tuple

from . import crypto, permissions
from .crypto import InvalidTag
from .errors import VaultError

VAULT_DIR = ".pskit-vault"
HEADER = "vault.json"
FORMAT = "pskit-vault"
VERSION = 1
MASTER_PREFIX = "pskm"
RECOVERY_PREFIX = "pskr"
MIN_PASSWORD = 12
_USERNAME = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{1,63}$")
_RECOVERY = "__recovery__"
_MAGIC = b"PSKV1"
_ATTRIBUTES = "* -text -diff\n"
BAD_LOGIN = "wrong username or password"
# Spent on an unknown username too, so the response time does not tell which usernames exist.
_DUMMY_SALT = b"\0" * 16


@dataclass
class Identity:
    """An authenticated account: enough to decrypt what it may."""

    username: str
    master: bytes
    private: bytes


def find_root(start: Path) -> Optional[Path]:
    """The project at or above ``start`` that has a vault."""
    current = Path(start).resolve()
    for folder in (current, *current.parents):
        if (folder / VAULT_DIR / HEADER).is_file():
            return folder
    return None


def check_password(password: str) -> None:
    if len(password or "") < MIN_PASSWORD:
        raise VaultError(f"the password needs at least {MIN_PASSWORD} characters", 400, "weak_password")


def check_username(username: str) -> None:
    if not _USERNAME.match(username or ""):
        raise VaultError("usernames start with a letter and use letters, digits, '.', '_' or '-' (2-64)")


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _json_bytes(doc: Any) -> bytes:
    return (json.dumps(doc, indent=1, sort_keys=True) + "\n").encode("utf-8")


class Vault:
    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.dir = self.root / VAULT_DIR
        self.path = self.dir / HEADER

    def exists(self) -> bool:
        return self.path.is_file()

    def header(self) -> Dict[str, Any]:
        try:
            doc = json.loads(self.path.read_text("utf-8"))
        except OSError:
            raise VaultError("this project has no vault", 404, "no_vault") from None
        except ValueError:
            raise VaultError("the vault file is damaged (a git merge conflict?)", 500, "damaged") from None
        if not isinstance(doc, dict) or doc.get("format") != FORMAT or doc.get("version") != VERSION:
            raise VaultError("the vault file has an unknown format", 500, "damaged")
        return doc

    @property
    def id(self) -> str:
        return str(self.header()["id"])

    # ------------------------------------------------------------------ master key
    def check_master(self, master: bytes) -> None:
        header = self.header()
        expected = crypto.mac(crypto.hkdf(master, b"check"), str(header["id"]).encode("ascii"))
        if not secrets.compare_digest(crypto.b64(expected), str(header.get("check") or "")):
            raise VaultError("wrong master key", 401, "bad_master_key")

    def accounts(self, master: bytes) -> Dict[str, Any]:
        header = self.header()
        self.check_master(master)
        key = crypto.hkdf(master, b"accounts")
        try:
            plain = crypto.unseal(key, crypto.unb64(str(header["accounts"])), str(header["id"]).encode("ascii"))
        except (InvalidTag, KeyError):
            raise VaultError("the accounts in the vault were changed or are damaged", 500, "damaged") from None
        doc: Dict[str, Any] = json.loads(plain.decode("utf-8"))
        return doc

    def _write(self, master: bytes, doc: Dict[str, Any], header: Optional[Dict[str, Any]] = None) -> None:
        current = header or self.header()
        vid = str(current["id"])
        current["check"] = crypto.b64(crypto.mac(crypto.hkdf(master, b"check"), vid.encode("ascii")))
        current["accounts"] = crypto.b64(
            crypto.seal(crypto.hkdf(master, b"accounts"), _json_bytes(doc), vid.encode("ascii"))
        )
        atomic_write(self.path, _json_bytes(current))

    # ------------------------------------------------------------------ create
    @classmethod
    def create(cls, root: Path, username: str, password: str) -> Tuple[Vault, Identity, str, str]:
        """A new vault with its first admin. Returns the printable master key and recovery code: shown only once."""
        check_username(username)
        check_password(password)
        vault = cls(root)
        if vault.exists():
            raise VaultError("this project already has a vault; log in instead", 409, "exists")
        master, recovery = crypto.random_key(), crypto.random_key()
        recovery_pair = _recovery_pair(recovery)
        vid = secrets.token_hex(16)
        account, private = _new_account(vid, username, password, "admin", {}, "first-run", must_change=False)
        doc: Dict[str, Any] = {
            "users": {username: account},
            "areas": {},
            "recovery_public": crypto.b64(recovery_pair["public"]),
            "audit_keys": [crypto.b64(crypto.random_key())],
        }
        for area in permissions.AREAS:
            doc["areas"][area] = {"generation": 1, "wraps": {}}
            _wrap_for(vid, doc, area, crypto.random_key(), [username, _RECOVERY])
        vault.dir.mkdir(parents=True, exist_ok=True)
        (vault.dir / ".gitattributes").write_bytes(_ATTRIBUTES.encode("ascii"))
        vault._write(master, doc, {"format": FORMAT, "version": VERSION, "id": vid, "created_at": _now()})
        identity = Identity(username, master, private)
        return (
            vault,
            identity,
            crypto.format_secret(MASTER_PREFIX, master),
            crypto.format_secret(RECOVERY_PREFIX, recovery),
        )

    # ------------------------------------------------------------------ login
    def authenticate(self, master: bytes, username: str, password: str) -> Identity:
        doc = self.accounts(master)
        user = (doc.get("users") or {}).get(username)
        if not isinstance(user, dict) or user.get("disabled"):
            crypto.password_key(password, _DUMMY_SALT, crypto.SCRYPT_N, crypto.SCRYPT_R, crypto.SCRYPT_P)
            raise VaultError(BAD_LOGIN, 401, "bad_login")
        try:
            return Identity(username, master, _open_private(self.id, username, user, password))
        except InvalidTag:
            raise VaultError(BAD_LOGIN, 401, "bad_login") from None

    def user(self, identity: Identity) -> Dict[str, Any]:
        """The account's current record: permissions changed by an admin apply at once."""
        user = (self.accounts(identity.master).get("users") or {}).get(identity.username)
        if not isinstance(user, dict) or user.get("disabled"):
            raise VaultError("this account was removed or disabled", 401, "session")
        return user

    def area_keys(self, identity: Identity) -> Dict[str, bytes]:
        """The data keys this account can open right now: never more than its permissions allow, whatever is wrapped."""
        doc = self.accounts(identity.master)
        user = (doc.get("users") or {}).get(identity.username)
        allowed = permissions.areas_for(user) if isinstance(user, dict) else frozenset()
        keys = _keys_of(self.id, doc, identity.username, identity.private)
        return {area: key for area, key in keys.items() if area in allowed}

    # ------------------------------------------------------------------ data files
    def data_dir(self, area: str) -> Path:
        return self.dir / "data" / area

    def seal_file(self, area: str, key: bytes, generation: int, rel: str, data: bytes) -> str:
        header = json.dumps({"path": rel}, sort_keys=True).encode("utf-8")
        plain = zlib.compress(struct.pack(">I", len(header)) + header + data, 9)
        blob = _MAGIC + struct.pack(">I", generation) + crypto.seal(key, plain, _file_aad(self.id, area, generation))
        path = self.data_dir(area) / _enc_name(key, rel)
        atomic_write(path, blob)
        return path.name

    def remove_file(self, area: str, key: bytes, rel: str) -> None:
        try:
            (self.data_dir(area) / _enc_name(key, rel)).unlink()
        except OSError:
            pass

    def read_area(self, area: str, key: bytes, generation: int) -> Iterator[Tuple[str, bytes]]:
        """Each file of the area as (relative path, content). Files of an older generation are skipped."""
        folder = self.data_dir(area)
        if not folder.is_dir():
            return
        vid = self.id
        offset = len(_MAGIC) + 4
        for path in sorted(folder.glob("*.enc")):
            raw = path.read_bytes()
            if raw[: len(_MAGIC)] != _MAGIC or len(raw) < offset:
                raise VaultError(f"{path.name} in the vault is damaged (a git merge conflict?)", 500, "damaged")
            if struct.unpack(">I", raw[len(_MAGIC) : offset])[0] != generation:
                continue
            try:
                plain = zlib.decompress(crypto.unseal(key, raw[offset:], _file_aad(vid, area, generation)))
            except (InvalidTag, zlib.error):
                raise VaultError(f"{path.name} in the vault was changed or is damaged", 500, "damaged") from None
            length = struct.unpack(">I", plain[:4])[0]
            header = json.loads(plain[4 : 4 + length].decode("utf-8"))
            yield str(header["path"]), plain[4 + length :]

    # ------------------------------------------------------------------ accounts (admin)
    def list_users(self, identity: Identity) -> List[Dict[str, Any]]:
        doc = self.accounts(identity.master)
        return [_public_user(name, user) for name, user in sorted(doc["users"].items())]

    def add_user(
        self, identity: Identity, username: str, password: str, role: str = "user", perms: Any = None,
    ) -> Dict[str, Any]:
        check_username(username)
        check_password(password)
        _check_role(role)
        doc = self.accounts(identity.master)
        if username in doc["users"]:
            raise VaultError(f"{username} already exists", 409, "exists")
        account, _private = _new_account(
            self.id, username, password, role, permissions.clean(perms or {}), identity.username, must_change=True,
        )
        doc["users"][username] = account
        self._apply_grants(identity, doc)
        self._write(identity.master, doc)
        return _public_user(username, account)

    def update_user(self, identity: Identity, username: str, changes: Dict[str, Any]) -> Dict[str, Any]:
        doc = self.accounts(identity.master)
        user = doc["users"].get(username)
        if user is None:
            raise VaultError(f"no such account: {username}", 404)
        if "role" in changes:
            _check_role(str(changes["role"]))
            user["role"] = str(changes["role"])
        if "permissions" in changes:
            user["permissions"] = permissions.clean(changes["permissions"])
        if "disabled" in changes:
            user["disabled"] = bool(changes["disabled"])
        _keep_an_admin(doc)
        self._apply_grants(identity, doc)
        self._write(identity.master, doc)
        return _public_user(username, user)

    def remove_user(self, identity: Identity, username: str) -> None:
        doc = self.accounts(identity.master)
        if username not in doc["users"]:
            raise VaultError(f"no such account: {username}", 404)
        del doc["users"][username]
        _keep_an_admin(doc)
        self._apply_grants(identity, doc)
        self._write(identity.master, doc)

    def change_password(self, identity: Identity, old: str, new: str) -> None:
        check_password(new)
        if old == new:
            raise VaultError("the new password must differ from the current one")
        doc = self.accounts(identity.master)
        user = doc["users"].get(identity.username)
        if user is None:
            raise VaultError("this account was removed", 401, "session")
        try:
            private = _open_private(self.id, identity.username, user, old)
        except InvalidTag:
            raise VaultError("the current password is wrong", 401, "bad_login") from None
        user["key"] = _seal_private(self.id, identity.username, private, new)
        user["must_change"] = False
        self._write(identity.master, doc)

    def reset_password(self, identity: Identity, username: str, password: str) -> None:
        """A forgotten password: the account gets a new key pair and the admin re-grants its areas."""
        check_password(password)
        doc = self.accounts(identity.master)
        user = doc["users"].get(username)
        if user is None:
            raise VaultError(f"no such account: {username}", 404)
        keys = _keys_of(self.id, doc, identity.username, identity.private)
        self._replace_keypair(doc, username, user, password, keys)
        user["must_change"] = True
        self._write(identity.master, doc)

    def _replace_keypair(
        self, doc: Dict[str, Any], username: str, user: Dict[str, Any], password: str, keys: Dict[str, bytes],
    ) -> None:
        pair = crypto.new_keypair()
        user["public"] = crypto.b64(pair["public"])
        user["key"] = _seal_private(self.id, username, pair["private"], password)
        for area in permissions.areas_for(user):
            if area not in keys:
                raise VaultError(f"you do not hold the {area} key, so you cannot reset this account", 403, "forbidden")
            doc["areas"][area]["wraps"][username] = crypto.wrap(
                keys[area], pair["public"], _wrap_context(self.id, area, username),
            )

    def rotate_master(self, identity: Identity) -> str:
        """A new master key, e.g. after someone left. Everyone needs the new one; git history keeps the old vault."""
        doc = self.accounts(identity.master)
        doc["audit_keys"].append(crypto.b64(crypto.random_key()))
        master = crypto.random_key()
        self._write(master, doc)
        identity.master = master
        return crypto.format_secret(MASTER_PREFIX, master)

    def rotate_recovery(self, identity: Identity) -> str:
        """A new recovery code, e.g. after the old one leaked. Every area gets a new key too: the old code and an old
        copy of this file from git history would otherwise still open today's data. Crash safe: nothing changes until
        the accounts naming the new generations are saved."""
        doc = self.accounts(identity.master)
        keys = _keys_of(self.id, doc, identity.username, identity.private)
        for area in doc["areas"]:
            if area not in keys:
                raise VaultError(f"you do not hold the {area} key, so you cannot replace the recovery code", 403, "forbidden")
        recovery = crypto.random_key()
        doc["recovery_public"] = crypto.b64(_recovery_pair(recovery)["public"])
        replaced = {area: self._reseal_area(doc, area, keys[area], _holders(doc, area)) for area in doc["areas"]}
        self._write(identity.master, doc)
        for area, generation in replaced.items():
            self._drop_generation(area, generation)
        return crypto.format_secret(RECOVERY_PREFIX, recovery)

    def recover(self, master: bytes, recovery_code: str, username: str, password: str) -> None:
        """Every admin password is lost: the recovery code plus the master key set a new admin password."""
        recovery = crypto.parse_secret(RECOVERY_PREFIX, recovery_code, "recovery code")
        check_password(password)
        doc = self.accounts(master)
        pair = _recovery_pair(recovery)
        if crypto.b64(pair["public"]) != doc.get("recovery_public"):
            raise VaultError("wrong recovery code", 401, "bad_key")
        user = doc["users"].get(username)
        if user is None or user.get("role") != "admin":
            raise VaultError(f"{username} is not an admin account")
        keys = {
            area: crypto.unwrap(info["wraps"][_RECOVERY], pair["private"], _wrap_context(self.id, area, _RECOVERY))
            for area, info in doc["areas"].items()
        }
        user["disabled"] = False
        self._replace_keypair(doc, username, user, password, keys)
        self._write(master, doc)

    # ------------------------------------------------------------------ grants
    def apply_grants(self, identity: Identity) -> bool:
        """Bring the key wraps in line with the permissions, for a vault made when these rules were wider. Admins only."""
        doc = self.accounts(identity.master)
        if (doc["users"].get(identity.username) or {}).get("role") != "admin":
            return False
        if all(set(info["wraps"]) - {_RECOVERY} == _holders(doc, area) for area, info in doc["areas"].items()):
            return False
        self._apply_grants(identity, doc)
        self._write(identity.master, doc)
        return True

    def _apply_grants(self, identity: Identity, doc: Dict[str, Any]) -> None:
        """Make the key wraps match the permissions. Losing access means a new key for that area."""
        vid = self.id
        keys = _keys_of(vid, doc, identity.username, identity.private)
        for area, info in doc["areas"].items():
            wanted = _holders(doc, area)
            current = set(info["wraps"]) - {_RECOVERY}
            if current == wanted:
                continue
            if area not in keys:
                raise VaultError(f"you do not hold the {area} key, so you cannot change who has it", 403, "forbidden")
            if current - wanted:
                self._rotate_area(identity.master, doc, area, keys[area], wanted)
            else:
                _wrap_for(vid, doc, area, keys[area], sorted(wanted - current))

    def _rotate_area(self, master: bytes, doc: Dict[str, Any], area: str, old: bytes, wanted: Collection[str]) -> None:
        """Crash safe: new files sit next to the old ones until the accounts naming the new generation are saved, and
        ``read_area`` only takes files of the current generation."""
        generation = self._reseal_area(doc, area, old, wanted)
        self._write(master, doc)
        self._drop_generation(area, generation)

    def _reseal_area(self, doc: Dict[str, Any], area: str, old: bytes, wanted: Collection[str]) -> int:
        """Encrypt an area again with a new key, in ``doc`` only until it is saved. Returns the generation replaced."""
        info = doc["areas"][area]
        new_key = crypto.random_key()
        generation = int(info["generation"])
        for rel, data in list(self.read_area(area, old, generation)):
            self.seal_file(area, new_key, generation + 1, rel, data)
        info["generation"] = generation + 1
        info["wraps"] = {}
        _wrap_for(self.id, doc, area, new_key, [*sorted(wanted), _RECOVERY])
        return generation

    def _drop_generation(self, area: str, generation: int) -> None:
        offset = len(_MAGIC) + 4
        for path in self.data_dir(area).glob("*.enc"):
            if struct.unpack(">I", path.read_bytes()[len(_MAGIC) : offset])[0] == generation:
                path.unlink()


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _check_role(role: str) -> None:
    if role not in ("admin", "user"):
        raise VaultError("role must be admin or user")


def _keep_an_admin(doc: Dict[str, Any]) -> None:
    if not any(u.get("role") == "admin" and not u.get("disabled") for u in doc["users"].values()):
        raise VaultError("the vault must keep at least one active admin", 409, "last_admin")


def _holders(doc: Dict[str, Any], area: str) -> Set[str]:
    return {name for name, user in doc["users"].items() if area in permissions.areas_for(user)}


def _recovery_pair(recovery: bytes) -> Dict[str, bytes]:
    private = crypto.hkdf(recovery, b"recovery-x25519")
    return {"private": private, "public": crypto.public_of(private)}


def _private_context(vault_id: str, username: str) -> bytes:
    return f"private|{vault_id}|{username}".encode()


def _wrap_context(vault_id: str, area: str, username: str) -> bytes:
    return f"area|{vault_id}|{area}|{username}".encode()


def _file_aad(vault_id: str, area: str, generation: int) -> bytes:
    return f"file|{vault_id}|{area}|{generation}".encode()


def _enc_name(key: bytes, rel: str) -> str:
    """Hides the file's path; the same file keeps its name, so git sees an update and not a new file."""
    return crypto.mac(crypto.hkdf(key, b"names"), rel.encode("utf-8")).hex()[:40] + ".enc"


def _seal_private(vault_id: str, username: str, private: bytes, password: str) -> Dict[str, Any]:
    salt = os.urandom(16)
    n, r, p = crypto.SCRYPT_N, crypto.SCRYPT_R, crypto.SCRYPT_P
    key = crypto.password_key(password, salt, n, r, p)
    return {
        "salt": crypto.b64(salt), "n": n, "r": r, "p": p,
        "ct": crypto.b64(crypto.seal(key, private, _private_context(vault_id, username))),
    }


def _open_private(vault_id: str, username: str, user: Dict[str, Any], password: str) -> bytes:
    sealed = user["key"]
    key = crypto.password_key(password, crypto.unb64(sealed["salt"]), int(sealed["n"]), int(sealed["r"]), int(sealed["p"]))
    return crypto.unseal(key, crypto.unb64(sealed["ct"]), _private_context(vault_id, username))


def _new_account(
    vault_id: str, username: str, password: str, role: str, perms: Dict[str, str], created_by: str, *, must_change: bool,
) -> Tuple[Dict[str, Any], bytes]:
    pair = crypto.new_keypair()
    account = {
        "role": role,
        "permissions": perms,
        "public": crypto.b64(pair["public"]),
        "key": _seal_private(vault_id, username, pair["private"], password),
        "must_change": must_change,
        "disabled": False,
        "created_at": _now(),
        "created_by": created_by,
    }
    return account, pair["private"]


def _wrap_for(vault_id: str, doc: Dict[str, Any], area: str, key: bytes, names: List[str]) -> None:
    wraps = doc["areas"][area]["wraps"]
    for name in names:
        public = doc["recovery_public"] if name == _RECOVERY else doc["users"][name]["public"]
        wraps[name] = crypto.wrap(key, crypto.unb64(public), _wrap_context(vault_id, area, name))


def _keys_of(vault_id: str, doc: Dict[str, Any], username: str, private: bytes) -> Dict[str, bytes]:
    out = {}
    for area, info in doc["areas"].items():
        entry = info["wraps"].get(username)
        if entry is None:
            continue
        try:
            out[area] = crypto.unwrap(entry, private, _wrap_context(vault_id, area, username))
        except InvalidTag:
            continue  # a password reset replaced this key pair: this session holds nothing any more
    return out


def _public_user(name: str, user: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "username": name,
        "role": user.get("role"),
        "permissions": user.get("permissions") or {},
        "areas": sorted(permissions.areas_for(user)),
        "disabled": bool(user.get("disabled")),
        "must_change": bool(user.get("must_change")),
        "created_at": user.get("created_at"),
        "created_by": user.get("created_by"),
    }
