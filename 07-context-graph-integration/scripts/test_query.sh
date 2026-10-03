#!/bin/bash
# Test querying the Neo4j context graph via Lambda

set -e

AWS_REGION="${AWS_REGION:-us-east-1}"

# Get Lambda function ARN from CloudFormation outputs
FUNCTION_ARN=$(aws cloudformation describe-stacks \
    --stack-name Neo4jContextGraph \
    --region $AWS_REGION \
    --query 'Stacks[0].Outputs[?OutputKey==`QueryGraphFunctionArn`].OutputValue' \
    --output text)

if [ -z "$FUNCTION_ARN" ]; then
    echo "❌ Could not find QueryGraphFunctionArn output from stack"
    exit 1
fi

FUNCTION_NAME=$(echo $FUNCTION_ARN | cut -d: -f7)

echo "🔍 Querying Neo4j context graph..."
echo "   Lambda: $FUNCTION_NAME"
echo ""

# Test 1: Query all Person entities
echo "📋 Test 1: Query all Person entities"
aws lambda invoke \
    --function-name $FUNCTION_NAME \
    --region $AWS_REGION \
    --payload '{"action":"query_entities","entity_type":"Person","actor_id":"demo-user-001"}' \
    --cli-binary-format raw-in-base64-out \
    /tmp/query_response.json

echo ""
cat /tmp/query_response.json | jq '.body | fromjson | .entities'
echo ""

# Test 2: Search context
echo "📋 Test 2: Search context for 'Sarah Chen'"
aws lambda invoke \
    --function-name $FUNCTION_NAME \
    --region $AWS_REGION \
    --payload '{"action":"search_context","query":"Sarah Chen from Acme Corp","actor_id":"demo-user-001"}' \
    --cli-binary-format raw-in-base64-out \
    /tmp/search_response.json

echo ""
cat /tmp/search_response.json | jq '.body | fromjson | .result'
echo ""

echo "✅ Query tests complete!"

rm /tmp/query_response.json /tmp/search_response.json
