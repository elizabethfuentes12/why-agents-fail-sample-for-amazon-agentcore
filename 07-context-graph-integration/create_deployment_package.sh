#!/bin/bash
set -e

echo "Creating deployment package for AgentCore Runtime..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_FILES_DIR="${SCRIPT_DIR}/agent_files"
PACKAGE_DIR="${AGENT_FILES_DIR}/deployment_package"
ZIP_FILE="${AGENT_FILES_DIR}/deployment_package.zip"

# Clean up previous build
rm -rf "${PACKAGE_DIR}"
rm -f "${ZIP_FILE}"

# Create package directory
mkdir -p "${PACKAGE_DIR}"

# Install dependencies into package directory
echo "Installing dependencies..."
pip install -q --target "${PACKAGE_DIR}" \
    strands-agents>=1.39.0 \
    bedrock-agentcore>=1.0.0 \
    boto3>=1.35.0

# Copy agent code
echo "Copying agent code..."
cp "${AGENT_FILES_DIR}/context_agent.py" "${PACKAGE_DIR}/"

# Create zip file
echo "Creating zip file..."
cd "${PACKAGE_DIR}"
zip -q -r "${ZIP_FILE}" .
cd "${SCRIPT_DIR}"

# Clean up package directory
rm -rf "${PACKAGE_DIR}"

echo "✅ Deployment package created: ${ZIP_FILE}"
echo "   Size: $(du -h "${ZIP_FILE}" | cut -f1)"
