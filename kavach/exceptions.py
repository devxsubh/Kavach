from collections.abc import Sequence


class KavachError(Exception):
    """Base exception for expected Kavach failures."""


class GuardrailViolation(KavachError):
    """A refusal carrying every boundary that failed, not just the first."""

    def __init__(self, rule_id: str, message: str, violations: Sequence[tuple[str, str]] | None = None):
        self.rule_id = rule_id
        self.message = message
        self.violations: tuple[tuple[str, str], ...] = tuple(violations) if violations else ((rule_id, message),)
        super().__init__("; ".join(f"{rule}: {detail}" for rule, detail in self.violations))

    @property
    def rule_ids(self) -> tuple[str, ...]:
        return tuple(rule for rule, _ in self.violations)


class IllegalTransition(KavachError):
    pass


class SignatureError(KavachError):
    pass


class ReplayError(KavachError):
    pass


class ConfigError(KavachError):
    pass
