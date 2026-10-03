#!/usr/bin/env python3
"""Test Titan V2 embeddings with correct format."""
import boto3
import json

client = boto3.client("bedrock-runtime", region_name="us-east-1")

model_id = "amazon.titan-embed-text-v2:0"

print(f"Trying: {model_id}")
try:
    # Correct Titan V2 format
    response = client.invoke_model(
        modelId=model_id,
        body=json.dumps({
            "inputText": "test embedding",
            "dimensions": 1536,
            "normalize": True
        })
    )
    result = json.loads(response['body'].read())
    embedding_length = len(result['embedding'])
    print(f"✅ SUCCESS: {model_id}")
    print(f"✅ Embedding dimensions: {embedding_length}")
except Exception as e:
    print(f"❌ FAILED: {str(e)}")

# Also try V1
model_id_v1 = "amazon.titan-embed-text-v1"
print(f"\nTrying: {model_id_v1}")
try:
    response = client.invoke_model(
        modelId=model_id_v1,
        body=json.dumps({"inputText": "test embedding"})
    )
    result = json.loads(response['body'].read())
    embedding_length = len(result['embedding'])
    print(f"✅ SUCCESS: {model_id_v1}")
    print(f"✅ Embedding dimensions: {embedding_length}")
except Exception as e:
    print(f"❌ FAILED: {str(e)}")
