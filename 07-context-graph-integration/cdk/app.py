#!/usr/bin/env python3
import os
import aws_cdk as cdk
from neo4j_stack.neo4j_context_graph_stack import Neo4jContextGraphStack

app = cdk.App()

Neo4jContextGraphStack(
    app,
    "Neo4jContextGraph",
    description="Neo4j Context Graph on ECS Fargate for AI Agent Memory",
    env=cdk.Environment(
        account=os.getenv('CDK_DEFAULT_ACCOUNT'),
        region=os.getenv('CDK_DEFAULT_REGION')
    )
)

app.synth()
