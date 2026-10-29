import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from chusky_bridge.approvals import ApprovalError, ApprovalStatus, assert_can_decide, is_expired, transition
from chusky_bridge.auth import Identity

PENDING = ApprovalStatus.PENDING
APPROVED = ApprovalStatus.APPROVED
EXECUTED = ApprovalStatus.EXECUTED
REJECTED = ApprovalStatus.REJECTED


def _identity(user_id: str) -> Identity:
    return Identity(tenant_id=uuid.uuid4(), user_id=user_id, agent_id="agent-1")


def test_pending_can_be_approved_or_rejected():
    assert transition(PENDING, APPROVED) is APPROVED
    assert transition(PENDING, REJECTED) is REJECTED


def test_execution_requires_prior_approval():
    with pytest.raises(ApprovalError):
        transition(PENDING, EXECUTED)


def test_executed_is_terminal():
    with pytest.raises(ApprovalError):
        transition(EXECUTED, APPROVED)


def test_rejected_cannot_later_be_approved():
    with pytest.raises(ApprovalError):
        transition(REJECTED, APPROVED)


def test_requester_cannot_approve_own_action():
    with pytest.raises(ApprovalError, match="own actions"):
        assert_can_decide("alice", _identity("alice"))


def test_other_user_may_decide():
    assert assert_can_decide("alice", _identity("bob")) is None


def test_expired_request_detected():
    assert is_expired(SimpleNamespace(expires_at=datetime.now(UTC) - timedelta(seconds=1)))


def test_fresh_request_not_expired():
    assert not is_expired(SimpleNamespace(expires_at=datetime.now(UTC) + timedelta(minutes=5)))
