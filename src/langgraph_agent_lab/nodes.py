"""Node functions for the LangGraph workflow.

Each function receives AgentState and returns a partial state update dict.
Do NOT mutate input state — return new values only.

LLM REQUIREMENT:
- classify_node MUST use a real LLM call (structured output for intent classification)
- answer_node MUST use a real LLM call (grounded response generation)
- evaluate_node SHOULD use LLM-as-judge (bonus points; heuristic acceptable for base score)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from .llm import get_llm
from .state import AgentState, ApprovalDecision, make_event


class ClassificationResult(BaseModel):
    """Structured classification payload returned by the LLM."""

    route: Literal["simple", "tool", "missing_info", "risky", "error"] = Field(
        description="Best support workflow route for the user query."
    )
    rationale: str = Field(description="Brief reason for the selected route.")


def _load_env_file() -> None:
    """Load simple KEY=value pairs from .env when the shell has not exported them."""
    env_path = Path(".env")
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def _message_content(response: object) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, list):
        return "\n".join(str(item) for item in content).strip()
    return str(content).strip()


# ─── EXAMPLE: working node (provided for reference) ──────────────────
def intake_node(state: AgentState) -> dict:
    """Normalize raw query. This node is provided as a working example."""
    query = state.get("query", "").strip()
    return {
        "query": query,
        "messages": [f"intake:{query[:40]}"],
        "events": [make_event("intake", "completed", "query normalized")],
    }


# ─── TODO(student): implement ALL nodes below ────────────────────────


def classify_node(state: AgentState) -> dict:
    """Classify the query into a route using an LLM.

    *** MUST use a real LLM call — keyword-only heuristics will lose points. ***

    Use .with_structured_output() or equivalent to get reliable enum classification.
    The LLM should classify into one of: simple, tool, missing_info, risky, error.

    Hints:
    - See llm.py for the get_llm() helper
    - Use Pydantic model or TypedDict with .with_structured_output()
    - Set risk_level to "high" for risky routes, "low" otherwise
    - Priority guide: risky > tool > missing_info > error > simple

    Return: {"route": str, "risk_level": str, "events": [make_event(...)]}
    """
    _load_env_file()
    query = state.get("query", "")
    classifier = get_llm(temperature=0.0).with_structured_output(ClassificationResult)
    result = classifier.invoke(
        [
            (
                "system",
                "Classify support tickets into exactly one route: risky, tool, "
                "missing_info, error, or simple. Priority order is risky > tool > "
                "missing_info > error > simple. Risky means side effects such as "
                "refunds, deletes, cancellations, sending email, or account changes. "
                "Tool means lookup/search/status requests. Missing_info means the "
                "request is too vague to act on. Error means system failures, "
                "timeouts, crashes, or unrecoverable processing failures. Simple "
                "means general support guidance answerable without tools.",
            ),
            ("human", f"Ticket: {query}"),
        ]
    )
    route = result.route
    return {
        "route": route,
        "risk_level": "high" if route == "risky" else "low",
        "messages": [f"classify:{route}"],
        "events": [
            make_event(
                "classify",
                "completed",
                "query classified",
                route=route,
                rationale=result.rationale,
            )
        ],
    }


def tool_node(state: AgentState) -> dict:
    """Execute a mock tool call.

    Simulate transient failures for error-route scenarios to test retry loops.

    Requirements:
    - Read current attempt count from state
    - If route is "error" and attempt < 2: return error result (string containing "ERROR")
    - Otherwise: return a mock success result string
    - Append result to tool_results list

    Return: {"tool_results": [result_string], "events": [make_event(...)]}
    """
    route = state.get("route", "simple")
    attempt = int(state.get("attempt", 0))
    query = state.get("query", "")
    proposed_action = state.get("proposed_action")

    if route == "error" and attempt < 2:
        result = f"ERROR transient tool failure on attempt {attempt}: simulated timeout"
        status = "error"
    elif route == "risky":
        result = f"MOCK_TOOL success: approved action executed - {proposed_action or query}"
        status = "success"
    elif route == "tool":
        result = f"MOCK_TOOL success: lookup result for '{query}' is available"
        status = "success"
    else:
        result = f"MOCK_TOOL success: processed '{query}'"
        status = "success"

    return {
        "tool_results": [result],
        "messages": [f"tool:{status}"],
        "events": [make_event("tool", status, "mock tool executed", attempt=attempt, route=route)],
    }


def evaluate_node(state: AgentState) -> dict:
    """Evaluate tool results — the retry-loop gate.

    Check whether the latest tool result is satisfactory or needs retry.

    SHOULD use LLM-as-judge for bonus points. Heuristic (e.g., check for "ERROR" substring)
    is acceptable for base score.

    Requirements:
    - Read the latest entry from tool_results
    - Set evaluation_result to "needs_retry" or "success"
    - This field drives route_after_evaluate conditional edge

    Note: You may need to add 'evaluation_result' to AgentState if not present.

    Return: {"evaluation_result": str, "events": [make_event(...)]}
    """
    latest_result = (state.get("tool_results") or [""])[-1]
    evaluation_result = "needs_retry" if "ERROR" in latest_result.upper() else "success"
    return {
        "evaluation_result": evaluation_result,
        "messages": [f"evaluate:{evaluation_result}"],
        "events": [
            make_event(
                "evaluate",
                "completed",
                "tool result evaluated",
                evaluation_result=evaluation_result,
            )
        ],
    }


def answer_node(state: AgentState) -> dict:
    """Generate a final response using an LLM.

    *** MUST use a real LLM call — hardcoded strings will lose points. ***

    The LLM should generate a helpful response grounded in available context:
    - tool_results (if any)
    - approval decision (if risky route)
    - original query

    Return: {"final_answer": str, "events": [make_event(...)]}
    """
    _load_env_file()
    query = state.get("query", "")
    context = {
        "route": state.get("route"),
        "tool_results": state.get("tool_results", []),
        "approval": state.get("approval"),
        "proposed_action": state.get("proposed_action"),
    }
    response = get_llm(temperature=0.2).invoke(
        [
            (
                "system",
                "You are a concise support agent. Answer only from the provided "
                "workflow context. If a tool result is present, ground the answer "
                "in it. If approval is present, mention whether the approved action "
                "was completed. Do not invent account data.",
            ),
            ("human", f"User query: {query}\nWorkflow context: {context}"),
        ]
    )
    answer = _message_content(response)
    return {
        "final_answer": answer,
        "messages": ["answer:completed"],
        "events": [make_event("answer", "completed", "final answer generated")],
    }


def ask_clarification_node(state: AgentState) -> dict:
    """Ask for missing information instead of hallucinating.

    Generate a specific clarification question based on the vague/incomplete query.

    Note: You may need to add 'pending_question' to AgentState if not present.

    Return: {"pending_question": str, "final_answer": str, "events": [make_event(...)]}
    """
    query = state.get("query", "")
    pending_question = (
        "Could you share the specific account, order, or issue details you want help with?"
    )
    if "fix" in query.lower():
        pending_question = (
            "What exactly is broken, and what error message or account/order ID should I check?"
        )
    return {
        "pending_question": pending_question,
        "final_answer": pending_question,
        "messages": ["clarify:pending"],
        "events": [make_event("clarify", "completed", "clarification requested")],
    }


def risky_action_node(state: AgentState) -> dict:
    """Prepare a risky action for human approval.

    Describe the proposed action and why it requires approval.

    Note: You may need to add 'proposed_action' to AgentState if not present.

    Return: {"proposed_action": str, "events": [make_event(...)]}
    """
    query = state.get("query", "")
    proposed_action = (
        f"Prepare high-risk support action for approval: {query}. "
        "This requires review because it may change customer data, send messages, or move money."
    )
    return {
        "proposed_action": proposed_action,
        "risk_level": "high",
        "messages": ["risky_action:prepared"],
        "events": [make_event("risky_action", "completed", "risky action prepared")],
    }


def approval_node(state: AgentState) -> dict:
    """Human-in-the-loop approval step.

    Default behavior: mock approval (approved=True) so tests and CI run offline.
    Extension: if env LANGGRAPH_INTERRUPT=true, use langgraph.types.interrupt() for real HITL.

    Return:
        {"approval": {"approved": bool, "reviewer": str, "comment": str}, "events": [...]}
    """
    proposed_action = state.get("proposed_action") or state.get("query", "")
    if os.getenv("LANGGRAPH_INTERRUPT", "").lower() == "true":
        from langgraph.types import interrupt

        payload = interrupt(
            {
                "question": "Approve this risky action?",
                "proposed_action": proposed_action,
            }
        )
        approved = bool(payload.get("approved")) if isinstance(payload, dict) else bool(payload)
        comment = payload.get("comment", "") if isinstance(payload, dict) else ""
        reviewer = (
            payload.get("reviewer", "human-reviewer")
            if isinstance(payload, dict)
            else "human-reviewer"
        )
        decision = ApprovalDecision(approved=approved, reviewer=reviewer, comment=comment)
    else:
        decision = ApprovalDecision(
            approved=True,
            reviewer="mock-reviewer",
            comment="Mock approval granted for lab execution.",
        )
    return {
        "approval": decision.model_dump(),
        "messages": [f"approval:{decision.approved}"],
        "events": [
            make_event(
                "approval",
                "completed",
                "approval decision recorded",
                approved=decision.approved,
                reviewer=decision.reviewer,
            )
        ],
    }


def retry_or_fallback_node(state: AgentState) -> dict:
    """Record a retry attempt.

    Increment the attempt counter and log the transient failure.

    Requirements:
    - Read current attempt from state, increment by 1
    - Add an error message to errors list
    - Return updated attempt count

    Return: {"attempt": int, "errors": [str], "events": [make_event(...)]}
    """
    next_attempt = int(state.get("attempt", 0)) + 1
    latest_result = (state.get("tool_results") or ["initial retry requested"])[-1]
    error = f"attempt {next_attempt}: {latest_result}"
    return {
        "attempt": next_attempt,
        "errors": [error],
        "messages": [f"retry:{next_attempt}"],
        "events": [
            make_event("retry", "completed", "retry attempt recorded", attempt=next_attempt)
        ],
    }


def dead_letter_node(state: AgentState) -> dict:
    """Handle unresolvable failures after max retries exceeded.

    This is the third layer: retry → fallback → dead letter.
    Log the failure and set a final_answer explaining that the request could not be completed.

    Return: {"final_answer": str, "events": [make_event(...)]}
    """
    attempt = int(state.get("attempt", 0))
    max_attempts = int(state.get("max_attempts", 3))
    answer = (
        "I could not complete this request after the allowed retry attempts. "
        "The issue has been moved to the dead-letter queue for manual review."
    )
    return {
        "final_answer": answer,
        "messages": ["dead_letter:completed"],
        "events": [
            make_event(
                "dead_letter",
                "completed",
                "max retry attempts exhausted",
                attempt=attempt,
                max_attempts=max_attempts,
            )
        ],
    }


def finalize_node(state: AgentState) -> dict:
    """Emit a final audit event. All routes must pass through here before END.

    Return: {"events": [make_event("finalize", "completed", "workflow finished")]}
    """
    return {
        "messages": ["finalize:completed"],
        "events": [make_event("finalize", "completed", "workflow finished")],
    }
