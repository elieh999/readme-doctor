from __future__ import annotations

import re
from urllib.parse import urlsplit

from readme_doctor.checks.base import CheckContext
from readme_doctor.models import Confidence, Finding

KNOWN_LANGUAGES = {
    "",
    "text",
    "plaintext",
    "console",
    "bash",
    "sh",
    "shell",
    "powershell",
    "ps1",
    "cmd",
    "python",
    "py",
    "javascript",
    "js",
    "typescript",
    "ts",
    "json",
    "yaml",
    "yml",
    "toml",
    "xml",
    "html",
    "css",
    "scss",
    "sql",
    "dart",
    "dockerfile",
    "makefile",
    "markdown",
    "md",
}
MISSPELLINGS = {
    "pyhton": "python",
    "javascrpt": "javascript",
    "powershel": "powershell",
    "yalm": "yaml",
    "shelll": "shell",
}
PLACEHOLDERS = [
    "todo",
    "tbd",
    "coming soon",
    "replace this",
    "your project name",
    "insert screenshot here",
    "lorem ipsum",
]
# Whole word matching keeps a phrase such as `todo` from firing inside an unrelated identifier.
PLACEHOLDER_PATTERNS = {
    phrase: re.compile(rf"(?<![\w-]){re.escape(phrase)}(?![\w-])", re.IGNORECASE)
    for phrase in PLACEHOLDERS
}
INLINE_CODE = re.compile(r"`[^`]*`")
LINK_TARGET = re.compile(r"\]\([^)]*\)")
BARE_URL = re.compile(r"<?\bhttps?://\S+>?")


def _prose(line: str) -> str:
    """Strip inline code, link targets, and bare URLs so only human readable text remains."""
    without_code = INLINE_CODE.sub(" ", line)
    without_targets = LINK_TARGET.sub("]", without_code)
    return BARE_URL.sub(" ", without_targets)


def _remote(destination: str) -> bool:
    return urlsplit(destination).scheme.lower() in {"http", "https", "mailto", "tel", "data"}


def check_links(context: CheckContext) -> list[Finding]:
    findings: list[Finding] = []
    anchors = {heading.anchor for heading in context.document.headings}
    anchors |= {anchor.casefold() for anchor in context.document.explicit_anchors}
    for link in context.document.links:
        destination = link.destination.strip()
        if not destination or _remote(destination):
            continue
        if destination.startswith("#"):
            requested = destination[1:].casefold()
            if requested not in anchors:
                finding = context.finding(
                    "RD003",
                    f"Internal anchor does not exist: #{requested}",
                    line=link.line,
                    evidence=destination,
                    suggestion="Update the fragment to match a README heading or explicit anchor.",
                )
                if finding:
                    findings.append(finding)
            continue
        path_text, _, fragment = destination.partition("#")
        candidate = context.repository.safe_path(context.document.path.parent, path_text)
        if candidate is None:
            finding = context.finding(
                "RD002",
                f"Local reference escapes the repository: {path_text}",
                line=link.line,
                evidence=destination,
                suggestion="Use a path that remains inside the repository.",
            )
            if finding:
                findings.append(finding)
            continue
        exists, case_difference = context.repository.case_sensitive_exists(candidate)
        if not exists or case_difference:
            reason = "has a case mismatch" if exists else "does not exist"
            finding = context.finding(
                "RD002",
                f"Referenced path {reason}: {path_text}",
                line=link.line,
                evidence=destination,
                suggestion="Correct the path and its letter casing.",
            )
            if finding:
                findings.append(finding)
        elif fragment and candidate.suffix.lower() == ".md":
            try:
                from readme_doctor.parser import parse_markdown

                target = parse_markdown(candidate, set())
                if fragment.casefold() not in {heading.anchor for heading in target.headings}:
                    finding = context.finding(
                        "RD003",
                        f"Anchor does not exist in {path_text}: #{fragment}",
                        line=link.line,
                        evidence=destination,
                    )
                    if finding:
                        findings.append(finding)
            except OSError:
                pass
    return findings


