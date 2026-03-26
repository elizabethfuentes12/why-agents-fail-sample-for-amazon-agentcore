"""Main CDK stack: DynamoDB + Secrets Manager + AgentCore Gateway + Runtime."""

import aws_cdk as cdk
import aws_cdk.aws_dynamodb as dynamodb
import aws_cdk.aws_secretsmanager as secretsmanager
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

        # --- Secrets Manager ---

        openai_key_secret = secretsmanager.Secret(
            self,
            "OpenAIKeySecret",
            secret_name=f"/{id}/openai-api-key",
            description="OpenAI API key for the booking agent",
        )

        # --- AgentCore IAM role ---

        execution_role = AgentCoreRole(self, "AgentCoreRole")

        bookings_table.grant_read_data(execution_role.role)
        openai_key_secret.grant_read(execution_role.role)

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
                "OPENAI_KEY_SECRET_ARN": openai_key_secret.secret_arn,
                "GATEWAY_URL": gateway.gateway.attr_gateway_url,
            },
        )

        # --- Outputs ---

        cdk.CfnOutput(self, "HotelsTableName", value=hotels_table.table_name)
        cdk.CfnOutput(self, "BookingsTableName", value=bookings_table.table_name)
        cdk.CfnOutput(self, "SteeringRulesTableName", value=steering_rules_table.table_name)
        cdk.CfnOutput(self, "OpenAIKeySecretArn", value=openai_key_secret.secret_arn)
        cdk.CfnOutput(self, "GatewayUrl", value=gateway.gateway.attr_gateway_url)
        cdk.CfnOutput(self, "AgentRuntimeArn", value=runtime.runtime.attr_agent_runtime_arn)
        cdk.CfnOutput(self, "GatewayId", value=gateway.gateway.attr_gateway_identifier)
