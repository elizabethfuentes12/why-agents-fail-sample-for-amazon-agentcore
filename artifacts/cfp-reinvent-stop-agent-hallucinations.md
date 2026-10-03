# CFP: Stop AI Agent Hallucinations in Production

## Proposed Session Title (70 characters max)

**Build Hallucination-Free AI Agents with Amazon Bedrock AgentCore**

(64 characters)

---

## Proposed Session Abstract (100 words max)

AI agents hallucinate statistics, pick wrong tools, and ignore business rules. This session demonstrates five research-backed techniques deployed on Amazon Bedrock AgentCore: Graph-RAG cuts fabricated statistics by 73%, semantic tool filtering reduces token waste by 89%, multi-agent validation catches undetected errors, neurosymbolic guardrails with DynamoDB enforce business rules, and steering controls let agents self-correct. You'll see each technique demonstrated locally with Strands Agents, then deployed to production using AgentCore Runtime, Gateway, Lambda tools, and Neo4j. Leave with architectural patterns applicable to any agent framework.

(99 words)

---

## Alternate Titles

1. **Stop Agent Hallucinations with Amazon Bedrock AgentCore** (56 chars)
2. **5 Ways to Stop AI Agent Hallucinations on Amazon Bedrock AgentCore** (67 chars)
3. **Production AI Agents Without Hallucinations Using Amazon Bedrock** (64 chars)
4. **Stop AI Agent Hallucinations: 5 Techniques That Actually Work** (61 chars - original)

---

## Session Details

**Track:** Machine Learning and AI

**Session Level:** 300 (Advanced)

**Session Format:** Breakout (45 minutes)

**Target Audience:** ML engineers, AI/ML architects, developers building production agent systems

---

## Key Takeaways

Attendees will learn:

1. **Why agents fail** — Four hallucination types with measurable examples (fabricated statistics, wrong tool picks, rule violations, undetected failures)
2. **How to detect failures** — Multi-agent validation patterns and testing strategies that catch hallucinations before production
3. **How to prevent failures** — Graph-RAG vs RAG (73% fewer hallucinations), semantic tool filtering (89% token reduction), neurosymbolic guardrails
4. **How to self-correct** — Agent Control steering patterns that let agents fix mistakes instead of blocking
5. **How to deploy** — Production architecture using Amazon Bedrock AgentCore, DynamoDB steering rules, Lambda tools, and Neo4j Graph-RAG

---

## Session Outline (45 minutes)

### Introduction (5 minutes)
- Four types of AI agent hallucinations with real examples
- Why prompts alone don't work

### Part 1: Detect and Measure (10 minutes)
- Demo 01: Graph-RAG vs RAG on 300 hotel FAQs
  - Show fabricated statistics failure
  - Run same query against FAISS (RAG) and Neo4j (Graph-RAG)
  - Results: 73% fewer hallucinations with knowledge graphs
- Demo 02: Semantic tool filtering with 29 tools
  - Show wrong tool selection at scale
  - FAISS registry reduces 29 tools to 5 relevant ones
  - Results: 89% token reduction, higher accuracy

### Part 2: Prevent and Enforce (10 minutes)
- Demo 03: Multi-agent validation (Executor→Validator→Critic)
  - Show undetected hallucination
  - Three-agent cross-check pipeline catches it
- Demo 04: Neurosymbolic guardrails
  - Show business rule ignored in prompt
  - Symbolic rules enforced via framework hooks

### Part 3: Self-Correct and Deploy (15 minutes)
- Demo 05: Agent Control steering
  - Show hard block stopping the task
  - Steering message guides agent to self-correct
- Demo 06: Production on Amazon Bedrock AgentCore
  - Architecture walkthrough (AgentCore Gateway, Lambda tools, DynamoDB rules)
  - Show steering rule update without redeployment
  - Show graph-RAG Lambda integration with Neo4j AuraDB
  - Invoke deployed agent with AWS CLI

### Conclusion (5 minutes)
- Applicability to other frameworks (LangGraph, AutoGen, CrewAI)
- Open source repository walkthrough
- Q&A

---

## Why This Session Matters

**The problem is measurable:** Research shows RAG agents fabricate statistics 73% more often than Graph-RAG approaches (RAG-KG-IL, 2025). Agents with 29 tools waste 89% of tokens on irrelevant context. Single agents fail silently without validation.

**The techniques are proven:** Each demo grounds its approach in academic research (RAG-KG-IL, MetaRAG, Agent Control papers) and shows measurable improvements with real code.

**The deployment is practical:** Unlike pure research talks, this session shows the complete path from local experimentation to production deployment on AWS using Amazon Bedrock AgentCore, DynamoDB, Lambda, and Neo4j AuraDB.

**The patterns are portable:** While demos use Strands Agents and Amazon Bedrock AgentCore, the architectural patterns (Graph-RAG, semantic filtering, multi-agent validation, neurosymbolic rules, steering controls) apply to any agent framework.

---

## Speaker Notes

**To strengthen this submission:**

1. Add specific production metrics if you've deployed similar patterns (error reduction %, cost savings, latency improvements)
2. Include a failure story — "We deployed agents without validation and here's what broke in production"
3. Mention if you contributed to or collaborated with any of the research papers cited (RAG-KG-IL, MetaRAG, Agent Control)
4. Reference specific AWS customer use cases if you've worked with teams implementing these patterns

**Session differentiators:**

- Not a single-technique talk — shows five complementary approaches
- Not research-only — demonstrates production deployment on AWS
- Not framework-locked — patterns apply beyond Strands Agents and AgentCore
- Not just problems — shows working solutions with open source code

---

## Resources

- **Open source repository:** https://github.com/aws-samples/sample-why-agents-fail
- **All demos run locally** (01-05) or deploy to AWS (06) with CDK
- **Research papers cited:**
  - RAG-KG-IL: Multi-Agent Hybrid Framework (arXiv:2503.13514)
  - MetaRAG: Metamorphic Testing for Hallucination Detection (arXiv:2509.09360)
  - Agent Control: Steering vs blocking patterns

---

## Metadata

- **Word count (abstract):** 99 words
- **Word count (full proposal):** ~750 words
- **Level:** 300 (Advanced) — assumes familiarity with LLMs, agents, and AWS services
- **Conference:** AWS re:Invent 2026
- **Track:** Machine Learning and AI
- **Format:** Breakout (45 minutes)
- **Date created:** 2026-05-08
