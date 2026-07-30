from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, PositiveInt, ValidationError, field_validator

from readme_doctor.models import Severity
from readme_doctor.rules import RULES


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReadmeConfig(StrictModel):
    paths: list[str] = Field(
        default_factory=lambda: ["README.md", "Readme.md", "readme.md", "README.rst"]
    )


class RequiredSectionsConfig(StrictModel):
    enabled: bool = True
    severity: Severity = Severity.NOTICE
    sections: list[str] = Field(
        default_factory=lambda: ["Installation", "Usage", "Testing", "License"]
    )


class RemoteLinksConfig(StrictModel):
    enabled: bool = False
    timeout_seconds: float = Field(default=5.0, gt=0, le=60)
    retries: int = Field(default=1, ge=0, le=5)
    redirect_limit: PositiveInt = 5
    ignored_domains: list[str] = Field(default_factory=list)
    allowed_status_codes: list[int] = Field(default_factory=lambda: [200, 204, 301, 302, 307, 308])


class EnvironmentConfig(StrictModel):
    enabled: bool = True
    example_files: list[str] = Field(
        default_factory=lambda: [".env.example", ".env.sample", ".env.template"]
    )


class RuleConfig(StrictModel):
    required_sections: RequiredSectionsConfig = Field(default_factory=RequiredSectionsConfig)
    remote_links: RemoteLinksConfig = Field(default_factory=RemoteLinksConfig)
    environment_variables: EnvironmentConfig = Field(default_factory=EnvironmentConfig)
    disabled: list[str] = Field(default_factory=list)
    severity: dict[str, Severity] = Field(default_factory=dict)
    known_code_languages: list[str] = Field(default_factory=list)
    decorative_images: list[str] = Field(default_factory=list)
    ignored_placeholders: list[str] = Field(default_factory=list)

    @field_validator("disabled")
    @classmethod
    def valid_disabled_rules(cls, value: list[str]) -> list[str]:
        unknown = sorted(set(value) - RULES.keys())
        if unknown:
            raise ValueError(f"unknown rule identifiers: {', '.join(unknown)}")
        return value

    @field_validator("severity")
    @classmethod
    def valid_severity_rules(cls, value: dict[str, Severity]) -> dict[str, Severity]:
        unknown = sorted(set(value) - RULES.keys())
        if unknown:
            raise ValueError(f"unknown rule identifiers: {', '.join(unknown)}")
        return value


class ExecutionConfig(StrictModel):
    """Settings for the opt in command verification subsystem.

    Only `verify_commands` is ever executed. README code blocks are never a command source, so
    there is no option to select which fenced languages may run.
    """

    enabled: bool = False
    timeout_seconds: PositiveInt = 120
    docker_image: str = "python:3.12-slim"
    verify_commands: list[str] = Field(default_factory=list)
    max_output_bytes: PositiveInt = 32_768


class IgnoreConfig(StrictModel):
    rules: list[str] = Field(default_factory=list)
    paths: list[str] = Field(
        default_factory=lambda: [
            ".git/**",
            ".venv/**",
            "venv/**",
            "node_modules/**",
            "vendor/**",
            "build/**",
            "dist/**",
            "tests/**",
        ]
    )

    @field_validator("rules")
    @classmethod
    def valid_rules(cls, value: list[str]) -> list[str]:
        unknown = sorted(set(value) - RULES.keys())
        if unknown:
            raise ValueError(f"unknown rule identifiers: {', '.join(unknown)}")
        return value


class DoctorConfig(StrictModel):
    version: Literal[1] = 1
    readme: ReadmeConfig = Field(default_factory=ReadmeConfig)
    rules: RuleConfig = Field(default_factory=RuleConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    ignore: IgnoreConfig = Field(default_factory=IgnoreConfig)
    max_file_size_bytes: PositiveInt = 2_000_000

    def enabled_rule_ids(self) -> list[str]:
        disabled = set(self.rules.disabled) | set(self.ignore.rules)
        return sorted(RULES.keys() - disabled)


DEFAULT_CONFIG = """version: 1

readme:
  paths:
    - README.md

rules:
  required_sections:
    enabled: true
    severity: notice
    sections:
      - Installation
      - Usage
      - Testing
  remote_links:
    enabled: false
  environment_variables:
    enabled: true
    example_files:
      - .env.example

# Command verification is opt in and requires both `enabled: true` here and the --execute flag.
# Only the commands listed below can run, and they run inside a confined Docker container.
execution:
  enabled: false
  timeout_seconds: 120
  docker_image: python:3.12-slim
  verify_commands: []

ignore:
  rules: []
  paths:
    - vendor/**
    - build/**
"""


class ConfigError(Exception):
    pass


def load_config(path: Path | None) -> DoctorConfig:
    if path is None:
        return DoctorConfig()
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"{path}: {exc}") from exc
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: configuration root must be a mapping")
    try:
        return DoctorConfig.model_validate(raw)
    except ValidationError as exc:
        messages = []
        for error in exc.errors(include_url=False):
            location = ".".join(str(part) for part in error["loc"])
            messages.append(f"{location}: {error['msg']}")
        raise ConfigError(f"{path}: " + "; ".join(messages)) from exc
