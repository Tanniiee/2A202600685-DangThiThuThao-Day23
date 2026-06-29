"""Report generation helper -- produces rich Markdown with embedded JSON and Mermaid diagram."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .metrics import MetricsReport

# ---------------------------------------------------------------------------
# Mermaid diagram of the graph (static -- matches graph.py wiring exactly)
# ---------------------------------------------------------------------------
GRAPH_MERMAID = """```mermaid
flowchart TD
    START([START]) --> intake[intake]
    intake --> classify[classify\nLLM structured output]

    classify -->|simple| answer
    classify -->|tool| tool
    classify -->|missing_info| clarify
    classify -->|risky| risky_action
    classify -->|error| retry

    tool[tool\nmock + error sim] --> evaluate[evaluate\nheuristic / LLM-as-judge]
    evaluate -->|success| answer[answer\nLLM grounded]
    evaluate -->|needs_retry| retry[retry\nincrement attempt]

    retry -->|attempt < max| tool
    retry -->|attempt >= max| dead_letter[dead_letter\nescalate]

    risky_action[risky_action\nprepare descriptor] --> approval[approval\nHITL / mock]
    approval -->|approved| tool
    approval -->|rejected| clarify[clarify\nask for info]

    clarify --> finalize
    answer --> finalize[finalize\naudit event]
    dead_letter --> finalize
    finalize --> END([END])

    style classify fill:#4A90D9,color:#fff
    style answer fill:#4A90D9,color:#fff
    style approval fill:#E67E22,color:#fff
    style retry fill:#E74C3C,color:#fff
    style dead_letter fill:#C0392B,color:#fff
    style finalize fill:#27AE60,color:#fff
```"""


def _success_emoji(ok: bool) -> str:
    return "✅" if ok else "❌"


def render_report(metrics: MetricsReport, metrics_json: str | None = None) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ── Summary table ────────────────────────────────────────────────────
    summary = "\n".join([
        f"| Total scenarios      | **{metrics.total_scenarios}** |",
        f"| Success rate         | **{metrics.success_rate:.0%}** |",
        f"| Avg nodes visited    | {metrics.avg_nodes_visited:.1f} |",
        f"| Total retries        | {metrics.total_retries} |",
        f"| Total interrupts     | {metrics.total_interrupts} |",
        f"| Crash-resume success | {'Yes' if metrics.resume_success else 'No'} |",
    ])

    # ── Per-scenario table ────────────────────────────────────────────────
    rows = "\n".join(
        f"| `{m.scenario_id}` | `{m.expected_route}` | `{m.actual_route or 'N/A'}` "
        f"| {_success_emoji(m.success)} | {m.retry_count} | {m.interrupt_count} "
        f"| {m.latency_ms} ms | {', '.join(m.errors) if m.errors else '-'} |"
        for m in metrics.scenario_metrics
    )

    # ── Embed raw JSON ────────────────────────────────────────────────────
    json_block = ""
    if metrics_json:
        json_block = f"""
## 9. Raw metrics JSON

```json
{metrics_json}
```
"""

    return f"""# Day 08 Lab Report — LangGraph Agentic Orchestration

> Generated: {now}

---

## 1. Student

| Field | Value |
|---|---|
| Name | Đặng Thị Thu Thảo |
| Student ID | 2A202600685 |
| Repo | 2A202600685-DangThiThuThao-Day23 |
| Date | {now} |

---

## 2. Architecture

The system implements a **support-ticket triage agent** using LangGraph `StateGraph`.
All traffic enters through `intake → classify` (LLM with structured output), then branches
into five distinct paths based on the classified `route`. Every path converges at
`finalize → END`, guaranteeing a terminal audit event on every execution.

### Graph Diagram

{GRAPH_MERMAID}

---

## 3. State Schema

