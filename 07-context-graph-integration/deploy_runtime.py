#!/usr/bin/env python3
"""Deploy Context-Aware Agent to AgentCore Runtime.

Uses bedrock-agentcore-starter-toolkit Runtime SDK to deploy the agent.

Prerequisites:
1. Neo4jContextGraph stack deployed
2. AgentCoreContext stack deployed (DynamoDB + IAM)
3. Neo4j seeded with sample data
"""

import os
import sys
import boto3
from bedrock_agentcore_starter_toolkit import Runtime

def get_stack_output(stack_name: str, output_key: str, region: str) -> str:
    """Get CloudFormation stack output value."""
    cfn = boto3.client("cloudformation", region_name=region)
    response = cfn.describe_stacks(StackName=stack_name)
    outputs = response["Stacks"][0]["Outputs"]
    for output in outputs:
        if output["OutputKey"] == output_key:
            return output["OutputValue"]
    raise ValueError(f"Output {output_key} not found in stack {stack_name}")


def main():
    print("=" * 60)
    print("Deploying Context-Aware Agent to AgentCore Runtime")
    print("=" * 60)

    # Get region from environment or AWS config
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
    if not region:
        session = boto3.Session()
        region = session.region_name

    if not region:
        print("❌ Could not determine AWS region. Set AWS_REGION environment variable.")
        sys.exit(1)

    print(f"\n📍 Using region: {region}")

    # Get stack outputs
    print("\n📦 Getting stack outputs...")
    try:
        memory_id = get_stack_output(
            "AgentCoreContext", "MemoryId", region
        )
        runtime_role_arn = get_stack_output(
            "AgentCoreContext", "RuntimeRoleArn", region
        )

        print(f"✅ Memory ID: {memory_id}")
        print(f"✅ Runtime Role: {runtime_role_arn}")

    except Exception as e:
        print(f"❌ Failed to get stack outputs: {e}")
        print("\nMake sure both stacks are deployed:")
        print("  1. Neo4jContextGraph")
        print("  2. AgentCoreContext")
        sys.exit(1)

    # Initialize Runtime SDK
    print("\n🚀 Configuring AgentCore Runtime...")
    runtime = Runtime()

    # Configure agent
    try:
        # Entrypoint: file path only (SDK will look for BedrockAgentCoreApp instance)
        result = runtime.configure(
            entrypoint="agent_files/context_agent.py",
            agent_name="context_aware_agent",
            execution_role=runtime_role_arn,
            memory_mode="STM_AND_LTM",  # Enable both short-term and long-term memory
            protocol="HTTP",  # BedrockAgentCoreApp uses HTTP, not MCP
            region=region,
            deployment_type="container",
            auto_create_ecr=True,
            auto_create_s3=False,
            vpc_enabled=False,
            non_interactive=True,
            disable_otel=False,
        )

        print("\n✅ Runtime configured successfully")
        print(f"📋 Configuration:")
        print(f"   Agent Name: context_aware_agent")
        print(f"   Memory Mode: STM_AND_LTM")
        print(f"   Protocol: MCP")
        if hasattr(result, 'agent_name'):
            print(f"   Runtime Type: {getattr(result, 'runtime_type', 'container')}")

    except Exception as e:
        print(f"❌ Failed to configure runtime: {e}")
        sys.exit(1)

    # Launch agent
    print("\n🚀 Launching agent to AWS...")
    try:
        # Memory strategies will be retrieved dynamically by the agent at runtime
        print(f"\n💾 Memory ID: {memory_id}")
        print("   Strategies will be configured dynamically")

        launch_result = runtime.launch(
            auto_update_on_conflict=True,
            env_vars={
                "BEDROCK_AGENTCORE_MEMORY_ID": memory_id,
                "AWS_REGION": region,
            }
        )

        print("\n✅ Agent launched successfully!")
        print(f"📋 Deployment details:")
        print(f"   Agent ARN: {launch_result.agent_arn}")
        print(f"   Endpoint: {launch_result.endpoint_url}")
        print(f"   Status: {launch_result.status}")

        # Get runtime status
        status = runtime.status()
        print(f"\n📊 Runtime Status:")
        print(f"   State: {status.runtime_status}")
        print(f"   Version: {status.runtime_version}")

        print("\n" + "=" * 60)
        print("✅ Deployment Complete!")
        print("=" * 60)
        print("\nTest the agent:")
        print(f'  python3 -c "')
        print(f'    from bedrock_agentcore_starter_toolkit import Runtime')
        print(f'    runtime = Runtime()')
        print(f'    result = runtime.invoke({{"prompt": "I met Sarah Chen from Acme Corp"}})')
        print(f'    print(result)')
        print(f'  "')

    except Exception as e:
        print(f"❌ Failed to launch agent: {e}")
        print("\nTroubleshooting:")
        print("  - Check that ECR repository was created")
        print("  - Verify IAM role has correct permissions")
        print("  - Check CloudWatch Logs for errors")
        sys.exit(1)


if __name__ == "__main__":
    main()
