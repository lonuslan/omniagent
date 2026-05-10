"""
Skill Installer — install, uninstall, and manage skills on disk.

Mirrors marketplace/installer.py patterns for agent packages.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from .models import InstalledSkill, SkillManifest
from .parser import parse_skill_md

SKILLS_DIR = Path.home() / ".omniagent" / "skills"


def install_skill_from_git(git_url: str, skill_id: str | None = None, force: bool = False) -> SkillManifest:
    """Clone a skill from a git URL, validate SKILL.md, install to skills dir.

    Steps:
      1. git clone --depth 1 into tempdir
      2. Find SKILL.md (root or subdirectory)
      3. Parse and validate
      4. Copy to SKILLS_DIR/<skill_id>/
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir) / "repo"

        # Clone
        result = subprocess.run(
            ["git", "clone", "--depth", "1", git_url, str(tmp_path)],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(f"git clone failed: {result.stderr[:300]}")

        # Find SKILL.md
        skill_md = _find_skill_md(tmp_path)
        if not skill_md:
            raise FileNotFoundError("No SKILL.md found in repository")

        # Parse
        manifest = parse_skill_md(skill_md)
        if not manifest.id:
            raise ValueError("SKILL.md has no 'id' field")

        target_id = skill_id or manifest.id
        target_dir = SKILLS_DIR / target_id

        # Check existing
        if target_dir.exists() and not force:
            raise FileExistsError(f"Skill '{target_id}' already installed. Use force=True to overwrite.")

        # Install
        if target_dir.exists():
            shutil.rmtree(target_dir)
        SKILLS_DIR.mkdir(parents=True, exist_ok=True)

        # Copy the skill directory (parent of SKILL.md)
        skill_src = skill_md.parent
        shutil.copytree(skill_src, target_dir)

        # Update manifest id if overridden
        if skill_id and skill_id != manifest.id:
            manifest.id = skill_id
            _update_skill_id(target_dir / "SKILL.md", skill_id)

        return manifest


def uninstall_skill(skill_id: str) -> bool:
    """Remove an installed skill. Returns True if removed."""
    target_dir = SKILLS_DIR / skill_id
    if target_dir.exists():
        shutil.rmtree(target_dir)
        return True
    return False


def list_installed_skills() -> list[SkillManifest]:
    """List all installed skills."""
    if not SKILLS_DIR.exists():
        return []

    manifests = []
    for entry in sorted(SKILLS_DIR.iterdir()):
        if not entry.is_dir():
            continue
        skill_md = entry / "SKILL.md"
        if skill_md.exists():
            try:
                manifests.append(parse_skill_md(skill_md))
            except Exception:
                pass
    return manifests


def is_skill_installed(skill_id: str) -> bool:
    """Check if a skill is installed."""
    return (SKILLS_DIR / skill_id / "SKILL.md").exists()


def _find_skill_md(base_path: Path) -> Path | None:
    """Find SKILL.md in base_path or immediate subdirectories."""
    # Check root
    direct = base_path / "SKILL.md"
    if direct.exists():
        return direct

    # Check one level deep
    for entry in base_path.iterdir():
        if entry.is_dir():
            candidate = entry / "SKILL.md"
            if candidate.exists():
                return candidate

    return None


def _update_skill_id(skill_md_path: Path, new_id: str) -> None:
    """Update the id field in a SKILL.md file."""
    text = skill_md_path.read_text(encoding="utf-8")
    import re
    text = re.sub(r'^(id:\s*).+$', f'\\g<1>{new_id}', text, count=1, flags=re.MULTILINE)
    skill_md_path.write_text(text, encoding="utf-8")
