"""SSH private keys given as text: checked and normalized before they are saved, and files only their owner can read.

OpenSSH refuses a key other accounts can read, and ``chmod`` does nothing on Windows, so there the ACL is set instead.
"""

from __future__ import annotations

import base64
import binascii
import getpass
import os
import re
import stat
import struct
import subprocess
import sys
import textwrap
from pathlib import Path

MAX_KEY_CHARS = 64 * 1024
_PEM = re.compile(r"-----BEGIN ([A-Z0-9 ]*)PRIVATE KEY-----(.*?)-----END \1PRIVATE KEY-----", re.S)
_OPENSSH_MAGIC = b"openssh-key-v1\0"
_ENCRYPTED_KEY = (
    "this key has a passphrase, which pskit cannot answer. Remove it from a copy "
    '(ssh-keygen -p -N "" -f copy-of-key) or log in with the SSH agent'
)


def clean_private_key(text: str) -> str:
    """The key in the form OpenSSH reads: LF line endings, wrapped, ending in a newline. Pasting often breaks these.

    Raises ``ValueError`` with what is wrong; the message never holds any of the key.
    """
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if "\n" not in raw and "\\n" in raw:  # an environment variable or CI secret holding one line
        raw = raw.replace("\\n", "\n")
    if len(raw) > MAX_KEY_CHARS:
        raise ValueError("that is too long for an SSH private key")
    if raw.startswith("PuTTY-User-Key-File"):
        raise ValueError("this is a PuTTY key: export it from PuTTYgen with Conversions > Export OpenSSH key")
    if "PUBLIC KEY-----" in raw or re.match(r"^(ssh-|ecdsa-|sk-)", raw):
        raise ValueError("this is a public key; paste the private key, which starts with -----BEGIN")
    found = _PEM.search(raw)
    if not found:
        raise ValueError("not an SSH private key: it must run from -----BEGIN ... PRIVATE KEY----- to -----END ... -----")
    label, body = found.group(1), found.group(2)
    if label == "ENCRYPTED " or "ENCRYPTED" in body:
        raise ValueError(_ENCRYPTED_KEY)
    joined = "".join(body.split())
    try:
        data = base64.b64decode(joined, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("the key is damaged: its text is not valid base64 (was part of it left out?)") from None
    if label == "OPENSSH " and _openssh_cipher(data) != b"none":
        raise ValueError(_ENCRYPTED_KEY)
    lines = "\n".join(textwrap.wrap(joined, 70 if label == "OPENSSH " else 64))
    return f"-----BEGIN {label}PRIVATE KEY-----\n{lines}\n-----END {label}PRIVATE KEY-----\n"


def _openssh_cipher(data: bytes) -> bytes:
    if not data.startswith(_OPENSSH_MAGIC) or len(data) < len(_OPENSSH_MAGIC) + 4:
        raise ValueError("the key is damaged: it is not in the OpenSSH format its header says")
    start = len(_OPENSSH_MAGIC)
    size = struct.unpack(">I", data[start : start + 4])[0]
    return data[start + 4 : start + 4 + size]


def restrict_to_owner(path: Path) -> None:
    """Only the current account can read ``path`` from now on."""
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:  # pragma: no cover - a file system without modes
        pass
    if sys.platform == "win32":
        subprocess.run(  # noqa: S603 - fixed program, no shell
            ["icacls", str(path), "/inheritance:r", "/grant:r", f"{getpass.getuser()}:F"],  # noqa: S607
            capture_output=True, check=False,
        )


def write_owner_only(path: Path, data: bytes) -> None:
    """Created closed and restricted before anything secret goes in."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    fd = os.open(str(tmp), os.O_CREAT | os.O_WRONLY | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR)
    os.close(fd)
    restrict_to_owner(tmp)
    with tmp.open("wb") as handle:
        handle.write(data)
    os.replace(tmp, path)
