"""Tests for the Marketplace module."""

import json
import time
from pathlib import Path

import pytest

from omniagent.marketplace.models import (
    AgentPackage,
    MarketplaceEntry,
    RegistryIndex,
    Review,
)
from omniagent.marketplace.registry import LocalRegistry
from omniagent.marketplace.installer import parse_agent_toml, validate_package


# ── Models ───────────────────────────────────────────────────────────────────


class TestMarketplaceEntry:
    def test_round_trip(self):
        entry = MarketplaceEntry(
            id="test-agent",
            name="Test Agent",
            version="1.0.0",
            author="tester",
            description="A test agent",
            capabilities=["code_generation"],
            tags=["test"],
        )
        d = entry.to_dict()
        restored = MarketplaceEntry.from_dict(d)
        assert restored.id == entry.id
        assert restored.name == entry.name
        assert restored.capabilities == entry.capabilities

    def test_from_dict_defaults(self):
        entry = MarketplaceEntry.from_dict({})
        assert entry.id == ""
        assert entry.version == "0.0.0"
        assert entry.capabilities == []


class TestReview:
    def test_round_trip(self):
        review = Review(agent_id="a1", user="u1", score=4, comment="good")
        d = review.to_dict()
        restored = Review.from_dict(d)
        assert restored.agent_id == "a1"
        assert restored.score == 4


class TestAgentPackage:
    def test_to_dict(self):
        pkg = AgentPackage(id="my-agent", name="My Agent", version="1.0.0")
        d = pkg.to_dict()
        assert d["id"] == "my-agent"
        assert d["entry_point"] == "agent.py"


class TestRegistryIndex:
    def test_round_trip(self):
        idx = RegistryIndex(entries=[
            MarketplaceEntry(id="a1", name="A1", version="1.0", author="x", description="d"),
        ])
        d = idx.to_dict()
        restored = RegistryIndex.from_dict(d)
        assert len(restored.entries) == 1
        assert restored.entries[0].id == "a1"


# ── LocalRegistry ────────────────────────────────────────────────────────────


class TestLocalRegistry:
    @pytest.fixture
    def registry(self, tmp_path):
        return LocalRegistry(
            index_path=tmp_path / "index.json",
            reviews_path=tmp_path / "reviews.json",
        )

    def test_empty_search(self, registry):
        assert registry.search("anything") == []

    def test_add_and_search(self, registry):
        entry = MarketplaceEntry(
            id="code-agent", name="Code Agent", version="1.0",
            author="test", description="Generates code",
            capabilities=["code_generation"], tags=["python"],
        )
        registry.add_entry(entry)

        results = registry.search("code")
        assert len(results) == 1
        assert results[0].id == "code-agent"

    def test_search_no_match(self, registry):
        entry = MarketplaceEntry(
            id="a", name="A", version="1.0", author="x", description="desc",
        )
        registry.add_entry(entry)
        assert registry.search("nonexistent") == []

    def test_search_with_capabilities(self, registry):
        registry.add_entry(MarketplaceEntry(
            id="a1", name="A1", version="1.0", author="x", description="",
            capabilities=["code_generation"],
        ))
        registry.add_entry(MarketplaceEntry(
            id="a2", name="A2", version="1.0", author="x", description="",
            capabilities=["documentation"],
        ))
        results = registry.search("", capabilities=["code_generation"])
        assert len(results) == 1
        assert results[0].id == "a1"

    def test_get_existing(self, registry):
        entry = MarketplaceEntry(
            id="a1", name="A1", version="1.0", author="x", description="d",
        )
        registry.add_entry(entry)
        result = registry.get("a1")
        assert result is not None
        assert result.name == "A1"

    def test_get_nonexistent(self, registry):
        assert registry.get("missing") is None

    def test_list_all(self, registry):
        for i in range(3):
            registry.add_entry(MarketplaceEntry(
                id=f"a{i}", name=f"A{i}", version="1.0", author="x", description="",
            ))
        assert len(registry.list_all()) == 3

    def test_remove_entry(self, registry):
        registry.add_entry(MarketplaceEntry(
            id="a1", name="A1", version="1.0", author="x", description="",
        ))
        assert registry.remove_entry("a1") is True
        assert registry.get("a1") is None
        assert registry.remove_entry("a1") is False

    def test_persistence(self, tmp_path):
        idx_path = tmp_path / "index.json"
        r1 = LocalRegistry(index_path=idx_path)
        r1.add_entry(MarketplaceEntry(
            id="a1", name="A1", version="1.0", author="x", description="d",
        ))
        # New instance should read from file
        r2 = LocalRegistry(index_path=idx_path)
        assert r2.get("a1") is not None

    def test_add_review(self, registry):
        registry.add_review(Review(agent_id="a1", user="u1", score=4))
        reviews = registry.get_reviews("a1")
        assert len(reviews) == 1
        assert reviews[0].score == 4

    def test_rating_aggregation(self, registry):
        registry.add_review(Review(agent_id="a1", user="u1", score=4))
        registry.add_review(Review(agent_id="a1", user="u2", score=2))
        avg, count = registry.get_rating("a1")
        assert count == 2
        assert avg == 3.0

    def test_rating_updates_entry(self, registry):
        registry.add_entry(MarketplaceEntry(
            id="a1", name="A1", version="1.0", author="x", description="",
        ))
        registry.add_review(Review(agent_id="a1", user="u1", score=5))
        entry = registry.get("a1")
        assert entry is not None
        assert entry.rating == 5.0
        assert entry.rating_count == 1

    def test_get_rating_empty(self, registry):
        avg, count = registry.get_rating("nonexistent")
        assert avg == 0.0
        assert count == 0


