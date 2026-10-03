# Architecture: Context Graph Integration

## Overview

This document details the technical architecture for Demo 07, which implements a **three-memory architecture** combining concepts from neo4j-labs/create-context-graph with AWS production patterns from Demo 06.

---

## System Architecture

**CRITICAL: AgentCore Runtime is STATELESS**
- Each `invoke-agent-runtime` call creates a fresh agent
- NO conversation_id, session_id, or built-in history management
- Client MUST format full conversation history into the prompt
- DynamoDB Conversations is for CLIENT retrieval, not for AgentCore

```
┌────────────────────────────────────────────────────────────────────────┐
│                    CONVERSATION ORCHESTRATOR                           │
│                     (NEW: Stateful Wrapper)                            │
│                                                                        │
│  Responsibilities:                                                     │
│  1. Retrieve conversation history from DynamoDB Conversations          │
│  2. Format history + new user prompt into full context                │
│  3. Invoke AgentCore Runtime with formatted prompt                    │
│  4. Store new messages (user + agent) in DynamoDB                     │
│                                                                        │
│  Implementation Options:                                               │
│  - Lambda function (conversation_orchestrator_lambda.py)              │
│  - Client SDK (for CLI/Web UI)                                        │
│  - API Gateway + Lambda (for HTTP API)                                │
└─────────────────────────────┬──────────────────────────────────────────┘
                              │ Formatted prompt with full history
                              ▼
┌────────────────────────────────────────────────────────────────────────┐
│                  AGENTCORE RUNTIME LAYER (STATELESS)                   │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │  Strands Agent with Context Hooks                                │ │
│  │                                                                  │ │
│  │  Created FRESH on every invocation (no memory)                   │ │
│  │                                                                  │ │
│  │  System Prompt:                                                  │ │
│  │  "You are a context-aware assistant. Extract entities from       │ │
│  │   conversations, query your knowledge graph for context, and     │ │
│  │   maintain decision provenance."                                 │ │
│  │                                                                  │ │
│  │  Hooks:                                                          │ │
│  │  - BeforeToolCallEvent → Validate steering rules (DynamoDB)     │ │
│  │  - AfterToolCallEvent → Log decision provenance (Neo4j)         │ │
│  └──────────────────────────────────────────────────────────────────┘ │
│                                                                        │
│  Container Lifecycle (warm 15min, max 8hr) - NOT conversation sessions│
└─────────────────────────────┬──────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────────┐
│                    TOOL DISCOVERY LAYER                                │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │  AgentCore Gateway (MCP Server)                                  │ │
│  │  - Exposes Lambda tools via Model Context Protocol              │ │
│  │  - Semantic tool filtering (future: reduce 20 tools → 3-5)      │ │
│  │  - Tool metadata: name, description, parameters                 │ │
│  └──────────────────────────────────────────────────────────────────┘ │
│                                                                        │
└─────────────────────────────┬──────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────────┐
│                      TOOL EXECUTION LAYER                              │
│                                                                        │
│  ┌─────────────────────┐  ┌─────────────────────┐  ┌───────────────┐ │
│  │  extract_entities   │  │   query_context     │  │ log_decision  │ │
│  │     (Lambda)        │  │      (Lambda)       │  │   (Lambda)    │ │
│  │                     │  │                     │  │               │ │
│  │ Input:              │  │ Input:              │  │ Input:        │ │
│  │ - user_message      │  │ - cypher_query OR   │  │ - tool_name   │ │
│  │ - conversation_id   │  │ - natural_language  │  │ - parameters  │ │
│  │                     │  │   question          │  │ - result      │ │
│  │ Output:             │  │                     │  │ - timestamp   │ │
│  │ - entities[]        │  │ Output:             │  │               │ │
│  │   (POLE+O model)    │  │ - query_results     │  │ Output:       │ │
│  │ - relationships[]   │  │ - context_summary   │  │ - decision_id │ │
│  └──────────┬──────────┘  └──────────┬──────────┘  └───────┬───────┘ │
│             │                         │                     │         │
└─────────────┼─────────────────────────┼─────────────────────┼─────────┘
              │                         │                     │
              │                         │                     │
              ▼                         ▼                     ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        STORAGE LAYER                                   │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │                    Neo4j AuraDB                                  │ │
│  │                                                                  │ │
│  │  ┌───────────────────────────┐  ┌──────────────────────────┐   │ │
│  │  │    LONG-TERM MEMORY       │  │   REASONING MEMORY       │   │ │
│  │  │                           │  │                          │   │ │
│  │  │  Node Labels:             │  │  Node Labels:            │   │ │
│  │  │  - Person                 │  │  - Decision              │   │ │
│  │  │  - Organization           │  │  - ToolCall              │   │ │
│  │  │  - Location               │  │  - Outcome               │   │ │
│  │  │  - Event                  │  │                          │   │ │
│  │  │  - Object (custom)        │  │  Relationships:          │   │ │
│  │  │                           │  │  - INPUT                 │   │ │
│  │  │  Relationships:           │  │  - CREATED               │   │ │
│  │  │  - WORKS_AT               │  │  - RESULTED_IN           │   │ │
│  │  │  - ATTENDED               │  │  - FOLLOWED_BY           │   │ │
│  │  │  - INTERESTED_IN          │  │  - CAUSED_BY             │   │ │
│  │  │  - LOCATED_IN             │  │                          │   │ │
│  │  └───────────────────────────┘  └──────────────────────────┘   │ │
│  │                                                                  │ │
│  │  Indexes:                                                        │ │
│  │  - Person.name (text)                                            │ │
│  │  - Organization.name (text)                                      │ │
│  │  - Decision.timestamp (datetime)                                 │ │
│  │                                                                  │ │
│  │  Constraints:                                                    │ │
│  │  - Person.id (unique)                                            │ │
│  │  - Organization.id (unique)                                      │ │
│  │  - Decision.id (unique)                                          │ │
│  └──────────────────────────────────────────────────────────────────┘ │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐ │
│  │                    Amazon DynamoDB                               │ │
│  │                                                                  │ │
│  │  ┌───────────────────────────┐  ┌──────────────────────────┐   │ │
│  │  │   SHORT-TERM MEMORY       │  │   Steering Rules         │   │ │
│  │  │   (Conversations table)    │  │   (Controls table)       │   │ │
│  │  │                           │  │                          │   │ │
│  │  │  PK: conversation_id      │  │  PK: rule_id             │   │ │
│  │  │  SK: message_timestamp    │  │                          │   │ │
│  │  │                           │  │  Attributes:             │   │ │
│  │  │  Attributes:              │  │  - tool_name             │   │ │
│  │  │  - role (user/assistant)  │  │  - condition (Python)    │   │ │
│  │  │  - content (text)         │  │  - fail_message          │   │ │
│  │  │  - entities_extracted[]   │  │  - steer_message         │   │ │
│  │  │  - ttl (30 days)          │  │  - enabled (boolean)     │   │ │
│  │  └───────────────────────────┘  └──────────────────────────┘   │ │
│  └──────────────────────────────────────────────────────────────────┘ │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Data Models

### Long-Term Memory (Neo4j)

**POLE+O Entity Model:**

```cypher
// Person node
CREATE (p:Person {
    id: "person_123",
    name: "Sarah Chen",
    email: "sarah.chen@acme.com",
    first_mentioned: datetime("2026-05-10T14:30:00Z"),
    last_mentioned: datetime("2026-05-10T14:30:00Z"),
    mention_count: 1
})

