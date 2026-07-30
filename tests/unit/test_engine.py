from __future__ import annotations

import json
from pathlib import Path

from readme_doctor import DoctorConfig, scan_repository


def ids(path: Path, config: DoctorConfig | None = None) -> list[str]:
    return [finding.rule_id for finding in scan_repository(path, config).findings]


def test_clean_repository_has_no_findings(repository: Path) -> None:
    assert ids(repository) == []


def test_missing_readme(repository: Path) -> None:
    (repository / "README.md").unlink()
    assert ids(repository) == ["RD001"]


def test_links_anchors_images_code_and_placeholders(repository: Path) -> None:
    (repository / "README.md").write_text(
        "# Demo\n\n[missing](docs/missing.md)\n[anchor](#absent)\n![](image.png)\n"
        "```pyhton\n```\nTODO\n",
        encoding="utf-8",
    )
    found = ids(repository)
    assert {"RD002", "RD003", "RD004", "RD005", "RD006", "RD015"} <= set(found)


def test_scripts_and_package_scripts(repository: Path) -> None:
    (repository / "package.json").write_text(
        json.dumps({"scripts": {"test": "pytest"}}), encoding="utf-8"
    )
    (repository / "README.md").write_text(
        "# Demo\n\n```bash\nnpm run dev\npython scripts/setup.py\n```\n"
        "## Installation\n## Usage\n## Testing\n## License\n",
        encoding="utf-8",
    )
    found = ids(repository)
    assert "RD007" in found
    assert "RD008" in found


def test_standard_python_tool_modules_are_not_project_references(repository: Path) -> None:
    (repository / "README.md").write_text(
        "# Demo\n\n```bash\npython -m venv .venv\npython -m pip install .\npython -m build\n```\n"
        "## Installation\n## Usage\n## Testing\n## License\n",
        encoding="utf-8",
    )
    assert "RD007" not in ids(repository)


def test_version_mismatches(repository: Path) -> None:
    (repository / "pyproject.toml").write_text(
        "[project]\nname='demo'\nversion='1'\nrequires-python='>=3.12'\n", encoding="utf-8"
    )
    (repository / "package.json").write_text(
        json.dumps({"engines": {"node": ">=22"}}), encoding="utf-8"
    )
    (repository / "pubspec.yaml").write_text(
        "environment:\n  sdk: '>=3.5.0 <4.0.0'\n", encoding="utf-8"
    )
    (repository / "README.md").write_text(
        "# Demo\nPython 3.10 or newer. Node 18 or newer. Dart 3.2 or newer.\n"
        "## Installation\n## Usage\n## Testing\n## License\n",
        encoding="utf-8",
    )
    found = ids(repository)
    assert {"RD009", "RD010", "RD011"} <= set(found)


def test_environment_and_port_checks(repository: Path) -> None:
    (repository / "app.py").write_text(
        "import os\nvalue = os.getenv('DATABASE_URL')\n", encoding="utf-8"
    )
    (repository / ".env.example").write_text("API_TOKEN=\n", encoding="utf-8")
    (repository / "compose.yaml").write_text(
        "services:\n  app:\n    ports:\n      - '8000:8000'\n", encoding="utf-8"
    )
    (repository / "README.md").write_text(
        "# Demo\nOpen http://localhost:3000.\n## Installation\n## Usage\n## Testing\n## License\n",
        encoding="utf-8",
    )
    found = ids(repository)
    assert found.count("RD012") == 2
    assert "RD013" in found


def test_rule_disable_and_suppression(repository: Path) -> None:
    (repository / "README.md").write_text(
        "# Demo\n<!-- readme-doctor-disable RD015 -->\nTODO\n", encoding="utf-8"
    )
    config = DoctorConfig.model_validate({"rules": {"disabled": ["RD014"]}})
    assert "RD015" not in ids(repository, config)
    assert "RD014" not in ids(repository, config)


def test_path_traversal_and_symlink_escape_are_reported(repository: Path, tmp_path: Path) -> None:
    (repository / "README.md").write_text(
        "# Demo\n[outside](../../outside.txt)\n## Installation\n## Usage\n## Testing\n## License\n",
        encoding="utf-8",
    )
    assert "RD002" in ids(repository)
