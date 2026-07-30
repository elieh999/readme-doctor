"""Public API for README Doctor."""

from readme_doctor.config import DoctorConfig
from readme_doctor.engine import scan_repository
from readme_doctor.models import Finding, Report

__all__ = ["DoctorConfig", "Finding", "Report", "scan_repository"]
__version__ = "0.1.0"
