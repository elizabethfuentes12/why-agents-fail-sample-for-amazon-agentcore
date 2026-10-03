# Demo 07: Arquitectura Correcta (Context Graph + AgentCore Memory + Neo4j ECS)

## ✅ Lo que aprendí de tu workshop

### **AgentCore Memory se integra NATIVAMENTE con Strands**
- NO necesita Lambdas para acceder
- Strands tiene `AgentCoreMemorySessionManager` built-in
- Memory extraction es **asíncrona** (60-90s después de invocación)

### **Neo4j en ECS/Fargate**
- CloudFormation stacks: foundation → build → service
- NLB provee endpoint estable
- Dump/restore workflow para pre-populate
- 2048 CPU / 4096 MEM sufficient

---

## 🎯 Arquitectura Final Demo 07

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
│  │  - Tools via MCP Gateway                                  │ │
│  │  - Hooks: BeforeToolCallEvent, AfterToolCallEvent        │ │
│  └───────────────────────────────────────────────────────────┘ │
└────────────┬────────────────────┬───────────────────────────────┘
             │                     │
             │ STM + LTM          │ MCP Tools
             ▼                     ▼
┌──────────────────────┐  ┌─────────────────────────────────────┐
│  AgentCore Memory    │  │    Lambda Tools (via MCP Gateway)   │
│  (Managed Service)   │  │  ┌───────────────────────────────┐ │
│                      │  │  │ extract_entities              │ │
│  Namespaces:         │  │  │ → Reads AgentCore Memory STM  │ │
│  /users/{actor}/     │  │  │ → Extracts POLE+O             │ │
│    preferences       │  │  │ → Writes to Neo4j             │ │
│  /users/{actor}/     │  │  └───────────────────────────────┘ │
│    facts             │  │  ┌───────────────────────────────┐ │
│                      │  │  │ query_context                 │ │
│  Strategies:         │  │  │ → Cypher queries on Neo4j     │ │
│  - User Preference   │  │  └───────────────────────────────┘ │
│  - Semantic Memory   │  │  ┌───────────────────────────────┐ │
│                      │  │  │ log_decision                  │ │
│  Memory Mode:        │  │  │ → Decision provenance to Neo4j│ │
│  STM_AND_LTM         │  │  └───────────────────────────────┘ │
└──────────────────────┘  └──────────────┬──────────────────────┘
                                         │
                                         ▼
                          ┌──────────────────────────────────────┐
                          │   Neo4j (ECS Fargate + NLB)          │
                          │                                      │
                          │  LONG-TERM MEMORY:                   │
                          │  - Entities (POLE+O)                 │
                          │  - Relationships (WORKS_AT, etc)     │
                          │                                      │
                          │  REASONING MEMORY:                   │
                          │  - Decision nodes                    │
                          │  - Provenance chains                 │
                          │  - memory_record_id (link to Memory) │
                          └──────────────────────────────────────┘
```

---

## 🔑 Three-Memory Architecture (Corregida)

| Memory Type | Storage | Managed By | Purpose | TTL |
|-------------|---------|------------|---------|-----|
| **SHORT-TERM** | AgentCore Memory | AWS (managed) | Conversation turns within session | Session lifetime |
| **LONG-TERM (Facts)** | AgentCore Memory + Neo4j | AWS + Custom | User preferences + Entity graph | Permanent |
| **REASONING** | Neo4j | Custom | Decision provenance, tool traces | Permanent |

### **Diferencia clave:**

**AgentCore Memory STM/LTM:**
- STM: Raw conversation ("User: I met Sarah Chen...")
- LTM: **Extracted strategies** ("User prefers 4-star hotels")
- **NO structured entities** (no POLE+O graph)
- Text-only semantic search

**Neo4j:**
- **Structured entities:** `(Person {name: "Sarah Chen"})-[:WORKS_AT]->(Organization {name: "Acme Corp"})`
- **Graph traversal:** "Who attended AWS Summit and works at Acme?"
- **Decision provenance:** `(Decision)-[:CREATED]->(Entity)`

---

## 🛠️ Integración Strands + AgentCore Memory (Sin Lambdas)

### **Código del Agent Runtime:**

```python
# agent_files/context_agent.py
import os
from strands import Agent
from strands.models.openai import OpenAIModel
from strands.tools.mcp.mcp_client import MCPClient
from bedrock_agentcore import BedrockAgentCoreApp
from bedrock_agentcore.memory import (
    AgentCoreMemoryConfig,
    AgentCoreMemorySessionManager,
    RetrievalConfig,
    RequestContext
)

