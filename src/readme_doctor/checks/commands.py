from __future__ import annotations

import json
import re
from pathlib import Path

from readme_doctor.checks.base import CheckContext
from readme_doctor.models import Confidence, Finding

# `npm run x` and `bun run x` are unambiguous. `yarn x` and `pnpm x` may be either a script or a
# builtin subcommand, so the manager name is captured and builtins are filtered out below.
PACKAGE_COMMAND = re.compile(
    r"\b(npm|pnpm|yarn|bun)\s+(?:(run)\s+)?(?:--\s+)?([\w:.@/-]+)",
)
# Builtin subcommands of pnpm and yarn, the two managers where `<manager> <name>` is also valid
# script shorthand. A README using one of these is not naming a package script, so reporting it as
# a missing script would be wrong. Script names such as `build`, `dev`, and `lint` are absent on
# purpose because neither manager implements them.
PACKAGE_SUBCOMMANDS = {
    "add",
    "audit",
    "autoclean",
    "bin",
    "cache",
    "check",
    "config",
    "create",
    "dedupe",
    "deploy",
    "dlx",
    "doctor",
    "env",
    "exec",
    "explain",
    "fetch",
    "generate-lock-entry",
    "global",
    "help",
    "import",
    "info",
    "init",
    "install",
    "install-test",
    "licenses",
    "link",
    "list",
    "ll",
    "login",
    "logout",
    "ls",
    "node",
    "npm",
    "outdated",
    "owner",
    "pack",
    "patch",
    "patch-commit",
    "patch-remove",
    "plugin",
    "policies",
    "prune",
    "publish",
    "rebuild",
    "remove",
    "root",
    "run",
    "self-update",
    "server",
    "set",
    "setup",
    "store",
    "tag",
    "team",
    "unlink",
    "unplug",
    "up",
    "upgrade",
    "upgrade-interactive",
    "version",
    "versions",
    "why",
    "workspace",
    "workspaces",
}
# Managers where the bare `<manager> <name>` form is idiomatic script shorthand.
SHORTHAND_MANAGERS = {"pnpm", "yarn"}
FILE_COMMAND = re.compile(
    r"(?:python(?:3)?\s+|powershell(?:\.exe)?\s+(?:-File\s+)?|pwsh\s+(?:-File\s+)?)?"
    r"((?:\./)?(?:scripts?|tools?)/[\w./\\ -]+\.(?:py|sh|ps1|js|ts|dart))"
)
MODULE_COMMAND = re.compile(r"\bpython(?:3)?\s+-m\s+([A-Za-z_][\w.]*)")
MAKE_COMMAND = re.compile(r"\bmake\s+([\w.-]+)")
KNOWN_EXTERNAL_MODULES = {
    "build",
    "coverage",
    "django",
    "flask",
    "http.server",
    "mypy",
    "pip",
    "pytest",
    "ruff",
    "uvicorn",
    "venv",
}


def _commands(context: CheckContext) -> list[tuple[str, int]]:
    commands: list[tuple[str, int]] = []
    shell_languages = {"bash", "sh", "shell", "console", "powershell", "ps1", "cmd"}
    for block in context.document.code_blocks:
        if block.language.casefold() not in shell_languages:
            continue
        for offset, command in enumerate(block.content.splitlines(), start=1):
            command = command.strip().removeprefix("$ ").removeprefix("> ")
            if command and not command.startswith("#"):
                commands.append((command, block.line + offset))
    return commands


def _package_scripts(context: CheckContext) -> set[str] | None:
    """Return every script name declared by the repository, or None when there is no manifest.

    Script names are collected from each `package.json` that is not ignored so that a monorepo
    documenting a workspace script in the root README does not produce a false finding.
    """
    manifests = [
        path for path in context.repository.files({".json"}) if path.name == "package.json"
    ]
    if not manifests:
        return None
    scripts: set[str] = set()
    for manifest in manifests:
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        declared = data.get("scripts") if isinstance(data, dict) else None
        if isinstance(declared, dict):
            scripts.update(str(name) for name in declared)
    return scripts


def check_commands(context: CheckContext) -> list[Finding]:
    findings: list[Finding] = []
    package_scripts = _package_scripts(context)
    makefile = context.repository.root / "Makefile"
    make_targets: set[str] = set()
    if makefile.is_file():
        make_targets = set(
            re.findall(
                r"^([A-Za-z0-9_.-]+)\s*:", makefile.read_text(encoding="utf-8"), re.MULTILINE
            )
        )
    for command, line in _commands(context):
        for match in PACKAGE_COMMAND.finditer(command):
            manager, explicit_run, script = match.group(1), match.group(2), match.group(3)
            if package_scripts is None:
                # No package.json anywhere in the repository, so there is nothing to compare
                # against. The README may be describing a separate project.
                continue
            if not explicit_run and (
                manager not in SHORTHAND_MANAGERS or script in PACKAGE_SUBCOMMANDS
            ):
                continue
            if script in package_scripts:
                continue
            finding = context.finding(
                "RD008",
                f"README references package script that is not defined: {script}",
                line=line,
                evidence=command,
                suggestion=f"Add `{script}` to package.json scripts or correct the command.",
                confidence=Confidence.HIGH if explicit_run else Confidence.MEDIUM,
            )
            if finding:
                findings.append(finding)
        for match in FILE_COMMAND.finditer(command):
            raw = match.group(1).replace("\\", "/").removeprefix("./")
            candidate = context.repository.safe_path(context.repository.root, raw)
            if candidate is None or not candidate.is_file():
                finding = context.finding(
                    "RD007",
                    f"README command references a missing script: {raw}",
                    line=line,
                    evidence=command,
                )
                if finding:
                    findings.append(finding)
        for match in MODULE_COMMAND.finditer(command):
            if match.group(1) in KNOWN_EXTERNAL_MODULES:
                continue
            module_path = Path(*match.group(1).split("."))
            candidates = [
                context.repository.root / f"{module_path}.py",
                context.repository.root / module_path / "__main__.py",
                context.repository.root / "src" / f"{module_path}.py",
                context.repository.root / "src" / module_path / "__main__.py",
            ]
            if not any(candidate.is_file() for candidate in candidates):
                finding = context.finding(
                    "RD007",
                    f"Python module referenced by README was not found: {match.group(1)}",
                    line=line,
                    evidence=command,
                    confidence=Confidence.MEDIUM,
                )
                if finding:
                    findings.append(finding)
        for match in MAKE_COMMAND.finditer(command):
            target = match.group(1)
            if makefile.is_file() and target not in make_targets:
                finding = context.finding(
                    "RD007",
                    f"README references a missing Make target: {target}",
                    line=line,
                    evidence=command,
                )
                if finding:
                    findings.append(finding)
    return findings
