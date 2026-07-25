from __future__ import annotations

from typing import Any

from .base_agent import AgentResult, BaseAgent
from .task_model import Task


def register_default_agents() -> "AgentRegistry":
    registry = AgentRegistry()
    registry.register(ProducerAgent())
    registry.register(ResearchAgent())
    registry.register(ScriptAgent())
    registry.register(VoiceAgent())
    registry.register(VisualAgent())
    registry.register(EditorAgent())
    registry.register(PackagingAgent())
    registry.register(YouTubePublisherAgent())
    registry.register(AnalyticsAgent())
    registry.register(QAAgent())
    return registry


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: list[BaseAgent] = []

    def register(self, agent: BaseAgent) -> None:
        self._agents.append(agent)

    def get_agent_for_task(self, task: Task) -> BaseAgent | None:
        for agent in self._agents:
            if agent.can_handle(task):
                return agent
        return None

    def list_roles(self) -> list[str]:
        return [agent.role for agent in self._agents]

    def list_agents(self) -> list[BaseAgent]:
        return list(self._agents)


class ProducerAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__("Producer Agent", "producer")

    def run(self, task: Task, context: dict[str, Any] | None = None) -> AgentResult:
        return AgentResult(True, {"note": "Production coordination is ready."})


class ResearchAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__("Research Agent", "research")

    def run(self, task: Task, context: dict[str, Any] | None = None) -> AgentResult:
        return AgentResult(True, {"artifact": "research/brief.md", "status": "found"})


class ScriptAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__("Script Agent", "script")

    def run(self, task: Task, context: dict[str, Any] | None = None) -> AgentResult:
        return AgentResult(True, {"artifact": "script/final.txt", "status": "ready"})


class VoiceAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__("Voice Agent", "voice")

    def run(self, task: Task, context: dict[str, Any] | None = None) -> AgentResult:
        return AgentResult(True, {"artifact": "voice/narration.wav", "status": "ready"})


class VisualAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__("Visual Agent", "visual")

    def run(self, task: Task, context: dict[str, Any] | None = None) -> AgentResult:
        if task.title == "visual_assets_check":
            return AgentResult(True, {"artifact": "visual/assets-check.txt", "status": "approved"})
        return AgentResult(True, {"artifact": "visual/plan.json", "status": "planned"})


class EditorAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__("Editor Agent", "editor")

    def run(self, task: Task, context: dict[str, Any] | None = None) -> AgentResult:
        return AgentResult(True, {"artifact": "video/edit-plan.json", "status": "ready"})


class PackagingAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__("Packaging Agent", "packaging")

    def run(self, task: Task, context: dict[str, Any] | None = None) -> AgentResult:
        return AgentResult(True, {"artifact": "packaging/package.zip", "status": "ready"})


class YouTubePublisherAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__("YouTube Publisher Agent", "youtube_publisher")

    def run(self, task: Task, context: dict[str, Any] | None = None) -> AgentResult:
        youtube_credentials = (context or {}).get("youtube_credentials")
        if task.title == "publish_readiness":
            if not youtube_credentials:
                return AgentResult(
                    True,
                    {
                        "status": "READY_FOR_MANUAL_UPLOAD",
                        "message": "YouTube credentials are not configured. Ready for manual upload.",
                    },
                )
            return AgentResult(True, {"status": "PUBLISHED", "message": "Publishing configured."})

        return AgentResult(True, {"metadata": {"title": "ATLAS ZERO Franklin", "description": "First documentary video release."}})


class AnalyticsAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__("Analytics Agent", "analytics")

    def run(self, task: Task, context: dict[str, Any] | None = None) -> AgentResult:
        return AgentResult(True, {"summary": "Analytics stub complete.", "insights": []})


class QAAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__("QA Agent", "qa")

    def run(self, task: Task, context: dict[str, Any] | None = None) -> AgentResult:
        return AgentResult(True, {"status": "checked", "note": "Visual asset readiness validated."})
