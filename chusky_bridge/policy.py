from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str
    requires_approval: bool = False


FORBIDDEN_ARGUMENT_KEYS = frozenset(
    {"sql", "query", "command", "shell", "path", "file_path", "url", "script", "eval", "exec"}
)
MAX_STRING_ARGUMENT_CHARS = 10_000


def _keys(value: Any):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield str(key).lower()
            yield from _keys(nested)
    elif isinstance(value, list):
        for item in value:
            yield from _keys(item)


def _longest_string(value: Any) -> int:
    if isinstance(value, str):
        return len(value)
    if isinstance(value, dict):
        return max((_longest_string(v) for v in value.values()), default=0)
    if isinstance(value, list):
        return max((_longest_string(v) for v in value), default=0)
    return 0


def evaluate_tool_policy(
    *,
    user_scopes: frozenset[str] | set[str] | list[str],
    tool_scopes: list[str],
    tool_read_only: bool,
    tool_risk_level: str,
    tool_requires_approval: bool,
    write_tools_enabled: bool,
    arguments: dict,
) -> PolicyDecision:
    """Deny by default. Every check is evaluated server-side on every call."""
    if not tool_read_only and not write_tools_enabled:
        return PolicyDecision(False, "write tools are disabled by platform policy")

    if not tool_read_only and not tool_requires_approval:
        return PolicyDecision(False, "write tools must require approval")

    if tool_risk_level == "high" and not tool_requires_approval:
        return PolicyDecision(False, "high-risk tools must require approval")

    missing = set(tool_scopes) - set(user_scopes)
    if missing:
        return PolicyDecision(False, f"missing scopes: {sorted(missing)}")

    if any(key in FORBIDDEN_ARGUMENT_KEYS for key in _keys(arguments)):
        return PolicyDecision(False, "arguments contain a forbidden execution or filesystem key")

    if _longest_string(arguments) > MAX_STRING_ARGUMENT_CHARS:
        return PolicyDecision(False, "an argument exceeds the maximum length")

    return PolicyDecision(True, "allowed", requires_approval=tool_requires_approval)
