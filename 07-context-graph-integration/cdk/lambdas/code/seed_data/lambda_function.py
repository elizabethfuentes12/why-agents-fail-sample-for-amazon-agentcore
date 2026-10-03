"""Lambda function to seed Neo4j with sample context graph data.

This function uses neo4j-agent-memory to create:
- Sample Person, Organization, Location, Event entities (POLE+O model)
- Relationships between entities (WORKS_AT, ATTENDED, etc.)
- Sample conversation messages
- Sample decision traces

Environment Variables:
    NEO4J_URI: Bolt connection URI (e.g., bolt://nlb-dns:7687)
    NEO4J_PASSWORD_SECRET_ARN: Secrets Manager ARN for Neo4j password
    NEO4J_USER: Neo4j username (default: neo4j)
    NEO4J_DATABASE: Neo4j database name (default: neo4j)
"""

import asyncio
import json
import logging
import os
import boto3
from typing import Any, Dict

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


async def seed_sample_data():
    """Seed Neo4j with sample context graph data using neo4j-agent-memory."""
    from neo4j_agent_memory import MemoryClient, MemorySettings
    from neo4j_agent_memory.config.settings import Neo4jConfig, EmbeddingConfig, EmbeddingProvider

    # Get Neo4j credentials
    neo4j_uri = os.environ["NEO4J_URI"]
    neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
    neo4j_password = get_neo4j_password()
    neo4j_database = os.environ.get("NEO4J_DATABASE", "neo4j")

    logger.info(f"Connecting to Neo4j at {neo4j_uri}")

    # Configure memory client
    settings = MemorySettings(
        neo4j=Neo4jConfig(
            uri=neo4j_uri,
            user=neo4j_user,
            password=neo4j_password,
            database=neo4j_database
        ),
        embedding=EmbeddingConfig(
            provider=EmbeddingProvider.SENTENCE_TRANSFORMERS,
            model="all-MiniLM-L6-v2"  # Lightweight model for Lambda
        )
    )

    async with MemoryClient(settings) as memory:
        logger.info("Memory client initialized")

        # Sample user ID (for multi-tenant isolation)
        user_id = "demo-user-001"
        session_id = "demo-session-001"

        # Add sample conversation messages
        logger.info("Adding sample messages...")
        await memory.short_term.add_message(
            session_id=session_id,
            role="user",
            content="Hi, I met Sarah Chen from Acme Corp at AWS Summit. She's the VP of Engineering."
        )

        await memory.short_term.add_message(
            session_id=session_id,
            role="assistant",
            content="Thanks for letting me know! I've saved that Sarah Chen from Acme Corp is someone you met at AWS Summit."
        )

        await memory.short_term.add_message(
            session_id=session_id,
            role="user",
            content="She mentioned they're interested in our enterprise tier for their AI platform project."
        )

        # Add entities
        logger.info("Adding sample entities...")
        sarah = await memory.long_term.add_entity(
            name="Sarah Chen",
            entity_type="Person",
            properties={
                "role": "VP of Engineering",
                "email": "sarah.chen@acmecorp.com",
                "actor_id": user_id
            }
        )

        acme = await memory.long_term.add_entity(
            name="Acme Corp",
            entity_type="Organization",
            properties={
                "industry": "Technology",
                "actor_id": user_id
            }
        )

        summit = await memory.long_term.add_entity(
            name="AWS Summit 2026",
            entity_type="Event",
            properties={
                "date": "2026-05-10",
                "location": "San Francisco",
                "actor_id": user_id
            }
        )

        # Add relationships
        logger.info("Adding sample relationships...")
        await memory.long_term.add_relationship(
            source_entity_id=sarah.entity_id,
            target_entity_id=acme.entity_id,
            relationship_type="WORKS_AT"
        )

        await memory.long_term.add_relationship(
            source_entity_id=sarah.entity_id,
            target_entity_id=summit.entity_id,
            relationship_type="ATTENDED"
        )

        # Add preferences
        logger.info("Adding sample preferences...")
        await memory.long_term.add_preference(
            category="product_tier",
            preference="Interested in Enterprise Tier",
            metadata={"contact": "Sarah Chen", "company": "Acme Corp"}
        )

        # Add a reasoning trace
        logger.info("Adding sample reasoning trace...")
        await memory.reasoning.add_trace(
            task="Extract entities from conversation",
            steps=[
                {
                    "thought": "User mentioned meeting someone at an event",
                    "action": "extract_entity",
                    "observation": "Found person: Sarah Chen"
                },
                {
                    "thought": "Person has affiliation with organization",
                    "action": "extract_relationship",
                    "observation": "Created WORKS_AT relationship"
                }
            ],
            outcome="Successfully extracted 3 entities and 2 relationships"
        )

        logger.info("Sample data seeded successfully!")

        return {
            "entities_created": 3,
            "relationships_created": 2,
            "messages_added": 3,
            "user_id": user_id,
            "session_id": session_id
        }


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler for seeding sample data.

    Args:
        event: Lambda event (not used)
        context: Lambda context

    Returns:
        Response with status and details of seeded data
    """
    try:
        logger.info("Starting data seeding...")
        result = asyncio.run(seed_sample_data())

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Sample data seeded successfully",
                "details": result
            })
        }

    except Exception as e:
        logger.error(f"Error seeding data: {str(e)}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": str(e),
                "message": "Failed to seed sample data"
            })
        }
