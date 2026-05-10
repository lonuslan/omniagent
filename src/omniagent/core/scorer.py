"""
Agent Scorer — Composite scoring for intelligent agent selection.

Combines three scoring dimensions:
  1. Capability Match — exact enum matching (existing algorithm)
  2. LLM Semantic Score — LLM rates agent-task fit (0-10)
  3. Reputation Score — execution history success rate + marketplace rating

Final score = capability * 0.4 + llm * 0.35 + reputation * 0.25
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..protocol import AgentCapability, AgentDescriptor
from .registry import capability_match_score

STATS_PATH = Path.home() / ".omniagent" / "stats.json"


@dataclass
class AgentStatsEntry:
    """Per-agent execution statistics."""
    agent_id: str
    total_tasks: int = 0
    successful: int = 0
    failed: int = 0
    total_duration_ms: float = 0.0
    last_used: float = 0.0
    marketplace_rating: float = 0.0  # 0-5 scale from marketplace reviews

    @property
    def success_rate(self) -> float:
        if self.total_tasks == 0:
            return 0.5  # neutral prior
        return self.successful / self.total_tasks

    @property
    def avg_duration_ms(self) -> float:
        if self.total_tasks == 0:
            return 0.0
        return self.total_duration_ms / self.total_tasks

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "total_tasks": self.total_tasks,
            "successful": self.successful,
            "failed": self.failed,
            "total_duration_ms": self.total_duration_ms,
            "last_used": self.last_used,
            "marketplace_rating": self.marketplace_rating,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentStatsEntry:
        return cls(
            agent_id=data.get("agent_id", ""),
            total_tasks=data.get("total_tasks", 0),
            successful=data.get("successful", 0),
            failed=data.get("failed", 0),
            total_duration_ms=data.get("total_duration_ms", 0.0),
            last_used=data.get("last_used", 0.0),
            marketplace_rating=data.get("marketplace_rating", 0.0),
        )


@dataclass
class ScoreBreakdown:
    """Detailed breakdown of how an agent was scored."""
    agent_id: str
    agent_name: str
    capability_score: float = 0.0
    llm_score: float = 0.0
    reputation_score: float = 0.0
    composite_score: float = 0.0
    llm_reasoning: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "capability": round(self.capability_score, 3),
            "llm": round(self.llm_score, 3),
            "reputation": round(self.reputation_score, 3),
            "composite": round(self.composite_score, 3),
            "reasoning": self.llm_reasoning,
        }


class AgentScorer:
    """
    Composite agent scorer combining capability matching, LLM semantic scoring,
    and reputation-based ranking.
    """

    # Weights for composite score
    W_CAPABILITY = 0.40
    W_LLM = 0.35
    W_REPUTATION = 0.25

    def __init__(self, llm_bridge: Any = None, stats_path: Path | None = None) -> None:
        self._llm_bridge = llm_bridge
        self._stats_path = stats_path or STATS_PATH
        self._stats: dict[str, AgentStatsEntry] = {}
        self._load_stats()

    # ── Stats Persistence ─────────────────────────────────────────────

    def _load_stats(self) -> None:
        if self._stats_path.exists():
            try:
                data = json.loads(self._stats_path.read_text(encoding="utf-8"))
                for entry_data in data.get("agents", []):
                    entry = AgentStatsEntry.from_dict(entry_data)
                    self._stats[entry.agent_id] = entry
            except Exception:
                pass

    def _save_stats(self) -> None:
        self._stats_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": 1,
            "agents": [e.to_dict() for e in self._stats.values()],
        }
        self._stats_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def get_stats(self, agent_id: str) -> AgentStatsEntry:
        if agent_id not in self._stats:
            self._stats[agent_id] = AgentStatsEntry(agent_id=agent_id)
        return self._stats[agent_id]

    # ── Record Execution ──────────────────────────────────────────────

    def record_success(self, agent_id: str, duration_ms: float = 0.0) -> None:
        stats = self.get_stats(agent_id)
        stats.total_tasks += 1
        stats.successful += 1
        stats.total_duration_ms += duration_ms
        stats.last_used = time.time()
        self._save_stats()

    def record_failure(self, agent_id: str, duration_ms: float = 0.0) -> None:
        stats = self.get_stats(agent_id)
        stats.total_tasks += 1
        stats.failed += 1
        stats.total_duration_ms += duration_ms
        stats.last_used = time.time()
        self._save_stats()

    def update_marketplace_rating(self, agent_id: str, rating: float) -> None:
        stats = self.get_stats(agent_id)
        stats.marketplace_rating = max(0.0, min(5.0, rating))
        self._save_stats()

    # ── Scoring ───────────────────────────────────────────────────────

    def capability_score(
        self,
        required: list[AgentCapability],
        offered: list[AgentCapability],
    ) -> float:
        """Existing capability match algorithm (0.0 - 1.0)."""
        return capability_match_score(required, offered)

    def llm_score(self, task_description: str, agent: AgentDescriptor) -> tuple[float, str]:
        """
        Ask LLM to rate how well this agent fits the task (0.0 - 1.0).
        Returns (score, reasoning). Falls back to 0.5 if no LLM available.
        """
        if not self._llm_bridge or not self._llm_bridge.is_configured():
            return 0.5, "No LLM configured, using neutral score"

        caps_str = ", ".join(c.value for c in agent.capabilities)
        prompt = f"""Rate how well this agent fits the task on a scale of 0-10.

Task: {task_description[:500]}

Agent: {agent.name}
Description: {agent.description}
Capabilities: {caps_str}

