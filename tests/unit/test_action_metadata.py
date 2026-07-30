"""The GitHub Action metadata, its runner script, and the workflows that use it."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
ACTION = ROOT / "action.yml"
RUNNER = ROOT / "scripts" / "run_action.py"
WORKFLOWS = ROOT / ".github" / "workflows"

EXPECTED_INPUTS = {
    "path",
    "config",
    "format",
    "strict",
    "network",
    "execute",
    "fail-severity",
    "output-path",
}
EXPECTED_OUTPUTS = {"errors", "warnings", "notices", "result", "report-path"}


@pytest.fixture(scope="module")
def action() -> dict[str, Any]:
    # BaseLoader keeps every scalar a string, which is how GitHub Actions treats input defaults.
    data: dict[str, Any] = yaml.load(ACTION.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    return data


def test_required_top_level_metadata(action: dict[str, Any]) -> None:
    assert action["name"]
    assert action["description"]
    assert action["branding"]["icon"]
    assert action["branding"]["color"]


def test_inputs_are_declared_documented_and_optional(action: dict[str, Any]) -> None:
    assert set(action["inputs"]) == EXPECTED_INPUTS
    for name, spec in action["inputs"].items():
        assert spec["description"], f"{name} needs a description"
        assert spec["required"] == "false", f"{name} must be optional"
        assert "default" in spec, f"{name} needs a default"


def test_dangerous_inputs_default_to_off(action: dict[str, Any]) -> None:
    assert action["inputs"]["execute"]["default"] == "false"
    assert action["inputs"]["network"]["default"] == "false"


def test_default_failure_severity_matches_the_cli_default(action: dict[str, Any]) -> None:
    assert action["inputs"]["fail-severity"]["default"] == "error"
    assert action["inputs"]["strict"]["default"] == "false"


def test_outputs_are_declared_and_wired_to_the_scan_step(action: dict[str, Any]) -> None:
    assert set(action["outputs"]) == EXPECTED_OUTPUTS
    for name, spec in action["outputs"].items():
        assert spec["description"], f"{name} needs a description"
        assert spec["value"] == f"${{{{ steps.scan.outputs.{name} }}}}"


def test_the_action_is_composite_and_declares_a_scan_step(action: dict[str, Any]) -> None:
    runs = action["runs"]
    assert runs["using"] == "composite"
    step_ids = [step.get("id") for step in runs["steps"]]
    assert "scan" in step_ids
    for step in runs["steps"]:
        if "run" in step:
            assert step["shell"] == "bash", "every run step needs an explicit shell"


def test_every_input_is_passed_to_the_runner_script(action: dict[str, Any]) -> None:
    scan = next(step for step in action["runs"]["steps"] if step.get("id") == "scan")
    for name in action["inputs"]:
        variable = f"INPUT_{name.replace('-', '_').upper()}"
        assert variable in scan["env"], f"{name} is declared but never passed to the runner"
        assert scan["env"][variable] == f"${{{{ inputs.{name} }}}}"


def test_the_runner_reads_exactly_the_variables_the_action_provides(action: dict[str, Any]) -> None:
    source = RUNNER.read_text(encoding="utf-8")
    for name in action["inputs"]:
        variable = f"INPUT_{name.replace('-', '_').upper()}"
        assert variable in source, f"{variable} is provided but the runner never reads it"


def test_the_runner_writes_every_declared_output(action: dict[str, Any]) -> None:
    source = RUNNER.read_text(encoding="utf-8")
    for name in action["outputs"]:
        assert name in source, f"{name} is declared as an output but the runner never writes it"


@pytest.mark.parametrize("workflow", sorted(WORKFLOWS.glob("*.yml")), ids=lambda p: p.name)
def test_workflows_parse_and_declare_minimal_permissions(workflow: Path) -> None:
    data = yaml.load(workflow.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    assert "permissions" in data, f"{workflow.name} must declare permissions explicitly"
    granted = data["permissions"]
    assert granted.get("contents") == "read"
    assert "write" not in str(granted.get("contents", ""))
    for job in data["jobs"].values():
        for step in job.get("steps", []):
            assert "continue-on-error" not in step, "required checks must not be skippable"


def test_no_workflow_enables_command_execution() -> None:
    for workflow in WORKFLOWS.glob("*.yml"):
        text = workflow.read_text(encoding="utf-8")
        assert "execute: 'true'" not in text
        assert 'execute: "true"' not in text


def _run_action(tmp_path: Path, **overrides: str) -> tuple[int, dict[str, str]]:
    """Run the action script the way action.yml does and return its exit code and outputs."""
    github_output = tmp_path / "github_output.txt"
    github_output.touch()
    environment = {
        **os.environ,
        "INPUT_PATH": str(tmp_path),
        "INPUT_CONFIG": "",
        "INPUT_FORMAT": "sarif",
        "INPUT_STRICT": "false",
        "INPUT_NETWORK": "false",
        "INPUT_EXECUTE": "false",
        "INPUT_FAIL_SEVERITY": "error",
        "INPUT_OUTPUT_PATH": str(tmp_path / "readme-doctor.sarif"),
        "GITHUB_OUTPUT": str(github_output),
        **overrides,
    }
    completed = subprocess.run(
        [sys.executable, str(RUNNER)],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )
    outputs: dict[str, str] = {}
    for line in github_output.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            outputs[key] = value
    return completed.returncode, outputs


def test_the_action_reports_counts_and_a_failing_result(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Demo\n\n[missing](docs/missing.md)\nTODO finish\n", encoding="utf-8"
    )
    code, outputs = _run_action(tmp_path)
    assert code == 1
    assert outputs["errors"] == "1"
    assert outputs["warnings"] == "1"
    assert outputs["result"] == "fail"
    assert outputs["report-path"].endswith("readme-doctor.sarif")
    sarif = json.loads((tmp_path / "readme-doctor.sarif").read_text(encoding="utf-8"))
    assert sarif["version"] == "2.1.0"


def test_the_action_reports_a_passing_result_for_a_clean_repository(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Demo\n\n## Installation\n\n## Usage\n\n## Testing\n\n## License\n", encoding="utf-8"
    )
    code, outputs = _run_action(tmp_path)
    assert code == 0
    assert outputs == {
        "errors": "0",
        "warnings": "0",
        "notices": "0",
        "result": "pass",
        "report-path": str(tmp_path / "readme-doctor.sarif"),
    }


def test_strict_mode_turns_a_notice_into_a_failure(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\n\n```\n```\n", encoding="utf-8")
    lenient_code, lenient = _run_action(tmp_path)
    strict_code, strict = _run_action(tmp_path, INPUT_STRICT="true")
    assert lenient_code == 0
    assert lenient["result"] == "pass"
    assert strict_code == 1
    assert strict["result"] == "fail"
    assert strict["notices"] == lenient["notices"]


def test_counts_describe_the_same_scan_as_the_exit_code(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\n\n[missing](a.md)\n", encoding="utf-8")
    for output_format in ("text", "json", "sarif"):
        code, outputs = _run_action(tmp_path, INPUT_FORMAT=output_format)
        assert code == 1, output_format
        assert outputs["errors"] == "1", output_format
        assert outputs["result"] == "fail", output_format


def test_an_invalid_format_input_is_refused(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    code, _ = _run_action(tmp_path, INPUT_FORMAT="html")
    assert code != 0


def test_an_invalid_severity_input_is_refused(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    code, _ = _run_action(tmp_path, INPUT_FAIL_SEVERITY="critical")
    assert code != 0
