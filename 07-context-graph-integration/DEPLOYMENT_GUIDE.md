# Deployment Guide - Cost-Optimized Architecture

This guide walks through deploying the **cost-optimized** version of Demo 07, which saves **$35/month (34%)** compared to the original design.

## Cost Savings Summary

| Item | Before | After | Savings |
|------|--------|-------|---------|
| NAT Gateway | $35/month | **$0** | ✅ $35 |
| VPC Endpoints | $0 | $7/month | ❌ -$7 |
| NLB (public → internal) | $16/month | $16/month | - |
| **Net Savings** | - | - | **$28/month** |

---

## Prerequisites

1. **AWS CLI** configured with credentials
2. **Docker** installed and running
3. **CDK** installed: `npm install -g aws-cdk`
4. **jq** installed (for testing scripts): `brew install jq` / `apt install jq`

---

## Step 1: Push Docker Images to ECR

The optimized architecture pulls images from ECR instead of Docker Hub, eliminating the need for a NAT Gateway.

### 1.1 Push Neo4j Image

```bash
cd 07-context-graph-integration
./scripts/push_neo4j_to_ecr.sh
```

**What it does:**
- Creates ECR repository `neo4j-enterprise`
- Pulls `neo4j:2026.01-enterprise-trixie` from Docker Hub
- Pushes to your ECR private registry

**Time:** ~3 minutes (2.1 GB image)

### 1.2 Build and Push Backup Sidecar

```bash
./scripts/push_backup_sidecar_to_ecr.sh
```

**What it does:**
- Builds custom Neo4j image with AWS CLI pre-installed
- Creates ECR repository `neo4j-backup-sidecar`
- Pushes to ECR

**Time:** ~5 minutes (includes apt install)

---

## Step 2: Deploy CDK Stack

```bash
cd cdk

# Activate Python virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Bootstrap CDK (first time only)
cdk bootstrap

# Deploy
cdk deploy
```

**What gets created:**
- VPC (2 AZs, private subnets only)
- VPC Endpoints (ECR, S3, CloudWatch, Secrets Manager)
- ECS Fargate service (Neo4j container + backup sidecar)
- Internal Network Load Balancer
- Lambda functions (seed_data, query_graph)
- S3 bucket for backups
- CloudWatch log groups

**Time:** ~7-10 minutes

---

## Step 3: Verify Deployment

### 3.1 Check Stack Status

```bash
aws cloudformation describe-stacks \
    --stack-name Neo4jContextGraph \
    --region us-east-1 \
    --query 'Stacks[0].StackStatus'
```

Expected: `"CREATE_COMPLETE"` or `"UPDATE_COMPLETE"`

### 3.2 Check ECS Service

```bash
aws ecs describe-services \
    --cluster Neo4jContextGraph-Neo4jCluster-xxxxx \
    --services Neo4jContextGraph-Neo4jService-xxxxx \
    --query 'services[0].runningCount'
```

Expected: `1` (one healthy task)

### 3.3 Check Neo4j Logs

```bash
aws logs tail /ecs/neo4j-context-graph --follow
```

Look for: `"Started."`

---

## Step 4: Seed Sample Data

```bash
cd ..  # Back to demo root
./scripts/seed_data.sh
```

**What it does:**
- Invokes `seed_data` Lambda
- Creates sample POLE+O entities:
  - Person: Sarah Chen (VP of Engineering)
  - Organization: Acme Corp
  - Event: AWS Summit 2026
  - Relationships: WORKS_AT, ATTENDED
  - Messages: 3 conversation turns
  - Preferences: "Interested in Enterprise Tier"

**Expected output:**
```json
{
  "statusCode": 200,
  "body": {
    "message": "Sample data seeded successfully",
    "details": {
      "entities_created": 3,
      "relationships_created": 2,
      "messages_added": 3,
      "user_id": "demo-user-001",
      "session_id": "demo-session-001"
    }
  }
}
```

---

## Step 5: Test Queries

```bash
./scripts/test_query.sh
```

**Test 1: Query entities**
```json
{
  "action": "query_entities",
  "entity_type": "Person",
  "entities": [
    {
      "entity_id": "...",
      "name": "Sarah Chen",
      "entity_type": "Person",
      "role": "VP of Engineering",
      "email": "sarah.chen@acmecorp.com"
    }
  ]
}
```

**Test 2: Search context**
```json
{
  "action": "search_context",
  "result": {
    "query": "Sarah Chen from Acme Corp",
    "context": {
      "messages": [...],
      "entities": [...],
      "preferences": [...]
    }
  }
}
```

---

## Architecture Comparison

