"""Context-Aware Agent for AgentCore Runtime with AgentCore Memory.

Uses AgentCore Memory for automatic context retention:
- Short-term: DynamoDB conversation history (turns within a session)
- Long-term: Semantic facts and user preferences (persists across sessions)
"""

import os
import logging
from typing import Any, Dict

from bedrock_agentcore import BedrockAgentCoreApp
from strands import Agent
from strands.models import BedrockModel
from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig
from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

MEMORY_ID = os.getenv("BEDROCK_AGENTCORE_MEMORY_ID")
REGION = os.getenv("AWS_REGION", "us-east-1")
MODEL_ID = "us.anthropic.claude-sonnet-4-20250514-v1:0"

SYSTEM_PROMPT = """You are a context-aware assistant with persistent memory across conversations.

Your memory system automatically:
- Stores facts from your responses in long-term memory
- Retrieves relevant context from past conversations
- Remembers information about people, companies, and events

## How memory works

When you respond, the memory system extracts facts from your answer and stores them automatically.
Before each conversation, relevant facts are retrieved and added to your context.

**IMPORTANT**: State facts clearly in your responses - that's what gets stored in memory.

## Workflow

When the user shares information about people, companies, or events:
1. Acknowledge what they told you
2. Include key details explicitly in your response
3. Example: "I'll remember that John Smith works at Microsoft as a Senior Engineer."

When the user asks about something:
1. Check if you have relevant information in your context
2. Answer based on what you remember
3. If you don't have information, say so explicitly

The memory system handles storage and retrieval automatically - just focus on giving helpful, fact-rich responses.
"""

app = BedrockAgentCoreApp()

_agent = None
_current_session = None


def get_or_create_agent(actor_id: str, session_id: str) -> Agent:
    """Get or create a Strands agent with AgentCore Memory.

    Args:
        actor_id: Identifies the USER - for long-term memory (facts, preferences).
                  Persists across sessions.
        session_id: Identifies the CONVERSATION - for short-term memory (turns).
                    Provided automatically by AgentCore Runtime.

    Returns:
        Agent with memory session manager configured
    """
    global _agent, _current_session

    # Reuse agent if same session
    if _agent is not None and _current_session == session_id:
        logger.info("Reusing existing agent for session=%s", session_id)
        return _agent

    # Configure memory with automatic retrieval
    session_manager = None
    if MEMORY_ID:
        # AgentCoreMemoryConfig without retrieval_config will use default retrieval
        memory_config = AgentCoreMemoryConfig(
            memory_id=MEMORY_ID,
            session_id=session_id,
            actor_id=actor_id,
        )
        session_manager = AgentCoreMemorySessionManager(memory_config, REGION)
        logger.info("✅ Memory configured: memory_id=%s, actor=%s, session=%s", MEMORY_ID, actor_id, session_id)
    else:
        logger.warning("⚠️  BEDROCK_AGENTCORE_MEMORY_ID not set, running without memory")

    # Create agent with memory session manager
    _agent = Agent(
        model=BedrockModel(model_id=MODEL_ID, region_name=REGION),
        system_prompt=SYSTEM_PROMPT,
        tools=[],  # No explicit memory tools - memory is automatic via session_manager
        session_manager=session_manager,
    )
    _current_session = session_id
    logger.info("✅ Agent created: model=%s, actor=%s, session=%s", MODEL_ID, actor_id, session_id)

    return _agent


@app.entrypoint
def invoke(payload: Dict[str, Any], context=None) -> str:
    """Entry point for AgentCore Runtime invocations.

    Args:
        payload: Request payload with 'prompt' and 'actor_id'
        context: Request context with session_id

    Returns:
        Agent response as string
    """
    # Get prompt from payload
    prompt = payload if isinstance(payload, str) else payload.get("prompt", "")

    # Get session_id from context (provided by AgentCore Runtime via runtimeSessionId)
    session_id = getattr(context, "session_id", None) or "default-session"

    # Get actor_id from payload (caller must provide)
    actor_id = payload.get("actor_id")
    if not actor_id and context:
        # Fallback: check custom header
        headers = getattr(context, "request_headers", None) or {}
        actor_id = headers.get("X-Amzn-Bedrock-AgentCore-Runtime-Custom-Actor-Id")
    if not actor_id:
        # Fallback: use context user_id
        actor_id = getattr(context, "user_id", None)
    if not actor_id:
        actor_id = "default-actor"

    logger.info("📨 Invoke: session=%s, actor=%s", session_id, actor_id)
    logger.info("💬 Prompt: %s", prompt[:100] + ("..." if len(prompt) > 100 else ""))

    # Create or reuse agent with memory
    agent = get_or_create_agent(actor_id=actor_id, session_id=session_id)

    # Run agent - memory retrieval happens automatically before this call
    result = agent(prompt)

    logger.info("✅ Response generated")
    return str(result)


if __name__ == "__main__":
    app.run()
