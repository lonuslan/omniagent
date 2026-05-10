"""
Skill Scanner — multi-path skill discovery.

Scans directories for SKILL.md files and returns InstalledSkill objects.
Search paths (priority order):
  1. <project>/.omniagent/skills/   (project-local)
  2. ~/.omniagent/skills/           (user-global)
"""

from __future__ import annotations

from pathlib import Path

from .models import InstalledSkill
from .parser import parse_skill_md


def default_search_paths() -> list[Path]:
    """Return the default skill search paths."""
    return [
        Path.cwd() / ".omniagent" / "skills",
        Path.home() / ".omniagent" / "skills",
    ]


class SkillScanner:
    """Discovers skills by scanning multiple directories."""

    def __init__(self, search_paths: list[Path] | None = None) -> None:
        self._search_paths = search_paths or default_search_paths()

    def scan(self) -> list[InstalledSkill]:
        """Scan all search paths and return discovered skills."""
        seen: set[str] = set()
        skills: list[InstalledSkill] = []

        for base in self._search_paths:
            for skill in self.scan_path(base):
                if skill.manifest.id not in seen:
                    seen.add(skill.manifest.id)
                    skills.append(skill)

        return skills

    def scan_path(self, base_path: Path) -> list[InstalledSkill]:
        """Scan a single directory for skills.

        Looks for:
          - <base>/<skill-id>/SKILL.md
          - <base>/<skill-id>/skill.toml (future)
        """
        skills: list[InstalledSkill] = []
        if not base_path.is_dir():
            return skills

        for entry in sorted(base_path.iterdir()):
            if not entry.is_dir():
                continue

            skill_md = entry / "SKILL.md"
            if skill_md.exists():
                try:
                    manifest = parse_skill_md(skill_md)
                    if manifest.id:
                        skills.append(InstalledSkill(
                            manifest=manifest,
                            path=entry,
                        ))
                except Exception:
                    pass  # Skip malformed skills

        return skills
