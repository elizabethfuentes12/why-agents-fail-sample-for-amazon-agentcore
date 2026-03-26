"""AgentCore Runtime deployment for the booking agent."""

from constructs import Construct

import aws_cdk.aws_bedrockagentcore as agentcore
import aws_cdk.aws_s3_assets as s3_assets


class AgentCoreRuntime(Construct):
    """Deploys the booking agent as an AgentCore Runtime."""

    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        role_arn: str,
        environment_variables: dict[str, str],
    ) -> None:
        super().__init__(scope, id)

        code_asset = s3_assets.Asset(
            self,
            "AgentCode",
            path="../agent_files/deployment_package.zip",
        )

        self.runtime = agentcore.CfnRuntime(
            self,
            "Runtime",
            agent_runtime_name="HotelBookingAgent",
            description="Hotel booking agent with DynamoDB-backed tools and symbolic validation",
            agent_runtime_artifact=agentcore.CfnRuntime.AgentRuntimeArtifactProperty(
                code_configuration=agentcore.CfnRuntime.CodeConfigurationProperty(
                    code=agentcore.CfnRuntime.CodeProperty(
                        s3=agentcore.CfnRuntime.S3LocationProperty(
                            bucket=code_asset.s3_bucket_name,
                            prefix=code_asset.s3_object_key,
                        )
                    ),
                    entry_point=["booking_agent.py"],
                    runtime="PYTHON_3_11",
                )
            ),
            network_configuration=agentcore.CfnRuntime.NetworkConfigurationProperty(
                network_mode="PUBLIC",
            ),
            lifecycle_configuration=agentcore.CfnRuntime.LifecycleConfigurationProperty(
                idle_runtime_session_timeout=900,  # 15 minutes
                max_lifetime=28800,  # 8 hours
            ),
            role_arn=role_arn,
            environment_variables=environment_variables,
        )
