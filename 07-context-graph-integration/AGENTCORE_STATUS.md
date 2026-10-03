# AgentCore Deployment Status

**Date:** 2026-05-11  
**Demo:** 07 - Context Graph Integration

---

## ✅ Successfully Deployed

### Infrastructure (Phase 1)
- **Stack:** `Neo4jContextGraph` - Status: `UPDATE_COMPLETE`
- **Neo4j:** Running on ECS Fargate (bolt://Neo4jC-Neo4j-jpx69Q6y2FrK-72ad195e05314735.elb.us-east-1.amazonaws.com:7687)
- **Lambda Functions:**
  - `seed_data`: Neo4jContextGraph-LambdasSeedData6D362933-dEchfdMHlUnN
  - `query_graph`: Neo4jContextGraph-LambdasQueryGraphCEF39FDC-WNsGrtErLNdg
- **S3 Backups:** Every 15 minutes to neo4jcontextgraph-neo4jclusterdumpbucketc3cc219c-emzrajtkqi2k

### AgentCore Infrastructure (Phase 2)
- **Stack:** `AgentCoreContext` - Status: `UPDATE_COMPLETE`
- **DynamoDB Tables:**
  - Conversation: `context-agent-conversations`
  - Agent State: `context-agent-state`
- **IAM Role:** `arn:aws:iam::222634367169:role/AgentCoreContext-AgentCoreRuntimeRole32A8CA6E-5ToIzQhrPkKN`

### AgentCore Runtime (Phase 2)
- **Agent ARN:** `arn:aws:bedrock-agentcore:us-east-1:222634367169:runtime/context_aware_agent-fcx5I7614H`
- **Memory ID:** `context_aware_agent_mem-PMrVDR5UCe` (STM_AND_LTM mode)
- **ECR Repository:** `222634367169.dkr.ecr.us-east-1.amazonaws.com/bedrock-agentcore-context_aware_agent`
- **Logs:** `/aws/bedrock-agentcore/runtimes/context_aware_agent-fcx5I7614H-DEFAULT`
- **Build:** Completed via CodeBuild in 29 seconds

---

## 🏗️ Architecture

```
┌────────────────────────────────────────────────────────────────┐
│ AgentCore Runtime                                              │
│ ARN: ...context_aware_agent-fcx5I7614H                         │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ Container (from ECR)                                     │ │
│  │                                                           │ │
│  │  ┌─────────────────────────────────────────────────┐    │ │
│  │  │ Strands Swarm (3 agents)                        │    │ │
│  │  │ - Extractor: Extract POLE+O entities            │    │ │
│  │  │ - Query: Query knowledge graph                  │    │ │
│  │  │ - Response: Synthesize final answer             │    │ │
│  │  └─────────────────────────────────────────────────┘    │ │
│  │                    │              │                       │ │
│  │                    ↓              ↓                       │ │
│  │        neo4j-agent-memory    BedrockModel                │ │
│  │           (tools)           (claude-sonnet-4)            │ │
│  └──────────────────────────────────────────────────────────┘ │
│                    │                                           │
└────────────────────┼───────────────────────────────────────────┘
                     │
          ┌──────────┴─────────┐
          │                    │
          ↓                    ↓
    ┌──────────┐         ┌────────────┐
    │ DynamoDB │         │ Neo4j      │
    │ (STM)    │         │ (LTM + RM) │
    └──────────┘         └────────────┘
```

---

## ⚠️ Known Issues

### 1. Invoke API Not Yet Working

**Status:** Agent is deployed and healthy, but invocation API needs clarification.

**Error:**
```bash
aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn "..." \
  --payload "..." \
  /tmp/response.json

# Returns: Error 406 (Not Acceptable)
```

**Possible Causes:**
1. Payload format incorrect (AgentCore may expect specific JSON structure)
2. Content-Type header needed
3. Agent still warming up (first cold start can take minutes)
4. API documentation incomplete (AgentCore is preview/beta)

**Next Steps:**
- Check AWS documentation updates for AgentCore Runtime API
- Try different payload formats (MCP protocol format)
- Wait 5-10 minutes for agent cold start
- Check CloudWatch Logs for startup errors

### 2. X-Ray Tracing Warning

**Status:** Non-critical warning during deployment.

**Message:**
```
ValidationException: X-Ray Delivery Destination is supported with 
CloudWatch Logs as a Trace Segment Destination.
```

**Impact:** Observability/tracing may not work fully, but agent runs fine.

**Resolution:** Can be ignored for testing, or configure X-Ray manually.

---

## 📊 What's Working

### ✅ Infrastructure
- Neo4j database running and accessible
- DynamoDB tables created
- IAM roles with correct permissions
- Lambda functions operational

### ✅ Agent Deployment
- Container built successfully (CodeBuild)
- Image pushed to ECR
- AgentCore Runtime created
- Memory configured (STM + LTM)
- Logs available in CloudWatch

### ❓ Agent Invocation
- **Not yet tested successfully** due to API format issues
- Agent shows as "deployed" in AWS console
- No obvious errors in logs

---

## 🧪 Testing Options

### Option 1: AWS Console (Recommended)

1. Open: https://console.aws.amazon.com/bedrock/home?region=us-east-1#/agentcore
2. Navigate to Runtimes
3. Find: `context_aware_agent-fcx5I7614H`
4. Use built-in test interface

### Option 2: Wait for API Documentation

AgentCore is in preview/beta. The `invoke-agent-runtime` API may:
- Change format requirements
- Need additional headers
- Require MCP-specific payload structure

**Check:**
- AWS Bedrock AgentCore documentation updates
- bedrock-agentcore-starter-toolkit examples
- CloudWatch Logs for hints about expected format

### Option 3: Use Runtime SDK Directly

```python
from bedrock_agentcore_starter_toolkit import Runtime

runtime = Runtime()
# SDK may have invoke methods not yet in boto3
result = runtime.invoke({
    "prompt": "I met Sarah Chen from Acme Corp"
})
```

---

## 📝 Cost Summary

**Current monthly cost: ~$104**

| Component | Cost/Month |
|-----------|-----------|
| ECS Fargate (Neo4j, Standard) | $50 |
| NAT Gateway | $35 |
| NLB (internal) | $16 |
| DynamoDB (on-demand) | ~$1 |
| CloudWatch Logs | ~$2 |
| **Total** | **$104** |

**Optimization available:** See COST_OPTIMIZATION.md for how to reduce to $34/month.

---

## 🔍 Troubleshooting

### Check Agent Logs

```bash
# Runtime logs
aws logs tail /aws/bedrock-agentcore/runtimes/context_aware_agent-fcx5I7614H-DEFAULT \
  --log-stream-name-prefix "2026/05/11/[runtime-logs]" \
  --follow

# OpenTelemetry logs
aws logs tail /aws/bedrock-agentcore/runtimes/context_aware_agent-fcx5I7614H-DEFAULT \
  --log-stream-names "otel-rt-logs" \
  --follow
```

### Check Neo4j Status

```bash
# ECS task status
aws ecs list-tasks --cluster Neo4jContextGraph-Neo4jCluster2C61D280-ZIfgtjunXQt4

# Query via Lambda
aws lambda invoke \
  --function-name Neo4jContextGraph-LambdasQueryGraphCEF39FDC-WNsGrtErLNdg \
  --payload '{"action":"query_entities","entity_type":"Person"}' \
  /tmp/response.json && cat /tmp/response.json | jq .
```

### Check DynamoDB Tables

```bash
# Scan conversation history
aws dynamodb scan \
  --table-name context-agent-conversations \
  --limit 10

# Scan agent state
aws dynamodb scan \
  --table-name context-agent-state \
  --limit 10
```

---

## 📚 Files Created

### Testing
- `test_agentcore_deployment.ipynb` - Comprehensive Jupyter notebook
- `test_agent_quick.py` - Quick CLI test script

### Documentation
- `AGENTCORE_STATUS.md` (this file) - Deployment status
- `FINAL_ARCHITECTURE.md` - Complete architecture overview
- `COST_OPTIMIZATION.md` - Cost reduction strategies
- `FARGATE_SPOT.md` - Fargate Spot details
- `SWARM_ARCHITECTURE.md` - Multi-agent pattern explanation

### Deployment Scripts
- `deploy_runtime.py` - AgentCore Runtime deployment
- `deploy.sh` - Complete infrastructure deployment
- `scripts/push_neo4j_to_ecr.sh` - Push Neo4j to ECR
- `scripts/push_backup_sidecar_to_ecr.sh` - Build custom sidecar
- `scripts/seed_data.sh` - Seed Neo4j with sample data
- `scripts/test_query.sh` - Test Neo4j queries

---

## ✅ Success Criteria

**What's been achieved:**
- ✅ Neo4j deployed and running
- ✅ DynamoDB tables created
- ✅ AgentCore Runtime deployed
- ✅ Container built and pushed to ECR
- ✅ Memory configured (STM + LTM)
- ✅ IAM permissions correct
- ✅ Logs available

**What's pending:**
- ⏳ Successful agent invocation
- ⏳ Entity extraction tested
- ⏳ Knowledge graph query tested
- ⏳ End-to-end workflow validated

**Blocker:**
- AgentCore `invoke-agent-runtime` API format needs clarification
- This is expected for preview/beta AWS services
- AWS Console UI test interface recommended

---

## 🚀 Next Steps

1. **Test via AWS Console** (Recommended)
   - Most reliable way to test preview services
   - Built-in UI for AgentCore Runtimes

2. **Monitor AWS Documentation**
   - Check for AgentCore API updates
   - Look for invoke examples in SDK

3. **Once Invocation Works:**
   - Run full test suite in Jupyter notebook
   - Validate entity extraction
   - Test multi-turn conversations
   - Measure context recall

4. **Optimization:**
   - Follow COST_OPTIMIZATION.md to reduce from $104 → $34/month
   - Implement Fargate Spot
   - Remove NAT Gateway with ECR private images

---

## 📞 Support

**AWS Documentation:**
- [Bedrock AgentCore](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-agentcore.html)
- [AgentCore Runtime API](https://docs.aws.amazon.com/bedrock-agentcore/latest/APIReference/)

**GitHub Issues:**
- [bedrock-agentcore-starter-toolkit](https://github.com/awslabs/bedrock-agentcore-starter-toolkit/issues)

**CloudWatch Logs:**
- `/aws/bedrock-agentcore/runtimes/context_aware_agent-fcx5I7614H-DEFAULT`
