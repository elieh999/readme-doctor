from __future__ import annotations

from dataclasses import dataclass

from readme_doctor.config import DoctorConfig
from readme_doctor.models import Confidence, Finding, Severity
from readme_doctor.parser import MarkdownDocument
from readme_doctor.repository import Repository
from readme_doctor.rules import RULES


@dataclass
class CheckContext:
    repository: Repository
    config: DoctorConfig
    document: MarkdownDocument

    @property
    def readme_path(self) -> str:
        return self.repository.relative(self.document.path)

    def finding(
        self,
        rule_id: str,
        explanation: str,
        *,
        line: int | None = None,
        evidence: str,
        suggestion: str | None = None,
        confidence: Confidence = Confidence.HIGH,
        fixable: bool = False,
        severity: Severity | None = None,
    ) -> Finding | None:
        if rule_id in self.config.rules.disabled or rule_id in self.config.ignore.rules:
            return None
        if self.document.is_suppressed(rule_id, line):
            return None
        rule = RULES[rule_id]
        return Finding(
            rule_id=rule_id,
            severity=severity or self.config.rules.severity.get(rule_id, rule.default_severity),
            title=rule.name,
            explanation=explanation,
            path=self.readme_path,
            line=line,
            column=1 if line else None,
            suggestion=suggestion or rule.help,
            evidence=evidence,
            confidence=confidence,
            fixable=fixable,
            documentation_url=f"https://github.com/elieh999/readme-doctor/blob/main/docs/rules.md#{rule_id.lower()}",
        )


def present(items: list[Finding | None]) -> list[Finding]:
    return [item for item in items if item is not None]
