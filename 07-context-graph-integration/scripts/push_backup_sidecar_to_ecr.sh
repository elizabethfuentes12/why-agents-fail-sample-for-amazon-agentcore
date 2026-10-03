#!/bin/bash
# Build and push backup sidecar image to ECR
# This image has AWS CLI pre-installed to eliminate NAT Gateway dependency

set -e

cd "$(dirname "$0")/../docker/backup-sidecar"

# Configuration
ECR_REPO_NAME="neo4j-backup-sidecar"
AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo "🚀 Building and pushing backup sidecar image to ECR..."
echo "   Account: $AWS_ACCOUNT_ID"
echo "   Region: $AWS_REGION"

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

# Build image
ECR_IMAGE="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_NAME:latest"
echo ""
echo "🔨 Building Docker image..."
docker build -t $ECR_IMAGE .

# Push to ECR
echo ""
echo "⬆️  Pushing to ECR..."
docker push $ECR_IMAGE

echo ""
echo "✅ Backup sidecar image pushed successfully!"
echo ""
echo "📝 Image URI: $ECR_IMAGE"
