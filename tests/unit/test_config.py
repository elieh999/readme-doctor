"""Configuration loading, validation, and the effect of each setting on a scan."""

from __future__ import annotations

from pathlib import Path

import pytest

from readme_doctor import scan_repository
from readme_doctor.config import DEFAULT_CONFIG, ConfigError, DoctorConfig, load_config

SECTIONS = "\n## Installation\n\n## Usage\n\n## Testing\n\n## License\n"


def write_config(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "readme-doctor.yml"
    path.write_text(text, encoding="utf-8")
    return path


def ids(path: Path, config: DoctorConfig | None = None) -> list[str]:
    return [finding.rule_id for finding in scan_repository(path, config).findings]


# --- loading ----------------------------------------------------------------------------------


def test_no_configuration_uses_defaults() -> None:
    config = load_config(None)
    assert config.version == 1
    assert config.rules.remote_links.enabled is False
    assert config.execution.enabled is False
    assert config.rules.required_sections.enabled is True


def test_a_valid_configuration_loads(tmp_path: Path) -> None:
    path = write_config(tmp_path, "version: 1\nrules:\n  disabled: [RD015]\n")
    assert load_config(path).rules.disabled == ["RD015"]


def test_an_empty_file_is_treated_as_defaults(tmp_path: Path) -> None:
    path = write_config(tmp_path, "")
    assert load_config(path).version == 1


def test_the_generated_starter_configuration_is_valid(tmp_path: Path) -> None:
    """`readme-doctor init` must not write a file the loader then rejects."""
    path = write_config(tmp_path, DEFAULT_CONFIG)
    config = load_config(path)
    assert config.execution.enabled is False
    assert config.rules.remote_links.enabled is False


def test_a_missing_configuration_file_is_a_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(tmp_path / "absent.yml")


# --- validation errors, each naming the offending field ---------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("version: 2\n", "version"),
        ("version: 1\nunknown_key: true\n", "unknown_key"),
        ("version: 1\nrules:\n  disabled: [RD999]\n", "RD999"),
        ("version: 1\nignore:\n  rules: [RD999]\n", "RD999"),
        ("version: 1\nrules:\n  severity: {RD999: error}\n", "RD999"),
        ("version: 1\nrules:\n  severity: {RD002: critical}\n", "severity"),
        ("version: 1\nrules:\n  required_sections:\n    severity: urgent\n", "severity"),
        ("version: 1\nexecution:\n  timeout_seconds: 0\n", "timeout_seconds"),
        ("version: 1\nexecution:\n  timeout_seconds: -5\n", "timeout_seconds"),
        ("version: 1\nexecution:\n  max_output_bytes: 0\n", "max_output_bytes"),
        ("version: 1\nrules:\n  remote_links:\n    timeout_seconds: 0\n", "timeout_seconds"),
        ("version: 1\nrules:\n  remote_links:\n    timeout_seconds: 999\n", "timeout_seconds"),
        ("version: 1\nrules:\n  remote_links:\n    retries: 99\n", "retries"),
        ("version: 1\nrules:\n  remote_links:\n    redirect_limit: 0\n", "redirect_limit"),
        ("version: 1\nmax_file_size_bytes: 0\n", "max_file_size_bytes"),
        ("version: 1\nreadme:\n  paths: notalist\n", "paths"),
        ("version: 1\nexecution:\n  verify_commands: notalist\n", "verify_commands"),
        # Options that existed but were never read have been removed, so they must be refused
        # rather than silently accepted.
        ("version: 1\nexecution:\n  allow_host: true\n", "allow_host"),
        ("version: 1\nexecution:\n  allowed_code_blocks: [bash]\n", "allowed_code_blocks"),
    ],
)
def test_invalid_configuration_names_the_field(tmp_path: Path, text: str, expected: str) -> None:
    path = write_config(tmp_path, text)
    with pytest.raises(ConfigError) as caught:
        load_config(path)
    assert expected.casefold() in str(caught.value).casefold()


@pytest.mark.parametrize(
    "text",
    [
        "version: 1\nrules:\n  disabled: [RD015\n",
        "version: 1\n\tbad indent: true\n",
        "key: [unclosed\n",
    ],
)
def test_malformed_yaml_is_a_config_error(tmp_path: Path, text: str) -> None:
    path = write_config(tmp_path, text)
    with pytest.raises(ConfigError):
        load_config(path)


@pytest.mark.parametrize(
    "text",
    [
        "!!python/object:os.system ['whoami']\n",
        "version: 1\nrules: !!python/object/apply:os.system ['echo pwned']\n",
        "!!python/name:os.system\n",
    ],
)
def test_python_object_construction_is_refused(tmp_path: Path, text: str) -> None:
    path = write_config(tmp_path, text)
    with pytest.raises(ConfigError):
        load_config(path)


@pytest.mark.parametrize("text", ["- a\n- b\n", "just a string\n", "42\n"])
def test_a_non_mapping_root_is_refused(tmp_path: Path, text: str) -> None:
    path = write_config(tmp_path, text)
    with pytest.raises(ConfigError) as caught:
        load_config(path)
    assert "mapping" in str(caught.value)


def test_error_messages_do_not_expose_a_traceback(tmp_path: Path) -> None:
    path = write_config(tmp_path, "version: 1\nunknown_key: true\n")
    with pytest.raises(ConfigError) as caught:
        load_config(path)
    message = str(caught.value)
    assert "Traceback" not in message
    assert "pydantic" not in message.casefold()
    assert "unknown_key" in message


