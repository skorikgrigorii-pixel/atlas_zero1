from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Mapping, MutableMapping

@dataclass
class ProjectContext:
    project_id: str
    profile: str = "balanced"
    project: MutableMapping[str, Any] = field(default_factory=dict)
    timeline: MutableMapping[str, Any] = field(default_factory=dict)
    assets: list[dict[str, Any]] = field(default_factory=list)
    settings: MutableMapping[str, Any] = field(default_factory=dict)
    results: MutableMapping[str, Any] = field(default_factory=dict)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)

    def require(self, key: str) -> Any:
        if key not in self.results:
            raise KeyError(f"Required context result is missing: {key}")
        return self.results[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.results.get(key, default)

    def publish(self, key: str, value: Any, *, overwrite: bool = True) -> None:
        if not overwrite and key in self.results:
            raise KeyError(f"Context result already exists: {key}")
        self.results[key] = value

    def publish_many(self, values: Mapping[str, Any], *, overwrite: bool = True) -> None:
        for key, value in values.items():
            self.publish(key, value, overwrite=overwrite)

    def add_diagnostic(self, event: Mapping[str, Any]) -> None:
        self.diagnostics.append(dict(event))

    def snapshot(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "profile": self.profile,
            "project": dict(self.project),
            "timeline": dict(self.timeline),
            "assets": [dict(item) for item in self.assets],
            "settings": dict(self.settings),
            "results": dict(self.results),
            "diagnostics": [dict(item) for item in self.diagnostics],
        }
