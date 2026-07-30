from __future__ import annotations

from io import StringIO

from rich.console import Console
from rich.text import Text

from readme_doctor.models import Report, Severity
from readme_doctor.reporters.redacted import redacted_report

COLORS = {
    Severity.ERROR: "bold red",
    Severity.WARNING: "bold yellow",
    Severity.NOTICE: "bold cyan",
}


def write_report(
    console: Console,
    report: Report,
    *,
    quiet: bool = False,
    verbose: bool = False,
) -> None:
    """Write the human readable report to a console.

    Both the string reporter and the documentation screenshot use this function so that the two
    cannot drift apart. Every value taken from the repository is printed as literal text: rendering
    it as Rich markup would silently drop anything inside square brackets.
    """
    safe = redacted_report(report)
    if not quiet:
        console.print(Text("README Doctor", style="bold"))
        console.print()
        for finding in safe.findings:
            location = finding.path
            if finding.line:
                location += f":{finding.line}:{finding.column or 1}"
            heading = Text(f"{location}  {finding.severity.value.upper()} {finding.rule_id}")
            heading.stylize(COLORS[finding.severity])
            console.print(heading)
            console.print(Text(finding.explanation))
            if verbose:
                console.print(Text(f"Evidence: {finding.evidence}", style="dim"))
                console.print(Text(f"Suggestion: {finding.suggestion}", style="dim"))
                console.print(Text(f"Confidence: {finding.confidence.value}", style="dim"))
            console.print()
    summary = safe.summary
    console.print(Text("Summary", style="bold"))
    console.print(
        Text(f"{summary.errors} errors, {summary.warnings} warnings, {summary.notices} notices")
    )
    if verbose:
        console.print(Text(f"Scanned in {safe.scan_duration_seconds:.3f}s", style="dim"))
        if safe.execution.enabled:
            console.print(
                Text(
                    f"Execution backend {safe.execution.backend}: "
                    f"{safe.execution.commands_executed} of "
                    f"{safe.execution.commands_considered} commands ran",
                    style="dim",
                )
            )


def render_text(
    report: Report,
    *,
    color: bool = True,
    quiet: bool = False,
    verbose: bool = False,
) -> str:
    buffer = StringIO()
    console = Console(
        file=buffer,
        force_terminal=color,
        color_system="standard" if color else None,
        width=100,
        highlight=False,
        soft_wrap=False,
    )
    write_report(console, report, quiet=quiet, verbose=verbose)
    return buffer.getvalue()