app = BedrockAgentCoreApp()

@app.entrypoint
def invoke(payload, context=None):
    # 1. Extract actor_id from request headers
    request_context = RequestContext(context)
    actor_id = request_context.request_headers.get(
        "x-amzn-bedrock-agentcore-runtime-custom-actor-id",
        "default-user"
    )
    
    # 2. Configure AgentCore Memory
    memory_config = AgentCoreMemoryConfig(
        memory_id=os.environ["BEDROCK_AGENTCORE_MEMORY_ID"],
        actor_id=actor_id,
        retrieval_config={
            "/users/{actor_id}/preferences": RetrievalConfig(top_k=5, relevance_score=0.7),
            "/users/{actor_id}/facts": RetrievalConfig(top_k=10, relevance_score=0.6)
        }
    )
    
    # 3. Create Session Manager (handles STM + LTM automatically)
    session_manager = AgentCoreMemorySessionManager(
        memory_config=memory_config,
        memory_mode="STM_AND_LTM"  # Enable both short-term and long-term
    )
    
    # 4. Create Agent with memory
    model = OpenAIModel(model_id="gpt-4o-mini", client_args={"api_key": get_openai_key()})
    
    # Discover tools from MCP Gateway
    mcp_client = MCPClient(lambda: streamablehttp_client(os.environ["GATEWAY_URL"]))
    with mcp_client:
        tools = mcp_client.list_tools_sync()
        
        agent = Agent(
            model=model,
            tools=tools,
            system_prompt=SYSTEM_PROMPT,
            session_manager=session_manager,  # Memory integration here
            hooks=[DecisionProvenanceHook()]
        )
        
        # 5. Invoke agent
        prompt = payload if isinstance(payload, str) else payload.get("prompt", "")
        result = agent(prompt)
        return str(result)
```

**Flujo automático:**
1. AgentCore Memory **automáticamente** inyecta STM (conversation history) en el prompt
2. AgentCore Memory **automáticamente** inyecta LTM (strategies) en el prompt
3. Agent procesa con full context
4. AgentCore Memory **asíncronamente** extrae strategies (60-90s después)

---

## 📦 CDK Stacks

### **Stack 1: Neo4j Foundation**
```python
# cdk/neo4j_foundation_stack.py
class Neo4jFoundationStack(Stack):
    def __init__(self, scope, id, *, vpc, **kwargs):
        super().__init__(scope, id, **kwargs)
        
        # Secret for Neo4j password
        self.neo4j_secret = secretsmanager.Secret(
            self, "Neo4jSecret",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                password_length=20,
                exclude_punctuation=True
            )
        )
        
        # S3 bucket for graph dumps
        self.dump_bucket = s3.Bucket(
            self, "GraphDumpBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            lifecycle_rules=[s3.LifecycleRule(expiration=Duration.days(30))]
        )
        
        # Security Group (Bolt port 7687)
        self.security_group = ec2.SecurityGroup(
            self, "Neo4jSecurityGroup",
            vpc=vpc,
            description="Neo4j Bolt access",
            allow_all_outbound=True
        )
        self.security_group.add_ingress_rule(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(7687),
            "Neo4j Bolt from anywhere"
        )
        
        # ECS Cluster
        self.cluster = ecs.Cluster(self, "Neo4jCluster", vpc=vpc)
        
        # IAM Roles
        self.task_role = iam.Role(
            self, "Neo4jTaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            inline_policies={
                "S3AndBedrock": iam.PolicyDocument(statements=[
                    iam.PolicyStatement(
                        actions=["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
                        resources=[self.dump_bucket.bucket_arn, f"{self.dump_bucket.bucket_arn}/*"]
                    ),
                    iam.PolicyStatement(
                        actions=["bedrock:InvokeModel"],
                        resources=["*"]
                    ),
                    iam.PolicyStatement(
                        actions=["secretsmanager:GetSecretValue"],
                        resources=[self.neo4j_secret.secret_arn]
                    )
                ])
            }
        )
