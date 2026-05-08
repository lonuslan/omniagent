"""
LLM-powered TaskAnalyzer — semantic task understanding.

Replaces keyword matching with structured LLM analysis.
Extracts: domain, tech stack, features, constraints, complexity,
and generates a tailored execution plan.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from ..llm.types import LLMRequest, Message, MessageRole, ToolDef
from ..protocol import AgentCapability, SubTask, Task


@dataclass
class TaskAnalysis:
    """Structured result of task analysis."""
    domain: str
    sub_domain: str = ""                    # e.g. "web_frontend", "mobile_app"
    summary: str = ""                       # One-sentence summary
    tech_stack: list[str] = field(default_factory=list)
    features: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    complexity: str = "medium"              # low/medium/high
    required_capabilities: list[AgentCapability] = field(default_factory=list)
    suggested_stages: list[dict[str, Any]] = field(default_factory=list)
    estimated_effort: str = "unknown"
    risks: list[str] = field(default_factory=list)


# Analysis prompt template
ANALYSIS_SYSTEM_PROMPT = """You are a technical project analyst. Analyze user task descriptions and return structured JSON.

Output ONLY valid JSON with these fields:
{
  "domain": "software" | "video" | "document" | "data" | "general",
  "sub_domain": "specific area like web_frontend, mobile_app, api_backend, etc",
  "summary": "one sentence describing what needs to be built",
  "tech_stack": ["list", "of", "technologies", "mentioned"],
  "features": ["key", "features", "requested"],
  "constraints": ["any", "constraints", "mentioned"],
  "complexity": "low" | "medium" | "high",
  "required_capabilities": ["subset of: code_generation, architecture_design, code_review, testing, deployment, ui_design, prototype_design, documentation, copywriting, video_editing, audio_production, data_analysis, general_purpose"],
  "suggested_stages": [
    {"name": "Stage name in user's language", "description": "what this stage does", "capabilities": ["capability1"], "estimated_duration": "short|medium|long"}
  ],
  "estimated_effort": "rough time estimate",
  "risks": ["potential", "risks"]
}

