# MCP Orchestrator Executable Foundation

## Purpose

The MCP Orchestrator is a contextual middleware layer for specialist MCP servers.
It is not a raw router. Every specialist call is built from an enriched execution
payload that includes request understanding, local context, execution constraints,
and trace information.

## Phase 1 Flow

```text
UserRequest
  -> RequestUnderstanding
  -> RetrievedContext
  -> EnrichedRequest
  -> ExecutionPolicyDecision
  -> ExecutionPlan
  -> SpecialistExecutionRequest
  -> SpecialistExecutionResult
  -> NormalizedResponse
```

The FastAPI layer only validates input and delegates to the orchestration service.
Business rules, context retrieval, routing, execution, and normalization stay in
separate modules.

## Local Context

The default local context directory is:

```text
docs/context/
  business_rules/
  schemas/
  technical_docs/
  examples/
  playbooks/
```

The Phase 1 retriever is intentionally simple. It loads Markdown and text files,
splits them into chunks, scores chunks by token overlap, and returns typed
`RetrievedContextItem` objects. Embeddings can be added later behind the same
retriever interface.

## Execution Governance

Before planning or specialist execution, the orchestrator creates an
`ExecutionPolicyDecision`. The decision records whether the request is
preview-only, read-only, write-oriented, side-effecting, blocked, or explicitly
allowed for execution.

Phase 1 defaults to preview-only execution. Read-only execution is allowed only
when request metadata includes:

```json
{
  "allow_execution": true
}
```

Write and side-effecting requests are blocked before any specialist MCP is
called. This keeps the orchestrator ready for a future confirmation workflow
without letting clients execute unsafe actions implicitly.

## Stronger Request Understanding

`RequestUnderstanding` now includes:

- `requested_action`
- `target_preference`
- `ambiguities`
- `risk_level`
- `reasoning_summary`

The current interpreter is still rule-based. The stronger typed contract makes
it replaceable by an LLM-based interpreter later without changing downstream
components.

## Orchestration Trace

Every orchestration creates an `OrchestrationTrace` with request id, stage
timestamps, selected target MCPs, retrieved context sources, policy decision,
warnings, fallback information, and debug notes.

The trace is returned under:

```text
NormalizedResponse.debug.orchestration_trace
```

Low-level transport details stay inside specialist result debug fields.

## MCP Client Capabilities

Specialist clients expose typed capabilities with target, supported tools, and
whether they support preview, read, write, or side-effecting operations. This is
the contract future SQL Server, Power BI, and Excel clients can implement
without changing the orchestration flow.

## PostgreSQL MCP Integration

PostgreSQL is the first real specialist integration. The orchestrator discovers
the local server from:

```text
mcps/postgressql-mcp-master/server.py
```

The `PostgreSqlMcpClient` calls the server through the stdio MCP transport using
`StdioMcpToolRunner`. For `/orchestrate`, PostgreSQL requests use the
`run_guided_query` tool. Preview-first requests use:

```json
{
  "auto_execute": false,
  "limit": 100
}
```

This means Phase 1 produces a safe SQL preview by default. If the request is
classified as read-only and metadata explicitly sets `allow_execution=true`, the
router may set `auto_execute=true`. Write and side-effecting requests remain
blocked before PostgreSQL is called.

The `question` sent to PostgreSQL is derived from the enriched request. It
contains the original request, interpreted intent, task type, constraints, and
retrieved local context. The raw user request is not sent as the full specialist
payload.

## API Example

```json
{
  "message": "Use PostgreSQL to find the tables that can answer monthly sales revenue, then prepare a safe SQL preview.",
  "domain_hint": "postgresql",
  "tags": ["sales", "postgresql"],
  "metadata": {}
}
```

Response data is returned as `NormalizedResponse`. Specialist transport details,
including raw MCP tool results, are kept under `debug`.
