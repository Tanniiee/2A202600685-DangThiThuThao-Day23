"""Graph construction.

This module is intentionally import-safe. It imports LangGraph only inside the builder so unit tests
that check schema/metrics can run even if students are still debugging graph wiring.
"""

from __future__ import annotations

from typing import Any

from .state import AgentState


def build_graph(checkpointer: Any | None = None):
    """Build and compile the LangGraph workflow.

    Graph architecture:

    START → intake → classify → [conditional: route_after_classify]
      simple       → answer → finalize → END
      tool         → tool → evaluate → [conditional: route_after_evaluate]
                                          success     → answer → finalize → END
                                          needs_retry → retry → [conditional: route_after_retry]
                                                                   attempt < max → tool (loop)
                                                                   attempt >= max → dead_letter → finalize → END
      missing_info → clarify → finalize → END
      risky        → risky_action → approval → [conditional: route_after_approval]
                                                  approved → tool → evaluate → ...
                                                  rejected → clarify → finalize → END
      error        → tool (fails internally) → evaluate → retry loop → tool or dead_letter
    """
    from langgraph.graph import END, START, StateGraph

    from .nodes import (
        answer_node,
        approval_node,
        ask_clarification_node,
        classify_node,
        dead_letter_node,
        evaluate_node,
        finalize_node,
        intake_node,
        retry_or_fallback_node,
        risky_action_node,
        tool_node,
    )
    from .routing import (
        route_after_approval,
        route_after_classify,
        route_after_evaluate,
        route_after_retry,
    )

    graph = StateGraph(AgentState)

    # ── Register all 11 nodes ────────────────────────────────────────────
    graph.add_node("intake", intake_node)
    graph.add_node("classify", classify_node)
    graph.add_node("tool", tool_node)
    graph.add_node("evaluate", evaluate_node)
    graph.add_node("answer", answer_node)
    graph.add_node("clarify", ask_clarification_node)
    graph.add_node("risky_action", risky_action_node)
    graph.add_node("approval", approval_node)
    graph.add_node("retry", retry_or_fallback_node)
    graph.add_node("dead_letter", dead_letter_node)
    graph.add_node("finalize", finalize_node)

    # ── Fixed edges ───────────────────────────────────────────────────────
    graph.add_edge(START, "intake")
    graph.add_edge("intake", "classify")
    graph.add_edge("tool", "evaluate")          # tool always feeds evaluate
    graph.add_edge("risky_action", "approval")  # risky action always needs approval
    graph.add_edge("answer", "finalize")         # answer always finalizes
    graph.add_edge("clarify", "finalize")        # clarify always finalizes
    graph.add_edge("dead_letter", "finalize")    # dead letter always finalizes
    graph.add_edge("finalize", END)              # finalize always ends

    # ── Conditional edges ─────────────────────────────────────────────────
    # After classify: branch to simple/tool/missing_info/risky/error paths
    graph.add_conditional_edges("classify", route_after_classify)

    # After evaluate: retry loop gate (needs_retry → retry, success → answer)
    graph.add_conditional_edges("evaluate", route_after_evaluate)

    # After retry: bounded retry check (attempt < max → tool, else → dead_letter)
    graph.add_conditional_edges("retry", route_after_retry)

    # After approval: approved → tool, rejected → clarify
    graph.add_conditional_edges("approval", route_after_approval)

    return graph.compile(checkpointer=checkpointer)
