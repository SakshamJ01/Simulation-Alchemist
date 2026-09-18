"""Multi-Tenant Authentication & Role-Based Access Control (RBAC) (Phase 4J).

Provides user credential hashing with cryptographic salt, JWT-style session tokens,
and fine-grained role-based permission verification for enterprise workbench access.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field
from enum import Enum


class Role(str, Enum):
    VIEWER = "viewer"
    RESEARCHER = "researcher"
    ADMIN = "admin"


class Permission(str, Enum):
    VIEW_RESULTS = "view_results"
    RUN_SIMULATION = "run_simulation"
    RUN_SWEEP = "run_sweep"
    RUN_DISCOVERY = "run_discovery"
    MANAGE_USERS = "manage_users"
    ADMIN_CONFIG = "admin_config"


ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.VIEWER: {Permission.VIEW_RESULTS},
    Role.RESEARCHER: {
        Permission.VIEW_RESULTS,
        Permission.RUN_SIMULATION,
        Permission.RUN_SWEEP,
        Permission.RUN_DISCOVERY,
    },
    Role.ADMIN: {
        Permission.VIEW_RESULTS,
        Permission.RUN_SIMULATION,
        Permission.RUN_SWEEP,
        Permission.RUN_DISCOVERY,
        Permission.MANAGE_USERS,
        Permission.ADMIN_CONFIG,
    },
}


@dataclass(frozen=True)
class User:
    username: str
    password_hash: str
    salt: str
    role: Role
    is_active: bool = True
    created_at: float = field(default_factory=time.time)


class AuthManager:
    """Enterprise authentication manager with RBAC and token validation."""

    def __init__(self, secret_key: str | None = None) -> None:
        self.secret_key = secret_key or secrets.token_hex(32)
        self._users: dict[str, User] = {}
        self._tokens: dict[str, tuple[str, float]] = {}  # token -> (username, expiry)

    @staticmethod
    def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
        s = salt or secrets.token_hex(16)
        pw_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), s.encode("utf-8"), 100000).hex()
        return pw_hash, s

    def register_user(self, username: str, password: str, role: Role = Role.RESEARCHER) -> User:
        if username in self._users:
            raise ValueError(f"User '{username}' already exists.")
        pw_hash, salt = self.hash_password(password)
        user = User(username=username, password_hash=pw_hash, salt=salt, role=role)
        self._users[username] = user
        return user

    def authenticate(self, username: str, password: str, ttl_seconds: float = 3600.0) -> str:
        """Authenticate user and return session token."""
        user = self._users.get(username)
        if not user or not user.is_active:
            raise PermissionError("Invalid username or inactive account.")

        expected_hash, _ = self.hash_password(password, user.salt)
        if not hmac.compare_digest(user.password_hash, expected_hash):
            raise PermissionError("Invalid password.")

        token = secrets.token_urlsafe(32)
        self._tokens[token] = (username, time.time() + ttl_seconds)
        return token

    def verify_token(self, token: str) -> User:
        """Verify token and return current User."""
        if token not in self._tokens:
            raise PermissionError("Invalid or missing session token.")

        username, expiry = self._tokens[token]
        if time.time() > expiry:
            del self._tokens[token]
            raise PermissionError("Session token expired.")

        user = self._users.get(username)
        if not user or not user.is_active:
            raise PermissionError("User is no longer active.")
        return user

    def check_permission(self, token: str, required_permission: Permission) -> bool:
        """Check if session token has the required permission."""
        try:
            user = self.verify_token(token)
            allowed = ROLE_PERMISSIONS.get(user.role, set())
            return required_permission in allowed
        except PermissionError:
            return False
