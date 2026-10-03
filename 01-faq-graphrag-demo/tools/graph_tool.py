# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Neo4j query tools for the hotel knowledge graph.

Used by:
- 01-graphrag-demo: direct Graph-RAG comparison
- 02-semantic-tools-demo: real hotel data for semantic filtering accuracy

Neo4j best practices applied here:
- A single, module-level driver is created once and reused across calls
  (the driver manages a connection pool; creating one per query is wasteful).
- Queries use parameters ($name) instead of string interpolation, which
  prevents Cypher injection and lets Neo4j cache the query plan.
- Sessions target an explicit database via NEO4J_DATABASE.
- The driver is closed once at process exit, not after every query.
"""

import atexit
import os

from neo4j import GraphDatabase

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

# Single driver reused across all calls (best practice: one driver per app).
_driver = None


def _get_driver():
    """Return the shared Neo4j driver, creating it once on first use."""
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    return _driver


@atexit.register
def _close_driver():
    """Close the shared driver once when the process exits."""
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None


def query_hotel_knowledge_graph(cypher_query: str) -> str:
    """Execute a Cypher query against the hotel knowledge graph.

    The graph is built by neo4j-graphrag's SimpleKGPipeline WITHOUT a fixed
    schema, so the LLM auto-discovers labels, relationship types, and property
    names from the source documents. The names below are the ones the pipeline
    typically produces for this dataset — treat them as a guide, not a contract.
    If a query returns nothing, inspect the actual schema first with:
        MATCH (n) RETURN DISTINCT labels(n) LIMIT 25
        CALL db.relationshipTypes()

    Typical node labels: Hotel, Room, Amenity, Policy, Service
    Typical Hotel properties: name, address, guestRating, totalRooms, email, phone
    Typical Room properties: type, bed_configuration, max_occupancy, min_rate, max_rate
    Typical Amenity properties: name, description, fee

    Typical relationships: (Hotel)-[:HAS_ROOM]->(Room), (Hotel)-[:OFFERS_AMENITY]->(Amenity),
                           (Hotel)-[:HAS_POLICY]->(Policy), (Hotel)-[:PROVIDES_SERVICE]->(Service)

    Location lives in the Hotel.address property, e.g. WHERE h.address CONTAINS 'Cairo'.
    Property names are typically camelCase (guestRating, totalRooms).
    """
    driver = _get_driver()
    try:
        with driver.session(database=NEO4J_DATABASE) as session:
            records = list(session.run(cypher_query))
            if not records:
                return "No results found."
            output = f"Found {len(records)} results:\n"
            for record in records[:15]:
                output += f"  {dict(record.items())}\n"
            return output
    except Exception as e:
        return f"Query error: {str(e)}"


# Keep old helpers for backward compatibility but marked as deprecated.
def search_hotels_by_country(country: str, min_rating: float = 0.0) -> str:
    """[DEPRECATED] Use query_hotel_knowledge_graph instead.

    Search hotels in a specific country with a minimum rating from Neo4j."""
    driver = _get_driver()
    cypher = """
    MATCH (h:Hotel)
    WHERE (h.address CONTAINS $country OR h.name CONTAINS $country)
      AND coalesce(h.guestRating, 0) >= $min_rating
    RETURN h.name AS name, h.address AS address,
           h.guestRating AS rating, h.totalRooms AS rooms
    ORDER BY h.guestRating DESC
    LIMIT 10
    """
    try:
        with driver.session(database=NEO4J_DATABASE) as session:
            records = list(session.run(cypher, country=country, min_rating=min_rating))
            if not records:
                return "No results found."
            return "\n".join(f"  {dict(r.items())}" for r in records)
    except Exception as e:
        return f"Query error: {str(e)}"


def get_top_rated_hotels(limit: int = 5) -> str:
    """[DEPRECATED] Use query_hotel_knowledge_graph instead.

    Get top-rated hotels from the Neo4j knowledge graph."""
    driver = _get_driver()
    cypher = """
    MATCH (h:Hotel)
    WHERE h.guestRating IS NOT NULL
    RETURN h.name AS name, h.address AS address,
           h.guestRating AS rating, h.totalRooms AS rooms
    ORDER BY h.guestRating DESC
    LIMIT $limit
    """
    try:
        with driver.session(database=NEO4J_DATABASE) as session:
            # LIMIT needs an integer parameter
            records = list(session.run(cypher, limit=int(limit)))
            if not records:
                return "No results found."
            return "\n".join(f"  {dict(r.items())}" for r in records)
    except Exception as e:
        return f"Query error: {str(e)}"
