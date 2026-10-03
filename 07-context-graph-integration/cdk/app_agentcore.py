#!/usr/bin/env python3
"""CDK app for AgentCore Context-Aware Agent stack.

This is a separate app from app.py because AgentCore stack depends on
Neo4j stack being deployed first (reads from SSM Parameter Store).

Deploy order:
1. cdk deploy (app.py) → Neo4jContextGraph stack
2. Seed Neo4j data
3. cdk -a "python3 app_agentcore.py" deploy → AgentCoreContext stack
"""

import aws_cdk as cdk
from agentcore_stack import AgentCoreContextStack

app = cdk.App()

import os

AgentCoreContextStack(
    app,
    "AgentCoreContext",
    env=cdk.Environment(
        account=os.getenv('CDK_DEFAULT_ACCOUNT'),
        region=os.getenv('CDK_DEFAULT_REGION', 'us-east-1')
    ),
    description="AgentCore Runtime with context-aware Swarm agent (Phase 2)"
)

app.synth()
