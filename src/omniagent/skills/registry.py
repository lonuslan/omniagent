"""
Skill Registry — central registry for all available skills.

Follows the same pattern as AgentRegistry and ToolRegistry.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .models import InstalledSkill, SkillManifest
from .scanner import SkillScanner


class SkillRegistry:
    """Central registry for all available skills."""

    def __init__(self) -> None:
        self._skills: dict[str, InstalledSkill] = {}
        self._by_capability: dict[str, list[str]] = defaultdict(list)
        self._scanner: SkillScanner | None = None

    def set_scanner(self, scanner: SkillScanner) -> None:
        """Set the scanner for auto-discovery."""
        self._scanner = scanner

    # ── Registration ────────────────────────────────────────────────────

    def register(self, skill: InstalledSkill) -> None:
        """Register a skill."""
        self._skills[skill.manifest.id] = skill
        self._rebuild_indexes()

    def unregister(self, skill_id: str) -> None:
        """Remove a skill from the registry."""
        self._skills.pop(skill_id, None)
        self._rebuild_indexes()

    def _rebuild_indexes(self) -> None:
        self._by_capability.clear()
        for skill in self._skills.values():
            for cap in skill.manifest.capabilities:
                self._by_capability[cap].append(skill.manifest.id)

    # ── Lookup ──────────────────────────────────────────────────────────

    def get(self, skill_id: str) -> InstalledSkill | None:
        return self._skills.get(skill_id)

    def list_all(self) -> list[InstalledSkill]:
        return list(self._skills.values())

    def list_enabled(self) -> list[InstalledSkill]:
        return [s for s in self._skills.values() if s.enabled]

    def find_by_capability(self, capabilities: list[str]) -> list[InstalledSkill]:
        """Find enabled skills that enhance any of the given capabilities."""
        skill_ids: set[str] = set()
        for cap in capabilities:
            skill_ids.update(self._by_capability.get(cap, []))
        return [
            self._skills[sid] for sid in skill_ids
            if sid in self._skills and self._skills[sid].enabled
        ]

    def find_by_trigger(self, text: str) -> list[InstalledSkill]:
        """Find enabled skills whose triggers match the given text."""
        text_lower = text.lower()
        results = []
        for skill in self._skills.values():
            if not skill.enabled:
                continue
            for trigger in skill.manifest.triggers:
                if trigger.lower() in text_lower:
                    results.append(skill)
                    break
        return results

    # ── Enable/Disable ──────────────────────────────────────────────────

    def enable(self, skill_id: str) -> bool:
        skill = self._skills.get(skill_id)
        if skill:
            skill.enabled = True
            return True
        return False

    def disable(self, skill_id: str) -> bool:
        skill = self._skills.get(skill_id)
        if skill:
            skill.enabled = False
            return True
        return False

    # ── Discovery ───────────────────────────────────────────────────────

    def discover(self) -> int:
        """Scan all search paths and register discovered skills. Returns count."""
        if not self._scanner:
            return 0
        count = 0
        for skill in self._scanner.scan():
            if skill.manifest.id not in self._skills:
                self.register(skill)
                count += 1
        return count

    # ── Serialization ───────────────────────────────────────────────────

    def to_list(self) -> list[dict[str, Any]]:
        """Return all skills as JSON-serializable dicts."""
        return [
            {
                "id": s.manifest.id,
                "name": s.manifest.name,
                "version": s.manifest.version,
                "description": s.manifest.description,
                "author": s.manifest.author,
                "tags": s.manifest.tags,
                "capabilities": s.manifest.capabilities,
                "triggers": s.manifest.triggers,
                "enabled": s.enabled,
                "path": str(s.path),
            }
            for s in self._skills.values()
        ]
