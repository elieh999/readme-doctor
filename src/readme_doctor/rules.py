from __future__ import annotations

from dataclasses import dataclass

from readme_doctor.models import Severity


@dataclass(frozen=True)
class Rule:
    identifier: str
    name: str
    default_severity: Severity
    help: str


RULES = {
    rule.identifier: rule
    for rule in [
        Rule("RD001", "Missing README", Severity.ERROR, "Add a recognized README file."),
        Rule("RD002", "Missing local reference", Severity.ERROR, "Correct or remove the link."),
        Rule("RD003", "Broken internal anchor", Severity.WARNING, "Link to an existing heading."),
        Rule("RD004", "Missing image alternative text", Severity.WARNING, "Describe the image."),
        Rule("RD005", "Empty code block", Severity.NOTICE, "Add an example or remove the block."),
        Rule("RD006", "Unknown code language", Severity.WARNING, "Correct the fence language."),
        Rule("RD007", "Missing referenced command", Severity.ERROR, "Add or correct the script."),
        Rule("RD008", "Missing package script", Severity.ERROR, "Define or correct the script."),
        Rule(
            "RD009", "Python version mismatch", Severity.WARNING, "Align documented requirements."
        ),
        Rule("RD010", "Node version mismatch", Severity.WARNING, "Align documented requirements."),
        Rule("RD011", "Dart or Flutter version mismatch", Severity.WARNING, "Align requirements."),
        Rule(
            "RD012",
            "Environment variable documentation",
            Severity.WARNING,
            "Document the variable.",
        ),
        Rule("RD013", "Port mismatch", Severity.WARNING, "Use one supported port consistently."),
        Rule("RD014", "Missing setup section", Severity.NOTICE, "Add the configured section."),
        Rule("RD015", "Placeholder content", Severity.WARNING, "Replace unfinished content."),
        Rule("RD016", "Invalid badge", Severity.WARNING, "Correct the badge image or target."),
        Rule("RD017", "Broken remote link", Severity.WARNING, "Update or remove the remote link."),
        Rule("RD018", "Command execution failed", Severity.ERROR, "Correct the verified command."),
        Rule("RD019", "Invalid suppression", Severity.WARNING, "Use a registered rule identifier."),
        Rule(
            "RD020",
            "Execution skipped",
            Severity.NOTICE,
            "Install Docker or change execution settings.",
        ),
        Rule(
            "RD021",
            "README format not analyzed",
            Severity.NOTICE,
            "Provide a Markdown README to enable the full rule set.",
        ),
    ]
}
