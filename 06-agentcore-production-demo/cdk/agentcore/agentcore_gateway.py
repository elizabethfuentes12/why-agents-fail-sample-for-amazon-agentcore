"""AgentCore Gateway with Lambda tool targets."""

import json
from pathlib import Path

from constructs import Construct

import aws_cdk as cdk
import aws_cdk.aws_bedrockagentcore as agentcore
import aws_cdk.aws_iam as iam
import aws_cdk.aws_lambda as _lambda


class AgentCoreGateway(Construct):
    """Creates an AgentCore Gateway with MCP protocol and Lambda tool targets."""

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        role_arn: str,
        hotels_table_name: str,
        hotels_table_arn: str,
        bookings_table_name: str,
        bookings_table_arn: str,
        steering_rules_table_name: str,
        steering_rules_table_arn: str,
        graphrag_query_lambda_arn: str = "",
    ) -> None:
        super().__init__(scope, id)

        self.gateway = agentcore.CfnGateway(
            self,
            "Gateway",
            name="HotelBookingGateway",
            description="MCP Gateway for hotel booking tools with semantic routing",
            protocol_type="MCP",
            protocol_configuration=agentcore.CfnGateway.GatewayProtocolConfigurationProperty(
                mcp=agentcore.CfnGateway.MCPGatewayConfigurationProperty(
                    instructions="Hotel booking tools: search, book, pay, confirm, cancel, and validate business rules.",
                    search_type="SEMANTIC",
                    supported_versions=["2025-03-26"],
                ),
            ),
            authorizer_type="NONE",
            role_arn=role_arn,
        )

        all_schemas = self._load_tool_schemas()

        # Only include query_knowledge_graph if GraphRAG stack is deployed
        schemas = [
            s for s in all_schemas
            if s["name"] != "query_knowledge_graph" or graphrag_query_lambda_arn
        ]

        lambda_role = iam.Role(
            self,
            "ToolLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                ),
            ],
        )

        lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "dynamodb:GetItem",
                    "dynamodb:PutItem",
                    "dynamodb:UpdateItem",
                    "dynamodb:Scan",
                    "dynamodb:Query",
                ],
                resources=[hotels_table_arn, bookings_table_arn, steering_rules_table_arn],
            )
        )

        env = {
            "HOTELS_TABLE": hotels_table_name,
            "BOOKINGS_TABLE": bookings_table_name,
            "STEERING_RULES_TABLE": steering_rules_table_name,
        }

        for schema in schemas:
            tool_name = schema["name"]

            # query_knowledge_graph uses the Lambda from the GraphRAG stack
            if tool_name == "query_knowledge_graph" and graphrag_query_lambda_arn:
                fn = _lambda.Function.from_function_arn(
                    self, f"Tool-{tool_name}", graphrag_query_lambda_arn
                )
            else:
                fn = _lambda.Function(
                    self,
                    f"Tool-{tool_name}",
                    function_name=f"hotel-booking-{tool_name}",
                    runtime=_lambda.Runtime.PYTHON_3_11,
                    handler="lambda_function.handler",
                    code=_lambda.Code.from_asset(f"../lambda_tools/{tool_name}"),
                    environment=env,
                    role=lambda_role,
                    timeout=cdk.Duration.seconds(30),
                    memory_size=256,
                )

            tool_definition = agentcore.CfnGatewayTarget.ToolDefinitionProperty(
                name=schema["name"],
                description=schema["description"],
                input_schema=self._build_schema_definition(schema["input_schema"]),
            )

            # GatewayTarget names must match ^([0-9a-zA-Z][-]?){1,100}$
            target_name = tool_name.replace("_", "-")

            agentcore.CfnGatewayTarget(
                self,
                f"Target-{tool_name}",
                name=target_name,
                gateway_identifier=self.gateway.attr_gateway_identifier,
                credential_provider_configurations=[
                    agentcore.CfnGatewayTarget.CredentialProviderConfigurationProperty(
                        credential_provider_type="GATEWAY_IAM_ROLE",
                    ),
                ],
                target_configuration=agentcore.CfnGatewayTarget.TargetConfigurationProperty(
                    mcp=agentcore.CfnGatewayTarget.McpTargetConfigurationProperty(
                        lambda_=agentcore.CfnGatewayTarget.McpLambdaTargetConfigurationProperty(
                            lambda_arn=fn.function_arn,
                            tool_schema=agentcore.CfnGatewayTarget.ToolSchemaProperty(
                                inline_payload=[tool_definition],
                            ),
                        ),
                    ),
                ),
            )

    def _load_tool_schemas(self) -> list[dict]:
        schema_path = Path(__file__).parent.parent.parent / "tool_schemas" / "tools.json"
        with open(schema_path, encoding="utf-8") as f:
            return json.load(f)

    def _build_schema_definition(
        self, schema: dict
    ) -> agentcore.CfnGatewayTarget.SchemaDefinitionProperty:
        props = {}
        if "properties" in schema:
            props = {
                k: agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
                    type=v.get("type", "string"),
                    description=v.get("description", ""),
                )
                for k, v in schema["properties"].items()
            }

        return agentcore.CfnGatewayTarget.SchemaDefinitionProperty(
            type=schema.get("type", "object"),
            properties=props if props else None,
            required=schema.get("required"),
        )
