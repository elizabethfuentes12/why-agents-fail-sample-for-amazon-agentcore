#!/usr/bin/env python3
"""Test AgentCore Runtime using boto3 directly."""

import boto3
import json
import uuid
import base64

print("=" * 60)
print("Testing AgentCore Context-Aware Agent")
print("=" * 60)

# Configuration
REGION = "us-east-1"
AGENT_ARN = "arn:aws:bedrock-agentcore:us-east-1:222634367169:runtime/context_aware_agent-fcx5I7614H"

# Initialize AWS client
client = boto3.client("bedrock-agentcore", region_name=REGION)

# Test 1: Entity Extraction
print("\nTest 1: Entity Extraction")
print("-" * 60)

session_id = f"test-{uuid.uuid4()}"
actor_id = "test-user-001"

print(f"Session ID: {session_id}")
print(f"Actor ID: {actor_id}")

try:
    payload = {
        "prompt": "I just met Sarah Chen from Acme Corporation. She's the VP of Engineering and we discussed their new AI platform project.",
        "actor_id": actor_id
    }

    # Send payload as JSON string (not base64)
    payload_str = json.dumps(payload)

    response = client.invoke_agent_runtime(
        agentRuntimeArn=AGENT_ARN,
        payload=payload_str,
        runtimeSessionId=session_id,
        runtimeUserId=actor_id
    )

    print("\n✅ Response received (HTTP {})".format(response['statusCode']))

    # Read streaming body
    if 'response' in response:
        response_body = response['response'].read().decode('utf-8')
        print("\nAgent Response:")
        print("-" * 60)
        print(response_body)
        print("-" * 60)

except Exception as e:
    print(f"\n❌ Error: {e}")
    print(f"Type: {type(e)}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
