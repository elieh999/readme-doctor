from __future__ import annotations

from pathlib import Path

import pytest

from readme_doctor.config import ConfigError, load_config


def test_safe_valid_config(tmp_path: Path) -> None:
    path = tmp_path / "readme-doctor.yml"
    path.write_text("version: 1\nrules:\n  disabled: [RD015]\n", encoding="utf-8")
    assert load_config(path).rules.disabled == ["RD015"]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("version: 2\n", "version"),
        ("version: 1\nunknown: true\n", "unknown"),
        ("version: 1\nrules:\n  disabled: [RD999]\n", "RD999"),
        ("!!python/object:os.system ['whoami']", "constructor"),
    ],
)
def test_invalid_config_is_friendly(tmp_path: Path, text: str, expected: str) -> None:
    path = tmp_path / "bad.yml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError) as caught:
        load_config(path)
    assert expected.casefold() in str(caught.value).casefold()
