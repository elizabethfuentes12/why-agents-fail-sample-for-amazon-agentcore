#!/bin/bash
# Invoke seed_data Lambda to populate Neo4j with sample POLE+O data

set -e

AWS_REGION="${AWS_REGION:-us-east-1}"

# Get Lambda function name from CloudFormation outputs
FUNCTION_NAME=$(aws cloudformation describe-stacks \
    --stack-name Neo4jContextGraph \
    --region $AWS_REGION \
    --query 'Stacks[0].Outputs[?OutputKey==`SeedDataFunctionName`].OutputValue' \
    --output text)

if [ -z "$FUNCTION_NAME" ]; then
    echo "❌ Could not find SeedDataFunctionName output from stack"
    exit 1
fi

echo "🌱 Seeding Neo4j with sample data..."
echo "   Lambda: $FUNCTION_NAME"
echo ""

# Invoke Lambda
aws lambda invoke \
    --function-name $FUNCTION_NAME \
    --region $AWS_REGION \
    --payload '{}' \
    --cli-binary-format raw-in-base64-out \
    /tmp/seed_response.json

echo ""
echo "📄 Response:"
cat /tmp/seed_response.json | jq .
echo ""

# Check if successful
STATUS=$(cat /tmp/seed_response.json | jq -r '.statusCode')
if [ "$STATUS" = "200" ]; then
    echo "✅ Data seeded successfully!"
    echo ""
    echo "   Sample data created:"
    cat /tmp/seed_response.json | jq -r '.body' | jq .
else
    echo "❌ Seeding failed!"
    cat /tmp/seed_response.json | jq .
    exit 1
fi

rm /tmp/seed_response.json
