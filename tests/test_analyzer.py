"""Tests for TaskAnalyzer."""

import pytest

from omniagent.core.analyzer import TaskAnalyzer, TaskAnalysis
from omniagent.protocol import AgentCapability, Task


def _make_task(description: str) -> Task:
    return Task(id="test-1", title="Test Task", description=description)


class TestTaskAnalyzerRuleBased:
    """Test rule-based analysis (no LLM)."""

    @pytest.fixture
    def analyzer(self):
        return TaskAnalyzer()

    async def test_software_domain(self, analyzer):
        task = _make_task("Build a React frontend with TypeScript")
        analysis = await analyzer.analyze(task)
        assert analysis.domain == "software"
        assert isinstance(analysis, TaskAnalysis)

    async def test_video_domain(self, analyzer):
        task = _make_task("Edit this video with transitions and subtitles")
        analysis = await analyzer.analyze(task)
        assert analysis.domain == "video"

    async def test_document_domain(self, analyzer):
        task = _make_task("Write a blog article about AI")
        analysis = await analyzer.analyze(task)
        assert analysis.domain == "document"

    async def test_data_domain(self, analyzer):
        task = _make_task("Analyze sales data and create statistics charts")
        analysis = await analyzer.analyze(task)
        assert analysis.domain == "data"

    async def test_general_domain_fallback(self, analyzer):
        task = _make_task("Help me organize my schedule")
        analysis = await analyzer.analyze(task)
        assert analysis.domain == "general"

    async def test_analysis_has_stages(self, analyzer):
        task = _make_task("Build a full-stack web application")
        analysis = await analyzer.analyze(task)
        assert len(analysis.suggested_stages) > 0

    async def test_analysis_has_capabilities(self, analyzer):
        task = _make_task("Develop and deploy a Python API")
        analysis = await analyzer.analyze(task)
        assert len(analysis.required_capabilities) > 0

    async def test_analysis_dataclass_fields(self, analyzer):
        task = _make_task("Create a mobile app")
        analysis = await analyzer.analyze(task)
        assert hasattr(analysis, "domain")
        assert hasattr(analysis, "sub_domain")
        assert hasattr(analysis, "summary")
        assert hasattr(analysis, "tech_stack")
        assert hasattr(analysis, "features")
        assert hasattr(analysis, "complexity")
        assert hasattr(analysis, "suggested_stages")
        assert hasattr(analysis, "risks")


class TestTaskAnalyzerSync:
    def test_analyze_sync(self):
        analyzer = TaskAnalyzer()
        task = _make_task("Build a Python REST API")
        analysis = analyzer.analyze_sync(task)
        assert isinstance(analysis, TaskAnalysis)
        assert analysis.domain == "software"


class TestTaskAnalyzerExtractJson:
    def test_extract_plain_json(self):
        analyzer = TaskAnalyzer()
        data = analyzer._extract_json('{"domain": "software"}')
        assert data == {"domain": "software"}

    def test_extract_json_from_code_block(self):
        analyzer = TaskAnalyzer()
        text = '```json\n{"domain": "video"}\n```'
        data = analyzer._extract_json(text)
        assert data == {"domain": "video"}

    def test_extract_json_from_code_block_no_lang(self):
        analyzer = TaskAnalyzer()
        text = '```\n{"domain": "data"}\n```'
        data = analyzer._extract_json(text)
        assert data == {"domain": "data"}
