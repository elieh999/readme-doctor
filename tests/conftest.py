from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from tkinter import Tk


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    (tmp_path / "README.md").write_text(
        "# Demo\n\n## Installation\n\n## Usage\n\n## Testing\n\n## License\n", encoding="utf-8"
    )
    return tmp_path


@pytest.fixture(scope="session")
def _tk_session() -> Iterator[Tk]:
    """One hidden Tk root shared by every desktop test.

    Creating a root per test is unreliable, and Tk is unavailable entirely on a headless runner,
    so the desktop tests skip rather than fail when it cannot start.
    """
    try:
        from tkinter import TclError, Tk
    except ImportError as exc:  # pragma: no cover - depends on the Python build
        pytest.skip(f"tkinter is unavailable: {exc}")
    try:
        root = Tk()
    except TclError as exc:  # pragma: no cover - depends on the display and the Tk install
        pytest.skip(f"Tk cannot start in this environment: {exc}")
    root.withdraw()
    yield root
    root.destroy()


@pytest.fixture
def tk_root(_tk_session: Tk) -> Iterator[Tk]:
    """The shared root, with any widgets a previous test created removed first."""
    for child in _tk_session.winfo_children():
        child.destroy()
    yield _tk_session
