# Demo 07: Context Graph Integration

**Production-Ready Context-Aware Agent with Three-Memory Architecture**

This demo uses [neo4j-agent-memory](https://github.com/neo4j-labs/agent-memory) from Neo4j Labs to implement a **three-memory architecture** for context-aware agents on AWS.

## 🎯 Executive Summary

**Status:** Phase 1 deployed ✅ | Phase 2 code ready ✅

**What's deployed (Phase 1):**
- Neo4j 2026.01 Enterprise on ECS Fargate with automated S3 backups (every 15 minutes)
- Lambda functions for seeding/querying POLE+O entities
- Network Load Balancer for stable Neo4j endpoint

**What's ready to deploy (Phase 2):**
- AgentCore Runtime with Strands Swarm (3-agent architecture: Extractor → Query → Response)
- DynamoDB for short-term memory (conversation history)
- Neo4j for long-term memory (POLE+O entities) + reasoning memory (decision provenance)
- Deployment via `bedrock-agentcore-starter-toolkit` Runtime SDK

**Next steps:**
```bash
# 1. Deploy infrastructure (5 minutes)
cd cdk && cdk -a "python3 app_agentcore.py" deploy

# 2. Deploy agent (10 minutes)
cd .. && python3 deploy_runtime.py

# 3. Test
from bedrock_agentcore_starter_toolkit import Runtime
runtime = Runtime()
runtime.invoke({"prompt": "I met Sarah Chen from Acme Corp"})
```

**Key innovation:** Uses Strands Swarm for automatic multi-agent orchestration with built-in loop detection, shared memory, and session persistence.

---

## Quick Start

### Phase 1: ✅ Neo4j + Lambda Stack Deployed

**Stack Name:** `Neo4jContextGraph`  
**Status:** `UPDATE_COMPLETE`  
**Region:** `us-east-1`

**Deployed Components:**
- ✅ Neo4j 2026.01 Enterprise on ECS Fargate
- ✅ Network Load Balancer (stable Bolt endpoint)
- ✅ S3 bucket for automated backups
- ✅ Backup sidecar (every 15 minutes)
- ✅ 2 Lambda functions (seed_data, query_graph)
- ✅ Lambda layer with neo4j-agent-memory

**Access Neo4j:**
```bash
# Get connection URI
aws cloudformation describe-stacks \
  --stack-name Neo4jContextGraph \
  --query 'Stacks[0].Outputs[?OutputKey==`Neo4jBoltUri`].OutputValue' \
  --output text

# Get password from Secrets Manager
NEO4J_SECRET_ARN=$(aws cloudformation describe-stacks \
  --stack-name Neo4jContextGraph \
  --query 'Stacks[0].Outputs[?OutputKey==`Neo4jPasswordSecretArn`].OutputValue' \
  --output text)

aws secretsmanager get-secret-value \
  --secret-id "$NEO4J_SECRET_ARN" \
  --query 'SecretString' \
  --output text
```

**Seed sample data:**
```bash
aws lambda invoke \
    --function-name Neo4jContextGraph-LambdasSeedData6D362933-dEchfdMHlUnN \
    --payload '{}' \
    response.json

cat response.json
```

**Query entities:**
```bash
aws lambda invoke \
    --function-name Neo4jContextGraph-LambdasQueryGraphCEF39FDC-WNsGrtErLNdg \
    --payload '{"action": "query_entities", "entity_type": "Person"}' \
    response.json

cat response.json
```

**Monitor backups:**
```bash
# Check S3 bucket for backups (created every 15 minutes)
BUCKET=$(aws cloudformation describe-stacks \
  --stack-name Neo4jContextGraph \
  --query 'Stacks[0].Outputs[?OutputKey==`DumpBucketName`].OutputValue' \
  --output text)

aws s3 ls s3://$BUCKET/ --recursive
```

### Phase 2: AgentCore Integration with Strands Swarm (Next)

**Prerequisites:**
- Phase 1 deployed and working
- Neo4j seeded with sample data
- Install AgentCore toolkit: `pip install bedrock-agentcore-starter-toolkit>=0.2.5`

**Step 1: Deploy infrastructure (DynamoDB + IAM):**
```bash
cd cdk
cdk -a "python3 app_agentcore.py" deploy
```

**Step 2: Deploy agent using Runtime SDK:**
```bash
cd ..
python3 deploy_runtime.py
```

This will:
1. Create ECR repository for agent container
2. Build and push agent Docker image
3. Deploy AgentCore Runtime with STM_AND_LTM memory mode
4. Configure environment variables (Neo4j connection, DynamoDB tables)

**Step 3: Test the agent:**
```python
from bedrock_agentcore_starter_toolkit import Runtime

runtime = Runtime()
result = runtime.invoke({
    "prompt": "I met Sarah Chen from Acme Corp at AWS Summit. She's interested in our enterprise tier."
})
print(result)
```

**Components:**
- ✅ DynamoDB tables (conversations + agent state)
- ✅ Strands Swarm with 3 specialized agents (Extractor, Query, Response)
- ✅ AgentCore Runtime with STM_AND_LTM memory mode (deployed via Runtime SDK)
- ✅ Integration with Neo4j context graph tools

**Architecture:** Uses **Strands Swarm** instead of manual delegation pattern for:
- Automatic agent handoffs with loop detection
- Shared working memory across all agents
- Built-in timeouts and circuit breakers
- Session persistence for resuming interrupted workflows

---

## What This Adds Beyond Demo 01 & 06

| Feature | Demo 01 | Demo 06 | Demo 07 |
|---------|---------|---------|---------|
| **Knowledge Graph** | ✅ Static FAQ retrieval | ✅ Static FAQ retrieval | ✅ **Dynamic POLE+O entity extraction** |
| **Conversation Memory** | ❌ | ❌ | ✅ **Neo4j Message nodes (STM)** |
| **Decision Provenance** | ❌ | ❌ | ✅ **Neo4j reasoning graph** |
| **Entity Model** | FAQ documents | FAQ documents | **POLE+O (Person, Org, Location, Event, Object)** |
| **Production Deployment** | ❌ | ✅ AgentCore | ✅ **Neo4j on ECS + AgentCore** |
| **Library Used** | neo4j-graphrag | None | **neo4j-agent-memory (official)** |
| **Multi-Agent Pattern** | N/A | N/A | ✅ **Strands Swarm (automatic handoffs)** |

---

## Three-Memory Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    AGENT MEMORY SYSTEM                       │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐           ┌──────────────┐              │
│  │ SHORT-TERM   │           │  LONG-TERM   │              │
│  │   MEMORY     │──────────▶│    MEMORY    │              │
│  │              │           │              │              │
│  │ Conversation │  Extract  │   Entities   │              │
│  │   History    │  Entities │   (POLE+O)   │              │
│  │  (DynamoDB)  │           │   (Neo4j)    │              │
│  └──────────────┘           └──────┬───────┘              │
│                                     │                       │
│                                     │ Query Context         │
│                                     ▼                       │
│                              ┌──────────────┐              │
│                              │  REASONING   │              │
│                              │    MEMORY    │              │
│                              │              │              │
│                              │  Decisions   │              │
│                              │ Provenance   │              │
│                              │   (Neo4j)    │              │
│                              └──────────────┘              │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 1. Short-Term Memory (DynamoDB)
Current conversation context — messages, user profile, session state.

### 2. Long-Term Memory (Neo4j)
Entity knowledge graph extracted from conversations over time.

**POLE+O Model:**
- **P**erson: "Sarah Chen", "John Doe"
- **O**rganization: "Acme Corp", "AWS"
- **L**ocation: "Seattle", "AWS Summit San Francisco"
- **E**vent: "re:Invent 2025", "Product Demo Meeting"
- **O**bject: Domain-specific (Hotel, Booking, Room Type)

### 3. Reasoning Memory (Neo4j)
Decision trace provenance — which tools were called, why, and what happened.

**Example:**
```cypher
(Decision:extract_entities {timestamp: "2026-05-10T14:30:00Z"})
  -[:INPUT]-> (Message:User "I met Sarah Chen...")
  -[:CREATED]-> (Person:Sarah_Chen)
  -[:CREATED]-> (Organization:Acme_Corp)
  -[:FOLLOWED_BY]-> (Decision:query_context)
```

---

## Architecture Diagram (Phase 1 - Deployed)

```
┌─────────────────────────────────────────────────────────────────┐
│                     ECS Fargate Task                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────────────┐   ┌──────────────────────────────────┐ │
│  │ dump-downloader    │   │  Neo4j 2026.01 Enterprise        │ │
│  │ (STOPPED)          │──▶│  - Port 7687 (Bolt)              │ │
│  │ Downloads S3 dump  │   │  - APOC enabled                  │ │
│  └────────────────────┘   │  - HEALTHY                       │ │
│                            └──────────────────────────────────┘ │
│                                        ▲                         │
│                                        │ localhost:7687          │
│  ┌─────────────────────────────────────▼──────────────────────┐ │
│  │ backup-sidecar (RUNNING)                                   │ │
│  │ - Backup every 15 minutes via APOC export                  │ │
│  │ - Uploads to S3: neo4j-graph.cypher                        │ │
│  │ - Final backup on SIGTERM                                  │ │
│  └────────────────────────────────────────────────────────────┘ │
└────────────────────────┬────────────────────────────────────────┘
                         │ Uploads backups
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                S3 Bucket (Persistent Storage)                   │
│  - neo4j-graph.cypher (latest backup)                           │
│  - backups/neo4j-{timestamp}.cypher (versioned)                 │
│  - Lifecycle: 30-day retention                                  │
└─────────────────────────────────────────────────────────────────┘
                         ▲
                         │ Read by Lambdas
                         │
┌─────────────────────────────────────────────────────────────────┐
│                   AWS Lambda Functions                          │
│  ┌──────────────────────┐    ┌───────────────────────────────┐ │
│  │  seed_data           │    │  query_graph                  │ │
│  │  - Populates POLE+O  │    │  - Cypher queries             │ │
│  │  - Sample entities   │    │  - Entity retrieval           │ │
│  └──────────────────────┘    └───────────────────────────────┘ │
│                                                                  │
│  Layer: neo4j-agent-memory (19MB ARM64)                         │
└─────────────────────────────────────────────────────────────────┘
                         │
                         │ Connects via NLB
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│           Network Load Balancer (Stable Endpoint)               │
│  bolt://Neo4jC-Neo4j-xxx.elb.us-east-1.amazonaws.com:7687      │
└─────────────────────────────────────────────────────────────────┘
```

**Phase 2 (Ready to Deploy):** AgentCore Runtime with Strands Swarm

```
┌─────────────────────────────────────────────────────────────────┐
│                   AgentCore Runtime (Strands Swarm)             │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Extractor Agent                                         │  │
│  │  - Tools: extract_entities (from neo4j-agent-memory)    │  │
│  │  - Handoff: Always → Query Agent                        │  │
│  └────────────────────────┬─────────────────────────────────┘  │
│                           ▼                                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Query Agent                                             │  │
│  │  - Tools: query_entities, query_relationships           │  │
│  │  - Handoff: Always → Response Agent                     │  │
│  └────────────────────────┬─────────────────────────────────┘  │
│                           ▼                                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Response Agent                                          │  │
│  │  - Tools: None (synthesis only)                         │  │
│  │  - Handoff: None (final response)                       │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ├─────────────────┐
                           ▼                 ▼
┌───────────────────────────────┐  ┌───────────────────────────┐
│  DynamoDB (STM)               │  │  Neo4j (LTM + RM)         │
│  - Conversation history       │  │  - POLE+O entities        │
│  - Agent state (Swarm)        │  │  - Decision provenance    │
│  - TTL: 7 days                │  │  - Persistent             │
└───────────────────────────────┘  └───────────────────────────┘
```

---

## Example Flow with Strands Swarm

### Scenario: Sales CRM Agent

**Turn 1:**
```
User: I met Sarah Chen from Acme Corp at AWS Summit. She's interested in our 
      enterprise tier.

Swarm Execution Flow:
  ┌──────────────────────────────────────────────────────────────┐
  │ 1. Extractor Agent (entry point)                             │
  │    - Receives: User message                                  │
  │    - Tool: extract_entities([                                │
  │        {name: "Sarah Chen", type: "Person"},                 │
  │        {name: "Acme Corp", type: "Organization"},            │
  │        {name: "AWS Summit", type: "Event"},                  │
  │        {name: "Enterprise Tier", type: "Object"}             │
  │      ])                                                      │
  │    - Stores in Neo4j: (Sarah)-[:WORKS_AT]->(Acme)           │
  │    - Handoff: → Query Agent                                  │
  └──────────────────────────────────────────────────────────────┘
  ┌──────────────────────────────────────────────────────────────┐
  │ 2. Query Agent                                               │
  │    - Receives: Extracted entities                            │
  │    - Tool: query_entities(entity_type="Person",             │
  │                           name="Sarah Chen")                 │
  │    - Returns: Existing Sarah Chen record (if any)           │
  │    - Handoff: → Response Agent                               │
  └──────────────────────────────────────────────────────────────┘
  ┌──────────────────────────────────────────────────────────────┐
  │ 3. Response Agent                                            │
  │    - Receives: Extracted entities + query results            │
  │    - Synthesizes: "Thanks for sharing! I've noted Sarah Chen │
  │      from Acme Corp. I'll remember her interest in our       │
  │      enterprise tier."                                       │
  │    - Returns: Final response to user                         │
  └──────────────────────────────────────────────────────────────┘

Agent Response: "Thanks for sharing! I've noted Sarah Chen from Acme Corp. 
                 I'll remember her interest in our enterprise tier."
```

**Turn 2 (days later):**
```
User: What companies are interested in our enterprise tier?

Swarm Execution Flow:
  ┌──────────────────────────────────────────────────────────────┐
  │ 1. Extractor Agent                                           │
  │    - No new entities to extract                              │
  │    - Handoff: → Query Agent                                  │
  └──────────────────────────────────────────────────────────────┘
  ┌──────────────────────────────────────────────────────────────┐
  │ 2. Query Agent                                               │
  │    - Tool: query_entities(entity_type="Organization")       │
  │    - Tool: query_relationships(relationship="INTERESTED_IN") │
  │    - Returns: Acme Corp (via Sarah Chen)                    │
  │    - Handoff: → Response Agent                               │
  └──────────────────────────────────────────────────────────────┘
  ┌──────────────────────────────────────────────────────────────┐
  │ 3. Response Agent                                            │
  │    - Synthesizes: "Based on our conversations, Acme Corp is  │
  │      interested (contact: Sarah Chen). We discussed this at  │
  │      AWS Summit."                                            │
  └──────────────────────────────────────────────────────────────┘

Agent Response: "Based on our conversations, Acme Corp is interested 
                 (contact: Sarah Chen). We discussed this at AWS Summit."
```

**Turn 3:**
```
User: Why did we reach out to Acme Corp?

Swarm Execution Flow:
  ┌──────────────────────────────────────────────────────────────┐
  │ 1. Extractor Agent                                           │
  │    - No extraction needed                                    │
  │    - Handoff: → Query Agent                                  │
  └──────────────────────────────────────────────────────────────┘
  ┌──────────────────────────────────────────────────────────────┐
  │ 2. Query Agent                                               │
  │    - Tool: query_entities(name="Acme Corp")                 │
  │    - Tool: query_relationships(entity="Acme Corp")          │
  │    - Returns: Created on 2026-05-10, Sarah Chen attended     │
  │      AWS Summit, interested in Enterprise Tier              │
  │    - Handoff: → Response Agent                               │
  └──────────────────────────────────────────────────────────────┘
  ┌──────────────────────────────────────────────────────────────┐
  │ 3. Response Agent                                            │
  │    - Synthesizes with provenance: "We logged Acme Corp       │
  │      because you mentioned meeting Sarah Chen from their     │
  │      team at AWS Summit on May 10th. She expressed interest  │
  │      in our enterprise tier."                                │
  └──────────────────────────────────────────────────────────────┘

Agent Response: "We logged Acme Corp because you mentioned meeting Sarah Chen 
                 from their team at AWS Summit on May 10th. She expressed 
                 interest in our enterprise tier."
```

**Key Swarm Features Demonstrated:**
- ✅ Automatic handoffs (no manual delegation)
- ✅ Shared working memory (all agents see previous results)
- ✅ Loop detection (prevents infinite Extractor → Query loops)
- ✅ Timeout protection (max 300s total, 60s per agent)

---

## Key Differences from Demo 01 & 06

### Demo 01: Static Graph-RAG
- **What:** Pre-built FAQ graph for retrieval
- **Use case:** "What's the hotel's cancellation policy?"
- **Limitation:** No memory of conversations, no entity extraction

### Demo 06: Production Agent
- **What:** AgentCore + Lambda tools + DynamoDB steering
- **Use case:** Book hotel with guardrails
- **Limitation:** No entity extraction, no context memory across sessions

### Demo 07: Context Graph Agent with Strands Swarm
- **What:** Three-memory architecture (STM + LTM + RM) + multi-agent orchestration
- **Pattern:** Strands Swarm with automatic handoffs (Extractor → Query → Response)
- **Use case:** "Remember Sarah from Acme Corp? What did we discuss?"
- **Advantage:** Context-aware across sessions, decision provenance, automatic agent routing with loop detection

---

## Use Cases

### 1. Sales CRM
- Extract companies, contacts, events from conversations
- Query: "Who attended AWS Summit and expressed interest in X?"
- Audit: "Why did we prioritize Acme Corp?"

### 2. Customer Support
- Track issues, resolutions, affected customers
- Query: "What problems has Acme Corp reported?"
- Audit: "When did we fix the authentication bug?"

### 3. Research Assistant
- Extract papers, authors, topics from discussions
- Query: "Who researches Graph-RAG and works at Amazon?"
- Audit: "How did we discover this paper?"

### 4. Meeting Notes
- Capture decisions, action items, attendees
- Query: "What did Sarah agree to deliver by Friday?"
- Audit: "Which meeting decided to use Neo4j?"

---

## Implementation Status Summary

**Phase 1:** ✅ DEPLOYED  
**Phase 2:** ✅ CODE READY — Infrastructure + agent code complete, ready to deploy

---

## Implementation Status

### ✅ Phase 1: Neo4j Infrastructure (DEPLOYED)
- [x] Research neo4j-labs/create-context-graph patterns
- [x] Research Strands framework capabilities
- [x] Design three-memory architecture
- [x] Document integration approach
- [x] Design Neo4j schema (POLE+O + reasoning graph)
- [x] Create CDK stack for Neo4j on ECS Fargate
- [x] Implement S3 backup automation (every 15 minutes)
- [x] Deploy Neo4j with Network Load Balancer
- [x] Implement seed_data Lambda (sample POLE+O entities)
- [x] Implement query_graph Lambda (Cypher queries)
- [x] Build Lambda layer with neo4j-agent-memory
- [x] Deploy to AWS (`Neo4jContextGraph` stack)
- [x] Verify Neo4j + Lambda connectivity

### 🚧 Phase 2: AgentCore Integration with Strands Swarm (Next)
- [x] Research Strands Swarm vs delegation pattern
- [x] Design DynamoDB tables (conversations + agent state)
- [x] Create Strands Swarm with 3 specialized agents
- [x] Create AgentCore Runtime stack (CDK for DynamoDB + IAM)
- [x] Integrate neo4j-agent-memory context_graph_tools
- [x] Configure STM_AND_LTM memory mode
- [x] Research bedrock-agentcore SDK and Runtime API
- [ ] Deploy AgentCore infrastructure (`cdk -a "python3 app_agentcore.py" deploy`)
- [ ] Deploy agent using Runtime.configure() from bedrock-agentcore-starter-toolkit
- [ ] Test end-to-end with sample conversations
- [ ] Measure context recall metrics

**Key Decisions:**
1. **Strands Swarm** vs manual delegation:
   - Built-in safeguards (max_handoffs, loop detection, timeouts)
   - Shared working memory across agents
   - Automatic handoff routing
   - Session persistence for interrupted workflows
   - Simpler code (~20 lines vs 247 lines)

2. **AgentCore Deployment:** Using `bedrock-agentcore-starter-toolkit.Runtime.configure()` instead of CDK L2 constructs (not available yet). CDK stack creates DynamoDB tables + IAM roles, then Runtime SDK deploys the agent container.

---

## How to Use (When Completed)

### Local Development
```bash
cd 07-context-graph-integration

# Install dependencies
uv venv && uv pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Add: OPENAI_API_KEY, NEO4J_URI, NEO4J_PASSWORD, AWS credentials

# Run local agent
uv run python context_agent_demo.py
```

### AWS Deployment
```bash
cd cdk

# Install CDK dependencies
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Deploy
cdk deploy ContextGraphStack

# Seed initial data (optional)
AWS_DEFAULT_REGION=us-east-1 uv run python ../seed_context_data.py

# Invoke agent
aws bedrock-agentcore invoke-agent-runtime \
    --agent-runtime-arn <ARN> \
    --payload "$(echo '{"prompt": "I met Sarah Chen..."}' | base64)" \
    --region us-east-1 /tmp/response.json
```

---

## Metrics to Measure

### Context Recall
- **Baseline (no LTM):** Agent forgets entities after conversation ends
- **With LTM:** Agent remembers entities across sessions
- **Measurement:** % of entities correctly recalled in follow-up questions

### Decision Auditability
- **Baseline (no RM):** "Why did you do X?" → No traceable reason
- **With RM:** Full provenance graph from input → reasoning → action → outcome
- **Measurement:** % of decisions that can be traced to original context

### Entity Extraction Accuracy
- **Baseline:** Manual tagging or no extraction
- **With extract_entities:** LLM-powered POLE+O extraction
- **Measurement:** Precision/Recall vs ground truth annotations

---

## Technical Considerations

### Why Neo4j AuraDB?
- Native Cypher support (mature ecosystem)
- Free tier available
- Compatibility with Demo 01 (SimpleKGPipeline)
- neo4j-labs tooling designed for AuraDB

### Why DynamoDB for Short-Term Memory?
- Fast retrieval of recent conversations
- Serverless (no management overhead)
- TTL support (auto-expire old conversations)
- Cost-effective for high-throughput reads/writes

### Why Separate Long-Term + Reasoning Memory?
- **Long-term:** Optimized for entity queries (MATCH patterns)
- **Reasoning:** Optimized for decision traces (temporal chains)
- Could be separate Neo4j databases or different node label namespaces

---

## Cost Estimate (10K conversations/month)

**Compute:**
- AgentCore Runtime: ~$50/month
- 3 Lambda functions @ 256MB, 1s avg: ~$15/month

**Data:**
- Neo4j AuraDB Free: $0 (pauses when idle)
- DynamoDB (10K items × 5KB): ~$0.50/month

**LLM:**
- Entity extraction (GPT-4o-mini): ~$30/month
- Context queries: Minimal (Cypher queries, no LLM calls)

**Total: ~$95/month** (vs $180/month for Demo 06 with full booking flow)

---

## References

- **neo4j-labs/create-context-graph:** https://github.com/neo4j-labs/create-context-graph
- **Strands Agents:** https://docs.strands-agents.dev
- **POLE Model:** Person, Organization, Location, Event extraction standard
- **Demo 01:** Graph-RAG baseline (static FAQ graph)
- **Demo 06:** Production AgentCore patterns (MCP, steering, DynamoDB)

---

## Key Insights

1. **Three memories > one memory**
   - Short-term: Avoids re-reading entire conversation history
   - Long-term: Structured entities enable precise queries
   - Reasoning: Decision provenance enables "why did you do X?" questions

2. **Live extraction > static graphs**
   - Demo 01 requires pre-building FAQ graph
   - Demo 07 extracts entities during conversation
   - Result: Knowledge graph grows with usage

3. **Provenance graphs enable trust**
   - "Why did you book this hotel?" → Trace back to user preference
   - "How do you know Sarah works at Acme?" → Link to original conversation
   - Critical for regulated industries (healthcare, finance)

4. **Strands hooks enable cross-cutting concerns**
   - AfterToolCallEvent → log every decision (no tool changes needed)
   - BeforeToolCallEvent → validate steering rules
   - Result: Tools remain pure, hooks handle observability + compliance

---

**Status:** Architecture designed, implementation in progress  
**Next:** Build local prototype → Deploy CDK stack → Measure context recall metrics
