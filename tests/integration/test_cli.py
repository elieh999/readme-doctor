from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from readme_doctor.cli import app

runner = CliRunner()


def test_cli_text_json_sarif_and_exit_codes(repository: Path) -> None:
    clean = runner.invoke(app, ["check", str(repository), "--no-color"])
    assert clean.exit_code == 0
    assert "0 errors" in clean.stdout
    assert clean.stdout.count("README Doctor") == 1
    (repository / "README.md").write_text("# Demo\nTODO\n", encoding="utf-8")
    normal = runner.invoke(app, ["check", str(repository), "--no-color"])
    assert normal.exit_code == 0
    strict = runner.invoke(app, ["check", str(repository), "--strict", "--no-color"])
    assert strict.exit_code == 1
    json_result = runner.invoke(app, ["check", str(repository), "--format", "json"])
    assert json.loads(json_result.stdout)["tool_version"] == "0.1.0"
    sarif = runner.invoke(app, ["check", str(repository), "--format", "sarif"])
    assert json.loads(sarif.stdout)["version"] == "2.1.0"


def test_cli_invalid_config_returns_two(repository: Path) -> None:
    config = repository / "bad.yml"
    config.write_text("version: 9\n", encoding="utf-8")
    result = runner.invoke(app, ["check", str(repository), "--config", str(config)])
    assert result.exit_code == 2


def test_init_does_not_overwrite(tmp_path: Path) -> None:
    config = tmp_path / "readme-doctor.yml"
    first = runner.invoke(app, ["init", str(config)])
    second = runner.invoke(app, ["init", str(config)])
    assert first.exit_code == 0
    assert second.exit_code == 2


def test_rules_and_fix_commands(tmp_path: Path) -> None:
    rules = runner.invoke(app, ["rules"])
    assert rules.exit_code == 0
    assert json.loads(rules.stdout)["RD001"]["name"] == "Missing README"
    (tmp_path / "README.md").write_text("# Demo\n```pyhton\npass\n```\n", encoding="utf-8")
    dry = runner.invoke(app, ["fix", str(tmp_path)])
    assert dry.exit_code == 0
    assert "+```python" in dry.stdout
    assert "```pyhton" in (tmp_path / "README.md").read_text(encoding="utf-8")
    applied = runner.invoke(app, ["fix", str(tmp_path), "--apply"])
    assert applied.exit_code == 0
    assert "```python" in (tmp_path / "README.md").read_text(encoding="utf-8")


def test_fix_without_readme_returns_two(tmp_path: Path) -> None:
    result = runner.invoke(app, ["fix", str(tmp_path)])
    assert result.exit_code == 2


def test_cli_requires_flag_even_when_config_enables_execution(
    repository: Path, monkeypatch: object
) -> None:
    config = repository / "execution.yml"
    config.write_text(
        "version: 1\nexecution:\n  enabled: true\n  verify_commands: [python --version]\n",
        encoding="utf-8",
    )
    result = runner.invoke(
        app, ["check", str(repository), "--config", str(config), "--format", "json"]
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["execution"]["enabled"] is False
