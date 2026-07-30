from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    (tmp_path / "README.md").write_text(
        "# Demo\n\n## Installation\n\n## Usage\n\n## Testing\n\n## License\n", encoding="utf-8"
    )
    return tmp_path
