# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Lambda: query_knowledge_graph — executes Cypher queries against Neo4j.

Two supported setups:

  * Neo4j AuraDB (managed): set NEO4J_URI to the full Aura connection URI
    (neo4j+s://xxxx.databases.neo4j.io). Aura is a public TLS endpoint, so this
    Lambda must run OUTSIDE a VPC (no VpcConfig).
  * Self-hosted Neo4j on EC2: set NEO4J_HOST to the instance private IP. The
    Lambda then runs in the same VPC/Security Group and connects over bolt://
    on port 7687.

Environment variables:
  NEO4J_URI: Full connection URI (preferred; required for AuraDB)
  NEO4J_HOST: Host/private IP — used only when NEO4J_URI is not set
  NEO4J_PASSWORD_SECRET_ARN: Secrets Manager ARN for the Neo4j password
  NEO4J_USER: Neo4j username (defaults to "neo4j")
"""

import json
import os

import boto3
from neo4j import GraphDatabase

secrets = boto3.client("secretsmanager")

NEO4J_URI = os.environ.get("NEO4J_URI", "")
NEO4J_HOST = os.environ.get("NEO4J_HOST", "")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD_SECRET_ARN = os.environ["NEO4J_PASSWORD_SECRET_ARN"]

_driver = None


def _resolve_uri():
    """Prefer the explicit URI (AuraDB); fall back to bolt:// for EC2 hosts."""
    if NEO4J_URI:
        return NEO4J_URI
    if not NEO4J_HOST:
        raise RuntimeError("Set NEO4J_URI (AuraDB) or NEO4J_HOST (self-hosted Neo4j).")
    # A bare Aura hostname would need TLS, so route it to neo4j+s:// as well.
    if NEO4J_HOST.endswith(".databases.neo4j.io"):
        return f"neo4j+s://{NEO4J_HOST}"
    return f"bolt://{NEO4J_HOST}:7687"


def _get_driver():
    global _driver
    if _driver is None:
        secret_string = secrets.get_secret_value(SecretId=NEO4J_PASSWORD_SECRET_ARN)["SecretString"]
        # The secret is either a JSON document with a "password" field or the
        # password itself in plain text. Both are accepted.
        try:
            password = json.loads(secret_string).get("password", secret_string)
        except (json.JSONDecodeError, AttributeError):
            password = secret_string
        _driver = GraphDatabase.driver(_resolve_uri(), auth=(NEO4J_USER, password))
    return _driver


def handler(event, context):
    body = json.loads(event.get("body", "{}")) if isinstance(event.get("body"), str) else event
    cypher_query = body.get("cypher_query", "")

    if not cypher_query:
        return {"statusCode": 400, "body": "ERROR: cypher_query is required."}

    try:
        driver = _get_driver()
        with driver.session() as session:
            result = session.run(cypher_query)
            records = [dict(record) for record in result][:15]

        if not records:
            return {"statusCode": 200, "body": "No results found."}

        formatted = json.dumps(records, indent=2, default=str)
        return {"statusCode": 200, "body": f"Query returned {len(records)} result(s):\n{formatted}"}

    except Exception as e:
        return {"statusCode": 200, "body": f"Query error: {str(e)}"}