# --- each setting actually changes a scan -----------------------------------------------------


def test_a_custom_readme_path_is_used(tmp_path: Path) -> None:
    (tmp_path / "DOCS.md").write_text("# Custom\n\n[missing](nope.md)\n", encoding="utf-8")
    config = DoctorConfig.model_validate({"readme": {"paths": ["DOCS.md"]}})
    report = scan_repository(tmp_path, config)
    assert report.readme_path == "DOCS.md"
    assert "RD002" in [item.rule_id for item in report.findings]


def test_a_disabled_rule_produces_nothing(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\nTODO\n" + SECTIONS, encoding="utf-8")
    config = DoctorConfig.model_validate({"rules": {"disabled": ["RD015"]}})
    assert "RD015" not in ids(tmp_path, config)


def test_ignore_rules_also_disables(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\nTODO\n" + SECTIONS, encoding="utf-8")
    config = DoctorConfig.model_validate({"ignore": {"rules": ["RD015"]}})
    assert "RD015" not in ids(tmp_path, config)


def test_a_disabled_rule_is_absent_from_the_enabled_list() -> None:
    config = DoctorConfig.model_validate({"rules": {"disabled": ["RD015"]}})
    assert "RD015" not in config.enabled_rule_ids()
    assert "RD002" in config.enabled_rule_ids()


def test_a_custom_severity_is_applied(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\nTODO\n" + SECTIONS, encoding="utf-8")
    config = DoctorConfig.model_validate({"rules": {"severity": {"RD015": "error"}}})
    report = scan_repository(tmp_path, config)
    placeholder = next(item for item in report.findings if item.rule_id == "RD015")
    assert placeholder.severity.value == "error"
    assert report.summary.errors == 1


def test_custom_required_sections_replace_the_defaults(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\n\n## Setup\n\n## Running\n", encoding="utf-8")
    config = DoctorConfig.model_validate(
        {"rules": {"required_sections": {"sections": ["Setup", "Running"]}}}
    )
    assert "RD014" not in ids(tmp_path, config)


def test_required_sections_can_be_turned_off(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    config = DoctorConfig.model_validate({"rules": {"required_sections": {"enabled": False}}})
    assert "RD014" not in ids(tmp_path, config)


def test_a_custom_code_language_is_accepted(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "# Demo\n\n```hcl\nresource {}\n```\n" + SECTIONS, encoding="utf-8"
    )
    assert "RD006" in ids(tmp_path)
    config = DoctorConfig.model_validate({"rules": {"known_code_languages": ["hcl"]}})
    assert "RD006" not in ids(tmp_path, config)


def test_an_ignored_placeholder_phrase_is_accepted(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\n\nTODO later\n" + SECTIONS, encoding="utf-8")
    config = DoctorConfig.model_validate({"rules": {"ignored_placeholders": ["todo"]}})
    assert "RD015" not in ids(tmp_path, config)


def test_custom_ignore_paths_exclude_a_directory(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\n" + SECTIONS, encoding="utf-8")
    generated = tmp_path / "generated"
    generated.mkdir()
    (generated / "app.py").write_text(
        "import os\nos.environ['GENERATED_VARIABLE']\n", encoding="utf-8"
    )
    assert "RD012" in ids(tmp_path)
    config = DoctorConfig.model_validate({"ignore": {"paths": ["generated/**"]}})
    assert "RD012" not in ids(tmp_path, config)


def test_environment_checks_can_be_turned_off(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\n" + SECTIONS, encoding="utf-8")
    (tmp_path / ".env.example").write_text("SOME_VARIABLE=\n", encoding="utf-8")
    assert "RD012" in ids(tmp_path)
    config = DoctorConfig.model_validate({"rules": {"environment_variables": {"enabled": False}}})
    assert "RD012" not in ids(tmp_path, config)


def test_a_custom_example_file_name_is_read(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\n" + SECTIONS, encoding="utf-8")
    (tmp_path / "env.template").write_text("CUSTOM_VARIABLE=\n", encoding="utf-8")
    assert "RD012" not in ids(tmp_path)
    config = DoctorConfig.model_validate(
        {"rules": {"environment_variables": {"example_files": ["env.template"]}}}
    )
    assert "RD012" in ids(tmp_path, config)


def test_network_and_execution_settings_round_trip() -> None:
    config = DoctorConfig.model_validate(
        {
            "rules": {
                "remote_links": {
                    "enabled": True,
                    "timeout_seconds": 2.5,
                    "retries": 3,
                    "redirect_limit": 2,
                    "ignored_domains": ["example.com"],
                    "allowed_status_codes": [200, 203],
                }
            },
            "execution": {
                "enabled": True,
                "timeout_seconds": 30,
                "docker_image": "python:3.11-slim",
                "verify_commands": ["python --version"],
                "max_output_bytes": 1024,
            },
        }
    )
    assert config.rules.remote_links.timeout_seconds == 2.5
    assert config.rules.remote_links.ignored_domains == ["example.com"]
    assert config.rules.remote_links.allowed_status_codes == [200, 203]
    assert config.execution.docker_image == "python:3.11-slim"
    assert config.execution.verify_commands == ["python --version"]
    assert config.execution.max_output_bytes == 1024
