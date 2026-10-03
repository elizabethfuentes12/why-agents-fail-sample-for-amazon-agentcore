#!/usr/bin/env python3
"""Deploy Context-Aware Agent with explicit Dockerfile to avoid dependency issues."""

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
    print("Deploying Context-Aware Agent (Clean Build)")
    print("=" * 60)

    # Get region
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
        memory_id = get_stack_output("AgentCoreContext", "MemoryId", region)
        runtime_role_arn = get_stack_output("AgentCoreContext", "RuntimeRoleArn", region)

        print(f"✅ Memory ID: {memory_id}")
        print(f"✅ Runtime Role: {runtime_role_arn}")

    except Exception as e:
        print(f"❌ Failed to get stack outputs: {e}")
        sys.exit(1)

    # Initialize Runtime SDK with new agent name
    print("\n🚀 Configuring AgentCore Runtime...")
    runtime = Runtime()

    try:
        # Use Dockerfile approach to control dependencies explicitly
        result = runtime.configure(
            entrypoint="agent_files/context_agent.py",
            agent_name="context_agent_v2",  # New name to avoid cache
            execution_role=runtime_role_arn,
            memory_mode="STM_AND_LTM",
            protocol="HTTP",
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
        print(f"   Agent Name: context_agent_v2")
        print(f"   Memory Mode: STM_AND_LTM")
        print(f"   Protocol: HTTP")

    except Exception as e:
        print(f"❌ Failed to configure runtime: {e}")
        sys.exit(1)

    # Launch agent
    print("\n🚀 Launching agent to AWS...")
    try:
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

    except Exception as e:
        print(f"❌ Failed to launch agent: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