// Organization node
CREATE (o:Organization {
    id: "org_456",
    name: "Acme Corp",
    domain: "acme.com",
    first_mentioned: datetime("2026-05-10T14:30:00Z"),
    industry: "Technology"
})

// Location node
CREATE (l:Location {
    id: "loc_789",
    name: "Seattle",
    type: "city",
    country: "USA"
})

// Event node
CREATE (e:Event {
    id: "event_101",
    name: "AWS Summit 2026",
    date: date("2026-05-15"),
    location: "Seattle"
})

// Object node (custom domain entities)
CREATE (prod:Object:Product {
    id: "product_202",
    name: "Enterprise Tier",
    type: "product",
    category: "subscription"
})

// Relationships
CREATE (p)-[:WORKS_AT {since: date("2023-01-01")}]->(o)
CREATE (p)-[:ATTENDED {date: date("2026-05-15")}]->(e)
CREATE (p)-[:INTERESTED_IN {expressed_on: date("2026-05-15")}]->(prod)
CREATE (e)-[:LOCATED_IN]->(l)
```

### Reasoning Memory (Neo4j)

**Decision Provenance Graph:**

```cypher
// Decision node
CREATE (d:Decision {
    id: "decision_123",
    action: "extract_entities",
    timestamp: datetime("2026-05-10T14:30:00Z"),
    conversation_id: "conv_789",
    reasoning: "User mentioned new contact and organization"
})

// Input message
CREATE (m:Message {
    id: "msg_456",
    content: "I met Sarah Chen from Acme Corp at AWS Summit",
    role: "user",
    timestamp: datetime("2026-05-10T14:30:00Z")
})

// Tool call
CREATE (tc:ToolCall {
    id: "toolcall_789",
    tool_name: "extract_entities",
    parameters: {user_message: "...", conversation_id: "conv_789"},
    duration_ms: 1250
})

