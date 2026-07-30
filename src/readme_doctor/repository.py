from __future__ import annotations

import fnmatch
import os
from collections.abc import Iterator
from pathlib import Path

from readme_doctor.config import DoctorConfig

# Directory names that never contain first party source, regardless of configuration. Matching by
# name alone is not enough, because a virtual environment can be called anything, so the presence
# of `pyvenv.cfg` is treated as the definitive marker.
ALWAYS_SKIPPED = {
    ".git",
    ".hg",
    ".svn",
    ".tox",
    ".nox",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "node_modules",
    "site-packages",
    "bower_components",
    ".dart_tool",
    ".gradle",
    ".terraform",
}
VENV_MARKER = "pyvenv.cfg"


class Repository:
    def __init__(self, root: Path, config: DoctorConfig) -> None:
        self.root = root.resolve()
        self.config = config

    def relative(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()

    def safe_path(self, base: Path, target: str) -> Path | None:
        candidate = (base / target).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError:
            return None
        return candidate

    def find_readme(self) -> Path | None:
        for configured in self.config.readme.paths:
            candidate = self.root / configured
            if candidate.is_file():
                return candidate
        by_case = {entry.name.casefold(): entry for entry in self.root.iterdir() if entry.is_file()}
        for configured in self.config.readme.paths:
            if configured.casefold() in by_case:
                return by_case[configured.casefold()]
        return None

    def ignored(self, path: Path) -> bool:
        relative = path.relative_to(self.root).as_posix()
        return any(
            fnmatch.fnmatch(relative, pattern) or fnmatch.fnmatch(f"{relative}/", pattern)
            for pattern in self.config.ignore.paths
        )

    def skipped_directory(self, path: Path) -> bool:
        """Whether a directory should never be traversed.

        This covers version control metadata, caches, dependency trees, and virtual environments.
        A virtual environment is recognized by its `pyvenv.cfg` marker rather than by name, so an
        environment called `.package-test` or `env311` is skipped just like `.venv`.
        """
        if path.name in ALWAYS_SKIPPED:
            return True
        try:
            return (path / VENV_MARKER).is_file()
        except OSError:
            return True

    def files(self, suffixes: set[str] | None = None) -> Iterator[Path]:
        for directory, names, files in os.walk(self.root, followlinks=False):
            directory_path = Path(directory)
            names[:] = [
                name
                for name in names
                if not self.ignored(directory_path / name)
                and not self.skipped_directory(directory_path / name)
                and not (directory_path / name).is_symlink()
            ]
            for name in files:
                path = directory_path / name
                if self.ignored(path) or path.is_symlink():
                    continue
                if suffixes is not None and path.suffix.lower() not in suffixes:
                    continue
                try:
                    if path.stat().st_size > self.config.max_file_size_bytes:
                        continue
                except OSError:
                    continue
                yield path

    def case_sensitive_exists(self, path: Path) -> tuple[bool, bool]:
        if not path.exists():
            parent = path.parent
            if parent.is_dir():
                names = {entry.name.casefold(): entry.name for entry in parent.iterdir()}
                return (path.name.casefold() in names, path.name not in names.values())
            return (False, False)
        current = self.root
        case_difference = False
        try:
            parts = path.resolve().relative_to(self.root).parts
        except ValueError:
            return (False, False)
        for part in parts:
            actual = {entry.name.casefold(): entry.name for entry in current.iterdir()}
            if part.casefold() not in actual:
                return (False, False)
            if actual[part.casefold()] != part:
                case_difference = True
            current /= actual[part.casefold()]
        return (True, case_difference)
