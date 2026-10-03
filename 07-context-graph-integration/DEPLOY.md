# Deploy Instructions - Demo 07

## Current Status

✅ **Lambda layer built successfully:**
- Location: `cdk/layers/neo4j_agent_memory/`
- Size: 19MB (compressed will be ~5-7MB)
- Architecture: ARM64 (manylinux_2_17_aarch64)
- Compatible with Lambda Python 3.12 ARM64

✅ **CDK stack validated:**
- `cdk synth` executed successfully
- CloudFormation template generated without errors
- Normal warnings (containerInsights deprecated, etc.)

⏳ **Pending: AWS deployment**

---

## Prerequisites

### 1. Configure AWS Credentials

```bash
# Option 1: AWS CLI configure
aws configure

# Option 2: Environment variables
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_DEFAULT_REGION="us-east-1"

# Option 3: AWS SSO
aws sso login --profile <profile-name>
export AWS_PROFILE=<profile-name>
```

### 2. Verify credentials

```bash
aws sts get-caller-identity
```

Should display your Account ID and ARN.

---

## Deployment

### Step 1: Bootstrap CDK (first time only)

```bash
cd cdk
source .venv/bin/activate
cdk bootstrap
```

### Step 2: Deploy Stack

```bash
# Suppress Node.js warning
export JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION=1

# Deploy (takes ~7-10 minutes)
cdk deploy
```

**Estimated time per resource:**
- VPC + Subnets + NAT Gateway: ~2 min
- ECS Cluster: ~30 sec
- Network Load Balancer: ~3 min
- Secrets Manager: ~10 sec
- Lambda functions: ~30 sec
- ECS Task + Service: ~3-5 min (waiting for health checks)

**Total: ~7-10 minutes**

### Step 3: Save Outputs

Deployment will show important outputs:

```
Outputs:
Neo4jContextGraph.Neo4jBoltUri = bolt://Neo4jC-Neo4j-ABC123.elb.us-east-1.amazonaws.com:7687
Neo4jContextGraph.Neo4jPasswordSecretArn = arn:aws:secretsmanager:us-east-1:123456789012:secret:...
Neo4jContextGraph.SeedDataFunctionName = Neo4jContextGraph-LambdasSeedData-ABC123
Neo4jContextGraph.QueryGraphFunctionArn = arn:aws:lambda:us-east-1:123456789012:function:...
Neo4jContextGraph.NLBDnsName = Neo4jC-Neo4j-ABC123.elb.us-east-1.amazonaws.com
```

**Save to a file:**
```bash
aws cloudformation describe-stacks \
  --stack-name Neo4jContextGraph \
  --query 'Stacks[0].Outputs' > outputs.json
```

---

## Post-Deployment: Verification

### 1. Verify ECS Service is running

```bash
aws ecs describe-services \
  --cluster Neo4jContextGraph-Neo4jClusterNeo4jCluster \
  --services Neo4jContextGraph-Neo4jClusterNeo4jService \
  --query 'services[0].{desiredCount:desiredCount,runningCount:runningCount,status:status}'
```

Should show `runningCount: 1`, `status: ACTIVE`.

### 2. View Neo4j logs

```bash
aws logs tail /ecs/neo4j-context-graph --follow
```

Look for:
- `Remote interface available at http://localhost:7474/`
- `Bolt enabled on bolt://0.0.0.0:7687`
- `Started.`

### 3. Get Neo4j password

```bash
NEO4J_SECRET_ARN=$(aws cloudformation describe-stacks \
  --stack-name Neo4jContextGraph \
  --query 'Stacks[0].Outputs[?OutputKey==`Neo4jPasswordSecretArn`].OutputValue' \
  --output text)

aws secretsmanager get-secret-value \
  --secret-id $NEO4J_SECRET_ARN \
  --query SecretString \
  --output text
```

### 4. Seed Sample Data

```bash
SEED_FUNCTION=$(aws cloudformation describe-stacks \
  --stack-name Neo4jContextGraph \
  --query 'Stacks[0].Outputs[?OutputKey==`SeedDataFunctionName`].OutputValue' \
  --output text)

aws lambda invoke \
  --function-name $SEED_FUNCTION \
  --payload '{}' \
  response.json

cat response.json
```

