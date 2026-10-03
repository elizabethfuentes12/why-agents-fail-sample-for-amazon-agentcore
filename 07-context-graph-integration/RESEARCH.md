# Research Summary: Context Graph Integration

## Investigation Overview

This document captures research for integrating neo4j-labs/create-context-graph concepts with the existing Graph-RAG demos (01 & 06) using Strands Agents on AWS.

---

## Key Findings

### 1. neo4j-labs/create-context-graph

**What it is:**
- Interactive CLI scaffolding tool (`npx create-context-graph`)
- Generates full-stack AI agent applications in ~5 minutes
- Think "create-react-app for graph-backed AI agents"

**Core Innovation: Three-Memory Architecture**

Unlike traditional RAG (retrieval-only), create-context-graph implements:

```
┌─────────────────────────────────────────────────────────────┐
│                    AGENT MEMORY SYSTEM                       │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  SHORT-TERM MEMORY          LONG-TERM MEMORY               │
│  ┌──────────────┐           ┌──────────────┐              │
│  │ Conversation │           │    Entity    │              │
│  │   History    │──────────▶│  Knowledge   │              │
│  │              │           │    Graph     │              │
│  └──────────────┘           │  (POLE+O)    │              │
│                              └──────────────┘              │
│                                     │                       │
│                              REASONING MEMORY              │
│                              ┌──────────────┐              │
│                              │   Decision   │              │
│                              │    Trace     │              │
│                              │ Provenance   │              │
│                              └──────────────┘              │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

1. **Short-term:** Conversation context (current session)
2. **Long-term:** Entity knowledge graph (POLE+O model: Person, Organization, Location, Event + custom Objects)
3. **Reasoning:** Decision trace provenance (thought chains, tool calls, causal relationships as graph nodes)

**Key differentiator from our Demo 01:**
- Demo 01: Pre-built FAQ graph for retrieval (static)
- create-context-graph: Live entity extraction + decision provenance (dynamic)

**Architecture components:**
```
CLI Generator (Jinja2 templates)
    │
    ├─ Backend: FastAPI + domain agents
    ├─ Frontend: Next.js + Chakra UI (streaming chat, graph viz)
    ├─ Database: Neo4j schema with constraints/indexes
    └─ Data: Synthetic or SaaS imports (GitHub, Slack, Notion, Linear)
