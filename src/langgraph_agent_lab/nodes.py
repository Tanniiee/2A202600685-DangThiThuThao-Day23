"""Node functions for the LangGraph workflow.

Each function receives AgentState and returns a partial state update dict.
Do NOT mutate input state -- return new values only.

LLM REQUIREMENT:
- classify_node MUST use a real LLM call (structured output for intent classification)
- answer_node MUST use a real LLM call (grounded response generation)
- evaluate_node SHOULD use LLM-as-judge (bonus points; heuristic acceptable for base score)
"""

from __future__ import annotations

import os

from pydantic import BaseModel

from .state import AgentState, ApprovalDecision, make_event


# --- EXAMPLE: working node (provided for reference) ---
def intake_node(state: AgentState) -> dict:
    """Normalize raw query. This node is provided as a working example."""
    query = state.get("query", "").strip()
    return {
        "query": query,
        "messages": [f"intake:{query[:40]}"],
        "events": [make_event("intake", "completed", "query normalized")],
    }


# --- Pydantic model for LLM structured output ---
class ClassificationResult(BaseModel):
    """Structured output schema for the classify node."""

    route: str       # one of: simple, tool, missing_info, risky, error
    risk_level: str  # "high" or "low"


CLASSIFY_SYSTEM = """You are a customer support ticket classifier.

Classify the user query into exactly ONE of these routes:
- "simple": General FAQ, how-to questions, password reset, general info -- no external tool needed
- "tool": Requires looking up live data (order status, account info, tracking numbers)
- "missing_info": Query is too vague or incomplete -- cannot be answered without clarification
- "risky": Destructive or financial actions (refunds, deletions, sending emails, account changes)
- "error": Indicates a system failure, timeout, technical error, or cannot-recover state

Priority order (if multiple apply): risky > tool > missing_info > error > simple

Set risk_level to "high" for risky routes, "low" for everything else.
"""


def classify_node(state: AgentState) -> dict:
    """Classify the query into a route using an LLM with structured output."""
    from .llm import get_llm

    llm = get_llm()
    structured_llm = llm.with_structured_output(ClassificationResult)

    result: ClassificationResult = structured_llm.invoke([
        {"role": "system", "content": CLASSIFY_SYSTEM},
        {"role": "user", "content": state.get("query", "")},
    ])

    valid_routes = {"simple", "tool", "missing_info", "risky", "error"}
    route = result.route if result.route in valid_routes else "simple"
    risk_level = "high" if route == "risky" else result.risk_level

    return {
        "route": route,
        "risk_level": risk_level,
        "messages": [f"classified:{route}"],
        "events": [make_event("classify", "completed", f"route={route} risk={risk_level}")],
    }


def tool_node(state: AgentState) -> dict:
    """Execute a mock tool call with transient error simulation for retry testing."""
    route = state.get("route", "")
    attempt = state.get("attempt", 0)

    if route == "error" and attempt < 2:
        result = f"ERROR: transient failure on attempt {attempt} (simulated)"
        return {
            "tool_results": [result],
            "events": [make_event("tool", "error", result, metadata={"attempt": attempt})],
        }

    query = state.get("query", "")
    result = f"MOCK_TOOL_SUCCESS: Retrieved data for '{query[:60]}' on attempt {attempt}"
    return {
        "tool_results": [result],
        "events": [make_event("tool", "completed", "tool call succeeded", metadata={"attempt": attempt})],
    }


def evaluate_node(state: AgentState) -> dict:
    """Evaluate tool result -- the retry-loop gate.

    Heuristic: if the latest tool result contains "ERROR", mark as needs_retry.
    """
    tool_results = state.get("tool_results") or []
    latest = tool_results[-1] if tool_results else ""
    evaluation_result = "needs_retry" if "ERROR" in latest else "success"

    return {
        "evaluation_result": evaluation_result,
        "events": [make_event("evaluate", "completed", f"evaluation={evaluation_result}")],
    }


ANSWER_SYSTEM = """You are a helpful customer support agent.

Generate a clear, concise response to the user query. Ground your answer in any tool results
or approval decisions provided. Be specific and actionable.
Do NOT invent data that is not in the provided context.
"""


