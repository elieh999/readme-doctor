from __future__ import annotations

from readme_doctor.models import Report
from readme_doctor.reporters.redacted import redacted_report


def render_json(report: Report) -> str:
    return redacted_report(report).model_dump_json(indent=2) + "\n"
