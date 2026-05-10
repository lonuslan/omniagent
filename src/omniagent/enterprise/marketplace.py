"""
Private Marketplace — Enterprise internal agent/skill catalog.

SQLite-backed catalog with publish/search/install tracking
and approval workflow for enterprise governance.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CatalogEntry:
    """An item in the private marketplace catalog."""
    id: int | None = None
    item_id: str = ""               # agent ID or skill ID
    item_type: str = ""             # "agent" or "skill"
    name: str = ""
    version: str = ""
    description: str = ""
    author: str = ""
    capabilities: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    git_url: str = ""
    published_by: str = ""
    published_at: float = 0.0
    status: str = "active"          # active, pending_review, rejected
    install_count: int = 0
    rating: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "item_id": self.item_id,
            "item_type": self.item_type,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "capabilities": self.capabilities,
            "tags": self.tags,
            "git_url": self.git_url,
            "published_by": self.published_by,
            "published_at": self.published_at,
            "status": self.status,
            "install_count": self.install_count,
            "rating": self.rating,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CatalogEntry:
        return cls(
            id=data.get("id"),
            item_id=data.get("item_id", ""),
            item_type=data.get("item_type", ""),
            name=data.get("name", ""),
            version=data.get("version", ""),
            description=data.get("description", ""),
            author=data.get("author", ""),
            capabilities=data.get("capabilities", []),
            tags=data.get("tags", []),
            git_url=data.get("git_url", ""),
            published_by=data.get("published_by", ""),
            published_at=data.get("published_at", 0.0),
            status=data.get("status", "active"),
            install_count=data.get("install_count", 0),
            rating=data.get("rating", 0.0),
        )


class PrivateMarketplace:
    """Enterprise-internal marketplace for agents and skills."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or (Path.home() / ".omniagent" / "marketplace.db")
        self._init_db()

    def _init_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path))
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS catalog (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id TEXT NOT NULL,
                    item_type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    version TEXT,
                    description TEXT,
                    author TEXT,
                    capabilities TEXT DEFAULT '[]',
                    tags TEXT DEFAULT '[]',
                    git_url TEXT,
                    published_by TEXT,
                    published_at REAL,
                    status TEXT DEFAULT 'active',
                    install_count INTEGER DEFAULT 0,
                    rating REAL DEFAULT 0.0,
                    UNIQUE(item_id, item_type)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id TEXT NOT NULL,
                    item_type TEXT NOT NULL,
                    submitted_by TEXT,
                    reviewed_by TEXT,
                    action TEXT,
                    reason TEXT,
                    timestamp REAL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS installations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id TEXT NOT NULL,
                    item_type TEXT NOT NULL,
                    user_id TEXT,
                    installed_at REAL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_catalog_type ON catalog(item_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_catalog_status ON catalog(status)")
            conn.commit()
        finally:
            conn.close()

    # ── Publish ─────────────────────────────────────────────────────────

    def publish(self, entry: CatalogEntry, published_by: str) -> int:
        """Publish an agent or skill to the private catalog."""
        entry.published_by = published_by
        entry.published_at = time.time()
        conn = sqlite3.connect(str(self._db_path))
        try:
            cursor = conn.execute(
                """INSERT OR REPLACE INTO catalog
                   (item_id, item_type, name, version, description, author,
                    capabilities, tags, git_url, published_by, published_at,
                    status, install_count, rating)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry.item_id, entry.item_type, entry.name, entry.version,
                    entry.description, entry.author,
                    json.dumps(entry.capabilities), json.dumps(entry.tags),
                    entry.git_url, entry.published_by, entry.published_at,
                    entry.status, entry.install_count, entry.rating,
                ),
            )
            conn.commit()
            return cursor.lastrowid or 0
        finally:
            conn.close()

    def unpublish(self, item_id: str, item_type: str) -> bool:
        conn = sqlite3.connect(str(self._db_path))
        try:
            cursor = conn.execute(
                "DELETE FROM catalog WHERE item_id = ? AND item_type = ?",
                (item_id, item_type),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    # ── Query ───────────────────────────────────────────────────────────

    def get(self, item_id: str, item_type: str) -> CatalogEntry | None:
        conn = sqlite3.connect(str(self._db_path))
        try:
            row = conn.execute(
                "SELECT * FROM catalog WHERE item_id = ? AND item_type = ?",
                (item_id, item_type),
            ).fetchone()
            return self._row_to_entry(row) if row else None
        finally:
            conn.close()

    def search(
        self,
        query: str = "",
        item_type: str | None = None,
        capabilities: list[str] | None = None,
        status: str = "active",
    ) -> list[CatalogEntry]:
        conditions = []
        params: list[Any] = []

        if status:
            conditions.append("status = ?")
            params.append(status)
        if item_type:
            conditions.append("item_type = ?")
            params.append(item_type)

        where = " AND ".join(conditions) if conditions else "1"
        sql = f"SELECT * FROM catalog WHERE {where} ORDER BY install_count DESC"

        conn = sqlite3.connect(str(self._db_path))
        try:
            rows = conn.execute(sql, params).fetchall()
            entries = [self._row_to_entry(row) for row in rows]

            # Text filter in Python (SQLite JSON support is limited)
            if query:
                q = query.lower()
                entries = [
                    e for e in entries
                    if q in e.name.lower() or q in e.description.lower()
                ]

            # Capability filter
            if capabilities:
                cap_set = set(capabilities)
                entries = [
                    e for e in entries
                    if cap_set.intersection(e.capabilities)
                ]

            return entries
        finally:
            conn.close()

    def list_all(self, item_type: str | None = None) -> list[CatalogEntry]:
        return self.search(item_type=item_type, status=None)

    # ── Install Tracking ────────────────────────────────────────────────

    def record_install(self, item_id: str, item_type: str, user_id: str) -> None:
        conn = sqlite3.connect(str(self._db_path))
        try:
            conn.execute(
                "INSERT INTO installations (item_id, item_type, user_id, installed_at) VALUES (?, ?, ?, ?)",
                (item_id, item_type, user_id, time.time()),
            )
            conn.execute(
                "UPDATE catalog SET install_count = install_count + 1 WHERE item_id = ? AND item_type = ?",
                (item_id, item_type),
            )
            conn.commit()
        finally:
            conn.close()

    def get_install_count(self, item_id: str, item_type: str) -> int:
        conn = sqlite3.connect(str(self._db_path))
        try:
            row = conn.execute(
                "SELECT install_count FROM catalog WHERE item_id = ? AND item_type = ?",
                (item_id, item_type),
            ).fetchone()
            return row[0] if row else 0
        finally:
            conn.close()

    # ── Approval Workflow ───────────────────────────────────────────────

    def submit_for_review(self, item_id: str, item_type: str, submitted_by: str) -> None:
        conn = sqlite3.connect(str(self._db_path))
        try:
            conn.execute(
                "UPDATE catalog SET status = 'pending_review' WHERE item_id = ? AND item_type = ?",
                (item_id, item_type),
            )
            conn.execute(
                "INSERT INTO reviews (item_id, item_type, submitted_by, action, timestamp) VALUES (?, ?, ?, 'submit', ?)",
                (item_id, item_type, submitted_by, time.time()),
            )
            conn.commit()
        finally:
            conn.close()

    def approve(self, item_id: str, item_type: str, approved_by: str) -> None:
        conn = sqlite3.connect(str(self._db_path))
        try:
            conn.execute(
                "UPDATE catalog SET status = 'active' WHERE item_id = ? AND item_type = ?",
                (item_id, item_type),
            )
            conn.execute(
                "INSERT INTO reviews (item_id, item_type, reviewed_by, action, timestamp) VALUES (?, ?, ?, 'approve', ?)",
                (item_id, item_type, approved_by, time.time()),
            )
            conn.commit()
        finally:
            conn.close()

    def reject(self, item_id: str, item_type: str, rejected_by: str, reason: str = "") -> None:
        conn = sqlite3.connect(str(self._db_path))
        try:
            conn.execute(
                "UPDATE catalog SET status = 'rejected' WHERE item_id = ? AND item_type = ?",
                (item_id, item_type),
            )
            conn.execute(
                "INSERT INTO reviews (item_id, item_type, reviewed_by, action, reason, timestamp) VALUES (?, ?, ?, 'reject', ?, ?)",
                (item_id, item_type, rejected_by, reason, time.time()),
            )
            conn.commit()
        finally:
            conn.close()

    # ── Internal ────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_entry(row: tuple) -> CatalogEntry:
        return CatalogEntry(
            id=row[0],
            item_id=row[1],
            item_type=row[2],
            name=row[3],
            version=row[4] or "",
            description=row[5] or "",
            author=row[6] or "",
            capabilities=json.loads(row[7]) if row[7] else [],
            tags=json.loads(row[8]) if row[8] else [],
            git_url=row[9] or "",
            published_by=row[10] or "",
            published_at=row[11] or 0.0,
            status=row[12] or "active",
            install_count=row[13] or 0,
            rating=row[14] or 0.0,
        )
