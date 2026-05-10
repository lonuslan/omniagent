"""
Skill data models.

A Skill is a composable instruction pack that augments agent behavior at runtime.
It consists of a manifest (metadata) + instructions (prompt injection).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SkillToolConfig:
    """Tool configuration injected by a skill."""
    tool_name: str
    parameters: dict[str, Any] = field(default_factory=dict)
    override_description: str = ""


@dataclass
class SkillManifest:
    """Parsed SKILL.md manifest — the core data structure for a skill."""
    id: str
    name: str
    version: str
    description: str = ""
    author: str = ""
    tags: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    tool_configs: list[SkillToolConfig] = field(default_factory=list)
    instructions: str = ""
    triggers: list[str] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "tags": self.tags,
            "capabilities": self.capabilities,
            "tool_configs": [
                {"tool_name": tc.tool_name, "parameters": tc.parameters,
                 "override_description": tc.override_description}
                for tc in self.tool_configs
            ],
            "instructions": self.instructions,
            "triggers": self.triggers,
            "requirements": self.requirements,
            "conflicts": self.conflicts,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SkillManifest:
        tool_configs = [
            SkillToolConfig(
                tool_name=tc.get("tool_name", ""),
                parameters=tc.get("parameters", {}),
                override_description=tc.get("override_description", ""),
            )
            for tc in data.get("tool_configs", [])
        ]
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            version=data.get("version", "0.0.0"),
            description=data.get("description", ""),
            author=data.get("author", ""),
            tags=data.get("tags", []),
            capabilities=data.get("capabilities", []),
            tool_configs=tool_configs,
            instructions=data.get("instructions", ""),
            triggers=data.get("triggers", []),
            requirements=data.get("requirements", []),
            conflicts=data.get("conflicts", []),
            metadata=data.get("metadata", {}),
        )


@dataclass
class InstalledSkill:
    """A skill installed on disk."""
    manifest: SkillManifest
    path: Path
    enabled: bool = True
