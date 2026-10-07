# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Model routing with Jev as the classifier.

Strands' ModelRouter picks which model serves each invocation. The built-in
ClassifierStrategy uses a chat model to choose; here we plug in a *decision
model* (Jev, via OpenRouter) as the classifier instead. Jev answers one bounded
choice question — "which candidate fits this request?" — with a calibrated
probability and no generated text, so the routing decision is fast and cheap.

    pip install "strands-decider[jev]"      # typesafe-sdk
    export OPENROUTER_API_KEY=sk-or-...

Run:
    python examples/model_routing_with_jev.py
"""
from __future__ import annotations

import asyncio
import os
from typing import Any

from strands import Agent
from strands.models import (
    BedrockModel,
    ModelRouter,
    RoutingCandidate,
    RoutingContext,
    RoutingStrategy,
)
from typesafe_sdk import AsyncTypeSafeClient, Choice


class JevRoutingStrategy(RoutingStrategy):
    """Route each invocation with Jev: one bounded choice over the candidates.

    Jev decides the opening candidate from the request. On a failed serving
    attempt it declines (returns None), so the router surfaces the error rather
    than cycling — same contract as the built-in ClassifierStrategy.
    """

    def __init__(self) -> None:
        self._jev = AsyncTypeSafeClient(
            api_key=os.environ["OPENROUTER_API_KEY"],
            base_url="https://openrouter.ai/api",      # SDK appends /v1/systemone
            model="~typesafe/jev-latest",
        )

    async def select(self, context: RoutingContext, **kwargs: Any) -> RoutingCandidate | None:
        if context.attempts:            # only choose the opening candidate
            return None
        query = ""
        for m in reversed(context.messages):
            if m.get("role") == "user":
                query = "".join(b.get("text", "") for b in m.get("content", []) if "text" in b)
                break
        criteria = {c.name: (c.description or c.name) for c in context.candidates}
        resp = await self._jev.system_one(
            state=query,
            questions={"model": Choice(
                instructions="Which model should handle this request?",
                criteria=criteria)},
        )
        pick = resp.answers["model"].choice
        for c in context.candidates:
            if c.name == pick:
                return c
        return None


async def main() -> None:
    routine = RoutingCandidate(
        BedrockModel(model_id="us.amazon.nova-lite-v1:0", region_name="us-east-1"),
        name="routine",
        description="Short factual questions and routine requests.",
    )
    advanced = RoutingCandidate(
        BedrockModel(model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0", region_name="us-east-1"),
        name="advanced",
        description="Multi-step reasoning, systems design, troubleshooting.",
    )
    router = ModelRouter(models=[routine, advanced], strategy=JevRoutingStrategy())
    agent = Agent(model=router, callback_handler=None)

    for q in ["What time zone is Tokyo in?",
              "Design a rollback-safe migration from regional to global idempotency keys."]:
        r = await agent.invoke_async(q)
        print(f"Q: {q[:50]}\n   -> {str(r)[:80]}\n")


if __name__ == "__main__":
    asyncio.run(main())