// Outcome
CREATE (out:Outcome {
    id: "outcome_101",
    success: true,
    entities_created: 3,
    relationships_created: 3
})

// Provenance chain
CREATE (d)-[:INPUT]->(m)
CREATE (d)-[:EXECUTED]->(tc)
CREATE (tc)-[:RESULTED_IN]->(out)
CREATE (out)-[:CREATED]->(p:Person {name: "Sarah Chen"})
CREATE (out)-[:CREATED]->(o:Organization {name: "Acme Corp"})
```

### Short-Term Memory (DynamoDB)

**IMPORTANT: This table is for CLIENT/ORCHESTRATOR use, NOT for AgentCore**

AgentCore Runtime does NOT read from this table. The Conversation Orchestrator:
1. Queries this table to retrieve history
2. Formats history into the prompt
3. Passes formatted prompt to AgentCore
4. Stores new messages after AgentCore responds

**Conversations Table:**

```python
{
    "conversation_id": "conv_789",  # PK
    "message_timestamp": "2026-05-10T14:30:00Z",  # SK
    "role": "user",  # user | assistant | system
    "content": "I met Sarah Chen from Acme Corp at AWS Summit",
    "entities_extracted": [
        {"type": "Person", "name": "Sarah Chen", "id": "person_123"},
        {"type": "Organization", "name": "Acme Corp", "id": "org_456"},
        {"type": "Event", "name": "AWS Summit 2026", "id": "event_101"}
    ],
    "tool_calls": [
        {"tool": "extract_entities", "duration_ms": 1250}
    ],
    "ttl": 1749456000  # Auto-expire after 30 days
}
```

**Steering Rules Table:**

```python
{
    "rule_id": "rule_001",  # PK
    "tool_name": "extract_entities",
    "condition": "len(params['user_message']) > 5000",
    "fail_message": "Message too long for entity extraction",
    "steer_message": "Split message into chunks under 5000 chars and extract from each",
    "enabled": True,
    "priority": 10,
    "created_at": "2026-05-01T00:00:00Z",
    "updated_at": "2026-05-10T12:00:00Z"
}
```

---

## Tool Specifications

### 1. extract_entities

**Purpose:** Extract POLE+O entities from user messages and store in Neo4j.

**Input:**
```python
{
    "user_message": str,  # User's message text
    "conversation_id": str  # Conversation context
}
```

**Output:**
```python
{
    "entities": [
        {
            "type": "Person" | "Organization" | "Location" | "Event" | "Object",
            "id": str,  # Neo4j node ID
            "name": str,
            "properties": dict  # Additional extracted properties
        }
    ],
    "relationships": [
        {
            "from_id": str,
            "to_id": str,
            "type": "WORKS_AT" | "ATTENDED" | "INTERESTED_IN" | ...,
            "properties": dict
        }
    ],
    "summary": str  # Natural language summary of extraction
}
```

**Implementation:**
1. Call OpenAI GPT-4o-mini with structured output prompt:
   ```
   Extract entities from the following message using the POLE+O model:
   - Person: People mentioned (name, email if available)
   - Organization: Companies, institutions
   - Location: Cities, countries, venues
   - Event: Meetings, conferences, milestones
   - Object: Domain-specific entities (products, bookings, etc.)
   
   Also identify relationships: WORKS_AT, ATTENDED, INTERESTED_IN, etc.
   
   Message: {user_message}
   ```

2. Store entities in Neo4j:
   ```cypher
   MERGE (p:Person {name: $name})
   ON CREATE SET p.id = $id, p.first_mentioned = datetime()
   ON MATCH SET p.last_mentioned = datetime(), p.mention_count = p.mention_count + 1
   ```

3. Store relationships:
   ```cypher
   MATCH (p:Person {id: $from_id}), (o:Organization {id: $to_id})
   MERGE (p)-[r:WORKS_AT]->(o)
   ON CREATE SET r.since = date()
   ```

**Error handling:**
- Message too long → Steer: split into chunks
- No entities found → Return empty arrays (not an error)
- Neo4j connection failure → Return error, retry with exponential backoff

---

### 2. query_context

**Purpose:** Query Neo4j knowledge graph for context retrieval.

**Input (Option A: Cypher):**
```python
{
    "cypher_query": str  # Direct Cypher query
}
```

**Input (Option B: Natural Language):**
```python
{
    "question": str,  # Natural language question
    "conversation_id": str  # For context-aware text2cypher
}
```

**Output:**
```python
{
    "results": [
        dict  # Query result rows
    ],
    "summary": str,  # Natural language summary of results
    "cypher_executed": str  # The Cypher query that was run (for provenance)
}
```

**Implementation:**

**Option A (direct Cypher):**
1. Validate Cypher (no DETACH DELETE, no SET, read-only)
2. Execute query against Neo4j
3. Format results as JSON

**Option B (text2cypher):**
1. Retrieve conversation context from DynamoDB
2. Call OpenAI with schema prompt:
   ```
   Convert this question to Cypher based on the schema:
   
   Node labels: Person, Organization, Location, Event, Object
   Relationships: WORKS_AT, ATTENDED, INTERESTED_IN, LOCATED_IN
   
   Person properties: id, name, email, first_mentioned, last_mentioned
   Organization properties: id, name, domain, industry
   
   Question: {question}
   Conversation context: {recent_messages}
   ```
3. Execute generated Cypher
4. Summarize results with LLM

**Error handling:**
- Invalid Cypher → Steer: "Query syntax error at token X. Try: {suggestion}"
- No results → Return "No matching data found"
- Neo4j timeout → Retry with simplified query (remove ORDER BY, LIMIT 10)

---

### 3. log_decision

**Purpose:** Log agent decisions to reasoning memory graph.

**Input:**
```python
{
    "tool_name": str,  # Name of tool that was called
    "parameters": dict,  # Tool parameters
    "result": dict,  # Tool output
    "timestamp": str,  # ISO8601 timestamp
    "conversation_id": str,
    "reasoning": str  # Why this tool was called (from agent)
}
```

**Output:**
```python
{
    "decision_id": str,  # Neo4j Decision node ID
    "provenance_chain": [str]  # IDs of related nodes in provenance graph
}
```

**Implementation:**
1. Create Decision node:
   ```cypher
   CREATE (d:Decision {
       id: $decision_id,
       action: $tool_name,
       timestamp: datetime($timestamp),
       conversation_id: $conversation_id,
       reasoning: $reasoning
   })
   ```

2. Link to input message (if available):
   ```cypher
   MATCH (m:Message {conversation_id: $conv_id})
   WHERE m.timestamp < datetime($timestamp)
   ORDER BY m.timestamp DESC LIMIT 1
   CREATE (d)-[:INPUT]->(m)
   ```

3. Link to created entities (if tool was extract_entities):
   ```cypher
   MATCH (d:Decision {id: $decision_id})
   MATCH (e) WHERE e.id IN $created_entity_ids
   CREATE (d)-[:CREATED]->(e)
   ```

4. Link to previous decision (temporal chain):
   ```cypher
   MATCH (prev:Decision {conversation_id: $conv_id})
   WHERE prev.timestamp < datetime($timestamp)
   ORDER BY prev.timestamp DESC LIMIT 1
   CREATE (prev)-[:FOLLOWED_BY]->(d)
   ```

**Hook integration:**
This tool is called automatically by `AfterToolCallEvent` hook:
```python
class DecisionProvenanceHook(HookProvider):
    def register_hooks(self, registry: HookRegistry):
        registry.add_callback(AfterToolCallEvent, self.log_decision)
    
    def log_decision(self, event: AfterToolCallEvent):
        # Call log_decision Lambda with event data
        lambda_client.invoke(
            FunctionName="log_decision",
            Payload=json.dumps({
                "tool_name": event.tool_use["name"],
                "parameters": event.tool_use["input"],
                "result": event.result,
                "timestamp": datetime.now().isoformat(),
                "conversation_id": event.conversation_id
            })
        )
