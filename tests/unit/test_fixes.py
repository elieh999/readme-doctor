from __future__ import annotations

from pathlib import Path

from readme_doctor.fixes import language_fixes


def test_fix_is_dry_run_then_applies(tmp_path: Path) -> None:
    path = tmp_path / "README.md"
    original = "# Demo\n```pyhton\nprint('ok')\n```\n"
    path.write_text(original, encoding="utf-8")
    dry = language_fixes(path)
    assert dry.changed
    assert "python" in dry.diff
    assert path.read_text(encoding="utf-8") == original
    language_fixes(path, apply=True)
    assert "```python" in path.read_text(encoding="utf-8")
