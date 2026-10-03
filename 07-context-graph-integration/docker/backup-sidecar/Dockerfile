# Custom Neo4j image with AWS CLI pre-installed for backup sidecar
# This eliminates the need for NAT Gateway during runtime

FROM neo4j:2026.01-enterprise-trixie

USER root

# Install AWS CLI v2 and dependencies
RUN apt-get update && \
    apt-get install -y curl unzip procps && \
    curl -s "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip && \
    unzip -q /tmp/awscliv2.zip -d /tmp && \
    /tmp/aws/install && \
    rm -rf /tmp/awscliv2.zip /tmp/aws && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Verify AWS CLI installation
RUN aws --version

# Keep neo4j user as default
USER neo4j

# Default command (will be overridden by ECS task definition)
CMD ["neo4j", "console"]
