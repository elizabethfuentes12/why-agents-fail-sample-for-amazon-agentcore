#!/usr/bin/env python3
"""Recreate Neo4j vector indexes with 1024 dimensions for Titan V2."""
import os
import boto3
from neo4j import GraphDatabase

def get_neo4j_password():
    secret_arn = "arn:aws:secretsmanager:us-east-1:222634367169:secret:Neo4jClusterNeo4jPassword11-rZ7E9b6Qzn4e-8rlJSL"
    client = boto3.client("secretsmanager", region_name="us-east-1")
    response = client.get_secret_value(SecretId=secret_arn)
    return response["SecretString"]

neo4j_uri = "bolt://Neo4jC-Neo4j-jpx69Q6y2FrK-72ad195e05314735.elb.us-east-1.amazonaws.com:7687"
password = get_neo4j_password()

driver = GraphDatabase.driver(neo4j_uri, auth=("neo4j", password))

with driver.session(database="neo4j") as session:
    print("Dropping old indexes...")
    
    # Drop old indexes
    try:
        session.run("DROP INDEX message_embedding IF EXISTS")
        print("✅ Dropped message_embedding index")
    except Exception as e:
        print(f"⚠️  Could not drop message_embedding: {e}")
    
    try:
        session.run("DROP INDEX entity_embedding IF EXISTS")
        print("✅ Dropped entity_embedding index")
    except Exception as e:
        print(f"⚠️  Could not drop entity_embedding: {e}")
    
    print("\nCreating new indexes with 1024 dimensions...")
    
    # Create new message embedding index (1024 dims for Titan V2)
    session.run("""
        CREATE VECTOR INDEX message_embedding IF NOT EXISTS
        FOR (m:Message)
        ON m.embedding
        OPTIONS {indexConfig: {
            `vector.dimensions`: 1024,
            `vector.similarity_function`: 'cosine'
        }}
    """)
    print("✅ Created message_embedding index (1024 dimensions)")
    
    # Create new entity embedding index (1024 dims for Titan V2)
    session.run("""
        CREATE VECTOR INDEX entity_embedding IF NOT EXISTS
        FOR (e:Entity)
        ON e.embedding
        OPTIONS {indexConfig: {
            `vector.dimensions`: 1024,
            `vector.similarity_function`: 'cosine'
        }}
    """)
    print("✅ Created entity_embedding index (1024 dimensions)")
    
    print("\nIndexes recreated successfully!")

driver.close()
