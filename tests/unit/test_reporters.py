from __future__ import annotations

import json
from pathlib import Path

from readme_doctor import scan_repository
from readme_doctor.reporters import render_json, render_sarif, render_text


def test_reporters_are_valid_and_deterministic(repository: Path) -> None:
    (repository / "README.md").write_text("# Demo\nTODO\n", encoding="utf-8")
    report = scan_repository(repository)
    payload = json.loads(render_json(report))
    assert payload["summary"]["warnings"] == 1
    sarif = json.loads(render_sarif(report))
    assert sarif["version"] == "2.1.0"
    assert sarif["runs"][0]["results"][0]["ruleId"] == report.findings[0].rule_id
    text = render_text(report, color=False, verbose=True)
    assert "README Doctor" in text
    assert "Summary" in text
