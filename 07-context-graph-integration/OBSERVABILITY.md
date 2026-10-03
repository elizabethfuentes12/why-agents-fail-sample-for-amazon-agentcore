# Observability: AgentCore + Strands OpenTelemetry

## Overview

Understanding agent behavior in production requires **three layers of observability**:

1. **Infrastructure metrics** (AWS CloudWatch) — Lambda duration, DynamoDB throttling, Neo4j connection errors
2. **Agent traces** (Strands OpenTelemetry) — Tool calls, reasoning steps, token usage
3. **Decision provenance** (Neo4j reasoning graph) — Why did the agent make this decision?

This document details how to implement all three layers for Demo 07.

---

## Layer 1: AWS Infrastructure Observability

### AgentCore Runtime Metrics (CloudWatch)

**What AgentCore provides out-of-the-box:**

```python
# From agentcore_runtime.py (Demo 06)
logging_configuration=agentcore.CfnRuntime.LoggingConfigurationProperty(
    cloud_watch_logs_configuration=agentcore.CfnRuntime.CloudWatchLogsConfigurationProperty(
        log_group_name=f"/aws/agentcore/runtime/{runtime_name}",
        enabled=True,
    ),
),
```

**Metrics available:**
- `Invocations` — Total calls to `invoke-agent-runtime`
- `Duration` — Time per invocation (P50, P95, P99)
- `Errors` — Failed invocations (4xx, 5xx)
- `ConcurrentExecutions` — Number of active runtime containers

**Key CloudWatch Logs Insights queries:**

```sql
-- Top 10 slowest invocations
fields @timestamp, @duration, @message
| filter @type = "AgentCore"
| sort @duration desc
| limit 10

-- Tool call frequency
fields tool_name, count() as call_count
| filter @message like /tool_call/
| stats count() by tool_name
| sort call_count desc

-- Error patterns
fields @timestamp, @message
| filter @type = "ERROR"
| stats count() by @message
```

---

### Lambda Tools Metrics (CloudWatch)

**Each Lambda function exports:**
- `Duration` — Tool execution time
- `Invocations` — Call frequency
- `Errors` — Failed tool calls
- `ConcurrentExecutions` — Parallelism

**Custom metrics to add:**

```python
# lambda_tools/extract_entities/lambda_function.py
import boto3
cloudwatch = boto3.client('cloudwatch')

def handler(event, context):
    start_time = time.time()
    
    try:
        entities = extract_entities_from_message(event['user_message'])
        
        # Custom metric: Entities extracted per call
        cloudwatch.put_metric_data(
            Namespace='ContextGraph/Tools',
            MetricData=[{
                'MetricName': 'EntitiesExtracted',
                'Value': len(entities),
                'Unit': 'Count',
                'Dimensions': [{'Name': 'ToolName', 'Value': 'extract_entities'}]
            }]
        )
        
        return {"entities": entities}
    
    except Exception as e:
        # Custom metric: Extraction failures
        cloudwatch.put_metric_data(
            Namespace='ContextGraph/Tools',
            MetricData=[{
                'MetricName': 'ExtractionFailures',
                'Value': 1,
                'Unit': 'Count',
                'Dimensions': [{'Name': 'ErrorType', 'Value': type(e).__name__}]
            }]
        )
        raise
    
    finally:
        duration_ms = (time.time() - start_time) * 1000
        cloudwatch.put_metric_data(
            Namespace='ContextGraph/Tools',
            MetricData=[{
                'MetricName': 'ToolDuration',
                'Value': duration_ms,
                'Unit': 'Milliseconds',
                'Dimensions': [{'Name': 'ToolName', 'Value': 'extract_entities'}]
            }]
        )
```

**CloudWatch Dashboard for Lambda Tools:**

```python
# CDK code
dashboard = cloudwatch.Dashboard(self, "ToolMetricsDashboard")

# Widget 1: Invocations per tool
dashboard.add_widgets(
    cloudwatch.GraphWidget(
        title="Tool Invocations",
        left=[
            extract_entities_lambda.metric_invocations(statistic="sum", period=Duration.minutes(5)),
            query_context_lambda.metric_invocations(statistic="sum", period=Duration.minutes(5)),
            log_decision_lambda.metric_invocations(statistic="sum", period=Duration.minutes(5))
        ]
    )
)

# Widget 2: Tool durations (P95)
dashboard.add_widgets(
    cloudwatch.GraphWidget(
        title="Tool Latency (P95)",
        left=[
            extract_entities_lambda.metric_duration(statistic="p95"),
            query_context_lambda.metric_duration(statistic="p95"),
            log_decision_lambda.metric_duration(statistic="p95")
        ]
    )
)

# Widget 3: Custom metric - Entities extracted
dashboard.add_widgets(
    cloudwatch.GraphWidget(
        title="Entities Extracted per Call",
        left=[
            cloudwatch.Metric(
                namespace="ContextGraph/Tools",
                metric_name="EntitiesExtracted",
                dimensions_map={"ToolName": "extract_entities"},
                statistic="Average"
            )
        ]
    )
)
```

