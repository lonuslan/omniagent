"""
OmniAgent Marketplace — Agent discovery, installation, and management.

Provides:
  - LocalRegistry: JSON file-based registry at ~/.omniagent/registry/
  - GitHubRegistry: Remote index with offline fallback
  - Package installer: git clone + validate + install
  - Dynamic loader: importlib-based runtime agent loading
"""

from .installer import install_from_git, is_installed, list_installed, uninstall
from .loader import load_agent_from_dir, load_and_register, package_to_descriptor
from .models import AgentPackage, MarketplaceEntry, RegistryIndex, Review
from .registry import GitHubRegistry, LocalRegistry

__all__ = [
    "AgentPackage",
    "MarketplaceEntry",
    "RegistryIndex",
    "Review",
    "LocalRegistry",
    "GitHubRegistry",
    "install_from_git",
    "uninstall",
    "list_installed",
    "is_installed",
    "load_agent_from_dir",
    "load_and_register",
    "package_to_descriptor",
]
