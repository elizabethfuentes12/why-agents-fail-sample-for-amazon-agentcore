# When to Use Neo4j for Agent Memory

## TL;DR Decision Tree

```
Does your agent need to answer these questions?
├─ "Who works at Company X?" → YES: Use Neo4j (relationship queries)
├─ "What did we discuss last week?" → NO: Use DynamoDB (simple retrieval)
├─ "Find people who attended Event Y and work at Company Z" → YES: Use Neo4j (multi-hop)
├─ "Show me my last 10 messages" → NO: Use DynamoDB (sorted range query)
├─ "Why did you make Decision X?" → YES: Use Neo4j (provenance chains)
└─ "Retrieve user preferences" → NO: Use DynamoDB (key-value)
```

**Rule of thumb:** If your query involves **relationships** or **graph traversal**, use Neo4j. If it's **simple retrieval by ID or timestamp**, use DynamoDB.

---

## Neo4j vs DynamoDB: Architecture Decision

### When to Use DynamoDB (Simpler, Cheaper)

**Use DynamoDB when:**

1. **Simple key-value retrieval:**
   ```python
   # Get user preferences
   response = dynamodb.get_item(Key={"user_id": "user_123"})
   ```

2. **Time-series data (conversation history):**
   ```python
   # Get last 20 messages in conversation
   response = dynamodb.query(
       KeyConditionExpression="conversation_id = :conv_id",
       SortKeyCondition="message_timestamp BETWEEN :start AND :end",
       Limit=20
   )
   ```

3. **No relationship queries:**
   - "Show my bookings" ✅
   - "List conversations for user X" ✅
   - "Get steering rules for tool Y" ✅

4. **Cost constraints:**
   - DynamoDB on-demand: $1.25 per 1M writes, $0.25 per 1M reads
   - Neo4j AuraDB: Free tier (50K nodes), then $65/month minimum

5. **Predictable access patterns:**
   - Always query by primary key (conversation_id, user_id, booking_id)
   - No "find all X related to Y" queries

**Example: Conversation History (DynamoDB is perfect)**

```python
# Store conversation
dynamodb.put_item(
    Item={
        "conversation_id": "conv_123",
        "message_timestamp": "2026-05-10T14:30:00Z",
        "role": "user",
        "content": "I met Sarah Chen from Acme Corp"
    }
)

# Retrieve conversation
response = dynamodb.query(
    KeyConditionExpression="conversation_id = :id",
    ScanIndexForward=False,  # Latest first
    Limit=20
)
```

**No relationships needed** → DynamoDB is simpler and cheaper.

---

### When to Use Neo4j (Relationships Matter)

**Use Neo4j when:**

1. **Relationship-based queries:**
   ```cypher
   // Find all people who work at companies we discussed
   MATCH (p:Person)-[:WORKS_AT]->(o:Organization)
   WHERE o.name IN ["Acme Corp", "TechCo"]
   RETURN p.name, o.name
   ```

2. **Multi-hop traversal:**
   ```cypher
   // Find people who attended same events as Sarah Chen
   MATCH (sarah:Person {name: "Sarah Chen"})-[:ATTENDED]->(e:Event)<-[:ATTENDED]-(other:Person)
   RETURN other.name, e.name
   ```

3. **Graph algorithms:**
   ```cypher
   // Find shortest path between two people (degrees of separation)
   MATCH path = shortestPath(
       (p1:Person {name: "Sarah Chen"})-[*]-(p2:Person {name: "John Doe"})
   )
   RETURN path
   ```

4. **Decision provenance chains:**
   ```cypher
   // Why did we create entity X? (follow provenance back to original input)
   MATCH (entity:Person {name: "Sarah Chen"})<-[:CREATED]-(out:Outcome)<-[:RESULTED_IN]-(tc:ToolCall)<-[:EXECUTED]-(d:Decision)-[:TRIGGERED_BY]->(input:Input)
   RETURN d.reasoning, input.content
   ```

