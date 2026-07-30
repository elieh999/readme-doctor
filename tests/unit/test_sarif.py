"""Structural validation of the SARIF report against what GitHub code scanning requires.

This checks the properties GitHub reads during ingestion. It is not a complete validation of the
SARIF 2.1.0 schema, which would need a network fetch or a vendored schema copy.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from readme_doctor import scan_repository
from readme_doctor.models import Severity
from readme_doctor.reporters import render_sarif
from readme_doctor.rules import RULES

REQUIRED_RESULT_KEYS = {"ruleId", "level", "message", "locations"}
VALID_LEVELS = {"error", "warning", "note", "none"}


@pytest.fixture
def sarif(tmp_path: Path) -> dict[str, Any]:
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='demo'\nversion='1'\nrequires-python='>=3.12'\n", encoding="utf-8"
    )
    (tmp_path / "package.json").write_text('{"scripts": {"test": "vitest"}}', encoding="utf-8")
    (tmp_path / "README.md").write_text(
        "# Demo\n\nPython 3.9 or newer.\n\n"
        "[missing](docs/missing.md)\n[anchor](#absent)\n![](logo.png)\n\n"
        "```bash\nnpm run dev\n```\n\nTODO finish this\n",
        encoding="utf-8",
    )
    document: dict[str, Any] = json.loads(render_sarif(scan_repository(tmp_path)))
    return document


def test_top_level_shape(sarif: dict[str, Any]) -> None:
    assert sarif["version"] == "2.1.0"
    assert sarif["$schema"].startswith("https://")
    assert len(sarif["runs"]) == 1


def test_driver_metadata(sarif: dict[str, Any]) -> None:
    driver = sarif["runs"][0]["tool"]["driver"]
    assert driver["name"] == "README Doctor"
    assert driver["version"]
    assert driver["informationUri"].startswith("https://")
    assert driver["rules"], "at least one rule descriptor is expected"


def test_rule_descriptors_are_complete_and_registered(sarif: dict[str, Any]) -> None:
    for rule in sarif["runs"][0]["tool"]["driver"]["rules"]:
        assert rule["id"] in RULES
        assert rule["shortDescription"]["text"]
        assert rule["fullDescription"]["text"]
        assert rule["help"]["text"]
        assert rule["helpUri"].startswith("https://")
        assert rule["defaultConfiguration"]["level"] in VALID_LEVELS


def test_results_are_well_formed_and_reference_declared_rules(sarif: dict[str, Any]) -> None:
    run = sarif["runs"][0]
    declared = [rule["id"] for rule in run["tool"]["driver"]["rules"]]
    assert run["results"], "the fixture is expected to produce findings"
    for result in run["results"]:
        assert set(result) >= REQUIRED_RESULT_KEYS
        assert result["ruleId"] in declared
        assert declared[result["ruleIndex"]] == result["ruleId"]
        assert result["level"] in VALID_LEVELS
        assert result["message"]["text"]
        physical = result["locations"][0]["physicalLocation"]
        uri = physical["artifactLocation"]["uri"]
        assert "\\" not in uri, "URIs must use forward slashes"
        assert not uri.startswith("/"), "URIs must be relative for GitHub ingestion"
        if "region" in physical:
            assert physical["region"]["startLine"] >= 1
            assert physical["region"]["startColumn"] >= 1


def test_severity_mapping_matches_the_report(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Demo\n[missing](nope.md)\n[anchor](#absent)\n", encoding="utf-8"
    )
    report = scan_repository(tmp_path)
    document = json.loads(render_sarif(report))
    expected = {
        Severity.ERROR: "error",
        Severity.WARNING: "warning",
        Severity.NOTICE: "note",
    }
    for finding, result in zip(report.findings, document["runs"][0]["results"], strict=True):
        assert result["level"] == expected[finding.severity]
        assert result["ruleId"] == finding.rule_id


def test_clean_repository_produces_an_empty_result_set(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Demo\n\n## Installation\n\n## Usage\n\n## Testing\n\n## License\n", encoding="utf-8"
    )
    document = json.loads(render_sarif(scan_repository(tmp_path)))
    assert document["runs"][0]["results"] == []
    assert document["runs"][0]["tool"]["driver"]["rules"] == []
