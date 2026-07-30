from __future__ import annotations

import sys
from pathlib import Path
from tkinter import Tk
from typing import Any

from readme_doctor import scan_repository
from readme_doctor.gui import APP_NAME, APP_VERSION, DoctorDesktop, _crash_log_path


def test_gui_metadata() -> None:
    assert APP_NAME == "README Doctor"
    assert APP_VERSION == "0.1.0"


def test_crash_log_uses_working_directory_when_not_frozen(
    tmp_path: Path, monkeypatch: object
) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    monkeypatch.delattr(sys, "frozen", raising=False)  # type: ignore[attr-defined]
    assert _crash_log_path() == tmp_path / "README Doctor Error.log"


def test_desktop_renders_findings_and_exports(
    repository: Path,
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    (repository / "README.md").write_text("# Demo\nTODO\n", encoding="utf-8")
    root = Tk()
    root.withdraw()
    desktop = DoctorDesktop(root)
    report = scan_repository(repository)
    desktop._scan_complete(report)
    assert desktop.current_report is report
    assert len(desktop.tree.get_children()) == len(report.findings)
    desktop.tree.selection_set("0")
    desktop.show_selected_finding()
    assert "Evidence:" in desktop.detail.get()

    json_path = tmp_path / "report.json"
    monkeypatch.setattr(
        "readme_doctor.gui.filedialog.asksaveasfilename",
        lambda **_: str(json_path),
    )
    desktop.export_json()
    assert '"tool_version": "0.1.0"' in json_path.read_text(encoding="utf-8")

    sarif_path = tmp_path / "report.sarif"
    monkeypatch.setattr(
        "readme_doctor.gui.filedialog.asksaveasfilename",
        lambda **_: str(sarif_path),
    )
    desktop.export_sarif()
    assert '"version": "2.1.0"' in sarif_path.read_text(encoding="utf-8")
    monkeypatch.setattr(
        "readme_doctor.gui.filedialog.askdirectory",
        lambda **_: str(repository),
    )
    desktop.choose_repository()
    assert desktop.repository.get() == str(repository)

    config = tmp_path / "readme-doctor.yml"
    config.write_text("version: 1\n", encoding="utf-8")
    monkeypatch.setattr(
        "readme_doctor.gui.filedialog.askopenfilename",
        lambda **_: str(config),
    )
    desktop.choose_config()
    assert desktop.config_path.get() == str(config)

    monkeypatch.setattr(root, "after", lambda _delay, function, *args: function(*args))
    desktop._scan_worker(repository, config, False)
    assert desktop.current_report is not None
    assert "errors" in desktop.summary.get()
    desktop._clear_findings()
    assert not desktop.tree.get_children()
    root.destroy()
