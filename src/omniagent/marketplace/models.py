"""
Marketplace data models.

Defines the data structures for the agent marketplace: registry entries,
agent packages, reviews, and index metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MarketplaceEntry:
    """An agent listed in the marketplace registry."""
    id: str
    name: str
    version: str
    author: str
    description: str
    capabilities: list[str] = field(default_factory=list)
    git_url: str = ""
    homepage: str = ""
    tags: list[str] = field(default_factory=list)
    downloads: int = 0
    rating: float = 0.0
    rating_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "capabilities": self.capabilities,
            "git_url": self.git_url,
            "homepage": self.homepage,
            "tags": self.tags,
            "downloads": self.downloads,
            "rating": self.rating,
            "rating_count": self.rating_count,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MarketplaceEntry:
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            version=data.get("version", "0.0.0"),
            author=data.get("author", ""),
            description=data.get("description", ""),
            capabilities=data.get("capabilities", []),
            git_url=data.get("git_url", ""),
            homepage=data.get("homepage", ""),
            tags=data.get("tags", []),
            downloads=data.get("downloads", 0),
            rating=data.get("rating", 0.0),
            rating_count=data.get("rating_count", 0),
            metadata=data.get("metadata", {}),
        )


@dataclass
class Review:
    """A user review/rating for an agent."""
    agent_id: str
    user: str
    score: int  # 1-5
    comment: str = ""
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "user": self.user,
            "score": self.score,
            "comment": self.comment,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Review:
        return cls(
            agent_id=data.get("agent_id", ""),
            user=data.get("user", ""),
            score=data.get("score", 5),
            comment=data.get("comment", ""),
            timestamp=data.get("timestamp", 0.0),
        )


@dataclass
class AgentPackage:
    """Parsed representation of an agent.toml + agent.py package."""
    id: str
    name: str
    version: str
    author: str = ""
    description: str = ""
    capabilities: list[str] = field(default_factory=list)
    entry_point: str = "agent.py"
    tags: list[str] = field(default_factory=list)
    homepage: str = ""
    git_url: str = ""
    requirements: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "capabilities": self.capabilities,
            "entry_point": self.entry_point,
            "tags": self.tags,
            "homepage": self.homepage,
            "git_url": self.git_url,
            "requirements": self.requirements,
            "metadata": self.metadata,
        }


@dataclass
class RegistryIndex:
    """The full marketplace index containing all entries."""
    version: str = "1.0"
    entries: list[MarketplaceEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "entries": [e.to_dict() for e in self.entries],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RegistryIndex:
        entries = [MarketplaceEntry.from_dict(e) for e in data.get("entries", [])]
        return cls(version=data.get("version", "1.0"), entries=entries)
