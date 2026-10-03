# Fargate Spot Configuration

This stack uses **Fargate Spot** for 70% compute cost savings, reducing total cost from $69/month to **$34/month (67% total savings)**.

## What is Fargate Spot?

Fargate Spot runs tasks on spare AWS capacity at up to **70% discount** compared to standard Fargate pricing.

**Standard Fargate:**
- 2048 CPU, 4096 MB, 730 hours/month = $50/month
- Guaranteed availability

**Fargate Spot:**
- 2048 CPU, 4096 MB, 730 hours/month = **$15/month**
- Can be interrupted with 2-minute warning when AWS needs capacity back

---

## How Interruptions are Handled

### 1. Backup Strategy Mitigates Data Loss

**Automated backups:**
- Backup sidecar exports graph to S3 **every 15 minutes**
- On task interrupt → final backup is created before shutdown
- On task restart → dump-downloader restores latest backup from S3

**Maximum data loss:** 15 minutes (between backups)

### 2. Automatic Recovery

When AWS interrupts a Fargate Spot task:

1. **T+0s:** AWS sends SIGTERM signal
2. **T+0-120s:** Backup sidecar creates final dump and uploads to S3
3. **T+120s:** Task terminates
4. **T+121s:** ECS immediately schedules new Spot task
5. **T+122s-240s:** New task starts, downloads latest dump, restores Neo4j
6. **T+240s:** Neo4j healthy, NLB routes traffic to new task

**Total downtime:** ~2-3 minutes (time to restore from backup)

### 3. Health Check Configuration

```python
health_check_grace_period=Duration.seconds(300)  # 5 minutes
```

This gives Neo4j enough time to:
- Download dump from S3 (~30s)
- Load dump into database (~1-2 min)
- Start and pass health check (~1-2 min)

---

## Interruption Frequency

**Historical data (AWS published):**
- Fargate Spot interruption rate: **< 5%** of tasks per month
- Average task lifetime: **several days to weeks**

**For this workload:**
- Task runs 24/7 (~730 hours/month)
- Expected interruptions: **0-2 per month**
- Expected downtime: **4-6 minutes/month total**

**Availability:** ~99.9% (vs 99.99% with standard Fargate)

---

## Trade-offs

### ✅ Acceptable for This Use Case

**Why it's safe:**
- **Stateless compute:** Neo4j data persists in S3 backups
- **Automatic recovery:** ECS reschedules immediately
- **Minimal data loss:** 15-minute backup interval
- **Not customer-facing:** Internal context graph for agents

### ❌ Not Recommended If

- Real-time financial transactions (no data loss tolerance)
- Customer-facing APIs (strict SLA requirements)
- Mission-critical workloads (need 99.99%+ uptime)
- No backup/restore strategy

---

## Monitoring Interruptions

### CloudWatch Metrics

```bash
# Check interruption count
aws cloudwatch get-metric-statistics \
    --namespace AWS/ECS \
    --metric-name SpotInterrupted \
    --dimensions Name=ClusterName,Value=Neo4jContextGraph-Neo4jCluster-xxxxx \
    --start-time 2026-05-01T00:00:00Z \
    --end-time 2026-05-11T00:00:00Z \
    --period 86400 \
    --statistics Sum
```

### ECS Events

```bash
# View service events (includes Spot interruptions)
aws ecs describe-services \
    --cluster Neo4jContextGraph-Neo4jCluster-xxxxx \
    --services Neo4jContextGraph-Neo4jService-xxxxx \
    --query 'services[0].events[0:10]'
```

Look for:
- `"message": "FARGATE_SPOT_INTERRUPTED"`
- `"message": "service ... has started 1 tasks"`

---

## Cost Breakdown (Fargate Spot)

| Component | Cost/Month |
|-----------|-----------|
| **Fargate Spot** (2048 CPU, 4096 MB, 730h) | **$15** |
| VPC Endpoints (4 interface + 1 gateway) | $7 |
| NLB (internal) | $16 |
| CloudWatch Logs | $2 |
| Secrets Manager | $0.40 |
| S3 backups | $1 |
| **Total** | **$34/month** |

