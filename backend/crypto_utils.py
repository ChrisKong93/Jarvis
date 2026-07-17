import base64
import os
from typing import Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


_SALT = b"jarvis-api-key-salt-v1"


def _derive_key(secret: str) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=_SALT, iterations=480000)
    return base64.urlsafe_b64encode(kdf.derive(secret.encode("utf-8")))


def _get_cipher() -> Fernet:
    secret = os.environ.get("SECRET_KEY", "jarvis-secret-key-change-in-production")
    return Fernet(_derive_key(secret))


def encrypt_api_key(plain_text: str) -> str:
    if not plain_text:
        return ""
    cipher = _get_cipher()
    return cipher.encrypt(plain_text.encode("utf-8")).decode("utf-8")


def decrypt_api_key(cipher_text: str) -> str:
    if not cipher_text:
        return ""
    try:
        cipher = _get_cipher()
        return cipher.decrypt(cipher_text.encode("utf-8")).decode("utf-8")
    except Exception:
        return ""
