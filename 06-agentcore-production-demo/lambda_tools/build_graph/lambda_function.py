"""Lambda: build_graph — builds knowledge graph in Neo4j AuraDB from S3 documents.

Triggered as a CDK Custom Resource after BucketDeployment completes.
Uses SimpleKGPipeline from neo4j-graphrag to auto-discover schema.

Based on the proven approach from 01-faq-graphrag-demo/build_graph_lite.py.
"""

import asyncio
import json
import os

import boto3
from neo4j import GraphDatabase
from neo4j_graphrag.embeddings import OpenAIEmbeddings
from neo4j_graphrag.experimental.pipeline.kg_builder import SimpleKGPipeline
from neo4j_graphrag.llm import OpenAILLM

s3 = boto3.client("s3")
secrets = boto3.client("secretsmanager")

DOCS_S3_BUCKET = os.environ["DOCS_S3_BUCKET"]
DOCS_S3_PREFIX = os.environ.get("DOCS_S3_PREFIX", "hotel-faqs/")
MAX_DOCS = int(os.environ.get("MAX_DOCS", "30"))
SKIP_DOCS = int(os.environ.get("SKIP_DOCS", "0"))
SKIP_CLEAR = os.environ.get("SKIP_CLEAR", "false") == "true"
NEO4J_URI_SECRET_ARN = os.environ["NEO4J_URI_SECRET_ARN"]
NEO4J_USER_SECRET_ARN = os.environ["NEO4J_USER_SECRET_ARN"]
NEO4J_PASSWORD_SECRET_ARN = os.environ["NEO4J_PASSWORD_SECRET_ARN"]
OPENAI_API_KEY_SECRET_ARN = os.environ["OPENAI_API_KEY_SECRET_ARN"]


def _get_secret(arn):
    return secrets.get_secret_value(SecretId=arn)["SecretString"]


def _download_documents():
    all_keys = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=DOCS_S3_BUCKET, Prefix=DOCS_S3_PREFIX):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith((".txt", ".md", ".json")):
                all_keys.append(key)

    # Sort for consistent ordering across batches, then apply skip/limit
    all_keys.sort()
    selected = all_keys[SKIP_DOCS:SKIP_DOCS + MAX_DOCS]

    docs = []
    for key in selected:
        response = s3.get_object(Bucket=DOCS_S3_BUCKET, Key=key)
        text = response["Body"].read().decode("utf-8")
        docs.append(text)
    return docs


async def _build_graph(docs, driver, llm, embedder):
    pipeline = SimpleKGPipeline(
        llm=llm,
        driver=driver,
        embedder=embedder,
        from_pdf=False,
        perform_entity_resolution=True,
    )

    total = len(docs)
    errors = 0
    for i, doc in enumerate(docs, 1):
        print(f"  [{i}/{total}] Processing...", end=" ", flush=True)
        try:
            await asyncio.wait_for(pipeline.run_async(text=doc), timeout=90)
            print("OK")
        except asyncio.TimeoutError:
            errors += 1
            print("TIMEOUT")
        except Exception as e:
            errors += 1
            print(f"ERROR: {str(e)[:80]}")

    return total, errors


def handler(event, context):
    """Handle CDK Custom Resource or direct invocation."""
    request_type = event.get("RequestType", "Create")

    # CDK Custom Resource: only build on Create/Update, skip Delete
    if request_type == "Delete":
        return {"Status": "SUCCESS", "PhysicalResourceId": "graph-build"}

    neo4j_uri = _get_secret(NEO4J_URI_SECRET_ARN)
    neo4j_user = _get_secret(NEO4J_USER_SECRET_ARN)
    neo4j_password = _get_secret(NEO4J_PASSWORD_SECRET_ARN)
    openai_api_key = _get_secret(OPENAI_API_KEY_SECRET_ARN)

    os.environ["OPENAI_API_KEY"] = openai_api_key

    print(f"Connecting to Neo4j at {neo4j_uri}...")
    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))

    print(f"Downloading documents from s3://{DOCS_S3_BUCKET}/{DOCS_S3_PREFIX} (max {MAX_DOCS})...")
    docs = _download_documents()

    if not docs:
        print("No documents found.")
        driver.close()
        return {"Status": "SUCCESS", "PhysicalResourceId": "graph-build", "Data": {"DocsProcessed": 0}}

    print(f"Found {len(docs)} documents (skip={SKIP_DOCS}, max={MAX_DOCS})...")
    if not SKIP_CLEAR:
        print("  Clearing existing graph...")
        with driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")

    llm = OpenAILLM(
        model_name="gpt-4o-mini",
        api_key=openai_api_key,
        model_params={"temperature": 0, "response_format": {"type": "json_object"}},
    )
    embedder = OpenAIEmbeddings(model="text-embedding-3-small")

    total, errors = asyncio.run(_build_graph(docs, driver, llm, embedder))

    # Log discovered schema
    with driver.session() as session:
        labels = session.run(
            "MATCH (n) WHERE NOT 'Chunk' IN labels(n) AND NOT 'Document' IN labels(n) "
            "RETURN DISTINCT [l IN labels(n) WHERE l <> '__Entity__'][0] AS label, "
            "count(*) AS count ORDER BY count DESC"
        ).data()
        print(f"\nDiscovered schema: {json.dumps(labels)}")

    driver.close()
    result = f"Graph built: {total - errors}/{total} documents processed, {errors} errors"
    print(result)

    return {"Status": "SUCCESS", "PhysicalResourceId": "graph-build", "Data": {"Result": result}}
