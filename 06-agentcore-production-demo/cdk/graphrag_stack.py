"""GraphRAG stack: AuraDB Free + automated graph build + query Lambda.

Deploys independently from the booking agent stack.
Exports connection parameters via SSM so the booking stack can consume them.

Modes (set via CDK context):
    - lite (default): Uploads 30 docs, builds graph in a single Lambda (~15 min)
    - full: Uploads all 300 docs, uses Step Functions to batch-process (~1-2 hours)

Usage:
    cdk deploy GraphRAGStack                         # lite mode (30 docs)
    cdk deploy GraphRAGStack -c graph_mode=full      # full mode (300 docs)

Prerequisites:
    1. Create a free AuraDB instance (a managed graph database) at https://neo4j.com/cloud/aura-free/
       (requires email registration; check regional availability at https://neo4j.com/cloud/aura-free/)
    2. In the AWS Console, navigate to the Secrets Manager service (for storing credentials securely),
       then populate the 4 secrets created by this stack
"""

import aws_cdk as cdk
import aws_cdk.aws_iam as iam
import aws_cdk.aws_lambda as _lambda
import aws_cdk.aws_logs as logs
import aws_cdk.aws_s3 as s3
import aws_cdk.aws_s3_deployment as s3_deployment
import aws_cdk.aws_secretsmanager as secretsmanager
import aws_cdk.aws_ssm as ssm
import aws_cdk.aws_stepfunctions as sfn
import aws_cdk.aws_stepfunctions_tasks as sfn_tasks
import aws_cdk.custom_resources as cr
from constructs import Construct


class GraphRAGStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        graph_mode = self.node.try_get_context("graph_mode") or "lite"
        max_docs = 30 if graph_mode == "lite" else 300

        # --- Secrets (populate via AWS Console after deploy) ---

        neo4j_uri_secret = secretsmanager.Secret(
            self, "Neo4jUri",
            secret_name=f"/{id}/neo4j-uri",
            description="AuraDB connection URI (e.g. neo4j+s://xxxx.databases.neo4j.io)",
        )

        neo4j_user = secretsmanager.Secret(
            self, "Neo4jUser",
            secret_name=f"/{id}/neo4j-user",
            description="AuraDB username (default: neo4j)",
        )

        neo4j_password = secretsmanager.Secret(
            self, "Neo4jPassword",
            secret_name=f"/{id}/neo4j-password",
            description="AuraDB password",
        )

        openai_api_key_secret = secretsmanager.Secret(
            self, "OpenAIApiKey",
            secret_name=f"/{id}/openai-api-key",
            description="OpenAI API key for graph building (SimpleKGPipeline)",
        )

        # --- S3 Bucket + auto-upload docs ---

        docs_bucket = s3.Bucket(
            self, "DocsBucket",
            removal_policy=cdk.RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
        )

        s3_deployment.BucketDeployment(
            self, "UploadHotelFaqs",
            sources=[s3_deployment.Source.asset("../data")],
            destination_bucket=docs_bucket,
            destination_key_prefix="hotel-faqs/",
        )

        # --- Build Graph Lambda ---

        build_lambda = _lambda.Function(
            self, "BuildGraph",
            function_name="graphrag-build-graph",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="lambda_function.handler",
            code=_lambda.Code.from_asset("../lambda_tools/build_graph/package"),
            timeout=cdk.Duration.minutes(15),
            memory_size=1024,
            environment={
                "DOCS_S3_BUCKET": docs_bucket.bucket_name,
                "DOCS_S3_PREFIX": "hotel-faqs/",
                "MAX_DOCS": str(max_docs),
                "NEO4J_URI_SECRET_ARN": neo4j_uri_secret.secret_arn,
                "NEO4J_USER_SECRET_ARN": neo4j_user.secret_arn,
                "NEO4J_PASSWORD_SECRET_ARN": neo4j_password.secret_arn,
                "OPENAI_API_KEY_SECRET_ARN": openai_api_key_secret.secret_arn,
            },
        )

        docs_bucket.grant_read(build_lambda)
        neo4j_uri_secret.grant_read(build_lambda)
        neo4j_user.grant_read(build_lambda)
        neo4j_password.grant_read(build_lambda)
        openai_api_key_secret.grant_read(build_lambda)

        # --- Graph Build Trigger ---

        if graph_mode == "full":
            # Full mode: Step Functions batches 300 docs across multiple Lambda invocations
            self._create_step_functions_pipeline(
                build_lambda, docs_bucket, max_docs,
                neo4j_uri_secret, neo4j_user, neo4j_password, openai_api_key_secret,
            )
        # Note: graph build is NOT auto-triggered during deploy.
        # Populate secrets first, then invoke manually:
        #   aws lambda invoke --function-name graphrag-build-graph --region us-east-1 /tmp/build.json

        # --- Query Lambda ---

        query_lambda = _lambda.Function(
            self, "QueryKnowledgeGraph",
            function_name="graphrag-query-knowledge-graph",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="lambda_function.handler",
            code=_lambda.Code.from_asset("../lambda_tools/query_knowledge_graph/package"),
            timeout=cdk.Duration.seconds(30),
            memory_size=256,
            environment={
                "NEO4J_URI_SECRET_ARN": neo4j_uri_secret.secret_arn,
                "NEO4J_USER_SECRET_ARN": neo4j_user.secret_arn,
                "NEO4J_PASSWORD_SECRET_ARN": neo4j_password.secret_arn,
            },
        )

        neo4j_uri_secret.grant_read(query_lambda)
        neo4j_user.grant_read(query_lambda)
        neo4j_password.grant_read(query_lambda)

        # --- Export parameters via SSM ---

        ssm.StringParameter(
            self, "SsmQueryLambdaArn",
            parameter_name=f"/{id}/query-lambda-arn",
            string_value=query_lambda.function_arn,
        )

        ssm.StringParameter(
            self, "SsmDocsBucket",
            parameter_name=f"/{id}/docs-bucket",
            string_value=docs_bucket.bucket_name,
        )

        # --- Outputs ---

        cdk.CfnOutput(self, "GraphMode", value=graph_mode)
        cdk.CfnOutput(self, "MaxDocs", value=str(max_docs))
        cdk.CfnOutput(self, "DocsBucketName", value=docs_bucket.bucket_name)
        cdk.CfnOutput(self, "QueryLambdaArn", value=query_lambda.function_arn)
        cdk.CfnOutput(self, "BuildLambdaName", value=build_lambda.function_name)
        cdk.CfnOutput(self, "Neo4jUriSecretArn", value=neo4j_uri_secret.secret_arn)
        cdk.CfnOutput(self, "Neo4jUserSecretArn", value=neo4j_user.secret_arn)
        cdk.CfnOutput(self, "Neo4jPasswordSecretArn", value=neo4j_password.secret_arn)
        cdk.CfnOutput(self, "OpenAIKeySecretArn", value=openai_api_key_secret.secret_arn)
        cdk.CfnOutput(
            self, "BuildGraphCommand",
            value=(
                f"aws lambda invoke --function-name {build_lambda.function_name} "
                f"--region {self.region} /tmp/build-graph-output.json "
                f"&& cat /tmp/build-graph-output.json"
            ),
        )

    def _create_step_functions_pipeline(
        self, build_lambda, docs_bucket, max_docs,
        neo4j_uri_secret, neo4j_user, neo4j_password, openai_api_key_secret,
    ):
        """Create Step Functions pipeline for full 300-doc processing."""

        # Each step processes a batch of 30 docs with an offset
        batch_size = 30
        steps = []

        for batch_start in range(0, max_docs, batch_size):
            # Create a Lambda for each batch with offset
            batch_lambda = _lambda.Function(
                self, f"BuildBatch{batch_start}",
                function_name=f"graphrag-build-batch-{batch_start}",
                runtime=_lambda.Runtime.PYTHON_3_11,
                handler="lambda_function.handler",
                code=_lambda.Code.from_asset("../lambda_tools/build_graph/package"),
                timeout=cdk.Duration.minutes(15),
                memory_size=1024,
                environment={
                    "DOCS_S3_BUCKET": docs_bucket.bucket_name,
                    "DOCS_S3_PREFIX": "hotel-faqs/",
                    "MAX_DOCS": str(batch_size),
                    "SKIP_DOCS": str(batch_start),
                    "SKIP_CLEAR": "true" if batch_start > 0 else "false",
                    "NEO4J_URI_SECRET_ARN": neo4j_uri_secret.secret_arn,
                    "NEO4J_USER_SECRET_ARN": neo4j_user.secret_arn,
                    "NEO4J_PASSWORD_SECRET_ARN": neo4j_password.secret_arn,
                    "OPENAI_API_KEY_SECRET_ARN": openai_api_key_secret.secret_arn,
                },
            )

            docs_bucket.grant_read(batch_lambda)
            neo4j_uri_secret.grant_read(batch_lambda)
            neo4j_user.grant_read(batch_lambda)
            neo4j_password.grant_read(batch_lambda)
            openai_api_key_secret.grant_read(batch_lambda)

            step = sfn_tasks.LambdaInvoke(
                self, f"ProcessBatch{batch_start}",
                lambda_function=batch_lambda,
                result_path=f"$.batch{batch_start}",
            )
            steps.append(step)

        # Chain steps sequentially
        chain = steps[0]
        for step in steps[1:]:
            chain = chain.next(step)

        sfn.StateMachine(
            self, "GraphBuildPipeline",
            state_machine_name="graphrag-build-pipeline",
            definition_body=sfn.DefinitionBody.from_chainable(chain),
            timeout=cdk.Duration.hours(4),
            logs=sfn.LogOptions(
                destination=logs.LogGroup(
                    self, "SfnLogs",
                    retention=logs.RetentionDays.ONE_WEEK,
                ),
                level=sfn.LogLevel.ERROR,
            ),
        )