```

### **Stack 2: Neo4j Service (Fargate)**
```python
# cdk/neo4j_service_stack.py
class Neo4jServiceStack(Stack):
    def __init__(self, scope, id, *, foundation: Neo4jFoundationStack, vpc, **kwargs):
        super().__init__(scope, id, **kwargs)
        
        # Task Definition
        task_def = ecs.FargateTaskDefinition(
            self, "Neo4jTask",
            cpu=2048,
            memory_limit_mib=4096,
            ephemeral_storage_gib=21,
            task_role=foundation.task_role
        )
        
        # Container: Neo4j
        neo4j_container = task_def.add_container(
            "neo4j",
            image=ecs.ContainerImage.from_registry("neo4j:2026.01-enterprise"),
            port_mappings=[ecs.PortMapping(container_port=7687, protocol=ecs.Protocol.TCP)],
            environment={
                "NEO4J_ACCEPT_LICENSE_AGREEMENT": "yes",
                "DUMP_BUCKET": foundation.dump_bucket.bucket_name
            },
            secrets={
                "NEO4J_PASSWORD": ecs.Secret.from_secrets_manager(foundation.neo4j_secret)
            },
            logging=ecs.LogDrivers.aws_logs(stream_prefix="neo4j"),
            entry_point=["/bin/bash", "-c"],
            command=[
                """
                set -e
                # Download dump from S3
                aws s3 cp s3://$DUMP_BUCKET/neo4j-graph.dump /tmp/neo4j-graph.dump
                
                # Load database
                neo4j-admin database load neo4j --from-stdin --overwrite-destination=true < /tmp/neo4j-graph.dump
                
                # Configure + start
                echo "server.default_listen_address=0.0.0.0" >> /var/lib/neo4j/conf/neo4j.conf
                neo4j-admin dbms set-initial-password "$NEO4J_PASSWORD"
                exec neo4j console
                """
            ]
        )
        
        # NLB
        nlb = elbv2.NetworkLoadBalancer(
            self, "Neo4jNLB",
            vpc=vpc,
            internet_facing=True
        )
        
        target_group = nlb.add_listener(
            "BoltListener",
            port=7687,
            protocol=elbv2.Protocol.TCP
        ).add_targets(
            "Neo4jTarget",
            port=7687,
            targets=[]  # Service will register itself
        )
        
        # ECS Service
        service = ecs.FargateService(
            self, "Neo4jService",
            cluster=foundation.cluster,
            task_definition=task_def,
            desired_count=1,
            assign_public_ip=True,
            security_groups=[foundation.security_group]
        )
        
        # Attach to NLB
        service.attach_to_network_target_group(target_group)
        
        # Output
        CfnOutput(self, "Neo4jBoltEndpoint", value=f"bolt://{nlb.load_balancer_dns_name}:7687")
```

### **Stack 3: AgentCore Memory**
```python
# cdk/agentcore_memory_stack.py
import aws_cdk.aws_bedrockagentcore as agentcore

class AgentCoreMemoryStack(Stack):
    def __init__(self, scope, id, *, role_arn, **kwargs):
        super().__init__(scope, id, **kwargs)
        
        # AgentCore Memory Resource
        self.memory = agentcore.CfnMemory(
            self, "ContextGraphMemory",
            name="ContextGraphMemory",
            description="Short-term + long-term memory for context graph agent",
            event_expiry_duration=2592000,  # 30 days
            memory_strategies=[
                agentcore.CfnMemory.MemoryStrategyProperty(
                    user_preference_memory_strategy=agentcore.CfnMemory.UserPreferenceMemoryStrategyProperty(
                        name="user-preferences",
                        namespaces=["/users/{actor_id}/preferences"]
                    )
                ),
                agentcore.CfnMemory.MemoryStrategyProperty(
                    semantic_memory_strategy=agentcore.CfnMemory.SemanticMemoryStrategyProperty(
                        name="semantic-facts",
                        namespaces=["/users/{actor_id}/facts"]
                    )
                )
            ],
            memory_execution_role_arn=role_arn
        )
        
        CfnOutput(self, "MemoryId", value=self.memory.attr_memory_id)
```

### **Stack 4: AgentCore Runtime + Gateway**
```python
# cdk/agentcore_runtime_stack.py
class AgentCoreRuntimeStack(Stack):
    def __init__(self, scope, id, *, memory: CfnMemory, **kwargs):
        super().__init__(scope, id, **kwargs)
        
        # Runtime
        runtime = agentcore.CfnRuntime(
            self, "ContextGraphRuntime",
            name="ContextGraphRuntime",
            execution_role_arn=role_arn,
            runtime_configuration=agentcore.CfnRuntime.RuntimeConfigurationProperty(
                entry_point="agent_files/context_agent.py",
                environment_variables=[
                    {"key": "BEDROCK_AGENTCORE_MEMORY_ID", "value": memory.attr_memory_id},
                    {"key": "GATEWAY_URL", "value": gateway_url},
                    {"key": "OPENAI_KEY_SECRET_ARN", "value": openai_secret_arn}
                ]
            ),
            tracing_configuration=agentcore.CfnRuntime.TracingConfigurationProperty(enabled=True)
        )
