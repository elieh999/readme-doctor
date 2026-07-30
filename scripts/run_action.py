"""Entry point used by action.yml to run README Doctor and publish step outputs."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

FORMATS = {"text", "json", "sarif"}
SEVERITIES = {"error", "warning", "notice"}


def truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().casefold() in {"1", "true", "yes", "on"}


def _required(name: str, allowed: set[str] | None = None) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"README Doctor action: {name} is empty")
    if allowed is not None and value.casefold() not in allowed:
        raise SystemExit(
            f"README Doctor action: {name} must be one of {', '.join(sorted(allowed))}, "
            f"received {value}"
        )
    return value


def _base_command(output_format: str, output_path: Path) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "readme_doctor",
        "check",
        _required("INPUT_PATH"),
        "--format",
        output_format,
        "--fail-on",
        _required("INPUT_FAIL_SEVERITY", SEVERITIES).casefold(),
        "--output",
        str(output_path),
        "--no-color",
    ]
    config = os.environ.get("INPUT_CONFIG", "").strip()
    if config:
        command.extend(["--config", config])
    if truthy("INPUT_STRICT"):
        command.append("--strict")
    command.append("--network" if truthy("INPUT_NETWORK") else "--no-network")
    if truthy("INPUT_EXECUTE"):
        command.append("--execute")
    return command


def _counts(payload: object) -> dict[str, int]:
    counts = {"errors": 0, "warnings": 0, "notices": 0}
    if isinstance(payload, dict):
        summary = payload.get("summary")
        if isinstance(summary, dict):
            for name in counts:
                value = summary.get(name)
                if isinstance(value, int):
                    counts[name] = value
    return counts


def main() -> int:
    output_format = _required("INPUT_FORMAT", FORMATS).casefold()
    output_path = Path(_required("INPUT_OUTPUT_PATH"))

    # The requested report is written to the output path. Counts come from a JSON copy of the same
    # scan so that the outputs always describe the run whose exit code is reported.
    with tempfile.TemporaryDirectory(prefix="readme-doctor-action-") as directory:
        json_path = Path(directory) / "report.json"
        if output_format == "json":
            completed = subprocess.run(_base_command("json", output_path), check=False)
            source = output_path
        else:
            completed = subprocess.run(_base_command(output_format, output_path), check=False)
            # Reuse the identical option set so both runs see the same configuration.
            subprocess.run(_base_command("json", json_path), check=False)
            source = json_path
        payload: Any = None
        if source.is_file():
            try:
                payload = json.loads(source.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = None
        counts = _counts(payload)

    lines = [f"{name}={value}" for name, value in counts.items()]
    lines.append(f"result={'pass' if completed.returncode == 0 else 'fail'}")
    lines.append(f"report-path={output_path}")
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with Path(github_output).open("a", encoding="utf-8") as stream:
            stream.write("\n".join(lines) + "\n")
    else:
        # Allows the script to be exercised outside a GitHub Actions runner.
        print("\n".join(lines))
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