**Expected output:**
```json
{
  "statusCode": 200,
  "body": "{\"message\": \"Sample data seeded successfully\", \"details\": {\"entities_created\": 3, \"relationships_created\": 2, \"messages_added\": 3, \"user_id\": \"demo-user-001\", \"session_id\": \"demo-session-001\"}}"
}
```

### 5. Query Graph

```bash
QUERY_FUNCTION=$(aws cloudformation describe-stacks \
  --stack-name Neo4jContextGraph \
  --query 'Stacks[0].Outputs[?OutputKey==`QueryGraphFunctionArn`].OutputValue' \
  --output text | cut -d: -f7)

aws lambda invoke \
  --function-name $QUERY_FUNCTION \
  --payload '{"action": "query_entities", "entity_type": "Person", "actor_id": "demo-user-001"}' \
  response.json

cat response.json
```

**Expected output:**
```json
{
  "statusCode": 200,
  "body": "{\"action\": \"query_entities\", \"entity_type\": \"Person\", \"actor_id\": \"demo-user-001\", \"entities\": [{\"name\": \"Sarah Chen\", \"role\": \"VP of Engineering\", \"email\": \"sarah.chen@acmecorp.com\"}]}"
}
```

---

## Troubleshooting

### Error: "Unable to locate credentials"

```bash
# Verify
aws sts get-caller-identity

# If fails, configure credentials
aws configure
```

### Error: "Stack already exists"

If you need to redeploy:
```bash
cdk deploy --force
```

### Error: ECS task not starting

```bash
# View logs
aws logs tail /ecs/neo4j-context-graph --follow

# View service events
aws ecs describe-services \
  --cluster Neo4jContextGraph-Neo4jClusterNeo4jCluster \
  --services Neo4jContextGraph-Neo4jClusterNeo4jService \
  --query 'services[0].events[:5]'
```

Common causes:
- Insufficient memory (increase to 8192 MB if fails)
- Health check timeout (Neo4j takes ~60s to start)
- Cannot pull image (check NAT Gateway)

### Lambda timeout connecting to Neo4j

If seed Lambda fails with timeout:

```bash
# View logs
aws logs tail /aws/lambda/Neo4jContextGraph-LambdasSeedData --follow
```

Common causes:
- Neo4j not ready yet (wait 2-3 min after deploy)
- Security Group blocking connection (verify Lambda can access Neo4j)
- VPC without NAT Gateway (Lambda cannot resolve DNS)

---

## Cleanup

⚠️ **WARNING:** This destroys all data in Neo4j.

```bash
cd cdk
source .venv/bin/activate
cdk destroy
```

Confirm when prompted.

---

## Next Steps (After Verification)

1. ✅ **Update README.md** with deployment results
2. ✅ **Create memory** with lessons learned
3. ✅ **Document outputs** for Phase 2 (AgentCore integration)
4. ⏳ **Phase 2:** Deploy AgentCore Runtime stack

---

## File Structure (Everything Ready)

```
07-context-graph-integration/
├── DEPLOY.md                        # ← This file
├── CLAUDE.md                        # ← Project documentation
├── README.md                        # ← Updated overview
├── requirements.txt                 # ← neo4j-agent-memory[all]
├── test_neo4j_agent_memory.ipynb   # ← Test notebook (for later)
│
├── cdk/
│   ├── .venv/                       # ✅ Virtual env created
│   ├── app.py                       # ✅ CDK app
│   ├── requirements.txt             # ✅ CDK 2.170.0
│   ├── cdk.json                     # ✅ Context flags
│   │
│   ├── neo4j_stack/                 # ✅ Main stack
│   ├── ecs/                         # ✅ Neo4j cluster construct
│   ├── lambdas/                     # ✅ Lambda constructs + code
│   │
│   └── layers/
│       ├── build_layer.sh           # ✅ Build script
│       └── neo4j_agent_memory/      # ✅ Layer built (19MB)
│           └── python/              # ✅ ARM64 dependencies
│
└── docs/
    ├── INTEGRATION_PLAN.md          # ✅ Full integration plan
    ├── CORRECTED_ARCHITECTURE.md    # ✅ Architecture details
    ├── OBSERVABILITY.md             # ✅ Monitoring guide
    └── WHEN_TO_USE_NEO4J.md        # ✅ Decision framework
```

**Status: READY TO DEPLOY** 🚀

Just need to configure AWS credentials and run `cdk deploy`.
