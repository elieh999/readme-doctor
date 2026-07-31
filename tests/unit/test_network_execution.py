from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar

import httpx
import pytest

from readme_doctor import DoctorConfig, scan_repository
from readme_doctor.execution.runner import DANGEROUS
from readme_doctor.network import UnsafeRemoteURL, _require_public_destination


class FakeClient:
    calls: ClassVar[list[str]] = []

    def __init__(self, **_: Any) -> None:
        pass

    def __enter__(self) -> FakeClient:
        return self

    def __exit__(self, *_: object) -> None:
        pass

    def head(self, url: str) -> SimpleNamespace:
        self.calls.append(url)
        status = 404 if "missing" in url else 503
        return SimpleNamespace(status_code=status)

    def get(self, url: str) -> SimpleNamespace:
        return self.head(url)


def test_network_links_are_cached_and_transient_errors_are_ignored(
    repository: Path, monkeypatch: Any
) -> None:
    """A broken URL is requested once, reported per location, and 503 is treated as transient."""
    (repository / "README.md").write_text(
        "# Demo\n"
        "[one](https://example.test/missing) [two](https://example.test/missing)\n"
        "[three](https://example.test/missing)\n"
        "[temporary](https://example.test/temporary)\n"
        "## Installation\n## Usage\n## Testing\n## License\n",
        encoding="utf-8",
    )
    FakeClient.calls = []
    monkeypatch.setattr("readme_doctor.network.httpx.Client", FakeClient)
    config = DoctorConfig.model_validate({"rules": {"remote_links": {"enabled": True}}})
    report = scan_repository(repository, config)
    remote = [item for item in report.findings if item.rule_id == "RD017"]
    # Two reported locations: the repeated link on line 2 collapses into one finding, and line 3
    # is a separate location. The 503 link is transient and is not reported at all.
    assert [item.line for item in remote] == [2, 3]
    assert FakeClient.calls.count("https://example.test/missing") == 1
    assert FakeClient.calls.count("https://example.test/temporary") == 1


def test_ignored_domains_cover_subdomains(repository: Path, monkeypatch: Any) -> None:
    (repository / "README.md").write_text(
        "# Demo\n"
        "[a](https://example.test/missing)\n"
        "[b](https://docs.example.test/missing)\n"
        "## Installation\n## Usage\n## Testing\n## License\n",
        encoding="utf-8",
    )
    FakeClient.calls = []
    monkeypatch.setattr("readme_doctor.network.httpx.Client", FakeClient)
    config = DoctorConfig.model_validate(
        {"rules": {"remote_links": {"enabled": True, "ignored_domains": ["example.test"]}}}
    )
    report = scan_repository(repository, config)
    assert [item.rule_id for item in report.findings] == []
    assert FakeClient.calls == []


def test_credentials_in_a_remote_url_are_not_reported(repository: Path, monkeypatch: Any) -> None:
    (repository / "README.md").write_text(
        "# Demo\n"
        "[private](https://user:hunter2@example.test/missing)\n"
        "## Installation\n## Usage\n## Testing\n## License\n",
        encoding="utf-8",
    )
    FakeClient.calls = []
    monkeypatch.setattr("readme_doctor.network.httpx.Client", FakeClient)
    config = DoctorConfig.model_validate({"rules": {"remote_links": {"enabled": True}}})
    report = scan_repository(repository, config)
    assert "hunter2" not in report.model_dump_json()
    assert FakeClient.calls == ["https://example.test/missing"]


def test_private_network_links_are_blocked_without_a_request(
    repository: Path, monkeypatch: Any
) -> None:
    (repository / "README.md").write_text(
        "# Demo\n[private](http://127.0.0.1/admin)\n"
        "## Installation\n## Usage\n## Testing\n## License\n",
        encoding="utf-8",
    )
    FakeClient.calls = []
    monkeypatch.setattr("readme_doctor.network.httpx.Client", FakeClient)
    config = DoctorConfig.model_validate({"rules": {"remote_links": {"enabled": True}}})
    report = scan_repository(repository, config)
    remote = [item for item in report.findings if item.rule_id == "RD017"]
    assert len(remote) == 1
    assert remote[0].evidence == "status=private network destination blocked"
    assert FakeClient.calls == []


def test_request_hook_blocks_a_hostname_that_resolves_to_a_private_address(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        "readme_doctor.network.socket.getaddrinfo",
        lambda *_: [(None, None, None, None, ("10.0.0.4", 443))],
    )

    with pytest.raises(UnsafeRemoteURL, match="private network destination"):
        _require_public_destination(httpx.Request("GET", "https://internal.example/"))


def test_remote_links_are_not_requested_when_disabled(repository: Path, monkeypatch: Any) -> None:
    (repository / "README.md").write_text(
        "# Demo\n[a](https://example.test/missing)\n"
        "## Installation\n## Usage\n## Testing\n## License\n",
        encoding="utf-8",
    )
    FakeClient.calls = []
    monkeypatch.setattr("readme_doctor.network.httpx.Client", FakeClient)
    report = scan_repository(repository)
    assert FakeClient.calls == []
    assert "RD017" not in [item.rule_id for item in report.findings]


def test_execution_unavailable_produces_notice(repository: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr("readme_doctor.execution.runner.shutil.which", lambda _: None)
    config = DoctorConfig.model_validate({"execution": {"enabled": True}})
    report = scan_repository(repository, config)
    assert report.execution.backend == "unavailable"
    assert [item.rule_id for item in report.findings] == ["RD020"]


def test_execution_rejects_dangerous_and_reports_failure(
    repository: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(
        "readme_doctor.execution.runner.shutil.which", lambda _: "C:/Docker/docker.exe"
    )

    def fake_run(*_: Any, **__: Any) -> SimpleNamespace:
        return SimpleNamespace(returncode=2, stdout="token=secret-value", stderr="failed")

    monkeypatch.setattr("readme_doctor.execution.runner.subprocess.run", fake_run)
    config = DoctorConfig.model_validate(
        {
            "execution": {
                "enabled": True,
                "verify_commands": ["rm -rf build", "python -m pytest"],
            }
        }
    )
    report = scan_repository(repository, config)
    assert [item.rule_id for item in report.findings] == ["RD018", "RD018"]
    assert "secret-value" not in report.findings[1].evidence
    assert report.execution.commands_considered == 2
    assert report.execution.commands_executed == 1
    assert DANGEROUS.search("rm -rf build")


def test_execution_success_and_timeout(repository: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr("readme_doctor.execution.runner.shutil.which", lambda _: "docker")
    calls = 0

    def fake_run(*_: Any, **__: Any) -> SimpleNamespace:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise subprocess.TimeoutExpired("docker", 1)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("readme_doctor.execution.runner.subprocess.run", fake_run)
    config = DoctorConfig.model_validate(
        {
            "execution": {
                "enabled": True,
                "timeout_seconds": 1,
                "verify_commands": ["python --version", "python -m pytest"],
            }
        }
    )
    report = scan_repository(repository, config)
    assert [item.rule_id for item in report.findings] == ["RD018"]
    assert "timed out" in report.findings[0].explanation
