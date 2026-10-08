FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim
WORKDIR /app

# Allow slow package downloads inside CodeBuild (avoids the 30s uv timeout).
ENV UV_SYSTEM_PYTHON=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_NO_PROGRESS=1 \
    UV_HTTP_TIMEOUT=120 \
    PYTHONUNBUFFERED=1 \
    DOCKER_CONTAINER=1 \
    AWS_REGION=us-east-1 \
    AWS_DEFAULT_REGION=us-east-1

COPY agent_requirements.txt agent_requirements.txt
# Install all dependencies in one resolved pass (aws-opentelemetry-distro is
# pinned in agent_requirements.txt, so there is no second install step).
RUN uv pip install -r agent_requirements.txt

# Create non-root user
RUN useradd -m -u 1000 bedrock_agentcore
USER bedrock_agentcore

EXPOSE 9000
EXPOSE 8000
EXPOSE 8080

# Copy entire project (respecting .dockerignore)
COPY . .

CMD ["opentelemetry-instrument", "python", "-m", "booking_agent"]
