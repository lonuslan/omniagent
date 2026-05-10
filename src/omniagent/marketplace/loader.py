"""
Dynamic Agent Loader.

Loads agent classes from installed marketplace packages using importlib,
and converts AgentPackage metadata into AgentDescriptor for registry integration.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from ..agents.base import BaseAgent
from ..protocol import AgentCapability, AgentDescriptor, AgentRole
from .installer import get_install_path, parse_agent_toml
from .models import AgentPackage


def load_agent_from_dir(agent_dir: Path) -> type[BaseAgent]:
    """
    Dynamically load a BaseAgent subclass from an agent package directory.
    Uses importlib.util.spec_from_file_location for runtime loading.
    """
    toml_path = agent_dir / "agent.toml"
    if not toml_path.exists():
        raise FileNotFoundError(f"agent.toml not found in {agent_dir}")

    pkg = parse_agent_toml(toml_path)
    entry_path = agent_dir / pkg.entry_point
    if not entry_path.exists():
        raise FileNotFoundError(f"Entry point not found: {entry_path}")

    module_name = f"omniagent.marketplace.agent_{pkg.id}"
    spec = importlib.util.spec_from_file_location(module_name, str(entry_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {entry_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    # Find the BaseAgent subclass
    agent_cls = None
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if (
            isinstance(attr, type)
            and issubclass(attr, BaseAgent)
            and attr is not BaseAgent
        ):
            agent_cls = attr
            break

    if agent_cls is None:
        raise TypeError(f"No BaseAgent subclass found in {entry_path}")

    return agent_cls


def package_to_descriptor(pkg: AgentPackage) -> AgentDescriptor:
    """Convert an AgentPackage into an AgentDescriptor for registry."""
    caps = []
    for cap_str in pkg.capabilities:
        try:
            caps.append(AgentCapability(cap_str))
        except ValueError:
            caps.append(AgentCapability.GENERAL_PURPOSE)

    return AgentDescriptor(
        id=pkg.id,
        name=pkg.name,
        version=pkg.version,
        capabilities=caps,
        role=AgentRole.EXECUTOR,
        description=pkg.description,
        provider="marketplace",
        metadata={"author": pkg.author, "tags": pkg.tags, **pkg.metadata},
    )


def load_and_register(agent_id: str, registry: Any) -> AgentDescriptor:
    """
    Load an installed agent by ID, instantiate it, and register with the registry.
    Returns the AgentDescriptor.
    """
    agent_path = get_install_path(agent_id)
    if agent_path is None:
        raise FileNotFoundError(f"Agent not installed: {agent_id}")

    pkg = parse_agent_toml(agent_path / "agent.toml")
    agent_cls = load_agent_from_dir(agent_path)
    descriptor = package_to_descriptor(pkg)

    # Instantiate to verify it works
    agent = agent_cls()
    agent.descriptor = descriptor

    registry.register(descriptor, agent_cls)
    return descriptor
