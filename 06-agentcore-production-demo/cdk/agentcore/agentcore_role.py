"""IAM roles for AgentCore Runtime and Gateway."""

from constructs import Construct

import aws_cdk.aws_iam as iam


class AgentCoreRole(Construct):
    """Creates IAM execution role for AgentCore Runtime and Gateway."""

    def __init__(self, scope: Construct, id: str) -> None:
        super().__init__(scope, id)

        self.role = iam.Role(
            self,
            "ExecutionRole",
            assumed_by=iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AWSXRayDaemonWriteAccess"),
            ],
        )

        self.role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock-agentcore:InvokeAgentRuntime",
                    "bedrock-agentcore:GetGateway",
                    "bedrock-agentcore:GetGatewayTarget",
                    "bedrock-agentcore:ListGatewayTargets",
                    "bedrock-agentcore:InvokeGateway",
                ],
                resources=["*"],
            )
        )

        self.role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                ],
                resources=["arn:aws:logs:*:*:log-group:/aws/bedrock-agentcore/*"],
            )
        )

        self.role.add_to_policy(
            iam.PolicyStatement(
                actions=["lambda:InvokeFunction"],
                resources=["arn:aws:lambda:*:*:function:hotel-booking-*"],
            )
        )