---

## Layer 2: Strands OpenTelemetry Integration

### What Strands Provides

**Strands Agents has built-in OpenTelemetry support:**

```python
# From Strands documentation
from strands import Agent
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

# Setup OpenTelemetry
trace.set_tracer_provider(TracerProvider())
tracer = trace.get_tracer(__name__)

# Optional: Export to console (for debugging)
span_processor = BatchSpanProcessor(ConsoleSpanExporter())
trace.get_tracer_provider().add_span_processor(span_processor)

# Agent automatically traces:
# - LLM requests (prompt, completion, tokens)
# - Tool calls (tool name, parameters, results)
# - Hook executions (BeforeToolCallEvent, AfterToolCallEvent)
agent = Agent(model=model, tools=tools)
```

**What gets traced automatically:**

| Span Name | Attributes | Use Case |
|-----------|-----------|----------|
| `agent.run` | `agent.name`, `model.id`, `input.prompt` | Top-level agent invocation |
| `llm.request` | `model.id`, `prompt.tokens`, `completion.tokens`, `latency_ms` | LLM API calls |
| `tool.call` | `tool.name`, `tool.parameters`, `tool.result`, `duration_ms` | Tool executions |
| `hook.before_tool_call` | `hook.name`, `tool.name`, `cancelled` | Pre-validation hooks |
| `hook.after_tool_call` | `hook.name`, `tool.name`, `logged` | Post-execution hooks |

### Export OpenTelemetry to AWS X-Ray

**Setup AWS X-Ray exporter in AgentCore Runtime:**

```python
# agent_files/booking_agent.py (Demo 07 version)
import os
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

# Check if running in AWS (Lambda or AgentCore container)
if os.environ.get("AWS_EXECUTION_ENV"):
    # Export to AWS X-Ray via OTLP
    trace.set_tracer_provider(TracerProvider())
    otlp_exporter = OTLPSpanExporter(
        endpoint="http://localhost:4317",  # X-Ray daemon endpoint
        insecure=True
    )
    span_processor = BatchSpanProcessor(otlp_exporter)
    trace.get_tracer_provider().add_span_processor(span_processor)

# Strands Agent will use this tracer automatically
from strands import Agent
agent = Agent(model=model, tools=tools)
```

**Enable X-Ray in AgentCore Runtime (CDK):**

```python
# cdk/agentcore/agentcore_runtime.py
runtime = agentcore.CfnRuntime(
    self, "ContextGraphRuntime",
    # ... other config ...
    tracing_configuration=agentcore.CfnRuntime.TracingConfigurationProperty(
        enabled=True  # Enables AWS X-Ray tracing
    )
)
```

**What you'll see in X-Ray:**

```
Service Map:
  AgentCore Runtime
    ├─ Lambda: extract_entities (avg 1.2s)
    ├─ Lambda: query_context (avg 120ms)
    ├─ Lambda: log_decision (avg 50ms)
    ├─ DynamoDB: SteeringRules (avg 10ms)
    └─ External: OpenAI API (avg 800ms)

Trace Details:
  Segment: agent.run (2.5s total)
    ├─ Subsegment: llm.request (800ms) — OpenAI GPT-4o-mini
    │   └─ Metadata: prompt_tokens=450, completion_tokens=200
    ├─ Subsegment: hook.before_tool_call (25ms) — SteeringRulesHook
    │   └─ Annotation: rule_checked="extract_length", passed=true
    ├─ Subsegment: tool.call (1.2s) — extract_entities
    │   ├─ Metadata: entities_extracted=3, relationships=2
    │   └─ Downstream: Lambda extract_entities
    └─ Subsegment: hook.after_tool_call (10ms) — DecisionProvenanceHook
        └─ Downstream: Lambda log_decision (async)
```

### Custom Spans for Business Logic

**Add custom spans to Lambda tools:**

