from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

import yaml

from readme_doctor.checks.base import CheckContext
from readme_doctor.models import Confidence, Finding

PYTHON_README = re.compile(
    r"\bPython\s+(?:version\s+)?(?:>=?\s*)?(\d+\.\d+)(?:\s*(?:or newer|\+))?", re.IGNORECASE
)
NODE_README = re.compile(
    r"\bNode(?:\.js)?\s+(?:version\s+)?(?:>=?\s*|v)?(\d+)(?:\.\d+)?(?:\s*(?:or newer|\+))?",
    re.IGNORECASE,
)
DART_README = re.compile(r"\b(Dart|Flutter)\s+(?:SDK\s+)?(?:>=?\s*)?(\d+\.\d+)", re.IGNORECASE)
ENV_USAGE = [
    re.compile(r"os\.(?:environ(?:\.get)?|getenv)\s*(?:\[|\()\s*[\"']([A-Z][A-Z0-9_]*)"),
    re.compile(r"(?:process\.env|import\.meta\.env)\.([A-Z][A-Z0-9_]*)"),
    re.compile(r"\$\{([A-Z][A-Z0-9_]*)"),
]
ENV_NAME = re.compile(r"\b([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+|[A-Z][A-Z0-9]{2,})\b")
ENV_ASSIGNMENT = re.compile(r"\b([A-Z][A-Z0-9_]*)\s*=")
# Variables supplied by a platform, a shell, or a toolchain. A project does not document these, so
# treating them as undocumented configuration would be wrong.
MANAGED_ENV_PREFIXES = (
    "ACTIONS_",
    "ANDROID_",
    "BASH_",
    "COMP_",
    "CONDA_",
    "DOTNET_",
    "GITHUB_",
    "GRADLE_",
    "INPUT_",
    "JAVA_",
    "LC_",
    "NPM_CONFIG_",
    "NVM_",
    "PIP_",
    "POETRY_",
    "PWSH_",
    "PYENV_",
    "PYTHON",
    "RUNNER_",
    "SETUPTOOLS_",
    "SSH_",
    "SYSTEM",
    "VIRTUAL_ENV",
    "VSCMD_",
    "XDG_",
)
MANAGED_ENV_NAMES = {
    "ALLUSERSPROFILE",
    "APPDATA",
    "CI",
    "COLORTERM",
    "COLUMNS",
    "COMPUTERNAME",
    "CURL_CA_BUNDLE",
    "DISPLAY",
    "EDITOR",
    "ENSUREPIP_OPTIONS",
    "FORCE_COLOR",
    "HOME",
    "HOMEDRIVE",
    "HOMEPATH",
    "HOSTNAME",
    "LANG",
    "LANGUAGE",
    "LINES",
    "LOCALAPPDATA",
    "LOGNAME",
    "MSYSTEM",
    "NETRC",
    "NO_COLOR",
    "NO_PROXY",
    "PAGER",
    "PATH",
    "PATHEXT",
    "PROCESSOR_ARCHITECTURE",
    "PROGRAMDATA",
    "PROGRAMFILES",
    "PROMPT",
    "PS1",
    "PWD",
    "REQUESTS_CA_BUNDLE",
    "SHELL",
    "SHLVL",
    "SSL_CERT_DIR",
    "SSL_CERT_FILE",
    "TEMP",
    "TERM",
    "TMP",
    "TMPDIR",
    "TZ",
    "USER",
    "USERDOMAIN",
    "USERNAME",
    "USERPROFILE",
    "VISUAL",
    "WINDIR",
}


def _is_project_variable(name: str) -> bool:
    """Whether a name looks like configuration the project itself owns."""
    if name in MANAGED_ENV_NAMES or name.startswith(MANAGED_ENV_PREFIXES):
        return False
    # Proxy settings are environment conventions rather than project configuration.
    return name not in {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "FTP_PROXY"}


def _minor(version: str) -> tuple[int, int]:
    parts = version.strip().lstrip("v").split(".")
    return (int(parts[0]), int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0)


def _python_requirement(root: Path) -> tuple[str, str] | None:
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            requirement = data.get("project", {}).get("requires-python")
            if isinstance(requirement, str):
                match = re.search(r">=?\s*(\d+\.\d+)", requirement)
                if match:
                    return (match.group(1), "pyproject.toml project.requires-python")
        except (OSError, tomllib.TOMLDecodeError):
            pass
    version_file = root / ".python-version"
    if version_file.is_file():
        match = re.search(r"(\d+\.\d+)", version_file.read_text(encoding="utf-8"))
        if match:
            return (match.group(1), ".python-version")
    setup_cfg = root / "setup.cfg"
    if setup_cfg.is_file():
        match = re.search(
            r"python_requires\s*=\s*>=?\s*(\d+\.\d+)", setup_cfg.read_text(encoding="utf-8")
        )
        if match:
            return (match.group(1), "setup.cfg python_requires")
    setup_py = root / "setup.py"
    if setup_py.is_file():
        match = re.search(
            r"python_requires\s*=\s*[\"']>=?\s*(\d+\.\d+)",
            setup_py.read_text(encoding="utf-8"),
        )
        if match:
            return (match.group(1), "setup.py python_requires")
    return None


