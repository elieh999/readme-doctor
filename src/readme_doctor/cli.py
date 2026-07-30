from __future__ import annotations

import json
import sys
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console

from readme_doctor.config import DEFAULT_CONFIG, ConfigError, RuleConfig, load_config
from readme_doctor.engine import scan_repository
from readme_doctor.fixes import language_fixes
from readme_doctor.models import Severity
from readme_doctor.reporters import render_json, render_sarif, render_text

app = typer.Typer(
    name="readme-doctor",
    help="Check whether README instructions still match the repository.",
    no_args_is_help=True,
)
console = Console(stderr=True)


class OutputFormat(StrEnum):
    TEXT = "text"
    JSON = "json"
    SARIF = "sarif"


def _exit_code(
    report_errors: int, report_warnings: int, report_notices: int, threshold: Severity
) -> int:
    if threshold is Severity.ERROR:
        return 1 if report_errors else 0
    if threshold is Severity.WARNING:
        return 1 if report_errors or report_warnings else 0
    return 1 if report_errors or report_warnings or report_notices else 0


@app.command()
def check(
    path: Annotated[Path, typer.Argument(help="Repository to inspect.")] = Path("."),
    output_format: Annotated[
        OutputFormat, typer.Option("--format", case_sensitive=False)
    ] = OutputFormat.TEXT,
    config_path: Annotated[
        Path | None, typer.Option("--config", exists=True, dir_okay=False)
    ] = None,
    strict: Annotated[bool, typer.Option(help="Fail on warnings and notices.")] = False,
    network: Annotated[
        bool | None, typer.Option("--network/--no-network", help="Validate remote links.")
    ] = None,
    execute: Annotated[
        bool, typer.Option(help="Run only configured commands in an isolated Docker container.")
    ] = False,
    no_color: Annotated[bool, typer.Option(help="Disable terminal color.")] = False,
    quiet: Annotated[bool, typer.Option(help="Print only the summary.")] = False,
    verbose: Annotated[bool, typer.Option(help="Print evidence and timing.")] = False,
    rule: Annotated[
        list[str] | None, typer.Option("--rule", help="Enable only selected rule identifiers.")
    ] = None,
    fail_on: Annotated[
        Severity, typer.Option(help="Lowest severity that causes exit code 1.")
    ] = Severity.ERROR,
    output: Annotated[Path | None, typer.Option(help="Write the report to a file.")] = None,
) -> None:
    """Inspect a repository without modifying it."""
    try:
        config = load_config(config_path)
        updates: dict[str, object] = {}
        if network is not None:
            updates["rules"] = config.rules.model_copy(
                update={
                    "remote_links": config.rules.remote_links.model_copy(
                        update={"enabled": network}
                    )
                }
            )
        updates["execution"] = config.execution.model_copy(update={"enabled": execute})
        if rule:
            unknown = sorted(set(rule) - set(config.enabled_rule_ids()))
            if unknown:
                raise ConfigError(f"unknown or disabled rule identifiers: {', '.join(unknown)}")
            current_rules = updates.get("rules", config.rules)
            assert isinstance(current_rules, RuleConfig)
            updates["rules"] = current_rules.model_copy(
                update={"disabled": sorted(set(config.enabled_rule_ids()) - set(rule))}
            )
        if updates:
            config = config.model_copy(update=updates)
        report = scan_repository(path, config)
    except (ConfigError, ValidationError, ValueError, OSError) as exc:
        console.print(f"[red]README Doctor configuration or tool error:[/red] {exc}")
        raise typer.Exit(2) from exc
    if output_format is OutputFormat.JSON:
        rendered = render_json(report)
    elif output_format is OutputFormat.SARIF:
        rendered = render_sarif(report)
    else:
        rendered = render_text(report, color=not no_color, quiet=quiet, verbose=verbose)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    else:
        typer.echo(rendered, nl=False)
    threshold = Severity.NOTICE if strict else fail_on
    raise typer.Exit(
        _exit_code(
            report.summary.errors,
            report.summary.warnings,
            report.summary.notices,
            threshold,
        )
    )


@app.command("init")
def initialize(
    path: Annotated[Path, typer.Argument(help="Configuration file to create.")] = Path(
        "readme-doctor.yml"
    ),
) -> None:
    """Create a starter configuration without overwriting files."""
    if path.exists():
        console.print(f"[red]Refusing to overwrite existing file:[/red] {path}")
        raise typer.Exit(2)
    path.write_text(DEFAULT_CONFIG, encoding="utf-8")
    console.print(f"Created {path}")


@app.command()
def fix(
    path: Annotated[Path, typer.Argument(help="Repository containing the README.")] = Path("."),
    apply: Annotated[
        bool, typer.Option("--apply", help="Apply safe language fence corrections.")
    ] = False,
) -> None:
    """Preview or apply deterministic fenced language corrections."""
    readme = next(
        (
            path / name
            for name in ("README.md", "Readme.md", "readme.md")
            if (path / name).is_file()
        ),
        None,
    )
    if readme is None:
        console.print("[red]No Markdown README found.[/red]")
        raise typer.Exit(2)
    result = language_fixes(readme, apply=apply)
    if not result.changed:
        console.print("No safe fixes available.")
        return
    typer.echo(result.diff)
    if not apply:
        console.print("Dry run only. Re-run with --apply to modify the README.")
    else:
        console.print(f"Updated {readme}. Review the diff in version control.")


@app.command("rules")
def list_rules() -> None:
    """Print the stable rule registry as JSON."""
    from readme_doctor.rules import RULES

    typer.echo(
        json.dumps(
            {
                identifier: {
                    "name": rule.name,
                    "default_severity": rule.default_severity,
                    "help": rule.help,
                }
                for identifier, rule in RULES.items()
            },
            indent=2,
        )
    )


def main() -> int:
    try:
        app()
    except SystemExit as exc:
        return int(exc.code or 0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
