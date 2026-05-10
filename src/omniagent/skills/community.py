"""
Community Skill Registry — fetches the remote skill index.

Mirrors marketplace/registry.py GitHubRegistry pattern with
TTL cache and offline fallback.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

SKILL_INDEX_URL = (
    "https://raw.githubusercontent.com/lonuslan/omniagent-marketplace/main/skills.json"
)

CACHE_TTL = 3600  # 1 hour


class SkillCommunityRegistry:
    """Fetches the community skill index from a remote URL."""

    def __init__(
        self,
        url: str = SKILL_INDEX_URL,
        local_path: Path | None = None,
    ) -> None:
        self._url = url
        self._local_path = local_path or (Path.home() / ".omniagent" / "skills_index.json")
        self._cache: list[dict[str, Any]] | None = None
        self._cache_time: float = 0.0

    def fetch(self, force: bool = False) -> list[dict[str, Any]]:
        """Fetch the remote skill index with TTL cache and offline fallback."""
        now = time.time()

        # Return memory cache if fresh
        if not force and self._cache and (now - self._cache_time) < CACHE_TTL:
            return self._cache

        # Try remote fetch
        try:
            import httpx
            with httpx.Client(timeout=15) as client:
                resp = client.get(self._url)
                if resp.status_code == 200:
                    data = resp.json()
                    skills = data.get("skills", [])
                    self._cache = skills
                    self._cache_time = now
                    # Persist for offline use
                    self._local_path.parent.mkdir(parents=True, exist_ok=True)
                    self._local_path.write_text(
                        json.dumps(data, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    return skills
        except Exception:
            pass

        # Fallback to local cache
        return self._load_local()

    def _load_local(self) -> list[dict[str, Any]]:
        """Load from local cache file."""
        if self._local_path.exists():
            try:
                data = json.loads(self._local_path.read_text(encoding="utf-8"))
                skills = data.get("skills", [])
                self._cache = skills
                self._cache_time = time.time()
                return skills
            except Exception:
                pass
        return []

    def search(self, query: str, tags: list[str] | None = None) -> list[dict[str, Any]]:
        """Search the community index by query and optional tags."""
        skills = self.fetch()
        query_lower = query.lower()
        results = []

        for skill in skills:
            # Text match
            text = f"{skill.get('name', '')} {skill.get('description', '')}".lower()
            if query_lower and query_lower not in text:
                continue
            # Tag match
            if tags:
                skill_tags = set(skill.get("tags", []))
                if not any(t in skill_tags for t in tags):
                    continue
            results.append(skill)

        return results

    def get(self, skill_id: str) -> dict[str, Any] | None:
        """Get a specific skill entry from the index."""
        skills = self.fetch()
        for skill in skills:
            if skill.get("id") == skill_id:
                return skill
        return None