def _node_requirement(root: Path) -> tuple[str, str] | None:
    package = root / "package.json"
    if package.is_file():
        try:
            engines = json.loads(package.read_text(encoding="utf-8")).get("engines", {})
            node = engines.get("node") if isinstance(engines, dict) else None
            if isinstance(node, str) and (match := re.search(r"(\d+)", node)):
                return (match.group(1), "package.json engines.node")
        except (OSError, json.JSONDecodeError, AttributeError):
            pass
    for name in (".nvmrc", ".node-version"):
        path = root / name
        if path.is_file() and (match := re.search(r"(\d+)", path.read_text(encoding="utf-8"))):
            return (match.group(1), name)
    return None


def _dart_requirements(root: Path) -> dict[str, tuple[str, str]]:
    pubspec = root / "pubspec.yaml"
    found: dict[str, tuple[str, str]] = {}
    if pubspec.is_file():
        try:
            data: Any = yaml.safe_load(pubspec.read_text(encoding="utf-8")) or {}
            environment = data.get("environment", {}) if isinstance(data, dict) else {}
            for key in ("sdk", "flutter"):
                raw = environment.get(key) if isinstance(environment, dict) else None
                if isinstance(raw, str) and (match := re.search(r"(\d+\.\d+)", raw)):
                    found["Dart" if key == "sdk" else "Flutter"] = (
                        match.group(1),
                        f"pubspec.yaml environment.{key}",
                    )
        except (OSError, yaml.YAMLError):
            pass
    fvm = root / ".fvmrc"
    if fvm.is_file():
        try:
            value = json.loads(fvm.read_text(encoding="utf-8")).get("flutter")
            if isinstance(value, str) and (match := re.search(r"(\d+\.\d+)", value)):
                found["Flutter"] = (match.group(1), ".fvmrc")
        except (OSError, json.JSONDecodeError, AttributeError):
            pass
    return found


def _first_lines(text: str, pattern: re.Pattern[str], group: int) -> dict[str, int]:
    """Map each documented version to the first README line that mentions it."""
    first: dict[str, int] = {}
    for match in pattern.finditer(text):
        first.setdefault(match.group(group), text[: match.start()].count("\n") + 1)
    return first


def _dart_first_lines(text: str) -> dict[tuple[str, str], int]:
    first: dict[tuple[str, str], int] = {}
    for match in DART_README.finditer(text):
        first.setdefault(
            (match.group(1).title(), match.group(2)), text[: match.start()].count("\n") + 1
        )
    return first


def check_versions(context: CheckContext) -> list[Finding]:
    findings: list[Finding] = []
    text = context.document.text
    root = context.repository.root

    def add(rule_id: str, explanation: str, line: int, evidence: str) -> None:
        finding = context.finding(rule_id, explanation, line=line, evidence=evidence)
        if finding:
            findings.append(finding)

    # Requirements are read once per language. A README that repeats the same requirement produces
    # one finding at its first mention rather than one per mention.
    python_versions = _first_lines(text, PYTHON_README, 1)
    if python_versions and (project := _python_requirement(root)):
        for documented, line in sorted(python_versions.items(), key=lambda item: item[1]):
            if _minor(documented) < _minor(project[0]):
                add(
                    "RD009",
                    f"README allows Python {documented}, but {project[1]} requires {project[0]}.",
                    line,
                    f"README={documented}; {project[1]}={project[0]}",
                )
    node_versions = _first_lines(text, NODE_README, 1)
    if node_versions and (node_project := _node_requirement(root)):
        for documented, line in sorted(node_versions.items(), key=lambda item: item[1]):
            if int(documented) < int(node_project[0]):
                add(
                    "RD010",
                    f"README allows Node {documented}, but "
                    f"{node_project[1]} requires {node_project[0]}.",
                    line,
                    f"README={documented}; {node_project[1]}={node_project[0]}",
                )
    dart = _dart_requirements(root)
    if dart:
        for (product, documented), line in sorted(
            _dart_first_lines(text).items(), key=lambda item: item[1]
        ):
            dart_project = dart.get(product)
            if dart_project and _minor(documented) < _minor(dart_project[0]):
                add(
                    "RD011",
                    f"README allows {product} {documented}, but "
                    f"{dart_project[1]} requires {dart_project[0]}.",
                    line,
                    f"README={documented}; {dart_project[1]}={dart_project[0]}",
                )
    return findings


def _example_variables(context: CheckContext) -> set[str]:
    variables: set[str] = set()
    for relative in context.config.rules.environment_variables.example_files:
        path = context.repository.root / relative
        if not path.is_file() or path.name == ".env":
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            match = re.match(r"\s*(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=", line)
            if match and _is_project_variable(match.group(1)):
                variables.add(match.group(1))
    return variables


