# Rule registry

Rule identifiers are stable within the 0.1 release line. A finding is never reported under two
identifiers, and each finding carries a confidence level describing how strong its evidence is.

Print the registry from the tool with `readme-doctor rules`.

| ID | Default | Rule | Evidence | Confidence |
| --- | --- | --- | --- | --- |
| RD001 | Error | Missing README | No configured README exists at the repository root | High |
| RD002 | Error | Missing local reference | Existence, containment, and letter case of a relative link or image target | High |
| RD003 | Warning | Broken internal anchor | GitHub style heading slugs plus explicit HTML anchors | High |
| RD004 | Warning | Missing image alternative text | Markdown image with an empty label | High |
| RD005 | Notice | Empty code block | Fenced block containing only whitespace | High |
| RD006 | Warning | Unknown code language | High for a known typo, medium for an unrecognized identifier | High or medium |
| RD007 | Error | Missing referenced command | Script file under `scripts/` or `tools/`, Python module, or Make target | High, medium for modules |
| RD008 | Error | Missing package script | Comparison against every `package.json` in the repository | High with `run`, medium for shorthand |
| RD009 | Warning | Python version mismatch | README minimum versus `pyproject.toml`, `.python-version`, `setup.cfg`, or `setup.py` | High |
| RD010 | Warning | Node version mismatch | README minimum versus `engines.node`, `.nvmrc`, or `.node-version` | High |
| RD011 | Warning | Dart or Flutter mismatch | README minimum versus `pubspec.yaml` or `.fvmrc` | High |
| RD012 | Warning | Environment documentation | Variable names from code, example files, and the README | Medium |
| RD013 | Warning | Port mismatch | One unambiguous README port and one published Compose or Vite port | High |
| RD014 | Notice | Missing setup section | Configured heading names compared with README headings | High |
| RD015 | Warning | Placeholder content | Known phrases matched as whole words outside code and link targets | High |
| RD016 | Warning | Invalid badge | Badge image URL syntax, checked without network access | High |
| RD017 | Warning | Broken remote link | Optional HTTP result, with transient failures ignored | High, medium on transport errors |
| RD018 | Error | Command execution failed | A configured command was rejected, failed, or timed out | High |
| RD019 | Warning | Invalid suppression | Unknown identifier in a suppression comment | High |
| RD020 | Notice | Execution skipped | Docker was unavailable after an explicit execution opt in | High |
| RD021 | Notice | README format not analyzed | A README was found but is not Markdown, so content rules did not run | High |

## Notes on the heuristic rules

Some rules read project files and compare them with prose, so their evidence is weaker than a file
existence check. These are the ones to know about.

**RD008** distinguishes two forms. `npm run build` names a script unambiguously and reports at high
confidence. `pnpm build` and `yarn lint` may be either a script or a builtin subcommand, so builtin
names are excluded and the remainder reports at medium confidence. When the repository contains no
`package.json` at all, the rule stays silent, because the README may be describing a separate
project.

**RD012** only treats a name as documented when it appears in inline code, in a fenced block, or in
an explicit `NAME=` form. Matching every uppercase word in the prose would count acronyms such as
JSON or MIT as documented variables. Actual `.env` files are never read, and no value from any
environment file is ever included in a report.

**RD013** compares the host side of a Docker Compose mapping, because that is the port a reader
opens. In `"3000:8000"` the host port is 3000. The rule reports only when the README names exactly
one port and the configuration publishes exactly one port.

**RD007** checks script paths under `scripts/` or `tools/`. Other command shapes are not inspected,
so a missing `./run.sh` at the repository root is not reported.

**RD009**, **RD010**, and **RD011** compare only the minimum version stated in the README against
the strongest declaration found in the project. A README that documents a newer version than the
project requires is not a conflict. A repeated requirement is reported once, at its first mention.

## Turning rules off

Every rule can be disabled globally through `rules.disabled` or `ignore.rules`, and its severity can
be changed through `rules.severity`. Findings located on a README line can also be suppressed with a
comment:

```markdown
<!-- readme-doctor-disable RD015 -->
TODO kept on purpose as an example
<!-- readme-doctor-enable RD015 -->
```

Use `readme-doctor-disable-line RD015` on the line before a single affected line. An unknown
identifier in a suppression comment produces RD019.
