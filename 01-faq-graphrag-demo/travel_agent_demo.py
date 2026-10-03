# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Travel Agent Demo: Traditional RAG vs Graph-RAG Comparison.

How this script works
----------------------
It builds TWO agents over the SAME 300 hotel-FAQ dataset and asks each the same
questions, so you can compare how they fail:

1. ``rag_agent`` — Traditional RAG. The ``search_faqs`` tool embeds the question
   with a local SentenceTransformer model, does a FAISS similarity search, and
   returns the top-3 closest documents. The LLM then answers from those chunks,
   so aggregations and counts are guessed and out-of-domain questions can be
   fabricated.
2. ``graph_agent`` — Graph-RAG. The ``query_knowledge_graph`` tool lets the LLM
   write Cypher (Text2Cypher) and run it against a Neo4j knowledge graph that was
   built from the same documents by ``build_graph.py``. Aggregations (AVG, COUNT)
   and multi-hop traversals run in the database, and missing data returns an
   honest empty result instead of a fabrication.

Model: OpenAI gpt-4o-mini (this repo's default). Embeddings: SentenceTransformer
(local, no API cost). Both agents use ``context_manager="auto"`` so Strands
truncates tool results and summarizes history as the window fills.

Neo4j best practices applied: a single driver is created once and reused across
all tool calls (the driver owns a connection pool), sessions target an explicit
database, and the driver is closed once at process exit.
"""
import atexit
import os
os.environ['OTEL_SDK_DISABLED'] = 'true'

from dotenv import load_dotenv
load_dotenv()

from strands import Agent, tool
from strands.models.openai import OpenAIModel
from neo4j import GraphDatabase
import faiss
import json
from sentence_transformers import SentenceTransformer

NEO4J_URI = os.getenv("NEO4J_URI", "neo4j://127.0.0.1:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

# Local embedding model for Traditional RAG (no API cost).
model = SentenceTransformer('all-MiniLM-L6-v2')
index = faiss.read_index("faqs_vector.index")
with open("faqs_docs.json", "r", encoding="utf-8") as f:
    documents = json.load(f)

# One Neo4j driver for the whole script. The driver manages a pooled set of
# connections, so creating a new one per query would be wasteful and slow.
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


@atexit.register
def _close_driver():
    """Close the shared Neo4j driver once when the process exits."""
    driver.close()


@tool
def search_faqs(query: str) -> str:
    """Search hotel FAQs using vector similarity (Traditional RAG).

    Embeds the query with SentenceTransformer, runs a FAISS top-3 similarity
    search, and returns the matching document snippets for the LLM to summarize.
    """
    query_embedding = model.encode([query])
    distances, indices = index.search(query_embedding.astype('float32'), 3)

    results = []
    for idx in indices[0]:
        doc = documents[idx]
        results.append(f"[{doc['filename']}]\n{doc['text'][:500]}...")

    return "\n\n".join(results)


@tool
def query_knowledge_graph(cypher_query: str) -> str:
    """Execute a Cypher query against the hotel knowledge graph (Graph-RAG).

    Cypher is Neo4j's pattern-matching query language — think SQL for graphs.
    Example: MATCH (h:Hotel)-[:HAS_ROOM]->(r:Room) WHERE h.name = 'Marriott' RETURN r

    The graph is built by neo4j-graphrag's SimpleKGPipeline WITHOUT a fixed
    schema, so the LLM auto-discovers labels, relationship types and property
    names from the documents. The names below are what the pipeline typically
    produces for this dataset — a guide, not a guaranteed contract. If a query
    returns nothing, inspect the real schema first:
        MATCH (n) RETURN DISTINCT labels(n) LIMIT 25

    Typical node labels: Hotel, Room, Amenity, Policy, Service
    Typical Hotel properties: name, address, guestRating, totalRooms, email, phone
    Typical relationships:
    - (Hotel)-[:HAS_ROOM]->(Room)
    - (Hotel)-[:OFFERS_AMENITY]->(Amenity)
    - (Hotel)-[:HAS_POLICY]->(Policy)
    - (Hotel)-[:PROVIDES_SERVICE]->(Service)

    Location lives in Hotel.address, e.g. WHERE h.address CONTAINS 'Cairo'.
    Property names are typically camelCase (guestRating, totalRooms).
    """
    # Reuse the shared driver; target an explicit database.
    with driver.session(database=NEO4J_DATABASE) as session:
        try:
            records = list(session.run(cypher_query))
            if not records:
                return "No results found."
            output = f"Found {len(records)} results:\n"
            for record in records[:15]:
                output += f"  {dict(record.items())}\n"
            return output
        except Exception as e:
            return f"Query error: {str(e)}"


MODEL = OpenAIModel(model_id="gpt-4o-mini")

# Traditional RAG Agent — only sees the top-3 vector matches.
rag_agent = Agent(
    name="RAG_Agent",
    system_prompt="You are a travel assistant. Answer in 2 sentences or fewer — be concise and factual.",
    tools=[search_faqs],
    model=MODEL,
    context_manager="auto",
)

# Graph-RAG Agent — writes Cypher and queries the whole graph.
graph_agent = Agent(
    name="GraphRAG_Agent",
    system_prompt="You are a travel assistant. Answer in 2 sentences or fewer — be concise and factual.",
    tools=[query_knowledge_graph],
    model=MODEL,
    context_manager="auto",
)

print("="*70)
print("TRAVEL AGENT COMPARISON: Traditional RAG vs Graph-RAG")
print("="*70)

queries = [
    # Test 1: Aggregation - RAG sees only top-3 docs, Graph-RAG AVG() over all 5
    "What is the average guest rating across all hotels in Las Vegas?",
    # Test 2: Precise counting - RAG cannot count across 297 docs, Graph-RAG COUNT()
    "How many hotels have an outdoor swimming pool?",
    # Test 3: Multi-hop reasoning - RAG mixes data, Graph-RAG traverses Hotel->Room
    "What room types does AnyCompany Las Vegas Strip offer?",
    # Test 4: Out-of-domain - RAG may hallucinate, Graph-RAG returns no data
    "Tell me about hotels in Antarctica",
]

for query in queries:
    print(f"\n{'='*70}")
    print(f"👤 Query: {query}")
    print("="*70)

    # Traditional RAG
    print("\n[TRADITIONAL RAG - Vector Search]")
    print("-" * 70)
    response = rag_agent(query)
    print(response.message['content'][0]['text'][:300] + "...")

    # Graph-RAG
    print("\n[GRAPH-RAG - Knowledge Graph]")
    print("-" * 70)
    response = graph_agent(query)
    print(response.message['content'][0]['text'][:300] + "...")

print("\n" + "="*70)
print("KEY INSIGHTS")
print("="*70)
print("""
Traditional RAG: Semantic similarity, may miss context or hallucinate
Graph-RAG: Structured queries on extracted entities, precise answers
Result: Graph-RAG eliminates hallucinations with verified data
""")