```

---

## Hook Specifications

### BeforeToolCallEvent: Steering Rules Validation

**Purpose:** Validate tool calls against DynamoDB steering rules.

**Implementation:**
```python
class SteeringRulesHook(HookProvider):
    def __init__(self):
        self._dynamodb = boto3.resource("dynamodb")
        self._rules_table = self._dynamodb.Table(os.environ["STEERING_RULES_TABLE"])
    
    def register_hooks(self, registry: HookRegistry):
        registry.add_callback(BeforeToolCallEvent, self.validate)
    
    def validate(self, event: BeforeToolCallEvent):
        tool_name = event.tool_use["name"]
        params = event.tool_use["input"]
        
        # Query DynamoDB for rules matching this tool
        response = self._rules_table.query(
            IndexName="tool_name-index",
            KeyConditionExpression="tool_name = :tool",
            ExpressionAttributeValues={":tool": tool_name},
            FilterExpression="enabled = :true",
            ExpressionAttributeValues={":true": True}
        )
        
        rules = response.get("Items", [])
        
        for rule in sorted(rules, key=lambda r: r.get("priority", 100)):
            condition = rule["condition"]
            
            # Evaluate condition (Python expression)
            try:
                if eval(condition, {"params": params, "len": len}):
                    # Rule violated
                    if rule.get("fail_message"):
                        # Hard block
                        event.cancel_tool = rule["fail_message"]
                        return
                    elif rule.get("steer_message"):
                        # Steering guidance (doesn't block, adds context)
                        event.cancel_tool = rule["steer_message"]
                        return
            except Exception as e:
                # Rule evaluation error (log but don't block)
                print(f"Rule {rule['rule_id']} evaluation failed: {e}")
                continue
