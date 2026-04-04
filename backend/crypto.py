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

def _get_fernet() -> Fernet:
    key = os.environ.get("TOKEN_ENCRYPT_KEY", "")
    if not key:
        # Derive from SESSION_SECRET as fallback so existing deployments
        # don't need a new env var if they set SESSION_SECRET already.
        secret = os.environ.get("SESSION_SECRET", "fallback-insecure-key")
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"hftoolbox-token-enc",
            iterations=100_000,
        )
        raw = kdf.derive(secret.encode("utf-8"))
        return Fernet(base64.urlsafe_b64encode(raw))
    return Fernet(key.encode() if len(key) < 60 else key.encode())


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
