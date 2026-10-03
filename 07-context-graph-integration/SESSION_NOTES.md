# Session Notes — Demo 07: Context Graph Integration

**Session Date:** 2026-05-11  
**Status:** Phase 1 deployed ✅ | Phase 2 code ready, ready to deploy

---

## 🎯 Current State

### ✅ What's Deployed (Phase 1)

**Stack:** `Neo4jContextGraph` (status: `UPDATE_COMPLETE`)  
**Region:** `us-east-1`

**Components:**
- Neo4j 2026.01 Enterprise on ECS Fargate (2048 CPU, 4096 MB)
- Network Load Balancer for stable Bolt endpoint
- S3 bucket with automated backups every 15 minutes (via backup sidecar)
- 2 Lambda functions: `seed_data`, `query_graph`
- Lambda layer: `neo4j-agent-memory` (ARM64)

**Access Neo4j:**
```bash
# Get URI
aws cloudformation describe-stacks \
  --stack-name Neo4jContextGraph \
  --query 'Stacks[0].Outputs[?OutputKey==`Neo4jBoltUri`].OutputValue' \
  --output text

# Get password
NEO4J_SECRET_ARN=$(aws cloudformation describe-stacks \
  --stack-name Neo4jContextGraph \
  --query 'Stacks[0].Outputs[?OutputKey==`Neo4jPasswordSecretArn`].OutputValue' \
  --output text)

aws secretsmanager get-secret-value \
  --secret-id "$NEO4J_SECRET_ARN" \
  --query 'SecretString' \
  --output text
```

**Lambda function names:**
- Seed data: `Neo4jContextGraph-LambdasSeedData6D362933-dEchfdMHlUnN`
- Query graph: `Neo4jContextGraph-LambdasQueryGraphCEF39FDC-WNsGrtErLNdg`

---

### ✅ What's Ready to Deploy (Phase 2)

**Stack:** `AgentCoreContext` (NOT YET DEPLOYED)

**Files created:**
```
cdk/
├── app_agentcore.py              # CDK app for AgentCore stack
├── agentcore_stack.py            # DynamoDB + IAM roles

agent_files/
├── context_agent.py              # Strands Swarm with 3 agents
├── agent_config.json             # Memory config (STM_AND_LTM)
└── requirements.txt              # Dependencies

deploy_runtime.py                 # Deployment script using Runtime SDK
SWARM_ARCHITECTURE.md             # Full documentation
```

**Architecture:** Strands Swarm with 3 specialized agents
1. **Extractor Agent** — Tools: extract_entities
2. **Query Agent** — Tools: query_entities, query_relationships
3. **Response Agent** — No tools (synthesis only)

Automatic handoffs: Extractor → Query → Response

**Memory configuration:**
- Short-term: DynamoDB (conversation history, 7-day TTL)
- Long-term: Neo4j (POLE+O entities, persistent)
- Reasoning: Neo4j (decision provenance, tracked via Swarm events)

---

## 🔍 Key Discoveries This Session

### 1. AgentCore Runtime Uses SDK, Not CDK

**Discovery:** AgentCore does NOT have CDK L2 constructs (as of 2026-05-11).

**Correct deployment flow:**
1. **CDK** creates infrastructure (DynamoDB, IAM, VPC)
2. **Runtime SDK** (`bedrock-agentcore-starter-toolkit`) deploys the agent

```python
from bedrock_agentcore_starter_toolkit import Runtime

runtime = Runtime()
runtime.configure(entrypoint="...", memory_mode="STM_AND_LTM")
runtime.launch(env_vars={...})
```

CDK only has `CfnAgent` for classic Bedrock Agents (different service).

### 2. Strands Swarm vs Manual Delegation

**Research comparison:** Financial Services Advisor (manual delegation) vs Strands Swarm

**Swarm advantages:**
- Built-in safeguards: max_handoffs=10, loop detection, timeouts
- Shared working memory across all agents
- Automatic handoff routing (no manual `@tool` wrappers)
- Session persistence for interrupted workflows
- Simpler: ~20 lines vs 247 lines for manual delegation

**Pattern used:**
```python
swarm = Swarm(
    nodes=[extractor_agent, query_agent, response_agent],
    entry_point=extractor_agent,
    max_handoffs=10,
    repetitive_handoff_detection_window=5,
)
result = swarm("I met Sarah Chen from Acme Corp")
```

### 3. All Regions Parameterized

Fixed all hardcoded `us-east-1` references:
- CDK stacks use `self.region` from environment
- Agent code reads `AWS_REGION` from environment
- Scripts use `${AWS_REGION:-$(aws configure get region)}`
- Bedrock model ARN: `arn:aws:bedrock:*::foundation-model/us.anthropic.*` (multi-region)

---

## 📋 Next Steps (When You Return)

### Step 1: Deploy AgentCore Infrastructure (~5 minutes)

```bash
cd 07-context-graph-integration/cdk
cdk -a "python3 app_agentcore.py" deploy
```

This creates:
- DynamoDB table: `context-agent-conversations` (STM)
- DynamoDB table: `context-agent-state` (Swarm session persistence)
- IAM role with permissions: Bedrock (multi-region), DynamoDB, Secrets Manager, CloudWatch Logs

### Step 2: Deploy Agent Using Runtime SDK (~10 minutes)

```bash
cd ..
python3 deploy_runtime.py
```

