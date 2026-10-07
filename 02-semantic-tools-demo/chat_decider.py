# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Same demo as chat.py, but the tool is chosen by a DECISION MODEL, not FAISS.

chat.py trims the agent to the top-k tools by vector similarity. Here a decision
model (strands-decider, the open-source Strands 2B) reads the request and picks
the single best tool, then the same before-invocation hook swaps just that tool
into the agent. The agent sees one tool instead of ~30.

Why a decision model instead of embeddings:
  * it returns a calibrated choice (a probability per tool), not a distance
  * no embedding index to build and no embedding tokens to pay per query
  * it generates no text, so there is nothing to parse

The 2B weights download on first run (Hugging Face) and then run locally on CPU.

Prerequisites:
  * a running Neo4j with the hotel graph (see demo 01's build_graph.py)
  * the decision model installed: `uv pip install strands-decider`
    (the first run downloads the ~2B weights from Hugging Face and caches them)

Run:
    AWS_PROFILE=<profile> AWS_REGION=us-east-1 python chat_decider.py
"""
import os

os.environ.setdefault("OTEL_SDK_DISABLED", "true")
# strands-decider (torch) and faiss both ship OpenMP; allow the duplicate on macOS.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
# the 2B weights are cached after the first download; stay offline afterwards.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from dotenv import load_dotenv
# Import strands_decider (torch) BEFORE semantic_tools (neo4j). Loading the neo4j
# driver's native libs before torch can crash the process with an OpenMP clash on
# some machines; this order avoids it.
from strands_decider.infer import load_engine
from strands_decider.schema import ChoiceQuestion
from strands import Agent
from strands.models import BedrockModel
from strands.session import FileSessionManager
from strands.hooks import HookProvider, HookRegistry, BeforeInvocationEvent

from semantic_tools import ALL_TOOLS

load_dotenv()

MODEL = BedrockModel(
    model_id="global.anthropic.claude-haiku-4-5-20251001-v1:0",
    region_name=os.getenv("AWS_REGION", "us-east-1"),
)
DECIDER_CHECKPOINT = "StrandsAgents/strands-decider-2B-hobson-v19"


class DeciderToolHook(HookProvider):
    """Pick one tool per request with a decision model, then swap it in.

    Mirrors SemanticToolHook, but the selection is a single bounded `choice`
    question answered by strands-decider instead of a FAISS nearest-neighbour.
    """

    def __init__(self, tools):
        self.tools = tools
        self._by_name = {t.tool_name: t for t in tools}
        self._criteria = {t.tool_name: t.tool_spec["description"] for t in tools}
        self._engine = load_engine(DECIDER_CHECKPOINT, device="cpu")
        self.last_selected = []

    def select(self, query):
        resp = self._engine.ask(query, {"tool": ChoiceQuestion(
            instructions="Which tool best answers this request?",
            criteria=self._criteria)})
        return [self._by_name[resp.answers["tool"].choice]]

    def register_hooks(self, registry: HookRegistry) -> None:
        registry.add_callback(BeforeInvocationEvent, self._trim)

    def _trim(self, event: BeforeInvocationEvent) -> None:
        msgs = event.messages or getattr(event.agent, "messages", [])
        query = ""
        for m in reversed(msgs):
            if m.get("role") == "user":
                query = "".join(b.get("text", "") for b in m.get("content", []))
                break
        if not query:
            return
        selected = self.select(query)
        self.last_selected = [t.tool_name for t in selected]
        reg = event.agent.tool_registry
        reg.registry.clear()
        reg.dynamic_tools.clear()
        for t in selected:
            reg.register_tool(t)


def main():
    print("Loading strands-decider 2B (first run downloads the weights)...")
    hook = DeciderToolHook(ALL_TOOLS)
    session = FileSessionManager(session_id="decider-tools-chat", storage_dir="./sessions/")
    agent = Agent(
        model=MODEL,
        system_prompt="You are a travel agent that helps people with hotels. Keep answers concise — at most two sentences.",
        tools=ALL_TOOLS,
        hooks=[hook],
        session_manager=session,
    )
    print(f"Travel assistant ready — {len(ALL_TOOLS)} tools, decision model picks one per question.")
    print("Memory persists across restarts. Ctrl-C to exit.\n")
    try:
        while True:
            q = input("you> ").strip()
            if not q:
                continue
            agent(q)
            print(f"\n  [decider picked: {hook.last_selected}]\n")
    except (KeyboardInterrupt, EOFError):
        print("\nBye!")


if __name__ == "__main__":
    main()
