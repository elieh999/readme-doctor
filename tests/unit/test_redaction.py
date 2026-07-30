"""Secret redaction, including the requirement that it never corrupt structured output."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from readme_doctor.execution.redaction import redact
from readme_doctor.models import Confidence, Finding, Report, Severity
from readme_doctor.reporters import redacted_report, render_json, render_sarif, render_text

SECRETS = [
    ("api_key=supersecretvalue", "supersecretvalue"),
    ("API-KEY: supersecretvalue", "supersecretvalue"),
    ("Authorization: Bearer abcdefghijklmnopqrstuvwxyz", "abcdefghijklmnopqrstuvwxyz"),
    ("authorization: basic YWxhZGRpbjpvcGVuc2VzYW1l", "YWxhZGRpbjpvcGVuc2VzYW1l"),
    ("password=hunter2hunter2", "hunter2hunter2"),
    ("access_token = abc123def456", "abc123def456"),
    ("secret: topsecretmaterial", "topsecretmaterial"),
    ("ghp_abcdefghijklmnopqrstuvwxyz123456", "ghp_abcdefghijklmnopqrstuvwxyz123456"),
    ("ghs_abcdefghijklmnopqrstuvwxyz123456", "ghs_abcdefghijklmnopqrstuvwxyz123456"),
    ("AKIAIOSFODNN7EXAMPLE", "AKIAIOSFODNN7EXAMPLE"),
    ("ASIAIOSFODNN7EXAMPLE", "ASIAIOSFODNN7EXAMPLE"),
    ("postgres://user:hunter2@localhost/db", "hunter2"),
    ("mongodb+srv://admin:letmein@cluster0.example.net", "letmein"),
    ("redis://default:cachepass@127.0.0.1:6379", "cachepass"),
    (
        "-----BEGIN RSA PRIVATE KEY-----\nMIIBOgIBAAJBAK\n-----END RSA PRIVATE KEY-----",
        "MIIBOgIBAAJBAK",
    ),
]


@pytest.mark.parametrize(("text", "secret"), SECRETS, ids=[item[1][:18] for item in SECRETS])
def test_secret_values_are_removed(text: str, secret: str) -> None:
    assert secret not in redact(text)


def test_redaction_keeps_surrounding_context() -> None:
    assert redact("Set password=hunter2hunter2 in config") == ("Set password=[REDACTED] in config")
    assert redact("no credentials here") == "no credentials here"


def _report(value: str) -> Report:
    finding = Finding(
        rule_id="RD012",
        severity=Severity.WARNING,
        title="Environment variable documentation",
        explanation=f"Documented as {value}",
        path="README.md",
        line=4,
        column=1,
        suggestion=f"Remove {value}",
        evidence=value,
        confidence=Confidence.HIGH,
    )
    return Report(repository=".", readme_path="README.md", findings=[finding]).sorted()


# A value whose secret sits at the end of the field is the case that previously consumed the
# closing quote of the serialized string and produced an unparseable document.
CORRUPTING_VALUES = [
    "password: hunter2",
    "token=abcdefghijklmn",
    "Authorization: Bearer abcdefghijklmnop",
    "postgres://user:hunter2@db.internal/app",
    "api_key=abc123",
]


@pytest.mark.parametrize("value", CORRUPTING_VALUES)
def test_json_output_stays_parseable_after_redaction(value: str) -> None:
    payload = json.loads(render_json(_report(value)))
    serialized = json.dumps(payload)
    assert "hunter2" not in serialized
    assert "abcdefghijklmn" not in serialized
    assert "abc123" not in serialized


@pytest.mark.parametrize("value", CORRUPTING_VALUES)
def test_sarif_output_stays_parseable_after_redaction(value: str) -> None:
    document = json.loads(render_sarif(_report(value)))
    serialized = json.dumps(document)
    assert "hunter2" not in serialized
    assert "abcdefghijklmn" not in serialized
    assert "abc123" not in serialized


@pytest.mark.parametrize("value", CORRUPTING_VALUES)
def test_text_output_is_redacted(value: str) -> None:
    text = render_text(_report(value), color=False, verbose=True)
    assert "hunter2" not in text
    assert "abcdefghijklmn" not in text
    assert "abc123" not in text
    assert "[REDACTED]" in text


def test_redaction_does_not_mutate_the_source_report() -> None:
    report = _report("password: hunter2")
    redacted_report(report)
    assert report.findings[0].evidence == "password: hunter2"


def test_findings_carrying_brackets_are_not_treated_as_markup(tmp_path: Path) -> None:
    finding = Finding(
        rule_id="RD002",
        severity=Severity.ERROR,
        title="Missing local reference",
        explanation="Referenced path does not exist: docs/[guide]/setup.md",
        path="README.md",
        line=2,
        column=1,
        suggestion="Correct the path.",
        evidence="docs/[guide]/setup.md",
        confidence=Confidence.HIGH,
    )
    report = Report(repository=str(tmp_path), readme_path="README.md", findings=[finding]).sorted()
    text = render_text(report, color=False, verbose=True)
    assert "docs/[guide]/setup.md" in text
