# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Build the Neo4j knowledge graph from hotel FAQ documents (full dataset).

How this script works
---------------------
1. Clears any existing graph (MATCH (n) DETACH DELETE n).
2. Runs neo4j-graphrag's SimpleKGPipeline over each of the 300 FAQ documents.
   The pipeline: loads text -> chunks it -> embeds chunks (OpenAI
   text-embedding-3-small) -> an LLM (OpenAI gpt-4o-mini) extracts entities and
   relationships -> writes nodes/relationships to Neo4j.
3. No fixed schema is passed, so the graph is "unconstrained": the LLM
   auto-discovers labels, relationship types and property names from the text.
   That is why the summary queries below filter labels defensively (CONTAINS
   'Hotel') instead of assuming exact names.
4. perform_entity_resolution=True merges duplicate entities across documents.

This is the Graph-RAG side of the comparison; load_vector_data.py builds the
FAISS index for the RAG side from the SAME documents.

Neo4j best practice: sessions target an explicit database (NEO4J_DATABASE) and
every driver opened here is closed when its work is done.
"""
import os
import asyncio
import atexit
os.environ['OTEL_SDK_DISABLED'] = 'true'

from dotenv import load_dotenv
load_dotenv()

from neo4j import GraphDatabase
from neo4j_graphrag.experimental.pipeline.kg_builder import SimpleKGPipeline
from neo4j_graphrag.llm import OpenAILLM
from neo4j_graphrag.embeddings import OpenAIEmbeddings

NEO4J_URI = os.getenv("NEO4J_URI", "neo4j://127.0.0.1:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

# Single Neo4j driver reused across clear/build/summary (best practice:
# one driver per app, it owns a connection pool). Closed once at exit.
_driver = None


def _get_driver():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    return _driver


@atexit.register
def _close_driver():
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None


async def build_graph():
    # Clear existing graph
    print("Clearing existing graph...")
    driver = _get_driver()
    with driver.session(database=NEO4J_DATABASE) as session:
        session.run("MATCH (n) DETACH DELETE n")
    print("✅ Graph cleared\n")

    # LLM and embedder
    llm = OpenAILLM(
        model_name="gpt-4o-mini",
        model_params={"temperature": 0, "response_format": {"type": "json_object"}}
    )
    embedder = OpenAIEmbeddings(model="text-embedding-3-small")

    # No hardcoded schema - LLM discovers entities automatically
    # schema="EXTRACTED" (default): LLM analyzes text, generates schema, then extracts
    kg_builder = SimpleKGPipeline(
        llm=llm,
        driver=_get_driver(),
        embedder=embedder,
        from_pdf=False,
        perform_entity_resolution=True,
    )

    # Load all 300 FAQ documents (same as FAISS)
    data_dir = "data"
    files = sorted(os.listdir(data_dir))
    total = len(files)
    print(f"Processing {total} documents...\n")

    errors = 0
    for i, filename in enumerate(files, 1):
        filepath = os.path.join(data_dir, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            text = f.read()

        print(f"  [{i}/{total}] {filename}...", end=" ", flush=True)
        try:
            await asyncio.wait_for(kg_builder.run_async(text=text), timeout=90)
            print("✅")
        except asyncio.TimeoutError:
            errors += 1
            print("⏰ timeout")
        except Exception as e:
            errors += 1
            print(f"❌ {str(e)[:60]}")

    # Summary
    print(f"\n{'='*60}")
    print(f"GRAPH BUILD COMPLETE ({total - errors}/{total} docs processed)")
    print(f"{'='*60}")

    driver = _get_driver()
    with driver.session(database=NEO4J_DATABASE) as session:
        result = session.run("""
            MATCH (n) 
            WHERE NOT 'Chunk' IN labels(n) AND NOT 'Document' IN labels(n)
            RETURN DISTINCT [l IN labels(n) WHERE l <> '__Entity__'][0] as label, count(*) as count 
            ORDER BY count DESC
        """)
        print("\nEntity types (auto-discovered):")
        for r in result:
            print(f"  :{r['label']}: {r['count']}")

        result = session.run("""
            MATCH ()-[r]->() 
            WHERE NOT type(r) IN ['PART_OF_DOCUMENT', 'NEXT_CHUNK', 'PART_OF_CHUNK', 'FROM_DOCUMENT', 'FROM_CHUNK']
            RETURN DISTINCT type(r) as rel, count(*) as count 
            ORDER BY count DESC
        """)
        print("\nRelationship types (auto-discovered):")
        for r in result:
            print(f"  :{r['rel']}: {r['count']}")

        # Test queries
        print("\n--- Test: Hotels in Egypt ---")
        result = session.run("""
            MATCH (h)-[*1..3]->(co)
            WHERE any(l IN labels(h) WHERE l CONTAINS 'Hotel' OR l = 'Hotel')
            AND any(l IN labels(co) WHERE l CONTAINS 'Country' OR l = 'Country')
            AND co.name CONTAINS 'Egypt'
            RETURN h.name, co.name
            LIMIT 5
        """)
        for r in result:
            print(f"  {r['h.name']} -> {r['co.name']}")

        print("\n--- Test: Hotels in Paris ---")
        result = session.run("""
            MATCH (h)-[*1..2]->(c)
            WHERE any(l IN labels(h) WHERE l CONTAINS 'Hotel' OR l = 'Hotel')
            AND c.name CONTAINS 'Paris'
            RETURN h.name, c.name
            LIMIT 5
        """)
        for r in result:
            print(f"  {r['h.name']} -> {r['c.name']}")

    print("\n✅ Done!")


if __name__ == "__main__":
    asyncio.run(build_graph())
