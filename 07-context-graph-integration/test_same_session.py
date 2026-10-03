#!/usr/bin/env python3
"""Test searching in the SAME session to verify data was stored."""

import boto3
import json
import uuid

REGION = "us-east-1"
AGENT_ARN = "arn:aws:bedrock-agentcore:us-east-1:222634367169:runtime/context_aware_agent-fcx5I7614H"

client = boto3.client("bedrock-agentcore", region_name=REGION)

actor_id = "test-user-002"
session_id = f"session-{uuid.uuid4()}"

print("=" * 60)
print("Test: Store and retrieve in SAME session")
print("=" * 60)
print(f"Session ID: {session_id}")
print(f"Actor ID: {actor_id}")

# Store
print("\n📝 Storing information...")
payload_1 = json.dumps({
    "prompt": "Remember this: John Smith works at Microsoft as a Senior Engineer.",
    "actor_id": actor_id
})

response_1 = client.invoke_agent_runtime(
    agentRuntimeArn=AGENT_ARN,
    payload=payload_1,
    runtimeSessionId=session_id,
    runtimeUserId=actor_id
)

print(f"✅ Stored: {response_1['response'].read().decode('utf-8')[:200]}")

# Search in SAME session
print("\n\n🔍 Searching in SAME session...")
payload_2 = json.dumps({
    "prompt": "What do you know about John Smith?",
    "actor_id": actor_id
})

response_2 = client.invoke_agent_runtime(
    agentRuntimeArn=AGENT_ARN,
    payload=payload_2,
    runtimeSessionId=session_id,  # SAME session
    runtimeUserId=actor_id
)

print(f"✅ Retrieved: {response_2['response'].read().decode('utf-8')}")
print("\n" + "=" * 60)
