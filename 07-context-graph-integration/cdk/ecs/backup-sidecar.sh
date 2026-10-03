#!/bin/bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
#
# Neo4j Backup Sidecar
# Runs alongside Neo4j container, performs periodic backups and final dump on shutdown

set -e

echo "================================================"
echo "Neo4j Backup Sidecar - Starting"
echo "================================================"

# Configuration
BACKUP_INTERVAL_SECONDS=${BACKUP_INTERVAL_SECONDS:-300}  # Default: 5 minutes
S3_BUCKET=${S3_BUCKET:?"S3_BUCKET not set"}
NEO4J_HOST=${NEO4J_HOST:-"localhost"}
NEO4J_USER=${NEO4J_USER:-"neo4j"}
NEO4J_PASSWORD=${NEO4J_PASSWORD:?"NEO4J_PASSWORD not set"}
NEO4J_URI="bolt://${NEO4J_HOST}:7687"

BACKUP_DIR="/tmp/backups"
mkdir -p "$BACKUP_DIR"

# Flag to track if we should keep running
RUNNING=true

# Trap SIGTERM for graceful shutdown with final backup
trap 'echo "Received SIGTERM, performing final backup..."; RUNNING=false' SIGTERM SIGINT

# Function: Wait for Neo4j to be ready
wait_for_neo4j() {
    echo "Waiting for Neo4j to be ready at ${NEO4J_URI}..."
    local max_wait=180
    local waited=0

    while [ $waited -lt $max_wait ]; do
        if cypher-shell -a "$NEO4J_URI" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" \
            "RETURN 1 AS result" &>/dev/null; then
            echo "✅ Neo4j is ready (took ${waited}s)"
            return 0
        fi
        sleep 5
        waited=$((waited + 5))
        echo "  Still waiting... (${waited}s)"
    done

    echo "❌ Neo4j did not become ready within ${max_wait}s"
    return 1
}

# Function: Perform incremental backup using APOC export (works while Neo4j is running)
perform_incremental_backup() {
    local timestamp=$(date +%Y%m%d-%H%M%S)
    local backup_file="${BACKUP_DIR}/neo4j-incremental-${timestamp}.cypher"

    echo ""
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] Starting incremental backup..."

    # Export all data to Cypher statements using APOC
    # This works while Neo4j is running and captures the current state
    if cypher-shell -a "$NEO4J_URI" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" \
        "CALL apoc.export.cypher.all(null, {
            stream: true,
            format: 'cypher-shell',
            useOptimizations: {type: 'UNWIND_BATCH', unwindBatchSize: 20}
        })
        YIELD file, batches, source, format, nodes, relationships, properties, time
        RETURN file, batches, nodes, relationships, properties, time" \
        > "$backup_file" 2>/dev/null; then

        # Upload to S3 with timestamp
        aws s3 cp "$backup_file" "s3://${S3_BUCKET}/incremental-backups/neo4j-${timestamp}.cypher" \
            --quiet --region "${AWS_REGION:-us-east-1}"

        # Also update the "latest" symlink
        aws s3 cp "$backup_file" "s3://${S3_BUCKET}/neo4j-latest.cypher" \
            --quiet --region "${AWS_REGION:-us-east-1}"

        echo "✅ Incremental backup complete: neo4j-${timestamp}.cypher"

        # Cleanup old local backups (keep last 3)
        ls -t ${BACKUP_DIR}/neo4j-incremental-*.cypher 2>/dev/null | tail -n +4 | xargs rm -f 2>/dev/null || true
    else
        echo "⚠️  Incremental backup failed (APOC may not be available), skipping..."
    fi
}

# Function: Perform full dump (requires stopping Neo4j, only on shutdown)
perform_full_dump() {
    echo ""
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] Performing final full dump..."

    local timestamp=$(date +%Y%m%d-%H%M%S)
    local dump_file="${BACKUP_DIR}/neo4j-${timestamp}.dump"

    # Signal Neo4j to shutdown gracefully
    echo "Signaling Neo4j to shutdown..."
    pkill -SIGTERM java || true

    # Wait for Neo4j to stop (max 30 seconds)
    local waited=0
    while pgrep java &>/dev/null && [ $waited -lt 30 ]; do
        sleep 2
        waited=$((waited + 2))
        echo "  Waiting for Neo4j to stop... (${waited}s)"
    done

    if pgrep java &>/dev/null; then
        echo "⚠️  Neo4j did not stop gracefully, forcing kill..."
        pkill -9 java || true
        sleep 2
    fi

    echo "Creating full dump..."
    if neo4j-admin database dump neo4j \
        --to-path="$BACKUP_DIR" \
        --verbose 2>&1; then

        # Rename to include timestamp
        mv "${BACKUP_DIR}/neo4j.dump" "$dump_file" || true

        # Upload full dump to S3
        echo "Uploading full dump to S3..."
        aws s3 cp "$dump_file" "s3://${S3_BUCKET}/neo4j-graph.dump" \
            --region "${AWS_REGION:-us-east-1}"

        # Also keep timestamped version
        aws s3 cp "$dump_file" "s3://${S3_BUCKET}/full-dumps/neo4j-${timestamp}.dump" \
            --region "${AWS_REGION:-us-east-1}"

        echo "✅ Full dump complete and uploaded to S3"
    else
        echo "❌ Full dump failed"
    fi
}

# Wait for Neo4j to be ready before starting backups
if ! wait_for_neo4j; then
    echo "❌ Cannot start backup sidecar - Neo4j is not available"
    exit 1
fi

# Perform initial backup
perform_incremental_backup

# Main backup loop
echo ""
echo "Starting periodic backup loop (interval: ${BACKUP_INTERVAL_SECONDS}s)"
echo "Press Ctrl+C or send SIGTERM to stop and perform final dump"
echo ""

SECONDS_SINCE_BACKUP=0

while $RUNNING; do
    sleep 10
    SECONDS_SINCE_BACKUP=$((SECONDS_SINCE_BACKUP + 10))

    if [ $SECONDS_SINCE_BACKUP -ge $BACKUP_INTERVAL_SECONDS ]; then
        perform_incremental_backup
        SECONDS_SINCE_BACKUP=0
    fi
done

# Perform final full dump on shutdown
perform_full_dump

echo ""
echo "================================================"
echo "Neo4j Backup Sidecar - Stopped"
echo "================================================"
