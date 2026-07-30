from __future__ import annotations

from pathlib import Path

from readme_doctor.parser import github_slug, parse_markdown
from readme_doctor.rules import RULES


def test_github_slug_handles_punctuation_and_unicode() -> None:
    assert github_slug("Hello, World!") == "hello-world"
    assert github_slug("Café Setup") == "café-setup"


def test_parser_extracts_duplicate_anchors_links_images_and_code(tmp_path: Path) -> None:
    path = tmp_path / "README.md"
    path.write_text(
        '# Setup\n# Setup\n<a id="manual"></a>\n'
        "[link](docs/a.md) ![alt](image.png) `inline`\n```py\nprint('ok')\n```\n",
        encoding="utf-8",
    )
    document = parse_markdown(path, set(RULES))
    assert [heading.anchor for heading in document.headings] == ["setup", "setup-1"]
    assert document.explicit_anchors == {"manual"}
    assert [(link.destination, link.is_image) for link in document.links] == [
        ("docs/a.md", False),
        ("image.png", True),
    ]
    # `<a id="manual"></a>` is an inline tag, so it opens a paragraph that continues onto the
    # next source line. The inline code sits on line 4, not on the line the paragraph started.
    assert document.inline_code == [("inline", 4)]
    assert document.code_blocks[0].language == "py"


def test_link_positions_follow_line_breaks_inside_a_paragraph(tmp_path: Path) -> None:
    path = tmp_path / "README.md"
    path.write_text(
        "# Setup\n\nFirst [one](a.md) here\nsecond [two](b.md) here\nthird ![alt](c.png) here\n",
        encoding="utf-8",
    )
    document = parse_markdown(path, set(RULES))
    assert [(link.destination, link.line) for link in document.links] == [
        ("a.md", 3),
        ("b.md", 4),
        ("c.png", 5),
    ]


def test_reference_style_links_resolve(tmp_path: Path) -> None:
    """Full, collapsed, and shortcut reference forms all resolve to their definition."""
    path = tmp_path / "README.md"
    path.write_text(
        "# Refs\n\n"
        "Full [the guide][guide], image ![logo][badge].\n"
        "Collapsed [guide][] and shortcut [guide].\n\n"
        "[guide]: docs/guide.md\n"
        "[badge]: images/logo.png\n",
        encoding="utf-8",
    )
    document = parse_markdown(path, set(RULES))
    assert [(link.destination, link.is_image, link.line) for link in document.links] == [
        ("docs/guide.md", False, 3),
        ("images/logo.png", True, 3),
        ("docs/guide.md", False, 4),
        ("docs/guide.md", False, 4),
    ]


def test_indented_code_is_recorded_but_marked_unfenced(tmp_path: Path) -> None:
    path = tmp_path / "README.md"
    path.write_text(
        "# Demo\n\nExample:\n\n    indented one\n    indented two\n\n```py\nfenced\n```\n",
        encoding="utf-8",
    )
    document = parse_markdown(path, set(RULES))
    assert [(block.fenced, block.language) for block in document.code_blocks] == [
        (False, ""),
        (True, "py"),
    ]
    # Both blocks contribute their lines, so prose rules skip them.
    assert {5, 6}.issubset(document.code_lines())
    assert {8, 9, 10}.issubset(document.code_lines())


def test_prose_text_blanks_code_without_shifting_lines(tmp_path: Path) -> None:
    path = tmp_path / "README.md"
    path.write_text("# Demo\n\n```text\nhidden\n```\n\nvisible prose\n", encoding="utf-8")
    document = parse_markdown(path, set(RULES))
    prose = document.prose_text().splitlines()
    assert "hidden" not in document.prose_text()
    assert prose[6] == "visible prose"
    assert len(prose) == len(document.text.splitlines())


def test_link_text_belongs_to_its_own_link(tmp_path: Path) -> None:
    path = tmp_path / "README.md"
    path.write_text(
        "# Setup\n\nSee [Installation](#installation) and [Usage](#usage) sections.\n",
        encoding="utf-8",
    )
    document = parse_markdown(path, set(RULES))
    assert [(link.text, link.destination) for link in document.links] == [
        ("Installation", "#installation"),
        ("Usage", "#usage"),
    ]


def test_suppressions_and_unknown_rules(tmp_path: Path) -> None:
    path = tmp_path / "README.md"
    path.write_text(
        "<!-- readme-doctor-disable RD015 -->\nTODO\n"
        "<!-- readme-doctor-enable RD015 -->\nTBD\n"
        "<!-- readme-doctor-disable RD999 -->\n",
        encoding="utf-8",
    )
    document = parse_markdown(path, set(RULES))
    assert document.is_suppressed("RD015", 2)
    assert not document.is_suppressed("RD015", 4)
    assert document.suppression_errors == [(5, "RD999")]
