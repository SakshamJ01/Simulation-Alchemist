"""Tests for Multi-Tenant Auth and RBAC (Phase 4J)."""

from __future__ import annotations

import pytest

from workbench.auth import AuthManager, Permission, Role


def test_user_registration_and_authentication() -> None:
    auth = AuthManager()
    user = auth.register_user("researcher_alice", "secure_pass_123", role=Role.RESEARCHER)
    assert user.username == "researcher_alice"
    assert user.role == Role.RESEARCHER

    # Duplicate registration fails
    with pytest.raises(ValueError):
        auth.register_user("researcher_alice", "pass2")

    # Valid login
    token = auth.authenticate("researcher_alice", "secure_pass_123")
    assert isinstance(token, str)

    # Invalid login
    with pytest.raises(PermissionError):
        auth.authenticate("researcher_alice", "wrong_pass")


def test_token_verification_and_rbac_permissions() -> None:
    auth = AuthManager()
    auth.register_user("viewer_bob", "pass_bob", role=Role.VIEWER)
    auth.register_user("admin_carol", "pass_carol", role=Role.ADMIN)

    token_bob = auth.authenticate("viewer_bob", "pass_bob")
    token_carol = auth.authenticate("admin_carol", "pass_carol")

    # Bob (Viewer) permissions
    assert auth.check_permission(token_bob, Permission.VIEW_RESULTS)
    assert not auth.check_permission(token_bob, Permission.RUN_SIMULATION)
    assert not auth.check_permission(token_bob, Permission.MANAGE_USERS)

    # Carol (Admin) permissions
    assert auth.check_permission(token_carol, Permission.VIEW_RESULTS)
    assert auth.check_permission(token_carol, Permission.RUN_SIMULATION)
    assert auth.check_permission(token_carol, Permission.MANAGE_USERS)
    assert auth.check_permission(token_carol, Permission.ADMIN_CONFIG)
