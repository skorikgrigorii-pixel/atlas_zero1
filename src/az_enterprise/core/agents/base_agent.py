from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from .task_model import Task


@dataclass
class AgentResult:
    success: bool
    output_data: dict[str, Any] = None
    error: str | None = None
    status: str = "COMPLETED"

    def __post_init__(self):
        if self.output_data is None:
            self.output_data = {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "status": self.status,
            "output_data": self.output_data,
            "error": self.error,
        }


class BaseAgent(ABC):
    def __init__(self, name: str, role: str):
        self.name = name
        self.role = role
        self._last_status: str = "IDLE"
        self._last_error: str | None = None

    def can_handle(self, task: Task) -> bool:
        return task.agent_role == self.role

    @abstractmethod
    def run(self, task: Task, context: dict[str, Any] | None = None) -> AgentResult:
        raise NotImplementedError

    def status(self) -> str:
        return self._last_status

    def error(self) -> str | None:
        return self._last_error
