from aws_cdk import (
    Duration,
    aws_iam as iam,
    aws_lambda,
    aws_ec2 as ec2,
)
from constructs import Construct
from layers_module import Neo4jAgentMemoryLayer

LAMBDA_TIMEOUT = 900

BASE_LAMBDA_CONFIG = dict(
    timeout=Duration.seconds(LAMBDA_TIMEOUT),
    architecture=aws_lambda.Architecture.ARM_64,
    runtime=aws_lambda.Runtime.PYTHON_3_12,
    tracing=aws_lambda.Tracing.ACTIVE
)


class ProjectLambdas(Construct):
    """Lambda functions for Neo4j Context Graph data operations.

    This construct creates Lambda functions for:
    - seed_data: Populate Neo4j with initial sample data using neo4j-agent-memory
    - query_graph: Query the context graph (used by agents)
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        neo4j_uri: str,
        neo4j_secret_arn: str,
        vpc: ec2.IVpc,
        security_group: ec2.ISecurityGroup,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Lambda layer with neo4j-agent-memory dependencies
        neo4j_layer = Neo4jAgentMemoryLayer(self, "Layer")

        # Seed data Lambda
        self.seed_data = aws_lambda.Function(
            self,
            "SeedData",
            layers=[neo4j_layer.layer],
            handler="lambda_function.lambda_handler",
            code=aws_lambda.Code.from_asset("./lambdas/code/seed_data"),
            environment={
                "NEO4J_URI": neo4j_uri,
                "NEO4J_PASSWORD_SECRET_ARN": neo4j_secret_arn,
                "NEO4J_USER": "neo4j",
                "NEO4J_DATABASE": "neo4j"
            },
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
            ),
            security_groups=[security_group],
            **BASE_LAMBDA_CONFIG
        )

        # Grant permissions to read Neo4j secret
        self.seed_data.add_to_role_policy(
            iam.PolicyStatement(
                actions=["secretsmanager:GetSecretValue"],
                resources=[neo4j_secret_arn]
            )
        )

        # Query graph Lambda (for agent tools)
        self.query_graph = aws_lambda.Function(
            self,
            "QueryGraph",
            layers=[neo4j_layer.layer],
            handler="lambda_function.lambda_handler",
            code=aws_lambda.Code.from_asset("./lambdas/code/query_graph"),
            environment={
                "NEO4J_URI": neo4j_uri,
                "NEO4J_PASSWORD_SECRET_ARN": neo4j_secret_arn,
                "NEO4J_USER": "neo4j",
                "NEO4J_DATABASE": "neo4j"
            },
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
            ),
            security_groups=[security_group],
            **BASE_LAMBDA_CONFIG
        )

        # Grant permissions to read Neo4j secret
        self.query_graph.add_to_role_policy(
            iam.PolicyStatement(
                actions=["secretsmanager:GetSecretValue"],
                resources=[neo4j_secret_arn]
            )
        )
