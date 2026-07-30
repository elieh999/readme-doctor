# Configuration

README Doctor runs with built in defaults. Configuration is read only when `--config` is supplied:

```bash
readme-doctor check --config readme-doctor.yml
```

`readme-doctor init` writes a starter file and refuses to overwrite one that already exists.

YAML is parsed with `yaml.safe_load`, so no Python objects can be constructed from a configuration
file. Unknown fields are rejected rather than ignored, which means a misspelled key is an error
instead of a silently missing setting. Validation failures report the exact field path and exit with
code 2.

## Fields

| Field | Default | Meaning |
| --- | --- | --- |
| `version` | required | Must be `1` |
| `readme.paths` | `README.md`, `Readme.md`, `readme.md`, `README.rst` | Root README names in preference order |
| `max_file_size_bytes` | `2000000` | Files larger than this are skipped during traversal |
| `rules.disabled` | empty | Rule identifiers to turn off |
| `rules.severity` | empty | Maps a rule identifier to `error`, `warning`, or `notice` |
| `rules.known_code_languages` | empty | Extra fenced language identifiers treated as valid |
| `rules.decorative_images` | empty | Image destinations allowed to have empty alternative text |
| `rules.ignored_placeholders` | empty | Placeholder phrases to accept |
| `rules.required_sections.enabled` | `true` | Whether RD014 runs |
| `rules.required_sections.severity` | `notice` | Severity for a missing section |
| `rules.required_sections.sections` | `Installation`, `Usage`, `Testing`, `License` | Heading names expected in the README |
| `rules.remote_links.enabled` | `false` | Whether RD017 makes HTTP requests |
| `rules.remote_links.timeout_seconds` | `5.0` | Per request timeout, greater than 0 and at most 60 |
| `rules.remote_links.retries` | `1` | Transport level retries, 0 to 5 |
| `rules.remote_links.redirect_limit` | `5` | Maximum redirects to follow |
| `rules.remote_links.ignored_domains` | empty | Hosts to skip, including their subdomains |
| `rules.remote_links.allowed_status_codes` | `200`, `204`, `301`, `302`, `307`, `308` | Statuses treated as reachable |
| `rules.environment_variables.enabled` | `true` | Whether RD012 runs |
| `rules.environment_variables.example_files` | `.env.example`, `.env.sample`, `.env.template` | Example files to read. A file named `.env` is refused |
| `execution.enabled` | `false` | Must be `true`, together with `--execute`, before any command runs |
| `execution.timeout_seconds` | `120` | Per command timeout |
| `execution.docker_image` | `python:3.12-slim` | Image the commands run in |
| `execution.verify_commands` | empty | The only commands that may run |
| `execution.max_output_bytes` | `32768` | Captured output is truncated to this size |
| `ignore.rules` | empty | A second rule disable list |
| `ignore.paths` | `.git/**`, `.venv/**`, `venv/**`, `node_modules/**`, `vendor/**`, `build/**`, `dist/**`, `tests/**` | Glob patterns skipped during traversal |

Setting `ignore.paths` replaces the default list rather than adding to it, so include the entries you
still want skipped.

## Example

```yaml
version: 1

readme:
  paths:
    - README.md

rules:
  required_sections:
    enabled: true
    severity: notice
    sections:
      - Installation
      - Usage
      - Testing
  remote_links:
    enabled: false
    ignored_domains:
      - internal.example.com
  environment_variables:
    enabled: true
    example_files:
      - .env.example
  known_code_languages:
    - hcl
  disabled:
    - RD016
  severity:
    RD005: notice

execution:
  enabled: false
  timeout_seconds: 120
  docker_image: python:3.12-slim
  verify_commands: []

ignore:
  rules: []
  paths:
    - .git/**
    - node_modules/**
    - vendor/**
    - build/**

max_file_size_bytes: 2000000
```

## Command line overrides

`--network` and `--no-network` override `rules.remote_links.enabled`. `--rule` restricts the run to
the identifiers given. `--fail-on` sets the severity that produces exit code 1, and `--strict` is
equivalent to `--fail-on notice`.

`--execute` is required before any command runs. It cannot be replaced by configuration: a file
setting `execution.enabled: true` still runs nothing without the flag.
