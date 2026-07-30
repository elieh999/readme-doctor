from __future__ import annotations

from pathlib import Path
from time import perf_counter

from readme_doctor.checks.base import CheckContext
from readme_doctor.checks.commands import check_commands
from readme_doctor.checks.markdown import (
    check_badges,
    check_code_blocks,
    check_images,
    check_links,
    check_sections_and_placeholders,
)
from readme_doctor.checks.project import check_environment, check_ports, check_versions
from readme_doctor.config import DoctorConfig
from readme_doctor.execution import execute_configured_commands
from readme_doctor.models import Confidence, ExecutionMetadata, Finding, Report, Severity
from readme_doctor.network import check_remote_links
from readme_doctor.parser import parse_markdown
from readme_doctor.repository import Repository
from readme_doctor.rules import RULES

DOCUMENTATION_ROOT = "https://github.com/elieh999/readme-doctor/blob/main/docs/rules.md"

CHECKS = [
    check_links,
    check_images,
    check_code_blocks,
    check_commands,
    check_versions,
    check_environment,
    check_ports,
    check_sections_and_placeholders,
    check_badges,
    check_remote_links,
]


def scan_repository(repository: Path, config: DoctorConfig | None = None) -> Report:
    started = perf_counter()
    config = config or DoctorConfig()
    repo = Repository(repository, config)
    if not repo.root.is_dir():
        raise ValueError(f"repository path is not a directory: {repository}")
    readme = repo.find_readme()
    if readme is None:
        finding = Finding(
            rule_id="RD001",
            severity=config.rules.severity.get("RD001", Severity.ERROR),
            title=RULES["RD001"].name,
            explanation="No recognized README file exists at the repository root.",
            path=".",
            suggestion=RULES["RD001"].help,
            evidence=", ".join(config.readme.paths),
            confidence=Confidence.HIGH,
            fixable=False,
            documentation_url=f"{DOCUMENTATION_ROOT}#rd001",
        )
        missing_findings = [finding] if "RD001" in config.enabled_rule_ids() else []
        return Report(
            repository=str(repo.root),
            readme_path=None,
            findings=missing_findings,
            enabled_rules=config.enabled_rule_ids(),
            scan_duration_seconds=perf_counter() - started,
        ).sorted()
    if readme.suffix.casefold() != ".md":
        # Only Markdown is parsed. Saying so is important, because an empty report would otherwise
        # read as a clean result rather than as analysis that did not run.
        relative = repo.relative(readme)
        unanalyzed = Finding(
            rule_id="RD021",
            severity=config.rules.severity.get("RD021", RULES["RD021"].default_severity),
            title=RULES["RD021"].name,
            explanation=(
                f"{relative} was found but only Markdown READMEs are analyzed, "
                "so no content rules ran."
            ),
            path=relative,
            suggestion=RULES["RD021"].help,
            evidence=f"suffix={readme.suffix}",
            confidence=Confidence.HIGH,
            documentation_url=f"{DOCUMENTATION_ROOT}#rd021",
        )
        return Report(
            repository=str(repo.root),
            readme_path=relative,
            findings=[unanalyzed] if "RD021" in config.enabled_rule_ids() else [],
            enabled_rules=config.enabled_rule_ids(),
            scan_duration_seconds=perf_counter() - started,
        ).sorted()
    document = parse_markdown(readme, set(RULES))
    context = CheckContext(repo, config, document)
    findings: list[Finding] = []
    for line, unknown in document.suppression_errors:
        suppression_finding = context.finding(
            "RD019",
            f"Suppression references unknown rule identifier: {unknown}",
            line=line,
            evidence=unknown,
        )
        if suppression_finding:
            findings.append(suppression_finding)
    for check in CHECKS:
        findings.extend(check(context))
    execution = ExecutionMetadata()
    if config.execution.enabled:
        execution_findings, execution = execute_configured_commands(context)
        findings.extend(execution_findings)
    return Report(
        repository=str(repo.root),
        readme_path=repo.relative(readme),
        findings=findings,
        execution=execution,
        enabled_rules=config.enabled_rule_ids(),
        scan_duration_seconds=perf_counter() - started,
    ).sorted()
