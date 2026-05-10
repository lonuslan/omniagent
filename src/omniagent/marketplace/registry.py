"""
Marketplace Registry implementations.

LocalRegistry — JSON file-based registry at ~/.omniagent/registry/
GitHubRegistry — Fetches remote index from GitHub raw URL with offline fallback.
"""

from __future__ import annotations

import json
import os
import time
from abc import ABC, abstractmethod
from pathlib import Path

from .models import MarketplaceEntry, RegistryIndex, Review

REGISTRY_DIR = Path.home() / ".omniagent" / "registry"
INDEX_FILE = REGISTRY_DIR / "index.json"
REVIEWS_FILE = REGISTRY_DIR / "reviews.json"
INSTALL_DIR = Path.home() / ".omniagent" / "agents"

GITHUB_INDEX_URL = (
    "https://raw.githubusercontent.com/lonuslan/omniagent-marketplace/main/index.json"
)
CACHE_TTL = 300  # 5 minutes


class BaseMarketplace(ABC):
    """Abstract base for marketplace registries."""

    @abstractmethod
    def search(self, query: str, capabilities: list[str] | None = None) -> list[MarketplaceEntry]:
        ...

    @abstractmethod
    def get(self, agent_id: str) -> MarketplaceEntry | None:
        ...

    @abstractmethod
    def list_all(self) -> list[MarketplaceEntry]:
        ...


class LocalRegistry(BaseMarketplace):
    """JSON file-based local registry at ~/.omniagent/registry/."""

    def __init__(self, index_path: Path | None = None, reviews_path: Path | None = None) -> None:
        self._index_path = index_path or INDEX_FILE
        self._reviews_path = reviews_path or REVIEWS_FILE
        self._index: RegistryIndex | None = None
        self._reviews: list[Review] | None = None

    # ── Index I/O ────────────────────────────────────────────────────────

    def _load_index(self) -> RegistryIndex:
        if self._index is not None:
            return self._index
        if self._index_path.exists():
            data = json.loads(self._index_path.read_text(encoding="utf-8"))
            self._index = RegistryIndex.from_dict(data)
        else:
            self._index = RegistryIndex()
        return self._index

    def _save_index(self) -> None:
        if self._index is None:
            return
        self._index_path.parent.mkdir(parents=True, exist_ok=True)
        self._index_path.write_text(
            json.dumps(self._index.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # ── Reviews I/O ──────────────────────────────────────────────────────

    def _load_reviews(self) -> list[Review]:
        if self._reviews is not None:
            return self._reviews
        if self._reviews_path.exists():
            data = json.loads(self._reviews_path.read_text(encoding="utf-8"))
            self._reviews = [Review.from_dict(r) for r in data]
        else:
            self._reviews = []
        return self._reviews

    def _save_reviews(self) -> None:
        if self._reviews is None:
            return
        self._reviews_path.parent.mkdir(parents=True, exist_ok=True)
        self._reviews_path.write_text(
            json.dumps([r.to_dict() for r in self._reviews], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # ── CRUD ─────────────────────────────────────────────────────────────

    def search(self, query: str, capabilities: list[str] | None = None) -> list[MarketplaceEntry]:
        index = self._load_index()
        q = query.lower()
        results = []
        for entry in index.entries:
            searchable = f"{entry.id} {entry.name} {entry.description} {' '.join(entry.tags)}".lower()
            if q and q not in searchable:
                continue
            if capabilities:
                entry_caps = set(entry.capabilities)
                if not entry_caps & set(capabilities):
                    continue
            results.append(entry)
        return results

    def get(self, agent_id: str) -> MarketplaceEntry | None:
        index = self._load_index()
        for entry in index.entries:
            if entry.id == agent_id:
                return entry
        return None

    def list_all(self) -> list[MarketplaceEntry]:
        return self._load_index().entries

    def add_entry(self, entry: MarketplaceEntry) -> None:
        index = self._load_index()
        # Replace if exists, else append
        index.entries = [e for e in index.entries if e.id != entry.id]
        index.entries.append(entry)
        self._save_index()

    def remove_entry(self, agent_id: str) -> bool:
        index = self._load_index()
        before = len(index.entries)
        index.entries = [e for e in index.entries if e.id != agent_id]
        if len(index.entries) < before:
            self._save_index()
            return True
        return False

    # ── Reviews ──────────────────────────────────────────────────────────

    def get_reviews(self, agent_id: str) -> list[Review]:
        reviews = self._load_reviews()
        return [r for r in reviews if r.agent_id == agent_id]

    def add_review(self, review: Review) -> None:
        reviews = self._load_reviews()
        reviews.append(review)
        self._save_reviews()
        # Update entry rating
        entry = self.get(review.agent_id)
        if entry:
            agent_reviews = self.get_reviews(review.agent_id)
            entry.rating = sum(r.score for r in agent_reviews) / len(agent_reviews)
            entry.rating_count = len(agent_reviews)
            self.add_entry(entry)

    def get_rating(self, agent_id: str) -> tuple[float, int]:
        reviews = self.get_reviews(agent_id)
        if not reviews:
            return (0.0, 0)
        return (sum(r.score for r in reviews) / len(reviews), len(reviews))


class GitHubRegistry(BaseMarketplace):
    """
    Remote marketplace that fetches the index from GitHub.
    Falls back to LocalRegistry on network failure.
    Caches the remote index for CACHE_TTL seconds.
    """

    def __init__(self, url: str = GITHUB_INDEX_URL, local: LocalRegistry | None = None) -> None:
        self._url = url
        self._local = local or LocalRegistry()
        self._cache: RegistryIndex | None = None
        self._cache_time: float = 0.0

    def _fetch_remote(self) -> RegistryIndex:
        now = time.time()
        if self._cache and (now - self._cache_time) < CACHE_TTL:
            return self._cache

        try:
            import httpx
            with httpx.Client(timeout=15) as client:
                resp = client.get(self._url)
                resp.raise_for_status()
                data = resp.json()
                self._cache = RegistryIndex.from_dict(data)
                self._cache_time = now
                # Sync to local
                for entry in self._cache.entries:
                    self._local.add_entry(entry)
                return self._cache
        except Exception:
            # Offline fallback
            return self._local._load_index()

    def search(self, query: str, capabilities: list[str] | None = None) -> list[MarketplaceEntry]:
        index = self._fetch_remote()
        q = query.lower()
        results = []
        for entry in index.entries:
            searchable = f"{entry.id} {entry.name} {entry.description} {' '.join(entry.tags)}".lower()
            if q and q not in searchable:
                continue
            if capabilities:
                entry_caps = set(entry.capabilities)
                if not entry_caps & set(capabilities):
                    continue
            results.append(entry)
        return results

    def get(self, agent_id: str) -> MarketplaceEntry | None:
        index = self._fetch_remote()
        for entry in index.entries:
            if entry.id == agent_id:
                return entry
        return None

    def list_all(self) -> list[MarketplaceEntry]:
        return self._fetch_remote().entries

    @property
    def local(self) -> LocalRegistry:
        return self._local
