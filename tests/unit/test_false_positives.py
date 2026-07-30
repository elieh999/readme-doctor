"""Regression tests proving that ordinary, correct repositories stay quiet.

Each test here encodes a real false positive that the checker produced at some point. A
documentation checker that reports weak guesses as facts stops being useful, so these are
treated as first class behavior.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from readme_doctor import DoctorConfig, scan_repository

SECTIONS = "\n## Installation\n\n## Usage\n\n## Testing\n\n## License\n"


def ids(path: Path, config: DoctorConfig | None = None) -> list[str]:
    return [finding.rule_id for finding in scan_repository(path, config).findings]


def write(path: Path, name: str, content: str) -> None:
    (path / name).write_text(content, encoding="utf-8")


def test_package_manager_subcommands_are_not_scripts(tmp_path: Path) -> None:
    write(tmp_path, "package.json", json.dumps({"scripts": {"dev": "vite"}}))
    write(
        tmp_path,
        "README.md",
        "# Demo\n\n```bash\nnpm install\nnpm ci\nyarn install\nyarn add react\n"
        "yarn remove react\npnpm install\npnpm add -D vitest\npnpm dlx tsc\n"
        "bun install\nyarn why react\nnpm run dev\n```\n" + SECTIONS,
    )
    assert "RD008" not in ids(tmp_path)


def test_missing_script_is_still_reported(tmp_path: Path) -> None:
    write(tmp_path, "package.json", json.dumps({"scripts": {"dev": "vite"}}))
    write(tmp_path, "README.md", "# Demo\n\n```bash\nnpm run build\n```\n" + SECTIONS)
    assert "RD008" in ids(tmp_path)


def test_shorthand_script_is_reported_for_pnpm_and_yarn(tmp_path: Path) -> None:
    write(tmp_path, "package.json", json.dumps({"scripts": {"dev": "vite"}}))
    write(tmp_path, "README.md", "# Demo\n\n```bash\npnpm build\nyarn lint\n```\n" + SECTIONS)
    found = ids(tmp_path)
    assert found.count("RD008") == 2


def test_package_scripts_are_not_checked_without_a_manifest(tmp_path: Path) -> None:
    """A Python project whose README mentions a separate frontend must not be flagged."""
    write(tmp_path, "README.md", "# Demo\n\n```bash\nnpm run dev\n```\n" + SECTIONS)
    assert "RD008" not in ids(tmp_path)


def test_workspace_scripts_in_a_monorepo_are_found(tmp_path: Path) -> None:
    write(tmp_path, "package.json", json.dumps({"private": True}))
    (tmp_path / "web").mkdir()
    write(tmp_path / "web", "package.json", json.dumps({"scripts": {"dev": "vite"}}))
    write(tmp_path, "README.md", "# Demo\n\n```bash\nnpm run dev\n```\n" + SECTIONS)
    assert "RD008" not in ids(tmp_path)


def test_documented_host_port_matches_a_compose_mapping(tmp_path: Path) -> None:
    """`3000:8000` publishes container port 8000 on host port 3000, so `localhost:3000` is right."""
    write(tmp_path, "compose.yaml", 'services:\n  web:\n    ports:\n      - "3000:8000"\n')
    write(tmp_path, "README.md", "# Demo\n\nOpen http://localhost:3000.\n" + SECTIONS)
    assert "RD013" not in ids(tmp_path)


def test_bound_address_in_a_compose_mapping_is_handled(tmp_path: Path) -> None:
    write(
        tmp_path, "compose.yaml", 'services:\n  web:\n    ports:\n      - "127.0.0.1:3000:8000"\n'
    )
    write(tmp_path, "README.md", "# Demo\n\nOpen http://localhost:3000.\n" + SECTIONS)
    assert "RD013" not in ids(tmp_path)


def test_genuine_port_mismatch_is_still_reported(tmp_path: Path) -> None:
    write(tmp_path, "compose.yaml", 'services:\n  web:\n    ports:\n      - "8080:8000"\n')
    write(tmp_path, "README.md", "# Demo\n\nOpen http://localhost:3000.\n" + SECTIONS)
    assert "RD013" in ids(tmp_path)


def test_acronyms_in_prose_are_not_environment_variables(tmp_path: Path) -> None:
    write(tmp_path, "app.py", "import os\nvalue = os.environ['DATABASE_URL']\n")
    write(tmp_path, ".env.example", "DATABASE_URL=\nMIT=\n")
    write(
        tmp_path,
        "README.md",
        "# Demo\n\nThis MIT licensed CLI emits JSON and SARIF output for CI use.\n\n"
        "Set `DATABASE_URL` before running.\n" + SECTIONS,
    )
    findings = scan_repository(tmp_path).findings
    variables = [item.evidence for item in findings if item.rule_id == "RD012"]
    # MIT is only an acronym in the prose, so it must not count as documented.
    assert any("MIT" in evidence for evidence in variables)
    assert not any("DATABASE_URL" in evidence for evidence in variables)


def test_an_underscored_name_mentioned_in_prose_counts_as_documented(tmp_path: Path) -> None:
    write(tmp_path, ".env.example", "DATABASE_URL=\n")
    write(
        tmp_path,
        "README.md",
        "# Demo\n\nDATABASE_URL configures the database connection.\n" + SECTIONS,
    )
    assert "RD012" not in ids(tmp_path)


def test_a_bare_acronym_does_not_count_as_documented(tmp_path: Path) -> None:
    write(tmp_path, ".env.example", "DEBUG=\n")
    write(tmp_path, "README.md", "# Demo\n\nDEBUG output is verbose.\n" + SECTIONS)
    assert "RD012" in ids(tmp_path)


def test_an_acronym_in_backticks_counts_as_documented(tmp_path: Path) -> None:
    write(tmp_path, ".env.example", "DEBUG=\n")
    write(tmp_path, "README.md", "# Demo\n\nSet `DEBUG` to enable verbose output.\n" + SECTIONS)
    assert "RD012" not in ids(tmp_path)


def test_a_variable_gap_is_reported_once(tmp_path: Path) -> None:
    write(tmp_path, "app.py", "import os\nvalue = os.environ['REDIS_URL']\n")
    write(tmp_path, ".env.example", "OTHER=\n")
    write(tmp_path, "README.md", "# Demo\n\nSet `REDIS_URL` before starting.\n" + SECTIONS)
    findings = [item for item in scan_repository(tmp_path).findings if item.rule_id == "RD012"]
    redis = [item for item in findings if "REDIS_URL" in item.evidence]
    assert len(redis) == 1


def test_a_repeated_version_requirement_is_reported_once(tmp_path: Path) -> None:
    write(
        tmp_path, "pyproject.toml", "[project]\nname='d'\nversion='1'\nrequires-python='>=3.12'\n"
    )
    write(
        tmp_path,
        "README.md",
        "# Demo\n\nNeeds Python 3.9 or newer. We suggest Python 3.9. Minimum is Python 3.9.\n"
        + SECTIONS,
    )
    assert ids(tmp_path).count("RD009") == 1


def test_matching_versions_produce_nothing(tmp_path: Path) -> None:
    write(
        tmp_path, "pyproject.toml", "[project]\nname='d'\nversion='1'\nrequires-python='>=3.11'\n"
    )
    write(tmp_path, "package.json", json.dumps({"engines": {"node": ">=20"}}))
    write(tmp_path, "README.md", "# Demo\n\nPython 3.11 or newer. Node 20 or newer.\n" + SECTIONS)
    found = ids(tmp_path)
    assert "RD009" not in found
    assert "RD010" not in found


def test_a_newer_documented_version_is_not_a_mismatch(tmp_path: Path) -> None:
    write(
        tmp_path, "pyproject.toml", "[project]\nname='d'\nversion='1'\nrequires-python='>=3.11'\n"
    )
    write(tmp_path, "README.md", "# Demo\n\nTested on Python 3.13.\n" + SECTIONS)
    assert "RD009" not in ids(tmp_path)


def test_placeholder_words_inside_identifiers_are_ignored(tmp_path: Path) -> None:
    write(
        tmp_path,
        "README.md",
        "# Demo\n\nThe todos module lives in `src/todo_list.py` and is described at "
        "https://example.com/todo-app in the mastodon integration notes.\n" + SECTIONS,
    )
    assert "RD015" not in ids(tmp_path)


def test_a_real_placeholder_is_still_reported(tmp_path: Path) -> None:
    write(tmp_path, "README.md", "# Demo\n\nTODO write the setup steps.\n" + SECTIONS)
    assert "RD015" in ids(tmp_path)


def test_standard_tooling_modules_are_not_project_modules(tmp_path: Path) -> None:
    write(
        tmp_path,
        "README.md",
        "# Demo\n\n```bash\npython -m venv .venv\npython -m pip install .\n"
        "python -m pytest\npython -m build\npython -m http.server\n```\n" + SECTIONS,
    )
    assert "RD007" not in ids(tmp_path)


def test_decorative_image_configuration_silences_alt_text(tmp_path: Path) -> None:
    write(tmp_path, "divider.png", "x")
    write(tmp_path, "README.md", "# Demo\n\n![](divider.png)\n" + SECTIONS)
    config = DoctorConfig.model_validate({"rules": {"decorative_images": ["divider.png"]}})
    assert "RD004" not in ids(tmp_path, config)


@pytest.mark.parametrize("name", [".venv", "venv", ".package-test", "env311", "myenv"])
def test_virtual_environments_are_skipped_whatever_they_are_called(
    tmp_path: Path, name: str
) -> None:
    """A virtual environment is recognized by `pyvenv.cfg`, not by its directory name.

    Without this, scanning a repository that happens to contain an environment reports every
    variable used by every installed dependency.
    """
    write(tmp_path, "README.md", "# Demo\n" + SECTIONS)
    environment = tmp_path / name / "Lib" / "site-packages" / "somedep"
    environment.mkdir(parents=True)
    write(tmp_path / name, "pyvenv.cfg", "home = /usr\n")
    write(environment, "config.py", "import os\nos.environ['DEPENDENCY_ONLY_VARIABLE']\n")
    assert "DEPENDENCY_ONLY_VARIABLE" not in scan_repository(tmp_path).model_dump_json()


@pytest.mark.parametrize(
    "directory", ["node_modules", "site-packages", "__pycache__", ".tox", ".git", ".dart_tool"]
)
def test_dependency_and_cache_directories_are_skipped(tmp_path: Path, directory: str) -> None:
    write(tmp_path, "README.md", "# Demo\n" + SECTIONS)
    nested = tmp_path / directory
    nested.mkdir()
    write(nested, "leak.py", "import os\nos.environ['VENDORED_VARIABLE']\n")
    assert "VENDORED_VARIABLE" not in scan_repository(tmp_path).model_dump_json()


@pytest.mark.parametrize(
    "variable",
    [
        "PATH",
        "HOME",
        "APPDATA",
        "EDITOR",
        "TERM",
        "TMPDIR",
        "XDG_CACHE_HOME",
        "PYTHONPATH",
        "GITHUB_TOKEN",
        "VIRTUAL_ENV",
        "PIP_INDEX_URL",
        "JAVA_HOME",
        "ANDROID_ROOT",
        "HTTPS_PROXY",
        "LC_ALL",
        "CI",
    ],
)
def test_platform_variables_are_not_treated_as_project_configuration(
    tmp_path: Path, variable: str
) -> None:
    write(tmp_path, "README.md", "# Demo\n" + SECTIONS)
    write(tmp_path, "app.py", f"import os\nvalue = os.environ['{variable}']\n")
    assert "RD012" not in ids(tmp_path)


def test_a_project_variable_is_still_reported_alongside_platform_variables(tmp_path: Path) -> None:
    write(tmp_path, "README.md", "# Demo\n" + SECTIONS)
    write(
        tmp_path,
        "app.py",
        "import os\nos.environ['PATH']\nos.environ['HOME']\nos.environ['STRIPE_API_KEY']\n",
    )
    findings = [item for item in scan_repository(tmp_path).findings if item.rule_id == "RD012"]
    assert [item.evidence for item in findings] == ["variable=STRIPE_API_KEY; source=code"]


def test_remote_links_are_not_treated_as_local_paths(tmp_path: Path) -> None:
    write(
        tmp_path,
        "README.md",
        "# Demo\n\n[site](https://example.com/docs/setup.md)\n"
        "[mail](mailto:team@example.com)\n[phone](tel:+15550100)\n" + SECTIONS,
    )
    assert "RD002" not in ids(tmp_path)