```python
# lambda_tools/extract_entities/lambda_function.py
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

def handler(event, context):
    with tracer.start_as_current_span("extract_entities") as span:
        user_message = event['user_message']
        span.set_attribute("message.length", len(user_message))
        
        # Step 1: Call OpenAI for entity extraction
        with tracer.start_as_current_span("openai.entity_extraction") as extraction_span:
            entities = call_openai_for_extraction(user_message)
            extraction_span.set_attribute("entities.count", len(entities))
        
        # Step 2: Store in Neo4j
        with tracer.start_as_current_span("neo4j.store_entities") as neo_span:
            store_entities_in_neo4j(entities)
            neo_span.set_attribute("neo4j.nodes_created", len(entities))
        
        span.set_attribute("extraction.success", True)
        return {"entities": entities}
```

**Query X-Ray for insights:**

```sql
-- Find slowest entity extractions
service("AgentCore Runtime") {
  tool.call.name = "extract_entities" 
  AND duration > 2000
}

-- Find failed tool calls
service("AgentCore Runtime") {
  error = true 
  AND tool.call.name EXISTS
}

-- Find steering rule blocks
service("AgentCore Runtime") {
  hook.before_tool_call.cancelled = true
}
```

---

## Layer 3: Decision Provenance Graph (Neo4j)

### What Layer 3 Provides

**Infrastructure (Layer 1) and OpenTelemetry (Layer 2) answer:**
- How long did extract_entities take? (1.2s)
- How many times was it called? (150 times today)
- Did it succeed? (yes)

**Decision Provenance (Layer 3) answers:**
- **Why** did the agent call extract_entities? (User mentioned new contact)
- **What context** led to this decision? (Previous conversation mentioned company)
- **What was the outcome?** (3 entities created, 2 relationships added)
- **What happened next?** (Agent queried graph for related entities)

### Neo4j Reasoning Graph Schema

```cypher
// Decision node (one per tool call or agent reasoning step)
CREATE (d:Decision {
    id: "decision_123",
    action: "extract_entities",  // Tool name or reasoning step
    timestamp: datetime("2026-05-10T14:30:00Z"),
    conversation_id: "conv_789",
    reasoning: "User mentioned new contact Sarah Chen and company Acme Corp",
    span_id: "abc123def456",  // Link to OpenTelemetry span
    duration_ms: 1250
})

// Input node (message or context that triggered decision)
CREATE (input:Input {
    id: "input_456",
    type: "user_message",
    content: "I met Sarah Chen from Acme Corp at AWS Summit",
    timestamp: datetime("2026-05-10T14:29:55Z")
})

// ToolCall node (parameters passed to tool)
CREATE (tc:ToolCall {
    id: "toolcall_789",
    tool_name: "extract_entities",
    parameters: {user_message: "...", conversation_id: "conv_789"},
    span_id: "def456ghi789"  // OpenTelemetry span ID
})

// Outcome node (result of tool execution)
CREATE (out:Outcome {
    id: "outcome_101",
    success: true,
    entities_created: 3,
    relationships_created: 2,
    summary: "Extracted Person(Sarah Chen), Organization(Acme Corp), Event(AWS Summit)"
})

// Provenance relationships
CREATE (d)-[:TRIGGERED_BY]->(input)
CREATE (d)-[:EXECUTED]->(tc)
CREATE (tc)-[:RESULTED_IN]->(out)

// Link to created entities (from long-term memory graph)
MATCH (p:Person {id: "person_123"})
CREATE (out)-[:CREATED]->(p)

// Link to next decision (temporal chain)
MATCH (next:Decision {conversation_id: "conv_789", timestamp: datetime("2026-05-10T14:31:00Z")})
CREATE (d)-[:FOLLOWED_BY]->(next)
```

### Querying Decision Provenance

**Query 1: Why did the agent extract entities?**

```cypher
MATCH (d:Decision {action: "extract_entities"})-[:TRIGGERED_BY]->(input:Input)
WHERE d.conversation_id = "conv_789"
RETURN d.timestamp, d.reasoning, input.content
ORDER BY d.timestamp DESC
LIMIT 1

// Result:
// 2026-05-10T14:30:00Z | "User mentioned new contact..." | "I met Sarah Chen..."
```

**Query 2: What decisions led to creating entity Sarah Chen?**

```cypher
MATCH (p:Person {name: "Sarah Chen"})<-[:CREATED]-(out:Outcome)<-[:RESULTED_IN]-(tc:ToolCall)<-[:EXECUTED]-(d:Decision)
MATCH (d)-[:TRIGGERED_BY]->(input:Input)
RETURN d.action, d.reasoning, input.content, d.timestamp
ORDER BY d.timestamp

// Result:
// extract_entities | "User mentioned new contact" | "I met Sarah Chen..." | 2026-05-10T14:30:00Z
```

