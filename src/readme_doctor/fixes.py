from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from pathlib import Path

from readme_doctor.checks.markdown import MISSPELLINGS
from readme_doctor.parser import parse_markdown
from readme_doctor.rules import RULES

# Leading indentation, the fence characters, the language token, and any remaining info string.
FENCE_LINE = re.compile(r"^(?P<indent>[ \t]*)(?P<fence>`{3,}|~{3,})(?P<language>\S+)(?P<rest>.*)$")


@dataclass(frozen=True)
class FixResult:
    path: Path
    changed: bool
    diff: str


def language_fixes(path: Path, *, apply: bool = False) -> FixResult:
    original = path.read_text(encoding="utf-8")
    document = parse_markdown(path, set(RULES))
    lines = original.splitlines(keepends=True)
    changed = list(lines)
    for block in document.code_blocks:
        corrected = MISSPELLINGS.get(block.language.casefold())
        if not corrected:
            continue
        index = block.line - 1
        if not (0 <= index < len(changed)):
            continue
        raw = changed[index]
        body = raw.rstrip("\r\n")
        ending = raw[len(body) :]
        match = FENCE_LINE.match(body)
        # Only rewrite when the opening fence looks exactly as expected. Anything else is left
        # alone rather than risking a rewrite that breaks the code block.
        if match is None or match.group("language").casefold() != block.language.casefold():
            continue
        changed[index] = (
            f"{match.group('indent')}{match.group('fence')}{corrected}{match.group('rest')}{ending}"
        )
    updated = "".join(changed)
    diff = "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            updated.splitlines(keepends=True),
            fromfile=str(path),
            tofile=str(path),
        )
    )
    if apply and updated != original:
        path.write_text(updated, encoding="utf-8")
    return FixResult(path, updated != original, diff)