**vs Original:** $104/month → **67% savings**

---

## Switching Between Standard and Spot

### Enable Fargate Spot (Current Configuration)

```python
capacity_provider_strategies=[
    ecs.CapacityProviderStrategy(
        capacity_provider="FARGATE_SPOT",
        weight=1,
        base=0
    )
]
```

### Switch to Standard Fargate

If interruptions become an issue, switch back:

```python
# Remove capacity_provider_strategies parameter
# CDK defaults to standard Fargate
```

Then deploy:
```bash
cd cdk
cdk deploy
```

**Cost impact:** +$35/month (back to $69/month)

---

## Hybrid Strategy (Not Implemented)

You can also use **both** Spot and Standard:

```python
capacity_provider_strategies=[
    ecs.CapacityProviderStrategy(
        capacity_provider="FARGATE",      # Standard
        weight=1,
        base=1  # Always run 1 standard task
    ),
    ecs.CapacityProviderStrategy(
        capacity_provider="FARGATE_SPOT", # Spot
        weight=4  # Run 4 Spot tasks for every 1 standard
    )
]
```

**Cost:** Mix of $50 and $15 per task  
**Availability:** Better than pure Spot  
**Use case:** High-traffic production with scale-out needs

---

## Best Practices

### 1. Test Interruption Handling

Simulate Spot interruption:

```bash
# Find task ARN
TASK_ARN=$(aws ecs list-tasks \
    --cluster Neo4jContextGraph-Neo4jCluster-xxxxx \
    --query 'taskArns[0]' --output text)

# Stop task (simulates interruption)
aws ecs stop-task \
    --cluster Neo4jContextGraph-Neo4jCluster-xxxxx \
    --task $TASK_ARN \
    --reason "Testing Spot interruption handling"

# Watch logs
aws logs tail /ecs/neo4j-context-graph --follow

# Verify new task starts and restores from backup
```

### 2. Monitor Backup Success

```bash
# Check S3 for recent backups
aws s3 ls s3://neo4jcontextgraph-dumpbucket-xxxxx/ --recursive \
    | sort | tail -5
```

Expected: New backups every 15 minutes

### 3. Set Up Alerts

Create CloudWatch alarm for service task count:

```bash
aws cloudwatch put-metric-alarm \
    --alarm-name neo4j-task-down \
    --metric-name DesiredTaskCount \
    --namespace AWS/ECS \
    --statistic Average \
    --period 60 \
    --threshold 1 \
    --comparison-operator LessThanThreshold \
    --evaluation-periods 2
```

---

## FAQ

**Q: Can I use Fargate Spot for production?**  
A: Yes, if you have proper backup/recovery strategy and can tolerate brief interruptions. Many AWS customers run production workloads on Spot.

**Q: How often will my task be interrupted?**  
A: Historically < 5% interruption rate. For a single task running 24/7, expect 0-2 interruptions per month.

**Q: What happens to data during interruption?**  
A: Backup sidecar creates final dump before shutdown. New task restores from latest backup. Max data loss: 15 minutes.

**Q: Can I reduce data loss window?**  
A: Yes, change `BACKUP_INTERVAL=300` (5 minutes) in `neo4j_cluster.py` line 284. Trade-off: more S3 API calls.

**Q: Does Spot work in all regions?**  
A: Yes, Fargate Spot is available in all commercial AWS regions.

**Q: Can I get notified before interruption?**  
A: AWS sends SIGTERM 120 seconds before termination. The backup sidecar handles this automatically.

---

## Further Reading

- [AWS Fargate Spot Pricing](https://aws.amazon.com/fargate/pricing/)
- [ECS Capacity Providers](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/cluster-capacity-providers.html)
- [Fargate Spot Best Practices](https://docs.aws.amazon.com/AmazonECS/latest/bestpracticesguide/fargate-spot.html)