# ── Agent.toml Parsing ───────────────────────────────────────────────────────


class TestParseAgentToml:
    def test_valid_toml(self, tmp_path):
        toml_content = """
id = "test-agent"
name = "Test Agent"
version = "1.0.0"
author = "tester"
description = "A test agent"
capabilities = ["code_generation", "testing"]
entry_point = "agent.py"
tags = ["test", "example"]
"""
        toml_path = tmp_path / "agent.toml"
        toml_path.write_text(toml_content, encoding="utf-8")

        pkg = parse_agent_toml(toml_path)
        assert pkg.id == "test-agent"
        assert pkg.name == "Test Agent"
        assert pkg.version == "1.0.0"
        assert pkg.capabilities == ["code_generation", "testing"]
        assert pkg.entry_point == "agent.py"

    def test_missing_required_field(self, tmp_path):
        toml_path = tmp_path / "agent.toml"
        toml_path.write_text('name = "No ID"\nversion = "1.0"\n', encoding="utf-8")
        with pytest.raises(ValueError, match="missing required field"):
            parse_agent_toml(toml_path)

    def test_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            parse_agent_toml(tmp_path / "missing.toml")


# ── Package Validation ───────────────────────────────────────────────────────


class TestValidatePackage:
    def test_valid_package(self, tmp_path):
        toml_content = """
id = "test-agent"
name = "Test Agent"
version = "1.0.0"
entry_point = "agent.py"
"""
        (tmp_path / "agent.toml").write_text(toml_content, encoding="utf-8")
        (tmp_path / "agent.py").write_text(
            "from omniagent.agents.base import BaseAgent\nclass MyAgent(BaseAgent): pass\n",
            encoding="utf-8",
        )
        valid, err = validate_package(tmp_path)
        assert valid is True
        assert err == ""

    def test_missing_toml(self, tmp_path):
        valid, err = validate_package(tmp_path)
        assert valid is False
        assert "agent.toml" in err

    def test_missing_entry_point(self, tmp_path):
        toml_content = 'id = "x"\nname = "X"\nversion = "1.0"\nentry_point = "main.py"\n'
        (tmp_path / "agent.toml").write_text(toml_content, encoding="utf-8")
        valid, err = validate_package(tmp_path)
        assert valid is False
        assert "Entry point" in err

    def test_no_base_agent_ref(self, tmp_path):
        toml_content = 'id = "x"\nname = "X"\nversion = "1.0"\nentry_point = "agent.py"\n'
        (tmp_path / "agent.toml").write_text(toml_content, encoding="utf-8")
        (tmp_path / "agent.py").write_text("class Foo: pass\n", encoding="utf-8")
        valid, err = validate_package(tmp_path)
        assert valid is False
        assert "BaseAgent" in err


# ── Loader ───────────────────────────────────────────────────────────────────


class TestPackageToDescriptor:
    def test_conversion(self):
        from omniagent.marketplace.loader import package_to_descriptor

        pkg = AgentPackage(
            id="test-agent", name="Test", version="1.0",
            capabilities=["code_generation", "testing"],
        )
        desc = package_to_descriptor(pkg)
        assert desc.id == "test-agent"
        assert desc.provider == "marketplace"
        from omniagent.protocol import AgentCapability
        assert AgentCapability.CODE_GENERATION in desc.capabilities
        assert AgentCapability.TESTING in desc.capabilities

    def test_unknown_capability(self):
        from omniagent.marketplace.loader import package_to_descriptor
        from omniagent.protocol import AgentCapability

        pkg = AgentPackage(id="x", name="X", version="1.0", capabilities=["unknown_cap"])
        desc = package_to_descriptor(pkg)
        assert desc.capabilities == [AgentCapability.GENERAL_PURPOSE]
