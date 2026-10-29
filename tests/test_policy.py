from chusky_bridge.policy import evaluate_tool_policy


def _evaluate(**overrides):
    kwargs = dict(
        user_scopes=["erp.purchase_orders.read"],
        tool_scopes=["erp.purchase_orders.read"],
        tool_read_only=True,
        tool_risk_level="low",
        tool_requires_approval=False,
        write_tools_enabled=False,
        arguments={"search_text": "acme", "limit": 10},
    )
    kwargs.update(overrides)
    return evaluate_tool_policy(**kwargs)


def test_read_tool_allowed_with_scope():
    decision = _evaluate()
    assert decision.allowed and not decision.requires_approval


def test_missing_scope_denied():
    decision = _evaluate(user_scopes=[])
    assert not decision.allowed and "missing scopes" in decision.reason


def test_write_tool_denied_while_platform_disables_writes():
    assert not _evaluate(tool_read_only=False, tool_risk_level="medium", tool_requires_approval=True).allowed


def test_write_tool_allowed_when_enabled_and_approval_required():
    decision = _evaluate(
        tool_read_only=False, tool_risk_level="medium", tool_requires_approval=True, write_tools_enabled=True
    )
    assert decision.allowed and decision.requires_approval


def test_write_without_approval_denied_even_when_enabled():
    assert not _evaluate(tool_read_only=False, tool_requires_approval=False, write_tools_enabled=True).allowed


def test_high_risk_without_approval_denied():
    assert not _evaluate(tool_risk_level="high", tool_requires_approval=False).allowed


def test_forbidden_key_denied_at_any_depth():
    decision = _evaluate(arguments={"filters": {"nested": {"SQL": "select 1"}}})
    assert not decision.allowed and "forbidden" in decision.reason


def test_oversized_argument_denied():
    assert not _evaluate(arguments={"search_text": "x" * 20_000}).allowed
