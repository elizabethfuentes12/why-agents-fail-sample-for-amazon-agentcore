from aws_cdk import aws_lambda
from constructs import Construct


class Neo4jAgentMemoryLayer(Construct):
    """Lambda layer with neo4j-agent-memory dependencies.

    This layer contains:
    - neo4j-agent-memory
    - neo4j driver
    - pydantic
    - All dependencies required for context graph operations

    Build the layer with: cd layers && ./build_layer.sh
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.layer = aws_lambda.LayerVersion(
            self,
            "Neo4jAgentMemoryLayer",
            code=aws_lambda.Code.from_asset("./layers/neo4j_agent_memory"),
            compatible_runtimes=[aws_lambda.Runtime.PYTHON_3_12],
            compatible_architectures=[aws_lambda.Architecture.ARM_64],
            description="neo4j-agent-memory library for context graphs"
        )
