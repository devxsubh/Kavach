from __future__ import annotations

import re
from dataclasses import dataclass

INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"system\s*:\s*",
    r"developer\s*:\s*",
    r"assistant\s*:\s*",
    r"reveal\s+(your|the)\s+(budget|prompt|instructions)",
    r"disregard\s+your\s+constraints",
]
ROLE_TOKENS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]|<\/?(system|user|assistant|developer)>|\[\/?INST\]", re.I)


@dataclass(frozen=True)
class FirewallResult:
    original: str
    sanitized: str
    flagged: bool
    reasons: tuple[str, ...]


class InputFirewall:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.patterns = [re.compile(p, re.I) for p in INJECTION_PATTERNS]

    def scan(self, text: str) -> FirewallResult:
        # When disabled the text passes through untouched; the unguarded baseline
        # must not benefit from quarantining.
        if not self.enabled:
            return FirewallResult(text, text, False, ())
        sanitized = ROLE_TOKENS.sub(" ", text).strip()
        reasons = tuple(p.pattern for p in self.patterns if p.search(text))
        flagged = bool(reasons)
        if flagged:
            sanitized = "[QUARANTINED UNTRUSTED TEXT]"
        return FirewallResult(text, sanitized, flagged, reasons)

    def data_block(self, label: str, text: str) -> str:
        result = self.scan(text)
        return f"<UNTRUSTED_DATA label={label!r}>\n{result.sanitized}\n</UNTRUSTED_DATA>"
