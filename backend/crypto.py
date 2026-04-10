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
import logging
import secrets
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

ENC_PREFIX = "e:"
log = logging.getLogger("crypto")
ENV = os.environ.get("ENV", "development").lower()
_WEAK_SECRETS = {
    "",
    "changeme",
    "change-me",
    "default",
    "fallback-insecure-key",
    "replace_with_64_char_random_hex_string",
}
_EPHEMERAL_FERNET = None


def _fernet_from_secret(secret: str) -> Fernet:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"hftoolbox-token-enc",
        iterations=100_000,
    )
    raw = kdf.derive(secret.encode("utf-8"))
    return Fernet(base64.urlsafe_b64encode(raw))


def _get_fernet() -> Fernet:
    global _EPHEMERAL_FERNET

    key = (os.environ.get("TOKEN_ENCRYPT_KEY") or "").strip()
    if key:
        return Fernet(key.encode())

    session_secret = (os.environ.get("SESSION_SECRET") or "").strip()
    session_secret_weak = session_secret in _WEAK_SECRETS or len(session_secret) < 32
    if not session_secret_weak:
        return _fernet_from_secret(session_secret)

    if ENV == "production":
        raise RuntimeError(
            "TOKEN_ENCRYPT_KEY is not set and SESSION_SECRET is missing or weak. "
            "Set a real TOKEN_ENCRYPT_KEY (recommended) or a strong SESSION_SECRET before starting production."
        )

    if _EPHEMERAL_FERNET is None:
        _EPHEMERAL_FERNET = Fernet(Fernet.generate_key())
        log.warning(
            "TOKEN_ENCRYPT_KEY is not set and SESSION_SECRET is missing or weak. "
            "Using an ephemeral development encryption key; encrypted tokens will be unreadable after restart."
        )
    return _EPHEMERAL_FERNET


def encrypt_token(token: str) -> str:
    """Encrypt a plaintext token. Returns 'e:<ciphertext>'."""
    if not token:
        return token
    if token.startswith(ENC_PREFIX):
        return token  # already encrypted
    try:
        return ENC_PREFIX + _get_fernet().encrypt(token.encode()).decode()
    except Exception:
        return token  # never lose data


def decrypt_token(value: str) -> str:
    """Decrypt an encrypted token. Returns plaintext. Handles legacy plaintext gracefully."""
    if not value or not value.startswith(ENC_PREFIX):
        return value  # legacy plaintext or empty
    try:
        return _get_fernet().decrypt(value[len(ENC_PREFIX):].encode()).decode()
    except (InvalidToken, Exception):
        return value  # wrong key or corrupt — return raw rather than crash
