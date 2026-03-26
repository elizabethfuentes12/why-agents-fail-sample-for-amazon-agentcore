#!/usr/bin/env python3
import os

import aws_cdk as cdk

from stack import HotelBookingAgentStack

app = cdk.App()

# Stack 1: Hotel booking agent (DynamoDB + AgentCore Runtime + Gateway)
HotelBookingAgentStack(app, "HotelBookingAgentStack")

# Stack 2: GraphRAG (Neo4j Fargate + S3 pipeline + query Lambda)
# Only instantiate if explicitly requested to avoid Docker bundling errors
# Deploy with: cdk deploy GraphRAGStack
if app.node.try_get_context("include_graphrag") or os.environ.get("INCLUDE_GRAPHRAG"):
    from graphrag_stack import GraphRAGStack
    GraphRAGStack(app, "GraphRAGStack")

app.synth()
