from __future__ import annotations

import sys
import threading
import traceback
from pathlib import Path
from tkinter import (
    BOTH,
    END,
    HORIZONTAL,
    LEFT,
    RIGHT,
    VERTICAL,
    BooleanVar,
    StringVar,
    Tk,
    filedialog,
    messagebox,
    ttk,
)
from typing import Any

from readme_doctor.config import ConfigError, load_config
from readme_doctor.engine import scan_repository
from readme_doctor.models import Finding, Report, Severity
from readme_doctor.reporters import render_json, render_sarif

APP_NAME = "README Doctor"
APP_VERSION = "0.1.0"


def _crash_log_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "README Doctor Error.log"
    return Path.cwd() / "README Doctor Error.log"


class DoctorDesktop:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title(f"{APP_NAME} {APP_VERSION}")
        self.root.geometry("1180x760")
        self.root.minsize(900, 620)
        self.root.configure(background="#edf3fb")
        self.repository = StringVar(value=str(Path.cwd()))
        self.config_path = StringVar()
        self.network = BooleanVar(value=False)
        self.strict = BooleanVar(value=False)
        self.status = StringVar(value="Choose a repository, then start a scan.")
        self.summary = StringVar(value="No scan yet")
        self.current_report: Report | None = None
        self._build_styles()
        self._build_layout()

    def _build_styles(self) -> None:
        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure(".", font=("Segoe UI", 10))
        style.configure("App.TFrame", background="#edf3fb")
        style.configure("Panel.TFrame", background="#ffffff")
        style.configure(
            "Title.TLabel",
            background="#edf3fb",
            foreground="#102a56",
            font=("Segoe UI Semibold", 23),
        )
        style.configure(
            "Subtitle.TLabel",
            background="#edf3fb",
            foreground="#58708f",
            font=("Segoe UI", 10),
        )
        style.configure(
            "PanelTitle.TLabel",
            background="#ffffff",
            foreground="#17365f",
            font=("Segoe UI Semibold", 11),
        )
        style.configure("Panel.TLabel", background="#ffffff", foreground="#304a6e")
        style.configure(
            "Summary.TLabel",
            background="#ffffff",
            foreground="#0e5f55",
            font=("Segoe UI Semibold", 12),
        )
        style.configure(
            "Primary.TButton",
            font=("Segoe UI Semibold", 10),
            padding=(18, 9),
        )
        style.configure("TButton", padding=(12, 7))
        style.configure("Treeview", rowheight=30, fieldbackground="#ffffff", background="#ffffff")
        style.configure(
            "Treeview.Heading",
            font=("Segoe UI Semibold", 9),
            foreground="#17365f",
        )

    def _build_layout(self) -> None:
        outer = ttk.Frame(self.root, style="App.TFrame", padding=24)
        outer.pack(fill=BOTH, expand=True)

        header = ttk.Frame(outer, style="App.TFrame")
        header.pack(fill="x", pady=(0, 18))
        ttk.Label(header, text=APP_NAME, style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Check whether README instructions still match the project around them.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        controls = ttk.Frame(outer, style="Panel.TFrame", padding=18)
        controls.pack(fill="x", pady=(0, 14))
        controls.columnconfigure(1, weight=1)

        ttk.Label(controls, text="Repository", style="PanelTitle.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 12), pady=(0, 10)
        )
        ttk.Entry(controls, textvariable=self.repository).grid(
            row=0, column=1, sticky="ew", pady=(0, 10)
        )
        ttk.Button(controls, text="Browse…", command=self.choose_repository).grid(
            row=0, column=2, padx=(10, 0), pady=(0, 10)
        )

        ttk.Label(controls, text="Configuration", style="Panel.TLabel").grid(
            row=1, column=0, sticky="w", padx=(0, 12)
        )
        ttk.Entry(controls, textvariable=self.config_path).grid(row=1, column=1, sticky="ew")
        ttk.Button(controls, text="Choose…", command=self.choose_config).grid(
            row=1, column=2, padx=(10, 0)
        )

        options = ttk.Frame(controls, style="Panel.TFrame")
        options.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(14, 0))
        ttk.Checkbutton(options, text="Check remote links", variable=self.network).pack(side=LEFT)
        ttk.Checkbutton(
            options,
            text="Strict result threshold",
            variable=self.strict,
        ).pack(side=LEFT, padx=(18, 0))
        self.scan_button = ttk.Button(
            options,
            text="Scan repository",
            style="Primary.TButton",
            command=self.start_scan,
        )
        self.scan_button.pack(side=RIGHT)

        result_panel = ttk.Frame(outer, style="Panel.TFrame", padding=16)
        result_panel.pack(fill=BOTH, expand=True)
        result_panel.rowconfigure(1, weight=1)
        result_panel.columnconfigure(0, weight=1)

        result_header = ttk.Frame(result_panel, style="Panel.TFrame")
        result_header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(result_header, textvariable=self.summary, style="Summary.TLabel").pack(side=LEFT)
        ttk.Button(result_header, text="Export JSON", command=self.export_json).pack(side=RIGHT)
        ttk.Button(result_header, text="Export SARIF", command=self.export_sarif).pack(
            side=RIGHT, padx=(0, 8)
        )

        tree_frame = ttk.Frame(result_panel, style="Panel.TFrame")
        tree_frame.grid(row=1, column=0, sticky="nsew")
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        columns = ("severity", "rule", "location", "message")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings")
        self.tree.heading("severity", text="Severity")
        self.tree.heading("rule", text="Rule")
        self.tree.heading("location", text="Location")
        self.tree.heading("message", text="Finding")
        self.tree.column("severity", width=90, minwidth=80, stretch=False)
        self.tree.column("rule", width=80, minwidth=70, stretch=False)
        self.tree.column("location", width=220, minwidth=140)
        self.tree.column("message", width=650, minwidth=280)
        self.tree.tag_configure("error", foreground="#a61b29")
        self.tree.tag_configure("warning", foreground="#996000")
        self.tree.tag_configure("notice", foreground="#176b87")
        self.tree.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(tree_frame, orient=VERTICAL, command=self.tree.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(tree_frame, orient=HORIZONTAL, command=self.tree.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.tree.bind("<<TreeviewSelect>>", self.show_selected_finding)

        detail = ttk.LabelFrame(result_panel, text="Finding details", padding=10)
        detail.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        self.detail = StringVar(
            value="Select a finding to see evidence and the suggested correction."
        )
        ttk.Label(
            detail,
            textvariable=self.detail,
            wraplength=1040,
            justify=LEFT,
        ).pack(fill="x")

        ttk.Label(outer, textvariable=self.status, style="Subtitle.TLabel").pack(
            fill="x", pady=(10, 0)
        )

    def choose_repository(self) -> None:
        chosen = filedialog.askdirectory(
            title="Choose a repository",
            initialdir=self.repository.get() or str(Path.cwd()),
        )
        if chosen:
            self.repository.set(chosen)

    def choose_config(self) -> None:
        chosen = filedialog.askopenfilename(
            title="Choose readme-doctor.yml",
            filetypes=[("YAML files", "*.yml *.yaml"), ("All files", "*.*")],
        )
        if chosen:
            self.config_path.set(chosen)

    def start_scan(self) -> None:
        repository = Path(self.repository.get()).expanduser()
        if not repository.is_dir():
            messagebox.showerror(APP_NAME, "Choose an existing repository folder.")
            return
        self.scan_button.configure(state="disabled")
        self.status.set("Scanning repository…")
        self.summary.set("Scan in progress")
        self._clear_findings()
        config_file = Path(self.config_path.get()) if self.config_path.get() else None
        network_enabled = self.network.get()
        threading.Thread(
            target=self._scan_worker,
            args=(repository, config_file, network_enabled),
            daemon=True,
        ).start()

    def _scan_worker(
        self,
        repository: Path,
        config_file: Path | None,
        network_enabled: bool,
    ) -> None:
        try:
            config = load_config(config_file)
            config = config.model_copy(
                update={
                    "rules": config.rules.model_copy(
                        update={
                            "remote_links": config.rules.remote_links.model_copy(
                                update={"enabled": network_enabled}
                            )
                        }
                    ),
                    "execution": config.execution.model_copy(update={"enabled": False}),
                }
            )
            report = scan_repository(repository, config)
            self.root.after(0, self._scan_complete, report)
        except (ConfigError, OSError, ValueError) as exc:
            self.root.after(0, self._scan_failed, str(exc))
        except Exception:
            details = traceback.format_exc()
            _crash_log_path().write_text(details, encoding="utf-8")
            self.root.after(
                0,
                self._scan_failed,
                f"An unexpected error occurred. Details were saved to {_crash_log_path()}.",
            )

    def _scan_complete(self, report: Report) -> None:
        self.current_report = report
        self._clear_findings()
        for index, finding in enumerate(report.findings):
            location = finding.path
            if finding.line:
                location += f":{finding.line}"
            self.tree.insert(
                "",
                END,
                iid=str(index),
                values=(
                    finding.severity.value.upper(),
                    finding.rule_id,
                    location,
                    finding.explanation,
                ),
                tags=(finding.severity.value,),
            )
        counts = report.summary
        self.summary.set(
            f"{counts.errors} errors   •   {counts.warnings} warnings   •   "
            f"{counts.notices} notices"
        )
        threshold_failed = (
            bool(report.findings)
            if self.strict.get()
            else any(item.severity is Severity.ERROR for item in report.findings)
        )
        if not report.findings:
            self.status.set(f"Scan complete in {report.scan_duration_seconds:.2f}s. No findings.")
        elif threshold_failed:
            self.status.set(
                f"Scan complete in {report.scan_duration_seconds:.2f}s. Attention required."
            )
        else:
            self.status.set(
                f"Scan complete in {report.scan_duration_seconds:.2f}s. No error-level findings."
            )
        self.scan_button.configure(state="normal")

    def _scan_failed(self, message: str) -> None:
        self.summary.set("Scan could not be completed")
        self.status.set(message)
        self.scan_button.configure(state="normal")
        messagebox.showerror(APP_NAME, message)

    def _clear_findings(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.detail.set("Select a finding to see evidence and the suggested correction.")

    def show_selected_finding(self, _: Any = None) -> None:
        if self.current_report is None:
            return
        selection = self.tree.selection()
        if not selection:
            return
        finding: Finding = self.current_report.findings[int(selection[0])]
        self.detail.set(
            f"{finding.title}\nEvidence: {finding.evidence}\n"
            f"Suggestion: {finding.suggestion}\nConfidence: {finding.confidence.value}"
        )

    def export_json(self) -> None:
        self._export_report("JSON report", ".json", render_json)

    def export_sarif(self) -> None:
        self._export_report("SARIF report", ".sarif", render_sarif)

    def _export_report(self, title: str, extension: str, renderer: Any) -> None:
        if self.current_report is None:
            messagebox.showinfo(APP_NAME, "Run a scan before exporting a report.")
            return
        destination = filedialog.asksaveasfilename(
            title=f"Save {title}",
            defaultextension=extension,
            filetypes=[(title, f"*{extension}"), ("All files", "*.*")],
        )
        if not destination:
            return
        Path(destination).write_text(renderer(self.current_report), encoding="utf-8")
        self.status.set(f"Saved {title} to {destination}")


def main() -> None:
    root = Tk()
    DoctorDesktop(root)
    root.mainloop()


if __name__ == "__main__":
    main()
