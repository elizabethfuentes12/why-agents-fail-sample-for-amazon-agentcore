#!/usr/bin/env python3
"""
Multi-Agent Hallucination Detection Test
Based on: https://arxiv.org/pdf/2510.19507 (Teaming LLMs to Detect and Mitigate Hallucinations)
"""
import os
import warnings

# Suppress OpenTelemetry warnings
warnings.filterwarnings('ignore', message='Failed to detach context')
os.environ['OTEL_SDK_DISABLED'] = 'true'

from strands import Agent
from strands.models.openai import OpenAIModel
from strands.multiagent import Swarm
from tools import search_hotels, book_hotel, get_booking

# Model configuration
# Option 1: OpenAI (default - requires OPENAI_API_KEY env var)
MODEL = OpenAIModel(model_id="gpt-4o-mini")

# Option 2: Amazon Bedrock (uncomment to use - requires AWS credentials)
# MODEL = "us.anthropic.claude-3-haiku-20240307-v1:0"

# Option 3: Other providers - see documentation
# https://strandsagents.com/docs/user-guide/concepts/model-providers/

# Ground truth for validation
GROUND_TRUTH = {
    "grand_hotel": {"price": 200, "available": True},
    "budget_inn": {"price": 80, "available": True},
    "luxury_resort": {"price": 500, "available": False}
}

print("="*70)
print("HALLUCINATION DETECTION TEST: Single vs Multi-Agent")
print("="*70)

# TEST 1: Single Agent (Baseline - prone to hallucinations)
print("\n[TEST 1] Single Agent - Valid Booking")
single_agent = Agent(
    name="single",
    system_prompt="You are a hotel booking assistant. Use tools to complete requests.",
    tools=[search_hotels, book_hotel, get_booking],
    model=MODEL
)

result = single_agent("Book grand_hotel for John for 2 nights")
print(f"✓ Response: {result.message['content'][0]['text'][:100]}...")

# TEST 2: Single Agent - Invalid Hotel (hallucination test)
print("\n[TEST 2] Single Agent - Invalid Hotel (the_ritz_paris doesn't exist)")
result = single_agent("Book the_ritz_paris for Sarah for 3 nights")
print(f"⚠️  Response: {result.message['content'][0]['text'][:150]}...")

# TEST 3: Multi-Agent with Validation
print("\n[TEST 3] Multi-Agent - Valid Booking with Validation")

executor = Agent(
    name="executor",
    system_prompt="""Execute booking requests using tools.
After EVERY action, call handoff_to_agent to pass to 'validator'.""",
    tools=[search_hotels, book_hotel, get_booking],
    model=MODEL
)

validator = Agent(
    name="validator",
    system_prompt="""Validate booking responses. Check:
- Was the correct tool used?
- Is the response accurate?
Say VALID or HALLUCINATION with reasons.
Then call handoff_to_agent to pass to 'critic'.""",
    model=MODEL
)

critic = Agent(
    name="critic",
    system_prompt="""Final review. Say APPROVED or REJECTED with reasoning.
You are the last agent - do NOT hand off.""",
    model=MODEL
)

swarm = Swarm([executor, validator, critic], entry_point=executor, max_handoffs=5)

result = swarm("Book grand_hotel for John for 2 nights")
print(f"✓ Flow: {' → '.join([n.node_id for n in result.node_history])}")
print(f"✓ Status: {result.status}")

# TEST 4: Multi-Agent - Invalid Hotel Detection
print("\n[TEST 4] Multi-Agent - Invalid Hotel Detection")
result = swarm("Book the_ritz_paris for Sarah for 3 nights")
print(f"✓ Flow: {' → '.join([n.node_id for n in result.node_history])}")
print(f"✓ Status: {result.status}")
final_text = result.results[result.node_history[-1].node_id].result.message['content']
if final_text:
    print(f"✓ Final verdict: {final_text[0]['text'][:200]}...")

print("\n" + "="*70)
print("CONCLUSION:")
print("- Single agent may fabricate responses for invalid hotels")
print("- Multi-agent system validates and catches hallucinations")
print("- Executor → Validator → Critic pattern provides cross-validation")
print("="*70)
