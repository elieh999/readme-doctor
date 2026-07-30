from __future__ import annotations

import re
import shutil
import subprocess
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

from readme_doctor.checks.base import CheckContext
from readme_doctor.execution.redaction import redact
from readme_doctor.models import ExecutionMetadata, Finding

DANGEROUS = re.compile(
    r"(?:^|[;&|]\s*)(?:sudo\s+)?(?:rm|del|erase|format|shutdown|reboot|mkfs|dd)\b"
    r"|(?:curl|wget).*\|\s*(?:sh|bash)"
    r"|`|\$\(|>\s*/",
    re.IGNORECASE,
)


def _docker_command(context: CheckContext, command: str, name: str) -> list[str]:
    root = str(context.repository.root)
    return [
        "docker",
        "run",
        "--rm",
        "--name",
        name,
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        "128",
        "--memory",
        "512m",
        "--cpus",
        "1",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=64m",
        "--mount",
        f"type=bind,src={root},dst=/workspace,readonly",
        "--workdir",
        "/workspace",
        context.config.execution.docker_image,
        "sh",
        "-lc",
        command,
    ]


def _remove_container(docker: str, name: str) -> None:
    """Force remove a container that outlived its client process.

    A timeout stops the local `docker run` process but leaves the container running, so it is
    removed explicitly. Failure to remove is ignored because the container may already be gone.
    """
    with suppress(OSError, subprocess.SubprocessError):
        subprocess.run(
            [docker, "rm", "--force", name],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            env={"PATH": str(Path(docker).parent)},
        )


def execute_configured_commands(
    context: CheckContext,
) -> tuple[list[Finding], ExecutionMetadata]:
    settings = context.config.execution
    docker = shutil.which("docker")
    metadata = ExecutionMetadata(
        enabled=True,
        backend="docker" if docker else "unavailable",
        commands_considered=len(settings.verify_commands),
    )
    findings: list[Finding] = []
    if docker is None:
        finding = context.finding(
            "RD020",
            "Command execution was requested but Docker is unavailable.",
            evidence="backend=docker; result=unavailable",
            suggestion=(
                "Install Docker. Host execution is intentionally unsupported in this release."
            ),
        )
        return ([finding] if finding else [], metadata)
    # A per run identifier keeps concurrent scans of the same repository from colliding on a
    # container name.
    run_id = uuid4().hex[:12]
    for index, command in enumerate(settings.verify_commands):
        if DANGEROUS.search(command):
            finding = context.finding(
                "RD018",
                "Configured verification command was rejected by the safety policy.",
                evidence=redact(command)[:300],
                suggestion="Use a noninteractive, read only verification command.",
            )
            if finding:
                findings.append(finding)
            continue
        container = f"readme-doctor-{run_id}-{index}"
        try:
            # The argument list is fixed and passed without a shell. The verification command is a
            # single argument to the container's own shell, never spliced into a host command line.
            completed = subprocess.run(
                _docker_command(context, command, container),
                cwd=context.repository.root,
                capture_output=True,
                text=True,
                timeout=settings.timeout_seconds,
                check=False,
                env={"PATH": str(Path(docker).parent)},
            )
            metadata.commands_executed += 1
            if completed.returncode:
                output = redact((completed.stdout + completed.stderr)[: settings.max_output_bytes])
                explanation = (
                    f"Configured verification command failed with exit code {completed.returncode}."
                )
                finding = context.finding(
                    "RD018",
                    explanation,
                    evidence=output or redact(command),
                )
                if finding:
                    findings.append(finding)
        except subprocess.TimeoutExpired:
            _remove_container(docker, container)
            metadata.commands_executed += 1
            explanation = (
                "Configured verification command timed out after "
                f"{settings.timeout_seconds} seconds."
            )
            finding = context.finding(
                "RD018",
                explanation,
                evidence=redact(command),
            )
            if finding:
                findings.append(finding)
        except OSError as exc:
            finding = context.finding(
                "RD018",
                "Configured verification command could not be started.",
                evidence=f"{type(exc).__name__}: {redact(str(exc))}"[:300],
            )
            if finding:
                findings.append(finding)
    return findings, metadata
