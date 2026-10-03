"""Context-Aware Agent using Strands Swarm for multi-agent orchestration.

Demonstrates three-memory architecture with automatic agent handoffs:
- Short-term memory: Neo4j Message nodes (conversation history)
- Long-term memory: Neo4j POLE+O entities (extracted facts)
- Reasoning memory: Neo4j Decision nodes (provenance graph)

Uses Strands Swarm instead of manual delegation for cleaner orchestration.
"""

import os
from typing import Any

from dotenv import load_dotenv
from neo4j_agent_memory import MemoryContext, add_entity, add_messages, query_entities
from neo4j_agent_memory.integrations.strands import StrandsConfig, context_graph_tools
from strands import Agent, tool
from strands.models import OpenAIModel
from strands.multiagent import Swarm

load_dotenv()

# Verify required environment variables
if not os.environ.get("OPENAI_API_KEY"):
    raise ValueError(
        "OPENAI_API_KEY not set. Get yours at https://platform.openai.com/api-keys "
        "and add it to a .env file."
    )
if not os.environ.get("NEO4J_URI"):
    raise ValueError("NEO4J_URI not set (e.g., bolt://localhost:7687)")
if not os.environ.get("NEO4J_PASSWORD"):
    raise ValueError("NEO4J_PASSWORD not set")


# --- Agent System Prompts ---

EXTRACTOR_PROMPT = """You are an entity extraction agent.

Your job: Extract entities (Person, Organization, Location, Event, Object) from user messages
and store them in the knowledge graph.

Use the extract_and_store_entities tool to:
1. Identify all entities in the conversation
2. Extract relationships between them
3. Store in Neo4j using POLE+O model

After extraction, hand off to the query agent to retrieve relevant context."""


QUERY_PROMPT = """You are a context query agent.

Your job: Query the knowledge graph for entities and relationships relevant to the user's question.

Use the query_context tool to:
1. Search for entities by type (Person, Organization, etc.)
2. Find relationships between entities
3. Retrieve historical context

After querying, hand off to the response agent with your findings."""


RESPONSE_PROMPT = """You are a response synthesis agent.

Your job: Synthesize information from the knowledge graph into a helpful response for the user.

You have access to:
- Extracted entities (from extractor agent)
- Historical context (from query agent)
- Conversation history (from short-term memory)

Provide a clear, concise answer that references specific entities and relationships."""


# --- Tools ---

@tool
def extract_and_store_entities(
    message: str,
    entities: list[dict[str, Any]],
) -> dict[str, Any]:
    """Extract entities from message and store in knowledge graph.

    Args:
        message: The user message to extract from
        entities: List of entity dicts with keys: name, entity_type, description

    Returns:
        Dict with status and entity_ids
    """
    context = MemoryContext(
        neo4j_uri=os.environ["NEO4J_URI"],
        neo4j_user=os.environ.get("NEO4J_USER", "neo4j"),
        neo4j_password=os.environ["NEO4J_PASSWORD"],
    )

    # Store message in STM
    add_messages(context, [{"role": "user", "content": message}])

    # Store entities in LTM
    entity_ids = []
    for entity in entities:
        entity_id = add_entity(
            context,
            name=entity["name"],
            entity_type=entity["entity_type"],
            description=entity.get("description", ""),
        )
        entity_ids.append(entity_id)

    return {
        "status": "extracted",
        "entity_count": len(entity_ids),
        "entity_ids": entity_ids,
        "message": f"Extracted {len(entity_ids)} entities from message",
    }


@tool
def query_context(
    entity_type: str | None = None,
    entity_name: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Query knowledge graph for entities and relationships.

    Args:
        entity_type: Filter by type (Person, Organization, Location, Event, Object)
        entity_name: Filter by name (partial match)
        limit: Maximum results to return

    Returns:
        Dict with matching entities and their relationships
    """
    context = MemoryContext(
        neo4j_uri=os.environ["NEO4J_URI"],
        neo4j_user=os.environ.get("NEO4J_USER", "neo4j"),
        neo4j_password=os.environ["NEO4J_PASSWORD"],
    )

    # Query entities
    filters = {}
    if entity_type:
        filters["entity_type"] = entity_type
    if entity_name:
        filters["name_contains"] = entity_name

    entities = query_entities(context, filters=filters, limit=limit)

    return {
        "status": "queried",
        "entity_count": len(entities),
        "entities": [
            {
                "id": e.get("id"),
                "name": e.get("name"),
                "type": e.get("entity_type"),
                "description": e.get("description"),
            }
            for e in entities
        ],
    }


# --- Create Agents ---

model = OpenAIModel("gpt-4o-mini")

extractor_agent = Agent(
    model=model,
    tools=[extract_and_store_entities],
    system_prompt=EXTRACTOR_PROMPT,
)

query_agent = Agent(
    model=model,
    tools=[query_context],
    system_prompt=QUERY_PROMPT,
)

response_agent = Agent(
    model=model,
    tools=[],  # No tools, just synthesizes responses
    system_prompt=RESPONSE_PROMPT,
)

# --- Create Swarm ---

swarm = Swarm(
    nodes=[extractor_agent, query_agent, response_agent],
    entry_point=extractor_agent,  # Always start with extraction
    max_handoffs=10,  # Prevent infinite loops
    max_iterations=20,
    execution_timeout=300.0,  # 5 minutes total
    node_timeout=60.0,  # 1 minute per agent
    repetitive_handoff_detection_window=5,  # Detect loops in last 5 handoffs
    repetitive_handoff_min_unique_agents=2,  # Require at least 2 different agents
)


# --- Demo ---

if __name__ == "__main__":
    print("🧠 Context-Aware Agent (Swarm Architecture)\n")
    print("=" * 60)

    # Test conversation
    messages = [
        "I met Sarah Chen from Acme Corp at AWS Summit. She's interested in our enterprise tier.",
        "What companies are interested in our enterprise tier?",
        "Who did I meet at AWS Summit?",
    ]

    for i, msg in enumerate(messages, 1):
        print(f"\n[Turn {i}] User: {msg}")
        print("-" * 60)

        # Invoke swarm (automatic agent handoffs)
        result = swarm(msg)

        print(f"✅ Status: {result.status}")
        print(f"📊 Iterations: {result.iterations}")
        print(f"🔄 Handoffs: {len([e for e in result.events if e.get('type') == 'multi_agent_handoff'])}")

        # Print final response
        if result.final_response:
            print(f"\n🤖 Agent: {result.final_response}")

        print("=" * 60)

    print("\n✅ Demo complete!")
    print("\nKey differences from delegation pattern:")
    print("- No manual @tool wrappers for sub-agents")
    print("- Swarm automatically routes between agents")
    print("- Built-in loop detection and timeouts")
    print("- Shared working memory across all agents")