```

**Example steering rules:**

```python
# Rule 1: Message length limit
{
    "rule_id": "extract_entities_length",
    "tool_name": "extract_entities",
    "condition": "len(params.get('user_message', '')) > 5000",
    "steer_message": "Message exceeds 5000 chars. Split into chunks and extract from each chunk.",
    "enabled": True,
    "priority": 10
}

# Rule 2: Cypher injection prevention
{
    "rule_id": "query_context_injection",
    "tool_name": "query_context",
    "condition": "'DELETE' in params.get('cypher_query', '').upper() or 'DETACH' in params.get('cypher_query', '').upper()",
    "fail_message": "BLOCKED: Cypher query contains destructive operations (DELETE/DETACH)",
    "enabled": True,
    "priority": 1
}

# Rule 3: Context query complexity
{
    "rule_id": "query_context_complexity",
    "tool_name": "query_context",
    "condition": "params.get('cypher_query', '').count('MATCH') > 5",
    "steer_message": "Query has >5 MATCH clauses. Simplify by breaking into smaller queries or add LIMIT clause.",
    "enabled": True,
    "priority": 20
}
```

---

### AfterToolCallEvent: Decision Provenance Logging

**Purpose:** Automatically log every tool call to reasoning memory.

**Implementation:**
```python
class DecisionProvenanceHook(HookProvider):
    def __init__(self):
        self._lambda_client = boto3.client("lambda")
        self._log_decision_function = os.environ["LOG_DECISION_FUNCTION_NAME"]
    
    def register_hooks(self, registry: HookRegistry):
        registry.add_callback(AfterToolCallEvent, self.log_decision)
    
    def log_decision(self, event: AfterToolCallEvent):
        # Extract conversation_id from context (if available)
        conversation_id = getattr(event, "conversation_id", "unknown")
        
        # Invoke log_decision Lambda asynchronously
        self._lambda_client.invoke(
            FunctionName=self._log_decision_function,
            InvocationType="Event",  # Async
            Payload=json.dumps({
                "tool_name": event.tool_use["name"],
                "parameters": event.tool_use["input"],
                "result": event.result,
                "timestamp": datetime.now().isoformat(),
                "conversation_id": conversation_id,
                "reasoning": event.reasoning if hasattr(event, "reasoning") else None
            })
        )
```

**Note:** This hook invokes asynchronously to avoid blocking agent execution. Decision logging is observability, not critical path.

---

## Deployment Architecture

### CDK Stack Structure

```
cdk/
├── app.py                           # CDK app entry point
├── context_graph_stack.py           # Main stack
├── requirements.txt                 # CDK dependencies
└── constructs/
    ├── neo4j_construct.py           # Neo4j AuraDB secrets + SSM params
    ├── dynamodb_construct.py        # Conversations + SteeringRules tables
    ├── lambda_tools_construct.py    # 3 Lambda functions
    └── agentcore_construct.py       # Runtime + Gateway
```

### Resource Naming Convention

```
Context Stack Resources:
- DynamoDB: ContextGraphStack-Conversations, ContextGraphStack-SteeringRules
- Lambda: context-extract-entities, context-query-context, context-log-decision
- AgentCore Runtime: ContextGraphStack-AgentRuntime
- AgentCore Gateway: ContextGraphStack-AgentGateway
- Secrets: /ContextGraphStack/neo4j-uri, /ContextGraphStack/neo4j-password, /ContextGraphStack/openai-api-key
- SSM Params: /ContextGraphStack/runtime-arn, /ContextGraphStack/gateway-url
```

---

## Metrics & Observability

### Key Metrics to Track

1. **Context Recall Accuracy**
   - Metric: % of entities correctly recalled in follow-up questions
   - Measurement: Ground truth annotations vs agent responses
   - Target: >95% recall for entities mentioned within same conversation

2. **Entity Extraction Precision/Recall**
   - Metric: Precision/Recall vs ground truth annotations
   - Measurement: Manual annotation of sample conversations
   - Target: Precision >90%, Recall >85%

3. **Decision Provenance Completeness**
   - Metric: % of decisions that have complete provenance chains
   - Measurement: Query reasoning graph for orphaned Decision nodes
   - Target: 100% of decisions linked to input + outcome

4. **Query Latency**
   - Metric: P50, P95, P99 latency for each tool
   - Measurement: CloudWatch Logs Insights
   - Targets:
     - extract_entities: P95 < 2s (LLM call dominates)
     - query_context: P95 < 100ms (Neo4j query)
     - log_decision: P95 < 50ms (async write)

5. **Neo4j Graph Growth**
   - Metric: # of nodes/relationships over time
   - Measurement: Daily Cypher query:
     ```cypher
     MATCH (n) RETURN labels(n)[0] AS type, COUNT(n) AS count
     ```
   - Expected: Linear growth with conversation volume

### CloudWatch Dashboard

```python
# CDK code to create dashboard
dashboard = cloudwatch.Dashboard(
    self, "ContextGraphDashboard",
    dashboard_name="ContextGraph-Metrics"
)

