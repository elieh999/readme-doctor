"""Command line options that change filtering, thresholds, and output destination."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from readme_doctor.cli import app

runner = CliRunner()

NOISY = (
    "# Demo\n\n[missing](docs/missing.md)\n[anchor](#absent)\n![](logo.png)\n\nTODO finish this\n"
)


@pytest.fixture
def noisy(tmp_path: Path) -> Path:
    (tmp_path / "README.md").write_text(NOISY, encoding="utf-8")
    return tmp_path


def _ids(path: Path, *options: str) -> list[str]:
    result = runner.invoke(app, ["check", str(path), "--format", "json", *options])
    payload = json.loads(result.stdout)
    return [finding["rule_id"] for finding in payload["findings"]]


def test_rule_filter_restricts_the_run(noisy: Path) -> None:
    assert set(_ids(noisy, "--rule", "RD002")) == {"RD002"}


def test_rule_filter_accepts_several_identifiers(noisy: Path) -> None:
    assert set(_ids(noisy, "--rule", "RD002", "--rule", "RD003")) == {"RD002", "RD003"}


def test_rule_filter_rejects_an_unknown_identifier(noisy: Path) -> None:
    result = runner.invoke(app, ["check", str(noisy), "--rule", "RD404"])
    assert result.exit_code == 2
    assert "RD404" in result.stderr


def test_rule_filter_rejects_a_rule_disabled_by_configuration(noisy: Path) -> None:
    config = noisy / "readme-doctor.yml"
    config.write_text("version: 1\nrules:\n  disabled: [RD002]\n", encoding="utf-8")
    result = runner.invoke(app, ["check", str(noisy), "--config", str(config), "--rule", "RD002"])
    assert result.exit_code == 2


def test_enabled_rules_are_reported_in_json(noisy: Path) -> None:
    result = runner.invoke(app, ["check", str(noisy), "--format", "json", "--rule", "RD002"])
    assert json.loads(result.stdout)["enabled_rules"] == ["RD002"]


@pytest.mark.parametrize(
    ("threshold", "expected"),
    [("error", 1), ("warning", 1), ("notice", 1)],
)
def test_fail_on_threshold(noisy: Path, threshold: str, expected: int) -> None:
    result = runner.invoke(app, ["check", str(noisy), "--fail-on", threshold, "--no-color"])
    assert result.exit_code == expected


def test_fail_on_error_passes_when_only_warnings_exist(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\nTODO finish\n", encoding="utf-8")
    error_only = runner.invoke(app, ["check", str(tmp_path), "--fail-on", "error", "--no-color"])
    warning = runner.invoke(app, ["check", str(tmp_path), "--fail-on", "warning", "--no-color"])
    assert error_only.exit_code == 0
    assert warning.exit_code == 1


def test_notice_threshold_fails_on_a_notice_only_report(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\n\n```\n```\n", encoding="utf-8")
    notice = runner.invoke(app, ["check", str(tmp_path), "--fail-on", "notice", "--no-color"])
    warning = runner.invoke(app, ["check", str(tmp_path), "--fail-on", "warning", "--no-color"])
    assert notice.exit_code == 1
    assert warning.exit_code == 0


@pytest.mark.parametrize("output_format", ["text", "json", "sarif"])
def test_output_file_is_written_and_nothing_goes_to_stdout(
    noisy: Path, tmp_path: Path, output_format: str
) -> None:
    destination = tmp_path / "reports" / f"report.{output_format}"
    result = runner.invoke(
        app,
        [
            "check",
            str(noisy),
            "--format",
            output_format,
            "--output",
            str(destination),
            "--no-color",
        ],
    )
    assert result.exit_code == 1
    assert destination.is_file()
    assert result.stdout == ""
    content = destination.read_text(encoding="utf-8")
    assert content
    if output_format != "text":
        json.loads(content)


def test_quiet_prints_only_the_summary(noisy: Path) -> None:
    result = runner.invoke(app, ["check", str(noisy), "--quiet", "--no-color"])
    assert "Summary" in result.stdout
    assert "RD002" not in result.stdout


def test_verbose_adds_evidence_and_timing(noisy: Path) -> None:
    result = runner.invoke(app, ["check", str(noisy), "--verbose", "--no-color"])
    assert "Evidence:" in result.stdout
    assert "Confidence:" in result.stdout
    assert "Scanned in" in result.stdout


def test_no_color_output_contains_no_escape_sequences(noisy: Path) -> None:
    result = runner.invoke(app, ["check", str(noisy), "--no-color"])
    assert "\x1b[" not in result.stdout


def test_findings_are_sorted_by_location(noisy: Path) -> None:
    result = runner.invoke(app, ["check", str(noisy), "--format", "json"])
    findings = json.loads(result.stdout)["findings"]
    assert findings, "the fixture is expected to produce findings"
    positions = [(item["path"], item["line"] or 0, item["rule_id"]) for item in findings]
    assert positions == sorted(positions)


def test_repeated_runs_produce_identical_output(noisy: Path) -> None:
    first = runner.invoke(app, ["check", str(noisy), "--format", "json"]).stdout
    second = runner.invoke(app, ["check", str(noisy), "--format", "json"]).stdout
    # The scan duration is the only field expected to vary between runs.
    assert json.loads(first)["findings"] == json.loads(second)["findings"]
    assert json.loads(
        runner.invoke(app, ["check", str(noisy), "--format", "sarif"]).stdout
    ) == json.loads(runner.invoke(app, ["check", str(noisy), "--format", "sarif"]).stdout)


def test_paths_in_json_use_forward_slashes(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\n[missing](nope.md)\n", encoding="utf-8")
    result = runner.invoke(app, ["check", str(tmp_path), "--format", "json"])
    payload = json.loads(result.stdout)
    assert payload["readme_path"] == "README.md"
    for finding in payload["findings"]:
        assert "\\" not in finding["path"]


def test_unicode_content_renders(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Café ☕ Sétup\n\n[missing](dócs/nöpe.md)\n[anchor](#café--sétup)\n", encoding="utf-8"
    )
    result = runner.invoke(app, ["check", str(tmp_path), "--no-color"])
    assert result.exit_code == 1
    assert "dócs/nöpe.md" in result.stdout


def test_a_missing_directory_reports_a_tool_error(tmp_path: Path) -> None:
    result = runner.invoke(app, ["check", str(tmp_path / "absent")])
    assert result.exit_code == 2
    assert "not a directory" in result.stderr


def test_a_file_given_instead_of_a_directory_reports_a_tool_error(tmp_path: Path) -> None:
    target = tmp_path / "README.md"
    target.write_text("# Demo\n", encoding="utf-8")
    result = runner.invoke(app, ["check", str(target)])
    assert result.exit_code == 2
