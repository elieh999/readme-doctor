from __future__ import annotations

import re

# Values are matched conservatively. The value character class deliberately excludes quotes and
# braces so that redacting a field inside serialized JSON cannot consume the closing quote and
# produce an unparseable document.
_VALUE = r"""[^\s,;"'}\]]+"""

AUTHORIZATION = re.compile(rf"(?i)(authorization\s*:\s*(?:bearer|basic)\s+){_VALUE}")
KEYED_SECRET = re.compile(
    rf"(?i)\b(api[_-]?key|access[_-]?token|token|password|passwd|secret)(\s*[=:]\s*){_VALUE}"
)
GITHUB_TOKEN = re.compile(r"\bgh[opusr]_[A-Za-z0-9_]{20,}\b")
AWS_ACCESS_KEY = re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")
CREDENTIALED_URL = re.compile(
    r"(?i)\b([a-z][a-z0-9+.-]*)://[^\s/@\"']+:[^\s/@\"']+@",
)
PRIVATE_KEY = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"
)

PLACEHOLDER = "[REDACTED]"


def redact(text: str) -> str:
    """Remove values that look like credentials from text destined for a report.

    This is a best effort filter for common formats. It cannot recognize every secret shape, so
    it reduces accidental exposure rather than guaranteeing that none occurs.
    """
    result = AUTHORIZATION.sub(rf"\1{PLACEHOLDER}", text)
    result = KEYED_SECRET.sub(rf"\1\2{PLACEHOLDER}", result)
    result = GITHUB_TOKEN.sub(PLACEHOLDER, result)
    result = AWS_ACCESS_KEY.sub(PLACEHOLDER, result)
    result = CREDENTIALED_URL.sub(rf"\1://{PLACEHOLDER}@", result)
    return PRIVATE_KEY.sub("[REDACTED PRIVATE KEY]", result)
