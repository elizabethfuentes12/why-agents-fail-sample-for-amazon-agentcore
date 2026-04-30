"""
Steering Controls - Server-managed policies as Python data structures
======================================================================

In the Strands version (Demo 05), controls live on an Agent Control server
and are evaluated remotely. Here we implement the same concept locally
to show how STEER and DENY controls work, without requiring a server.

In production (Demo 06), these would be DynamoDB items:
    {
        "rule_id": "max-guests",
        "action": "book",
        "condition_field": "guests",
        "operator": "gt",
        "threshold": 10,
        "fail_message": "Guest count exceeds maximum of 10",
        "steer_message": "Reduce to 10, proceed, inform user...",
        "enabled": True
    }

CONTROL TYPES:
    STEER: Evaluates LLM output text -> if violation found, sends guidance
           back to the LLM so it can retry with corrected parameters.
           The task COMPLETES with adjusted values.

    DENY:  Evaluates tool input params -> if violation found, hard-blocks
           the tool call. The task FAILS (user must fix the issue).
"""
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Control:
    """A server-managed policy that evaluates agent behavior.

    Attributes:
        name: Unique identifier for the control
        description: Human-readable description
        decision: "steer" or "deny"
        scope: What to evaluate - "llm_output" or "tool_input"
        tool_name: For tool_input scope, which tool to check (None = all)
        pattern: Regex pattern to detect violations
        fail_message: Message explaining the violation
        steer_message: Guidance for the agent to self-correct (steer only)
        enabled: Whether the control is active
    """

    name: str
    description: str
    decision: str  # "steer" or "deny"
    scope: str  # "llm_output" or "tool_input"
    tool_name: Optional[str]  # specific tool or None for all
    pattern: str  # regex pattern
    fail_message: str
    steer_message: str = ""  # only for steer decisions
    enabled: bool = True
    tags: list[str] = field(default_factory=list)


# These controls mirror what setup_controls.py creates on the Agent Control server.
# Same logic, same patterns, same messages — just defined locally.

CONTROLS = [
    # Control 1: STEER at LLM output level — too many guests
    # When the LLM describes a booking with > 10 guests, steer it to reduce.
    # Regex matches "11 guests" through "99 guests" in the LLM's text output.
    Control(
        name="steer-max-guests",
        description="Guide agent to reduce guest count when exceeding maximum of 10",
        decision="steer",
        scope="llm_output",
        tool_name=None,  # evaluated on LLM text, not tool params
        pattern=r"(1[1-9]|[2-9]\d)\s*guest",
        fail_message="Guest count exceeds maximum of 10",
        steer_message=(
            "The booking has more than 10 guests, which exceeds the hotel maximum "
            "capacity of 10. Reduce the guest count to 10, retry the booking, and "
            "inform the user that the maximum capacity is 10 guests so the booking "
            "was adjusted accordingly."
        ),
        tags=["booking", "steer", "capacity"],
    ),
    # Control 2: DENY at tool level — confirm without payment
    # When confirm_booking is called, check if any booking ID is present.
    # In the real system, this would check if payment exists in state.
    # Here we simplify to show the DENY pattern.
    Control(
        name="deny-no-payment",
        description="Block booking confirmation without prior payment",
        decision="deny",
        scope="tool_input",
        tool_name="confirm_booking",
        pattern=r"BK\d{3}",
        fail_message="Payment must be processed before confirming a booking",
        tags=["booking", "deny", "payment"],
    ),
]


def evaluate_controls(
    text: str,
    scope: str,
    tool_name: str = None,
) -> tuple[Optional[Control], Optional[re.Match]]:
    """Evaluate text against all active controls for a given scope.

    Returns the first matching control and its regex match, or (None, None).

    This is the local equivalent of what the Agent Control server does:
    1. Filter controls by scope (llm_output or tool_input)
    2. Filter by tool_name if applicable
    3. Run regex evaluator against the text
    4. Return first match
    """
    for control in CONTROLS:
        if not control.enabled:
            continue
        if control.scope != scope:
            continue
        if control.tool_name and control.tool_name != tool_name:
            continue

        match = re.search(control.pattern, text)
        if match:
            return control, match

    return None, None