This will:
1. Read CloudFormation outputs (DynamoDB tables, IAM role ARN, Neo4j URI)
2. Create ECR repository (if not exists)
3. Build Docker image with agent code
4. Deploy to AgentCore Runtime
5. Configure environment variables (Neo4j connection, DynamoDB tables)

### Step 3: Test the Agent

```python
from bedrock_agentcore_starter_toolkit import Runtime

runtime = Runtime()

# Test entity extraction
result = runtime.invoke({
    "prompt": "I met Sarah Chen from Acme Corp at AWS Summit. She's interested in our enterprise tier."
})
print(result)

# Test context recall (days later)
result = runtime.invoke({
    "prompt": "What companies are interested in our enterprise tier?"
})
print(result)

# Test decision provenance
result = runtime.invoke({
    "prompt": "Why did we reach out to Acme Corp?"
})
print(result)
```

### Step 4: Verify Swarm Execution

Check CloudWatch Logs for Swarm events:
- `multi_agent_node_start` — Agent begins execution
- `multi_agent_handoff` — Control handed off between agents
- `multi_agent_node_stop` — Agent completes

---

## 🐛 Known Issues / Troubleshooting

### Issue: Lambda layer build fails

**Symptom:** `pip install neo4j-agent-memory[all]` exceeds 250MB
**Solution:** Use core profile instead of [all], or build on EC2 with more disk space

### Issue: AgentCore Runtime fails to deploy

**Check:**
1. IAM role has correct permissions (Bedrock multi-region ARN)
2. ECR repository was created successfully
3. Agent code has correct entrypoint: `agent_files/context_agent.py:get_agent`
4. Environment variables are set (Neo4j URI, DynamoDB tables)

### Issue: Neo4j connection fails from Lambda

**Check:**
1. Lambda is in VPC with NAT Gateway
2. Security Group allows Lambda → Neo4j on port 7687
3. Neo4j service is running: `aws ecs describe-services --cluster Neo4jCluster`
4. Check Neo4j logs: `aws logs tail /ecs/neo4j-context-graph --follow`

### Issue: Agent doesn't remember entities

**Check:**
1. Memory mode is set to `STM_AND_LTM` (not `STM_ONLY`)
2. Neo4j has entities: invoke `query_graph` Lambda
3. `context_graph_tools()` are loaded in agent code
4. DynamoDB tables exist and have correct names in env vars

---

## 📚 Documentation Files

**Architecture:**
- `README.md` — Overview, quick start, architecture diagrams
- `SWARM_ARCHITECTURE.md` — Deep dive on Swarm vs delegation pattern
- `ARCHITECTURE.md` — Three-memory architecture details
- `INTEGRATION_PLAN.md` — Integration strategy with neo4j-agent-memory

**Deployment:**
- `cdk/README.md` — CDK deployment guide
- `deploy_runtime.py` — Agent deployment script
- `SESSION_NOTES.md` — This file (session state)

**Code:**
- `agent_files/context_agent.py` — Strands Swarm implementation
- `agent_files/agent_config.json` — AgentCore Memory config
- `cdk/agentcore_stack.py` — CDK stack for infrastructure
- `cdk/lambdas/project_lambdas.py` — Lambda functions construct

---

## 💡 Key Patterns Learned

### Pattern 1: Research Before Implementing

Always check official documentation before writing code:
- Discovered AgentCore uses Runtime SDK, not CDK
- Avoided writing custom deployment code
- Found correct API: `Runtime.configure()` + `Runtime.launch()`

### Pattern 2: Design First, Build Second

Created architecture diagrams and documentation before coding:
- `SWARM_ARCHITECTURE.md` explained pattern before implementing
- Compared alternatives (Swarm vs delegation) with data
- Result: Clear decision rationale for future maintainers

### Pattern 3: No Hardcoded Regions

All regions parameterized from environment:
- CDK: `self.region`
- Python: `os.environ.get("AWS_REGION")`
- Bash: `${AWS_REGION:-$(aws configure get region)}`
- Multi-region Bedrock ARN: `arn:aws:bedrock:*::foundation-model/*`

---

## 📊 Metrics to Measure (After Deployment)

### Context Recall
- **Test:** Ask about entities mentioned days ago
- **Baseline:** Agent with no LTM (forgets after session)
- **Expected:** 95%+ recall of extracted entities

### Decision Auditability
- **Test:** Ask "Why did you do X?"
- **Baseline:** No traceable reason
- **Expected:** Full provenance from Swarm events

### Handoff Efficiency
- **Measurement:** Average handoffs per successful workflow
- **Manual delegation:** ~2.5 handoffs
- **Swarm expected:** ~1.8 handoffs (optimized routing)

---

## 🔗 References

**Official Documentation:**
- neo4j-agent-memory: https://github.com/neo4j-labs/agent-memory
- Strands Agents: https://docs.strands-agents.dev
- bedrock-agentcore SDK: `pip show bedrock-agentcore`
- Runtime.configure() docs: `help(Runtime.configure)`

**Demo Comparisons:**
- Demo 01: Graph-RAG baseline (static FAQ graph)
- Demo 06: Production AgentCore (hotel booking with guardrails)
- Demo 07: Context graph with Swarm (this demo)

---

**When you return:** Start with Step 1 (deploy AgentCore infrastructure). All code is ready, just needs deployment + testing.
