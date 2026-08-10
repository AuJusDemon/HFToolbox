"""
crypto.py — Token encryption using a server-side key.

The HF OAuth token is the only sensitive field encrypted at rest.
Encryption uses a Fernet key stored in TOKEN_ENCRYPT_KEY in .env.

Usage:
    enc = encrypt_token(token)   # store this in DB
    tok = decrypt_token(enc)     # retrieve plaintext token
"""

import os
import base64
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

ENC_PREFIX = "e:"


def _session_fernet() -> Fernet:
    """Fallback key derived from SESSION_SECRET — used for tokens encrypted before TOKEN_ENCRYPT_KEY was set."""
    secret = os.environ.get("SESSION_SECRET", "fallback-insecure-key")
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"hftoolbox-token-enc",
        iterations=100_000,
    )
    raw = kdf.derive(secret.encode("utf-8"))
    return Fernet(base64.urlsafe_b64encode(raw))


def _primary_fernet() -> Fernet | None:
    """Returns Fernet from TOKEN_ENCRYPT_KEY, or None if not set."""
    key = os.environ.get("TOKEN_ENCRYPT_KEY", "").strip()
    if not key:
        return None
    return Fernet(key.encode())


def encrypt_token(token: str) -> str:
    """Encrypt a plaintext token. Returns 'e:<ciphertext>'."""
    if not token:
        return token
    if token.startswith(ENC_PREFIX):
        return token  # already encrypted
    try:
        f = _primary_fernet() or _session_fernet()
        return ENC_PREFIX + f.encrypt(token.encode()).decode()
    except Exception as exc:
        raise RuntimeError("token encryption failed") from exc


def decrypt_token(value: str) -> str:
    """
    Decrypt an encrypted token. Tries TOKEN_ENCRYPT_KEY first, falls back to
    SESSION_SECRET-derived key for tokens encrypted before TOKEN_ENCRYPT_KEY was set.
    Returns plaintext. Handles legacy plaintext gracefully.
    """
    if not value or not value.startswith(ENC_PREFIX):
        return value  # plaintext or empty
    ciphertext = value[len(ENC_PREFIX):].encode()
    primary = _primary_fernet()
    if primary:
        try:
            return primary.decrypt(ciphertext).decode()
        except (InvalidToken, Exception):
            pass
    # Fall back to SESSION_SECRET-derived key (pre-TOKEN_ENCRYPT_KEY tokens)
    try:
        return _session_fernet().decrypt(ciphertext).decode()
    except (InvalidToken, Exception):
        return value  # corrupt or wrong key — return raw rather than crash
