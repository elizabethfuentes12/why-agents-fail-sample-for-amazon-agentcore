"""AgentCore Runtime deployment construct using CfnRuntime."""

import os
import subprocess
from typing import Optional

from constructs import Construct
from aws_cdk import (
    aws_bedrockagentcore as bedrockagentcore,
    aws_s3_assets as s3_assets,
    aws_iam as iam,
)


class AgentCoreDeployment(Construct):
    """Creates an AgentCore Runtime with code-based deployment."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        role: iam.Role,
        memory_id: str,
        environment_variables: Optional[dict] = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        env_vars = {
            "BEDROCK_AGENTCORE_MEMORY_ID": memory_id,
        }
        if environment_variables:
            env_vars.update(environment_variables)

        # Build deployment package if it doesn't exist
        directory = os.path.join(os.path.dirname(__file__), "..", "..", "agent_files")
        zip_path = os.path.join(directory, "deployment_package.zip")
        if not os.path.exists(zip_path):
            script_path = os.path.join(os.path.dirname(__file__), "..", "..", "create_deployment_package.sh")
            result = subprocess.run(
                ["bash", script_path],
                cwd=os.path.join(os.path.dirname(__file__), "..", ".."),
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise RuntimeError(f"Failed to create deployment package: {result.stderr}")

        code_asset = s3_assets.Asset(self, "AgentCodeAsset", path=zip_path)
        code_asset.grant_read(role)

        self.runtime = bedrockagentcore.CfnRuntime(
            self,
            "AgentCoreRuntime",
            agent_runtime_artifact=bedrockagentcore.CfnRuntime.AgentRuntimeArtifactProperty(
                code_configuration=bedrockagentcore.CfnRuntime.CodeConfigurationProperty(
                    code=bedrockagentcore.CfnRuntime.CodeProperty(
                        s3=bedrockagentcore.CfnRuntime.S3LocationProperty(
                            bucket=code_asset.s3_bucket_name,
                            prefix=code_asset.s3_object_key,
                        )
                    ),
                    entry_point=["context_agent.py"],
                    runtime="PYTHON_3_11",
                )
            ),
            agent_runtime_name="ContextAwareAgent",
            description="Context-aware agent with AgentCore Memory",
            environment_variables=env_vars,
            network_configuration=bedrockagentcore.CfnRuntime.NetworkConfigurationProperty(
                network_mode="PUBLIC"
            ),
            lifecycle_configuration=bedrockagentcore.CfnRuntime.LifecycleConfigurationProperty(
                idle_runtime_session_timeout=900,
                max_lifetime=28800,
            ),
            role_arn=role.role_arn,
        )
        self.runtime.node.add_dependency(code_asset)

    @property
    def agent_runtime_arn(self) -> str:
        return self.runtime.attr_agent_runtime_arn

    @property
    def agent_runtime_id(self) -> str:
        return self.runtime.ref
