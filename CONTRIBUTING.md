# Contributing

Thanks for improving README Doctor.

## Development setup

Python 3.11 or newer.

```bash
python -m venv .venv
python -m pip install -e ".[dev]"
```

On Windows, call `.\.venv\Scripts\python` directly if script activation is restricted.

## Quality checks

Run these before opening a pull request:

```bash
ruff format --check .
ruff check .
mypy src
pytest --cov=readme_doctor --cov-report=term-missing
python -m build
```

Do not weaken lint, typing, or coverage settings to make a change pass. If a rule genuinely needs an
exception, narrow it to the line and say why in a comment.

Two symlink tests skip on Windows unless developer mode allows unprivileged symlink creation. That is
expected. Everything else should pass on both platforms.

## Adding or changing a rule

The hard part of a documentation checker is not finding problems, it is not inventing them. A rule
that reports guesses as facts makes people stop using the tool, so silence is the better failure mode.

A rule needs:

1. A stable `RDxxx` identifier added to `readme_doctor/rules.py`. Never reuse or renumber one.
2. One responsibility. If a problem is already reported by another rule, do not report it again.
3. Evidence a reader can check, in the `evidence` field, naming the file it came from.
4. An honest confidence level. Reserve `high` for comparisons against a file that exists. Use
   `medium` when the reading is plausible but the syntax is ambiguous.
5. A severity that fits. Use `error` only when the repository proves the README wrong.
6. A suggested correction someone can act on.
7. A test that triggers it, in the relevant `tests/unit` module.
8. A test in `tests/unit/test_false_positives.py` proving it stays quiet on a correct repository.
   Every entry in that file is a real false positive this tool once produced.
9. A row in `docs/rules.md`, and a note in the heuristic section if the evidence is indirect.

Rules must respect `rules.disabled`, `ignore.rules`, `rules.severity`, and suppression comments. Going
through `CheckContext.finding` gives you all four.

## Security changes

Anything touching command execution, path resolution, symlinks, network access, or redaction needs a
regression test in `tests/unit/test_security.py` and a matching update to `docs/security-model.md`.
That document describes what the code does, so it should never describe a behavior the code does not
have.

Command execution stays off by default. It stays limited to `execution.verify_commands`. README
content never becomes a command source.

## Documentation

Every documented option must exist, every documented default must match the code, and every command in
the documentation should be one you ran. When you change output or the demo fixture, regenerate the
screenshot:

```bash
python scripts/capture_demo.py
```

## Pull requests

Keep changes focused. Describe the problem you observed, what you changed, and the exact commands you
used to verify it.

Never commit `.env` files, tokens, virtual environments, coverage data, build artifacts, or generated
reports. `.gitignore` covers the usual cases; check `git status` before committing.
