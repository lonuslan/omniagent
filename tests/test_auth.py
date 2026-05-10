"""Tests for auth providers and AuthManager."""

import pytest

from omniagent.enterprise.auth import (
    AuthConfig,
    AuthManager,
    LDAPAuthProvider,
    MockAuthProvider,
    OIDCAuthProvider,
)
from omniagent.enterprise.rbac import RBACManager, Role


@pytest.fixture
def rbac(tmp_path):
    return RBACManager(db_path=tmp_path / "rbac.db")


@pytest.fixture
def auth_manager(rbac):
    return AuthManager(rbac)


class TestMockAuthProvider:
    def test_authenticate_success(self):
        provider = MockAuthProvider()
        user = provider.authenticate("admin", "pass123")
        assert user is not None
        assert user.username == "admin"
        assert user.role == Role.ADMIN
        assert user.display_name == "Admin User"

    def test_authenticate_developer(self):
        provider = MockAuthProvider()
        user = provider.authenticate("developer", "pass")
        assert user is not None
        assert user.role == Role.DEVELOPER

    def test_authenticate_viewer(self):
        provider = MockAuthProvider()
        user = provider.authenticate("viewer", "pass")
        assert user is not None
        assert user.role == Role.VIEWER

    def test_authenticate_unknown_user(self):
        provider = MockAuthProvider()
        assert provider.authenticate("nonexistent", "pass") is None

    def test_authenticate_empty_password(self):
        provider = MockAuthProvider()
        assert provider.authenticate("admin", "") is None

    def test_get_user_info_found(self):
        provider = MockAuthProvider()
        info = provider.get_user_info("admin")
        assert info is not None
        assert info["email"] == "admin@company.com"
        assert info["role"] == "admin"

    def test_get_user_info_not_found(self):
        provider = MockAuthProvider()
        assert provider.get_user_info("nonexistent") is None


class TestLDAPAuthProvider:
    def test_authenticate_raises(self):
        config = AuthConfig(provider_type="ldap", server_url="ldap://example.com")
        provider = LDAPAuthProvider(config)
        with pytest.raises(NotImplementedError, match="ldap3"):
            provider.authenticate("user", "pass")

    def test_get_user_info_raises(self):
        config = AuthConfig(provider_type="ldap", server_url="ldap://example.com")
        provider = LDAPAuthProvider(config)
        with pytest.raises(NotImplementedError, match="ldap3"):
            provider.get_user_info("user")


class TestOIDCAuthProvider:
    def test_authenticate_raises(self):
        config = AuthConfig(provider_type="oidc", issuer_url="https://idp.example.com")
        provider = OIDCAuthProvider(config)
        with pytest.raises(NotImplementedError, match="authlib"):
            provider.authenticate("user", "pass")

    def test_get_user_info_raises(self):
        config = AuthConfig(provider_type="oidc", issuer_url="https://idp.example.com")
        provider = OIDCAuthProvider(config)
        with pytest.raises(NotImplementedError, match="authlib"):
            provider.get_user_info("user")


class TestAuthManager:
    def test_configure_mock(self, auth_manager):
        config = AuthConfig(provider_type="mock")
        auth_manager.configure(config)
        assert "mock" in auth_manager.list_providers()

    def test_configure_ldap(self, auth_manager):
        config = AuthConfig(provider_type="ldap", server_url="ldap://x")
        auth_manager.configure(config)
        assert "ldap" in auth_manager.list_providers()

    def test_configure_oidc(self, auth_manager):
        config = AuthConfig(provider_type="oidc", issuer_url="https://idp")
        auth_manager.configure(config)
        assert "oidc" in auth_manager.list_providers()

    def test_configure_unknown_raises(self, auth_manager):
        config = AuthConfig(provider_type="saml")
        with pytest.raises(ValueError, match="Unknown provider type"):
            auth_manager.configure(config)

    def test_login_success(self, auth_manager):
        auth_manager.configure(AuthConfig(provider_type="mock"))
        token = auth_manager.login("admin", "password", provider="mock")
        assert token is not None
        assert isinstance(token, str)

    def test_login_invalid_credentials(self, auth_manager):
        auth_manager.configure(AuthConfig(provider_type="mock"))
        token = auth_manager.login("nonexistent", "pass", provider="mock")
        assert token is None

    def test_login_no_provider(self, auth_manager):
        token = auth_manager.login("admin", "pass", provider="ldap")
        assert token is None

    def test_get_session(self, auth_manager):
        auth_manager.configure(AuthConfig(provider_type="mock"))
        token = auth_manager.login("admin", "pass")
        user = auth_manager.get_session(token)
        assert user is not None
        assert user.username == "admin"

    def test_get_session_invalid_token(self, auth_manager):
        assert auth_manager.get_session("bad-token") is None

    def test_logout(self, auth_manager):
        auth_manager.configure(AuthConfig(provider_type="mock"))
        token = auth_manager.login("admin", "pass")
        auth_manager.logout(token)
        assert auth_manager.get_session(token) is None

    def test_login_creates_rbac_user(self, auth_manager, rbac):
        auth_manager.configure(AuthConfig(provider_type="mock"))
        auth_manager.login("admin", "pass")
        user = rbac.get_user_by_username("admin")
        assert user is not None
        assert user.role == Role.ADMIN

    def test_login_upserts_existing_user(self, auth_manager, rbac):
        rbac.create_user("admin", "Admin", "a@b.com", Role.DEVELOPER)
        auth_manager.configure(AuthConfig(provider_type="mock"))
        token = auth_manager.login("admin", "pass")
        user = auth_manager.get_session(token)
        assert user.role == Role.DEVELOPER  # preserved existing role

    def test_multiple_sessions(self, auth_manager):
        auth_manager.configure(AuthConfig(provider_type="mock"))
        t1 = auth_manager.login("admin", "pass1")
        t2 = auth_manager.login("developer", "pass2")
        assert t1 != t2
        assert auth_manager.get_session(t1).username == "admin"
        assert auth_manager.get_session(t2).username == "developer"

    def test_list_providers_empty(self, auth_manager):
        assert auth_manager.list_providers() == []