**Query 3: Full conversation decision timeline**

```cypher
MATCH path = (first:Decision {conversation_id: "conv_789"})-[:FOLLOWED_BY*]->(last:Decision)
WHERE NOT (first)<-[:FOLLOWED_BY]-()
RETURN [n IN nodes(path) | {action: n.action, timestamp: n.timestamp, reasoning: n.reasoning}] as timeline
```

**Query 4: Link OpenTelemetry traces to provenance**

```cypher
// Find decision by OpenTelemetry span ID
MATCH (d:Decision {span_id: "abc123def456"})
MATCH (d)-[:EXECUTED]->(tc:ToolCall)-[:RESULTED_IN]->(out:Outcome)
RETURN d.action, d.reasoning, tc.parameters, out.summary

// Use this to jump from X-Ray trace → Neo4j provenance graph
```

### Implementing Decision Logging

**Hook in AgentCore Runtime:**

```python
# agent_files/booking_agent.py
from strands.hooks import HookProvider, HookRegistry, AfterToolCallEvent
from opentelemetry import trace
import boto3

class DecisionProvenanceHook(HookProvider):
    def __init__(self):
        self._lambda_client = boto3.client("lambda")
        self._log_decision_function = os.environ["LOG_DECISION_FUNCTION_NAME"]
    
    def register_hooks(self, registry: HookRegistry):
        registry.add_callback(AfterToolCallEvent, self.log_decision)
    
    def log_decision(self, event: AfterToolCallEvent):
        # Get OpenTelemetry span context
        current_span = trace.get_current_span()
        span_context = current_span.get_span_context()
        
        # Invoke log_decision Lambda asynchronously
        self._lambda_client.invoke(
            FunctionName=self._log_decision_function,
            InvocationType="Event",  # Async (don't block agent)
            Payload=json.dumps({
                "tool_name": event.tool_use["name"],
                "parameters": event.tool_use["input"],
                "result": event.result,
                "timestamp": datetime.now().isoformat(),
                "conversation_id": getattr(event, "conversation_id", "unknown"),
                "reasoning": getattr(event, "reasoning", None),
                "span_id": f"{span_context.trace_id:032x}:{span_context.span_id:016x}"  # Link to X-Ray
            })
        )
```

**Lambda log_decision implementation:**

```python
# lambda_tools/log_decision/lambda_function.py
from neo4j import GraphDatabase
import os

NEO4J_URI = get_secret("NEO4J_URI")
NEO4J_USER = get_secret("NEO4J_USER")
NEO4J_PASSWORD = get_secret("NEO4J_PASSWORD")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

def handler(event, context):
    decision_id = generate_id()
    
    with driver.session() as session:
        # Create Decision node
        session.run("""
            CREATE (d:Decision {
                id: $decision_id,
                action: $tool_name,
                timestamp: datetime($timestamp),
                conversation_id: $conversation_id,
                reasoning: $reasoning,
                span_id: $span_id,
                duration_ms: $duration_ms
            })
        """, {
            "decision_id": decision_id,
            "tool_name": event["tool_name"],
            "timestamp": event["timestamp"],
            "conversation_id": event["conversation_id"],
            "reasoning": event.get("reasoning"),
            "span_id": event["span_id"],
            "duration_ms": event.get("duration_ms", 0)
        })
        
        # Link to created entities (if tool was extract_entities)
        if event["tool_name"] == "extract_entities" and "entities" in event["result"]:
            for entity in event["result"]["entities"]:
                session.run("""
                    MATCH (d:Decision {id: $decision_id})
                    MATCH (e) WHERE e.id = $entity_id
                    CREATE (d)-[:CREATED]->(e)
                """, {"decision_id": decision_id, "entity_id": entity["id"]})
        
        # Link to previous decision (temporal chain)
        session.run("""
            MATCH (d:Decision {id: $decision_id})
            MATCH (prev:Decision {conversation_id: $conversation_id})
            WHERE prev.timestamp < d.timestamp
            WITH d, prev
            ORDER BY prev.timestamp DESC
            LIMIT 1
            CREATE (prev)-[:FOLLOWED_BY]->(d)
        """, {"decision_id": decision_id, "conversation_id": event["conversation_id"]})
    
    return {"decision_id": decision_id}
```

---

## Observability Dashboard

### Combined Dashboard (CloudWatch + X-Ray + Neo4j)

**Dashboard sections:**

