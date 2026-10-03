FROM public.ecr.aws/docker/library/python:3.11-slim

WORKDIR /app

# Install uv
RUN pip install uv

# Copy only what we need
COPY context_agent.py .
COPY requirements.txt .

# Install dependencies with explicit list
RUN uv pip install --system strands-agents>=1.39.0 bedrock-agentcore>=1.0.0 boto3>=1.35.0

# Set entrypoint
CMD ["python", "-m", "bedrock_agentcore.runtime.container_entrypoint"]
