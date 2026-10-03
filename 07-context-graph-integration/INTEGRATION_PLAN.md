# Demo 07: Integración con neo4j-agent-memory

## ✅ Decisión Final

**Usaremos `neo4j-agent-memory` de Neo4j Labs** — la biblioteca oficial que implementa la three-memory architecture con POLE+O, diseñada por especialistas de Neo4j.

---

## 🎯 Por qué neo4j-agent-memory

### 1. **Diseñado por especialistas de Neo4j Labs**
- Mantenido por el equipo oficial de Neo4j
- POLE+O es su modelo base (`_base.yaml` en `create-context-graph`)
- 22+ dominios pre-construidos con ontologías listas

### 2. **Integración nativa con Strands**
```python
from neo4j_agent_memory.integrations.strands import context_graph_tools

tools = context_graph_tools(
    neo4j_uri=os.environ["NEO4J_URI"],
    neo4j_password=os.environ["NEO4J_PASSWORD"],
    embedding_provider="bedrock",  # ← Usa Bedrock, no OpenAI
)

agent = Agent(
    model="anthropic.claude-sonnet-4-20250514-v1:0",
    tools=tools  # ← Tools listos para usar
)
```

### 3. **Three-memory architecture completa**
- **Short-term memory:** Conversation history (per session)
- **Long-term memory:** POLE+O entity graph con entity resolution
- **Reasoning memory:** Decision traces con provenance

### 4. **Entity extraction automática**
- Multi-stage pipeline: spaCy → GLiNER → LLM
- Relationship extraction con GLiREL
- Entity resolution y deduplication nativa
- Background enrichment (Wikipedia, Diffbot)

### 5. **Compatible con AgentCore Memory**
- `neo4j-agent-memory` maneja Neo4j (entities + decisions)
- AgentCore Memory maneja STM/LTM strategies (text-only)
- **Complementarios, no conflictivos**

---

## 📊 Arquitectura Demo 07

```
┌─────────────────────────────────────────────────────────────────┐
│                     CLIENT                                      │
│  - Web UI o CLI                                                 │
│  - Provee: actor_id (user-xxx), session_id (opcional)          │
└────────────────────┬────────────────────────────────────────────┘
                     │ HTTP Request con headers:
                     │ x-amzn-bedrock-agentcore-runtime-custom-actor-id
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│              AGENTCORE RUNTIME (Fargate)                        │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  Strands Agent                                            │ │
│  │  - AgentCoreMemorySessionManager (built-in)              │ │
│  │  - memory_mode: "STM_AND_LTM"                             │ │
│  │  - Tools: neo4j-agent-memory Strands integration         │ │
│  │  - Hooks: BeforeToolCallEvent, AfterToolCallEvent        │ │
│  └───────────────────────────────────────────────────────────┘ │
└────────────┬────────────────────┬───────────────────────────────┘
             │                     │
             │ STM + LTM          │ neo4j-agent-memory tools
             ▼                     ▼
┌──────────────────────┐  ┌─────────────────────────────────────┐
│  AgentCore Memory    │  │  Neo4j (ECS Fargate + NLB)          │
│  (Managed Service)   │  │                                      │
│                      │  │  Powered by neo4j-agent-memory:     │
│  Namespaces:         │  │                                      │
│  /users/{actor}/     │  │  SHORT-TERM MEMORY:                 │
│    preferences       │  │  - Message nodes (per session)      │
│  /users/{actor}/     │  │  - Vector search on content         │
│    facts             │  │                                      │
│                      │  │  LONG-TERM MEMORY:                   │
│  Strategies:         │  │  - POLE+O entities                  │
│  - User Preference   │  │  - Relationships (WORKS_AT, etc)    │
│  - Semantic Memory   │  │  - Entity resolution                │
│                      │  │                                      │
│  Memory Mode:        │  │  REASONING MEMORY:                   │
│  STM_AND_LTM         │  │  - Decision nodes                   │
└──────────────────────┘  │  - Tool calls + provenance          │
                          │  - :TOUCHED audit edges             │
                          └─────────────────────────────────────┘
```

---

## 🔧 Componentes Clave

### 1. **AgentCore Runtime con neo4j-agent-memory**

