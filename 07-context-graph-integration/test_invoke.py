#!/usr/bin/env python3
"""Test AgentCore Runtime using SDK."""

from bedrock_agentcore_starter_toolkit import Runtime
import json
import uuid

print("=" * 60)
print("Testing AgentCore Context-Aware Agent")
print("=" * 60)

# Initialize Runtime (reads from .bedrock_agentcore.yaml)
runtime = Runtime()

# Check status
print("\n📊 Agent Status:")
print("-" * 60)
try:
    status = runtime.status()
    print(json.dumps(status, indent=2, default=str))
except Exception as e:
    print(f"❌ Error getting status: {e}")

# Test 1: Entity Extraction
print("\n\nTest 1: Entity Extraction")
print("-" * 60)

session_id = f"test-{uuid.uuid4()}"
actor_id = "test-user-001"

print(f"Session ID: {session_id}")
print(f"Actor ID: {actor_id}")

try:
    result = runtime.invoke(
        payload={
            "prompt": "I just met Sarah Chen from Acme Corporation. She's the VP of Engineering and we discussed their new AI platform project.",
            "actor_id": actor_id  # Required by neo4j-agent-memory
        },
        session_id=session_id  # Passed as HTTP header by SDK
    )

    print("\n✅ Response received:")
    print(json.dumps(result, indent=2, default=str))

except Exception as e:
    print(f"\n❌ Error: {e}")
    print(f"Type: {type(e)}")
    import traceback
    traceback.print_exc()

# Test 2: Context Recall (same session)
print("\n\nTest 2: Context Recall")
print("-" * 60)

try:
    result = runtime.invoke(
        payload={
            "prompt": "What do you know about Sarah?",
            "actor_id": actor_id
        },
        session_id=session_id  # Same session
    )

    print("\n✅ Response received:")
    print(json.dumps(result, indent=2, default=str))

except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
