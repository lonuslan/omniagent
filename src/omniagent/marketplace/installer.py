"""
Agent Package Installer.

Handles parsing agent.toml, validating packages, installing from git repos,
and managing the installed agent directory at ~/.omniagent/agents/.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from .models import AgentPackage
from .registry import INSTALL_DIR

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ModuleNotFoundError:
        tomllib = None  # type: ignore[assignment]


def parse_agent_toml(toml_path: Path) -> AgentPackage:
    """Parse an agent.toml file into an AgentPackage."""
    if not toml_path.exists():
        raise FileNotFoundError(f"agent.toml not found: {toml_path}")
    if tomllib is None:
        raise RuntimeError("tomllib not available (requires Python 3.11+)")

    data = tomllib.loads(toml_path.read_text(encoding="utf-8"))

    required = ["id", "name", "version"]
    for field in required:
        if field not in data:
            raise ValueError(f"agent.toml missing required field: {field}")

    return AgentPackage(
        id=data["id"],
        name=data["name"],
        version=data["version"],
        author=data.get("author", ""),
        description=data.get("description", ""),
        capabilities=data.get("capabilities", []),
        entry_point=data.get("entry_point", "agent.py"),
        tags=data.get("tags", []),
        homepage=data.get("homepage", ""),
        git_url=data.get("git_url", ""),
        requirements=data.get("requirements", []),
        metadata=data.get("metadata", {}),
    )


def validate_package(pkg_dir: Path) -> tuple[bool, str]:
    """
    Validate an agent package directory.
    Returns (is_valid, error_message).
    """
    toml_path = pkg_dir / "agent.toml"
    if not toml_path.exists():
        return False, "Missing agent.toml"

    try:
        pkg = parse_agent_toml(toml_path)
    except Exception as e:
        return False, f"Invalid agent.toml: {e}"

    entry = pkg_dir / pkg.entry_point
    if not entry.exists():
        return False, f"Entry point not found: {pkg.entry_point}"

    # Check for BaseAgent subclass
    try:
        content = entry.read_text(encoding="utf-8")
        if "BaseAgent" not in content and "base.BaseAgent" not in content:
            return False, "Entry point does not reference BaseAgent"
    except Exception:
        return False, "Cannot read entry point file"

    return True, ""


def install_from_git(git_url: str, agent_id: str | None = None, force: bool = False) -> AgentPackage:
    """
    Clone an agent package from a git URL, validate it, and install to ~/.omniagent/agents/.
    Returns the parsed AgentPackage.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir) / "repo"
        result = subprocess.run(
            ["git", "clone", "--depth", "1", git_url, str(tmp_path)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"git clone failed: {result.stderr.strip()}")

        # Find agent.toml (may be in root or subdirectory)
        toml_candidates = list(tmp_path.rglob("agent.toml"))
        if not toml_candidates:
            raise FileNotFoundError("No agent.toml found in repository")
        toml_path = toml_candidates[0]
        pkg_dir = toml_path.parent

        pkg = parse_agent_toml(toml_path)
        valid, err = validate_package(pkg_dir)
        if not valid:
            raise ValueError(f"Invalid package: {err}")

        target_id = agent_id or pkg.id
        target_dir = INSTALL_DIR / target_id
        if target_dir.exists():
            if not force:
                raise FileExistsError(f"Agent already installed: {target_id}")
            shutil.rmtree(target_dir)

        shutil.copytree(pkg_dir, target_dir)
        return pkg


def uninstall(agent_id: str) -> bool:
    """Remove an installed agent. Returns True if removed."""
    target_dir = INSTALL_DIR / agent_id
    if target_dir.exists():
        shutil.rmtree(target_dir)
        return True
    return False


def list_installed() -> list[AgentPackage]:
    """List all installed agent packages."""
    if not INSTALL_DIR.exists():
        return []
    packages = []
    for d in sorted(INSTALL_DIR.iterdir()):
        if d.is_dir():
            toml_path = d / "agent.toml"
            if toml_path.exists():
                try:
                    packages.append(parse_agent_toml(toml_path))
                except Exception:
                    continue
    return packages


def is_installed(agent_id: str) -> bool:
    """Check if an agent is installed."""
    return (INSTALL_DIR / agent_id).is_dir()


def get_install_path(agent_id: str) -> Path | None:
    """Get the install path for an agent, or None if not installed."""
    path = INSTALL_DIR / agent_id
    return path if path.is_dir() else None
