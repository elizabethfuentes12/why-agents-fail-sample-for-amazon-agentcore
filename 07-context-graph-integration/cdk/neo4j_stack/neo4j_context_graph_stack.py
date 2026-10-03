from aws_cdk import (
    Stack,
    CfnOutput,
    aws_ssm as ssm,
)
from constructs import Construct
from ecs import Neo4jCluster
from lambdas import ProjectLambdas


class Neo4jContextGraphStack(Stack):
    """Complete Neo4j Context Graph stack on AWS.

    This stack creates:
    1. Neo4j database cluster on ECS Fargate with Network Load Balancer
    2. Lambda functions for data seeding and graph queries
    3. SSM parameters for cross-stack references
    4. All necessary networking, security groups, and IAM roles

    The Neo4j database is accessible via a stable NLB endpoint and uses
    Secrets Manager for password storage.
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ECR image URIs (must be pushed before deploying this stack)
        # Run: ./scripts/push_neo4j_to_ecr.sh && ./scripts/push_backup_sidecar_to_ecr.sh
        import os
        account = os.environ.get('CDK_DEFAULT_ACCOUNT')
        region = os.environ.get('CDK_DEFAULT_REGION', 'us-east-1')

        neo4j_image = f"{account}.dkr.ecr.{region}.amazonaws.com/neo4j-enterprise:latest"
        backup_image = f"{account}.dkr.ecr.{region}.amazonaws.com/neo4j-backup-sidecar:latest"

        # Create Neo4j cluster on ECS Fargate
        neo4j = Neo4jCluster(
            self,
            "Neo4jCluster",
            cpu=2048,
            memory_limit_mib=4096,
            neo4j_ecr_image_uri=neo4j_image,
            backup_ecr_image_uri=backup_image
        )

        # Create Lambda functions for data operations
        lambdas = ProjectLambdas(
            self,
            "Lambdas",
            neo4j_uri=neo4j.neo4j_uri,
            neo4j_secret_arn=neo4j.neo4j_secret.secret_arn,
            vpc=neo4j.vpc,
            security_group=neo4j.security_group
        )

        # Store Neo4j connection details in SSM Parameter Store
        # These parameters can be used by other stacks (AgentCore, etc.)
        ssm.StringParameter(
            self,
            "Neo4jUriParameter",
            parameter_name="/neo4j/context-graph/uri",
            string_value=neo4j.neo4j_uri,
            description="Neo4j Bolt URI for context graph"
        )

        ssm.StringParameter(
            self,
            "Neo4jSecretArnParameter",
            parameter_name="/neo4j/context-graph/secret-arn",
            string_value=neo4j.neo4j_secret.secret_arn,
            description="Secrets Manager ARN for Neo4j password"
        )

        ssm.StringParameter(
            self,
            "Neo4jVpcIdParameter",
            parameter_name="/neo4j/context-graph/vpc-id",
            string_value=neo4j.vpc.vpc_id,
            description="VPC ID where Neo4j is running"
        )

        ssm.StringParameter(
            self,
            "Neo4jSecurityGroupIdParameter",
            parameter_name="/neo4j/context-graph/security-group-id",
            string_value=neo4j.security_group.security_group_id,
            description="Security Group ID for Neo4j access"
        )

        ssm.StringParameter(
            self,
            "Neo4jDumpBucketParameter",
            parameter_name="/neo4j/context-graph/dump-bucket",
            string_value=neo4j.dump_bucket.bucket_name,
            description="S3 bucket name for Neo4j dumps"
        )

        # Outputs
        CfnOutput(
            self,
            "Neo4jBoltUri",
            value=neo4j.neo4j_uri,
            description="Neo4j Bolt connection URI",
            export_name="Neo4jContextGraphUri"
        )

        CfnOutput(
            self,
            "Neo4jPasswordSecretArn",
            value=neo4j.neo4j_secret.secret_arn,
            description="Secrets Manager ARN for Neo4j password",
            export_name="Neo4jContextGraphSecretArn"
        )

        CfnOutput(
            self,
            "SeedDataFunctionName",
            value=lambdas.seed_data.function_name,
            description="Lambda function for seeding sample data",
            export_name="Neo4jContextGraphSeedDataFunction"
        )

        CfnOutput(
            self,
            "QueryGraphFunctionArn",
            value=lambdas.query_graph.function_arn,
            description="Lambda function ARN for querying the graph",
            export_name="Neo4jContextGraphQueryFunction"
        )

        CfnOutput(
            self,
            "NLBDnsName",
            value=neo4j.nlb.load_balancer_dns_name,
            description="Network Load Balancer DNS name"
        )

        CfnOutput(
            self,
            "DumpBucketName",
            value=neo4j.dump_bucket.bucket_name,
            description="S3 bucket for Neo4j dumps (backup/restore)",
            export_name="Neo4jContextGraphDumpBucket"
        )
