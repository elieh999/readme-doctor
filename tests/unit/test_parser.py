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