def check_images(context: CheckContext) -> list[Finding]:
    findings: list[Finding] = []
    ignored = set(context.config.rules.decorative_images)
    for link in context.document.links:
        if link.is_image and not link.text.strip() and link.destination not in ignored:
            finding = context.finding(
                "RD004",
                "Image has empty alternative text.",
                line=link.line,
                evidence=link.destination,
                suggestion="Add concise alternative text or configure it as decorative.",
            )
            if finding:
                findings.append(finding)
    return findings


def check_code_blocks(context: CheckContext) -> list[Finding]:
    findings: list[Finding] = []
    known = KNOWN_LANGUAGES | set(context.config.rules.known_code_languages)
    for block in context.document.code_blocks:
        if not block.fenced:
            # An indented block has no fence and no language, so neither rule applies to it.
            continue
        if not block.content.strip():
            finding = context.finding(
                "RD005",
                "Fenced code block is empty.",
                line=block.line,
                evidence=f"language={block.language or '(none)'}",
            )
            if finding:
                findings.append(finding)
        language = block.language.casefold()
        if language not in known:
            suggestion = MISSPELLINGS.get(language)
            finding = context.finding(
                "RD006",
                f"Unknown fenced code language: {block.language}",
                line=block.line,
                evidence=block.language,
                suggestion=(
                    f"Change the language to `{suggestion}`."
                    if suggestion
                    else "Use a recognized language or add it to configuration."
                ),
                confidence=Confidence.HIGH if suggestion else Confidence.MEDIUM,
                fixable=suggestion is not None,
            )
            if finding:
                findings.append(finding)
    return findings


def check_sections_and_placeholders(context: CheckContext) -> list[Finding]:
    findings: list[Finding] = []
    required = context.config.rules.required_sections
    existing = {heading.text.strip().casefold() for heading in context.document.headings}
    if required.enabled:
        for section in required.sections:
            if section.strip().casefold() not in existing:
                finding = context.finding(
                    "RD014",
                    f"Configured README section is missing: {section}",
                    evidence=section,
                    severity=required.severity,
                    confidence=Confidence.HIGH,
                )
                if finding:
                    findings.append(finding)
    ignored = {phrase.casefold() for phrase in context.config.rules.ignored_placeholders}
    code_lines = context.document.code_lines()
    for line_number, line in enumerate(context.document.text.splitlines(), start=1):
        if line_number in code_lines:
            continue
        plain = _prose(line)
        for phrase in PLACEHOLDERS:
            if phrase in ignored:
                continue
            if PLACEHOLDER_PATTERNS[phrase].search(plain):
                finding = context.finding(
                    "RD015",
                    f"README contains unfinished placeholder text: {phrase}",
                    line=line_number,
                    evidence=line.strip()[:160],
                    suggestion="Replace the placeholder with finished documentation.",
                )
                if finding:
                    findings.append(finding)
                break
    return findings


def check_badges(context: CheckContext) -> list[Finding]:
    """Report badge images whose URL is malformed.

    Only destinations that are meant to be absolute are inspected. A badge stored in the
    repository is a relative path, which is perfectly valid, and its existence is already RD002's
    responsibility. Checking it here would report one problem under two rules.
    """
    findings: list[Finding] = []
    for link in context.document.links:
        if not link.is_image:
            continue
        destination = link.destination.strip()
        lower = destination.casefold()
        if "badge" not in lower and "shields.io" not in lower:
            continue
        parsed = urlsplit(destination)
        # A relative path has no scheme and no leading `//`. Leave those to RD002.
        if not parsed.scheme and not destination.startswith("//"):
            continue
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            finding = context.finding(
                "RD016",
                f"Badge image URL is not a valid absolute URL: {destination}",
                line=link.line,
                evidence=destination,
                suggestion=(
                    "Use a complete https URL, or a relative path to a badge in the repository."
                ),
            )
            if finding:
                findings.append(finding)
    return findings
