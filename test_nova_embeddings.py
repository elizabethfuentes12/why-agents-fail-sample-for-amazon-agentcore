#!/usr/bin/env python3
"""Test Nova embeddings directly."""
import boto3
import json

client = boto3.client("bedrock-runtime", region_name="us-east-1")

model_ids_to_try = [
    "amazon.nova-embed-text-v1:0",
    "us.amazon.nova-embed-text-v1:0",
    "amazon.nova-embed-text-v1",
]

for model_id in model_ids_to_try:
    print(f"\nTrying: {model_id}")
    try:
        response = client.invoke_model(
            modelId=model_id,
            body=json.dumps({"inputText": "test"})
        )
        print(f"✅ SUCCESS: {model_id}")
        break
    except Exception as e:
        print(f"❌ FAILED: {str(e)[:100]}")
