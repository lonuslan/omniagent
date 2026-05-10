"""Tests for Skill ecosystem: models, parser, scanner, registry."""

import pytest
from pathlib import Path

from omniagent.skills.models import InstalledSkill, SkillManifest, SkillToolConfig
from omniagent.skills.parser import parse_skill_md, parse_skill_md_text
from omniagent.skills.scanner import SkillScanner
from omniagent.skills.registry import SkillRegistry


# ── Models ──────────────────────────────────────────────────────────────────


class TestSkillManifest:
    def test_round_trip(self):
        m = SkillManifest(
            id="code-style", name="Code Style", version="1.0.0",
            description="Enforce code style", author="test",
            tags=["python"], capabilities=["code_generation"],
            instructions="Follow PEP 8",
            triggers=["python", "pep8"],
            requirements=["read", "write"],
        )
        d = m.to_dict()
        restored = SkillManifest.from_dict(d)
        assert restored.id == "code-style"
        assert restored.name == "Code Style"
        assert restored.instructions == "Follow PEP 8"
        assert restored.triggers == ["python", "pep8"]

    def test_from_dict_minimal(self):
        m = SkillManifest.from_dict({"id": "x", "name": "X", "version": "1"})
        assert m.id == "x"
        assert m.capabilities == []
        assert m.instructions == ""

    def test_tool_config_round_trip(self):
        m = SkillManifest(
            id="t", name="T", version="1",
            tool_configs=[SkillToolConfig(tool_name="read", parameters={"max_lines": 100})],
        )
        d = m.to_dict()
        restored = SkillManifest.from_dict(d)
        assert len(restored.tool_configs) == 1
        assert restored.tool_configs[0].tool_name == "read"


# ── Parser ──────────────────────────────────────────────────────────────────


