# Cost Optimization

This demo has been optimized to reduce AWS costs while maintaining functionality and security.

## Original Architecture vs Optimized

### Before: $104/month
- ECS Fargate Standard (2048 CPU, 4096 MB): $50/month
- Network Load Balancer (public): $16/month
- **NAT Gateway: $35/month** ← Eliminated
- CloudWatch Logs + Secrets Manager: $2/month
- S3 storage: ~$1/month

### After (Current): $34/month (67% savings)
- **ECS Fargate Spot (2048 CPU, 4096 MB): $15/month** ← 70% compute savings
- Network Load Balancer (internal): $16/month
- **VPC Endpoints (ECR + CloudWatch + Secrets): $7/month** ← Added
- CloudWatch Logs + Secrets Manager: $2/month
- S3 storage: ~$1/month
- **NAT Gateway: $0** ← Removed

**Monthly savings: $70 (67%)**

**Trade-off:** AWS can interrupt Fargate Spot tasks with 2-minute warning (~0-2 interruptions/month). Backups every 15 minutes mitigate data loss.

---

## What Changed

### 1. Eliminated NAT Gateway ($35/month savings)

**Problem:** Original design used NAT Gateway for:
- Pulling Neo4j image from Docker Hub
- Installing AWS CLI in backup sidecar at runtime

**Solution:**
- Push Neo4j image to **ECR private repository** (one-time setup)
- Build custom backup sidecar with **AWS CLI pre-installed** (no runtime download)
- Add **VPC Endpoints** for ECR, S3, CloudWatch, Secrets Manager (~$7/month)

**Net savings:** $35 - $7 = **$28/month**

### 2. Changed NLB from Public to Internal

**Why:** Neo4j only needs to be accessible from within the VPC:
- Lambda functions in same VPC
- AgentCore will be in same VPC (Phase 2)
- No external access needed

**Benefits:**
- More secure (no internet exposure)
- Same cost ($16/month)

### 3. VPC Endpoints Replace Internet Access

**Endpoints added:**
- `com.amazonaws.us-east-1.ecr.api` - ECR API calls ($7/month)
- `com.amazonaws.us-east-1.ecr.dkr` - Docker image pulls ($7/month)
- `com.amazonaws.us-east-1.s3` - S3 access (Gateway endpoint, **free**)
- `com.amazonaws.us-east-1.logs` - CloudWatch Logs (included in ECR endpoint pricing)
- `com.amazonaws.us-east-1.secretsmanager` - Secrets Manager (included)

**Total VPC endpoint cost:** ~$7/month (interface endpoints are ~$7/month per endpoint for 2 AZs, but S3 gateway is free)

---

## Alternative Configuration: Standard Fargate

The current configuration uses **Fargate Spot** for maximum savings. If you need higher availability:

### Switch to Standard Fargate (+$35/month)

**Change in `neo4j_cluster.py`:**
```python
# Remove capacity_provider_strategies parameter
# CDK will default to standard Fargate
```

**Cost:** $69/month (34% savings vs original)
**Total increase:** +$35/month from current

**Benefits:**
- No interruptions
- 99.99% availability
- Suitable for production critical workloads

**When to use:**
- Customer-facing APIs with strict SLAs
- Zero-tolerance for downtime
- Production systems without backup strategy

---

### Option B: Remove NLB, use Service Discovery (additional $15/month savings from current)

**Change:**
```python
# Replace NLB with Cloud Map
namespace = servicediscovery.PrivateDnsNamespace(
    self, "Neo4jNamespace",
    name="neo4j.local",
    vpc=vpc
)

service.enable_cloud_map(
    name="neo4j-db",
    dns_record_type=servicediscovery.DnsRecordType.A
)

# URI: bolt://neo4j-db.neo4j.local:7687
```

**Cost:** $0.50/month (Cloud Map service)
**Total cost:** $19/month (82% total savings vs original)

**Trade-offs:**
- DNS propagation delay (~60s) when task IP changes
- Combined with Fargate Spot interruptions
- Best for dev/test, not production

---

## Recommended Configurations

### Development/Testing
**Recommendation:** Fargate Spot + NLB internal
**Cost:** $34/month (67% savings)
**Why:** Balances cost with reasonable stability

### Production (Low-traffic)
**Recommendation:** Fargate Standard + NLB internal (current)
**Cost:** $69/month (34% savings)
**Why:** Stable, predictable, secure

### Production (High-availability)
**Recommendation:** Add second Fargate task + ALB health checks
**Cost:** ~$130/month
**Why:** Zero-downtime deployments, automatic failover

---

## Cost Comparison Table

| Configuration | Monthly Cost | Savings | Trade-offs |
|--------------|--------------|---------|------------|
| Original (NAT + public NLB + Fargate Standard) | $104 | 0% | Baseline |
| VPC endpoints + internal NLB + Fargate Standard | $69 | 34% | None |
| **Current (VPC endpoints + internal NLB + Fargate Spot)** | **$34** | **67%** | **Spot interruptions (~2/month)** |
| Maximum (Fargate Spot + Service Discovery) | $19 | 82% | Spot + DNS delays |

---

## Implementation

The optimized configuration is **already implemented** in the CDK code. To deploy:

```bash
# One-time setup: push images to ECR
./scripts/push_neo4j_to_ecr.sh
./scripts/push_backup_sidecar_to_ecr.sh

# Deploy stack
cd cdk
cdk deploy
```

No code changes needed — the optimization is the default.

---

## Why Not Use Neptune or MemoryDB?

**Amazon Neptune:**
- Minimum cost: ~$300/month (db.t3.medium + storage + backups)
- Uses Gremlin or SPARQL (not Cypher)
- neo4j-agent-memory requires Neo4j specifically

**Amazon MemoryDB (Graph preview):**
- Not compatible with Neo4j Cypher queries
- Pricing not yet public (preview)

**Conclusion:** Neo4j on Fargate is the most cost-effective option for this use case.
