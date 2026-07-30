from __future__ import annotations

import json
from typing import Any

from readme_doctor.models import Report, Severity
from readme_doctor.reporters.redacted import redacted_report
from readme_doctor.rules import RULES

SARIF_SCHEMA = (
    "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json"
)
DOCUMENTATION_ROOT = "https://github.com/elieh999/readme-doctor/blob/main/docs/rules.md"

LEVELS = {
    Severity.ERROR: "error",
    Severity.WARNING: "warning",
    Severity.NOTICE: "note",
}


def _uri(path: str) -> str:
    """Return a relative POSIX style URI that GitHub code scanning accepts."""
    normalized = path.replace("\\", "/").lstrip("/")
    return normalized or "."


def render_sarif(report: Report) -> str:
    safe = redacted_report(report)
    used = sorted({finding.rule_id for finding in safe.findings})
    rule_index = {rule_id: index for index, rule_id in enumerate(used)}
    rules: list[dict[str, Any]] = [
        {
            "id": rule_id,
            "name": RULES[rule_id].name.title().replace(" ", ""),
            "shortDescription": {"text": RULES[rule_id].name},
            "fullDescription": {"text": RULES[rule_id].help},
            "help": {
                "text": RULES[rule_id].help,
                "markdown": f"{RULES[rule_id].help}\n\n[Rule documentation]"
                f"({DOCUMENTATION_ROOT}#{rule_id.lower()})",
            },
            "helpUri": f"{DOCUMENTATION_ROOT}#{rule_id.lower()}",
            "defaultConfiguration": {"level": LEVELS[RULES[rule_id].default_severity]},
            "properties": {"tags": ["documentation", "readme"]},
        }
        for rule_id in used
    ]
    results: list[dict[str, Any]] = []
    for finding in safe.findings:
        physical: dict[str, Any] = {"artifactLocation": {"uri": _uri(finding.path)}}
        if finding.line:
            physical["region"] = {
                "startLine": finding.line,
                "startColumn": finding.column or 1,
            }
        results.append(
            {
                "ruleId": finding.rule_id,
                "ruleIndex": rule_index[finding.rule_id],
                "level": LEVELS[finding.severity],
                "message": {"text": finding.explanation},
                "locations": [{"physicalLocation": physical}],
                "properties": {
                    "confidence": finding.confidence.value,
                    "evidence": finding.evidence,
                    "suggestion": finding.suggestion,
                },
            }
        )
    document = {
        "$schema": SARIF_SCHEMA,
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "README Doctor",
                        "version": safe.tool_version,
                        "semanticVersion": safe.tool_version,
                        "informationUri": "https://github.com/elieh999/readme-doctor",
                        "rules": rules,
                    }
                },
                "automationDetails": {"id": "readme-doctor/check"},
                "results": results,
            }
        ],
    }
    return json.dumps(document, indent=2) + "\n"
