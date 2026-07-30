from __future__ import annotations

from readme_doctor.execution.redaction import redact
from readme_doctor.models import Finding, Report


def redacted_finding(finding: Finding) -> Finding:
    """Return a copy of the finding with credential shaped values removed."""
    return finding.model_copy(
        update={
            "explanation": redact(finding.explanation),
            "evidence": redact(finding.evidence),
            "suggestion": redact(finding.suggestion),
            "title": redact(finding.title),
        }
    )


def redacted_report(report: Report) -> Report:
    """Return a copy of the report with every free text field redacted.

    Redaction happens on the model rather than on serialized output. Rewriting a serialized
    document can consume a closing quote and produce invalid JSON or SARIF.
    """
    return report.model_copy(
        update={"findings": [redacted_finding(finding) for finding in report.findings]}
    )
