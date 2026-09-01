from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .exceptions import SignatureError


def _default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone().isoformat()
    if isinstance(value, Enum):
        return value.value
    raise TypeError(f"unsupported canonical value: {type(value)!r}")


def canonical_bytes(value: Any) -> bytes:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, default=_default, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


class KeyPair:
    def __init__(self, private: Ed25519PrivateKey | None = None):
        self.private = private or Ed25519PrivateKey.generate()
        self.public = self.private.public_key()

    @property
    def public_b64(self) -> str:
        return base64.b64encode(self.public.public_bytes_raw()).decode()

    def sign(self, value: Any) -> str:
        return base64.b64encode(self.private.sign(canonical_bytes(value))).decode()

    @staticmethod
    def verify(public_b64: str, value: Any, signature: str) -> None:
        try:
            public = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_b64))
            public.verify(base64.b64decode(signature), canonical_bytes(value))
        except (InvalidSignature, ValueError, TypeError) as exc:
            raise SignatureError("signature verification failed") from exc
