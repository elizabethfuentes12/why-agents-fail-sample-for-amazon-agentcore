"""Main CDK stack: DynamoDB + AgentCore Gateway + Runtime (Amazon Bedrock)."""

import aws_cdk as cdk
import aws_cdk.aws_dynamodb as dynamodb
from constructs import Construct

from agentcore import AgentCoreGateway, AgentCoreRole, AgentCoreRuntime


class HotelBookingAgentStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # --- DynamoDB tables ---

        hotels_table = dynamodb.Table(
            self,
            "HotelsTable",
            table_name=f"{id}-Hotels",
            partition_key=dynamodb.Attribute(
                name="hotel_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        bookings_table = dynamodb.Table(
            self,
            "BookingsTable",
            table_name=f"{id}-Bookings",
            partition_key=dynamodb.Attribute(
                name="booking_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        steering_rules_table = dynamodb.Table(
            self,
            "SteeringRulesTable",
            table_name=f"{id}-SteeringRules",
            partition_key=dynamodb.Attribute(
                name="rule_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        # --- AgentCore IAM role ---

        execution_role = AgentCoreRole(self, "AgentCoreRole")

        bookings_table.grant_read_data(execution_role.role)

        # Allow the agent to invoke Amazon Bedrock models (Claude Sonnet 4).
        execution_role.role.add_to_policy(
            cdk.aws_iam.PolicyStatement(
                actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                resources=["*"],
            )
        )

        # --- GraphRAG integration (optional) ---

        graphrag_query_lambda_arn = self.node.try_get_context("graphrag_query_lambda_arn") or ""

        # --- AgentCore Gateway (MCP semantic tool routing) ---

        gateway = AgentCoreGateway(
            self,
            "AgentCoreGateway",
            role_arn=execution_role.role.role_arn,
            hotels_table_name=hotels_table.table_name,
            hotels_table_arn=hotels_table.table_arn,
            bookings_table_name=bookings_table.table_name,
            bookings_table_arn=bookings_table.table_arn,
            steering_rules_table_name=steering_rules_table.table_name,
            steering_rules_table_arn=steering_rules_table.table_arn,
            graphrag_query_lambda_arn=graphrag_query_lambda_arn,
        )

        # --- AgentCore Runtime (connects to Gateway via MCP) ---

        runtime = AgentCoreRuntime(
            self,
            "AgentCoreRuntime",
            role_arn=execution_role.role.role_arn,
            environment_variables={
                "AWS_REGION": self.region,
                "BOOKINGS_TABLE": bookings_table.table_name,
                "GATEWAY_URL": gateway.gateway.attr_gateway_url,
            },
        )

        # --- Outputs ---

        cdk.CfnOutput(self, "HotelsTableName", value=hotels_table.table_name)
        cdk.CfnOutput(self, "BookingsTableName", value=bookings_table.table_name)
        cdk.CfnOutput(self, "SteeringRulesTableName", value=steering_rules_table.table_name)
        cdk.CfnOutput(self, "GatewayUrl", value=gateway.gateway.attr_gateway_url)
        cdk.CfnOutput(self, "AgentRuntimeArn", value=runtime.runtime.attr_agent_runtime_arn)
        cdk.CfnOutput(self, "GatewayId", value=gateway.gateway.attr_gateway_identifier)
