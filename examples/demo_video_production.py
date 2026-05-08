"""
Demo: Multi-Agent Collaborative Video Production.

This demonstrates OmniAgent's universality — the same orchestration system
applied to video production instead of software development.

Run: python examples/demo_video_production.py
"""

from __future__ import annotations

import asyncio
import uuid

from omniagent.core.analyzer import TaskAnalyzer
from omniagent.core.workflow import VideoProductionWorkflow
from omniagent.protocol import Task, TaskStatus


async def demo_video_production():
    """Demonstrate video production workflow with multi-agent orchestration."""
    print("=" * 60)
    print("  OmniAgent Demo: Video Production Pipeline")
    print("=" * 60)

    task = Task(
        id=str(uuid.uuid4()),
        title="Product Launch Video",
        description=(
            "Create a 3-minute product launch video for the new MiMo AI platform. "
            "Include screen recordings of key features, background music, "
            "Chinese voice-over, smooth transitions, and subtitle overlay."
        ),
        domain="video",
        workflow_template="video_production",
    )

    analyzer = TaskAnalyzer()
    analysis = analyzer.analyze(task)
    print(f"\n📋 Task Analysis:")
    print(f"   Domain: {analysis['domain']}")
    print(f"   Required: {analysis['required_capabilities']}")

    workflow = VideoProductionWorkflow()
    sub_tasks = workflow.generate_sub_tasks(task)
    print(f"\n🎬 Production Pipeline ({len(sub_tasks)} stages):")
    for st in sub_tasks:
        emoji = {
            "文案脚本": "📝",
            "素材准备": "📦",
            "视频剪辑": "✂️",
            "音频制作": "🎵",
            "转场特效": "✨",
            "审阅修改": "👀",
            "导出发布": "🚀",
        }
        stage_name = st.title.split("] ")[1] if "] " in st.title else st.title
        icon = emoji.get(stage_name, "▶️")
        print(f"   {icon} {stage_name}")
        print(f"      Required: {[c.value for c in st.required_capabilities]}")

    task.status = TaskStatus.COMPLETED
    print(f"\n✅ Video production pipeline ready!")
    print(f"   This demonstrates OmniAgent's cross-domain capability —")
    print(f"   the same orchestrator works for software AND video production.")


if __name__ == "__main__":
    asyncio.run(demo_video_production())
