"""AgentCore Runtime stack for context-aware agent.

This stack creates:
1. AgentCore Memory (LTM) with semantic and preference strategies
2. IAM roles for memory and runtime execution
3. AgentCore Runtime with code deployment
4. RuntimeEndpoint for invocation

Everything deployed via CDK - no separate deployment script needed.
"""

import os

from aws_cdk import (
    Stack,
    CfnOutput,
    aws_bedrockagentcore as bedrockagentcore,
    aws_iam as iam,
)
from constructs import Construct

from constructs.agentcore_deployment import AgentCoreDeployment


class AgentCoreContextStack(Stack):
    """AgentCore Runtime with context-aware Swarm agent."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # AgentCore Memory execution role
        memory_role = iam.Role(
            self,
            "MemoryExecutionRole",
            assumed_by=iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
            description="Execution role for AgentCore Memory"
        )

        memory_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                    "bedrock-agentcore:CreateEvent",
                    "bedrock-agentcore:GetEvent",
                    "bedrock-agentcore:ListEvents",
                    "bedrock-agentcore:RetrieveMemoryRecords",
                    "bedrock-agentcore:ListMemoryRecords",
                    "bedrock-agentcore:DeleteMemoryRecord",
                ],
                resources=["*"],
            )
        )

        # AgentCore Memory with semantic and preference strategies
        memory = bedrockagentcore.CfnMemory(
            self,
            "AgentMemory",
            name="ContextAgentMemory",
            description="Long-term memory for context-aware agent - stores facts and preferences across sessions",
            event_expiry_duration=7,  # Events expire after 7 days
            memory_execution_role_arn=memory_role.role_arn,
            memory_strategies=[
                bedrockagentcore.CfnMemory.MemoryStrategyProperty(
                    semantic_memory_strategy=bedrockagentcore.CfnMemory.SemanticMemoryStrategyProperty(
                        name="UserFacts",
                        description="Extracts and stores factual information - names, companies, events, relationships",
                    )
                ),
                bedrockagentcore.CfnMemory.MemoryStrategyProperty(
                    user_preference_memory_strategy=bedrockagentcore.CfnMemory.UserPreferenceMemoryStrategyProperty(
                        name="UserPreferences",
                        description="Tracks user preferences and recurring patterns",
                    )
                ),
            ],
        )

        # IAM role for AgentCore Runtime
        runtime_role = iam.Role(
            self,
            "AgentCoreRuntimeRole",
            assumed_by=iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
            description="Execution role for AgentCore Runtime with context agent",
        )

        # Grant access to AgentCore Memory
        runtime_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock-agentcore:CreateEvent",
                    "bedrock-agentcore:GetEvent",
                    "bedrock-agentcore:ListEvents",
                    "bedrock-agentcore:RetrieveMemoryRecords",
                    "bedrock-agentcore:ListMemoryRecords",
                ],
                resources=[memory.attr_memory_arn],
            )
        )

        # Grant ECR permissions for AgentCore to pull container images
        runtime_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "ecr:GetAuthorizationToken",
                    "ecr:BatchGetImage",
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:BatchCheckLayerAvailability"
                ],
                resources=["*"]  # GetAuthorizationToken requires *
            )
        )

        # Grant Bedrock model access (cross-region)
        # Cross-region inference profiles can route to any region
        runtime_role.add_to_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                resources=[
                    # Claude Sonnet 4 cross-region inference profile
                    f"arn:aws:bedrock:{self.region}:{self.account}:inference-profile/us.anthropic.claude-sonnet-4-*",
                    # Allow foundation model access in ALL regions (cross-region routing)
                    "arn:aws:bedrock:*::foundation-model/anthropic.claude-sonnet-4-*",
                    "arn:aws:bedrock:*::foundation-model/us.anthropic.claude-sonnet-4-*",
                    # Amazon Titan embeddings V2 (all regions, 1024 dimensions, recommended)
                    "arn:aws:bedrock:*::foundation-model/amazon.titan-embed-text-v2:0",
                ],
            )
        )

        # Grant AgentCore Runtime permissions
        runtime_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock-agentcore:InvokeAgentRuntime",
                    "bedrock-agentcore:GetGateway",
                    "bedrock-agentcore:GetGatewayTarget",
                    "bedrock-agentcore:ListGatewayTargets",
                    "bedrock-agentcore:InvokeGateway",
                ],
                resources=["*"],  # Scoped to account by IAM
            )
        )

        # Grant CloudWatch Logs access
        runtime_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                ],
                resources=[f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/bedrock-agentcore/*"],
            )
        )

        # Grant X-Ray tracing
        runtime_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AWSXRayDaemonWriteAccess")
        )

        # --- AgentCore Runtime ---
        agentcore = AgentCoreDeployment(
            self,
            "AgentCore",
            role=runtime_role,
            memory_id=memory.attr_memory_id,
            environment_variables={
                "AWS_REGION": os.environ.get("AWS_REGION", self.region),
            },
        )

        # --- AgentCore Runtime Endpoint ---
        endpoint = bedrockagentcore.CfnRuntimeEndpoint(
            self,
            "AgentCoreEndpoint",
            agent_runtime_id=agentcore.agent_runtime_id,
            name="ContextAgentEndpoint",
            description="Endpoint to invoke the context-aware agent",
        )
        endpoint.node.add_dependency(agentcore.runtime)

        # Outputs
        CfnOutput(
            self,
            "MemoryId",
            value=memory.attr_memory_id,
            description="AgentCore Memory ID",
            export_name="ContextAgentMemoryId",
        )

        CfnOutput(
            self,
            "MemoryArn",
            value=memory.attr_memory_arn,
            description="AgentCore Memory ARN",
            export_name="ContextAgentMemoryArn",
        )

        CfnOutput(
            self,
            "RuntimeRoleArn",
            value=runtime_role.role_arn,
            description="IAM role ARN for AgentCore Runtime",
            export_name="ContextAgentRuntimeRole",
        )

        CfnOutput(
            self,
            "AgentRuntimeArn",
            value=agentcore.agent_runtime_arn,
            description="AgentCore Runtime ARN",
            export_name="ContextAgentRuntimeArn",
        )

        CfnOutput(
            self,
            "AgentRuntimeId",
            value=agentcore.agent_runtime_id,
            description="AgentCore Runtime ID",
        )

        CfnOutput(
            self,
            "EndpointArn",
            value=endpoint.attr_agent_runtime_endpoint_arn,
            description="AgentCore RuntimeEndpoint ARN",
        )