5. **Frequent "find related entities" queries:**
   - "Who works at Company X?" → Neo4j ✅, DynamoDB ❌ (requires scan)
   - "What events did Person Y attend?" → Neo4j ✅, DynamoDB ❌ (requires index + filter)
   - "Find all X connected to Y" → Neo4j ✅, DynamoDB ❌ (not designed for this)

**Example: Entity Relationships (Neo4j shines)**

```cypher
// Store entities with relationships
CREATE (sarah:Person {id: "person_123", name: "Sarah Chen"})
CREATE (acme:Organization {id: "org_456", name: "Acme Corp"})
CREATE (summit:Event {id: "event_789", name: "AWS Summit 2026"})
CREATE (sarah)-[:WORKS_AT]->(acme)
CREATE (sarah)-[:ATTENDED]->(summit)

// Query: Find all people we know at Acme Corp
MATCH (p:Person)-[:WORKS_AT]->(o:Organization {name: "Acme Corp"})
RETURN p.name, p.email
```

**DynamoDB alternative would require:**
1. Scan entire Persons table
2. Filter by `organization = "Acme Corp"` (slow, expensive)
3. Requires GSI (Global Secondary Index) for each query pattern

**Neo4j: One query, instant results.**

---

## Real-World Demo 07 Decision

### Our Use Case: Context Graph Agent

**What the agent needs to do:**

1. ✅ **Extract entities from conversations** → POLE+O model (Person, Organization, Location, Event, Object)
2. ✅ **Answer relationship queries:**
   - "Who works at Acme Corp?"
   - "What companies are interested in Product X?"
   - "Who attended Event Y?"
3. ✅ **Decision provenance:**
   - "Why did you extract entity X?"
   - "What decisions led to this outcome?"
4. ✅ **Multi-turn conversation history:**
   - "Show me our last conversation"
   - "Retrieve context for conversation_id"

**Our architecture decision:**

```
┌─────────────────────────────────────────────────────────────────┐
│                      MEMORY LAYER                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  DynamoDB Conversations (SHORT-TERM MEMORY)                     │
│  ├─ Store: conversation_id, message_timestamp, role, content   │
│  ├─ Retrieve: Last N messages for conversation                 │
│  └─ Use case: "Show me our chat history"                       │
│                                                                 │
│  Neo4j Entities (LONG-TERM MEMORY)                              │
│  ├─ Store: Person, Organization, Location, Event nodes         │
│  ├─ Relationships: WORKS_AT, ATTENDED, INTERESTED_IN           │
│  └─ Use case: "Who works at Acme Corp?"                        │
│                                                                 │
│  Neo4j Decisions (REASONING MEMORY)                             │
│  ├─ Store: Decision, ToolCall, Outcome nodes                   │
│  ├─ Relationships: EXECUTED, RESULTED_IN, FOLLOWED_BY          │
│  └─ Use case: "Why did you create entity X?"                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Why we use BOTH:**
- **DynamoDB** for conversation history (simple time-series retrieval)
- **Neo4j** for entity relationships + decision provenance (graph queries)

---

## Cost Analysis: DynamoDB-Only vs Neo4j Hybrid

### Scenario: 10,000 agent conversations/month

**Assumptions:**
- Each conversation: 10 messages (5 user + 5 agent)
- Each conversation extracts 3 entities with 2 relationships
- Agent makes 5 decisions per conversation

---

### **Option A: DynamoDB Only (No Neo4j)**

**Data model:**

```python
# Conversations table (same as before)
{
    "conversation_id": "conv_123",
    "message_timestamp": "2026-05-10T14:30:00Z",
    "role": "user",
    "content": "..."
}

# Entities table (flattened)
{
    "entity_id": "person_123",
    "entity_type": "Person",
    "name": "Sarah Chen",
    "organization": "Acme Corp",  # Denormalized!
    "events_attended": ["AWS Summit"],  # Denormalized!
    "conversation_id": "conv_123"
}

