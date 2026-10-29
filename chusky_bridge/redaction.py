import re
from typing import Any

SECRET_KEY_PATTERN = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|credential|connection[_-]?string|authorization|dsn)",
    re.IGNORECASE,
)
_BEARER = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9\-._~+/]+=*")
_PWD = re.compile(r"(?i)((?:pwd|password)\s*=\s*)[^;\s]+")
MAX_STRING_CHARS = 2000


def truncate_text(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "...[truncated]"


def redact_text(text: str) -> str:
    text = _BEARER.sub(r"\1[REDACTED]", text)
    return _PWD.sub(r"\1[REDACTED]", text)


def redact(value: Any) -> Any:
    """Recursively redact secret-like keys and credential-like strings."""
    if isinstance(value, dict):
        return {
            key: ("[REDACTED]" if SECRET_KEY_PATTERN.search(str(key)) else redact(item)) for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return redact_text(truncate_text(value, MAX_STRING_CHARS))
    return value
