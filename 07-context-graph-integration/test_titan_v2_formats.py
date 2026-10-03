#!/usr/bin/env python3
"""Test different Titan V2 request formats."""
import boto3
import json

client = boto3.client("bedrock-runtime", region_name="us-east-1")

model_id = "amazon.titan-embed-text-v2:0"

# Try different formats
formats = [
    {"inputText": "test"},
    {"inputText": "test", "dimensions": 1536},
    {"inputText": "test", "embeddingConfig": {"outputEmbeddingLength": 1536}},
    {"inputText": "test", "dimensions": 1536, "normalize": True},
]

for i, body in enumerate(formats):
    print(f"\nFormat {i+1}: {body}")
    try:
        response = client.invoke_model(
            modelId=model_id,
            body=json.dumps(body)
        )
        result = json.loads(response['body'].read())
        embedding_length = len(result['embedding'])
        print(f"✅ SUCCESS - Dimensions: {embedding_length}")
    except Exception as e:
        print(f"❌ FAILED: {str(e)[:150]}")