```python
# agent_files/context_agent.py
import os
from strands import Agent
from strands.models.openai import OpenAIModel
from bedrock_agentcore import BedrockAgentCoreApp
from bedrock_agentcore.memory import (
    AgentCoreMemoryConfig,
    AgentCoreMemorySessionManager,
    RetrievalConfig,
    RequestContext
)
from neo4j_agent_memory.integrations.strands import context_graph_tools

app = BedrockAgentCoreApp()

@app.entrypoint
def invoke(payload, context=None):
    # 1. Extract actor_id from request headers
    request_context = RequestContext(context)
    actor_id = request_context.request_headers.get(
        "x-amzn-bedrock-agentcore-runtime-custom-actor-id",
        "default-user"
    )
    
    # 2. Configure AgentCore Memory (text-only STM/LTM)
    memory_config = AgentCoreMemoryConfig(
        memory_id=os.environ["BEDROCK_AGENTCORE_MEMORY_ID"],
        actor_id=actor_id,
        retrieval_config={
            "/users/{actor_id}/preferences": RetrievalConfig(top_k=5, relevance_score=0.7),
            "/users/{actor_id}/facts": RetrievalConfig(top_k=10, relevance_score=0.6)
        }
    )
    
    session_manager = AgentCoreMemorySessionManager(
        memory_config=memory_config,
        memory_mode="STM_AND_LTM"
    )
    
    # 3. Create neo4j-agent-memory tools
    neo4j_tools = context_graph_tools(
        neo4j_uri=os.environ["NEO4J_URI"],
        neo4j_password=os.environ["NEO4J_PASSWORD"],
        embedding_provider="bedrock",
        embedding_model="amazon.titan-embed-text-v2:0",
        aws_region=os.environ.get("AWS_REGION", "us-east-1")
    )
    
    # 4. Create Agent with both memory systems
    model = OpenAIModel(model_id="gpt-4o-mini", client_args={"api_key": get_openai_key()})
    
    agent = Agent(
        model=model,
        tools=neo4j_tools,  # ← 16 tools from neo4j-agent-memory
        system_prompt=SYSTEM_PROMPT,
        session_manager=session_manager,  # ← AgentCore Memory integration
        hooks=[DecisionProvenanceHook()]
    )
    
    # 5. Invoke agent
    prompt = payload if isinstance(payload, str) else payload.get("prompt", "")
    result = agent(prompt)
    return str(result)
```

### 2. **Neo4j en ECS Fargate (CloudFormation → CDK)**

Portaremos los templates de:
- `/Users/eliaws/Documents/repositories/aws-workshop/.../static/cfn/neo4j-foundation.yaml`
- `/Users/eliaws/Documents/repositories/aws-workshop/.../static/cfn/neo4j-service.yaml`

**Cambios clave:**
- NO usaremos dump/restore workflow (neo4j-agent-memory maneja schema)
- Sí usaremos NLB para endpoint estable
- neo4j-agent-memory crea schema en primera conexión

### 3. **Tools de neo4j-agent-memory (Strands integration)**

La integración Strands incluye 16 tools:

#### Core tools (6):
1. **`search_context`** — Vector search en messages + entities + preferences
2. **`get_context`** — Full context retrieval para LLM prompt
3. **`store_message`** — Guardar mensaje en short-term memory
4. **`add_entity`** — Crear entity node (Person, Organization, etc.)
5. **`add_preference`** — Guardar user preference
6. **`add_fact`** — Guardar fact/observation

#### Extended tools (16 total):
7. **`get_conversation_history`** — Retrieve messages por session_id
8. **`get_entity_details`** — Get entity + relationships
9. **`export_graph`** — Export subgraph como JSON
10. **`create_relationship`** — Link entities
11. **`add_reasoning_trace`** — Decision provenance
12. **`add_observation`** — Observation node
13. **`run_cypher_readonly`** — Custom Cypher queries
14. **`search_entities`** — Entity-specific search
15. **`get_preferences`** — List user preferences
16. **`delete_entity`** — Remove entity

**Configuración:**
```python
# Use core profile (fewer tools, less context overhead)
tools = context_graph_tools(..., profile="core")

# Or extended profile (default)
tools = context_graph_tools(..., profile="extended")
```

