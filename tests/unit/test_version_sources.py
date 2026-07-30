"""Each supported declaration file is read and attributed correctly."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from readme_doctor import scan_repository
from readme_doctor.models import Finding

SECTIONS = "\n## Installation\n\n## Usage\n\n## Testing\n\n## License\n"


def _finding(path: Path, rule_id: str) -> Finding | None:
    for finding in scan_repository(path).findings:
        if finding.rule_id == rule_id:
            return finding
    return None


def _require(path: Path, rule_id: str) -> Finding:
    finding = _finding(path, rule_id)
    assert finding is not None, f"expected {rule_id}"
    return finding


def _evidence(path: Path, rule_id: str) -> str:
    return _require(path, rule_id).evidence


@pytest.mark.parametrize(
    ("name", "content", "source"),
    [
        (
            "pyproject.toml",
            "[project]\nname='d'\nversion='1'\nrequires-python='>=3.12'\n",
            "pyproject.toml project.requires-python",
        ),
        (".python-version", "3.12.4\n", ".python-version"),
        ("setup.cfg", "[options]\npython_requires = >=3.12\n", "setup.cfg python_requires"),
        (
            "setup.py",
            'from setuptools import setup\nsetup(python_requires=">=3.12")\n',
            "setup.py python_requires",
        ),
    ],
)
def test_python_requirement_sources(tmp_path: Path, name: str, content: str, source: str) -> None:
    (tmp_path / name).write_text(content, encoding="utf-8")
    (tmp_path / "README.md").write_text(
        "# Demo\n\nRequires Python 3.9 or newer.\n" + SECTIONS, encoding="utf-8"
    )
    assert source in _evidence(tmp_path, "RD009")


def test_pyproject_takes_precedence_over_a_version_file(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='d'\nversion='1'\nrequires-python='>=3.12'\n", encoding="utf-8"
    )
    (tmp_path / ".python-version").write_text("3.10\n", encoding="utf-8")
    (tmp_path / "README.md").write_text(
        "# Demo\n\nRequires Python 3.9 or newer.\n" + SECTIONS, encoding="utf-8"
    )
    assert "pyproject.toml" in _evidence(tmp_path, "RD009")


def test_malformed_pyproject_is_ignored_without_crashing(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project\nbroken = \n", encoding="utf-8")
    (tmp_path / "README.md").write_text(
        "# Demo\n\nRequires Python 3.9 or newer.\n" + SECTIONS, encoding="utf-8"
    )
    assert _finding(tmp_path, "RD009") is None


@pytest.mark.parametrize(
    ("name", "content", "source"),
    [
        ("package.json", json.dumps({"engines": {"node": ">=22"}}), "package.json engines.node"),
        (".nvmrc", "22.4.0\n", ".nvmrc"),
        (".node-version", "v22.4.0\n", ".node-version"),
    ],
)
def test_node_requirement_sources(tmp_path: Path, name: str, content: str, source: str) -> None:
    (tmp_path / name).write_text(content, encoding="utf-8")
    (tmp_path / "README.md").write_text(
        "# Demo\n\nRequires Node 18 or newer.\n" + SECTIONS, encoding="utf-8"
    )
    assert source in _evidence(tmp_path, "RD010")


def test_malformed_package_json_is_ignored_without_crashing(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "README.md").write_text(
        "# Demo\n\nRequires Node 18 or newer.\n" + SECTIONS, encoding="utf-8"
    )
    assert _finding(tmp_path, "RD010") is None


def test_pubspec_dart_and_flutter_are_reported_separately(tmp_path: Path) -> None:
    (tmp_path / "pubspec.yaml").write_text(
        "name: demo\nenvironment:\n  sdk: '>=3.5.0 <4.0.0'\n  flutter: '>=3.24.0'\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(
        "# Demo\n\nNeeds Dart 3.2 and Flutter 3.19.\n" + SECTIONS, encoding="utf-8"
    )
    findings = [item for item in scan_repository(tmp_path).findings if item.rule_id == "RD011"]
    sources = " ".join(item.evidence for item in findings)
    assert "environment.sdk" in sources
    assert "environment.flutter" in sources


def test_fvmrc_overrides_the_pubspec_flutter_constraint(tmp_path: Path) -> None:
    (tmp_path / "pubspec.yaml").write_text(
        "name: demo\nenvironment:\n  flutter: '>=3.10.0'\n", encoding="utf-8"
    )
    (tmp_path / ".fvmrc").write_text(json.dumps({"flutter": "3.24.0"}), encoding="utf-8")
    (tmp_path / "README.md").write_text(
        "# Demo\n\nNeeds Flutter 3.19.\n" + SECTIONS, encoding="utf-8"
    )
    assert ".fvmrc" in _evidence(tmp_path, "RD011")


def test_malformed_pubspec_is_ignored_without_crashing(tmp_path: Path) -> None:
    (tmp_path / "pubspec.yaml").write_text("environment: [unclosed\n", encoding="utf-8")
    (tmp_path / "README.md").write_text(
        "# Demo\n\nNeeds Flutter 3.19.\n" + SECTIONS, encoding="utf-8"
    )
    assert _finding(tmp_path, "RD011") is None


def test_no_version_is_reported_when_the_readme_says_nothing(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='d'\nversion='1'\nrequires-python='>=3.12'\n", encoding="utf-8"
    )
    (tmp_path / "README.md").write_text("# Demo\n" + SECTIONS, encoding="utf-8")
    assert _finding(tmp_path, "RD009") is None


def test_make_targets_are_compared_only_when_a_makefile_exists(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Demo\n\n```bash\nmake build\n```\n" + SECTIONS, encoding="utf-8"
    )
    assert _finding(tmp_path, "RD007") is None
    (tmp_path / "Makefile").write_text("test:\n\tpytest\n", encoding="utf-8")
    assert "build" in _require(tmp_path, "RD007").explanation


def test_a_referenced_script_is_accepted_when_present(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "setup.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "README.md").write_text(
        "# Demo\n\n```bash\npython scripts/setup.py\n```\n" + SECTIONS, encoding="utf-8"
    )
    assert _finding(tmp_path, "RD007") is None
