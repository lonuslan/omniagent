"""Tests for RBAC permission system."""

import pytest

from omniagent.enterprise.rbac import (
    Action,
    Permission,
    RBACManager,
    ResourceType,
    Role,
    User,
    ROLE_DEFAULTS,
)


@pytest.fixture
def rbac(tmp_path):
    return RBACManager(db_path=tmp_path / "test.db")


class TestUser:
    def test_round_trip(self):
        u = User(
            id="u1", username="alice", display_name="Alice",
            email="alice@test.com", role=Role.DEVELOPER,
        )
        d = u.to_dict()
        restored = User.from_dict(d)
        assert restored.id == "u1"
        assert restored.username == "alice"
        assert restored.role == Role.DEVELOPER

    def test_default_permissions_empty(self):
        u = User(id="u1", username="bob", display_name="Bob", email="", role=Role.VIEWER)
        assert u.permissions == []
        assert u.active is True


class TestRoleDefaults:
    def test_admin_has_all_resource_types(self):
        admin_perms = ROLE_DEFAULTS[Role.ADMIN]
        resources = {p.resource for p in admin_perms}
        assert ResourceType.USER in resources
        assert ResourceType.CONFIG in resources

    def test_viewer_read_only(self):
        for perm in ROLE_DEFAULTS[Role.VIEWER]:
            for action in perm.actions:
                assert action == Action.READ

    def test_developer_can_execute(self):
        dev_perms = ROLE_DEFAULTS[Role.DEVELOPER]
        agent_perm = next(p for p in dev_perms if p.resource == ResourceType.AGENT)
        assert Action.EXECUTE in agent_perm.actions


class TestRBACManager:
    def test_create_user(self, rbac):
        user = rbac.create_user("alice", "Alice", "a@test.com", Role.DEVELOPER)
        assert user.username == "alice"
        assert user.role == Role.DEVELOPER

    def test_create_duplicate_username(self, rbac):
        rbac.create_user("alice", "Alice", "a@test.com", Role.DEVELOPER)
        with pytest.raises(ValueError, match="already exists"):
            rbac.create_user("alice", "Alice 2", "a2@test.com", Role.VIEWER)

    def test_get_user(self, rbac):
        user = rbac.create_user("bob", "Bob", "b@test.com", Role.VIEWER)
        assert rbac.get_user(user.id) is user
        assert rbac.get_user("nonexistent") is None

    def test_get_by_username(self, rbac):
        user = rbac.create_user("carol", "Carol", "c@test.com", Role.ADMIN)
        assert rbac.get_user_by_username("carol") is user
        assert rbac.get_user_by_username("nobody") is None

    def test_list_users(self, rbac):
        rbac.create_user("a", "A", "", Role.DEVELOPER)
        rbac.create_user("b", "B", "", Role.VIEWER)
        assert len(rbac.list_users()) == 2

    def test_update_user(self, rbac):
        user = rbac.create_user("dave", "Dave", "d@test.com", Role.VIEWER)
        assert rbac.update_user(user.id, display_name="David", role="developer")
        updated = rbac.get_user(user.id)
        assert updated.display_name == "David"
        assert updated.role == Role.DEVELOPER

    def test_update_nonexistent(self, rbac):
        assert rbac.update_user("nope", display_name="X") is False

    def test_deactivate_user(self, rbac):
        user = rbac.create_user("eve", "Eve", "e@test.com", Role.DEVELOPER)
        assert rbac.deactivate_user(user.id)
        assert rbac.get_user(user.id).active is False

    def test_deactivate_nonexistent(self, rbac):
        assert rbac.deactivate_user("nope") is False

    def test_record_login(self, rbac):
        user = rbac.create_user("frank", "Frank", "f@test.com", Role.DEVELOPER)
        assert user.last_login is None
        rbac.record_login(user.id)
        assert rbac.get_user(user.id).last_login is not None


class TestPermissionChecks:
    def test_admin_always_allowed(self, rbac):
        user = rbac.create_user("admin", "Admin", "", Role.ADMIN)
        assert rbac.check_permission(user, ResourceType.AGENT, Action.DELETE)
        assert rbac.check_permission(user, ResourceType.USER, Action.CREATE)
        assert rbac.check_permission(user, ResourceType.CONFIG, Action.UPDATE)

    def test_developer_can_read_agent(self, rbac):
        user = rbac.create_user("dev", "Dev", "", Role.DEVELOPER)
        assert rbac.check_permission(user, ResourceType.AGENT, Action.READ)

    def test_developer_cannot_delete_agent(self, rbac):
        user = rbac.create_user("dev", "Dev", "", Role.DEVELOPER)
        assert not rbac.check_permission(user, ResourceType.AGENT, Action.DELETE)

    def test_viewer_cannot_execute(self, rbac):
        user = rbac.create_user("viewer", "Viewer", "", Role.VIEWER)
        assert not rbac.check_permission(user, ResourceType.AGENT, Action.EXECUTE)
        assert not rbac.check_permission(user, ResourceType.TASK, Action.EXECUTE)

    def test_viewer_can_read(self, rbac):
        user = rbac.create_user("viewer", "Viewer", "", Role.VIEWER)
        assert rbac.check_permission(user, ResourceType.AGENT, Action.READ)
        assert rbac.check_permission(user, ResourceType.AUDIT, Action.READ)

    def test_inactive_user_denied(self, rbac):
        user = rbac.create_user("gone", "Gone", "", Role.ADMIN)
        rbac.deactivate_user(user.id)
        assert not rbac.check_permission(user, ResourceType.AGENT, Action.READ)

    def test_explicit_permission_override(self, rbac):
        user = rbac.create_user("custom", "Custom", "", Role.VIEWER)
        user.permissions = [Permission(ResourceType.AGENT, {Action.DELETE})]
        rbac._save_user(user)
        assert rbac.check_permission(user, ResourceType.AGENT, Action.DELETE)

    def test_get_effective_permissions(self, rbac):
        user = rbac.create_user("dev", "Dev", "", Role.DEVELOPER)
        perms = rbac.get_effective_permissions(user)
        assert len(perms) > 0
        resources = {p["resource"] for p in perms}
        assert "agent" in resources


class TestPersistence:
    def test_users_survive_restart(self, tmp_path):
        db_path = tmp_path / "test.db"
        m1 = RBACManager(db_path=db_path)
        m1.create_user("alice", "Alice", "a@test.com", Role.DEVELOPER)
        m1.create_user("bob", "Bob", "b@test.com", Role.ADMIN)

        m2 = RBACManager(db_path=db_path)
        assert len(m2.list_users()) == 2
        assert m2.get_user_by_username("alice").role == Role.DEVELOPER
        assert m2.get_user_by_username("bob").role == Role.ADMIN

    def test_user_update_persists(self, tmp_path):
        db_path = tmp_path / "test.db"
        m1 = RBACManager(db_path=db_path)
        user = m1.create_user("carol", "Carol", "c@test.com", Role.VIEWER)
        m1.update_user(user.id, role="admin")

        m2 = RBACManager(db_path=db_path)
        assert m2.get_user_by_username("carol").role == Role.ADMIN
