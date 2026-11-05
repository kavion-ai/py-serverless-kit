"""Encrypted project data, accounts, per-feature permissions and the audit log.

``.pskit-vault/`` is committed to git and holds only ciphertext. See ``docs/security-vault.md``.
"""

from .errors import VaultError

VAULT_DIR = ".pskit-vault"

__all__ = ["VAULT_DIR", "VaultError"]