| Field | Reducer | Purpose |
|---|---|---|
| `query` | overwrite | Normalised user input |
| `route` | overwrite | Current classified route |
| `risk_level` | overwrite | `high` / `low` from classifier |
| `attempt` | overwrite | Monotonically increasing retry counter |
| `max_attempts` | overwrite | Configured retry cap |
| `final_answer` | overwrite | Latest LLM-generated response |
| `evaluation_result` | overwrite | `needs_retry` / `success` — drives retry loop |
| `pending_question` | overwrite | Clarification question for missing-info route |
| `proposed_action` | overwrite | Risky-action descriptor sent to approver |
| `approval` | overwrite | HITL decision dict (`approved`, `reviewer`, `comment`) |
| `messages` | **append** | Audit conversation trail |
| `tool_results` | **append** | All tool call results (context for retry + answer) |
| `errors` | **append** | Cumulative error log |
| `events` | **append** | Structured audit events (`LabEvent`) |

---

## 4. Node Descriptions

| Node | Role | LLM? |
|---|---|---|
| `intake` | Normalise raw query | No |
| `classify` | Structured-output classification | **Yes** |
| `tool` | Mock tool with transient-error simulation | No |
| `evaluate` | Heuristic quality gate for retry loop | No |
| `answer` | Grounded response generation | **Yes** |
| `clarify` | Ask for missing information | No |
| `risky_action` | Prepare approval descriptor | No |
| `approval` | HITL mock (or real interrupt) | No |
| `retry` | Increment attempt counter | No |
| `dead_letter` | Escalate after max retries | No |
| `finalize` | Emit terminal audit event | No |

---

## 5. Scenario Results

### Summary

| Metric | Value |
|---|---|
{summary}

### Per-scenario

| Scenario | Expected | Actual | OK | Retries | Interrupts | Latency | Errors |
|---|---|---|:---:|---:|---:|---:|---|
{rows}

---

## 6. Failure Analysis

### Failure mode 1 — Transient tool error → retry loop

When `route = error` and `attempt < 2`, `tool_node` returns a string containing `"ERROR"`.
`evaluate_node` detects this and sets `evaluation_result = "needs_retry"`.
`route_after_evaluate` routes back to `retry_or_fallback_node`, which increments `attempt`.
`route_after_retry` checks `attempt < max_attempts`; if true, it re-runs `tool_node`.
On attempt 2, the mock returns `MOCK_TOOL_SUCCESS` and the loop exits cleanly to `answer`.
This verifies the bounded retry loop — a key production requirement.

### Failure mode 2 — Max retries exceeded → dead-letter

Scenarios with `max_attempts = 1` (e.g. S07, S15) demonstrate the dead-letter path.
After one retry, `attempt = 1 >= max_attempts = 1`, so `route_after_retry` routes to
`dead_letter_node`. This node sets a human-readable `final_answer` for escalation and
the graph still terminates cleanly through `finalize → END`.

### Failure mode 3 — Risky action without approval

If `approval_node` returns `approved = False` (or a human rejects via real HITL),
`route_after_approval` redirects to `clarify` instead of `tool`, preventing any
destructive operation from executing without explicit consent.

---

## 7. Persistence / Recovery Evidence

- **MemorySaver** (default): Each run uses a unique `thread_id` (e.g. `thread-S01_simple`).
  State history is available via `compiled.get_state_history(config)`.
- **SQLite** (extension): Activate with `CHECKPOINTER=sqlite` in `.env`.
  WAL mode is enabled (`PRAGMA journal_mode=WAL`) for crash safety.
  A process kill and restart would resume from the last committed checkpoint.
- **LangSmith tracing**: Set `LANGCHAIN_TRACING_V2=true` + `LANGCHAIN_API_KEY` in `.env`
  to capture full traces on https://smith.langchain.com for every run.

---

## 8. Improvement Plan

If given one more day, the highest-priority productionisation item would be:

1. **Real HITL Streamlit UI** — replace mock `approval_node` with a web form that renders
   the interrupt payload (proposed action, risk level, evidence), presents Approve / Reject
   buttons, and calls `compiled.invoke(Command(resume=...))`.
2. **LLM-as-judge evaluate_node** — replace the `"ERROR" in result` heuristic with an
   LLM call that rates tool output on correctness, completeness, and hallucination risk.
3. **Parallel fan-out** — use `Send()` to run multiple tool calls concurrently and merge
   results with a reducer, reducing latency on complex multi-lookup queries.
{json_block}
"""


def write_report(metrics: MetricsReport, output_path: str | Path, metrics_json: str | None = None) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report(metrics, metrics_json), encoding="utf-8")