# Lambda invocation counts
dashboard.add_widgets(
    cloudwatch.GraphWidget(
        title="Tool Invocations",
        left=[
            extract_entities_lambda.metric_invocations(),
            query_context_lambda.metric_invocations(),
            log_decision_lambda.metric_invocations()
        ]
    )
)

# Lambda durations
dashboard.add_widgets(
    cloudwatch.GraphWidget(
        title="Tool Latency (ms)",
        left=[
            extract_entities_lambda.metric_duration(statistic="p95"),
            query_context_lambda.metric_duration(statistic="p95"),
            log_decision_lambda.metric_duration(statistic="p95")
        ]
    )
)

# DynamoDB read/write capacity
dashboard.add_widgets(
    cloudwatch.GraphWidget(
        title="DynamoDB Operations",
        left=[
            conversations_table.metric_consumed_read_capacity_units(),
            conversations_table.metric_consumed_write_capacity_units()
        ]
    )
)
```

---

## Security Considerations

### 1. Data Privacy

**PII in Knowledge Graph:**
- Entity extraction may capture PII (names, emails)
- Neo4j AuraDB must be in compliant region (GDPR, HIPAA)
- Implement data retention policies (TTL on Message nodes)

**Mitigation:**
- Add PII detection hook (BeforeToolCallEvent for extract_entities)
- Redact or encrypt PII before storing in Neo4j
- Provide user deletion endpoint (GDPR right to be forgotten)

### 2. Query Injection

**Cypher Injection:**
- query_context accepts user-provided Cypher queries
- Risk: Malicious queries (DELETE, DETACH DELETE, slow queries)

**Mitigation:**
- Validate Cypher in steering rules (block destructive keywords)
- Use read-only Neo4j user for query_context Lambda
- Query timeout (30s max)
- Rate limiting on query_context tool

### 3. Secrets Management

**Credentials:**
- Neo4j URI/password
- OpenAI API key
- AWS credentials (for Lambda)

**Mitigation:**
- Store all secrets in AWS Secrets Manager
- Lambda IAM roles with least-privilege policies
- Rotate secrets every 90 days (automate with Secrets Manager rotation)

### 4. Steering Rule Tampering

**Risk:**
- DynamoDB steering rules control agent behavior
- Malicious rule could disable guardrails or inject misleading instructions

**Mitigation:**
- DynamoDB table has no public access (VPC-only Lambda)
- IAM policy: Only admin role can write to SteeringRules table
- Audit log: All rule changes logged to CloudTrail
- Rule validation: Condition must be valid Python expression (reject `eval` of user input)

---

## Cost Optimization

### Neo4j AuraDB Free Tier

**Limits:**
- 50K nodes + 175K relationships (sufficient for ~1000 conversations with entity extraction)
- Auto-pauses after inactivity (requires manual resume)

**Optimization:**
- Use AuraDB Free for development/demos
- Upgrade to AuraDB Professional when graph exceeds 50K nodes
- Alternative: Self-hosted Neo4j on EC2 (no pause, but requires management)

### DynamoDB On-Demand

**Cost:**
- $1.25 per million write requests
- $0.25 per million read requests

**Optimization:**
- Use TTL (30 days) to auto-expire old conversations (reduces storage cost)
- Batch write decision logs (reduces write requests by 80%)
- Cache recent conversations in Lambda memory (reduces read requests)

### Lambda Pricing

**Cost:**
- $0.20 per 1M requests
- $0.0000166667 per GB-second

**extract_entities (1024MB, 2s avg):**
- 10K calls/month: 10K × 2s × 1024MB = 20,480 GB-seconds = $0.34
- 10K × $0.20/1M = $0.002
- **Total: $0.34/month**

**query_context (256MB, 0.1s avg):**
- 10K calls/month: 10K × 0.1s × 256MB = 256 GB-seconds = $0.004
- **Total: $0.004/month**

**log_decision (256MB, 0.05s avg, async):**
- 30K calls/month (logged for every tool call): 30K × 0.05s × 256MB = 384 GB-seconds = $0.006
- **Total: $0.006/month**

**Grand total Lambda: $0.35/month**

### LLM Costs (GPT-4o-mini)

**extract_entities:**
- Input: 500 tokens/call (system prompt + user message)
- Output: 200 tokens/call (JSON entity list)
- 10K calls/month: 10K × 500 × $0.15/1M + 10K × 200 × $0.60/1M = $0.75 + $1.20 = **$1.95/month**

**query_context (text2cypher only, not direct Cypher):**
- Input: 300 tokens/call (schema + question)
- Output: 50 tokens/call (Cypher query)
- 5K calls/month: 5K × 300 × $0.15/1M + 5K × 50 × $0.60/1M = $0.23 + $0.15 = **$0.38/month**

**Total LLM: $2.33/month**

### Total Cost Summary (10K conversations/month)

```
Neo4j AuraDB Free:         $0
DynamoDB:                  $1 (storage + requests)
Lambda:                    $0.35
LLM (GPT-4o-mini):         $2.33
AgentCore Runtime:         ~$50 (estimate)
────────────────────────────────
Total:                     ~$54/month
```

**Cost per conversation: $0.0054**

---

## Scalability Considerations

### Neo4j Query Performance

**Challenge:** Graph queries slow down as graph size increases (>100K nodes).

**Solutions:**
1. **Indexes:** Create indexes on frequently queried properties (Person.name, Organization.name)
2. **Query optimization:** Use LIMIT clauses, avoid cartesian products
3. **Sharding:** Separate entity graph by customer/tenant if multi-tenant
4. **Read replicas:** Neo4j Enterprise supports read replicas (not available in AuraDB Free)

**Benchmark targets:**
- <50ms for single-hop queries (e.g., "Who works at Acme Corp?")
- <200ms for two-hop queries (e.g., "Who attended events with Sarah?")
- <1s for complex queries (e.g., "Find shortest path between two people")

### DynamoDB Throughput

**Challenge:** On-demand mode throttles at 40K RCU/WCU per table.

**Solutions:**
1. **Provisioned capacity:** Switch to provisioned if traffic is predictable (cheaper at high volume)
2. **Caching:** Use ElastiCache Redis for hot conversation data
3. **Sharding:** Create multiple tables if single-tenant exceeds 40K RPS

**Benchmark targets:**
- <10ms P50 read latency
- <20ms P50 write latency
- Support 1000 concurrent conversations (1000 reads/sec, 500 writes/sec)

### Lambda Concurrency

**Challenge:** Lambda has default concurrency limit of 1000 per account.

**Solutions:**
1. **Reserved concurrency:** Reserve capacity for critical tools (extract_entities)
2. **Async processing:** log_decision is async (doesn't block agent)
3. **Request throttling:** Use API Gateway rate limiting to prevent runaway costs

**Benchmark targets:**
- Support 100 concurrent agent conversations
- Each conversation calls 3-5 tools → 300-500 concurrent Lambdas
- Well within 1000 limit

---

## Testing Strategy

### Unit Tests

**Test extract_entities:**
```python
def test_extract_entities_person():
    result = extract_entities_handler({
        "user_message": "I met Sarah Chen from Acme Corp",
        "conversation_id": "test_conv"
    }, None)
    
    assert len(result["entities"]) == 2
    assert result["entities"][0]["type"] == "Person"
    assert result["entities"][0]["name"] == "Sarah Chen"
    assert result["entities"][1]["type"] == "Organization"
    assert result["entities"][1]["name"] == "Acme Corp"
    
    assert len(result["relationships"]) == 1
    assert result["relationships"][0]["type"] == "WORKS_AT"