# Decisions table (flattened)
{
    "decision_id": "decision_789",
    "action": "extract_entities",
    "conversation_id": "conv_123",
    "entities_created": ["person_123", "org_456"],  # Denormalized!
    "timestamp": "2026-05-10T14:30:00Z"
}
```

**Queries:**

1. **"Who works at Acme Corp?"**
   ```python
   # Requires GSI on organization field
   response = dynamodb.query(
       IndexName="organization-index",
       KeyConditionExpression="organization = :org",
       ExpressionAttributeValues={":org": "Acme Corp"}
   )
   # Cost: 1 RCU per 4KB = ~1 RCU per query
   ```

2. **"What decisions created entity X?"**
   ```python
   # Requires Scan (no efficient query possible)
   response = dynamodb.scan(
       TableName="Decisions",
       FilterExpression="contains(entities_created, :entity_id)",
       ExpressionAttributeValues={":entity_id": "person_123"}
   )
   # Cost: Scans entire table = ~100 RCU
   ```

3. **"Find people who attended Event Y and work at Company Z"**
   ```python
   # Requires TWO queries + manual join in application code
   # Step 1: Query Entities by organization (GSI)
   # Step 2: Filter results by events_attended (client-side)
   # Cost: ~5 RCU + application complexity
   ```

**Monthly cost:**

| Operation | Volume | Cost per operation | Monthly cost |
|-----------|--------|-------------------|--------------|
| Write conversations (100K messages) | 100K | $1.25/1M writes | $0.13 |
| Write entities (30K entities) | 30K | $1.25/1M writes | $0.04 |
| Write decisions (50K decisions) | 50K | $1.25/1M writes | $0.06 |
| Read conversations (10K queries) | 10K | $0.25/1M reads | $0.003 |
| Query entities by relationship (5K) | 5K | $0.25/1M reads | $0.001 |
| **Scan decisions (500 queries)** | 500 × 100 RCU | $0.25/1M reads | **$0.01** |
| **GSI writes (30K)** | 30K | $1.25/1M writes | $0.04 |
| **Total** | | | **$0.28/month** |

**Problems:**
- ❌ Scans are slow and scale poorly (500 queries × 100 RCU = 50K RCU)
- ❌ Denormalized data requires complex application logic
- ❌ Multi-hop queries ("friends of friends") are impossible
- ❌ No decision provenance chains (FOLLOWED_BY relationships)

---

### **Option B: DynamoDB + Neo4j Hybrid (Our Architecture)**

**Data model:**

```python
# DynamoDB: Conversations only
{
    "conversation_id": "conv_123",
    "message_timestamp": "2026-05-10T14:30:00Z",
    "role": "user",
    "content": "..."
}
```

```cypher
// Neo4j: Entities with relationships
(sarah:Person)-[:WORKS_AT]->(acme:Organization)
(sarah)-[:ATTENDED]->(summit:Event)

