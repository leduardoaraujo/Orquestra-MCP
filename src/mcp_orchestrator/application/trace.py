from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from mcp_orchestrator.domain.models import OrchestrationTrace, OrchestrationTraceStage


class OrchestrationTraceRecorder:
    def __init__(self, request_id: str) -> None:
        self.trace = OrchestrationTrace(request_id=request_id)
        self._active: dict[str, tuple[int, float]] = {}

    def start_stage(self, name: str, details: dict[str, Any] | None = None) -> None:
        self.trace.stages.append(
            OrchestrationTraceStage(
                name=name,
                started_at=datetime.now(UTC),
                details=details or {},
            )
        )
        self._active[name] = (len(self.trace.stages) - 1, perf_counter())

    def end_stage(
        self,
        name: str,
        *,
        status: str = "success",
        details: dict[str, Any] | None = None,
    ) -> float:
        index, started_at = self._active.pop(name)
        duration_ms = (perf_counter() - started_at) * 1000
        stage = self.trace.stages[index]
        stage.completed_at = datetime.now(UTC)
        stage.duration_ms = round(duration_ms, 3)
        stage.status = status
        if details:
            stage.details.update(details)
        return duration_ms

    def complete(self) -> OrchestrationTrace:
        self.trace.completed_at = datetime.now(UTC)
        return self.trace