```

**Test query_context:**
```python
def test_query_context_cypher():
    result = query_context_handler({
        "cypher_query": "MATCH (p:Person) RETURN p.name LIMIT 1"
    }, None)
    
    assert "results" in result
    assert len(result["results"]) <= 1

def test_query_context_injection_blocked():
    result = query_context_handler({
        "cypher_query": "MATCH (p:Person) DELETE p"
    }, None)
    
    assert "error" in result
    assert "destructive" in result["error"].lower()
```

**Test steering hooks:**
```python
def test_steering_hook_message_length():
    event = BeforeToolCallEvent(
        tool_use={
            "name": "extract_entities",
            "input": {"user_message": "x" * 10000}
        }
    )
    
    hook = SteeringRulesHook()
    hook.validate(event)
    
    assert event.cancel_tool is not None
    assert "split into chunks" in event.cancel_tool.lower()
```

### Integration Tests

**Test end-to-end flow:**
```python
def test_e2e_entity_extraction_and_query():
    # Step 1: Extract entities from message
    extract_result = lambda_client.invoke(
        FunctionName="context-extract-entities",
        Payload=json.dumps({
            "user_message": "I met Sarah Chen from Acme Corp at AWS Summit",
            "conversation_id": "integ_test_1"
        })
    )
    
    entities = json.load(extract_result["Payload"])["entities"]
    person_id = next(e["id"] for e in entities if e["type"] == "Person")
    
    # Step 2: Query for the extracted person
    query_result = lambda_client.invoke(
        FunctionName="context-query-context",
        Payload=json.dumps({
            "cypher_query": f"MATCH (p:Person {{id: '{person_id}'}}) RETURN p.name"
        })
    )
    
    results = json.load(query_result["Payload"])["results"]
    assert len(results) == 1
    assert results[0]["p.name"] == "Sarah Chen"
    
    # Step 3: Verify decision provenance logged
    time.sleep(2)  # Wait for async log_decision
    
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session() as session:
        provenance = session.run(
            "MATCH (d:Decision {conversation_id: 'integ_test_1'}) RETURN count(d) AS count"
        ).single()
        assert provenance["count"] > 0
