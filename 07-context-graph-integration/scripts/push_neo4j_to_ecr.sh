#!/bin/bash
# Push Neo4j Enterprise image to ECR private repository
# This eliminates the need for NAT Gateway to pull from Docker Hub

set -e

# Configuration
NEO4J_VERSION="2026.01-enterprise-trixie"
ECR_REPO_NAME="neo4j-enterprise"
AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo "🚀 Pushing Neo4j image to ECR..."
echo "   Account: $AWS_ACCOUNT_ID"
echo "   Region: $AWS_REGION"
echo "   Neo4j version: $NEO4J_VERSION"

# Create ECR repository if it doesn't exist
echo ""
echo "📦 Creating ECR repository..."
aws ecr describe-repositories --repository-names $ECR_REPO_NAME --region $AWS_REGION 2>/dev/null || \
  aws ecr create-repository \
    --repository-name $ECR_REPO_NAME \
    --region $AWS_REGION \
    --image-scanning-configuration scanOnPush=true \
    --encryption-configuration encryptionType=AES256

# Login to ECR
echo ""
echo "🔐 Logging in to ECR..."
aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

# Pull Neo4j image from Docker Hub
echo ""
echo "⬇️  Pulling Neo4j $NEO4J_VERSION from Docker Hub..."
docker pull neo4j:$NEO4J_VERSION

# Tag for ECR
ECR_IMAGE="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_NAME:$NEO4J_VERSION"
echo ""
echo "🏷️  Tagging image as $ECR_IMAGE"
docker tag neo4j:$NEO4J_VERSION $ECR_IMAGE

# Push to ECR
echo ""
echo "⬆️  Pushing to ECR..."
docker push $ECR_IMAGE

# Tag as latest
echo ""
echo "🏷️  Tagging as latest..."
docker tag neo4j:$NEO4J_VERSION "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_NAME:latest"
docker push "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_NAME:latest"

echo ""
echo "✅ Neo4j image pushed successfully!"
echo ""
echo "📝 Image URI: $ECR_IMAGE"
echo "📝 Latest:    $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_NAME:latest"
echo ""
echo "💡 Update your CDK code to use this image instead of Docker Hub"