### Before: With NAT Gateway ($104/month)

```
┌─────────────────────────────────────────────┐
│ VPC                                         │
│                                             │
│  ┌──────────────┐      ┌─────────────────┐ │
│  │ Private      │─NAT─→│ NAT Gateway     │─┼─→ Internet
│  │ Subnet       │      │ ($35/month)     │ │   (Docker Hub)
│  │              │      └─────────────────┘ │
│  │ ┌──────────┐ │                          │
│  │ │ Fargate  │ │                          │
│  │ │ Neo4j    │←┼─── NLB (public)         │
│  │ └──────────┘ │                          │
│  └──────────────┘                          │
└─────────────────────────────────────────────┘
```

### After: With VPC Endpoints ($69/month)

```
┌─────────────────────────────────────────────┐
│ VPC                                         │
│                                             │
│  ┌──────────────┐      ┌─────────────────┐ │
│  │ Private      │      │ VPC Endpoints   │ │
│  │ Isolated     │─────→│ - ECR           │ │
│  │ Subnet       │      │ - S3            │ │
│  │              │      │ - Secrets       │ │
│  │ ┌──────────┐ │      │ ($7/month)      │ │
│  │ │ Fargate  │ │      └─────────────────┘ │
│  │ │ Neo4j    │←┼─── NLB (internal)       │
│  │ └──────────┘ │                          │
│  └──────────────┘                          │
└─────────────────────────────────────────────┘
```

**Key differences:**
1. ❌ No NAT Gateway → saves $35/month
2. ✅ VPC Endpoints → costs $7/month
3. ✅ Images from ECR (not Docker Hub)
4. ✅ NLB is internal-only (more secure)
5. ✅ No public IP addresses anywhere

---

## Troubleshooting

### Error: ECR repository does not exist

**Cause:** You didn't run the image push scripts before `cdk deploy`.

**Fix:**
```bash
./scripts/push_neo4j_to_ecr.sh
./scripts/push_backup_sidecar_to_ecr.sh
cd cdk && cdk deploy
```

---

### Error: Task fails to start (ResourceInitializationError)

**Cause:** ECR permissions issue or VPC endpoints not configured.

**Fix:**
1. Check ECR permissions in CloudWatch Logs
2. Verify VPC endpoints exist: `aws ec2 describe-vpc-endpoints`
3. Check security groups allow ENI creation

---

### Error: Lambda timeout

**Cause:** Neo4j is not healthy yet, or network connectivity issue.

**Fix:**
1. Wait 2-3 minutes after deployment for Neo4j to fully start
2. Check Neo4j health: `aws logs tail /ecs/neo4j-context-graph`
3. Verify Lambda is in correct VPC/subnet

---

### Neo4j data lost after task restart

**Not a bug!** This is expected behavior:

1. Backup sidecar dumps to S3 every 15 minutes
2. On task restart, downloader restores latest dump
3. Maximum data loss: 15 minutes

**To reduce:**
- Change backup interval in `neo4j_cluster.py` (line 284): `BACKUP_INTERVAL=300` for 5-minute backups

---

## Next Steps

### Phase 2: Deploy AgentCore

```bash
# Deploy AgentCore infrastructure
cd cdk
cdk -a "python3 app_agentcore.py" deploy

# Deploy agent runtime
cd ..
python3 deploy_runtime.py
```

See [SWARM_ARCHITECTURE.md](./SWARM_ARCHITECTURE.md) for details on the multi-agent pattern.

---

## Cost Monitoring

### Track actual costs

```bash
# Get cost for last 7 days
aws ce get-cost-and-usage \
    --time-period Start=2026-05-04,End=2026-05-11 \
    --granularity DAILY \
    --metrics UnblendedCost \
    --filter file://cost-filter.json
```

**cost-filter.json:**
```json
{
  "Tags": {
    "Key": "aws:cloudformation:stack-name",
    "Values": ["Neo4jContextGraph"]
  }
}
```

---

## Cleanup

```bash
# Destroy stack
cd cdk
cdk destroy

# Delete ECR images (optional)
aws ecr batch-delete-image \
    --repository-name neo4j-enterprise \
    --image-ids imageTag=latest

aws ecr batch-delete-image \
    --repository-name neo4j-backup-sidecar \
    --image-ids imageTag=latest
```

**Note:** S3 bucket auto-deletes due to `auto_delete_objects=True` in CDK.

---

## Further Optimization

See [COST_OPTIMIZATION.md](./COST_OPTIMIZATION.md) for additional savings options:
- Fargate Spot: additional $35/month savings (67% total)
- Service Discovery instead of NLB: additional $15/month savings (49% total)
