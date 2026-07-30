from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

from markdown_it import MarkdownIt
from markdown_it.token import Token


@dataclass(frozen=True)
class Heading:
    text: str
    anchor: str
    line: int
    level: int


@dataclass(frozen=True)
class Link:
    destination: str
    text: str
    line: int
    is_image: bool = False


@dataclass(frozen=True)
class CodeBlock:
    language: str
    content: str
    line: int
    # Indented code blocks carry no language and no fence, so the rules about fence syntax do not
    # apply to them. They are still recorded so their lines can be excluded from prose checks.
    fenced: bool = True


@dataclass
class MarkdownDocument:
    path: Path
    text: str
    headings: list[Heading] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    code_blocks: list[CodeBlock] = field(default_factory=list)
    inline_code: list[tuple[str, int]] = field(default_factory=list)
    explicit_anchors: set[str] = field(default_factory=set)
    suppressions: dict[int, set[str]] = field(default_factory=dict)
    suppression_errors: list[tuple[int, str]] = field(default_factory=list)

    def is_suppressed(self, rule_id: str, line: int | None) -> bool:
        if line is None:
            return False
        return rule_id in self.suppressions.get(line, set())

    def code_lines(self) -> set[int]:
        """Line numbers covered by any code block, fenced or indented.

        A fenced block's range includes both fence lines. Prose rules use this so an example
        inside a code block is not read as a statement about the project.
        """
        covered: set[int] = set()
        for block in self.code_blocks:
            span = block.content.count("\n") + (2 if block.fenced else 0)
            covered.update(range(block.line, block.line + span))
        return covered

    def prose_text(self) -> str:
        """The document with fenced code blocks blanked out, keeping every line number intact.

        Rules that read requirements out of prose use this. Sample output and example commands
        inside a fenced block describe what a reader will see, not what the project requires, so
        matching them would report the documentation's own examples as conflicts.
        """
        covered = self.code_lines()
        return "\n".join(
            "" if number in covered else line
            for number, line in enumerate(self.text.splitlines(), start=1)
        )


def github_slug(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).strip().lower()
    normalized = re.sub(r"<[^>]+>", "", normalized)
    normalized = re.sub(r"[^\w\- ]", "", normalized, flags=re.UNICODE)
    return re.sub(r"[\s]+", "-", normalized)


def _plain_text(children: list[Token] | None) -> str:
    if not children:
        return ""
    return "".join(token.content for token in children if token.type in {"text", "code_inline"})


def _line(token: Token) -> int:
    return (token.map[0] + 1) if token.map else 1


def _extract_inline(document: MarkdownDocument, token: Token, line: int) -> None:
    """Collect links, images, and inline code from one inline token.

    An inline token covers a whole block, so a paragraph spanning several lines reports one map
    position for all of its content. Line breaks inside the block arrive as `softbreak` and
    `hardbreak` children, so counting them keeps each link on the line where it was written.

    Link text is the content between `link_open` and `link_close`, so open links are tracked on a
    stack and completed when the matching close token arrives. Each entry records the line where
    the link started.
    """
    if not token.children:
        return
    current = line
    open_links: list[tuple[str, list[str], int]] = []
    for child in token.children:
        if child.type in {"softbreak", "hardbreak"}:
            current += 1
        elif child.type == "text":
            for _, parts, _start in open_links:
                parts.append(child.content)
        elif child.type == "code_inline":
            document.inline_code.append((child.content, current))
            for _, parts, _start in open_links:
                parts.append(child.content)
        elif child.type == "link_open":
            open_links.append((unquote(str(child.attrGet("href") or "")), [], current))
        elif child.type == "link_close":
            if open_links:
                destination, parts, start = open_links.pop()
                document.links.append(Link(destination, "".join(parts), start))
        elif child.type == "image":
            destination = unquote(str(child.attrGet("src") or ""))
            document.links.append(Link(destination, child.content, current, True))
            for _, parts, _start in open_links:
                parts.append(child.content)
    # A malformed document can leave a link open. Record it so nothing is silently dropped.
    while open_links:
        destination, parts, start = open_links.pop()
        document.links.append(Link(destination, "".join(parts), start))


def _build_suppressions(document: MarkdownDocument, known_rules: set[str]) -> None:
    disabled: set[str] = set()
    disable_pattern = re.compile(
        r"<!--\s*readme-doctor-(disable|enable)(?:-line)?\s+([A-Z]{2}\d{3})\s*-->"
    )
    for number, raw_line in enumerate(document.text.splitlines(), start=1):
        document.suppressions[number] = set(disabled)
        for action, rule_id in disable_pattern.findall(raw_line):
            if rule_id not in known_rules:
                document.suppression_errors.append((number, rule_id))
                continue
            if "-line" in raw_line:
                document.suppressions.setdefault(number + 1, set(disabled)).add(rule_id)
            elif action == "disable":
                disabled.add(rule_id)
            else:
                disabled.discard(rule_id)
        document.suppressions[number] = set(disabled) | document.suppressions[number]


def parse_markdown(path: Path, known_rules: set[str]) -> MarkdownDocument:
    text = path.read_text(encoding="utf-8", errors="replace")
    document = MarkdownDocument(path=path, text=text)
    parser = MarkdownIt("commonmark", {"html": True})
    tokens = parser.parse(text)
    anchors_seen: dict[str, int] = {}
    for index, token in enumerate(tokens):
        line = _line(token)
        if token.type == "heading_open" and index + 1 < len(tokens):
            inline = tokens[index + 1]
            heading_text = _plain_text(inline.children)
            base = github_slug(heading_text)
            duplicate = anchors_seen.get(base, 0)
            anchor = base if duplicate == 0 else f"{base}-{duplicate}"
            anchors_seen[base] = duplicate + 1
            document.headings.append(Heading(heading_text, anchor, line, int(token.tag[1])))
        elif token.type == "inline":
            _extract_inline(document, token, line)
        elif token.type == "fence":
            language = token.info.strip().split(maxsplit=1)[0] if token.info.strip() else ""
            document.code_blocks.append(CodeBlock(language, token.content, line))
        elif token.type == "code_block":
            document.code_blocks.append(CodeBlock("", token.content, line, fenced=False))
        elif token.type == "html_block":
            document.explicit_anchors.update(
                match.group(1)
                for match in re.finditer(
                    r"""(?:id|name)\s*=\s*["']([^"']+)["']""", token.content, re.IGNORECASE
                )
            )
    document.explicit_anchors.update(
        match.group(1)
        for match in re.finditer(
            r"""<a\s+[^>]*(?:id|name)\s*=\s*["']([^"']+)["']""", text, re.IGNORECASE
        )
    )
    _build_suppressions(document, known_rules)
    return document
