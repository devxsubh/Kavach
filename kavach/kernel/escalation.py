from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from ..advanced_models import EscalationRequest, EscalationStatus
from ..exceptions import GuardrailViolation
from ..world.db import Database


class EscalationGate:
    def __init__(self, db: Database, timeout_seconds: float = 30):
        self.db = db
        self.timeout_seconds = timeout_seconds

    def request(self, buyer_id: str, seller_id: str, amount_minor: int, reason: str) -> EscalationRequest:
        request = EscalationRequest(request_id=f"approval_{uuid4().hex[:12]}", buyer_id=buyer_id, seller_id=seller_id, amount_minor=amount_minor, reason=reason)
        self.db.save_escalation(request)
        self.db.append_audit("kernel", "ESCALATION_REQUESTED", request.model_dump(mode="json"))
        return request

    def decide(self, request: EscalationRequest, approved: bool, approval_ref: str | None = None) -> EscalationRequest:
        if request.expires_at <= datetime.now(timezone.utc):
            updated = request.model_copy(update={"status": EscalationStatus.TIMED_OUT})
            self.db.save_escalation(updated)
            self.db.append_audit("kernel", "ESCALATION_TIMED_OUT", {"request_id": request.request_id})
            raise GuardrailViolation("GR-12", "human approval timed out")
        status = EscalationStatus.APPROVED if approved else EscalationStatus.REFUSED
        updated = request.model_copy(update={"status": status, "approval_ref": approval_ref})
        self.db.save_escalation(updated)
        self.db.append_audit("human", "ESCALATION_DECIDED", updated.model_dump(mode="json"))
        if not approved:
            raise GuardrailViolation("GR-12", "human approval refused")
        return updated
