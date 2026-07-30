"""The Windows desktop interface.

These tests use one shared hidden Tk root from the `tk_root` fixture. They skip when Tk cannot
start, which is the case on a headless runner.
"""

from __future__ import annotations

import sys
from pathlib import Path
from tkinter import Tk
from typing import Any

from readme_doctor import scan_repository
from readme_doctor.gui import (
    APP_NAME,
    APP_VERSION,
    DoctorDesktop,
    _crash_log_path,
    _write_crash_log,
)


def test_gui_metadata() -> None:
    assert APP_NAME == "README Doctor"
    assert APP_VERSION == "0.1.0"


def test_crash_log_uses_working_directory_when_not_frozen(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert _crash_log_path() == tmp_path / "README Doctor Error.log"


def test_crash_log_uses_the_executable_directory_when_frozen(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "README Doctor.exe"))
    assert _crash_log_path() == tmp_path / "README Doctor Error.log"


def test_crash_log_returns_the_path_it_wrote(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delattr(sys, "frozen", raising=False)
    written = _write_crash_log("traceback details")
    assert written is not None
    assert written.read_text(encoding="utf-8") == "traceback details"


def test_crash_log_failure_does_not_raise(monkeypatch: Any) -> None:
    """The executable can sit somewhere unwritable. That must not replace the original error."""

    def refuse(*_: object, **__: object) -> None:
        raise OSError("read only location")

    monkeypatch.setattr("readme_doctor.gui.Path.write_text", refuse)
    assert _write_crash_log("details") is None


def test_a_stale_selection_index_does_not_crash(tk_root: Tk, tmp_path: Path) -> None:
    """Deleting rows changes the selection, so the handler can see an index from a longer report."""
    many = tmp_path / "many"
    few = tmp_path / "few"
    many.mkdir()
    few.mkdir()
    (many / "README.md").write_text(
        "# Many\n\n" + "\n".join(f"[a{n}](missing{n}.md)" for n in range(10)) + "\n",
        encoding="utf-8",
    )
    (few / "README.md").write_text("# Few\n\n[a](missing.md)\n", encoding="utf-8")

    desktop = DoctorDesktop(tk_root)
    desktop._scan_complete(scan_repository(many))
    assert len(desktop.tree.get_children()) >= 10

    long_count = len(desktop.tree.get_children())
    short = scan_repository(few)
    assert len(short.findings) < long_count

    # The state the crash needed: a row id from the long report still selected while the report
    # object has already been replaced by the shorter one.
    desktop.current_report = short
    desktop._clear_findings()
    stale = str(long_count - 1)
    desktop.tree.insert("", "end", iid=stale, values=("ERROR", "RD002", "x", "y"))
    desktop.tree.selection_set(stale)
    desktop.show_selected_finding()

    desktop.tree.insert("", "end", iid="not-a-number", values=("ERROR", "RD002", "x", "y"))
    desktop.tree.selection_set("not-a-number")
    desktop.show_selected_finding()

    desktop._scan_complete(short)
    assert len(desktop.tree.get_children()) == len(short.findings)


def test_selection_without_a_report_is_ignored(tk_root: Tk) -> None:
    desktop = DoctorDesktop(tk_root)
    desktop.show_selected_finding()
    assert "Select a finding" in desktop.detail.get()


def test_findings_render_with_severity_tags(tk_root: Tk, repository: Path) -> None:
    (repository / "README.md").write_text(
        "# Demo\n\n[missing](nope.md)\nTODO finish\n\n```\n```\n", encoding="utf-8"
    )
    desktop = DoctorDesktop(tk_root)
    report = scan_repository(repository)
    desktop._scan_complete(report)
    assert len(desktop.tree.get_children()) == len(report.findings)
    severities = {str(desktop.tree.item(item, "tags")[0]) for item in desktop.tree.get_children()}
    assert severities <= {"error", "warning", "notice"}
    assert "errors" in desktop.summary.get()


def test_selected_finding_shows_evidence_and_confidence(tk_root: Tk, repository: Path) -> None:
    (repository / "README.md").write_text("# Demo\nTODO\n", encoding="utf-8")
    desktop = DoctorDesktop(tk_root)
    desktop._scan_complete(scan_repository(repository))
    desktop.tree.selection_set("0")
    desktop.show_selected_finding()
    detail = desktop.detail.get()
    assert "Evidence:" in detail
    assert "Suggestion:" in detail
    assert "Confidence:" in detail


def test_a_clean_repository_reports_no_findings(tk_root: Tk, repository: Path) -> None:
    desktop = DoctorDesktop(tk_root)
    desktop._scan_complete(scan_repository(repository))
    assert desktop.tree.get_children() == ()
    assert "No findings" in desktop.status.get()


def test_json_and_sarif_exports_are_written(
    tk_root: Tk, repository: Path, tmp_path: Path, monkeypatch: Any
) -> None:
    (repository / "README.md").write_text("# Demo\nTODO\n", encoding="utf-8")
    desktop = DoctorDesktop(tk_root)
    desktop._scan_complete(scan_repository(repository))

    json_path = tmp_path / "report.json"
    monkeypatch.setattr(
        "readme_doctor.gui.filedialog.asksaveasfilename", lambda **_: str(json_path)
    )
    desktop.export_json()
    assert '"tool_version": "0.1.0"' in json_path.read_text(encoding="utf-8")

    sarif_path = tmp_path / "report.sarif"
    monkeypatch.setattr(
        "readme_doctor.gui.filedialog.asksaveasfilename", lambda **_: str(sarif_path)
    )
    desktop.export_sarif()
    assert '"version": "2.1.0"' in sarif_path.read_text(encoding="utf-8")


def test_a_cancelled_export_dialog_writes_nothing(
    tk_root: Tk, repository: Path, monkeypatch: Any
) -> None:
    (repository / "README.md").write_text("# Demo\nTODO\n", encoding="utf-8")
    desktop = DoctorDesktop(tk_root)
    desktop._scan_complete(scan_repository(repository))
    monkeypatch.setattr("readme_doctor.gui.filedialog.asksaveasfilename", lambda **_: "")
    desktop.export_json()
    assert "Saved" not in desktop.status.get()


def test_an_unwritable_export_destination_is_reported_not_raised(
    tk_root: Tk, repository: Path, tmp_path: Path, monkeypatch: Any
) -> None:
    (repository / "README.md").write_text("# Demo\nTODO\n", encoding="utf-8")
    desktop = DoctorDesktop(tk_root)
    desktop._scan_complete(scan_repository(repository))
    # A directory path cannot be written to as a file.
    monkeypatch.setattr("readme_doctor.gui.filedialog.asksaveasfilename", lambda **_: str(tmp_path))
    errors: list[str] = []
    monkeypatch.setattr(
        "readme_doctor.gui.messagebox.showerror", lambda _title, message: errors.append(message)
    )
    desktop.export_json()
    assert errors, "the failure must be shown to the user"
    assert "Could not save" in errors[0]


def test_exporting_before_a_scan_asks_for_a_scan(tk_root: Tk, monkeypatch: Any) -> None:
    desktop = DoctorDesktop(tk_root)
    messages: list[str] = []
    monkeypatch.setattr(
        "readme_doctor.gui.messagebox.showinfo", lambda _title, message: messages.append(message)
    )
    desktop.export_json()
    desktop.export_sarif()
    assert len(messages) == 2


def test_a_missing_repository_folder_is_refused(
    tk_root: Tk, tmp_path: Path, monkeypatch: Any
) -> None:
    desktop = DoctorDesktop(tk_root)
    desktop.repository.set(str(tmp_path / "absent"))
    errors: list[str] = []
    monkeypatch.setattr(
        "readme_doctor.gui.messagebox.showerror", lambda _title, message: errors.append(message)
    )
    desktop.start_scan()
    assert errors == ["Choose an existing repository folder."]


def test_an_invalid_configuration_is_reported_and_the_button_returns(
    tk_root: Tk, repository: Path, monkeypatch: Any
) -> None:
    desktop = DoctorDesktop(tk_root)
    config = repository / "bad.yml"
    config.write_text("version: 99\n", encoding="utf-8")
    monkeypatch.setattr(tk_root, "after", lambda _delay, function, *args: function(*args))
    monkeypatch.setattr("readme_doctor.gui.messagebox.showerror", lambda *_: None)
    desktop._scan_worker(repository, config, False)
    assert "could not be completed" in desktop.summary.get()
    assert str(desktop.scan_button.cget("state")) == "normal"


def test_an_unexpected_failure_is_logged_and_surfaced(
    tk_root: Tk, repository: Path, tmp_path: Path, monkeypatch: Any
) -> None:
    desktop = DoctorDesktop(tk_root)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(tk_root, "after", lambda _delay, function, *args: function(*args))
    monkeypatch.setattr("readme_doctor.gui.messagebox.showerror", lambda *_: None)

    def explode(*_: object, **__: object) -> None:
        raise RuntimeError("unexpected internal failure")

    monkeypatch.setattr("readme_doctor.gui.scan_repository", explode)
    desktop._scan_worker(repository, None, False)
    log = tmp_path / "README Doctor Error.log"
    assert log.is_file()
    assert "unexpected internal failure" in log.read_text(encoding="utf-8")
    assert str(desktop.scan_button.cget("state")) == "normal"


def test_the_strict_option_changes_the_reported_status(tk_root: Tk, repository: Path) -> None:
    (repository / "README.md").write_text("# Demo\nTODO finish\n", encoding="utf-8")
    report = scan_repository(repository)
    assert report.summary.errors == 0 and report.summary.warnings > 0

    desktop = DoctorDesktop(tk_root)
    desktop.strict.set(False)
    desktop._scan_complete(report)
    assert "No error-level findings" in desktop.status.get()

    desktop.strict.set(True)
    desktop._scan_complete(report)
    assert "Attention required" in desktop.status.get()


def test_the_desktop_never_enables_command_execution(
    tk_root: Tk, repository: Path, monkeypatch: Any
) -> None:
    """The interface has no execution control, and must not inherit one from configuration."""
    config = repository / "readme-doctor.yml"
    config.write_text(
        "version: 1\nexecution:\n  enabled: true\n  verify_commands: [python --version]\n",
        encoding="utf-8",
    )
    desktop = DoctorDesktop(tk_root)
    monkeypatch.setattr(tk_root, "after", lambda _delay, function, *args: function(*args))
    desktop._scan_worker(repository, config, False)
    assert desktop.current_report is not None
    assert desktop.current_report.execution.enabled is False
    assert desktop.current_report.execution.commands_executed == 0


def test_remote_link_checking_follows_the_checkbox(
    tk_root: Tk, repository: Path, monkeypatch: Any
) -> None:
    captured: list[bool] = []

    def record(_path: Path, config: Any) -> Any:
        captured.append(config.rules.remote_links.enabled)
        return scan_repository(_path)

    desktop = DoctorDesktop(tk_root)
    monkeypatch.setattr(tk_root, "after", lambda _delay, function, *args: function(*args))
    monkeypatch.setattr("readme_doctor.gui.scan_repository", record)
    desktop._scan_worker(repository, None, False)
    desktop._scan_worker(repository, None, True)
    assert captured == [False, True]


def test_browse_dialogs_set_the_selected_paths(
    tk_root: Tk, repository: Path, tmp_path: Path, monkeypatch: Any
) -> None:
    desktop = DoctorDesktop(tk_root)
    monkeypatch.setattr("readme_doctor.gui.filedialog.askdirectory", lambda **_: str(repository))
    desktop.choose_repository()
    assert desktop.repository.get() == str(repository)

    config = tmp_path / "readme-doctor.yml"
    config.write_text("version: 1\n", encoding="utf-8")
    monkeypatch.setattr("readme_doctor.gui.filedialog.askopenfilename", lambda **_: str(config))
    desktop.choose_config()
    assert desktop.config_path.get() == str(config)


def test_cancelled_browse_dialogs_leave_the_paths_alone(
    tk_root: Tk, repository: Path, monkeypatch: Any
) -> None:
    desktop = DoctorDesktop(tk_root)
    desktop.repository.set(str(repository))
    monkeypatch.setattr("readme_doctor.gui.filedialog.askdirectory", lambda **_: "")
    monkeypatch.setattr("readme_doctor.gui.filedialog.askopenfilename", lambda **_: "")
    desktop.choose_repository()
    desktop.choose_config()
    assert desktop.repository.get() == str(repository)
    assert desktop.config_path.get() == ""