---

## 🔄 Data Flow

### **Turn 1: Initial Contact**
```
User → AgentCore Runtime
  Headers: x-amzn-bedrock-agentcore-runtime-custom-actor-id: user-abc123
  Body: "I met Sarah Chen from Acme Corp at AWS Summit."

AgentCore Runtime:
  1. AgentCoreMemorySessionManager retrieves LTM strategies (empty, first time)
  2. Agent processes with STM (empty) + LTM (empty)
  3. Agent calls store_message tool (neo4j-agent-memory)
  
neo4j-agent-memory (automatic extraction):
  1. Stores Message node in Neo4j
  2. Runs entity extraction pipeline:
     - spaCy: detects "Sarah Chen" (PERSON), "Acme Corp" (ORG), "AWS Summit" (EVENT)
     - GLiREL: extracts relationships (Sarah WORKS_AT Acme, Sarah ATTENDED Summit)
  3. Creates entity nodes with actor_id field:
     CREATE (p:Person {name: "Sarah Chen", actor_id: "user-abc123"})
     CREATE (o:Organization {name: "Acme Corp", actor_id: "user-abc123"})
     CREATE (e:Event {name: "AWS Summit", actor_id: "user-abc123"})
     CREATE (p)-[:WORKS_AT]->(o)
     CREATE (p)-[:ATTENDED]->(e)

Agent responds: "Thanks! I've saved that to your context graph."

[60-90 seconds later, asynchronously]
  AgentCore Memory extracts strategies:
    /users/user-abc123/facts: "Contact: Sarah Chen, Organization: Acme Corp"
```

### **Turn 2: Recall**
```
User → AgentCore Runtime
  Headers: x-amzn-bedrock-agentcore-runtime-custom-actor-id: user-abc123
  Body: "Who works at Acme Corp?"

AgentCore Runtime:
  1. Retrieves LTM strategies (gets facts about Sarah/Acme)
  2. Injects strategies into prompt
  3. Agent calls search_context tool

neo4j-agent-memory:
  MATCH (p:Person)-[:WORKS_AT]->(o:Organization {name: "Acme Corp"})
  WHERE p.actor_id = "user-abc123"
  RETURN p

Agent responds: "Based on our previous conversation, Sarah Chen works at Acme Corp."
```

---

## 📦 CDK Stacks

### **Stack 1: Neo4j Foundation**
```python
class Neo4jFoundationStack(Stack):
    def __init__(self, scope, id, *, vpc, **kwargs):
        # Neo4j Secret
        # S3 bucket (optional, for backups)
        # Security Group (Bolt port 7687)
        # ECS Cluster
        # IAM Roles (S3 + Bedrock + Secrets)
```

### **Stack 2: Neo4j Service**
```python
class Neo4jServiceStack(Stack):
    def __init__(self, scope, id, *, foundation, vpc, **kwargs):
        # Task Definition (Neo4j Enterprise 2026.01)
        # NLB (Bolt listener port 7687)
        # Fargate Service (desired_count=1)
        # Output: Neo4j URI (bolt://NLB-DNS:7687)
```

### **Stack 3: AgentCore Memory**
```python
class AgentCoreMemoryStack(Stack):
    def __init__(self, scope, id, *, role_arn, **kwargs):
        # CfnMemory with strategies:
        # - User Preference (/users/{actor_id}/preferences)
        # - Semantic Memory (/users/{actor_id}/facts)
```

### **Stack 4: AgentCore Runtime**
```python
class AgentCoreRuntimeStack(Stack):
    def __init__(self, scope, id, *, memory, neo4j_uri, **kwargs):
        # Runtime with environment variables:
        # - BEDROCK_AGENTCORE_MEMORY_ID
        # - NEO4J_URI
        # - NEO4J_PASSWORD (from Secrets Manager)
        # - OPENAI_KEY_SECRET_ARN (from Secrets Manager)
        # 
        # Dependencies: neo4j-agent-memory[strands,bedrock]
```

---

## 🎓 Beneficios de Esta Arquitectura