```

### Load Tests

**Locust test script:**
```python
from locust import HttpUser, task, between

class ContextGraphUser(HttpUser):
    wait_time = between(1, 3)
    
    @task(3)
    def extract_entities(self):
        self.client.post("/invoke", json={
            "prompt": f"I met contact_{self.user_id} from company_{self.user_id}"
        })
    
    @task(1)
    def query_context(self):
        self.client.post("/invoke", json={
            "prompt": "What companies have we discussed?"
        })
```

**Target:** 100 concurrent users, 300 requests/sec, <2s P95 latency

---

## Migration Path from Demo 06

### What to keep:
- DynamoDB steering rules table (same schema)
- AgentCore Runtime + Gateway (same MCP architecture)
- Lambda deployment patterns (package/ directories)
- CDK stack structure

### What to add:
- `extract_entities` Lambda
- `query_context` Lambda
- `log_decision` Lambda
- Neo4j schema (POLE+O + reasoning graph)
- DynamoDB Conversations table (new)
- `AfterToolCallEvent` hook for decision logging

### Migration steps:

1. **Deploy new infrastructure** (no changes to Demo 06):
   ```bash
   cd 07-context-graph-integration/cdk
   cdk deploy ContextGraphStack
   ```

2. **Populate Neo4j secrets** (via AWS Console):
   - /ContextGraphStack/neo4j-uri
   - /ContextGraphStack/neo4j-password
   - /ContextGraphStack/openai-api-key

3. **Test local agent** (before AgentCore):
   ```bash
   cd 07-context-graph-integration
   uv run python context_agent_demo.py
   ```

4. **Deploy AgentCore agent**:
   ```bash
   ./deploy_agent.sh  # Packages and uploads to AgentCore Runtime
   ```

5. **Invoke and validate**:
   ```bash
   aws bedrock-agentcore invoke-agent-runtime \
       --agent-runtime-arn $(aws ssm get-parameter --name /ContextGraphStack/runtime-arn --query Parameter.Value --output text) \
       --payload "$(echo '{"prompt": "I met Sarah Chen from Acme Corp"}' | base64)" \
       --region us-east-1 /tmp/response.json
   
   # Verify entities in Neo4j
   # Verify decision in reasoning graph
   ```

---

## Future Enhancements

### 1. Multi-Agent Coordination
- Multiple agents sharing the same knowledge graph
- Agent A extracts entities, Agent B answers questions, Agent C audits decisions
- Requires: Agent ID tracking in Decision nodes

### 2. Temporal Queries
- "What did we discuss last week?"
- "Show me all decisions made on May 10th"
- Requires: Temporal indexes on timestamp properties

### 3. Graph Visualization UI
- Next.js frontend (like create-context-graph generates)
- Streaming chat + live graph rendering
- Decision trace timeline view

### 4. Advanced Provenance
- Counterfactual reasoning: "What if we hadn't extracted this entity?"
- Blame assignment: "Which decision led to this outcome?"
- Requires: Causal graph structure (CAUSED_BY, PREVENTED relationships)

### 5. Federated Graphs
- Multi-tenant: Each customer has separate graph
- Cross-customer: Aggregate entities without exposing raw data
- Requires: Graph sharding + access control

---

**Document Status:** Architecture complete, ready for implementation  
**Next Steps:** Implement extract_entities Lambda → Test entity extraction → Deploy CDK stack
