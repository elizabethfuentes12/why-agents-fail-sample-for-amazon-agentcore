#!/bin/bash
set -e

echo "Building AgentCore Runtime deployment package..."
cd agent_files

# Remove any existing deployment package to start fresh
rm -rf deployment_package deployment_package.zip

# Install Python dependencies for AWS Lambda ARM64 architecture
uv pip install \
  --python-platform aarch64-manylinux2014 \
  --python-version 3.11 \
  --target=deployment_package \
  --only-binary=:all: \
  -r requirements.txt

# Create zip archive from installed dependencies, excluding bytecode files
cd deployment_package && zip -r ../deployment_package.zip . -x "*.pyc" "__pycache__/*"

# Add application source files to the zip
cd .. && zip deployment_package.zip ./*.py requirements.txt

echo "Created: agent_files/deployment_package.zip"