def _used_variables(context: CheckContext) -> set[str]:
    variables: set[str] = set()
    suffixes = {".py", ".js", ".jsx", ".ts", ".tsx", ".yaml", ".yml"}
    for path in context.repository.files(suffixes):
        if path.name.startswith(".env"):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for pattern in ENV_USAGE:
            variables.update(
                variable for variable in pattern.findall(text) if _is_project_variable(variable)
            )
    return variables


def _documented_variables(context: CheckContext) -> set[str]:
    """Return variable names the README actually presents as configuration.

    Three forms count as documentation. A name inside an inline code span or a fenced block, a
    `NAME=` assignment anywhere, and a bare mention of an underscored name such as `DATABASE_URL`
    in the prose. A bare uppercase word without an underscore does not count, because acronyms
    like JSON or MIT would otherwise be treated as documented variables.
    """
    documented: set[str] = set()
    for content, _ in context.document.inline_code:
        documented.update(ENV_NAME.findall(content))
    for block in context.document.code_blocks:
        documented.update(ENV_ASSIGNMENT.findall(block.content))
        if block.language.casefold() in {"", "env", "dotenv", "ini", "properties"}:
            documented.update(ENV_NAME.findall(block.content))
    text = context.document.text
    documented.update(ENV_ASSIGNMENT.findall(text))
    documented.update(name for name in ENV_NAME.findall(text) if "_" in name)
    return documented


def check_environment(context: CheckContext) -> list[Finding]:
    if not context.config.rules.environment_variables.enabled:
        return []
    findings: list[Finding] = []
    documented = _documented_variables(context)
    examples = _example_variables(context)
    used = _used_variables(context)

    def add(explanation: str, evidence: str, suggestion: str) -> None:
        finding = context.finding(
            "RD012",
            explanation,
            evidence=evidence,
            suggestion=suggestion,
            confidence=Confidence.MEDIUM,
        )
        if finding:
            findings.append(finding)

    # Each variable produces at most one finding so that a single gap is not reported through
    # several overlapping conditions.
    for variable in sorted(used - examples):
        if variable in documented:
            add(
                f"{variable} is documented in the README and used by the repository, "
                "but is missing from the environment example.",
                f"variable={variable}; source=README and code",
                f"Add `{variable}=` to an example environment file.",
            )
        else:
            add(
                f"{variable} is used by the repository but is missing from environment examples "
                "and the README.",
                f"variable={variable}; source=code",
                f"Add `{variable}=` to an example environment file and document it.",
            )
    for variable in sorted(examples - documented):
        add(
            f"{variable} appears in an environment example but is not mentioned in the README.",
            f"variable={variable}; source=environment example",
            f"Explain `{variable}` in setup documentation.",
        )
    return findings


def _compose_published_ports(text: str) -> set[int]:
    """Return the host side of each Docker Compose port mapping.

    A mapping such as `"3000:8000"` publishes container port 8000 on host port 3000. A README
    that tells a reader to open a browser is describing the host port, so only that side is
    comparable. The optional leading address in `127.0.0.1:3000:8000` is skipped.
    """
    published: set[int] = set()
    for match in re.finditer(
        r"""^\s*-\s*["']?(?:\d{1,3}(?:\.\d{1,3}){3}:)?(\d{2,5}):(\d{2,5})""",
        text,
        re.MULTILINE,
    ):
        published.add(int(match.group(1)))
    return published


def check_ports(context: CheckContext) -> list[Finding]:
    readme_ports = {
        int(port)
        for port in re.findall(
            r"(?:localhost|127\.0\.0\.1|--port(?:=|\s+)|PORT\s*=\s*)(?::)?(\d{2,5})",
            context.document.text,
            re.IGNORECASE,
        )
    }
    strong: set[int] = set()
    compose = next(
        (
            context.repository.root / name
            for name in ("compose.yaml", "compose.yml", "docker-compose.yml", "docker-compose.yaml")
            if (context.repository.root / name).is_file()
        ),
        None,
    )
    if compose:
        text = compose.read_text(encoding="utf-8", errors="replace")
        strong.update(_compose_published_ports(text))
    vite = next(
        (
            context.repository.root / name
            for name in ("vite.config.ts", "vite.config.js")
            if (context.repository.root / name).is_file()
        ),
        None,
    )
    if vite:
        strong.update(
            int(port)
            for port in re.findall(
                r"\bport\s*:\s*(\d{2,5})", vite.read_text(encoding="utf-8", errors="replace")
            )
        )
    if len(readme_ports) == 1 and len(strong) == 1 and readme_ports != strong:
        readme_port = next(iter(readme_ports))
        project_port = next(iter(strong))
        finding = context.finding(
            "RD013",
            f"README uses port {readme_port}, but repository configuration uses {project_port}.",
            evidence=f"README={readme_port}; configuration={project_port}",
            confidence=Confidence.HIGH,
        )
        return [finding] if finding else []
    return []
