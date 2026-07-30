"""Record the terminal screenshot used in the documentation.

The SVG is produced from the tool's own reporter so that the image cannot drift away from what
`readme-doctor check` actually prints.
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path

from rich.console import Console

from readme_doctor import scan_repository
from readme_doctor.reporters.text import write_report

FIXTURE = Path("tests") / "fixtures" / "terminal_demo"
DESTINATION = Path("docs") / "screenshots" / "terminal-demo.svg"


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
    console.save_svg(str(destination), title=f"readme-doctor check {FIXTURE.as_posix()}")
    print(f"wrote {destination}")


if __name__ == "__main__":
    main()
