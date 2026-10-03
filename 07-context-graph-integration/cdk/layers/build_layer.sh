#!/bin/bash
set -e

echo "Building neo4j-agent-memory Lambda layer..."

# Clean previous builds
rm -rf neo4j_agent_memory/python

# Create layer directory structure
mkdir -p neo4j_agent_memory/python

# Install dependencies into layer directory
# Using ARM64 architecture to match Lambda runtime
pip install \
    --platform manylinux2014_aarch64 \
    --target neo4j_agent_memory/python \
    --implementation cp \
    --python-version 3.12 \
    --only-binary=:all: \
    --upgrade \
    neo4j-agent-memory

echo "Layer built successfully at neo4j_agent_memory/"
echo "Layer size:"
du -sh neo4j_agent_memory/