// Neo4j: Decision provenance
(decision)-[:CREATED]->(sarah)
(decision)-[:FOLLOWED_BY]->(next_decision)
```

**Queries:**

1. **"Who works at Acme Corp?"**
   ```cypher
   MATCH (p:Person)-[:WORKS_AT]->(o:Organization {name: "Acme Corp"})
   RETURN p.name
   // Cost: ~10ms query, $0 (AuraDB Free tier)
   ```

2. **"What decisions created entity X?"**
   ```cypher
   MATCH (d:Decision)-[:CREATED]->(e:Person {id: "person_123"})
   RETURN d
   // Cost: ~5ms query, $0
   ```

3. **"Find people who attended Event Y and work at Company Z"**
   ```cypher
   MATCH (p:Person)-[:ATTENDED]->(:Event {name: "Event Y"})
   WHERE (p)-[:WORKS_AT]->(:Organization {name: "Company Z"})
   RETURN p.name
   // Cost: ~15ms query, $0
   ```

**Monthly cost:**

| Operation | Volume | Cost per operation | Monthly cost |
|-----------|--------|-------------------|--------------|
| Write conversations (100K messages) | 100K | $1.25/1M writes | $0.13 |
| Neo4j AuraDB Free | 50K nodes | $0 | $0.00 |
| Neo4j entity writes (from Lambda) | 30K | Included | $0.00 |
| Neo4j decision writes (from Lambda) | 50K | Included | $0.00 |
| Neo4j queries (5K relationship queries) | 5K | Included | $0.00 |
| **Total** | | | **$0.13/month** |

**Benefits:**
- ✅ Relationship queries are instant (10-15ms)
- ✅ Multi-hop traversal is native (FOLLOWED_BY chains)
- ✅ Decision provenance is explicit (graph structure)
- ✅ Simpler application code (Cypher vs manual joins)
- ✅ **Cheaper than DynamoDB-only** (no GSI writes, no scans)

---

## When Neo4j Becomes Too Complex

### Don't use Neo4j if:

1. **You never query relationships:**
   ```
   Queries you DO have:
   - "Get conversation history for user X" → DynamoDB ✅
   - "Retrieve booking BK-123" → DynamoDB ✅
   - "List steering rules for tool Y" → DynamoDB ✅
   
   Queries you DON'T have:
   - "Who works at X?"
   - "Find people connected to Y"
   - "Show decision provenance"
   
   → Don't use Neo4j. DynamoDB is sufficient.
   ```

2. **Your graph is just a list:**
   ```cypher
   // If your "graph" looks like this:
   (entity1)  (entity2)  (entity3)  (entity4)  (entity5)
   
   // No relationships → Not a graph → Use DynamoDB
   ```

3. **You have <1000 entities total:**
   - Neo4j overhead (connection pooling, Cypher parsing) is overkill
   - DynamoDB scan of 1000 items = 250 RCU = $0.00006 per query
   - Not worth Neo4j complexity

4. **Your access pattern is always "get by ID":**
   ```python
   # If this is your ONLY query pattern:
   dynamodb.get_item(Key={"entity_id": "person_123"})
   
   # Neo4j equivalent:
   session.run("MATCH (p:Person {id: $id}) RETURN p", id="person_123")
   
   # DynamoDB is faster and simpler for key-value retrieval
   ```

5. **You can't manage Neo4j operationally:**
   - Requires monitoring Neo4j AuraDB (auto-pause after inactivity)
   - Requires Neo4j-specific alerting (connection pool exhausted, slow queries)
   - Requires Cypher query optimization skills
   - If your team only knows SQL/DynamoDB, learning curve is steep

---

## Demo 07: Justified Use of Neo4j

### Why we chose Neo4j for Demo 07:

**Use case: Context-aware agent that remembers entities and explains decisions**

**Requirements:**

1. ✅ **"Who works at Company X?"** → Neo4j relationship query
2. ✅ **"What events did Person Y attend?"** → Neo4j traversal
3. ✅ **"Find people who attended Event Z and work at Company X"** → Neo4j multi-hop
4. ✅ **"Why did you extract entity X?"** → Neo4j provenance chain (Decision)-[:CREATED]->(Entity)
5. ✅ **"What decisions led to outcome Y?"** → Neo4j temporal chain (Decision)-[:FOLLOWED_BY]->(Decision)
6. ✅ **"Shortest path between Person A and Person B"** → Neo4j graph algorithm

**These queries are:**
- ❌ Impossible in DynamoDB (no relationship model)
- ❌ Extremely slow in DynamoDB (require multiple scans + manual joins)
- ✅ Native in Neo4j (10-20ms Cypher queries)

**Cost justification:**
- Neo4j AuraDB Free: 50K nodes, 175K relationships = enough for 15,000 conversations with entity extraction
- If we exceed free tier: $65/month for AuraDB Professional
- DynamoDB alternative: Complex GSI architecture + slow scans = worse performance at similar cost

**Operational justification:**
- Neo4j AuraDB is **fully managed** (no server maintenance)
- Auto-pause saves cost during inactivity
- Cypher queries are **declarative** (easier to maintain than manual joins in application code)

**Educational justification (for CFP talk):**
- Demonstrates **three-memory architecture** (STM + LTM + RM)
- Shows **real-world Graph-RAG** beyond just retrieval
- Highlights **decision provenance** for explainable AI (critical for regulated industries)

---

## Migration Path: Start Simple, Add Neo4j When Needed

### Phase 1: DynamoDB Only (MVP)

```python
# Start with DynamoDB for ALL data
Tables:
- Conversations (conversation_id, message_timestamp, content)
- Entities (entity_id, name, type, metadata_json)
- Decisions (decision_id, action, timestamp, metadata_json)