def answer_node(state: AgentState) -> dict:
    """Generate a final response using an LLM grounded in available context."""
    from .llm import get_llm

    llm = get_llm()

    context_parts: list[str] = [f"User query: {state.get('query', '')}"]

    tool_results = state.get("tool_results") or []
    if tool_results:
        lines = "\n".join(f"  - {r}" for r in tool_results)
        context_parts.append(f"Tool results:\n{lines}")

    approval = state.get("approval")
    if approval:
        status = "APPROVED" if approval.get("approved") else "REJECTED"
        comment = approval.get("comment", "")
        context_parts.append(f"Approval decision: {status}. {comment}")

    user_content = "\n\n".join(context_parts)

    response = llm.invoke([
        {"role": "system", "content": ANSWER_SYSTEM},
        {"role": "user", "content": user_content},
    ])

    answer = response.content if hasattr(response, "content") else str(response)

    return {
        "final_answer": answer,
        "messages": [f"answer:{answer[:60]}"],
        "events": [make_event("answer", "completed", "LLM answer generated")],
    }


def ask_clarification_node(state: AgentState) -> dict:
    """Ask for missing information instead of hallucinating."""
    query = state.get("query", "")
    question = (
        f"To help with '{query}', could you provide more details? "
        "Specifically: what item, order, or account are you referring to, "
        "and what outcome are you looking for?"
    )
    return {
        "pending_question": question,
        "final_answer": question,
        "messages": ["clarify:asked for missing info"],
        "events": [make_event("clarify", "completed", "clarification question sent")],
    }


def risky_action_node(state: AgentState) -> dict:
    """Prepare a risky action descriptor for human approval."""
    query = state.get("query", "")
    proposed = (
        f"PROPOSED ACTION: '{query}'. "
        "This action is irreversible or financially significant and requires explicit human approval."
    )
    return {
        "proposed_action": proposed,
        "messages": ["risky_action:prepared for approval"],
        "events": [make_event("risky_action", "completed", "proposed action prepared")],
    }


def approval_node(state: AgentState) -> dict:
    """Human-in-the-loop approval step.

    Default: mock approval (approved=True) so tests and CI run offline.
    Set LANGGRAPH_INTERRUPT=true in .env for real HITL via interrupt().
    """
    use_interrupt = os.getenv("LANGGRAPH_INTERRUPT", "").lower() == "true"

    if use_interrupt:
        from langgraph.types import interrupt
        decision_raw = interrupt({
            "action": state.get("proposed_action", ""),
            "risk": state.get("risk_level", "high"),
            "evidence": state.get("tool_results", []),
        })
        decision = ApprovalDecision(
            approved=bool(decision_raw.get("approved", False)),
            reviewer=decision_raw.get("reviewer", "human"),
            comment=decision_raw.get("comment", ""),
        )
    else:
        decision = ApprovalDecision(
            approved=True,
            reviewer="mock-reviewer",
            comment="auto-approved in mock mode",
        )

    return {
        "approval": decision.model_dump(),
        "messages": [f"approval:{'approved' if decision.approved else 'rejected'}"],
        "events": [make_event("approval", "completed", f"decision={decision.approved}")],
    }


def retry_or_fallback_node(state: AgentState) -> dict:
    """Record a retry attempt -- increments counter and logs the failure."""
    current_attempt = state.get("attempt", 0)
    new_attempt = current_attempt + 1
    error_msg = f"retry attempt {new_attempt}: tool result was unsatisfactory or route is error"

    return {
        "attempt": new_attempt,
        "errors": [error_msg],
        "events": [make_event("retry", "retrying", error_msg, metadata={"attempt": new_attempt})],
    }


def dead_letter_node(state: AgentState) -> dict:
    """Handle unresolvable failures after max retries exceeded."""
    attempts = state.get("attempt", 0)
    query = state.get("query", "")
    msg = (
        f"Unable to process your request after {attempts} attempt(s): '{query[:80]}'. "
        "This issue has been escalated to our support team for manual review."
    )
    return {
        "final_answer": msg,
        "messages": ["dead_letter:escalated"],
        "events": [make_event("dead_letter", "failed", "max retries exceeded, escalating")],
    }


def finalize_node(state: AgentState) -> dict:
    """Emit a final audit event. All routes must pass through here before END."""
    return {
        "events": [make_event("finalize", "completed", "workflow finished")],
    }
