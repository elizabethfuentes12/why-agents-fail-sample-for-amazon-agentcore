#!/bin/bash
# Complete deployment script for Demo 07: Context Graph Integration
# This script handles ECR image push and CDK deployment

set -e

echo "🚀 Demo 07: Context Graph Integration - Full Deployment"
echo "=========================================================="
echo ""

# Check prerequisites
echo "✅ Checking prerequisites..."

if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

if ! command -v aws &> /dev/null; then
    echo "❌ AWS CLI is not installed. Please install AWS CLI first."
    exit 1
fi

if ! command -v cdk &> /dev/null; then
    echo "❌ CDK is not installed. Please run: npm install -g aws-cdk"
    exit 1
fi

# Get AWS account and region
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export AWS_REGION="${AWS_REGION:-us-east-1}"
export CDK_DEFAULT_ACCOUNT=$AWS_ACCOUNT_ID
export CDK_DEFAULT_REGION=$AWS_REGION

echo "   AWS Account: $AWS_ACCOUNT_ID"
echo "   AWS Region: $AWS_REGION"
echo ""

# Step 1: Push Neo4j image to ECR
echo "📦 Step 1/4: Pushing Neo4j image to ECR..."
echo "   This eliminates the need for NAT Gateway ($35/month savings)"
echo ""
./scripts/push_neo4j_to_ecr.sh

# Step 2: Build and push backup sidecar image
echo ""
echo "📦 Step 2/4: Building and pushing backup sidecar image..."
echo "   This image has AWS CLI pre-installed"
echo ""
./scripts/push_backup_sidecar_to_ecr.sh

# Step 3: CDK Bootstrap (if needed)
echo ""
echo "🏗️  Step 3/4: CDK Bootstrap (if needed)..."
cd cdk
if ! aws cloudformation describe-stacks --stack-name CDKToolkit --region $AWS_REGION &>/dev/null; then
    echo "   Bootstrapping CDK..."
    cdk bootstrap
else
    echo "   CDK already bootstrapped ✓"
fi

# Step 4: CDK Deploy
echo ""
echo "🚀 Step 4/4: Deploying CDK stack..."
echo "   Estimated time: 7-10 minutes"
echo "   Cost: ~$34/month (vs $104/month original)"
echo ""
echo "   Stack includes:"
echo "   - Neo4j on ECS Fargate Spot (70% compute savings)"
echo "   - VPC endpoints (no NAT Gateway)"
echo "   - Internal NLB (VPC-only access)"
echo "   - Lambda functions for data operations"
echo "   - S3 backup automation (every 15 minutes)"
echo ""
echo "   ⚠️  Using Fargate Spot: AWS can interrupt with 2-min warning"
echo "   ✅ Backups every 15min mitigate data loss"
echo ""

cdk deploy --require-approval never

# Get outputs
echo ""
echo "✅ Deployment complete!"
echo ""
echo "📋 Stack Outputs:"
aws cloudformation describe-stacks \
    --stack-name Neo4jContextGraph \
    --region $AWS_REGION \
    --query 'Stacks[0].Outputs[*].[OutputKey,OutputValue]' \
    --output table

echo ""
echo "🎯 Next Steps:"
echo "   1. Seed data: ./scripts/seed_data.sh"
echo "   2. Test query: ./scripts/test_query.sh"
echo "   3. Deploy AgentCore: cd cdk && cdk -a 'python3 app_agentcore.py' deploy"
echo ""
echo "💰 Cost Savings:"
echo "   - Original:         $104/month"
echo "   - VPC endpoints:    $69/month (34% savings)"
echo "   - + Fargate Spot:   $34/month (67% savings)"
echo "   - Total savings:    $70/month"
echo ""