Reply with ONLY a JSON object: {{"score": <0-10>, "reason": "<one sentence>"}}"""

        try:
            result = self._llm_bridge.complete_sync(
                model=self._llm_bridge._active_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150,
                temperature=0.1,
            )
            content = result.get("content", "") if isinstance(result, dict) else str(result)
            if result.get("error"):
                return 0.5, f"LLM error: {result['error']}"

            # Parse JSON response
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                data = json.loads(content[json_start:json_end])
                raw_score = data.get("score", 5)
                reasoning = data.get("reason", "")
                return min(1.0, max(0.0, raw_score / 10.0)), reasoning
        except Exception:
            pass

        return 0.5, "LLM scoring failed, using neutral score"

    def reputation_score(self, agent_id: str) -> float:
        """
        Compute reputation from execution history + marketplace rating.
        Returns 0.0 - 1.0.
        """
        stats = self.get_stats(agent_id)

        # Execution history component (0-1)
        history_score = stats.success_rate

        # Marketplace rating component (0-5 → 0-1)
        marketplace_score = stats.marketplace_rating / 5.0 if stats.marketplace_rating > 0 else 0.5

        # Blend: 70% history, 30% marketplace (if marketplace data exists)
        if stats.marketplace_rating > 0 and stats.total_tasks > 0:
            return history_score * 0.7 + marketplace_score * 0.3
        elif stats.total_tasks > 0:
            return history_score
        elif stats.marketplace_rating > 0:
            return marketplace_score
        else:
            return 0.5  # no data, neutral prior

    def composite_score(
        self,
        task_description: str,
        agent: AgentDescriptor,
        required_caps: list[AgentCapability],
        use_llm: bool = True,
    ) -> ScoreBreakdown:
        """
        Compute the full composite score for an agent on a task.
        Returns ScoreBreakdown with all components.
        """
        cap_score = self.capability_score(required_caps, agent.capabilities)

        if use_llm:
            llm_s, llm_reason = self.llm_score(task_description, agent)
        else:
            llm_s, llm_reason = 0.5, "LLM scoring disabled"

        rep_score = self.reputation_score(agent.id)

        composite = (
            cap_score * self.W_CAPABILITY
            + llm_s * self.W_LLM
            + rep_score * self.W_REPUTATION
        )

        return ScoreBreakdown(
            agent_id=agent.id,
            agent_name=agent.name,
            capability_score=cap_score,
            llm_score=llm_s,
            reputation_score=rep_score,
            composite_score=composite,
            llm_reasoning=llm_reason,
        )

    # ── Ranking ───────────────────────────────────────────────────────

    def rank_agents(
        self,
        task_description: str,
        candidates: list[AgentDescriptor],
        required_caps: list[AgentCapability],
        use_llm: bool = True,
    ) -> list[ScoreBreakdown]:
        """
        Rank all candidate agents by composite score.
        Returns sorted list (best first) with full score breakdown.
        """
        # Batch LLM scoring: one prompt for all candidates to reduce latency
        llm_scores: dict[str, tuple[float, str]] = {}
        if use_llm and self._llm_bridge and self._llm_bridge.is_configured() and len(candidates) > 1:
            llm_scores = self._batch_llm_score(task_description, candidates)

        results = []
        for agent in candidates:
            if agent.id in llm_scores:
                llm_s, llm_reason = llm_scores[agent.id]
                cap_score = self.capability_score(required_caps, agent.capabilities)
                rep_score = self.reputation_score(agent.id)
                composite = (
                    cap_score * self.W_CAPABILITY
                    + llm_s * self.W_LLM
                    + rep_score * self.W_REPUTATION
                )
                results.append(ScoreBreakdown(
                    agent_id=agent.id,
                    agent_name=agent.name,
                    capability_score=cap_score,
                    llm_score=llm_s,
                    reputation_score=rep_score,
                    composite_score=composite,
                    llm_reasoning=llm_reason,
                ))
            else:
                results.append(self.composite_score(
                    task_description, agent, required_caps, use_llm=use_llm
                ))

        results.sort(key=lambda x: x.composite_score, reverse=True)
        return results

    def _batch_llm_score(
        self,
        task_description: str,
        candidates: list[AgentDescriptor],
    ) -> dict[str, tuple[float, str]]:
        """
        Score all candidates in a single LLM call to reduce latency.
        Returns {agent_id: (score, reasoning)}.
        """
        agent_lines = []
        for i, a in enumerate(candidates):
            caps = ", ".join(c.value for c in a.capabilities)
            agent_lines.append(f"{i+1}. {a.name} — {a.description} [capabilities: {caps}]")

        prompt = f"""Rate how well each agent fits this task. Score 0-10 for each.

Task: {task_description[:400]}

Agents:
{chr(10).join(agent_lines)}

Reply with ONLY a JSON array: [{{"id": "<agent-id>", "score": <0-10>, "reason": "<brief>"}}]"""

        try:
            result = self._llm_bridge.complete_sync(
                model=self._llm_bridge._active_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.1,
            )
            content = result.get("content", "") if isinstance(result, dict) else str(result)
            if result.get("error"):
                return {}

            json_start = content.find("[")
            json_end = content.rfind("]") + 1
            if json_start >= 0 and json_end > json_start:
                data = json.loads(content[json_start:json_end])
                scores = {}
                for item in data:
                    agent_id = item.get("id", "")
                    # Match by name if ID doesn't match directly
                    if not any(a.id == agent_id for a in candidates):
                        for a in candidates:
                            if a.name.lower().startswith(agent_id.lower()) or agent_id.lower() in a.name.lower():
                                agent_id = a.id
                                break
                    score = min(1.0, max(0.0, item.get("score", 5) / 10.0))
                    reason = item.get("reason", "")
                    scores[agent_id] = (score, reason)
                return scores
        except Exception:
            pass

        return {}
