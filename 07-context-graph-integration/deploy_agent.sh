#!/bin/bash
# Deploy context-aware agent to AgentCore Runtime
#
# Prerequisites:
# 1. Neo4jContextGraph stack deployed (cdk deploy)
# 2. AgentCoreContext stack deployed (cdk -a "python3 app_agentcore.py" deploy)
# 3. Neo4j seeded with sample data (aws lambda invoke ...)

set -e

echo "================================================"
echo "Deploying Context-Aware Agent to AgentCore"
echo "================================================"

# Get stack outputs
echo ""
echo "📦 Getting stack outputs..."
CONVERSATION_TABLE=$(aws cloudformation describe-stacks \
    --stack-name AgentCoreContext \
    --query 'Stacks[0].Outputs[?OutputKey==`ConversationTableName`].OutputValue' \
    --output text)

AGENT_STATE_TABLE=$(aws cloudformation describe-stacks \
    --stack-name AgentCoreContext \
    --query 'Stacks[0].Outputs[?OutputKey==`AgentStateTableName`].OutputValue' \
    --output text)

NEO4J_URI=$(aws cloudformation describe-stacks \
    --stack-name AgentCoreContext \
    --query 'Stacks[0].Outputs[?OutputKey==`Neo4jUri`].OutputValue' \
    --output text)

NEO4J_SECRET_ARN=$(aws cloudformation describe-stacks \
    --stack-name AgentCoreContext \
    --query 'Stacks[0].Outputs[?OutputKey==`Neo4jSecretArn`].OutputValue' \
    --output text)

RUNTIME_ROLE_ARN=$(aws cloudformation describe-stacks \
    --stack-name AgentCoreContext \
    --query 'Stacks[0].Outputs[?OutputKey==`RuntimeRoleArn`].OutputValue' \
    --output text)

echo "✅ Conversation Table: $CONVERSATION_TABLE"
echo "✅ Agent State Table: $AGENT_STATE_TABLE"
echo "✅ Neo4j URI: $NEO4J_URI"
echo "✅ Runtime Role: $RUNTIME_ROLE_ARN"

# Create deployment package
echo ""
echo "📦 Creating deployment package..."
DEPLOY_DIR="agent_deployment"
rm -rf "$DEPLOY_DIR"
mkdir -p "$DEPLOY_DIR"

# Copy agent files
cp -r agent_files/* "$DEPLOY_DIR/"

# Install dependencies
echo "Installing dependencies..."
cd "$DEPLOY_DIR"

# Install from requirements.txt
pip install -t . \
    -r requirements.txt \
    --platform manylinux2014_x86_64 \
    --only-binary=:all: \
    --python-version 3.12 \
    --upgrade

# Verify critical packages
echo ""
echo "Verifying installed packages..."
python3 -c "import strands; print(f'✅ strands-agents: {strands.__version__}')" 2>/dev/null || echo "⚠️  strands-agents not found"
python3 -c "import neo4j_agent_memory; print('✅ neo4j-agent-memory installed')" 2>/dev/null || echo "⚠️  neo4j-agent-memory not found"
python3 -c "import neo4j; print('✅ neo4j driver installed')" 2>/dev/null || echo "⚠️  neo4j driver not found"
echo ""

# Create updated agent_config.json with actual values
cat > agent_config.json <<EOF
{
  "name": "context-aware-agent",
  "description": "Context-aware agent with three-memory architecture using Neo4j and Strands Swarm",
  "version": "1.0.0",
  "agent_file": "context_agent.py",
  "agent_function": "get_agent",
  "memory": {
    "mode": "STM_AND_LTM",
    "config": {
      "short_term": {
        "type": "dynamodb",
        "table_name": "$CONVERSATION_TABLE"
      },
      "long_term": {
        "type": "neo4j",
        "uri": "$NEO4J_URI",
        "user": "neo4j",
        "password_secret_arn": "$NEO4J_SECRET_ARN"
      }
    }
  },
  "environment": {
    "NEO4J_URI": "$NEO4J_URI",
    "NEO4J_USER": "neo4j",
    "NEO4J_PASSWORD_SECRET_ARN": "$NEO4J_SECRET_ARN",
    "AWS_REGION": "\${AWS_REGION:-\$(aws configure get region)}",
    "CONVERSATION_TABLE": "$CONVERSATION_TABLE",
    "AGENT_STATE_TABLE": "$AGENT_STATE_TABLE"
  }
}
EOF

# Create ZIP file
echo "Creating ZIP archive..."
zip -r ../context-agent.zip . -x "*.pyc" -x "__pycache__/*" -x ".DS_Store"
cd ..

echo ""
echo "✅ Deployment package created: context-agent.zip"
echo ""
echo "================================================"
echo "Next Steps (Manual - AgentCore API not yet in CDK):"
echo "================================================"
echo ""
echo "1. Upload agent package to S3:"
echo "   aws s3 cp context-agent.zip s3://YOUR-BUCKET/agents/"
echo ""
REGION="\${AWS_REGION:-\$(aws configure get region)}"

echo "2. Create AgentCore Runtime:"
echo "   aws bedrock-agentcore create-agent-runtime \\"
echo "     --agent-name context-aware-agent \\"
echo "     --runtime-config '{\"s3Location\": \"s3://YOUR-BUCKET/agents/context-agent.zip\"}' \\"
echo "     --execution-role-arn $RUNTIME_ROLE_ARN \\"
echo "     --region \$REGION"
echo ""
echo "3. Create AgentCore Gateway:"
echo "   aws bedrock-agentcore create-agent-gateway \\"
echo "     --agent-runtime-arn <RUNTIME_ARN> \\"
echo "     --region \$REGION"
echo ""
echo "4. Test the agent:"
echo "   aws bedrock-agentcore invoke-agent-runtime \\"
echo "     --agent-runtime-arn <RUNTIME_ARN> \\"
echo "     --payload '\$(echo '{\"prompt\": \"I met Sarah Chen from Acme Corp\"}' | base64)' \\"
echo "     --region \$REGION /tmp/response.json"
echo ""
