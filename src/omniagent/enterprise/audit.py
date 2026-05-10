"""
Audit Log Persistence — SQLite-backed audit trail.

Extends the in-memory ExecutionRecord with persistent storage,
rich querying (time range, tool, user, outcome), and purge support.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class AuditEntry:
    """Extended audit record with user context and persistence fields."""
    id: int | None = None
    tool_name: str = ""
    agent_id: str = ""
    task_id: str = ""
    user_id: str = ""
    user_role: str = ""
    args: str = ""
    result: str = ""
    is_error: bool = False
    duration_ms: float = 0.0
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tool_name": self.tool_name,
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "user_id": self.user_id,
            "user_role": self.user_role,
            "args": self.args,
            "result": self.result,
            "is_error": self.is_error,
            "duration_ms": round(self.duration_ms, 1),
            "timestamp": self.timestamp,
        }


class AuditStore:
    """SQLite-backed persistent audit log."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or (Path.home() / ".omniagent" / "audit.db")
        self._init_db()

    def _init_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path))
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool_name TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    task_id TEXT,
                    user_id TEXT,
                    user_role TEXT,
                    args TEXT,
                    result TEXT,
                    is_error BOOLEAN,
                    duration_ms REAL,
                    timestamp REAL NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_tool ON audit_log(tool_name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_agent ON audit_log(agent_id)")
            conn.commit()
        finally:
            conn.close()

    def record(self, entry: AuditEntry) -> int:
        """Insert an audit entry. Returns the row ID."""
        ts = entry.timestamp or time.time()
        conn = sqlite3.connect(str(self._db_path))
        try:
            cursor = conn.execute(
                """INSERT INTO audit_log
                   (tool_name, agent_id, task_id, user_id, user_role, args, result, is_error, duration_ms, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry.tool_name,
                    entry.agent_id,
                    entry.task_id,
                    entry.user_id,
                    entry.user_role,
                    entry.args,
                    entry.result,
                    int(entry.is_error),
                    entry.duration_ms,
                    ts,
                ),
            )
            conn.commit()
            return cursor.lastrowid or 0
        finally:
            conn.close()

    def query(
        self,
        start_time: float | None = None,
        end_time: float | None = None,
        tool_name: str | None = None,
        agent_id: str | None = None,
        user_id: str | None = None,
        is_error: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditEntry]:
        """Query audit entries with filters."""
        conditions = []
        params: list[Any] = []

        if start_time is not None:
            conditions.append("timestamp >= ?")
            params.append(start_time)
        if end_time is not None:
            conditions.append("timestamp <= ?")
            params.append(end_time)
        if tool_name is not None:
            conditions.append("tool_name = ?")
            params.append(tool_name)
        if agent_id is not None:
            conditions.append("agent_id = ?")
            params.append(agent_id)
        if user_id is not None:
            conditions.append("user_id = ?")
            params.append(user_id)
        if is_error is not None:
            conditions.append("is_error = ?")
            params.append(int(is_error))

        where = " AND ".join(conditions) if conditions else "1"
        sql = f"SELECT * FROM audit_log WHERE {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        conn = sqlite3.connect(str(self._db_path))
        try:
            rows = conn.execute(sql, params).fetchall()
            return [self._row_to_entry(row) for row in rows]
        finally:
            conn.close()

    def count(
        self,
        start_time: float | None = None,
        end_time: float | None = None,
        tool_name: str | None = None,
        agent_id: str | None = None,
        user_id: str | None = None,
        is_error: bool | None = None,
    ) -> int:
        """Count matching entries."""
        conditions = []
        params: list[Any] = []

        if start_time is not None:
            conditions.append("timestamp >= ?")
            params.append(start_time)
        if end_time is not None:
            conditions.append("timestamp <= ?")
            params.append(end_time)
        if tool_name is not None:
            conditions.append("tool_name = ?")
            params.append(tool_name)
        if agent_id is not None:
            conditions.append("agent_id = ?")
            params.append(agent_id)
        if user_id is not None:
            conditions.append("user_id = ?")
            params.append(user_id)
        if is_error is not None:
            conditions.append("is_error = ?")
            params.append(int(is_error))

        where = " AND ".join(conditions) if conditions else "1"
        sql = f"SELECT COUNT(*) FROM audit_log WHERE {where}"

        conn = sqlite3.connect(str(self._db_path))
        try:
            return conn.execute(sql, params).fetchone()[0]
        finally:
            conn.close()

    def get_by_id(self, entry_id: int) -> AuditEntry | None:
        conn = sqlite3.connect(str(self._db_path))
        try:
            row = conn.execute("SELECT * FROM audit_log WHERE id = ?", (entry_id,)).fetchone()
            return self._row_to_entry(row) if row else None
        finally:
            conn.close()

    def purge_before(self, timestamp: float) -> int:
        """Delete entries older than timestamp. Returns count deleted."""
        conn = sqlite3.connect(str(self._db_path))
        try:
            cursor = conn.execute("DELETE FROM audit_log WHERE timestamp < ?", (timestamp,))
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    def get_stats(self) -> dict[str, Any]:
        """Return aggregate statistics."""
        conn = sqlite3.connect(str(self._db_path))
        try:
            total = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
            errors = conn.execute("SELECT COUNT(*) FROM audit_log WHERE is_error = 1").fetchone()[0]
            tools = conn.execute(
                "SELECT tool_name, COUNT(*) as cnt FROM audit_log GROUP BY tool_name ORDER BY cnt DESC LIMIT 10"
            ).fetchall()
            return {
                "total_entries": total,
                "total_errors": errors,
                "error_rate": round(errors / total, 3) if total > 0 else 0.0,
                "top_tools": [{"tool": t[0], "count": t[1]} for t in tools],
            }
        finally:
            conn.close()

    @staticmethod
    def _row_to_entry(row: tuple) -> AuditEntry:
        return AuditEntry(
            id=row[0],
            tool_name=row[1],
            agent_id=row[2],
            task_id=row[3] or "",
            user_id=row[4] or "",
            user_role=row[5] or "",
            args=row[6] or "",
            result=row[7] or "",
            is_error=bool(row[8]),
            duration_ms=row[9] or 0.0,
            timestamp=row[10] or 0.0,
        )
