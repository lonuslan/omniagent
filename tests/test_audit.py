"""Tests for AuditStore (SQLite-backed audit log)."""

import pytest

from omniagent.enterprise.audit import AuditEntry, AuditStore


@pytest.fixture
def store(tmp_path):
    return AuditStore(db_path=tmp_path / "audit.db")


class TestAuditEntry:
    def test_to_dict(self):
        entry = AuditEntry(
            id=1, tool_name="read", agent_id="a1", task_id="t1",
            user_id="u1", user_role="developer", args='{"path": "x"}',
            result="ok", is_error=False, duration_ms=12.5, timestamp=1000.0,
        )
        d = entry.to_dict()
        assert d["tool_name"] == "read"
        assert d["duration_ms"] == 12.5


class TestAuditStore:
    def test_record_and_query(self, store):
        store.record(AuditEntry(
            tool_name="read", agent_id="a1", task_id="t1",
            args='{"path": "x.txt"}', result="content",
            duration_ms=5.0, timestamp=1000.0,
        ))
        results = store.query()
        assert len(results) == 1
        assert results[0].tool_name == "read"

    def test_query_by_tool(self, store):
        store.record(AuditEntry(tool_name="read", agent_id="a1", timestamp=1.0))
        store.record(AuditEntry(tool_name="write", agent_id="a1", timestamp=2.0))
        store.record(AuditEntry(tool_name="read", agent_id="a2", timestamp=3.0))
        assert store.count(tool_name="read") == 2
        assert store.count(tool_name="write") == 1

    def test_query_by_agent(self, store):
        store.record(AuditEntry(tool_name="read", agent_id="a1", timestamp=1.0))
        store.record(AuditEntry(tool_name="read", agent_id="a2", timestamp=2.0))
        assert store.count(agent_id="a1") == 1

    def test_query_by_user(self, store):
        store.record(AuditEntry(tool_name="read", agent_id="a1", user_id="u1", timestamp=1.0))
        store.record(AuditEntry(tool_name="read", agent_id="a1", user_id="u2", timestamp=2.0))
        assert store.count(user_id="u1") == 1

    def test_query_by_error(self, store):
        store.record(AuditEntry(tool_name="read", agent_id="a1", is_error=False, timestamp=1.0))
        store.record(AuditEntry(tool_name="read", agent_id="a1", is_error=True, timestamp=2.0))
        assert store.count(is_error=True) == 1
        assert store.count(is_error=False) == 1

    def test_query_time_range(self, store):
        for i in range(10):
            store.record(AuditEntry(tool_name="read", agent_id="a1", timestamp=float(i)))
        results = store.query(start_time=3.0, end_time=7.0)
        assert len(results) == 5  # 3, 4, 5, 6, 7

    def test_query_limit_offset(self, store):
        for i in range(20):
            store.record(AuditEntry(tool_name="read", agent_id="a1", timestamp=float(i)))
        page1 = store.query(limit=5, offset=0)
        page2 = store.query(limit=5, offset=5)
        assert len(page1) == 5
        assert len(page2) == 5
        assert page1[0].id != page2[0].id

    def test_query_ordered_by_timestamp_desc(self, store):
        store.record(AuditEntry(tool_name="read", agent_id="a1", timestamp=1.0))
        store.record(AuditEntry(tool_name="read", agent_id="a1", timestamp=5.0))
        store.record(AuditEntry(tool_name="read", agent_id="a1", timestamp=3.0))
        results = store.query()
        assert results[0].timestamp == 5.0
        assert results[1].timestamp == 3.0
        assert results[2].timestamp == 1.0

    def test_get_by_id(self, store):
        row_id = store.record(AuditEntry(tool_name="write", agent_id="a1", timestamp=1.0))
        entry = store.get_by_id(row_id)
        assert entry is not None
        assert entry.tool_name == "write"
        assert store.get_by_id(99999) is None

    def test_purge_before(self, store):
        for i in range(10):
            store.record(AuditEntry(tool_name="read", agent_id="a1", timestamp=100.0 + i))
        deleted = store.purge_before(105.0)
        assert deleted == 5  # 100, 101, 102, 103, 104
        assert store.count() == 5

    def test_get_stats(self, store):
        store.record(AuditEntry(tool_name="read", agent_id="a1", is_error=False, timestamp=1.0))
        store.record(AuditEntry(tool_name="read", agent_id="a1", is_error=False, timestamp=2.0))
        store.record(AuditEntry(tool_name="write", agent_id="a1", is_error=True, timestamp=3.0))
        stats = store.get_stats()
        assert stats["total_entries"] == 3
        assert stats["total_errors"] == 1
        assert stats["error_rate"] == pytest.approx(1 / 3, abs=0.01)
        assert len(stats["top_tools"]) == 2

    def test_persistence(self, tmp_path):
        db_path = tmp_path / "test.db"
        s1 = AuditStore(db_path=db_path)
        s1.record(AuditEntry(tool_name="read", agent_id="a1", timestamp=1.0))
        s1.record(AuditEntry(tool_name="write", agent_id="a2", timestamp=2.0))

        s2 = AuditStore(db_path=db_path)
        assert s2.count() == 2
