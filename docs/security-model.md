# Security model

README Doctor reads repositories it did not write, so repository content and configuration are both
treated as untrusted input. This document describes what the code actually does in 0.1.0.

## What a normal scan does

`readme-doctor check` reads files and writes a report. It does not execute anything, does not make
network requests, and does not modify the repository. A test asserts that modification times are
unchanged after a scan.

**Path containment.** Every relative reference in the README is resolved and then required to stay
inside the repository root. A reference that resolves outside, whether through `../`, an absolute
path, or a symlink, is reported as RD002 and the target is never opened. The reported evidence is the
text from the README, not the file contents.

**Symlinks.** Directory symlinks are not followed during traversal, and `os.walk` runs with
`followlinks=False`. A symlink loop cannot make traversal run away.

**Traversal scope.** Version control metadata, caches, dependency trees, and virtual environments are
skipped. A virtual environment is recognized by its `pyvenv.cfg` marker rather than by directory name,
so an environment called `env311` or `.package-test` is skipped just like `.venv`. Files above
`max_file_size_bytes` are skipped. This is a correctness measure as much as a performance one: without
it, environment variable discovery reports variables used by installed dependencies.

**Environment files.** Actual `.env` files are never read. Configuring `.env` as an example file does
not override this. No value from any environment file appears in a report, only variable names.

**Configuration.** YAML is parsed with `yaml.safe_load`, so a configuration file cannot construct
Python objects. Unknown fields are rejected rather than ignored. Validation errors report the field
path and exit with code 2 instead of printing a traceback.

## Network checks

Remote link checking is off unless `--network` or `rules.remote_links.enabled` turns it on.

When enabled it applies a per request timeout, a redirect limit, a transport retry limit, and an
identifying user agent. Each URL is requested at most once per run and the result is reused for every
location that references it. Configured domains are skipped, including their subdomains. Credentials
embedded in a URL are stripped before the request and before the URL appears in any report. Loopback,
link local, and private network destinations are blocked on both initial requests and redirects.

Rate limit and server error responses are treated as transient and produce no finding, so a result
does not depend on a site having a bad minute. Certificate verification failures are reported with a
readable reason rather than an exception class name.

Tests use a fake client. Nothing in the suite depends on a public website.

## Command execution

This is the highest risk feature and it is off by default in three separate ways.

1. `execution.enabled` must be `true` in configuration.
2. `--execute` must be passed on the command line. Configuration alone runs nothing, and a test
   asserts this.
3. `execution.verify_commands` must list the command. A README code block is never a command source,
   and a test asserts that enabling execution against a README full of shell commands runs nothing.

When all three conditions hold, each command runs through `docker run` with:

- `--network none`
- `--read-only` root filesystem
- the repository bind mounted at `/workspace` with `readonly`
- `--cap-drop ALL` and `--security-opt no-new-privileges`
- `--pids-limit 128`, `--memory 512m`, `--cpus 1`
- a `noexec,nosuid` tmpfs at `/tmp`
- a per command timeout from `execution.timeout_seconds`
- captured output truncated to `execution.max_output_bytes` and redacted before reporting

The argument list is fixed and no host shell is involved. The command is passed as a single argument
to the container's own shell, so it is never spliced into a host command line. Commands matching known
destructive patterns, including `rm`, `dd`, `mkfs`, `shutdown`, pipes into `sh` or `bash`, command
substitution, backticks, and redirection to absolute paths, are refused before anything starts.

A container name is generated per run, so two concurrent scans of the same repository cannot collide.
When a command times out, the container is force removed rather than left running.

Host execution is not implemented. If Docker is unavailable the run is skipped and reported as RD020.
There is no configuration option that moves execution onto the host.

## GitHub Actions

The action defaults `execute` and `network` to `false`. Neither is enabled by anything in a
repository's content, so opening a pull request cannot turn execution on.

Do not enable `execute` on a `pull_request_target` trigger, and do not pass repository secrets into a
workflow that runs code from a fork. The action needs `contents: read` only. Add
`security-events: write` solely when uploading SARIF.

The action installs the checked out action directory with pip and runs the tool as a subprocess. It
declares no other tools and relies only on `actions/setup-python`.

## Redaction

Redaction removes values matching common shapes: authorization headers, keyed secrets such as
`api_key=`, `token:`, and `password=`, GitHub tokens, AWS access key identifiers, credentials embedded
in URLs, and PEM private key blocks.

Two properties matter. First, redaction runs on the report model before serialization, not on
serialized text. Rewriting a serialized document can consume a closing quote and produce invalid JSON
or SARIF, so it is never done that way. Second, findings are printed as literal text rather than as
Rich markup, so a path containing square brackets is neither dropped nor interpreted.

Redaction is a best effort filter. It recognizes common formats and will miss unusual ones. It reduces
accidental exposure and does not guarantee that no secret is ever printed. Do not rely on it as the
only control over secrets in a repository.

## Reporting a vulnerability

See [SECURITY.md](../SECURITY.md). Please do not open a public issue for anything involving command
execution or secret exposure.
