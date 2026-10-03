# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Build the LITE Neo4j knowledge graph from hotel FAQ documents.

How this script works
---------------------
Same SimpleKGPipeline flow as build_graph.py (load -> chunk -> embed -> LLM
entity/relationship extraction -> write to Neo4j), but only the first 30
documents (10% of the dataset) so a full build takes ~10-15 min instead of
~2 hours. No fixed schema is passed, so the LLM auto-discovers labels,
relationship types and property names from the text. Pair this with
load_vector_data_lite.py for a fair RAG-vs-Graph-RAG comparison on the same
30 documents.

Neo4j best practice: sessions target an explicit database (NEO4J_DATABASE).
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

# Single Neo4j driver reused across clear/build/summary, closed once at exit.
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

# LITE: Process only first 30 documents
MAX_DOCS = 30


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

    # No hardcoded schema - the LLM automatically discovers entities from the text,
    # eliminating the need to manually define entity types in advance
    kg_builder = SimpleKGPipeline(
        llm=llm,
        driver=_get_driver(),
        embedder=embedder,
        from_pdf=False,
        perform_entity_resolution=True,
    )

    # Load LITE subset of FAQ documents
    data_dir = "data"
    files = sorted(os.listdir(data_dir))[:MAX_DOCS]  # Only first 30
    total = len(files)
    print(f"🚀 LITE MODE: Processing {total} documents (10% of full dataset)...\n")

    errors = 0
    for i, filename in enumerate(files, 1):
        filepath = os.path.join(data_dir, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            text = f.read()
        
        try:
            print(f"[{i}/{total}] Processing {filename}...")
            await kg_builder.run_async(text=text)
        except Exception as e:
            print(f"  ❌ Error: {e}")
            errors += 1
    
    # Note: do not close kg_builder here — it shares the single driver,
    # which is closed once at process exit via _close_driver().

    print(f"\n{'='*60}")
    print(f"LITE GRAPH BUILD COMPLETE ({total - errors}/{total} docs processed)")
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
              AND co.id =~ '(?i).*egypt.*'
            RETURN h.id as hotel, co.id as country
            LIMIT 5
        """)
        for r in result:
            print(f"  {r['hotel']} -> {r['country']}")

    print("\n✅ LITE graph ready for queries!")


if __name__ == "__main__":
    asyncio.run(build_graph())
