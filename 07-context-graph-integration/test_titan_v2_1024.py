#!/usr/bin/env python3
"""Test Titan V2 with dimensions parameter."""
import boto3
import json

client = boto3.client("bedrock-runtime", region_name="us-east-1")

# Test without dimensions (should default to 1024)
print("Test 1: No dimensions parameter")
response1 = client.invoke_model(
    modelId="amazon.titan-embed-text-v2:0",
    body=json.dumps({
        "inputText": "test",
        "normalize": True
    })
)
result1 = json.loads(response1['body'].read())
print(f"✅ Dimensions: {len(result1['embedding'])}")

# Test with explicit dimensions=1024
print("\nTest 2: dimensions=1024")
try:
    response2 = client.invoke_model(
        modelId="amazon.titan-embed-text-v2:0",
        body=json.dumps({
            "inputText": "test",
            "dimensions": 1024,
            "normalize": True
        })
    )
    result2 = json.loads(response2['body'].read())
    print(f"✅ Dimensions: {len(result2['embedding'])}")
except Exception as e:
    print(f"❌ Error: {e}")