IMPORTANT:
- suggested_stages should reflect a realistic workflow for the task
- For software tasks, include stages like: requirements, design, implementation, testing, deployment
- For video tasks: scripting, footage, editing, audio, review, export
- Capabilities must be from the list above
- Keep stage names concise (2-4 words)"""


class TaskAnalyzer:
    """
    Semantic task analyzer with dual-mode operation:

    - LLM mode: Uses an LLM provider for deep semantic analysis
    - Rule mode: Falls back to keyword matching when no LLM is available

    The LLM mode extracts structured analysis including domain, tech stack,
    features, and generates a tailored stage-by-stage execution plan.
    """

    def __init__(self, llm_provider: Any = None) -> None:
        self._llm = llm_provider

    async def analyze(self, task: Task) -> TaskAnalysis:
        """Analyze a task. Uses LLM if available, otherwise falls back to rules."""
        if self._llm:
            try:
                return await self._analyze_with_llm(task)
            except Exception:
                pass
        return self._analyze_with_rules(task)

    def analyze_sync(self, task: Task) -> TaskAnalysis:
        """Synchronous analysis using rules only (for demos)."""
        return self._analyze_with_rules(task)

    # ── LLM Analysis ─────────────────────────────────────────────────────

    async def _analyze_with_llm(self, task: Task) -> TaskAnalysis:
        request = LLMRequest(
            messages=[
                Message(role=MessageRole.SYSTEM, content=ANALYSIS_SYSTEM_PROMPT),
                Message(role=MessageRole.USER, content=task.description),
            ],
            max_tokens=1024,
            temperature=0.3,
        )

        completion = await self._llm.complete(request)

        # Parse JSON from response
        data = self._extract_json(completion.content)
        return self._parse_analysis(data)

    def _extract_json(self, text: str) -> dict[str, Any]:
        """Extract JSON from LLM response, handling markdown code blocks."""
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = lines[1:] if lines[0].startswith("```") else lines
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        return json.loads(text)

    def _parse_analysis(self, data: dict[str, Any]) -> TaskAnalysis:
        caps = []
        for c in data.get("required_capabilities", []):
            try:
                caps.append(AgentCapability(c))
            except ValueError:
                pass

        return TaskAnalysis(
            domain=data.get("domain", "general"),
            sub_domain=data.get("sub_domain", ""),
            summary=data.get("summary", ""),
            tech_stack=data.get("tech_stack", []),
            features=data.get("features", []),
            constraints=data.get("constraints", []),
            complexity=data.get("complexity", "medium"),
            required_capabilities=caps,
            suggested_stages=data.get("suggested_stages", []),
            estimated_effort=data.get("estimated_effort", "unknown"),
            risks=data.get("risks", []),
        )

    # ── Rule-based Fallback ──────────────────────────────────────────────

    DOMAIN_KEYWORDS: dict[str, list[str]] = {
        "software": ["code", "develop", "frontend", "backend", "api", "bug", "deploy",
                      "react", "python", "database", "app", "web", "build"],
        "video": ["video", "edit", "transition", "subtitle", "clip", "audio", "footage"],
        "document": ["document", "report", "article", "write", "blog", "docs"],
        "data": ["data", "analysis", "statistics", "chart", "report", "visualize"],
    }

    DOMAIN_CAPABILITIES: dict[str, list[AgentCapability]] = {
        "software": [
            AgentCapability.ARCHITECTURE_DESIGN, AgentCapability.CODE_GENERATION,
            AgentCapability.CODE_REVIEW, AgentCapability.TESTING, AgentCapability.DEPLOYMENT,
        ],
        "video": [
            AgentCapability.VIDEO_EDITING, AgentCapability.AUDIO_PRODUCTION,
            AgentCapability.COPYWRITING,
        ],
        "document": [AgentCapability.COPYWRITING, AgentCapability.DOCUMENTATION],
        "data": [AgentCapability.DATA_ANALYSIS],
    }

    DOMAIN_STAGES: dict[str, list[dict[str, Any]]] = {
        "software": [
            {"name": "需求确认", "description": "Clarify requirements with user", "capabilities": ["general_purpose"]},
            {"name": "需求分析", "description": "Technical analysis and spec", "capabilities": ["architecture_design"]},
            {"name": "原型设计", "description": "UI/UX wireframes", "capabilities": ["ui_design", "prototype_design"]},
            {"name": "前端开发", "description": "Frontend implementation", "capabilities": ["code_generation"]},
            {"name": "后端开发", "description": "Backend API implementation", "capabilities": ["code_generation"]},
            {"name": "测试", "description": "Testing and review", "capabilities": ["testing", "code_review"]},
            {"name": "部署上线", "description": "Deploy to production", "capabilities": ["deployment"]},
        ],
        "video": [
            {"name": "文案脚本", "description": "Script writing", "capabilities": ["copywriting"]},
            {"name": "素材准备", "description": "Collect assets", "capabilities": ["general_purpose"]},
            {"name": "视频剪辑", "description": "Edit timeline", "capabilities": ["video_editing"]},
            {"name": "音频制作", "description": "Voice & music", "capabilities": ["audio_production"]},
            {"name": "转场特效", "description": "Transitions & effects", "capabilities": ["video_editing"]},
            {"name": "审阅修改", "description": "Review & revise", "capabilities": ["general_purpose"]},
        ],
        "document": [
            {"name": "大纲规划", "description": "Outline structure", "capabilities": ["copywriting"]},
            {"name": "初稿撰写", "description": "First draft", "capabilities": ["copywriting"]},
            {"name": "审阅修订", "description": "Review & edit", "capabilities": ["documentation"]},
            {"name": "定稿发布", "description": "Finalize", "capabilities": ["documentation"]},
        ],
        "data": [
            {"name": "数据采集", "description": "Collect data", "capabilities": ["data_analysis"]},
            {"name": "数据清洗", "description": "Clean data", "capabilities": ["data_analysis"]},
            {"name": "分析建模", "description": "Analysis & modeling", "capabilities": ["data_analysis"]},
            {"name": "可视化", "description": "Visualize results", "capabilities": ["data_analysis"]},
        ],
    }

    def _analyze_with_rules(self, task: Task) -> TaskAnalysis:
        domain = self._detect_domain(task.description)
        caps = self.DOMAIN_CAPABILITIES.get(domain, [AgentCapability.GENERAL_PURPOSE])
        stages = self.DOMAIN_STAGES.get(domain, [])
        return TaskAnalysis(
            domain=domain,
            summary=task.title,
            required_capabilities=caps,
            suggested_stages=stages,
            complexity="medium",
        )

    def _detect_domain(self, description: str) -> str:
        text = description.lower()
        scores: dict[str, int] = {}
        for domain, keywords in self.DOMAIN_KEYWORDS.items():
            scores[domain] = sum(1 for kw in keywords if kw in text)
        return max(scores, key=scores.get) if max(scores.values()) > 0 else "general"
