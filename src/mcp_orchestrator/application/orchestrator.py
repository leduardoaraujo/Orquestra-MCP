from __future__ import annotations

from uuid import uuid4

from mcp_orchestrator.config import Settings
from mcp_orchestrator.domain.models import (
    McpToolCallResponse,
    McpToolDefinition,
    NormalizedResponse,
    UserRequest,
)
from mcp_orchestrator.domain.ports import (
    ContextComposer,
    ContextRetriever,
    ExecutionPolicyService,
    RequestUnderstandingService,
    ResponseNormalizer,
)
from mcp_orchestrator.infrastructure.context import LocalContextRetriever
from mcp_orchestrator.infrastructure.mcp_clients import DefaultMcpClientRegistry
from mcp_orchestrator.infrastructure.mcp_servers import LocalMcpServerCatalog, StdioMcpToolRunner
from mcp_orchestrator.normalization import DefaultResponseNormalizer
from mcp_orchestrator.observability import TimingRecorder, get_logger, log_stage

from .composer import DefaultContextComposer
from .intake import HeuristicRequestUnderstandingService
from .policy import DefaultExecutionPolicyService
from .routing import ExecutionRouter
from .trace import OrchestrationTraceRecorder


class OrchestrationService:
    def __init__(
        self,
        *,
        understanding_service: RequestUnderstandingService | None = None,
        interpreter: RequestUnderstandingService | None = None,
        retriever: ContextRetriever,
        composer: ContextComposer,
        policy_service: ExecutionPolicyService | None = None,
        router: ExecutionRouter,
        normalizer: ResponseNormalizer,
        server_catalog: LocalMcpServerCatalog,
        tool_runner: StdioMcpToolRunner,
        rag_top_k: int,
    ) -> None:
        self.understanding_service = understanding_service or interpreter
        if self.understanding_service is None:
            raise ValueError("understanding_service is required.")
        self.retriever = retriever
        self.composer = composer
        self.policy_service = policy_service or DefaultExecutionPolicyService()
        self.router = router
        self.normalizer = normalizer
        self.server_catalog = server_catalog
        self.tool_runner = tool_runner
        self.rag_top_k = rag_top_k
        self.logger = get_logger(__name__)

    async def orchestrate(self, request: UserRequest) -> NormalizedResponse:
        correlation_id = str(uuid4())
        timing = TimingRecorder()
        trace_recorder = OrchestrationTraceRecorder(correlation_id)

        trace_recorder.start_stage("intake")
        started_at = timing.start()
        understanding = self.understanding_service.understand(request)
        self._record_stage(trace_recorder, correlation_id, "intake", timing, started_at)

        trace_recorder.start_stage("context_retrieval")
        started_at = timing.start()
        retrieved_context = self.retriever.retrieve(
            request.message,
            filters=self._context_filters(request, understanding),
            limit=self.rag_top_k,
        )
        trace_recorder.trace.retrieved_context_sources = list(
            dict.fromkeys(item.source_path for item in retrieved_context.items)
        )
        self._record_stage(
            trace_recorder,
            correlation_id,
            "context_retrieval",
            timing,
            started_at,
            {"source_count": len(trace_recorder.trace.retrieved_context_sources)},
        )

        trace_recorder.start_stage("compose")
        started_at = timing.start()
        enriched = self.composer.compose(correlation_id, request, understanding, retrieved_context)
        self._record_stage(trace_recorder, correlation_id, "compose", timing, started_at)

        trace_recorder.start_stage("policy")
        started_at = timing.start()
        policy_decision = self.policy_service.decide(enriched, trace_recorder.trace)
        trace_recorder.trace.policy_decision = policy_decision
        trace_recorder.trace.warnings.extend(policy_decision.warnings)
        self._record_stage(
            trace_recorder,
            correlation_id,
            "policy",
            timing,
            started_at,
            {
                "safety_level": policy_decision.safety_level.value,
                "allow_execution": policy_decision.allow_execution,
            },
        )

        trace_recorder.start_stage("planning")
        started_at = timing.start()
        plan = self.router.create_plan(enriched, policy_decision)
        trace_recorder.trace.selected_target_mcps = plan.target_mcps
        self._log(
            correlation_id,
            "planning",
            timing.stop("planning", started_at),
            {"selected_targets": [target.value for target in plan.target_mcps]},
        )
        trace_recorder.end_stage(
            "planning",
            details={"selected_targets": [target.value for target in plan.target_mcps]},
        )

        trace_recorder.start_stage("mcp_execution")
        started_at = timing.start()
        results = await self.router.execute_plan(enriched, plan, trace_recorder.trace)
        self._record_stage(trace_recorder, correlation_id, "mcp_execution", timing, started_at)

        trace_recorder.start_stage("normalization")
        started_at = timing.start()
        response = self.normalizer.normalize(correlation_id, results, timing.timings)
        duration_ms = timing.stop("normalization", started_at)
        response.timings["normalization"] = round(duration_ms, 3)
        trace_recorder.end_stage("normalization")
        trace = trace_recorder.complete()
        response.debug["orchestration_trace"] = trace.model_dump(mode="json")
        self._log(correlation_id, "normalization", duration_ms, {"status": response.status.value})
        return response

    def docs_index_status(self) -> dict[str, object]:
        return self.retriever.status()

    def rebuild_docs_index(self) -> dict[str, object]:
        self.retriever.rebuild()
        return self.retriever.status()

    def mcp_servers_status(self) -> dict[str, object]:
        return self.server_catalog.status()

    async def list_mcp_tools(self, server_name: str) -> list[McpToolDefinition]:
        server = self.server_catalog.get(server_name)
        if not server:
            raise ValueError(f"MCP server not found: {server_name}")
        return await self.tool_runner.list_tools(server)

    async def call_mcp_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, object],
    ) -> McpToolCallResponse:
        server = self.server_catalog.get(server_name)
        if not server:
            raise ValueError(f"MCP server not found: {server_name}")
        return await self.tool_runner.call_tool(server, tool_name, arguments)

    def _context_filters(self, request: UserRequest, understanding) -> dict[str, object]:
        filters: dict[str, object] = {}
        if request.tags:
            filters["tags"] = request.tags
        if understanding.domain.value not in {"analytics", "general", "unknown"}:
            filters["domain"] = understanding.domain.value
        return filters

    def _log(
        self,
        correlation_id: str,
        stage: str,
        duration_ms: float,
        extra: dict[str, object] | None = None,
    ) -> None:
        log_stage(
            self.logger,
            correlation_id=correlation_id,
            stage=stage,
            status=(extra or {}).pop("status", "success"),
            duration_ms=duration_ms,
            extra=extra,
        )

    def _record_stage(
        self,
        trace_recorder: OrchestrationTraceRecorder,
        correlation_id: str,
        stage: str,
        timing: TimingRecorder,
        started_at: float,
        details: dict[str, object] | None = None,
    ) -> None:
        duration_ms = timing.stop(stage, started_at)
        trace_recorder.end_stage(stage, details=details)
        self._log(correlation_id, stage, duration_ms, details)


def create_orchestration_service(settings: Settings | None = None) -> OrchestrationService:
    settings = settings or Settings()
    server_catalog = LocalMcpServerCatalog(settings.resolved_mcps_dir())
    tool_runner = StdioMcpToolRunner()
    registry = DefaultMcpClientRegistry(
        server_catalog=server_catalog,
        tool_runner=tool_runner,
    )
    router = ExecutionRouter(registry)
    retriever = LocalContextRetriever(
        settings.resolved_docs_dir(),
        chunk_size=settings.rag_chunk_size,
    )
    return OrchestrationService(
        understanding_service=HeuristicRequestUnderstandingService(),
        retriever=retriever,
        composer=DefaultContextComposer(),
        policy_service=DefaultExecutionPolicyService(),
        router=router,
        normalizer=DefaultResponseNormalizer(),
        server_catalog=server_catalog,
        tool_runner=tool_runner,
        rag_top_k=settings.rag_top_k,
    )
