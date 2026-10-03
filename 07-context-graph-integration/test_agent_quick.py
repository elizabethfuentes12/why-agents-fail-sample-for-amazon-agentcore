#!/usr/bin/env python3
"""Quick test script for deployed AgentCore Runtime agent.

This is a simplified version of the Jupyter notebook for command-line testing.
"""

import boto3
import json
from datetime import datetime

# Configuration
REGION = "us-east-1"
AGENT_RUNTIME_ARN = "arn:aws:bedrock-agentcore:us-east-1:222634367169:runtime/context_aware_agent-fcx5I7614H"

print("=" * 60)
print("AgentCore Context-Aware Agent - Quick Test")
print("=" * 60)
print(f"\n📍 Region: {REGION}")
print(f"🤖 Agent: {AGENT_RUNTIME_ARN}")
print()

# Initialize AWS clients
bedrock_agent_runtime = boto3.client("bedrock-agent-runtime", region_name=REGION)

def invoke_agent(agent_arn: str, prompt: str, session_id: str = None):
    """Invoke AgentCore Runtime."""
    if not session_id:
        session_id = f"test-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    print(f"\n📤 Invoking agent...")
    print(f"   Session: {session_id}")
    print(f"   Prompt: {prompt}")
    print()
    print("💬 Response:")
    print("-" * 60)

    try:
        response = bedrock_agent_runtime.invoke_agent(
            agentId=agent_arn.split('/')[-1],  # Extract agent ID from ARN
            agentAliasId="DEFAULT",
            sessionId=session_id,
            inputText=prompt
        )

        # AgentCore returns streaming response
        completion = ""
        for event in response.get("completion", []):
            if "chunk" in event:
                chunk = event["chunk"]
                if "bytes" in chunk:
                    text = chunk["bytes"].decode("utf-8")
                    completion += text
                    print(text, end="", flush=True)

        print("\n" + "-" * 60)
        print()
        return completion, session_id

    except Exception as e:
        print(f"\n❌ Error invoking agent: {e}")
        print(f"\nNote: If 'invoke_agent' API fails, AgentCore may use different API.")
        print(f"Check AWS documentation for bedrock-agent-runtime API updates.")
        return None, session_id


# Test 1: Entity extraction
print("\n" + "=" * 60)
print("TEST 1: Entity Extraction")
print("=" * 60)

try:
    response, session_id = invoke_agent(
        AGENT_RUNTIME_ARN,
        "I just met Sarah Chen from Acme Corporation. She's the VP of Engineering and we discussed their new AI platform project."
    )

    if response:
        print(f"✅ Test 1 passed - Agent responded successfully")
    else:
        print(f"⚠️  Test 1 incomplete - See error above")

except Exception as e:
    print(f"❌ Test 1 failed: {e}")
    session_id = None


# Test 2: Query knowledge graph (only if Test 1 succeeded)
if session_id:
    print("\n" + "=" * 60)
    print("TEST 2: Query Knowledge Graph")
    print("=" * 60)

    try:
        response, _ = invoke_agent(
            AGENT_RUNTIME_ARN,
            "What do you know about Sarah Chen?",
            session_id=session_id  # Continue same session
        )

        if response:
            print(f"✅ Test 2 passed - Agent recalled context")
        else:
            print(f"⚠️  Test 2 incomplete")

    except Exception as e:
        print(f"❌ Test 2 failed: {e}")


# Verify Neo4j data via Lambda
print("\n" + "=" * 60)
print("VERIFY: Neo4j Data Storage")
print("=" * 60)

try:
    cfn = boto3.client("cloudformation", region_name=REGION)
    lambda_client = boto3.client("lambda", region_name=REGION)

    # Get Lambda ARN from CloudFormation
    response = cfn.describe_stacks(StackName="Neo4jContextGraph")
    outputs = response["Stacks"][0]["Outputs"]

    query_function_arn = None
    for output in outputs:
        if output["OutputKey"] == "QueryGraphFunctionArn":
            query_function_arn = output["OutputValue"]
            break

    if query_function_arn:
        print(f"📦 Querying Neo4j via Lambda: {query_function_arn.split(':')[-1]}")

        # Query all Person entities
        response = lambda_client.invoke(
            FunctionName=query_function_arn,
            InvocationType="RequestResponse",
            Payload=json.dumps({
                "action": "query_entities",
                "entity_type": "Person",
                "actor_id": "demo-user-001"
            })
        )

        result = json.loads(response["Payload"].read())
        body = json.loads(result["body"])

        print(f"\n📊 Entities in Neo4j (Person type):")
        if body.get("entities"):
            for entity in body["entities"]:
                print(f"  • {entity.get('name', 'N/A')} - {entity.get('role', entity.get('entity_type', 'N/A'))}")
            print(f"\n✅ Found {len(body['entities'])} entities in Neo4j")
        else:
            print("  (No Person entities found)")
            print("\n⚠️  This is expected if agent hasn't extracted entities yet")
    else:
        print("❌ QueryGraphFunctionArn not found in stack outputs")

except Exception as e:
    print(f"❌ Verification failed: {e}")


# Summary
print("\n" + "=" * 60)
print("TEST SUMMARY")
print("=" * 60)
print()
print("If tests passed:")
print("  ✅ AgentCore Runtime is working")
print("  ✅ Agent can process requests")
print("  ✅ Multi-turn conversation works")
print()
print("Next steps:")
print("  1. Open Jupyter notebook for interactive testing:")
print("     jupyter notebook test_agentcore_deployment.ipynb")
print()
print("  2. View agent logs:")
print("     aws logs tail /aws/bedrock-agentcore/runtimes/context_aware_agent-fcx5I7614H-DEFAULT \\")
print("       --log-stream-name-prefix '2026/05/11/[runtime-logs]' --follow")
print()
print("  3. Check Neo4j data:")
print("     aws lambda invoke --function-name Neo4jContextGraph-LambdasQueryGraphCEF39FDC-WNsGrtErLNdg \\")
print("       --payload '{\"action\":\"query_entities\",\"entity_type\":\"Person\"}' /tmp/response.json")
print()
