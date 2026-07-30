from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    NOTICE = "notice"

    @property
    def rank(self) -> int:
        return {"notice": 1, "warning": 2, "error": 3}[self.value]


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Finding(BaseModel):
    rule_id: str
    severity: Severity
    title: str
    explanation: str
    path: str
    line: int | None = None
    column: int | None = None
    suggestion: str
    evidence: str
    confidence: Confidence
    fixable: bool = False
    documentation_url: str | None = None

    @property
    def message(self) -> str:
        return self.explanation

    def sort_key(self) -> tuple[str, int, int, str]:
        return (self.path.casefold(), self.line or 0, self.column or 0, self.rule_id)

    def identity(self) -> tuple[str, str, int, int, str]:
        """Values that make two findings the same reported problem."""
        return (self.rule_id, self.path, self.line or 0, self.column or 0, self.explanation)


class Summary(BaseModel):
    errors: int = 0
    warnings: int = 0
    notices: int = 0

    @classmethod
    def from_findings(cls, findings: list[Finding]) -> Summary:
        return cls(
            errors=sum(item.severity is Severity.ERROR for item in findings),
            warnings=sum(item.severity is Severity.WARNING for item in findings),
            notices=sum(item.severity is Severity.NOTICE for item in findings),
        )


class ExecutionMetadata(BaseModel):
    enabled: bool = False
    backend: str = "disabled"
    commands_considered: int = 0
    commands_executed: int = 0


class Report(BaseModel):
    tool_version: str = "0.1.0"
    repository: str
    readme_path: str | None
    findings: list[Finding] = Field(default_factory=list)
    summary: Summary = Field(default_factory=Summary)
    execution: ExecutionMetadata = Field(default_factory=ExecutionMetadata)
    scan_duration_seconds: float = 0.0
    enabled_rules: list[str] = Field(default_factory=list)

    def sorted(self) -> Report:
        """Deduplicate, order, and recount findings so output is stable."""
        unique: dict[tuple[str, str, int, int, str], Finding] = {}
        for finding in self.findings:
            unique.setdefault(finding.identity(), finding)
        self.findings = sorted(unique.values(), key=Finding.sort_key)
        self.summary = Summary.from_findings(self.findings)
        return self

    @property
    def repository_path(self) -> Path:
        return Path(self.repository)
