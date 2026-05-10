"""
RBAC — Role-Based Access Control for enterprise deployments.

Defines users, roles, permissions, and provides a manager for
user CRUD and permission checking with SQLite persistence.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class Role(str, Enum):
    ADMIN = "admin"
    DEVELOPER = "developer"
    VIEWER = "viewer"


class ResourceType(str, Enum):
    AGENT = "agent"
    SKILL = "skill"
    TOOL = "tool"
    TASK = "task"
    AUDIT = "audit"
    CONFIG = "config"
    USER = "user"


class Action(str, Enum):
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    EXECUTE = "execute"
    INSTALL = "install"


@dataclass
class Permission:
    """A single permission grant."""
    resource: ResourceType
    actions: set[Action]
    resource_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource": self.resource.value,
            "actions": [a.value for a in self.actions],
            "resource_id": self.resource_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Permission:
        return cls(
            resource=ResourceType(data["resource"]),
            actions={Action(a) for a in data.get("actions", [])},
            resource_id=data.get("resource_id"),
        )


@dataclass
class User:
    """Enterprise user model."""
    id: str
    username: str
    display_name: str
    email: str
    role: Role
    permissions: list[Permission] = field(default_factory=list)
    groups: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_login: float | None = None
    active: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "username": self.username,
            "display_name": self.display_name,
            "email": self.email,
            "role": self.role.value,
            "permissions": [p.to_dict() for p in self.permissions],
            "groups": self.groups,
            "created_at": self.created_at,
            "last_login": self.last_login,
            "active": self.active,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> User:
        permissions = [Permission.from_dict(p) for p in data.get("permissions", [])]
        return cls(
            id=data.get("id", ""),
            username=data.get("username", ""),
            display_name=data.get("display_name", ""),
            email=data.get("email", ""),
            role=Role(data.get("role", "viewer")),
            permissions=permissions,
            groups=data.get("groups", []),
            created_at=data.get("created_at", 0.0),
            last_login=data.get("last_login"),
            active=data.get("active", True),
        )


# Default permissions per role
ROLE_DEFAULTS: dict[Role, list[Permission]] = {
    Role.ADMIN: [
        Permission(ResourceType.AGENT, {Action.CREATE, Action.READ, Action.UPDATE, Action.DELETE, Action.EXECUTE, Action.INSTALL}),
        Permission(ResourceType.SKILL, {Action.CREATE, Action.READ, Action.UPDATE, Action.DELETE, Action.INSTALL}),
        Permission(ResourceType.TOOL, {Action.READ, Action.UPDATE}),
        Permission(ResourceType.TASK, {Action.CREATE, Action.READ, Action.DELETE, Action.EXECUTE}),
        Permission(ResourceType.AUDIT, {Action.READ}),
        Permission(ResourceType.CONFIG, {Action.READ, Action.UPDATE}),
        Permission(ResourceType.USER, {Action.CREATE, Action.READ, Action.UPDATE, Action.DELETE}),
    ],
    Role.DEVELOPER: [
        Permission(ResourceType.AGENT, {Action.READ, Action.EXECUTE}),
        Permission(ResourceType.SKILL, {Action.READ, Action.INSTALL}),
        Permission(ResourceType.TOOL, {Action.READ}),
        Permission(ResourceType.TASK, {Action.CREATE, Action.READ, Action.EXECUTE}),
        Permission(ResourceType.AUDIT, {Action.READ}),
        Permission(ResourceType.CONFIG, {Action.READ}),
    ],
    Role.VIEWER: [
        Permission(ResourceType.AGENT, {Action.READ}),
        Permission(ResourceType.SKILL, {Action.READ}),
        Permission(ResourceType.TASK, {Action.READ}),
        Permission(ResourceType.AUDIT, {Action.READ}),
    ],
}


class RBACManager:
    """Manages users, roles, and permission checks with SQLite persistence."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or (Path.home() / ".omniagent" / "enterprise.db")
        self._users: dict[str, User] = {}
        self._init_db()
        self._load_users()

    # ── User CRUD ───────────────────────────────────────────────────────

    def create_user(
        self,
        username: str,
        display_name: str,
        email: str,
        role: Role,
    ) -> User:
        """Create a new user."""
        if self.get_user_by_username(username):
            raise ValueError(f"User '{username}' already exists")
        user = User(
            id=str(uuid.uuid4()),
            username=username,
            display_name=display_name,
            email=email,
            role=role,
        )
        self._users[user.id] = user
        self._save_user(user)
        return user

    def get_user(self, user_id: str) -> User | None:
        return self._users.get(user_id)

    def get_user_by_username(self, username: str) -> User | None:
        for user in self._users.values():
            if user.username == username:
                return user
        return None

    def list_users(self) -> list[User]:
        return list(self._users.values())

    def update_user(self, user_id: str, **kwargs: Any) -> bool:
        """Update user fields (display_name, email, role)."""
        user = self._users.get(user_id)
        if not user:
            return False
        for key in ("display_name", "email", "role"):
            if key in kwargs:
                val = kwargs[key]
                if key == "role" and isinstance(val, str):
                    val = Role(val)
                setattr(user, key, val)
        self._save_user(user)
        return True

    def deactivate_user(self, user_id: str) -> bool:
        user = self._users.get(user_id)
        if not user:
            return False
        user.active = False
        self._save_user(user)
        return True

    def record_login(self, user_id: str) -> None:
        user = self._users.get(user_id)
        if user:
            user.last_login = time.time()
            self._save_user(user)

    # ── Permission Checks ───────────────────────────────────────────────

    def check_permission(
        self,
        user: User,
        resource: ResourceType,
        action: Action,
        resource_id: str | None = None,
    ) -> bool:
        """Check if user has permission for the given action on the resource."""
        if not user.active:
            return False

        # Admin always has access
        if user.role == Role.ADMIN:
            return True

        # Check explicit user permissions first
        for perm in user.permissions:
            if perm.resource == resource:
                if action in perm.actions:
                    if perm.resource_id is None or perm.resource_id == resource_id:
                        return True

        # Check role defaults
        for perm in ROLE_DEFAULTS.get(user.role, []):
            if perm.resource == resource and action in perm.actions:
                return True

        return False

    def get_effective_permissions(self, user: User) -> list[dict[str, Any]]:
        """Get all effective permissions for a user (role defaults + overrides)."""
        seen: set[tuple[str, str]] = set()
        result = []

        # Role defaults
        for perm in ROLE_DEFAULTS.get(user.role, []):
            key = (perm.resource.value, ",".join(sorted(a.value for a in perm.actions)))
            if key not in seen:
                seen.add(key)
                result.append(perm.to_dict())

        # User overrides
        for perm in user.permissions:
            key = (perm.resource.value, ",".join(sorted(a.value for a in perm.actions)))
            if key not in seen:
                seen.add(key)
                result.append(perm.to_dict())

        return result

    # ── SQLite Persistence ──────────────────────────────────────────────

    def _init_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path))
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    display_name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    role TEXT NOT NULL,
                    permissions TEXT DEFAULT '[]',
                    groups TEXT DEFAULT '[]',
                    created_at REAL NOT NULL,
                    last_login REAL,
                    active BOOLEAN DEFAULT 1
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
            conn.commit()
        finally:
            conn.close()

    def _load_users(self) -> None:
        conn = sqlite3.connect(str(self._db_path))
        try:
            rows = conn.execute("SELECT * FROM users").fetchall()
            for row in rows:
                user = User(
                    id=row[0],
                    username=row[1],
                    display_name=row[2],
                    email=row[3],
                    role=Role(row[4]),
                    permissions=[Permission.from_dict(p) for p in json.loads(row[5])],
                    groups=json.loads(row[6]),
                    created_at=row[7],
                    last_login=row[8],
                    active=bool(row[9]),
                )
                self._users[user.id] = user
        finally:
            conn.close()

    def _save_user(self, user: User) -> None:
        conn = sqlite3.connect(str(self._db_path))
        try:
            conn.execute(
                """INSERT OR REPLACE INTO users
                   (id, username, display_name, email, role, permissions, groups, created_at, last_login, active)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    user.id,
                    user.username,
                    user.display_name,
                    user.email,
                    user.role.value,
                    json.dumps([p.to_dict() for p in user.permissions]),
                    json.dumps(user.groups),
                    user.created_at,
                    user.last_login,
                    int(user.active),
                ),
            )
            conn.commit()
        finally:
            conn.close()
