"""Encrypted secret storage helpers for native connections."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from typing import Any

from fastapi import HTTPException

from src.app.core.settings import Settings, get_settings


def ensure_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


class SecretVault:
    """Versioned local secret envelope for access and refresh tokens."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def _key(self) -> bytes:
        raw = self._settings.aethos_secrets_key
        if not raw:
            raise HTTPException(status_code=503, detail="AETHOS_SECRETS_KEY is required for native connections.")
        return hashlib.sha256(raw.encode("utf-8")).digest()

    @staticmethod
    def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
        stream = bytearray()
        counter = 0
        while len(stream) < length:
            counter_bytes = counter.to_bytes(8, "big")
            stream.extend(hashlib.blake2b(nonce + counter_bytes, key=key, digest_size=32).digest())
            counter += 1
        return bytes(stream[:length])

    def encrypt(self, payload: dict[str, Any]) -> str:
        key = self._key()
        nonce = secrets.token_bytes(16)
        plaintext = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        keystream = self._keystream(key, nonce, len(plaintext))
        ciphertext = bytes(a ^ b for a, b in zip(plaintext, keystream, strict=False))
        mac = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
        envelope = {
            "version": 1,
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
            "mac": base64.b64encode(mac).decode("ascii"),
        }
        return json.dumps(envelope, separators=(",", ":"))

    def decrypt(self, envelope_text: str) -> dict[str, Any]:
        key = self._key()
        try:
            envelope = json.loads(envelope_text)
            nonce = base64.b64decode(str(envelope["nonce"]))
            ciphertext = base64.b64decode(str(envelope["ciphertext"]))
            received_mac = base64.b64decode(str(envelope["mac"]))
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Stored connection secret is invalid.") from exc
        expected_mac = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(received_mac, expected_mac):
            raise HTTPException(status_code=500, detail="Stored connection secret failed integrity check.")
        keystream = self._keystream(key, nonce, len(ciphertext))
        plaintext = bytes(a ^ b for a, b in zip(ciphertext, keystream, strict=False))
        try:
            data = json.loads(plaintext.decode("utf-8"))
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Stored connection secret is unreadable.") from exc
        return ensure_dict(data)


__all__ = ["SecretVault", "ensure_dict"]
