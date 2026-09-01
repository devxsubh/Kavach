from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

import requests

from ..config import KavachConfig
from ..exceptions import ConfigError
from .base import ExternalOrder

RAZORPAY_API = "https://api.razorpay.com/v1"


class RazorpayRail:
    """Razorpay test-mode adapter via REST (no razorpay SDK / pkg_resources).

    Never called when the kernel refuses checkout.
    """

    provider = "razorpay"

    def __init__(self, config: KavachConfig, session: requests.Session | None = None):
        if not config.razorpay_key_id or not config.razorpay_key_secret:
            raise ConfigError("Razorpay rail requires RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET")
        self.key_id = config.razorpay_key_id
        self.key_secret = config.razorpay_key_secret
        self.webhook_secret = config.razorpay_webhook_secret or config.razorpay_key_secret
        self._session = session or requests.Session()
        self._session.auth = (self.key_id, self.key_secret)
        self._session.headers.update({"Content-Type": "application/json"})

    def create_order(
        self,
        *,
        amount_minor: int,
        currency: str = "INR",
        receipt: str,
        notes: dict[str, str] | None = None,
    ) -> ExternalOrder:
        # Razorpay INR amounts are in paise (= Kavach minor units).
        payload = {
            "amount": int(amount_minor),
            "currency": currency,
            "receipt": receipt[:40],
            "notes": notes or {},
            "payment_capture": 1,
        }
        response = self._session.post(f"{RAZORPAY_API}/orders", data=json.dumps(payload), timeout=30)
        if response.status_code >= 400:
            raise ConfigError(f"Razorpay order create failed: {response.status_code} {response.text}")
        created = response.json()
        return ExternalOrder(
            provider=self.provider,
            external_id=created["id"],
            amount_minor=int(created["amount"]),
            currency=created.get("currency", currency),
            raw=dict(created),
        )

    def verify_payment_signature(self, order_id: str, payment_id: str, signature: str) -> bool:
        message = f"{order_id}|{payment_id}".encode()
        expected = hmac.new(self.key_secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature or "")

    def verify_webhook_signature(self, body: bytes, signature: str) -> bool:
        expected = hmac.new(self.webhook_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature or "")


class FakeRazorpayRail:
    """In-memory stand-in for tests — no network."""

    provider = "razorpay"

    def __init__(self, key_id: str = "rzp_test_fake", key_secret: str = "secret"):
        self.key_id = key_id
        self.key_secret = key_secret
        self.webhook_secret = key_secret
        self.created: list[ExternalOrder] = []
        self._seq = 0

    def create_order(
        self,
        *,
        amount_minor: int,
        currency: str = "INR",
        receipt: str,
        notes: dict[str, str] | None = None,
    ) -> ExternalOrder:
        self._seq += 1
        order = ExternalOrder(
            provider=self.provider,
            external_id=f"order_fake_{self._seq:04d}",
            amount_minor=amount_minor,
            currency=currency,
            raw={"id": f"order_fake_{self._seq:04d}", "amount": amount_minor, "receipt": receipt, "notes": notes or {}},
        )
        self.created.append(order)
        return order

    def verify_payment_signature(self, order_id: str, payment_id: str, signature: str) -> bool:
        message = f"{order_id}|{payment_id}".encode()
        expected = hmac.new(self.key_secret.encode(), message, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def verify_webhook_signature(self, body: bytes, signature: str) -> bool:
        expected = hmac.new(self.webhook_secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def sign_payment(self, order_id: str, payment_id: str) -> str:
        message = f"{order_id}|{payment_id}".encode()
        return hmac.new(self.key_secret.encode(), message, hashlib.sha256).hexdigest()

    def sign_webhook(self, body: bytes | dict) -> str:
        raw = body if isinstance(body, bytes) else json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
        return hmac.new(self.webhook_secret.encode(), raw, hashlib.sha256).hexdigest()
