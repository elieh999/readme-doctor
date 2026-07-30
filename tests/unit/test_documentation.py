"""Checks on the repository's own documentation.

The point of this project is that documentation drifts away from the code. These tests keep that
from happening here: every rule identifier, exit code, command, and image referenced by the
documentation is compared against what the code actually does.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

from readme_doctor import __version__, scan_repository
from readme_doctor.parser import parse_markdown
from readme_doctor.reporters.text import write_report
from readme_doctor.rules import RULES

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
RULES_DOC = ROOT / "docs" / "rules.md"
SCREENSHOT = ROOT / "docs" / "screenshots" / "terminal-demo.svg"
DEMO_FIXTURE = ROOT / "tests" / "fixtures" / "terminal_demo"
SKIP_DIRECTORIES = {".git", ".venv", ".package-test", ".docker-test", "node_modules", "dist"}

RULE_REFERENCE = re.compile(r"\bRD(\d{3})\b")


def markdown_files() -> list[Path]:
    return sorted(
        path
        for path in ROOT.rglob("*.md")
        if not any(part in SKIP_DIRECTORIES for part in path.relative_to(ROOT).parts)
        and "fixtures" not in path.relative_to(ROOT).parts
        and ".pytest_cache" not in path.relative_to(ROOT).parts
    )


# --- rule identifiers -------------------------------------------------------------------------


@pytest.mark.parametrize("document", markdown_files(), ids=lambda p: p.name)
def test_every_referenced_rule_identifier_exists(document: Path) -> None:
    text = document.read_text(encoding="utf-8")
    referenced = {f"RD{number}" for number in RULE_REFERENCE.findall(text)}
    unknown = sorted(referenced - RULES.keys())
    assert not unknown, f"{document.name} references rules that do not exist: {unknown}"


def test_the_rules_document_covers_every_registered_rule() -> None:
    text = RULES_DOC.read_text(encoding="utf-8")
    documented = {f"RD{number}" for number in RULE_REFERENCE.findall(text)}
    missing = sorted(RULES.keys() - documented)
    assert not missing, f"docs/rules.md is missing: {missing}"


def test_the_readme_rule_table_covers_every_registered_rule() -> None:
    text = README.read_text(encoding="utf-8")
    listed = {f"RD{number}" for number in RULE_REFERENCE.findall(text)}
    missing = sorted(RULES.keys() - listed)
    assert not missing, f"the README rule table is missing: {missing}"


def test_the_documented_default_severity_matches_the_registry() -> None:
    text = RULES_DOC.read_text(encoding="utf-8")
    for row in text.splitlines():
        match = re.match(r"\|\s*(RD\d{3})\s*\|\s*(\w+)\s*\|", row)
        if match is None:
            continue
        rule_id, documented = match.group(1), match.group(2).casefold()
        assert documented == RULES[rule_id].default_severity.value, (
            f"{rule_id} is documented as {documented} but defaults to "
            f"{RULES[rule_id].default_severity.value}"
        )


# --- links and images -------------------------------------------------------------------------


@pytest.mark.parametrize("document", markdown_files(), ids=lambda p: p.name)
def test_relative_links_and_images_resolve(document: Path) -> None:
    parsed = parse_markdown(document, set(RULES))
    problems: list[str] = []
    own_anchors = {heading.anchor for heading in parsed.headings}
    own_anchors |= {anchor.casefold() for anchor in parsed.explicit_anchors}
    for link in parsed.links:
        destination = link.destination.strip()
        if not destination or urlsplit(destination).scheme:
            continue
        target_text, _, fragment = destination.partition("#")
        if not target_text:
            if fragment.casefold() not in own_anchors:
                problems.append(f"line {link.line}: dead anchor #{fragment}")
            continue
        target = (document.parent / unquote(target_text)).resolve()
        if not target.exists():
            problems.append(f"line {link.line}: missing {target_text}")
    assert not problems, f"{document.name}: " + "; ".join(problems)


@pytest.mark.parametrize("document", markdown_files(), ids=lambda p: p.name)
def test_referenced_images_exist(document: Path) -> None:
    parsed = parse_markdown(document, set(RULES))
    for link in parsed.links:
        if not link.is_image or urlsplit(link.destination).scheme:
            continue
        target = (document.parent / unquote(link.destination)).resolve()
        assert target.is_file(), f"{document.name} line {link.line}: missing image"
        assert link.text.strip(), f"{document.name} line {link.line}: image needs alt text"


# --- the terminal screenshot ------------------------------------------------------------------


def test_the_screenshot_needs_no_network_access() -> None:
    """GitHub blocks external requests from README images, so the file must be self contained."""
    svg = SCREENSHOT.read_text(encoding="utf-8")
    assert "@font-face" not in svg
    assert "cdnjs" not in svg
    external = [
        url
        for url in re.findall(r"https?://[^\"')\s]+", svg)
        if "www.w3.org" not in url and "textualize.io" not in url
    ]
    assert not external, f"the screenshot references external resources: {external}"


def test_the_screenshot_matches_the_current_output() -> None:
    """A stale screenshot is exactly the drift this project exists to catch."""
    report = scan_repository(DEMO_FIXTURE)
    from io import StringIO

    from rich.console import Console

    buffer = StringIO()
    write_report(
        Console(file=buffer, width=100, color_system=None, highlight=False, no_color=True),
        report,
    )
    svg = SCREENSHOT.read_text(encoding="utf-8")
    for line in buffer.getvalue().splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        # SVG splits text into spans, so compare on the distinctive tokens rather than whole lines.
        for token in re.findall(r"RD\d{3}|README\.md:\d+:\d+", stripped):
            assert token in svg, (
                f"the screenshot is out of date: {token!r} is in the current output but not in "
                "the image. Regenerate it with: python scripts/capture_demo.py"
            )


def test_the_readme_shows_the_current_demo_output() -> None:
    """The output block in the README must be what the command prints today."""
    report = scan_repository(DEMO_FIXTURE)
    readme = README.read_text(encoding="utf-8")
    for finding in report.findings:
        assert finding.explanation in readme, (
            f"the README output block is out of date, missing: {finding.explanation}"
        )
    assert (
        f"{report.summary.errors} errors, {report.summary.warnings} warnings, "
        f"{report.summary.notices} notices"
    ) in readme


# --- commands and metadata --------------------------------------------------------------------


def test_the_documented_python_requirement_matches_the_project() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    requirement = data["project"]["requires-python"]
    minimum = re.search(r">=\s*(\d+\.\d+)", requirement)
    assert minimum is not None
    assert f"Python {minimum.group(1)} or newer" in README.read_text(encoding="utf-8")


def test_the_documented_version_matches_the_package() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["version"] == __version__
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## {__version__}" in changelog


def test_every_cli_command_named_in_the_readme_exists() -> None:
    from readme_doctor.cli import app

    registered = {
        command.name or (command.callback.__name__ if command.callback else "")
        for command in app.registered_commands
    }
    readme = README.read_text(encoding="utf-8")
    for command in re.findall(r"readme-doctor (\w[\w-]*)", readme):
        if command in {"check", "init", "fix", "rules"}:
            assert command in registered, f"the README documents a missing command: {command}"


def test_the_readme_documents_every_exit_code() -> None:
    readme = README.read_text(encoding="utf-8")
    for code in ("| 0 |", "| 1 |", "| 2 |"):
        assert code in readme, f"exit code row {code} is missing from the README"


def test_the_shipped_configuration_is_valid() -> None:
    from readme_doctor.config import load_config

    config = load_config(ROOT / "readme-doctor.yml")
    assert config.execution.enabled is False
    assert config.rules.remote_links.enabled is False


def test_the_project_passes_its_own_configured_check() -> None:
    """README Doctor must not report problems in its own README."""
    from readme_doctor.config import load_config

    report = scan_repository(ROOT, load_config(ROOT / "readme-doctor.yml"))
    assert report.findings == [], [
        f"{item.rule_id} {item.path}:{item.line} {item.explanation}" for item in report.findings
    ]