class TestSkillParser:
    def test_parse_full_skill_md(self):
        text = """---
id: code-style-python
name: Python Code Style
version: 1.0.0
author: omniagent-team
description: Enforces PEP 8 conventions
capabilities: [code_generation, code_review]
tags: [python, style, pep8]
triggers: ["python", "pep8"]
requirements: [read, write, edit]
---

## Instructions

When generating Python code, follow these rules:
1. All functions must have type hints
2. Use Google style docstrings
"""
        m = parse_skill_md_text(text)
        assert m.id == "code-style-python"
        assert m.name == "Python Code Style"
        assert m.version == "1.0.0"
        assert m.author == "omniagent-team"
        assert m.capabilities == ["code_generation", "code_review"]
        assert m.tags == ["python", "style", "pep8"]
        assert m.triggers == ["python", "pep8"]
        assert m.requirements == ["read", "write", "edit"]
        assert "PEP 8" in m.description
        assert "type hints" in m.instructions

    def test_parse_minimal_skill_md(self):
        text = """---
id: minimal
name: Minimal
version: 0.1.0
---
Just do it.
"""
        m = parse_skill_md_text(text)
        assert m.id == "minimal"
        assert m.instructions == "Just do it."

    def test_parse_no_front_matter(self):
        text = "Just some instructions without front matter."
        m = parse_skill_md_text(text)
        assert m.id == ""
        assert m.instructions == text

    def test_parse_multiline_list(self):
        text = """---
id: ml
name: Multi-line
version: 1
tags:
  - python
  - testing
  - quality
---
Body here.
"""
        m = parse_skill_md_text(text)
        assert m.tags == ["python", "testing", "quality"]

    def test_parse_booleans(self):
        text = """---
id: bool-test
name: Bool
version: 1
metadata:
  public: true
  deprecated: false
---
Done.
"""
        m = parse_skill_md_text(text)
        assert m.metadata.get("public") is True
        assert m.metadata.get("deprecated") is False

    def test_parse_file(self, tmp_path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("""---
id: file-test
name: File Test
version: 1.0.0
---
Read from file.
""", encoding="utf-8")
        m = parse_skill_md(skill_md)
        assert m.id == "file-test"
        assert m.instructions == "Read from file."


# ── Scanner ─────────────────────────────────────────────────────────────────


class TestSkillScanner:
    def test_scan_path(self, tmp_path):
        # Create two skills
        for sid in ["skill-a", "skill-b"]:
            d = tmp_path / sid
            d.mkdir()
            (d / "SKILL.md").write_text(
                f"---\nid: {sid}\nname: {sid}\nversion: 1\n---\nInstructions.",
                encoding="utf-8",
            )
        scanner = SkillScanner(search_paths=[tmp_path])
        skills = scanner.scan()
        assert len(skills) == 2
        ids = {s.manifest.id for s in skills}
        assert ids == {"skill-a", "skill-b"}

    def test_scan_empty_dir(self, tmp_path):
        scanner = SkillScanner(search_paths=[tmp_path])
        assert scanner.scan() == []

    def test_scan_nonexistent_dir(self, tmp_path):
        scanner = SkillScanner(search_paths=[tmp_path / "nope"])
        assert scanner.scan() == []

    def test_scan_skips_malformed(self, tmp_path):
        d = tmp_path / "bad-skill"
        d.mkdir()
        (d / "SKILL.md").write_text("no front matter here", encoding="utf-8")
        scanner = SkillScanner(search_paths=[tmp_path])
        # Malformed SKILL.md has no id, so it's skipped
        skills = scanner.scan()
        assert len(skills) == 0

    def test_scan_deduplicates(self, tmp_path):
        """Same skill in two paths — first one wins."""
        for base in [tmp_path / "a", tmp_path / "b"]:
            base.mkdir()
            d = base / "dup-skill"
            d.mkdir()
            (d / "SKILL.md").write_text(
                "---\nid: dup\nname: Dup\nversion: 1\n---\nBody.",
                encoding="utf-8",
            )
        scanner = SkillScanner(search_paths=[tmp_path / "a", tmp_path / "b"])
        skills = scanner.scan()
        assert len(skills) == 1


# ── Registry ────────────────────────────────────────────────────────────────


class TestSkillRegistry:
    def _make_skill(self, sid: str, caps: list[str] | None = None, triggers: list[str] | None = None) -> InstalledSkill:
        return InstalledSkill(
            manifest=SkillManifest(
                id=sid, name=sid, version="1.0.0",
                capabilities=caps or [], triggers=triggers or [],
            ),
            path=Path(f"/skills/{sid}"),
        )

    def test_register_and_get(self):
        reg = SkillRegistry()
        s = self._make_skill("a")
        reg.register(s)
        assert reg.get("a") is s
        assert reg.get("b") is None

    def test_list_all(self):
        reg = SkillRegistry()
        reg.register(self._make_skill("a"))
        reg.register(self._make_skill("b"))
        assert len(reg.list_all()) == 2

    def test_list_enabled(self):
        reg = SkillRegistry()
        reg.register(self._make_skill("a"))
        reg.register(self._make_skill("b"))
        reg.disable("b")
        enabled = reg.list_enabled()
        assert len(enabled) == 1
        assert enabled[0].manifest.id == "a"

    def test_find_by_capability(self):
        reg = SkillRegistry()
        reg.register(self._make_skill("a", caps=["code_generation"]))
        reg.register(self._make_skill("b", caps=["testing"]))
        reg.register(self._make_skill("c", caps=["code_generation", "testing"]))
        results = reg.find_by_capability(["code_generation"])
        ids = {s.manifest.id for s in results}
        assert ids == {"a", "c"}

    def test_find_by_trigger(self):
        reg = SkillRegistry()
        reg.register(self._make_skill("a", triggers=["python", "pep8"]))
        reg.register(self._make_skill("b", triggers=["javascript"]))
        results = reg.find_by_trigger("Write some python code")
        assert len(results) == 1
        assert results[0].manifest.id == "a"

    def test_find_by_trigger_disabled_excluded(self):
        reg = SkillRegistry()
        reg.register(self._make_skill("a", triggers=["python"]))
        reg.disable("a")
        assert reg.find_by_trigger("python code") == []

    def test_enable_disable(self):
        reg = SkillRegistry()
        reg.register(self._make_skill("a"))
        assert reg.disable("a") is True
        assert reg.get("a").enabled is False
        assert reg.enable("a") is True
        assert reg.get("a").enabled is True
        assert reg.enable("nonexistent") is False

    def test_unregister(self):
        reg = SkillRegistry()
        reg.register(self._make_skill("a", caps=["code_generation"]))
        reg.unregister("a")
        assert reg.get("a") is None
        assert reg.find_by_capability(["code_generation"]) == []

    def test_discover(self, tmp_path):
        d = tmp_path / "my-skill"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\nid: discovered\nname: Discovered\nversion: 1\ncapabilities: [testing]\n---\nBody.",
            encoding="utf-8",
        )
        scanner = SkillScanner(search_paths=[tmp_path])
        reg = SkillRegistry()
        reg.set_scanner(scanner)
        count = reg.discover()
        assert count == 1
        assert reg.get("discovered") is not None

    def test_to_list(self):
        reg = SkillRegistry()
        reg.register(self._make_skill("a", caps=["code_generation"]))
        lst = reg.to_list()
        assert len(lst) == 1
        assert lst[0]["id"] == "a"
        assert lst[0]["capabilities"] == ["code_generation"]
