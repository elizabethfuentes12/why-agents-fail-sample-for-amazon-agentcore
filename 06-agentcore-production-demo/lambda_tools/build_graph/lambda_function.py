"""Lambda: build_graph — builds knowledge graph in Neo4j AuraDB from S3 documents.

Triggered as a CDK Custom Resource after BucketDeployment completes.
Uses SimpleKGPipeline from neo4j-graphrag to auto-discover schema.

Based on the proven approach from 01-faq-graphrag-demo/build_graph.py.
Uses Amazon Bedrock (Claude Sonnet 4 for extraction, Nova 2 for embeddings).
"""

import asyncio
import json
import os

import boto3
from neo4j import GraphDatabase
from neo4j_graphrag.embeddings.base import Embedder
from neo4j_graphrag.experimental.pipeline.kg_builder import SimpleKGPipeline
from neo4j_graphrag.llm.base import LLMInterface, LLMResponse

s3 = boto3.client("s3")
secrets = boto3.client("secretsmanager")

DOCS_S3_BUCKET = os.environ["DOCS_S3_BUCKET"]
DOCS_S3_PREFIX = os.environ.get("DOCS_S3_PREFIX", "hotel-faqs/")
MAX_DOCS = int(os.environ.get("MAX_DOCS", "30"))
SKIP_DOCS = int(os.environ.get("SKIP_DOCS", "0"))
SKIP_CLEAR = os.environ.get("SKIP_CLEAR", "false") == "true"
AWS_REGION = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
NEO4J_URI_SECRET_ARN = os.environ["NEO4J_URI_SECRET_ARN"]
NEO4J_USER_SECRET_ARN = os.environ["NEO4J_USER_SECRET_ARN"]
NEO4J_PASSWORD_SECRET_ARN = os.environ["NEO4J_PASSWORD_SECRET_ARN"]


# --- Amazon Bedrock wrappers that neo4j-graphrag's pipeline requires ---

class BedrockLLM(LLMInterface):
    """Claude Sonnet 4 via the Bedrock Converse API (entity extraction)."""

    def __init__(self, model_id="global.anthropic.claude-sonnet-4-6", region=AWS_REGION):
        self.model_id = model_id
        self.client = boto3.client("bedrock-runtime", region_name=region)

    def _converse(self, text, system_instruction=None):
        kwargs = {
            "modelId": self.model_id,
            "messages": [{"role": "user", "content": [{"text": text}]}],
            "inferenceConfig": {"temperature": 0, "maxTokens": 4096},
        }
        if system_instruction:
            kwargs["system"] = [{"text": system_instruction}]
        resp = self.client.converse(**kwargs)
        return LLMResponse(content=resp["output"]["message"]["content"][0]["text"])

    def invoke(self, input, message_history=None, system_instruction=None):
        return self._converse(input, system_instruction)

    async def ainvoke(self, input, message_history=None, system_instruction=None):
        return await asyncio.to_thread(self._converse, input, system_instruction)


class BedrockEmbeddings(Embedder):
    """Amazon Nova 2 Multimodal Embeddings (1024-dim) for chunk vectors."""

    def __init__(self, model_id="amazon.nova-2-multimodal-embeddings-v1:0", region=AWS_REGION):
        self.model_id = model_id
        self.client = boto3.client("bedrock-runtime", region_name=region)

    def embed_query(self, text):
        resp = self.client.invoke_model(
            modelId=self.model_id,
            body=json.dumps({"taskType": "SINGLE_EMBEDDING", "singleEmbeddingParams": {
                "embeddingPurpose": "GENERIC_INDEX", "embeddingDimension": 1024,
                "text": {"truncationMode": "END", "value": text[:8000]}}}),
            contentType="application/json", accept="application/json",
        )
        return json.loads(resp["body"].read())["embeddings"][0]["embedding"]


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

    llm = BedrockLLM()
    embedder = BedrockEmbeddings()

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
