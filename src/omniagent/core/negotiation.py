"""
Agent Negotiation Protocol — Structured debate with LLM arbitration.

When two agents disagree on an approach, they engage in a structured debate:
  1. Proposal A — Agent A presents its approach with reasoning
  2. Proposal B — Agent B presents its alternative with reasoning
  3. Rebuttal A — Agent A critiques B's proposal
  4. Rebuttal B — Agent B critiques A's proposal
  5. Arbitration — LLM evaluates all arguments and selects the winner

This is the implementation of Hard Problem 3 from the development plan.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DebateProposal:
    """A single agent's proposal in a debate."""
    agent_id: str
    agent_name: str
    position: str  # The proposed approach
    reasoning: str  # Why this approach is better
    evidence: list[str] = field(default_factory=list)  # Supporting evidence


@dataclass
class DebateRound:
    """One round of the debate (proposal + rebuttal)."""
    proposal: DebateProposal
    rebuttal: str = ""  # Critique of the opponent's proposal


@dataclass
class ArbitrationResult:
    """The outcome of LLM arbitration."""
    winner_id: str
    winner_name: str
    reasoning: str  # Why the arbitrator chose this winner
    confidence: float  # 0.0-1.0, how confident the arbitrator is
    merged_approach: str = ""  # Optional: best elements from both proposals


@dataclass
class NegotiationResult:
    """Complete result of a negotiation."""
    topic: str
    rounds: list[DebateRound]
    arbitration: ArbitrationResult
    all_proposals: list[DebateProposal]


class NegotiationProtocol:
    """
    Manages structured debates between agents with LLM arbitration.

    Usage:
        protocol = NegotiationProtocol(llm_bridge)
        result = await protocol.negotiate(topic, proposals)
    """

    def __init__(self, llm_bridge: Any = None) -> None:
        self._llm_bridge = llm_bridge

    def negotiate(
        self,
        topic: str,
        proposals: list[DebateProposal],
        context: str = "",
    ) -> NegotiationResult:
        """
        Run a structured negotiation between 2+ proposals.
        Returns the arbitration result with the winning approach.
        """
        if len(proposals) < 2:
            # No disagreement — single proposal wins by default
            p = proposals[0] if proposals else DebateProposal(
                agent_id="default", agent_name="Default", position="No proposal", reasoning=""
            )
            return NegotiationResult(
                topic=topic,
                rounds=[],
                arbitration=ArbitrationResult(
                    winner_id=p.agent_id,
                    winner_name=p.agent_name,
                    reasoning="Only one proposal submitted",
                    confidence=1.0,
                ),
                all_proposals=proposals,
            )

        # Use first two proposals for structured debate (extend for multi-party later)
        a, b = proposals[0], proposals[1]

        # Generate rebuttals via LLM
        rebuttal_a = self._generate_rebuttal(topic, a, b, context)
        rebuttal_b = self._generate_rebuttal(topic, b, a, context)

        rounds = [
            DebateRound(proposal=a, rebuttal=rebuttal_a),
            DebateRound(proposal=b, rebuttal=rebuttal_b),
        ]

        # LLM arbitration
        arbitration = self._arbitrate(topic, rounds, context)

        return NegotiationResult(
            topic=topic,
            rounds=rounds,
            arbitration=arbitration,
            all_proposals=proposals,
        )

    def _generate_rebuttal(
        self,
        topic: str,
        critic: DebateProposal,
        target: DebateProposal,
        context: str,
    ) -> str:
        """Use LLM to generate a rebuttal from the critic's perspective."""
        if not self._llm_bridge or not self._llm_bridge.is_configured():
            return f"{critic.agent_name} disagrees with {target.agent_name}'s approach but cannot elaborate (no LLM)."

        prompt = f"""You are role-playing as Agent "{critic.agent_name}" in a technical debate.

Topic: {topic}
Context: {context[:500]}

Your proposal: {critic.position}
Your reasoning: {critic.reasoning}

Opponent's proposal: {target.position}
Opponent's reasoning: {target.reasoning}

Write a concise rebuttal (2-3 sentences) critiquing the opponent's approach from your perspective.
Focus on concrete weaknesses, missing considerations, or risks. Be specific."""

        try:
            result = self._llm_bridge.complete_sync(
                model=self._llm_bridge._active_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.3,
            )
            content = result.get("content", "") if isinstance(result, dict) else str(result)
            if result.get("error"):
                return f"{critic.agent_name} challenges {target.agent_name}'s approach."
            return content.strip()
        except Exception:
            return f"{critic.agent_name} challenges {target.agent_name}'s approach."

    def _arbitrate(
        self,
        topic: str,
        rounds: list[DebateRound],
        context: str,
    ) -> ArbitrationResult:
        """Use LLM as an impartial judge to evaluate the debate."""
        if not self._llm_bridge or not self._llm_bridge.is_configured():
            # Default to first proposal
            winner = rounds[0].proposal
            return ArbitrationResult(
                winner_id=winner.agent_id,
                winner_name=winner.agent_name,
                reasoning="No LLM available for arbitration, defaulting to first proposal",
                confidence=0.5,
            )

        debate_text = ""
        for i, r in enumerate(rounds):
            p = r.proposal
            debate_text += f"\n--- Proposal {i+1}: {p.agent_name} ---\n"
            debate_text += f"Position: {p.position}\n"
            debate_text += f"Reasoning: {p.reasoning}\n"
            if r.rebuttal:
                debate_text += f"Rebuttal: {r.rebuttal}\n"

        prompt = f"""You are an impartial technical judge evaluating a debate between agents.

Topic: {topic}
Context: {context[:400]}

{debate_text}

Evaluate both proposals. Consider: feasibility, risk, alignment with the task, and strength of arguments.

Reply with ONLY a JSON object:
{{"winner": "<agent-name>", "confidence": <0.0-1.0>, "reasoning": "<2-3 sentences explaining your decision>", "merged_approach": "<optional: combine best elements from both>"}}"""

        try:
            result = self._llm_bridge.complete_sync(
                model=self._llm_bridge._active_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
                temperature=0.1,
            )
            content = result.get("content", "") if isinstance(result, dict) else str(result)
            if result.get("error"):
                raise Exception(result["error"])

            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                data = json.loads(content[json_start:json_end])
                winner_name = data.get("winner", "")
                # Match winner name to proposal
                winner_proposal = rounds[0].proposal
                for r in rounds:
                    if r.proposal.agent_name.lower() in winner_name.lower() or winner_name.lower() in r.proposal.agent_name.lower():
                        winner_proposal = r.proposal
                        break
                return ArbitrationResult(
                    winner_id=winner_proposal.agent_id,
                    winner_name=winner_proposal.agent_name,
                    reasoning=data.get("reasoning", "Arbitrator selected this proposal"),
                    confidence=min(1.0, max(0.0, data.get("confidence", 0.7))),
                    merged_approach=data.get("merged_approach", ""),
                )
        except Exception:
            pass

        # Fallback
        winner = rounds[0].proposal
        return ArbitrationResult(
            winner_id=winner.agent_id,
            winner_name=winner.agent_name,
            reasoning="Arbitration failed, defaulting to first proposal",
            confidence=0.5,
        )
