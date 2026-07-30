# README Doctor v0.1.0

The first release. README Doctor compares a repository README against the project around it and
reports instructions that no longer hold.

## What it checks

Twenty one rules, RD001 through RD021, with stable identifiers:

- README discovery, and a notice when a README exists but is not Markdown
- Relative links and images: existence, letter case, and containment inside the repository
- Heading anchors, using GitHub style slugs and explicit HTML anchors
- Image alternative text, empty code fences, and unrecognized or misspelled fence languages
- Referenced scripts under `scripts/` and `tools/`, Python modules, and Make targets
- Package scripts named in README commands against every `package.json` in the repository
- Python, Node, Dart, and Flutter minimum versions against the project's declaration files
- Environment variables across code, example files, and the README
- Documented ports against published Docker Compose and Vite ports
- Configured setup sections and leftover placeholder text
- Badge URL syntax, and optionally remote link reachability
- Results from opt in command verification

Each finding carries a severity, a confidence level, the evidence it used, a suggested correction, and
a documentation link. The full registry is in `docs/rules.md` or from `readme-doctor rules`.

## Command line

```bash
readme-doctor check
readme-doctor check path/to/project --format sarif --output readme-doctor.sarif
readme-doctor check --strict --verbose
readme-doctor check --rule RD002 --rule RD008
readme-doctor init
readme-doctor fix
readme-doctor rules
```

Exit code 0 means nothing reached the failure threshold, 1 means something did, and 2 means invalid
configuration or a tool error. The threshold is `error` by default and `--strict` lowers it to any
finding.

`check` never writes to the repository. `fix` is a preview unless `--apply` is passed, and it only
corrects misspelled fence languages.

## GitHub Action

A composite action with inputs `path`, `config`, `format`, `strict`, `network`, `execute`,
`fail-severity`, and `output-path`, and outputs `errors`, `warnings`, `notices`, `result`, and
`report-path`. Its counts and exit status always describe the same scan. See `docs/github-action.md`,
including the SARIF upload workflow.

## Python API

`scan_repository`, `DoctorConfig`, `Report`, and `Finding` are the public API for 0.1.x. The package
ships `py.typed`.

## Output formats

Text for people, JSON for tooling, and SARIF 2.1.0 for GitHub code scanning. Findings are
deduplicated and sorted, so repeated runs produce identical output. Credentials are removed from all
three formats, and redaction runs on the report model before serialization so it cannot produce an
invalid document.

## Security defaults

Command execution is off. Enabling it takes three deliberate steps: `execution.enabled: true`, the
`--execute` flag, and an explicit entry in `execution.verify_commands`. README code blocks are never a
command source. Commands run in a Docker container with no network, a read only root filesystem, a
read only repository mount, all capabilities dropped, and limits on processes, memory, CPU, output,
and time. If Docker is missing the run is skipped rather than moved onto the host.

Network checks are off. Actual `.env` files are never read, and no environment value appears in a
report. Relative references must resolve inside the repository, and directory symlinks are not
followed. Configuration YAML is parsed safely and unknown fields are errors.

The GitHub Action defaults both `execute` and `network` to false and needs only `contents: read`.

Details are in `docs/security-model.md`.

## Verified for this release

Every item below was run, not assumed. CI results are from the run on the release commit.

- 354 tests pass on Linux with no skips. On Windows 352 pass and 2 skip, because unprivileged
  symlink creation is unavailable there
- Branch coverage 90.7 percent against an 80 percent gate
- Tested on Python 3.11, 3.12, and 3.13 on Linux, and on Python 3.12 on Windows
- `ruff format --check`, `ruff check`, and `mypy --strict` clean
- `twine check --strict` passes for the wheel and the source distribution
- `pip-audit --strict` reports no known vulnerabilities in the dependency tree
- The wheel installs into a clean environment, and the command line, JSON, SARIF, and rules output
  all work from it
- The Docker image builds and scans a fixture successfully
- GitHub code scanning accepted the SARIF output, so the format is confirmed valid in practice
- The action runs against this repository on every push and passes

Real Docker command execution, meaning `--execute` actually running a container, was not exercised.
The Docker unavailable path was verified directly and reports RD020 without falling back to the
host. The container arguments are asserted by tests rather than by a live run.

## Known limitations

Only Markdown READMEs are analyzed; an `.rst` README reports RD021 rather than being parsed. Version
detection reads common declaration files and compares minimums only. RD007 checks scripts under
`scripts/` and `tools/`, so a missing `./run.sh` at the root is not reported. RD013 needs one
unambiguous README port and one published port. Remote link results depend on how a site answers
automated requests, and rate limits and server errors are treated as transient. Docker execution
cannot install dependencies or write to the project tree. Redaction covers common secret formats and
cannot detect every one.

## Not published

This release is not on PyPI. Install it from a clone or from the built wheel.
