"""Symmetric encryption for secrets stored in the database (broker access tokens).

Fernet = AES-128-CBC + HMAC-SHA256 (authenticated: a tampered ciphertext fails to decrypt).
MultiFernet takes several keys, newest first: it encrypts with the first and decrypts with any,
so a key can be rotated by prepending a new one and re-encrypting at leisure.

What this protects against: a leaked database, backup or replica. What it does not: anyone
who can read the app's environment, where the key lives. In production the key would come
from a KMS / secrets manager (envelope encryption), not a plain env var.
"""
from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from pydantic import SecretStr

from src.core.config import settings


class EncryptionNotConfiguredError(Exception):
    """TOKEN_ENCRYPTION_KEYS is not set: secrets cannot be stored or read."""


class TokenCipher:
    def __init__(self, keys: SecretStr | None = None) -> None:
        keys = keys or settings.token_encryption_keys
        if keys is None:
            raise EncryptionNotConfiguredError("TOKEN_ENCRYPTION_KEYS is not set (run `make env`)")
        self._fernet = MultiFernet([Fernet(k.strip()) for k in keys.get_secret_value().split(",") if k.strip()])

    def encrypt(self, secret: SecretStr) -> str:
        return self._fernet.encrypt(secret.get_secret_value().encode()).decode()

    def decrypt(self, ciphertext: str) -> SecretStr:
        """Raises InvalidToken if the ciphertext was tampered with or no key matches."""
        return SecretStr(self._fernet.decrypt(ciphertext.encode()).decode())


__all__ = ["EncryptionNotConfiguredError", "InvalidToken", "TokenCipher"]
