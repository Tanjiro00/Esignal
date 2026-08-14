from __future__ import annotations

import base64
import hashlib
import secrets

from cryptography.fernet import Fernet, InvalidToken

TOKEN_ENCRYPTION_VERSION = "fernet-v1"


class TokenCipher:
    def __init__(self, key: str) -> None:
        if not key:
            raise ValueError("TOKEN_ENCRYPTION_KEY is not configured")
        try:
            self._fernet = Fernet(key.encode())
        except (TypeError, ValueError) as error:
            raise ValueError("TOKEN_ENCRYPTION_KEY must be a valid Fernet key") from error

    def encrypt(self, value: str) -> str:
        if not value:
            return ""
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        if not value:
            return ""
        try:
            return self._fernet.decrypt(value.encode()).decode()
        except InvalidToken as error:
            raise ValueError("Encrypted OAuth token cannot be decrypted") from error


def build_pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return verifier, challenge


def hash_oauth_state(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
