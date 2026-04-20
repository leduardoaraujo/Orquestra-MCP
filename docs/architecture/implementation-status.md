# MCP Orchestrator - Status da Implementação

## Visão Geral

O **MCP Orchestrator** evoluiu de uma arquitetura conceitual para uma fundação executável, modular e tipada.

O sistema atua como um **middleware contextual de orquestração para servidores MCP especializados**. Ele não é um roteador simples. Antes de chamar qualquer MCP especialista, o orquestrador interpreta a solicitação, recupera contexto local, compõe uma requisição enriquecida, aplica governança de execução, cria um plano de execução e só então chama o cliente especialista adequado.

Atualmente, o PostgreSQL é a primeira integração especialista real, usando o servidor PostgreSQL MCP local por meio de `stdio`.

## Fluxo Atual da Orquestração

```mermaid
flowchart TD
    A["UserRequest"] --> B["RequestUnderstanding"]
    B --> C["RetrievedContext"]
    C --> D["EnrichedRequest"]
    D --> E["ExecutionPolicyDecision"]
    E --> F["ExecutionPlan"]
    F --> G["SpecialistExecutionRequest"]
    G --> H["SpecialistExecutionResult"]
    H --> I["NormalizedResponse"]
```

Esse fluxo garante que nenhum MCP especialista receba diretamente a solicitação bruta do usuário.

## O Que Foi Implementado

### Fase 0 - Fundação Executável

A primeira fase de implementação criou a fundação executável do orquestrador:

- estrutura modular do projeto
- contratos Pydantic tipados
- aplicação FastAPI
- `GET /health`
- `POST /orchestrate`
- camada inicial de entendimento da solicitação
- recuperação de contexto local a partir de `docs/context`
- composição de requisição enriquecida
- roteamento para MCP especialista
- contrato de resposta normalizada
- integração real com PostgreSQL MCP por meio de `stdio`
- testes automatizados para o fluxo principal

A estrutura de contexto local é:

```text
docs/context/
  business_rules/
  schemas/
  technical_docs/
  examples/
  playbooks/
```

### Fase 1 - Governança de Execução e Rastreabilidade

A segunda etapa de implementação adicionou governança explícita de execução, entendimento mais forte da solicitação, trace de orquestração tipado e capacidades declaradas dos clientes MCP.

Agora, o orquestrador toma uma decisão explícita de política antes de chamar qualquer MCP especialista.

## Arquitetura Modular

```mermaid
flowchart LR
    API["Camada de API<br/>rotas FastAPI"] --> APP["Camada de Aplicação<br/>fluxo de orquestração"]

    APP --> UNDERSTANDING["Entendimento da Solicitação"]
    APP --> RETRIEVAL["Recuperação de Contexto"]
    APP --> COMPOSER["Composição de Contexto"]
    APP --> POLICY["Política de Execução"]
    APP --> ROUTER["Roteador de Execução"]
    APP --> NORMALIZER["Normalizador de Resposta"]

    ROUTER --> CLIENTS["Camada de Clientes MCP"]
    CLIENTS --> PG["PostgreSQL MCP<br/>integração real via stdio"]
    CLIENTS --> PBI["Power BI<br/>cliente futuro"]
    CLIENTS --> SQLS["SQL Server<br/>cliente futuro"]
    CLIENTS --> EXCEL["Excel<br/>cliente futuro"]

    RETRIEVAL --> DOCS["docs/context"]
```

A camada de API não contém lógica de negócio. Ela valida a entrada e delega para o serviço de orquestração.

## Contratos Principais

O orquestrador usa contratos explícitos para cada etapa do fluxo:

- `UserRequest`
- `RequestUnderstanding`
- `RetrievedContext`
- `EnrichedRequest`
- `ExecutionPolicyDecision`
- `ExecutionPlan`
- `SpecialistExecutionRequest`
- `SpecialistExecutionResult`
- `NormalizedResponse`
- `OrchestrationTrace`
- `McpClientCapability`

Esses contratos tornam o sistema mais fácil de testar, inspecionar e estender.

## Integração com PostgreSQL MCP

O PostgreSQL é a primeira integração real com um MCP especialista.

O servidor MCP local é descoberto a partir de:

```text
mcps/postgressql-mcp-master/server.py
```

O `PostgreSqlMcpClient` chama o servidor PostgreSQL MCP por meio do transporte MCP `stdio`.

Por padrão, a orquestração chama:

```text
run_guided_query
```

com:

```json
{
  "auto_execute": false,
  "limit": 100
}
```

Isso significa que o comportamento padrão é **preview-first**: o sistema prepara uma prévia segura de SQL em vez de executar consultas automaticamente no banco de dados.

## Política de Execução

A Fase 1 introduziu uma camada explícita de governança de execução.

```mermaid
flowchart TD
    A["EnrichedRequest"] --> B["ExecutionPolicyService"]
    B --> C{"Ação solicitada"}

    C -->|Preview ou geração de SQL| D["preview_only = true"]
    C -->|Read-only com allow_execution=true| E["allow_execution = true"]
    C -->|Write ou efeitos colaterais| F["blocked"]

    D --> G["ExecutionPlan"]
    E --> G
    F --> H["MCP especialista não é chamado"]
```

A decisão de política inclui:

- `preview_only`
- `read_only`
- `write`
- `side_effects`
- `requires_confirmation`
- `allow_execution`
- `blocked_reason`
- `safety_level`
- `risk_level`

Solicitações de escrita e solicitações com efeitos colaterais são bloqueadas antes de chegar a um MCP especialista.

## Entendimento Mais Forte da Solicitação

O contrato `RequestUnderstanding` foi expandido para capturar mais detalhes sobre a solicitação do usuário:

- `intent`
- `domain`
- `task_type`
- `requested_action`
- `target_preference`
- `candidate_mcps`
- `constraints`
- `ambiguities`
- `confidence`
- `risk_level`
- `reasoning_summary`

A implementação atual ainda é baseada em regras, mas o contrato já está preparado para um futuro interpretador baseado em LLM sem alterar o fluxo de orquestração posterior.

## Trace de Orquestração

O orquestrador agora cria um trace tipado para cada solicitação.

```mermaid
sequenceDiagram
    participant User as Usuário
    participant API
    participant Orchestrator as Orquestrador
    participant Retriever as Recuperador
    participant Policy as Política
    participant Router as Roteador
    participant PostgresMCP
    participant Normalizer as Normalizador

    User->>API: POST /orchestrate
    API->>Orchestrator: UserRequest
    Orchestrator->>Orchestrator: RequestUnderstanding
    Orchestrator->>Retriever: recuperar contexto
    Retriever-->>Orchestrator: RetrievedContext
    Orchestrator->>Policy: decidir política de execução
    Policy-->>Orchestrator: ExecutionPolicyDecision
    Orchestrator->>Router: criar ExecutionPlan
    Router-->>Orchestrator: SpecialistExecutionRequest
    Orchestrator->>PostgresMCP: run_guided_query
    PostgresMCP-->>Orchestrator: SpecialistExecutionResult
    Orchestrator->>Normalizer: normalizar resposta
    Normalizer-->>API: NormalizedResponse
    API-->>User: resposta
```

O trace captura:

- id da solicitação
- timestamps por etapa
- MCPs alvo selecionados
- fontes de contexto recuperadas
- decisão de política
- avisos
- informações de fallback
- notas de debug

Ele é retornado em:

```text
NormalizedResponse.debug.orchestration_trace
```

Detalhes de baixo nível do transporte MCP ficam dentro dos campos `debug` e não são promovidos para os campos principais da resposta.

## Capacidades dos Clientes MCP

Clientes especialistas agora expõem capacidades tipadas.

```mermaid
classDiagram
    class BaseMCPClient {
        +name
        +target
        +capabilities()
        +can_handle()
        +execute()
    }

    class PostgreSqlMcpClient {
        +supports_preview
        +supports_read
        +supports_write = false
        +default_tool = run_guided_query
    }

    class PowerBiMcpClient {
        +integração futura
    }

    class SqlServerMcpClient {
        +integração futura
    }

    class ExcelMcpClient {
        +integração futura
    }

    BaseMCPClient <|.. PostgreSqlMcpClient
    BaseMCPClient <|.. PowerBiMcpClient
    BaseMCPClient <|.. SqlServerMcpClient
    BaseMCPClient <|.. ExcelMcpClient
```

Cada cliente pode declarar:

- MCP alvo
- ferramentas suportadas
- suporte a preview
- suporte a leitura
- suporte a escrita
- suporte a efeitos colaterais
- ferramenta padrão

Isso prepara a arquitetura para futuros clientes reais de Power BI, SQL Server e Excel.

## Modelo de Segurança Atual

```mermaid
stateDiagram-v2
    [*] --> Interpreted
    Interpreted --> PreviewOnly: geração SQL ou preview
    Interpreted --> ReadAllowed: allow_execution=true e read_only
    Interpreted --> Blocked: write ou efeitos colaterais

    PreviewOnly --> PostgreSQLPreview
    ReadAllowed --> PostgreSQLExecution
    Blocked --> NormalizedError

    PostgreSQLPreview --> NormalizedResponse
    PostgreSQLExecution --> NormalizedResponse
    NormalizedError --> NormalizedResponse
```

Padrões atuais:

- PostgreSQL não executa consultas automaticamente no banco de dados.
- Geração de SQL usa modo preview.
- Solicitações de escrita são bloqueadas.
- Solicitações com efeitos colaterais são bloqueadas.
- Execução read-only exige opt-in explícito via metadata.

Exemplo de opt-in explícito:

```json
{
  "message": "Read rows from PostgreSQL sales_orders.",
  "domain_hint": "postgresql",
  "tags": ["sales", "postgresql"],
  "metadata": {
    "allow_execution": true
  }
}
```

## Testes

A suíte de testes cobre:

- contratos Pydantic
- recuperação de contexto local
- entendimento da solicitação
- decisões de política de execução
- roteamento
- capacidades dos clientes MCP
- comportamento preview-first do PostgreSQL
- trace de orquestração
- endpoints FastAPI

Resultado atual:

```text
36 testes passando
```

## Commits Criados

Commits regulares foram criados durante a implementação:

```text
9d254db Add execution governance foundation
1a58a83 Document and test execution governance
```

## Estado Atual do Projeto

O projeto agora possui:

- fundação executável de orquestração
- fluxo tipado de ponta a ponta
- integração real com PostgreSQL MCP
- recuperação de contexto local
- governança explícita de execução
- rastreabilidade tipada
- modelo extensível de capacidades dos clientes MCP
- testes cobrindo o comportamento central

## Próximos Passos Para a Fase 2

Próximos passos recomendados:

1. Adicionar um fluxo de confirmação para ações bloqueadas ou sensíveis.
2. Persistir traces e decisões de política em um storage auditável.
3. Substituir o interpretador heurístico por um interpretador baseado em LLM.
4. Implementar um cliente real para Power BI MCP.
5. Implementar um cliente real para SQL Server MCP.
6. Melhorar a recuperação local com embeddings.
7. Adicionar logs estruturados e métricas mais ricas.
8. Adicionar testes de integração controlados contra um banco PostgreSQL real.

A arquitetura central está pronta para essas adições sem reescrever o pipeline de orquestração.
