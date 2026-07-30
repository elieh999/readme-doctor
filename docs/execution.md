# Command execution

README Doctor does not run the commands in your README. It never has and there is no option that
makes it. What `--execute` does is run a short list of commands that you wrote in configuration, in a
confined container, to confirm they still work.

## Turning it on

Three things must all be true before any command runs.

```yaml
version: 1
execution:
  enabled: true
  docker_image: python:3.12-slim
  timeout_seconds: 60
  max_output_bytes: 32768
  verify_commands:
    - python --version
```

```bash
readme-doctor check --config readme-doctor.yml --execute
```

Configuration alone is not enough. Running without `--execute` reports nothing and leaves
`execution.enabled` false in the JSON report. This is deliberate: a repository cannot enable execution
by shipping a configuration file.

## What the container looks like

Each command runs through `docker run` with the repository mounted read only at `/workspace`, which is
also the working directory. The container has:

- no network
- a read only root filesystem
- every Linux capability dropped, and no new privileges
- a process limit of 128, a memory limit of 512 MB, and one CPU
- a `noexec,nosuid` tmpfs at `/tmp`
- a name unique to this run, so concurrent scans do not collide

The command is one argument handed to the container's shell. README Doctor never builds a host shell
command line, so nothing from configuration is interpolated into a host command.

## What is refused

Commands matching known destructive patterns are rejected before Docker is invoked, and the rejection
is reported as RD018. That covers `rm`, `del`, `dd`, `mkfs`, `format`, `shutdown`, `reboot`, chaining
with `;`, `&&`, or `|`, piping a download into `sh` or `bash`, command substitution with `$(` or
backticks, and redirection to an absolute path.

This is a denylist. It stops obvious mistakes and obvious mischief. It is not a sandbox on its own,
which is why the container restrictions above exist.

## What the results mean

| Outcome | Rule | Severity |
| --- | --- | --- |
| Command rejected by the safety policy | RD018 | Error |
| Command exited nonzero | RD018 | Error |
| Command exceeded the timeout | RD018 | Error |
| Command could not be started | RD018 | Error |
| Docker unavailable | RD020 | Notice |

Failure output is truncated to `max_output_bytes` and redacted before it reaches the report.

On a timeout the local `docker run` process is stopped and the container is then force removed, so a
timed out command does not leave something running.

## When Docker is missing

The run is skipped and reported as RD020, a notice. Execution never falls back to the host. There is
no `allow_host` option in 0.1.0; host execution is not implemented.

Add `--verbose` to see which backend was selected and how many commands ran:

```text
Execution backend unavailable: 0 of 2 commands ran
```

## What will not work

The repository is mounted read only and the container has no network. Anything that installs
dependencies, writes into the project tree, or downloads something will fail. This model suits short
checks such as `python --version`, `python -c "import mypackage"`, or a command that reads files and
exits. It does not suit a full build.

## In GitHub Actions

Leave it off. The action defaults `execute` to `false`.

If you enable it on a trusted branch, never do so on a `pull_request_target` trigger and never pass
repository secrets into a workflow that runs code from a fork. See
[security-model.md](security-model.md).
