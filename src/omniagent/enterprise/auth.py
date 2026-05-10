"""
External Authentication — SSO/LDAP integration stubs.

Defines the auth provider interface and provides mock implementations.
Real LDAP/OIDC integration requires ldap3 and authlib libraries.
"""

from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from .rbac import RBACManager, Role, User


@dataclass
class AuthConfig:
    """Configuration for external auth providers."""
    provider_type: str              # "ldap", "oidc", "mock"
    server_url: str = ""
    base_dn: str = ""               # LDAP base DN
    bind_dn: str = ""               # LDAP bind DN
    bind_password: str = ""         # LDAP bind password
    client_id: str = ""             # OIDC client ID
    client_secret: str = ""         # OIDC client secret
    issuer_url: str = ""            # OIDC issuer URL
    attribute_mapping: dict[str, str] = field(default_factory=dict)


class AuthProvider(ABC):
    """Abstract base for authentication providers."""

    @abstractmethod
    def authenticate(self, username: str, password: str) -> User | None:
        """Authenticate credentials. Returns User or None."""
        ...

    @abstractmethod
    def get_user_info(self, username: str) -> dict[str, Any] | None:
        """Fetch user attributes from the external provider."""
        ...


class MockAuthProvider(AuthProvider):
    """Mock auth provider for testing. Accepts any non-empty credentials."""

    def __init__(self, config: AuthConfig | None = None) -> None:
        self._config = config
        self._users: dict[str, dict[str, Any]] = {
            "admin": {"display_name": "Admin User", "email": "admin@company.com", "role": "admin"},
            "developer": {"display_name": "Dev User", "email": "dev@company.com", "role": "developer"},
            "viewer": {"display_name": "View User", "email": "viewer@company.com", "role": "viewer"},
        }

    def authenticate(self, username: str, password: str) -> User | None:
        """Accepts any known username with any non-empty password."""
        if not password:
            return None
        info = self._users.get(username)
        if not info:
            return None
        return User(
            id=str(uuid.uuid4()),
            username=username,
            display_name=info["display_name"],
            email=info["email"],
            role=Role(info["role"]),
            last_login=time.time(),
        )

    def get_user_info(self, username: str) -> dict[str, Any] | None:
        return self._users.get(username)


class LDAPAuthProvider(AuthProvider):
    """LDAP/Active Directory authentication stub.

    Real implementation requires the ldap3 library:
        pip install ldap3

    Flow:
        1. Bind with service account (bind_dn/bind_password)
        2. Search for user in base_dn
        3. Attempt bind with user DN + password
        4. Map LDAP attributes to User model
    """

    def __init__(self, config: AuthConfig) -> None:
        self._config = config

    def authenticate(self, username: str, password: str) -> User | None:
        raise NotImplementedError(
            "LDAP authentication requires the ldap3 library. "
            "Install with: pip install ldap3"
        )

    def get_user_info(self, username: str) -> dict[str, Any] | None:
        raise NotImplementedError(
            "LDAP authentication requires the ldap3 library. "
            "Install with: pip install ldap3"
        )


class OIDCAuthProvider(AuthProvider):
    """OpenID Connect authentication stub.

    Supports Azure AD, Google, Keycloak, etc.
    Real implementation requires the authlib library:
        pip install authlib

    Flow (CLI): Resource Owner Password Credentials grant
    Flow (GUI): Authorization Code grant (redirect to browser)
    """

    def __init__(self, config: AuthConfig) -> None:
        self._config = config

    def authenticate(self, username: str, password: str) -> User | None:
        raise NotImplementedError(
            "OIDC authentication requires the authlib library. "
            "Install with: pip install authlib"
        )

    def get_user_info(self, username: str) -> dict[str, Any] | None:
        raise NotImplementedError(
            "OIDC authentication requires the authlib library. "
            "Install with: pip install authlib"
        )


class AuthManager:
    """Manages authentication providers and session state."""

    def __init__(self, rbac: RBACManager) -> None:
        self._rbac = rbac
        self._providers: dict[str, AuthProvider] = {}
        self._sessions: dict[str, User] = {}  # session_token -> User

    def configure(self, config: AuthConfig) -> None:
        """Configure an auth provider."""
        if config.provider_type == "ldap":
            self._providers["ldap"] = LDAPAuthProvider(config)
        elif config.provider_type == "oidc":
            self._providers["oidc"] = OIDCAuthProvider(config)
        elif config.provider_type == "mock":
            self._providers["mock"] = MockAuthProvider(config)
        else:
            raise ValueError(f"Unknown provider type: {config.provider_type}")

    def login(self, username: str, password: str, provider: str = "mock") -> str | None:
        """Authenticate and create a session. Returns session token or None."""
        auth_provider = self._providers.get(provider)
        if not auth_provider:
            return None

        user = auth_provider.authenticate(username, password)
        if not user:
            return None

        # Upsert user in RBAC
        existing = self._rbac.get_user_by_username(username)
        if existing:
            self._rbac.record_login(existing.id)
            user = existing
        else:
            user = self._rbac.create_user(
                username=user.username,
                display_name=user.display_name,
                email=user.email,
                role=user.role,
            )

        token = str(uuid.uuid4())
        self._sessions[token] = user
        return token

    def get_session(self, token: str) -> User | None:
        """Get the user associated with a session token."""
        return self._sessions.get(token)

    def logout(self, token: str) -> None:
        """Invalidate a session."""
        self._sessions.pop(token, None)

    def list_providers(self) -> list[str]:
        """List configured provider names."""
        return list(self._providers.keys())