### 1. **Best practices de Neo4j Labs**
- ✅ POLE+O model oficial
- ✅ Entity extraction multi-stage (spaCy → GLiNER → LLM)
- ✅ Entity resolution nativa
- ✅ Three-memory architecture completa

### 2. **Integración AWS nativa**
- ✅ AgentCore Memory para STM/LTM strategies
- ✅ Bedrock embeddings (no OpenAI)
- ✅ Neo4j en ECS Fargate (no AuraDB auto-pause)
- ✅ Strands agent framework

### 3. **Multi-tenant con actor_id**
- ✅ Neo4j: todas las queries filtran por `actor_id`
- ✅ AgentCore Memory: namespaces `/users/{actor_id}/...`
- ✅ Aislamiento completo entre usuarios

### 4. **No reinventamos la rueda**
- ❌ NO escribimos nuestro propio entity extractor
- ❌ NO escribimos nuestro propio entity resolution
- ❌ NO escribimos nuestros propios tools
- ✅ Usamos `neo4j-agent-memory` que ya lo tiene todo

### 5. **Production-ready**
- ✅ 1,259 tests en neo4j-agent-memory
- ✅ Usado en producción por 22+ dominios
- ✅ Mantenido por Neo4j Labs
- ✅ Apache 2.0 license

---

## 🚀 Plan de Implementación

### **Phase 1: Setup (1 día)**
1. ✅ Crear `requirements.txt` con neo4j-agent-memory[strands,bedrock]
2. ✅ Portar CloudFormation → CDK (Neo4j Foundation + Service)
3. ✅ CDK Stack 3: AgentCore Memory
4. ✅ CDK Stack 4: AgentCore Runtime con neo4j-agent-memory

### **Phase 2: Agent Implementation (1 día)**
1. ✅ Implementar `context_agent.py` con:
   - AgentCoreMemorySessionManager
   - context_graph_tools from neo4j-agent-memory
   - DecisionProvenanceHook
2. ✅ Test local con Neo4j Docker

### **Phase 3: Deployment (1 día)**
1. ✅ Deploy Neo4j stack
2. ✅ Deploy AgentCore Memory stack
3. ✅ Deploy AgentCore Runtime stack
4. ✅ Test end-to-end: entity extraction + recall

### **Phase 4: Observability (1 día)**
1. ✅ CloudWatch dashboard (infra metrics)
2. ✅ X-Ray service map (agent traces)
3. ✅ Neo4j Browser queries (provenance graph)

### **Phase 5: CFP Materials (1-2 días)**
1. ✅ Diagrama arquitectura AWS
2. ✅ Slide deck con demo flow
3. ✅ CFP abstract
4. ✅ Demo video
5. ✅ Repo público con step-by-step guide

---

## 🎤 CFP Pitch Actualizado

"Imagine un agente que **aprende de cada conversación**, **entiende relaciones entre entidades**, y **explica cada decisión** con trazabilidad completa.

Demo 07 integra **`neo4j-agent-memory` de Neo4j Labs** con **AWS AgentCore** en producción:

- **Short-term memory:** AgentCore Memory strategies (text-only semantic search)
- **Long-term memory:** Neo4j POLE+O entities (Person, Organization, Location, Event, Object)
- **Reasoning memory:** Neo4j decision traces con full provenance

**Entity extraction automática:** spaCy → GLiNER → LLM pipeline con entity resolution nativa.

**Tools listos:** 16 Strands tools de neo4j-agent-memory (search_context, add_entity, store_message, etc.)

**Multi-tenant:** actor_id isolation en Neo4j + AgentCore Memory namespaces.

**Observability:** CloudWatch (infra) + X-Ray (agent traces) + Neo4j Browser (provenance graph).

Salí con arquitectura production-ready usando **best practices oficiales de Neo4j Labs**."

---

## 📚 Referencias

- **neo4j-agent-memory:** https://github.com/neo4j-labs/agent-memory
- **create-context-graph:** https://github.com/neo4j-labs/create-context-graph
- **Strands integration:** https://neo4j.com/labs/agent-memory/how-to/integrations/aws-strands
- **POLE+O model:** https://neo4j.com/labs/agent-memory/explanation/poleo-model

---

**Status:** Plan de integración finalizado. Listo para implementar.