```

---

## 🔄 Data Flow Example

### **Turn 1: Initial Contact**
```
User → AgentCore Runtime
  Headers: x-amzn-bedrock-agentcore-runtime-custom-actor-id: user-abc123
  Body: "I met Sarah Chen from Acme Corp at AWS Summit. She's interested in our enterprise tier."

AgentCore Runtime:
  1. AgentCoreMemorySessionManager creates session (if first message)
  2. Retrieves LTM strategies for actor_id="user-abc123" (empty, first time)
  3. Agent processes with STM (empty) + LTM (empty)
  4. Agent calls extract_entities Lambda (via MCP)
  
extract_entities Lambda:
  1. Queries AgentCore Memory for recent STM (gets raw conversation)
  2. Extracts: Person(Sarah Chen), Organization(Acme Corp), Event(AWS Summit)
  3. Stores in Neo4j:
     CREATE (p:Person {name: "Sarah Chen"})
     CREATE (o:Organization {name: "Acme Corp"})
     CREATE (e:Event {name: "AWS Summit"})
     CREATE (p)-[:WORKS_AT]->(o)
     CREATE (p)-[:ATTENDED]->(e)

Agent responds: "Thanks! I've noted Sarah Chen from Acme Corp. I'll remember she's interested in our enterprise tier."

[60-90 seconds later, asynchronously]
  AgentCore Memory extracts strategies:
    /users/user-abc123/facts: "Contact: Sarah Chen, Organization: Acme Corp"
    /users/user-abc123/preferences: "Interested in enterprise tier"
```

### **Turn 2: Recall (Same Actor, New Session)**
```
User → AgentCore Runtime
  Headers: x-amzn-bedrock-agentcore-runtime-custom-actor-id: user-abc123
  Body: "What companies are interested in our enterprise tier?"

AgentCore Runtime:
  1. Retrieves LTM strategies for actor_id="user-abc123"
     → Returns: ["Contact: Sarah Chen, Organization: Acme Corp", "Interested in enterprise tier"]
  2. Injects LTM strategies into prompt automatically
  3. Agent processes with context

Agent calls query_context Lambda:
  MATCH (p:Person)-[:INTERESTED_IN]->(prod:Product {name: "Enterprise Tier"})
  MATCH (p)-[:WORKS_AT]->(o:Organization)
  RETURN o.name, p.name

Agent responds: "Based on our previous conversations, Acme Corp is interested (contact: Sarah Chen)."
```

---

## 📊 Comparison: This vs create-context-graph

| Feature | create-context-graph | Demo 07 (Ours) |
|---------|---------------------|----------------|
| **Short-term memory** | Neo4j Message nodes | AgentCore Memory STM |
| **Long-term memory** | Neo4j Entity graph | AgentCore Memory LTM + Neo4j entities |
| **Reasoning memory** | Neo4j Decision traces | Neo4j decision provenance |
| **Agent framework** | 8 options (PydanticAI, LangGraph, etc.) | Strands (AWS-native) |
| **Deployment** | Local (Docker/Aura) | AWS production (ECS, AgentCore) |
| **Memory extraction** | Manual via neo4j-agent-memory lib | Automatic via AgentCore |
| **Neo4j hosting** | AuraDB managed | ECS Fargate (self-managed) |
| **Frontend** | Next.js + graph viz | API-only (future: add UI) |

---

## ✅ Benefits of This Architecture

1. **No DynamoDB conversations** — AgentCore Memory handles STM
2. **No Lambda for memory access** — Strands integrates natively
3. **Async strategy extraction** — AWS manages background processing
4. **Actor-based isolation** — Each user gets separate memory namespace
5. **Neo4j in ECS** — Full control, no AuraDB auto-pause issues
6. **Graph persistence** — Dump/restore workflow for reproducibility

---

## 🚀 Next Steps

1. ✅ Port CloudFormation templates to CDK
2. ✅ Implement `extract_entities` Lambda
3. ✅ Implement `query_context` Lambda
4. ✅ Implement `log_decision` Lambda
5. ✅ Configure AgentCore Memory with strategies
6. ✅ Test STM_AND_LTM flow
7. ✅ Measure memory extraction latency (60-90s)
8. ✅ Add observability (X-Ray + Neo4j provenance)

---

**Status:** Architecture finalizada, lista para CDK implementation.
