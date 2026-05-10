"""Tests for PrivateMarketplace."""

import pytest

from omniagent.enterprise.marketplace import CatalogEntry, PrivateMarketplace


@pytest.fixture
def market(tmp_path):
    return PrivateMarketplace(db_path=tmp_path / "market.db")


def _make_entry(item_id: str, name: str, item_type: str = "agent", **kw) -> CatalogEntry:
    return CatalogEntry(
        item_id=item_id, item_type=item_type, name=name,
        version=kw.get("version", "1.0.0"),
        description=kw.get("description", f"{name} description"),
        author=kw.get("author", "test"),
        capabilities=kw.get("capabilities", []),
        tags=kw.get("tags", []),
    )


class TestCatalogEntry:
    def test_round_trip(self):
        e = CatalogEntry(
            item_id="my-agent", item_type="agent", name="My Agent",
            version="1.0", description="Test", capabilities=["code_generation"],
        )
        d = e.to_dict()
        restored = CatalogEntry.from_dict(d)
        assert restored.item_id == "my-agent"
        assert restored.capabilities == ["code_generation"]


class TestPrivateMarketplace:
    def test_publish_and_get(self, market):
        entry = _make_entry("agent-a", "Agent A")
        market.publish(entry, "admin")
        got = market.get("agent-a", "agent")
        assert got is not None
        assert got.name == "Agent A"
        assert got.published_by == "admin"

    def test_unpublish(self, market):
        market.publish(_make_entry("agent-a", "Agent A"), "admin")
        assert market.unpublish("agent-a", "agent")
        assert market.get("agent-a", "agent") is None

    def test_search_by_query(self, market):
        market.publish(_make_entry("a1", "Code Generator"), "admin")
        market.publish(_make_entry("a2", "Test Runner"), "admin")
        market.publish(_make_entry("a3", "Code Reviewer"), "admin")
        results = market.search(query="code")
        assert len(results) == 2

    def test_search_by_type(self, market):
        market.publish(_make_entry("a1", "Agent", item_type="agent"), "admin")
        market.publish(_make_entry("s1", "Skill", item_type="skill"), "admin")
        assert len(market.search(item_type="agent")) == 1
        assert len(market.search(item_type="skill")) == 1

    def test_search_by_capability(self, market):
        market.publish(_make_entry("a1", "A1", capabilities=["code_generation"]), "admin")
        market.publish(_make_entry("a2", "A2", capabilities=["testing"]), "admin")
        results = market.search(capabilities=["code_generation"])
        assert len(results) == 1
        assert results[0].item_id == "a1"

    def test_search_excludes_non_active(self, market):
        market.publish(_make_entry("a1", "Active"), "admin")
        e = _make_entry("a2", "Pending")
        market.publish(e, "admin")
        market.submit_for_review("a2", "agent", "user")
        assert len(market.search(status="active")) == 1
        assert len(market.search(status="pending_review")) == 1
        assert len(market.search(status=None)) == 2

    def test_record_install(self, market):
        market.publish(_make_entry("a1", "A1"), "admin")
        market.record_install("a1", "agent", "user1")
        market.record_install("a1", "agent", "user2")
        assert market.get_install_count("a1", "agent") == 2

    def test_approval_workflow(self, market):
        market.publish(_make_entry("a1", "A1"), "dev")
        market.submit_for_review("a1", "agent", "dev")
        entry = market.get("a1", "agent")
        assert entry.status == "pending_review"

        market.approve("a1", "agent", "admin")
        entry = market.get("a1", "agent")
        assert entry.status == "active"

    def test_rejection_workflow(self, market):
        market.publish(_make_entry("a1", "A1"), "dev")
        market.submit_for_review("a1", "agent", "dev")
        market.reject("a1", "agent", "admin", "Missing tests")
        entry = market.get("a1", "agent")
        assert entry.status == "rejected"

    def test_publish_update(self, market):
        market.publish(_make_entry("a1", "V1", version="1.0"), "admin")
        market.publish(_make_entry("a1", "V2", version="2.0"), "admin")
        entry = market.get("a1", "agent")
        assert entry.version == "2.0"

    def test_list_all(self, market):
        market.publish(_make_entry("a1", "A1", item_type="agent"), "admin")
        market.publish(_make_entry("s1", "S1", item_type="skill"), "admin")
        assert len(market.list_all()) == 2
        assert len(market.list_all(item_type="agent")) == 1

    def test_persistence(self, tmp_path):
        db_path = tmp_path / "test.db"
        m1 = PrivateMarketplace(db_path=db_path)
        m1.publish(_make_entry("a1", "Agent A"), "admin")
        m1.record_install("a1", "agent", "user1")

        m2 = PrivateMarketplace(db_path=db_path)
        entry = m2.get("a1", "agent")
        assert entry is not None
        assert entry.install_count == 1
