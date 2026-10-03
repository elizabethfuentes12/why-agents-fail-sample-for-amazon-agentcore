#!/bin/bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

set -e

echo "================================================"
echo "Neo4j Context Graph - Backup to S3"
echo "================================================"

# Get region from environment or AWS config
REGION="${AWS_REGION:-$(aws configure get region)}"
echo "Using region: $REGION"

# Get stack outputs
echo "Getting stack outputs..."
DUMP_BUCKET=$(aws cloudformation describe-stacks \
    --stack-name Neo4jContextGraph \
    --query 'Stacks[0].Outputs[?OutputKey==`DumpBucketName`].OutputValue' \
    --output text --region "$REGION")

NEO4J_URI=$(aws ssm get-parameter \
    --name /neo4j/context-graph/uri \
    --query 'Parameter.Value' \
    --output text --region "$REGION")

NEO4J_SECRET_ARN=$(aws ssm get-parameter \
    --name /neo4j/context-graph/secret-arn \
    --query 'Parameter.Value' \
    --output text --region "$REGION")

echo "Dump bucket: $DUMP_BUCKET"
echo "Neo4j URI: $NEO4J_URI"

# Get Neo4j password from Secrets Manager
echo "Getting Neo4j password..."
NEO4J_PASSWORD=$(aws secretsmanager get-secret-value \
    --secret-id "$NEO4J_SECRET_ARN" \
    --query 'SecretString' \
    --output text --region "$REGION")

# Create local dump using neo4j-admin dump (requires neo4j-admin in PATH)
# This creates a backup without stopping the database
echo ""
echo "Creating dump..."
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
DUMP_FILE="/tmp/neo4j-${TIMESTAMP}.dump"

# Option 1: If neo4j-admin is available locally
if command -v neo4j-admin &> /dev/null; then
    neo4j-admin database dump neo4j \
        --to-path=/tmp \
        --database=neo4j \
        --verbose

    mv /tmp/neo4j.dump "$DUMP_FILE"
else
    echo "⚠️  neo4j-admin not found locally"
    echo "Using cypher-shell to export data instead..."

    # Extract host from URI (bolt://hostname:7687 -> hostname)
    NEO4J_HOST=$(echo "$NEO4J_URI" | sed 's|bolt://||' | sed 's|:7687||')

    # Export using cypher-shell (less efficient but works remotely)
    cypher-shell -a "$NEO4J_URI" -u neo4j -p "$NEO4J_PASSWORD" \
        "CALL apoc.export.json.all(null, {stream: true, useTypes: true})" \
        > "$DUMP_FILE"
fi

# Upload to S3
echo ""
echo "Uploading dump to s3://${DUMP_BUCKET}/neo4j-graph.dump"
aws s3 cp "$DUMP_FILE" "s3://${DUMP_BUCKET}/neo4j-graph.dump" --region "$REGION"

# Also keep timestamped version
aws s3 cp "$DUMP_FILE" "s3://${DUMP_BUCKET}/backups/neo4j-${TIMESTAMP}.dump" --region "$REGION"

# Cleanup
rm "$DUMP_FILE"

echo ""
echo "✅ Backup complete!"
echo ""
echo "To restore from this backup:"
echo "  1. Delete the current ECS task (it will restart)"
echo "  2. The new task will automatically load from s3://${DUMP_BUCKET}/neo4j-graph.dump"
echo ""
echo "================================================"