```

**Supported frameworks:** 8 agent frameworks including Strands, LangGraph, CrewAI, PydanticAI, Claude Agent SDK

**SaaS integrations:** GitHub issues, Slack threads, Linear decisions, Google Workspace → graph nodes

**Documentation:** https://github.com/neo4j-labs/create-context-graph

---

### 2. Strands Agents Framework

**What it is:**
Open-source SDK (Python + TypeScript) built from production systems within Amazon, designed for enterprise-scale autonomous agents.

**Core capabilities:**

1. **Dynamic Tool Management**
   ```python
   # Runtime tool swapping without losing conversation history
   agent.tool_registry.registry.clear()
   agent.tool_registry.dynamic_tools.clear()
   for tool in new_tools:
       agent.tool_registry.register_tool(tool)
   ```
   Critical for Demo 02 (semantic filtering): 29 tools → 5 tools per query, 89% token reduction

2. **Hook System (Lifecycle Interception)**
   ```python
   class NeurosymbolicHook(HookProvider):
       def register_hooks(self, registry: HookRegistry):
           registry.add_callback(BeforeToolCallEvent, self.validate)
       
       def validate(self, event: BeforeToolCallEvent):
           if violates_rule(event.tool_use["input"]):
               event.cancel_tool = "BLOCKED: Rule violation"
   ```
   Used in Demo 04 (neurosymbolic) and Demo 06 (production guardrails)

3. **MCP (Model Context Protocol) Integration**
   ```python
   mcp_client = MCPClient(lambda: streamablehttp_client(GATEWAY_URL))
   with mcp_client:
       tools = mcp_client.list_tools_sync()  # Discover from Gateway
       agent = Agent(model=model, tools=tools)
   ```
   Powers Demo 06: AgentCore Gateway exposes Lambda tools via MCP

4. **Steering vs Blocking**
   - **Hard block:** "Guest count > 10" → Stop execution
   - **Steering:** "Guest count > 10. Split into two rooms: 10 + 5 guests" → Self-correct
   
   Demo 05 benchmark: Steering = 100% accuracy, Prompts-only = 82.5%

**Comparison to other frameworks:**

| Feature | Strands | LangGraph | CrewAI |
|---------|---------|-----------|--------|
| Dynamic tool swapping | Native | Requires recreation | Requires recreation |
| Hook system | `BeforeToolCallEvent` | Custom nodes | Limited |
| MCP integration | Built-in `MCPClient` | Custom | None |
| AWS Bedrock | Native support | Via LangChain | Custom |
| Steering handlers | First-class | Prompt-based | Prompt-based |

**Key architectural pattern:**
Strands separates **policy** (DynamoDB steering rules) from **enforcement** (framework hooks). Demo 06 stores steering messages in DynamoDB—changeable without redeploying agent code.

---

## Integration Opportunity: Context Graph + Strands on AWS

### Problem Statement

Current demos show:
- **Demo 01:** Graph-RAG retrieval from static FAQ graph (Neo4j SimpleKGPipeline)
- **Demo 06:** Production deployment with DynamoDB + Lambda tools + AgentCore

**Gap:** No live entity extraction from conversations or decision provenance tracking.

### Proposed Integration

Build a **"Context Graph Agent"** that combines:

1. **Three-Memory Architecture** (from create-context-graph)
   - Short-term: Conversation in DynamoDB
   - Long-term: Entity graph in Neo4j (POLE+O model)
   - Reasoning: Decision trace in Neo4j (tool calls → outcomes as graph relationships)

2. **Strands Production Patterns** (from Demo 06)
   - AgentCore Runtime + Gateway (MCP tool discovery)
   - Lambda tools for entity extraction, graph queries, decision logging
   - DynamoDB steering rules + framework hooks

3. **AWS Deployment** (CDK infrastructure)
   - Neo4j AuraDB for entity + reasoning graphs
   - DynamoDB for conversations + steering rules
   - Lambda for: extract_entities, query_context, log_decision, validate_rules
   - AgentCore for agent runtime + MCP gateway

### Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                        USER REQUEST                              │
└────────────────────────┬─────────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────────┐
│              Amazon Bedrock AgentCore Runtime                    │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  Strands Agent with Hooks                                  │ │
│  │  - BeforeToolCallEvent: Validate steering rules            │ │
│  │  - AfterToolCallEvent: Log decision provenance             │ │
│  └────────────────────────────────────────────────────────────┘ │
└────────────────────────┬─────────────────────────────────────────┘
                         │ MCP Tool Discovery
                         ▼
┌──────────────────────────────────────────────────────────────────┐
│              Amazon Bedrock AgentCore Gateway                    │
│  - Exposes Lambda tools via MCP                                  │
│  - Semantic tool filtering (reduces 20+ tools to 3-5)           │
└────────────────────────┬─────────────────────────────────────────┘
                         │ Invokes Lambda Functions
                         ▼
┌──────────────────────────────────────────────────────────────────┐
│                    AWS Lambda Tools                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ extract_entities│  │  query_context  │  │  log_decision   │ │
│  │   (STM → LTM)   │  │  (LTM → Agent)  │  │ (Action → RM)   │ │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘ │
│           │                     │                     │          │
│           │ POLE+O entities     │ Cypher queries      │ Decision │
│           │                     │                     │ trace    │
└───────────┼─────────────────────┼─────────────────────┼──────────┘
            │                     │                     │
            ▼                     ▼                     ▼
┌──────────────────────────────────────────────────────────────────┐
│                     Neo4j AuraDB                                 │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  LONG-TERM MEMORY         REASONING MEMORY                 │ │
│  │  ┌──────────────┐         ┌──────────────┐                │ │
│  │  │   Entities   │         │  Decisions   │                │ │
│  │  │  (POLE+O)    │◀───────▶│  (Provenance)│                │ │
│  │  └──────────────┘         └──────────────┘                │ │
│  └────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
            │                                      │
            │ Conversation history                 │ Steering rules
            ▼                                      ▼
┌──────────────────────────────────────────────────────────────────┐
│                      Amazon DynamoDB                             │
│  ┌────────────────────────────┐  ┌──────────────────────────┐  │
│  │   SHORT-TERM MEMORY        │  │   Steering Rules         │  │
│  │   (Conversations table)     │  │   (Controls table)       │  │
│  └────────────────────────────┘  └──────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### Data Flow Example

**User:** "I met Sarah Chen from Acme Corp at the AWS Summit. She's interested in our hotel booking platform."

1. **Short-term memory:** Conversation stored in DynamoDB
2. **Entity extraction:** Lambda calls LLM to extract:
   ```
   Person: Sarah Chen
   Organization: Acme Corp
   Event: AWS Summit
   Location: [inferred from context]
   ```
3. **Long-term memory:** Entities stored in Neo4j:
   ```cypher
   CREATE (p:Person {name: "Sarah Chen"})
   CREATE (o:Organization {name: "Acme Corp"})
   CREATE (e:Event {name: "AWS Summit"})
   CREATE (p)-[:WORKS_AT]->(o)
   CREATE (p)-[:ATTENDED]->(e)
   ```
4. **Reasoning memory:** Agent's decision to extract entities logged:
   ```cypher
   CREATE (d:Decision {
       action: "extract_entities",
       timestamp: "2026-05-10T14:30:00Z",
       input: "User message text...",
       output: "3 entities extracted"
   })
   CREATE (d)-[:CREATED]->(p)
   CREATE (d)-[:CREATED]->(o)
   ```

**User:** "What companies have we talked about?"

1. **Context retrieval:** Lambda queries Neo4j:
   ```cypher
   MATCH (o:Organization)
   RETURN o.name, COUNT((p:Person)-[:WORKS_AT]->(o)) as employees
   ```
2. **Agent response:** "We've discussed Acme Corp (1 contact: Sarah Chen)."
3. **Decision logging:** Query action logged in reasoning graph

### Use Cases

1. **Sales CRM:** Track conversations with prospects, extract companies/people/events, query "Who attended AWS Summit?"
2. **Customer Support:** Build knowledge graph of issues/resolutions, ask "What problems did Acme Corp report?"
3. **Research Assistant:** Extract entities from papers, connect authors/topics, query "Who researches Graph-RAG?"
4. **Meeting Notes:** Capture decisions/action items, build accountability graph, ask "What did Sarah agree to?"

### CFP Talk Structure (45 min)

**Title:** "From Hallucinations to Context: Building Production Graph-Backed Agents on AWS"

**Outline:**

1. **Problem Demo (5 min)**
   - Traditional RAG fabricates hotel stats
   - No memory of past conversations
   - No audit trail of agent decisions

2. **Solution 1: Graph-RAG (7 min)**
   - Demo 01: Static FAQ graph (SimpleKGPipeline)
   - Result: 73% fewer hallucinations
   - Limitation: Static data, no entity extraction

3. **Solution 2: Three-Memory Architecture (10 min)**
   - Short-term: Conversation history (DynamoDB)
   - Long-term: Entity knowledge graph (Neo4j POLE+O)
   - Reasoning: Decision provenance (Neo4j relationships)
   - Live demo: Extract entities from conversation → query context

4. **Solution 3: Production Patterns (15 min)**
   - Strands hooks for guardrails (BeforeToolCallEvent)
   - MCP tool discovery (AgentCore Gateway)
   - DynamoDB steering rules (changeable without redeploy)
   - Demo 07: Full context graph agent on AWS

5. **Framework Portability (5 min)**
   - Same patterns in LangGraph, CrewAI, AutoGen
   - neo4j-labs/create-context-graph as scaffolding tool

6. **Q&A (3 min)**

### Metrics to Highlight

- **Token reduction:** 89% via semantic filtering (Demo 02)
- **Accuracy improvement:** 100% steering vs 82.5% prompts (Demo 05)
- **Latency:** 25ms DynamoDB validation, 13ms Neo4j queries (Demo 06)
- **Cost savings:** $711/year from tool filtering alone (10K queries/day)
- **Hallucination reduction:** 73% via Graph-RAG (Demo 01)

### Take-Home Tools

1. **This repo:** Progressive demos (01-07) with CloudFormation/CDK
2. **neo4j-labs/create-context-graph:** Scaffold new apps in 5 minutes
3. **Strands Agents:** Open-source SDK for production agents

---

## Next Steps

### Phase 1: Architecture Design
- [x] Research neo4j-labs/create-context-graph
- [x] Research Strands framework capabilities
- [ ] Design Neo4j schema for POLE+O + reasoning graph
- [ ] Design DynamoDB tables for conversations + steering
- [ ] Design Lambda functions for extract/query/log

### Phase 2: Local Prototype
- [ ] Build entity extraction tool (OpenAI → Neo4j)
- [ ] Build context query tool (Cypher → results)
- [ ] Build decision logging hook (AfterToolCallEvent → Neo4j)
- [ ] Test three-memory flow with sample conversations

### Phase 3: AWS Deployment (CDK)
- [ ] Port to Lambda functions
- [ ] Create AgentCore Runtime + Gateway
- [ ] Deploy Neo4j AuraDB (or Neptune Graph if fully managed)
- [ ] Create DynamoDB tables
- [ ] End-to-end test with AgentCore invocation

### Phase 4: CFP Materials
- [ ] Create architecture diagrams (draw.io with AWS icons)
- [ ] Record demo videos (local + AWS)
- [ ] Write talk abstract
- [ ] Create slide deck
- [ ] Build GitHub repo with step-by-step guide

---

## Technical Considerations

### Why Neo4j AuraDB vs Amazon Neptune?

**Neo4j AuraDB:**
- ✅ Native Cypher support (mature ecosystem)
- ✅ Free tier available (pauses after inactivity)
- ✅ SimpleKGPipeline integration (Demo 01 compatibility)
- ✅ neo4j-labs tooling designed for AuraDB
- ❌ Requires secret management (URI/password)
- ❌ Auto-pause requires manual resume

**Amazon Neptune:**
- ✅ Fully managed (no pause/resume)
- ✅ IAM authentication (no passwords)
- ✅ VPC integration (security)
- ❌ OpenCypher support is partial (not full Cypher)
- ❌ No SimpleKGPipeline support out-of-box
- ❌ Higher cost (no free tier)

**Recommendation:** Start with Neo4j AuraDB for demo compatibility, document Neptune migration path for production.

### Why Strands vs LangGraph?

**Strands:**
- ✅ Dynamic tool swapping (Demo 02 requires this)
- ✅ Native MCP support (AgentCore integration)
- ✅ Hook system for guardrails (Demo 04/06 pattern)
- ✅ Built from Amazon production systems
- ❌ Smaller community vs LangChain ecosystem

**LangGraph:**
- ✅ Larger community, more examples
- ✅ LangSmith observability
- ✅ Pre-built integrations (LangChain tools)
- ❌ Tool swapping requires agent recreation (loses history)
- ❌ MCP support requires custom implementation
- ❌ Guardrails via prompt or custom nodes (not hooks)

**Recommendation:** Primary demo in Strands (shows AWS integration + unique capabilities), bonus section showing LangGraph port.

### Cost Estimate (10K queries/day)

**Compute:**
- AgentCore Runtime: ~$50/month (estimate based on Lambda equivalent)
- 5 Lambda functions @ 256MB, 1s avg: ~$20/month
- DynamoDB (on-demand): ~$10/month

**Data:**
- Neo4j AuraDB Free: $0 (pauses when idle)
- DynamoDB storage (10K conversations × 5KB): ~$0.50/month

**LLM:**
- GPT-4o-mini @ $0.15/1M input, $0.60/1M output
- 10K queries × 150 tokens input × $0.15/1M = $0.23/day
- 10K queries × 500 tokens output × $0.60/1M = $3.00/day
- **Total LLM: ~$100/month**

**Grand total: ~$180/month** (dominated by LLM costs)

**Optimization:**
- Use Amazon Bedrock Claude Haiku for extraction (cheaper than GPT-4o-mini)
- Cache entity extraction prompts (reduces input tokens by 50%)
- Batch decision logging (reduce Lambda invocations)

---

## References

- **neo4j-labs/create-context-graph:** https://github.com/neo4j-labs/create-context-graph
- **Strands Agents Docs:** https://docs.strands-agents.dev
- **Amazon Bedrock AgentCore:** https://docs.aws.amazon.com/bedrock/latest/agentcore/
- **Neo4j AuraDB Free:** https://neo4j.com/cloud/aura-free/
- **MCP Protocol:** https://modelcontextprotocol.io

---

## Key Insights

1. **create-context-graph is a scaffolding tool, not a runtime library**
   - Generates application code (FastAPI, Next.js, Neo4j schema)
   - Supports 8 agent frameworks (including Strands)
   - Useful for rapid prototyping, not for this specific integration (we need custom Lambda deployment)

2. **Three-memory architecture is the key differentiator**
   - Current demos only have "long-term memory" (static FAQ graph)
   - Adding short-term (conversations) + reasoning (decisions) enables:
     - Multi-turn context ("Remember Sarah from Acme Corp?")
     - Decision auditing ("Why did the agent book this hotel?")
     - Continuous learning ("What have we learned about Acme Corp?")

3. **Strands hooks enable separation of concerns**
   - Tools remain pure functions (no validation logic embedded)
   - Hooks centralize guardrails (reusable across agents)
   - DynamoDB steering rules allow runtime policy changes

4. **MCP solves the tool discovery problem**
   - Without MCP: Agent hardcodes tool list, Lambda updates require agent redeploy
   - With MCP: Agent discovers tools from Gateway, Lambda updates automatically available
   - This is critical for teams where tools are owned by different services

5. **Steering > Blocking for production agents**
   - Hard blocks stop workflows ("Guest count invalid, fix it")
   - Steering guides self-correction ("Guest count > 10, split into rooms of 10 + 5")
   - Demo 05 shows 17.5% accuracy improvement with steering

---

**Author:** Research conducted by Elizabeth (AWS Solutions Architect) for CFP talk on production Graph-RAG agents  
**Date:** 2026-05-10  
**Status:** Research complete, ready for implementation planning