1. **Infrastructure Health** (CloudWatch)
   - AgentCore Runtime: Invocations, Duration (P95), Errors
   - Lambda Tools: Invocations per tool, Duration (P95), Concurrent executions
   - DynamoDB: ConsumedReadCapacity, ConsumedWriteCapacity, ThrottledRequests
   - Neo4j: Connection errors (custom metric from Lambda)

2. **Agent Behavior** (X-Ray Insights)
   - Service map: AgentCore → Lambda tools → DynamoDB/Neo4j/OpenAI
   - Slowest traces (>5s)
   - Failed tool calls (error = true)
   - Steering rule blocks (hook.cancelled = true)

3. **Decision Provenance** (Neo4j queries via CloudWatch dashboard custom widget)
   - Total decisions logged (Cypher: `MATCH (d:Decision) RETURN count(d)`)
   - Decisions per tool (Cypher: `MATCH (d:Decision) RETURN d.action, count(d)`)
   - Average decision chain length (Cypher: `MATCH path=(d)-[:FOLLOWED_BY*]->() RETURN avg(length(path))`)

**Example custom CloudWatch widget for Neo4j metrics:**

```python
# Lambda function that queries Neo4j and returns metric
def neo4j_metric_collector(event, context):
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    with driver.session() as session:
        # Query: Total decisions logged
        result = session.run("MATCH (d:Decision) RETURN count(d) as count")
        decision_count = result.single()["count"]
        
        # Publish to CloudWatch
        cloudwatch.put_metric_data(
            Namespace='ContextGraph/Provenance',
            MetricData=[{
                'MetricName': 'DecisionsLogged',
                'Value': decision_count,
                'Unit': 'Count'
            }]
        )
    
    return {"statusCode": 200}

# Invoke this Lambda every 5 minutes via EventBridge rule
```

---

## When Observability Becomes Critical

### Production Scenarios

1. **Agent makes wrong decision:**
   - X-Ray: Which tool calls happened? (tool sequence)
   - Neo4j: Why did agent think this was correct? (reasoning field)
   - CloudWatch: Was steering rule supposed to block this? (hook logs)

2. **Slow agent response:**
   - CloudWatch: Which Lambda is slow? (Duration metric)
   - X-Ray: Is OpenAI API slow? (external call duration)
   - Neo4j: Did agent query too many entities? (check query_context Decision nodes)

3. **Cost spike:**
   - CloudWatch: Which tool is called most? (Invocations metric)
   - X-Ray: How many LLM calls per agent invocation? (llm.request spans)
   - Neo4j: Are we extracting duplicate entities? (CREATED relationships per entity)

4. **Compliance audit:**
   - Neo4j: "Show all decisions that accessed user data X"
   - Neo4j: "Which agent made this booking decision and why?"
   - X-Ray + Neo4j: Link span_id from audit log → full decision chain

---

## Summary: Three Layers Working Together

| Question | CloudWatch | X-Ray | Neo4j Provenance |
|----------|------------|-------|------------------|
| How long did it take? | ✅ Duration metric | ✅ Span duration | ❌ |
| Did it succeed? | ✅ Errors metric | ✅ Span status | ✅ Outcome.success |
| How many times? | ✅ Invocations | ❌ | ✅ MATCH (d:Decision) |
| **Why did it happen?** | ❌ | ❌ | ✅ Decision.reasoning |
| **What context led to this?** | ❌ | ❌ | ✅ TRIGGERED_BY → Input |
| **What happened next?** | ❌ | ❌ | ✅ FOLLOWED_BY → Decision |
| Which tool called which? | ❌ | ✅ Service map | ✅ Decision chain |
| Was rule applied? | ✅ Hook logs | ✅ hook.cancelled | ❌ |

**Use all three together for complete observability.**

---

## Cost Considerations

| Service | Cost | Volume (10K agent invocations/month) | Monthly Cost |
|---------|------|--------------------------------------|--------------|
| CloudWatch Logs | $0.50/GB ingested | ~5GB (agent + tool logs) | ~$2.50 |
| CloudWatch Metrics | $0.30 per custom metric | 10 custom metrics | ~$3.00 |
| X-Ray Traces | $5.00 per 1M traces | 10K traces + 30K tool calls = 40K | ~$0.20 |
| Neo4j AuraDB Free | $0 | 50K Decision nodes | $0 |
| **Total** | | | **~$6/month** |

**Optimization tips:**
- Sample X-Ray traces (10% sampling = 90% cost reduction)
- Use CloudWatch Logs Insights instead of storing all logs (query on-demand)
- Batch Decision logging (buffer 10 decisions, write once)

---

**Next:** See WHEN_TO_USE_NEO4J.md for guidance on when the complexity of a knowledge graph is justified.