# Accept limitations:
- No relationship queries
- Manual filtering in application code
```

**When to move to Phase 2:**
- You find yourself writing complex application-side joins
- Queries like "find all X related to Y" become common
- Decision provenance becomes a requirement (audit, compliance)

---

### Phase 2: Hybrid (DynamoDB + Neo4j)

```python
# DynamoDB: Conversations only (time-series retrieval)
Conversations table (unchanged)

# Neo4j: Entities + Relationships + Provenance
(Person)-[:WORKS_AT]->(Organization)
(Decision)-[:CREATED]->(Entity)
(Decision)-[:FOLLOWED_BY]->(Decision)
```

**Migration strategy:**
1. Deploy Neo4j AuraDB Free
2. Backfill entities from DynamoDB Entities table → Neo4j
3. Update `extract_entities` Lambda to write to Neo4j (not DynamoDB Entities)
4. Keep DynamoDB Entities table as read-only backup (delete after 30 days)
5. Update queries to use Neo4j for relationships, DynamoDB for conversations

**Rollback plan:**
- If Neo4j fails, fall back to DynamoDB Entities table (read-only)
- Re-enable writes to DynamoDB Entities if needed

---

## Summary: Decision Framework

| Factor | Use DynamoDB | Use Neo4j |
|--------|--------------|-----------|
| **Queries** | Key-value, time-series | Relationships, traversal |
| **Data size** | Any size | >1000 entities |
| **Query patterns** | "Get by ID", "List recent" | "Find related", "Provenance" |
| **Cost** | $0.25-$1.25 per 1M ops | Free (50K nodes), then $65/month |
| **Complexity** | Low (familiar) | Medium (learn Cypher) |
| **Latency** | <10ms (key-value) | 10-50ms (graph queries) |
| **Use case** | Conversation history, preferences | Entity relationships, decision chains |

**For Demo 07:**
- ✅ Use DynamoDB for conversation history (simple retrieval)
- ✅ Use Neo4j for entity relationships + decision provenance (complex graph queries)
- ✅ Justify Neo4j with concrete query examples (not just "it's cool")

---

## Next Steps

1. **Review your query patterns:**
   - List ALL queries your agent needs to answer
   - For each query, ask: "Does this involve relationships or traversal?"
   - If yes → Neo4j, if no → DynamoDB

2. **Prototype with DynamoDB first:**
   - Build MVP with DynamoDB-only
   - Measure: How often do you need relationship queries?
   - If >20% of queries are relationship-based → add Neo4j

3. **Monitor query performance:**
   - DynamoDB scans taking >500ms? → Consider Neo4j
   - Application code has complex manual joins? → Consider Neo4j
   - Users asking "why did you do X?" → Provenance graph → Neo4j

4. **Cost-benefit analysis:**
   - DynamoDB with GSIs + scans: Calculate monthly cost
   - Neo4j AuraDB: $0 (free tier) or $65/month (professional)
   - If Neo4j is cheaper OR queries are >10x faster → worth it

**Remember:** Neo4j is a tool, not a requirement. Use it when relationships matter.
