# GitHub Action

The action is a composite action. It sets up Python, installs README Doctor from the action
directory, runs a scan, writes a report, and publishes counts as step outputs. The job's exit status
follows the scan.

## Basic use

```yaml
name: README Doctor

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  readme:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: elieh999/readme-doctor@v1
        with:
          format: text
          strict: "true"
```

Check out the repository first. The action scans the workspace, not a remote.

## Inputs

| Input | Default | Meaning |
| --- | --- | --- |
| `path` | `.` | Repository directory to scan |
| `config` | empty | Path to a configuration file. Omitted when empty |
| `format` | `sarif` | `text`, `json`, or `sarif` |
| `strict` | `false` | Fail on any finding, equivalent to `--fail-on notice` |
| `network` | `false` | Enable remote link checks |
| `execute` | `false` | Enable configured command verification |
| `fail-severity` | `error` | Lowest severity that fails the job |
| `output-path` | `readme-doctor.sarif` | Where the report is written |

All inputs are optional. `format` and `fail-severity` are validated, and an unrecognized value fails
the step with a readable message rather than passing a bad flag through.

Set `output-path` to something matching the format you chose. A `format: text` run writing to
`readme-doctor.sarif` will produce a text file with a misleading name.

## Outputs

| Output | Meaning |
| --- | --- |
| `errors` | Error finding count |
| `warnings` | Warning finding count |
| `notices` | Notice finding count |
| `result` | `pass` or `fail`, matching the step's exit status |
| `report-path` | The path the report was written to |

Counts always describe the same scan whose exit code the step reported, including when `network` is
enabled.

```yaml
      - uses: elieh999/readme-doctor@v1
        id: readme
      - if: steps.readme.outputs.result == 'fail'
        run: echo "${{ steps.readme.outputs.errors }} errors found"
```

## Code scanning with SARIF

```yaml
permissions:
  contents: read
  security-events: write

jobs:
  readme:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: elieh999/readme-doctor@v1
        with:
          format: sarif
          output-path: readme-doctor.sarif
      - uses: github/codeql-action/upload-sarif@v4
        if: always()
        with:
          sarif_file: readme-doctor.sarif
```

`if: always()` matters. Without it a failing scan skips the upload and the findings never reach the
Security tab.

Grant `security-events: write` only when you upload SARIF. `contents: read` is enough otherwise.

## Permissions and untrusted pull requests

`execute` and `network` default to false and nothing in a repository's content can change that, so a
pull request cannot make the action run code.

Do not use this action on a `pull_request_target` trigger with `execute: "true"`, and do not pass
repository secrets into a workflow that runs code from a fork. The `pull_request` trigger runs with a
read only token and no secrets, which is the right default here.

## Exit codes

The step fails when a finding reaches the threshold. `fail-severity: error` is the default;
`strict: "true"` fails on anything at all. The full table is in the
[README](../README.md#exit-codes).

## Testing the action

This repository runs the action against itself in `.github/workflows/readme-doctor.yml` using
`uses: ./`, which is the practical way to exercise a composite action before tagging a release.

`tests/unit/test_action_metadata.py` checks the metadata against the runner script: that every
declared input is passed through, that every passed variable is read, that every declared output is
written, and that dangerous inputs default to off. It also runs `scripts/run_action.py` directly with
a synthetic `GITHUB_OUTPUT` and asserts the counts, the `result` value, and the exit code for clean,
failing, and strict cases.

## Versioning

Consumers should pin a tag. Publish `v0.1.0` and move a floating `v1` tag to it when the interface is
stable enough to promise compatibility.
