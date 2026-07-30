# Changelog

All notable changes are documented here. This project follows semantic versioning from 0.1.0 onward.
Rule identifiers are stable within a minor line.

## 0.1.0

First release.

### Included

- Command line scanner (`check`, `init`, `fix`, `rules`) built on Typer, with Rich terminal output.
- Reusable Python API: `scan_repository`, `DoctorConfig`, `Report`, and `Finding`. The package ships
  `py.typed`.
- Composite GitHub Action with documented inputs, outputs, and safe defaults.
- Windows desktop interface, built locally with PyInstaller.
- Rules RD001 through RD021, each with a stable identifier, severity, confidence level, evidence, and
  a suggested correction.
- Text, JSON, and SARIF 2.1.0 output. Findings are deduplicated and sorted, so repeated runs produce
  identical output.
- Configuration validated with Pydantic and loaded with `yaml.safe_load`. Unknown fields and unknown
  rule identifiers are errors.
- Suppression comments, ignore patterns, per rule severity overrides, and rule filtering.
- Optional remote link checking, off by default, with per run caching and transient failure handling.
- Opt in command verification that runs only configured commands, only inside a confined Docker
  container, and only when both configuration and `--execute` agree.
- Secret redaction applied to the report model before serialization.
- Docker image and CI workflows covering formatting, linting, strict type checking, tests, coverage,
  packaging, and the action metadata.

### Fixed during pre release review

These were found and corrected while auditing the first implementation, before any release existed.

- JSON and SARIF output could be unparseable. Redaction ran over the serialized document and could
  consume a closing quote. Redaction now runs on the report model before serialization.
- `fix --apply` corrupted indented code fences, destroying both the fence and its indentation. The
  opening fence is now matched precisely and left alone when it does not match exactly.
- The text reporter interpreted findings as Rich markup, silently dropping anything inside square
  brackets, so a path such as `docs/[guide]/setup.md` was reported incorrectly. Findings are now
  printed as literal text.
- Links inside a multi line paragraph all reported the paragraph's first line. Line breaks are now
  counted, so each finding points at the line where it was written.
- Link text was attributed to the preceding link rather than its own.
- RD008 reported package manager subcommands such as `yarn install`, `yarn add`, and `pnpm install`
  as missing scripts, at error severity. Builtin subcommands are now excluded, shorthand forms report
  at medium confidence, and the rule stays silent when the repository has no `package.json`.
- RD013 compared the README against the container side of a Docker Compose port mapping instead of
  the published host side, so a correct README was reported as wrong.
- RD012 reported the same variable twice through overlapping conditions, and treated every uppercase
  word in the prose as a documented variable, so acronyms such as JSON and MIT counted as
  configuration.
- RD009, RD010, and RD011 produced one finding per mention. A repeated requirement is now reported
  once, at its first mention, and requirement files are read once per language rather than once per
  match.
- RD015 matched placeholder words inside identifiers and URLs. Matching is now whole word, and link
  targets and inline code are excluded.
- Repository traversal only skipped virtual environments named `.venv` or `venv`, so scanning a
  repository containing any other environment reported environment variables belonging to installed
  dependencies. Environments are now detected by their `pyvenv.cfg` marker. On this project's own
  repository that removed 63 false findings and cut scan time from 10.07s to 0.18s.
- Environment variable discovery reported platform and toolchain variables such as `PATH`, `HOME`,
  `APPDATA`, `XDG_*`, and `PYTHONPATH` as undocumented project configuration.
- A non Markdown README produced an empty report that read as a clean result. It now reports RD021
  to say that content rules did not run.
- A command that timed out left its Docker container running. Containers are now named per run and
  force removed after a timeout, which also prevents concurrent scans from colliding.
- The GitHub Action ran the scan twice and derived its counts from a second run that always disabled
  network checks, so outputs could disagree with the exit code. It also raised `KeyError` outside a
  runner and passed unvalidated `format` and `fail-severity` values through.
- `execution.allow_host` and `execution.allowed_code_blocks` were accepted by the configuration model
  and documented but never read by any code. Both were removed. A configuration file using them now
  fails validation with a field level message.
- The source distribution embedded a 1.3 MB presentation image, making it 1.39 MB. Excluding
  presentation assets reduced it to 58 KB.
- The terminal screenshot was produced by code that duplicated the reporter and could drift from it.
  It is now generated by the reporter itself.
- The desktop interface could raise `IndexError` and close. Selecting a finding, rescanning a
  repository with fewer findings, and letting the selection event fire during row deletion indexed
  the new report with an index from the old one. The index is now validated.
- An export to a location the user cannot write to raised `OSError` out of the desktop event loop.
  It is now reported in a dialog. A failure to write the crash log no longer replaces the original
  error, and a failure before the event loop starts is logged rather than lost, which matters
  because the packaged application has no console.
- RD016 reported local badge images as invalid URLs, so a badge committed to the repository was
  reported by both RD016 and RD002. Only destinations meant to be absolute are inspected now.
- Indented code blocks were invisible to the parser, so a placeholder or a version inside one was
  read as prose. They are recorded and excluded from prose rules, without becoming subject to the
  fence syntax rules.
- The desktop tests created a Tk root per test, which was unreliable, and would have failed outright
  on a headless runner. They now share one root and skip when Tk cannot start.

### Known limitations

Only Markdown READMEs are analyzed. Version detection reads common declaration files and compares
minimums only. RD007 checks scripts under `scripts/` and `tools/`. Remote link results depend on how
a site answers automated requests. Docker execution cannot install dependencies or write to the
project tree. Redaction covers common secret formats and cannot detect every one.
