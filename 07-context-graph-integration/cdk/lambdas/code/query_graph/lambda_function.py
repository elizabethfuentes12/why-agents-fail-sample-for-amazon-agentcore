"""Lambda function to query the Neo4j context graph.

This function provides graph query capabilities for AI agents, including:
- Entity search by name or type
- Relationship traversal
- Context retrieval for LLM prompts
- Cypher query execution

Environment Variables:
    NEO4J_URI: Bolt connection URI
    NEO4J_PASSWORD_SECRET_ARN: Secrets Manager ARN for Neo4j password
    NEO4J_USER: Neo4j username (default: neo4j)
    NEO4J_DATABASE: Neo4j database name (default: neo4j)
"""

import asyncio
import json
import logging
import os
import boto3
from typing import Any, Dict, List

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize boto3 clients
secrets_client = boto3.client("secretsmanager")


def get_neo4j_password() -> str:
    """Retrieve Neo4j password from Secrets Manager."""
    secret_arn = os.environ["NEO4J_PASSWORD_SECRET_ARN"]
    response = secrets_client.get_secret_value(SecretId=secret_arn)
    return response["SecretString"]


async def query_entities(
    entity_type: str | None = None,
    actor_id: str | None = None,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """Query entities from the context graph.

    Args:
        entity_type: Filter by entity type (Person, Organization, etc.)
        actor_id: Filter by actor_id for multi-tenant isolation
        limit: Maximum number of results

    Returns:
        List of entity dictionaries
    """
    from neo4j_agent_memory import MemoryClient, MemorySettings
    from neo4j_agent_memory.config.settings import Neo4jConfig, EmbeddingConfig, EmbeddingProvider

    neo4j_uri = os.environ["NEO4J_URI"]
    neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
    neo4j_password = get_neo4j_password()
    neo4j_database = os.environ.get("NEO4J_DATABASE", "neo4j")

    settings = MemorySettings(
        neo4j=Neo4jConfig(
            uri=neo4j_uri,
            user=neo4j_user,
            password=neo4j_password,
            database=neo4j_database
        ),
        embedding=EmbeddingConfig(
            provider=EmbeddingProvider.SENTENCE_TRANSFORMERS,
            model="all-MiniLM-L6-v2"
        )
    )

    async with MemoryClient(settings) as memory:
        # Build Cypher query
        where_clauses = []
        if entity_type:
            where_clauses.append(f"e.entity_type = '{entity_type}'")
        if actor_id:
            where_clauses.append(f"e.actor_id = '{actor_id}'")

        where_clause = " AND ".join(where_clauses) if where_clauses else "true"

        cypher = f"""
        MATCH (e)
        WHERE {where_clause}
        RETURN e
        LIMIT {limit}
        """

        logger.info(f"Executing Cypher: {cypher}")

        # Execute query using memory client's driver
        async with memory.driver.session(database=neo4j_database) as session:
            result = await session.run(cypher)
            records = await result.data()

            entities = []
            for record in records:
                node = record["e"]
                entities.append(dict(node))

            return entities


async def search_context(query: str, actor_id: str, top_k: int = 10) -> Dict[str, Any]:
    """Search the context graph for relevant information.

    Args:
        query: Search query text
        actor_id: User ID for multi-tenant isolation
        top_k: Number of results to return

    Returns:
        Dictionary with messages, entities, and preferences
    """
    from neo4j_agent_memory import MemoryClient, MemorySettings
    from neo4j_agent_memory.config.settings import Neo4jConfig, EmbeddingConfig, EmbeddingProvider

    neo4j_uri = os.environ["NEO4J_URI"]
    neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
    neo4j_password = get_neo4j_password()
    neo4j_database = os.environ.get("NEO4J_DATABASE", "neo4j")

    settings = MemorySettings(
        neo4j=Neo4jConfig(
            uri=neo4j_uri,
            user=neo4j_user,
            password=neo4j_password,
            database=neo4j_database
        ),
        embedding=EmbeddingConfig(
            provider=EmbeddingProvider.SENTENCE_TRANSFORMERS,
            model="all-MiniLM-L6-v2"
        )
    )

    async with MemoryClient(settings) as memory:
        # Get full context using neo4j-agent-memory
        context = await memory.get_context(
            query=query,
            limit=top_k
        )

        return {
            "query": query,
            "actor_id": actor_id,
            "context": context
        }


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler for querying the context graph.

    Expected event format:
    {
        "action": "query_entities" | "search_context",
        "entity_type": "Person" (optional, for query_entities),
        "actor_id": "user-123" (required for search_context),
        "query": "search text" (required for search_context),
        "limit": 10 (optional)
    }

    Args:
        event: Lambda event with query parameters
        context: Lambda context

    Returns:
        Response with query results
    """
    try:
        action = event.get("action", "query_entities")
        logger.info(f"Action: {action}, Event: {json.dumps(event)}")

        if action == "query_entities":
            entity_type = event.get("entity_type")
            actor_id = event.get("actor_id")
            limit = event.get("limit", 10)

            result = asyncio.run(query_entities(entity_type, actor_id, limit))

            return {
                "statusCode": 200,
                "body": json.dumps({
                    "action": "query_entities",
                    "entity_type": entity_type,
                    "actor_id": actor_id,
                    "entities": result
                })
            }

        elif action == "search_context":
            query = event.get("query")
            actor_id = event.get("actor_id")
            top_k = event.get("limit", 10)

            if not query or not actor_id:
                return {
                    "statusCode": 400,
                    "body": json.dumps({
                        "error": "query and actor_id are required for search_context"
                    })
                }

            result = asyncio.run(search_context(query, actor_id, top_k))

            return {
                "statusCode": 200,
                "body": json.dumps({
                    "action": "search_context",
                    "result": result
                })
            }

        else:
            return {
                "statusCode": 400,
                "body": json.dumps({
                    "error": f"Unknown action: {action}. Supported: query_entities, search_context"
                })
            }

    except Exception as e:
        logger.error(f"Error querying graph: {str(e)}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": str(e),
                "message": "Failed to query context graph"
            })
        }
