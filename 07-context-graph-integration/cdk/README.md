# Neo4j Context Graph on AWS - CDK Stack

AWS CDK stack for deploying Neo4j database on ECS Fargate with Lambda functions for data seeding and querying using [neo4j-agent-memory](https://github.com/neo4j-labs/agent-memory).

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Neo4jContextGraphStack                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌────────────────────────────────────────────────────┐   │
│  │  Neo4jCluster (ECS Fargate)                        │   │
│  │  - VPC with public + private subnets               │   │
│  │  - Network Load Balancer (stable endpoint)         │   │
│  │  - Neo4j 5.26 Enterprise on Fargate               │   │
│  │  - Security Group (Bolt port 7687)                │   │
│  │  - Secrets Manager (password storage)             │   │
│  │  - CloudWatch Logs                                 │   │
│  └────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌────────────────────────────────────────────────────┐   │
│  │  ProjectLambdas                                     │   │
│  │  - seed_data: Populate sample POLE+O data         │   │
│  │  - query_graph: Query context graph               │   │
│  │  - Layer: neo4j-agent-memory + dependencies       │   │
│  └────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌────────────────────────────────────────────────────┐   │
│  │  SSM Parameters (for cross-stack references)       │   │
│  │  - /neo4j/context-graph/uri                        │   │
│  │  - /neo4j/context-graph/secret-arn                 │   │
│  │  - /neo4j/context-graph/vpc-id                     │   │
│  │  - /neo4j/context-graph/security-group-id         │   │
│  └────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Prerequisites

- Python 3.12+
- AWS CLI configured with credentials
- AWS CDK Toolkit: `npm install -g aws-cdk`
- Docker (for building Lambda layer)

## Quick Start

### 1. Install Dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Build Lambda Layer

The Lambda layer contains `neo4j-agent-memory` and its dependencies:

```bash
cd layers
./build_layer.sh
cd ..
```

This creates `layers/neo4j_agent_memory/python/` with all dependencies installed for ARM64 Lambda runtime.

### 3. Bootstrap CDK (First Time Only)

```bash
cdk bootstrap
```

### 4. Deploy Stack

```bash
cdk deploy
```

Review the resources that will be created and confirm when prompted.

**Deployment time:** ~5-7 minutes (ECS service takes longest to stabilize)

### 5. Get Connection Details

After deployment completes, note the stack outputs:

```
Outputs:
Neo4jContextGraph.Neo4jBoltUri = bolt://Neo4jC-Neo4j-XXXXX.elb.us-east-1.amazonaws.com:7687
Neo4jContextGraph.Neo4jPasswordSecretArn = arn:aws:secretsmanager:us-east-1:...
Neo4jContextGraph.SeedDataFunctionName = Neo4jContextGraph-LambdasSeedData-XXXXX
```

### 6. Retrieve Neo4j Password

```bash
aws secretsmanager get-secret-value \
    --secret-id <Neo4jPasswordSecretArn> \
    --query SecretString \
    --output text
```

### 7. Seed Sample Data

Invoke the seed Lambda to populate Neo4j with sample POLE+O entities:

```bash
aws lambda invoke \
    --function-name <SeedDataFunctionName> \
    --payload '{}' \
    response.json

cat response.json
```

Expected output:
```json
{
  "statusCode": 200,
  "body": "{\"message\": \"Sample data seeded successfully\", \"details\": {\"entities_created\": 3, \"relationships_created\": 2, \"messages_added\": 3}}"
}
```

### 8. Test Neo4j Connection

Using the Neo4j Browser (requires port forwarding or VPN):

```cypher
// List all entities
MATCH (n) RETURN n LIMIT 25;

// Find Person entities
MATCH (p:Person) RETURN p;

// Find relationships
MATCH (p:Person)-[r:WORKS_AT]->(o:Organization)
RETURN p.name, o.name;
```

Or use the query Lambda:

```bash
aws lambda invoke \
    --function-name <QueryGraphFunctionName> \
    --payload '{"action": "query_entities", "entity_type": "Person", "actor_id": "demo-user-001"}' \
    response.json

cat response.json
```

## Stack Components

### Neo4jCluster (ECS Construct)

- **VPC:** 2 AZs with public and private subnets
- **NAT Gateway:** 1 (for pulling Docker images)
- **ECS Cluster:** Fargate-based, container insights enabled
- **Task Definition:** 2048 CPU, 4096 MB memory
- **Neo4j Container:** 
  - Image: `neo4j:5.26-enterprise`
  - Port: 7687 (Bolt)
  - Health check: Cypher shell query
  - Logs: CloudWatch `/ecs/neo4j-context-graph`
- **Network Load Balancer:** Internet-facing, TCP port 7687
- **Security Group:** Allows inbound Bolt traffic from anywhere

### ProjectLambdas

#### seed_data Lambda
- **Purpose:** Populate Neo4j with sample context graph data
- **Runtime:** Python 3.12, ARM64
- **Timeout:** 900 seconds
- **Memory:** 512 MB (default)
- **Layer:** neo4j-agent-memory
- **Sample data:**
  - 3 entities (Person, Organization, Event)
  - 2 relationships (WORKS_AT, ATTENDED)
  - 3 conversation messages
  - 1 reasoning trace

#### query_graph Lambda
- **Purpose:** Query entities and search context
- **Actions:**
  - `query_entities`: List entities by type
  - `search_context`: Semantic search across messages + entities
- **Runtime:** Python 3.12, ARM64
- **Timeout:** 900 seconds
- **Layer:** neo4j-agent-memory

## SSM Parameters

Stack outputs are stored in Parameter Store for cross-stack references:

| Parameter | Value |
|-----------|-------|
| `/neo4j/context-graph/uri` | Bolt connection URI |
| `/neo4j/context-graph/secret-arn` | Secrets Manager ARN for password |
| `/neo4j/context-graph/vpc-id` | VPC ID |
| `/neo4j/context-graph/security-group-id` | Security Group ID |

**Usage in other stacks:**

```python
neo4j_uri = ssm.StringParameter.value_from_lookup(
    self, "/neo4j/context-graph/uri"
)
```

## Cost Estimate

Based on us-east-1 pricing (as of January 2026):

| Resource | Configuration | Monthly Cost |
|----------|--------------|--------------|
| ECS Fargate | 2048 CPU, 4096 MB, 24/7 | ~$50 |
| Network Load Balancer | 1 NLB | ~$16 |
| NAT Gateway | 1 NAT + data transfer | ~$35 |
| CloudWatch Logs | 1 GB retention | ~$1 |
| Secrets Manager | 1 secret | ~$0.40 |
| Lambda (occasional) | Seed + query invocations | <$1 |
| **Total** | | **~$103/month** |

**Cost optimization:**
- Use EC2 instance instead of Fargate: saves ~$35/month
- Remove NAT Gateway, use VPC endpoints: saves ~$32/month
- Deploy Neo4j in private subnet only: saves ~$16/month (NLB)

## Development

### Run Tests

```bash
pytest tests/ -v
```

### Update Lambda Layer

When neo4j-agent-memory releases a new version:

```bash
cd layers
./build_layer.sh
cd ..
cdk deploy
```

### View Logs

```bash
# Neo4j container logs
aws logs tail /ecs/neo4j-context-graph --follow

# Seed Lambda logs
aws logs tail /aws/lambda/<SeedDataFunctionName> --follow
```

### Clean Up

**⚠️ Warning:** This destroys all data in Neo4j.

```bash
cdk destroy
```

Confirm when prompted. Cleanup takes ~3-5 minutes.

## Next Steps

After deploying this stack:

1. **AgentCore Integration:** Deploy the AgentCore stack that references these SSM parameters
2. **Custom Data:** Modify `seed_data` Lambda to load your own domain data
3. **Monitoring:** Add CloudWatch alarms for ECS task health and NLB target health
4. **Backups:** Configure automated graph dumps to S3

## Troubleshooting

### Neo4j container fails to start

Check logs:
```bash
aws logs tail /ecs/neo4j-context-graph --follow
```

Common issues:
- Memory limit too low (increase to 8192 MB)
- Health check timeout (increase `start_period`)

### Lambda timeout connecting to Neo4j

- Check security group rules allow Lambda → Neo4j
- Verify Lambda is in VPC with NAT Gateway

### "Unable to pull image" error

- NAT Gateway missing or misconfigured
- Check ECS task execution role has ECR permissions

## References

- [neo4j-agent-memory](https://github.com/neo4j-labs/agent-memory)
- [AWS CDK Python Reference](https://docs.aws.amazon.com/cdk/api/v2/python/)
- [Neo4j on AWS](https://neo4j.com/cloud/)
