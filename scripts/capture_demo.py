"""Record the terminal screenshot used in the documentation.

The SVG is produced from the tool's own reporter so that the image cannot drift away from what
`readme-doctor check` actually prints.
"""

from __future__ import annotations

import re
from io import StringIO
from pathlib import Path

from rich.console import Console

from readme_doctor import scan_repository
from readme_doctor.reporters.text import write_report

FIXTURE = Path("tests") / "fixtures" / "terminal_demo"
DESTINATION = Path("docs") / "screenshots" / "terminal-demo.svg"

FONT_FACE = re.compile(r"\s*@font-face\s*\{[^}]*\}", re.DOTALL)
FONT_FAMILY = re.compile(r"font-family:\s*[^;\n]*Fira Code[^;\n]*;")
MONOSPACE = 'font-family: ui-monospace, SFMono-Regular, "SF Mono", Consolas, monospace;'


def make_self_contained(svg: str) -> str:
    """Remove the web font so the image needs no network access to render.

    Rich embeds `@font-face` rules pointing at a CDN. GitHub serves README images through a proxy
    that blocks external requests, so those rules never load anything. Dropping them keeps the
    image identical everywhere and means viewing the documentation contacts no third party.
    """
    without_faces = FONT_FACE.sub("", svg)
    return FONT_FAMILY.sub(MONOSPACE, without_faces)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    report = scan_repository(root / FIXTURE)
    # The screenshot uses the reporter itself, so the image cannot show anything the command
    # would not print.
    console = Console(
        record=True,
        width=100,
        color_system="truecolor",
        file=StringIO(),
        highlight=False,
    )
    write_report(console, report)
    destination = root / DESTINATION
    destination.parent.mkdir(parents=True, exist_ok=True)
    svg = console.export_svg(title=f"readme-doctor check {FIXTURE.as_posix()}")
    destination.write_text(make_self_contained(svg), encoding="utf-8")
    print(f"wrote {destination} ({destination.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
