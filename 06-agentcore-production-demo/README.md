[< Back to Main README](../README.md)

# Production-Ready Booking Agent on Amazon Bedrock AgentCore

Apply anti-hallucination techniques from the previous demos in this series (01-05) and deploy them to production using [Amazon Bedrock AgentCore](https://aws.amazon.com/bedrock/agentcore/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el), [Amazon DynamoDB](https://aws.amazon.com/dynamodb/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el), [AWS Secrets Manager](https://aws.amazon.com/secrets-manager/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el), and [Neo4j AuraDB](https://neo4j.com/cloud/aura-free/).

[![Python](https://img.shields.io/badge/Python-3.11-green.svg?style=flat)](https://python.org)
[![AgentCore](https://img.shields.io/badge/Bedrock-AgentCore-orange.svg?style=flat&logo=amazon-aws)](https://aws.amazon.com/bedrock/agentcore/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el)
[![CDK](https://img.shields.io/badge/AWS_CDK-v2-blue.svg?style=flat&logo=amazon-aws)](https://aws.amazon.com/cdk/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el)
[![DynamoDB](https://img.shields.io/badge/DynamoDB-tables-orange.svg?style=flat&logo=amazon-aws)](https://aws.amazon.com/dynamodb/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el)
[![Neo4j](https://img.shields.io/badge/Neo4j-AuraDB-blue.svg?style=flat)](https://neo4j.com/cloud/aura-free/)

This demo uses [Strands Agents](https://github.com/strands-agents/sdk-python) with [OpenAI](https://platform.openai.com/).

> **Complexity note:** This guide uses [AWS CDK](https://aws.amazon.com/cdk/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el) and core AWS services (Lambda, DynamoDB, S3, IAM). New to CDK? We recommend starting with the [CDK Workshop](https://cdkworkshop.com/) to build foundational knowledge, then returning to this guide.

## What This Demo Shows

Demos 01-05 demonstrate techniques that can significantly reduce hallucinations. This demo takes those techniques to production:

| Technique (from demos) | Production implementation |
|------------------------|--------------------------|
| **Semantic tool selection** (demo 02) | [Amazon Bedrock AgentCore Gateway](https://aws.amazon.com/bedrock/agentcore/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el) with MCP semantic routing — no custom FAISS index needed |
| **Multi-agent validation** (demo 03) | `validate_booking_rules` tool backed by [Amazon DynamoDB](https://aws.amazon.com/dynamodb/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el) — same safety, lower latency |
| **Neurosymbolic guardrails** (demo 04) | Steering rules in [Amazon DynamoDB](https://aws.amazon.com/dynamodb/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el) — change rules without redeploying |
| **Agent Control steering** (demo 05) | STEER messages in DynamoDB rules — agent self-corrects instead of failing |
| **Graph-RAG** (demo 01) | [Neo4j AuraDB Free](https://neo4j.com/cloud/aura-free/) with query [AWS Lambda](https://aws.amazon.com/lambda/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el) |

## Architecture

![Architecture diagram showing AgentCore Runtime connecting to Gateway via MCP, which routes to Lambda booking tools backed by DynamoDB tables, with an optional GraphRAG stack connecting to Neo4j AuraDB](images/architecture.svg)

## Two Independent Stacks

### Stack 1: `HotelBookingAgentStack`

Deploy first. Works without GraphRAG.

| Resource | Purpose |
|----------|---------|
| [Amazon DynamoDB](https://aws.amazon.com/dynamodb/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el) Hotels | Hotel inventory (18 seeded hotels across 18 cities worldwide) |
| [Amazon DynamoDB](https://aws.amazon.com/dynamodb/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el) Bookings | Reservation CRUD |
| [Amazon DynamoDB](https://aws.amazon.com/dynamodb/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el) SteeringRules | Business rules with STEER messages (changeable without redeploy) |
| [AWS Secrets Manager](https://aws.amazon.com/secrets-manager/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el) | OpenAI API key (populate via Console after deploy) |
| [Amazon Bedrock AgentCore Runtime](https://aws.amazon.com/bedrock/agentcore/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el) | Agent connects to Gateway via MCP to discover and invoke tools |
| [Amazon Bedrock AgentCore Gateway](https://aws.amazon.com/bedrock/agentcore/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el) | MCP semantic routing to Lambda tools |
| 7 [AWS Lambda](https://aws.amazon.com/lambda/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el) functions | search, book, get_booking, process_payment, confirm, cancel, validate |
| Hard hooks (in agent) | Payment before confirm, cancellation window 48h — enforced at framework level |

### Stack 2: `GraphRAGStack`

Deploy separately when ready. Connects to Stack 1 via [AWS Systems Manager Parameter Store](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-parameter-store.html?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el).

| Resource | Purpose |
|----------|---------|
| [Amazon S3](https://aws.amazon.com/s3/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el) Bucket | Hotel FAQ documents (auto-uploaded during deploy) |
| [AWS Lambda](https://aws.amazon.com/lambda/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el) build_graph | Builds knowledge graph using [SimpleKGPipeline](https://neo4j.com/docs/neo4j-graphrag-python/current/user_guide_kg_builder.html) (lite: 30 docs, full: 300 docs via [AWS Step Functions](https://aws.amazon.com/step-functions/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el)) |
| [AWS Lambda](https://aws.amazon.com/lambda/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el) query_knowledge_graph | Executes [Cypher](https://neo4j.com/docs/cypher-manual/current/) queries against Neo4j AuraDB, registered as Gateway target |
| [AWS Secrets Manager](https://aws.amazon.com/secrets-manager/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el) | [Neo4j AuraDB](https://neo4j.com/cloud/aura-free/) URI, username, password, and [OpenAI](https://platform.openai.com/) API key |
| [Neo4j AuraDB Free](https://neo4j.com/cloud/aura-free/) | Managed graph database ($0/month free tier, 200K nodes) |

---

## Quick Start

### Prerequisites

Before starting, make sure you have:

- **[Python](https://python.org/downloads) 3.11+** installed ([download here](https://python.org/downloads))
- **[uv](https://docs.astral.sh/uv/)** package manager ([installation guide](https://docs.astral.sh/uv/getting-started/installation/))
- **[AWS CLI](https://aws.amazon.com/cli/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el)** installed and configured ([installation guide](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el))
- **[AWS CDK v2](https://aws.amazon.com/cdk/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el)** installed ([getting started guide](https://docs.aws.amazon.com/cdk/v2/guide/getting_started.html?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el))
- **[OpenAI API key](https://platform.openai.com/api-keys)** ([create one here](https://platform.openai.com/api-keys))

### Step 1: Clone and install

```bash
git clone https://github.com/aws-samples/sample-why-agents-fail
cd sample-why-agents-fail/stop-ai-agent-hallucinations/06-agentcore-production-demo

# Install local dependencies
uv venv && uv pip install -r requirements.txt
```

### Step 2: Build and deploy the booking agent

```bash
# Build the agent deployment package
./create_deployment_package.sh

# Set up CDK and deploy
cd cdk
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cdk bootstrap   # Only needed once per AWS account/region
cdk deploy HotelBookingAgentStack
```

CDK will create all the AWS resources and output the ARNs you need. Note the `AgentRuntimeArn` and `OpenAIKeySecretArn` from the output.

### Step 3: Store your OpenAI API key

1. Open the [AWS Secrets Manager Console](https://console.aws.amazon.com/secretsmanager/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el)
2. Find the secret named `/HotelBookingAgentStack/openai-api-key`
3. Click **Retrieve secret value** → **Set secret value**
4. Paste your [OpenAI API key](https://platform.openai.com/api-keys) as plaintext

### Step 4: Seed the hotel data

```bash
cd ..   # Back to 06-agentcore-production-demo/
AWS_DEFAULT_REGION=us-east-1 uv run python seed_data.py
```

This loads 10 hotels and 6 steering rules into [Amazon DynamoDB](https://aws.amazon.com/dynamodb/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el).

### Step 5: Test the agent

```bash
aws bedrock-agentcore invoke-agent-runtime \
    --agent-runtime-arn <AgentRuntimeArn from Step 2 output> \
    --payload "$(echo '{"prompt": "Search for hotels in Paris"}' | base64)" \
    --region us-east-1 /tmp/response.json && cat /tmp/response.json
```

Or open `test_agent_local.ipynb` in your IDE (VS Code, Kiro, or any editor with notebook support) to test with the local tools against the same DynamoDB tables.

---

## Adding GraphRAG (Optional)

GraphRAG adds a knowledge graph for answering questions about hotel amenities, policies, and FAQs. It uses [Neo4j AuraDB Free](https://neo4j.com/cloud/aura-free/) — a managed graph database with a free tier ($0/month, 200K nodes, no credit card required).

### Step 1: Create a Neo4j AuraDB Free instance

1. Go to [neo4j.com/cloud/aura-free](https://neo4j.com/cloud/aura-free/) and create a free account
2. Click **New Instance** → **AuraDB Free**
3. Choose a name (e.g. `hotel-graphrag`) and region
4. Save the connection URI and password — you'll need them in Step 3

> **What is Neo4j?** [Neo4j](https://neo4j.com/) is a graph database that stores data as nodes and relationships instead of rows and columns. This lets the agent answer questions like "What amenities does the Grand Hotel have?" by traversing the graph directly (following the connections between data points), instead of guessing from text chunks. Learn more in [demo 01](../01-faq-graphrag-demo/).

### Step 2: Deploy the GraphRAG stack

```bash
cd cdk
source .venv/bin/activate
INCLUDE_GRAPHRAG=1 cdk deploy GraphRAGStack
```

This creates:
- [AWS Lambda](https://aws.amazon.com/lambda/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el) functions (graph builder + query)
- [Amazon S3](https://aws.amazon.com/s3/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el) bucket with 300 hotel FAQ documents auto-uploaded
- [AWS Secrets Manager](https://aws.amazon.com/secrets-manager/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el) secrets (empty — you fill them next)

By default, it deploys in **lite mode** (30 documents, ~15 min build). For the full dataset, see [Full Mode (300 documents)](#full-mode-300-documents) below.

### Step 3: Store Neo4j credentials

1. Open the [AWS Secrets Manager Console](https://console.aws.amazon.com/secretsmanager/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el)
2. Set values for these 4 secrets:

| Secret name | Value | Where to find it |
|-------------|-------|-----------------|
| `/GraphRAGStack/neo4j-uri` | Connection URI | Shown after AuraDB instance creation (e.g. `neo4j+s://xxxx.databases.neo4j.io`) |
| `/GraphRAGStack/neo4j-user` | Username | Shown after creation (default: `neo4j`) |
| `/GraphRAGStack/neo4j-password` | Password | Auto-generated by AuraDB — save it during creation |
| `/GraphRAGStack/openai-api-key` | API key | Get from [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |

### Step 4: Build the knowledge graph

The graph builder uses [neo4j-graphrag](https://neo4j.com/docs/neo4j-graphrag-python/current/) with `SimpleKGPipeline` to automatically discover entities and relationships from hotel FAQ documents — no schema hardcoding needed.

Trigger the build (runs in [AWS Lambda](https://aws.amazon.com/lambda/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el), ~15 min for lite mode):

```bash
aws lambda invoke --function-name graphrag-build-graph \
    --region us-east-1 --cli-read-timeout 900 \
    /tmp/build-graph-output.json && cat /tmp/build-graph-output.json
```

The Lambda reads the 30 hotel FAQ documents from [Amazon S3](https://aws.amazon.com/s3/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el), calls [OpenAI](https://platform.openai.com/) to extract entities, and loads them into your [Neo4j AuraDB](https://neo4j.com/cloud/aura-free/) instance.

### Step 5: Connect GraphRAG to the booking agent

```bash
cd cdk
cdk deploy HotelBookingAgentStack \
    -c graphrag_query_lambda_arn=<QueryLambdaArn from GraphRAGStack output>
```

This adds the `query_knowledge_graph` tool to the [Amazon Bedrock AgentCore Gateway](https://aws.amazon.com/bedrock/agentcore/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el). The agent can now answer questions like "What amenities does the Grand Hotel have?" using real data from the graph.

---

## Steering Rules

Rules live in [Amazon DynamoDB](https://aws.amazon.com/dynamodb/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el), not in code. Change agent behavior without redeploying:

```json
{
    "rule_id": "max-guests",
    "action": "book",
    "condition_field": "guests",
    "operator": "gt",
    "threshold": 10,
    "fail_message": "Guest count exceeds maximum of 10",
    "steer_message": "Reduce the guest count to 10, proceed with the booking, and inform the user about the maximum capacity policy.",
    "enabled": true
}
```

The agent calls `validate_booking_rules` before every booking action. When a rule is violated, it receives the `steer_message` — an instruction on how to self-correct — instead of a hard failure.

**To change a rule** (takes effect immediately, no redeploy):

```bash
aws dynamodb update-item \
    --table-name HotelBookingAgentStack-SteeringRules \
    --key '{"rule_id": {"S": "max-guests"}}' \
    --update-expression "SET threshold = :t" \
    --expression-attribute-values '{":t": {"N": "8"}}'
```

---

## Runtime Lifecycle Configuration

The runtime includes a `lifecycle_configuration` that controls how long sessions stay active. Adjust these values in `cdk/agentcore/agentcore_runtime.py` to match your workload:

```python
lifecycle_configuration=agentcore.CfnRuntime.LifecycleConfigurationProperty(
    idle_runtime_session_timeout=900,  # 15 minutes — shuts down if no requests
    max_lifetime=28800,  # 8 hours — maximum total session lifetime
),
```

| Parameter | Default | What it controls |
|-----------|:-------:|-----------------|
| `idle_runtime_session_timeout` | 900s (15 min) | How long the runtime stays active without receiving requests before shutting down |
| `max_lifetime` | 28800s (8 hrs) | Maximum total lifetime of a runtime session, regardless of activity |

**To change** (takes effect on next deploy):

```bash
# Edit cdk/agentcore/agentcore_runtime.py, then:
cd cdk && cdk deploy HotelBookingAgentStack
```

Lower `idle_runtime_session_timeout` for cost savings on low-traffic agents. Increase `max_lifetime` for long-running sessions that handle many sequential requests.

---

## Full Mode (300 documents)

The lite mode (default) processes 30 documents, which is enough to demonstrate GraphRAG. To process all 300 hotel FAQ documents, deploy with full mode:

```bash
cd cdk
source .venv/bin/activate
INCLUDE_GRAPHRAG=1 cdk deploy GraphRAGStack -c graph_mode=full
```

Full mode creates an [AWS Step Functions](https://aws.amazon.com/step-functions/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el) pipeline that splits the 300 documents into 10 batches of 30 and processes each batch in a separate [AWS Lambda](https://aws.amazon.com/lambda/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el) (15 min timeout per batch). Total processing time: **~1-2 hours**.

Start the pipeline:

```bash
aws stepfunctions start-execution \
    --state-machine-arn arn:aws:states:<region>:<account>:stateMachine:graphrag-build-pipeline \
    --region us-east-1
```

Monitor progress in the [Step Functions Console](https://console.aws.amazon.com/states/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el).

| Mode | Documents | Build time | Method | Cost estimate |
|------|-----------|-----------|--------|---------------|
| **Lite** (default) | 30 | ~15 min | Single Lambda | ~$0.15 (Lambda) + ~$0.02 (OpenAI) |
| **Full** | 300 | ~1-2 hours | Step Functions + 10 Lambdas | ~$1.50 (Lambda) + ~$0.20 (OpenAI) |

---

## Test Scenarios

| # | Scenario | Expected behavior |
|---|----------|-------------------|
| 1 | Full booking: search → validate → book → pay → confirm | CONFIRMED |
| 2 | 15 guests (max 10) | validate → STEER: "15 not available, adjusted to 10" |
| 3 | Confirm without payment | Hard hook BLOCKS confirm → agent asks to pay first |
| 4 | Hotel with no rooms | book_hotel → ERROR (DynamoDB: available_rooms = 0) |
| 5 | City with no hotels | search → "No hotels found" (no hallucination) |
| 6 | Non-existent hotel | book_hotel → ERROR (DynamoDB: not found) |
| 7 | Non-existent booking | get_booking → ERROR (no hallucination) |
| 8 | "What amenities does Grand Hotel have?" | query_knowledge_graph → [Cypher](https://neo4j.com/docs/cypher-manual/current/) → real data from Neo4j |

---

## File Structure

```
06-agentcore-production-demo/
├── test_agent_local.ipynb          # Test locally before deploying
├── local_tools.py                  # Strands @tool functions (DynamoDB, for local testing)
├── config.py                       # Table names from environment
├── seed_data.py                    # Seed hotels + steering rules
├── requirements.txt                # Local dependencies
├── agent_files/
│   ├── booking_agent.py            # AgentCore Runtime entry point (connects to Gateway via MCP)
│   └── requirements.txt            # Runtime dependencies
├── lambda_tools/
│   ├── search_available_hotels/    # DynamoDB scan with filters
│   ├── book_hotel/                 # Create PENDING reservation
│   ├── get_booking/                # Read booking status
│   ├── process_payment/            # PENDING → PAID
│   ├── confirm_booking/            # PAID → CONFIRMED
│   ├── cancel_booking/             # Cancel + return room
│   ├── validate_booking_rules/     # Steering rules from DynamoDB
│   ├── build_graph/                # SimpleKGPipeline (auto-schema discovery)
│   └── query_knowledge_graph/      # Cypher queries to Neo4j AuraDB
├── tool_schemas/
│   └── tools.json                  # Tool definitions for Gateway
├── images/
│   ├── architecture.drawio         # Editable architecture diagram
│   └── architecture.svg            # Architecture diagram (animated)
├── cdk/
│   ├── app.py                      # Both stacks registered
│   ├── stack.py                    # HotelBookingAgentStack
│   ├── graphrag_stack.py           # GraphRAGStack
│   └── agentcore/                  # CDK constructs
├── create_deployment_package.sh    # Package agent for AgentCore Runtime
```

---

## Technologies

| Technology | Purpose |
|------------|---------|
| [Amazon Bedrock AgentCore](https://aws.amazon.com/bedrock/agentcore/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el) | Runtime (agent hosting), Gateway (MCP semantic tool routing) |
| [Amazon DynamoDB](https://aws.amazon.com/dynamodb/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el) | Hotels, bookings, and steering rules tables |
| [AWS Lambda](https://aws.amazon.com/lambda/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el) | Serverless tool functions (search, book, validate, query graph) |
| [AWS Secrets Manager](https://aws.amazon.com/secrets-manager/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el) | Secure credential storage ([OpenAI](https://platform.openai.com/) API key, [Neo4j](https://neo4j.com/) credentials) |
| [AWS CDK v2](https://aws.amazon.com/cdk/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el) | Infrastructure as code (two independent stacks) |
| [Amazon S3](https://aws.amazon.com/s3/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el) | Hotel FAQ documents storage |
| [AWS Systems Manager Parameter Store](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-parameter-store.html?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el) | Cross-stack parameter sharing |
| [Strands Agents](https://github.com/strands-agents/sdk-python) | Open-source AI agent framework (tool calling, hooks) |
| [OpenAI](https://platform.openai.com/) | LLM provider (GPT-4o-mini) |
| [Neo4j AuraDB Free](https://neo4j.com/cloud/aura-free/) | Managed graph database for knowledge graph |
| [neo4j-graphrag](https://neo4j.com/docs/neo4j-graphrag-python/current/) | Auto schema discovery ([SimpleKGPipeline](https://neo4j.com/docs/neo4j-graphrag-python/current/user_guide_kg_builder.html)) |
| [Cypher](https://neo4j.com/docs/cypher-manual/current/) | Neo4j query language for graph traversal |

---

## Observability

Amazon Bedrock AgentCore provides [built-in observability](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability.html?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el) when the OpenTelemetry dependencies are included in the agent package. The agent's `requirements.txt` includes:

```
strands-agents[openai,otel]>=1.27.0
aws-opentelemetry-distro>=0.7.0
```

With these dependencies, Amazon Bedrock AgentCore automatically instruments Strands Agents — capturing invocation logs, tool call traces (which Lambda was called, input/output, latency), and error tracking (failed tool calls, guardrail blocks) in [Amazon CloudWatch](https://aws.amazon.com/cloudwatch/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el).

See the [observability getting started guide](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability-get-started.html?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el) for details.

---

## Troubleshooting

**Agent returns 500 error:** Check [Amazon CloudWatch Logs](https://aws.amazon.com/cloudwatch/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el) under `/aws/bedrock-agentcore/runtimes/` for the runtime logs.

**"NoRegionError":** Ensure `AWS_DEFAULT_REGION` is set when running local scripts. The CDK stack passes `AWS_REGION` to the runtime automatically.

**"SecretString is empty":** Go to [AWS Secrets Manager Console](https://console.aws.amazon.com/secretsmanager/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el) and populate the secret values (Step 3 in Quick Start).

**Graph builder fails to connect:** Verify your [Neo4j AuraDB](https://neo4j.com/cloud/aura-free/) instance is running (not paused) and the URI/password in Secrets Manager are correct.

**Model alternatives:** The agent supports multiple LLM providers including [OpenAI](https://platform.openai.com/), [Amazon Bedrock](https://aws.amazon.com/bedrock/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el), Anthropic, or Ollama. Change the model in `booking_agent.py`.

**Clean up resources:** To avoid ongoing charges, destroy the stacks when done:

```bash
cd cdk
cdk destroy HotelBookingAgentStack
INCLUDE_GRAPHRAG=1 cdk destroy GraphRAGStack
```

---

## Frequently Asked Questions

### What is Amazon Bedrock AgentCore and how does it work?

Amazon Bedrock AgentCore is an AWS managed service for hosting AI agents in production. It provides a Runtime (agent hosting with auto-scaling) and a Gateway (MCP-based semantic routing to tools). The agent connects to the Gateway via MCP, which discovers and routes tool calls to Lambda functions — no custom routing code needed.

### How much does this deployment cost?

The booking agent stack uses pay-per-use AWS services: DynamoDB on-demand (~$0 at low volume), Lambda (~$0.20/1M requests), Secrets Manager (~$0.40/secret/month), and AgentCore Runtime (see [pricing](https://aws.amazon.com/bedrock/agentcore/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el)). The optional GraphRAG stack adds ~$0.15 (Lambda) + ~$0.02 (OpenAI) for the lite build. Neo4j AuraDB Free is $0/month.

### Can I use a different LLM provider instead of OpenAI?

Yes. Change the model in `booking_agent.py` to use any provider supported by Strands Agents: Amazon Bedrock (Claude, Titan), Anthropic API, Ollama (local models), or any OpenAI-compatible endpoint. The tools and infrastructure remain the same — only the LLM provider changes.

This demo uses Strands Agents for the agent framework. The production patterns demonstrated (DynamoDB-backed steering rules, Lambda tool functions, MCP routing) are applicable with other agent frameworks that support Amazon Bedrock AgentCore Runtime.

---

## Navigation

- **Previous:** [Demo 05 - Agent Control Steering](../05-agent-control-demo/)
- **Start from the beginning:** [Demo 01 - Graph-RAG vs RAG](../01-faq-graphrag-demo/)

---

## Security

If you discover a potential security issue in this project, notify AWS/Amazon Security via the [vulnerability reporting page](https://aws.amazon.com/security/vulnerability-reporting/?trk=87c4c426-cddf-4799-a299-273337552ad8&sc_channel=el). Please do **not** create a public GitHub issue.

---

## License

This library is licensed under the MIT-0 License. See the [LICENSE](../LICENSE) file for details.

> Last updated: March 2026 | AWS CDK v2 | Strands Agents 1.27+ | Python 3.11+
