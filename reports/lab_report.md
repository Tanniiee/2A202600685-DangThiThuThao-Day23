# Day 08 Lab Report — LangGraph Agentic Orchestration

> Generated: 2026-06-29 14:51

---

## 1. Student

| Field | Value |
|---|---|
| Name | Đặng Thị Thu Thảo |
| Student ID | 2A202600685 |
| Repo | 2A202600685-DangThiThuThao-Day23 |
| Date | 2026-06-29 14:51 |

---

## 2. Architecture

The system implements a **support-ticket triage agent** using LangGraph `StateGraph`.
All traffic enters through `intake → classify` (LLM with structured output), then branches
into five distinct paths based on the classified `route`. Every path converges at
`finalize → END`, guaranteeing a terminal audit event on every execution.

### Graph Diagram

```mermaid
flowchart TD
    START([START]) --> intake[intake]
    intake --> classify[classify
LLM structured output]

    classify -->|simple| answer
    classify -->|tool| tool
    classify -->|missing_info| clarify
    classify -->|risky| risky_action
    classify -->|error| retry

    tool[tool
mock + error sim] --> evaluate[evaluate
heuristic / LLM-as-judge]
    evaluate -->|success| answer[answer
LLM grounded]
    evaluate -->|needs_retry| retry[retry
increment attempt]

    retry -->|attempt < max| tool
    retry -->|attempt >= max| dead_letter[dead_letter
escalate]

    risky_action[risky_action
prepare descriptor] --> approval[approval
HITL / mock]
    approval -->|approved| tool
    approval -->|rejected| clarify[clarify
ask for info]

    clarify --> finalize
    answer --> finalize[finalize
audit event]
    dead_letter --> finalize
    finalize --> END([END])

    style classify fill:#4A90D9,color:#fff
    style answer fill:#4A90D9,color:#fff
    style approval fill:#E67E22,color:#fff
    style retry fill:#E74C3C,color:#fff
    style dead_letter fill:#C0392B,color:#fff
    style finalize fill:#27AE60,color:#fff
```

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
| Total scenarios      | **25** |
| Success rate         | **100%** |
| Avg nodes visited    | 6.1 |
| Total retries        | 6 |
| Total interrupts     | 6 |
| Crash-resume success | Yes |

### Per-scenario

| Scenario | Expected | Actual | OK | Retries | Interrupts | Latency | Errors |
|---|---|---|:---:|---:|---:|---:|---|
| `S01_simple` | `simple` | `simple` | ✅ | 0 | 0 | 43846 ms | - |
| `S02_tool` | `tool` | `tool` | ✅ | 0 | 0 | 1791 ms | - |
| `S03_missing` | `missing_info` | `missing_info` | ✅ | 0 | 0 | 742 ms | - |
| `S04_risky` | `risky` | `risky` | ✅ | 0 | 1 | 4595 ms | - |
| `S05_error` | `error` | `error` | ✅ | 2 | 0 | 2175 ms | retry attempt 1: tool result was unsatisfactory or route is error, retry attempt 2: tool result was unsatisfactory or route is error |
| `S06_delete` | `risky` | `risky` | ✅ | 0 | 1 | 1876 ms | - |
| `S07_dead_letter` | `error` | `error` | ✅ | 1 | 0 | 655 ms | retry attempt 1: tool result was unsatisfactory or route is error |
| `S08_complex_tool` | `tool` | `tool` | ✅ | 0 | 0 | 1918 ms | - |
| `S09_complex_risky` | `risky` | `risky` | ✅ | 0 | 1 | 2172 ms | - |
| `S10_complex_missing` | `risky` | `risky` | ✅ | 0 | 1 | 2206 ms | - |
| `S11_complex_retry` | `error` | `error` | ✅ | 2 | 0 | 3302 ms | retry attempt 1: tool result was unsatisfactory or route is error, retry attempt 2: tool result was unsatisfactory or route is error |
| `S12_policy_simple` | `simple` | `simple` | ✅ | 0 | 0 | 2407 ms | - |
| `S13_escalation_risky` | `risky` | `risky` | ✅ | 0 | 1 | 1851 ms | - |
| `S14_missing_order` | `tool` | `tool` | ✅ | 0 | 0 | 2030 ms | - |
| `S15_dead_letter_hard` | `error` | `error` | ✅ | 1 | 0 | 690 ms | retry attempt 1: tool result was unsatisfactory or route is error |
| `S16_gq_refund_days` | `simple` | `simple` | ✅ | 0 | 0 | 2233 ms | - |
| `S17_gq_refund_exclusion` | `simple` | `simple` | ✅ | 0 | 0 | 2366 ms | - |
| `S18_gq_refund_processing` | `risky` | `risky` | ✅ | 0 | 1 | 1779 ms | - |
| `S19_gq_sla_p1_response` | `simple` | `simple` | ✅ | 0 | 0 | 2158 ms | - |
| `S20_gq_sla_p1_resolution` | `simple` | `simple` | ✅ | 0 | 0 | 1578 ms | - |
| `S21_gq_sla_escalate` | `simple` | `simple` | ✅ | 0 | 0 | 1687 ms | - |
| `S22_gq_account_lock` | `simple` | `simple` | ✅ | 0 | 0 | 2172 ms | - |
| `S23_gq_vpn_devices` | `simple` | `simple` | ✅ | 0 | 0 | 2421 ms | - |
| `S24_gq_hr_leave` | `simple` | `simple` | ✅ | 0 | 0 | 1810 ms | - |
| `S25_gq_admin_access` | `missing_info` | `missing_info` | ✅ | 0 | 0 | 727 ms | - |

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

## 9. Raw metrics JSON

```json
{
  "total_scenarios": 25,
  "success_rate": 1.0,
  "avg_nodes_visited": 6.08,
  "total_retries": 6,
  "total_interrupts": 6,
  "resume_success": true,
  "scenario_metrics": [
    {
      "scenario_id": "S01_simple",
      "success": true,
      "expected_route": "simple",
      "actual_route": "simple",
      "nodes_visited": 4,
      "retry_count": 0,
      "interrupt_count": 0,
      "approval_required": false,
      "approval_observed": false,
      "latency_ms": 43846,
      "errors": []
    },
    {
      "scenario_id": "S02_tool",
      "success": true,
      "expected_route": "tool",
      "actual_route": "tool",
      "nodes_visited": 6,
      "retry_count": 0,
      "interrupt_count": 0,
      "approval_required": false,
      "approval_observed": false,
      "latency_ms": 1791,
      "errors": []
    },
    {
      "scenario_id": "S03_missing",
      "success": true,
      "expected_route": "missing_info",
      "actual_route": "missing_info",
      "nodes_visited": 4,
      "retry_count": 0,
      "interrupt_count": 0,
      "approval_required": false,
      "approval_observed": false,
      "latency_ms": 742,
      "errors": []
    },
    {
      "scenario_id": "S04_risky",
      "success": true,
      "expected_route": "risky",
      "actual_route": "risky",
      "nodes_visited": 8,
      "retry_count": 0,
      "interrupt_count": 1,
      "approval_required": true,
      "approval_observed": true,
      "latency_ms": 4595,
      "errors": []
    },
    {
      "scenario_id": "S05_error",
      "success": true,
      "expected_route": "error",
      "actual_route": "error",
      "nodes_visited": 12,
      "retry_count": 2,
      "interrupt_count": 0,
      "approval_required": false,
      "approval_observed": false,
      "latency_ms": 2175,
      "errors": [
        "retry attempt 1: tool result was unsatisfactory or route is error",
        "retry attempt 2: tool result was unsatisfactory or route is error"
      ]
    },
    {
      "scenario_id": "S06_delete",
      "success": true,
      "expected_route": "risky",
      "actual_route": "risky",
      "nodes_visited": 8,
      "retry_count": 0,
      "interrupt_count": 1,
      "approval_required": true,
      "approval_observed": true,
      "latency_ms": 1876,
      "errors": []
    },
    {
      "scenario_id": "S07_dead_letter",
      "success": true,
      "expected_route": "error",
      "actual_route": "error",
      "nodes_visited": 7,
      "retry_count": 1,
      "interrupt_count": 0,
      "approval_required": false,
      "approval_observed": false,
      "latency_ms": 655,
      "errors": [
        "retry attempt 1: tool result was unsatisfactory or route is error"
      ]
    },
    {
      "scenario_id": "S08_complex_tool",
      "success": true,
      "expected_route": "tool",
      "actual_route": "tool",
      "nodes_visited": 6,
      "retry_count": 0,
      "interrupt_count": 0,
      "approval_required": false,
      "approval_observed": false,
      "latency_ms": 1918,
      "errors": []
    },
    {
      "scenario_id": "S09_complex_risky",
      "success": true,
      "expected_route": "risky",
      "actual_route": "risky",
      "nodes_visited": 8,
      "retry_count": 0,
      "interrupt_count": 1,
      "approval_required": true,
      "approval_observed": true,
      "latency_ms": 2172,
      "errors": []
    },
    {
      "scenario_id": "S10_complex_missing",
      "success": true,
      "expected_route": "risky",
      "actual_route": "risky",
      "nodes_visited": 8,
      "retry_count": 0,
      "interrupt_count": 1,
      "approval_required": true,
      "approval_observed": true,
      "latency_ms": 2206,
      "errors": []
    },
    {
      "scenario_id": "S11_complex_retry",
      "success": true,
      "expected_route": "error",
      "actual_route": "error",
      "nodes_visited": 12,
      "retry_count": 2,
      "interrupt_count": 0,
      "approval_required": false,
      "approval_observed": false,
      "latency_ms": 3302,
      "errors": [
        "retry attempt 1: tool result was unsatisfactory or route is error",
        "retry attempt 2: tool result was unsatisfactory or route is error"
      ]
    },
    {
      "scenario_id": "S12_policy_simple",
      "success": true,
      "expected_route": "simple",
      "actual_route": "simple",
      "nodes_visited": 4,
      "retry_count": 0,
      "interrupt_count": 0,
      "approval_required": false,
      "approval_observed": false,
      "latency_ms": 2407,
      "errors": []
    },
    {
      "scenario_id": "S13_escalation_risky",
      "success": true,
      "expected_route": "risky",
      "actual_route": "risky",
      "nodes_visited": 8,
      "retry_count": 0,
      "interrupt_count": 1,
      "approval_required": true,
      "approval_observed": true,
      "latency_ms": 1851,
      "errors": []
    },
    {
      "scenario_id": "S14_missing_order",
      "success": true,
      "expected_route": "tool",
      "actual_route": "tool",
      "nodes_visited": 6,
      "retry_count": 0,
      "interrupt_count": 0,
      "approval_required": false,
      "approval_observed": false,
      "latency_ms": 2030,
      "errors": []
    },
    {
      "scenario_id": "S15_dead_letter_hard",
      "success": true,
      "expected_route": "error",
      "actual_route": "error",
      "nodes_visited": 7,
      "retry_count": 1,
      "interrupt_count": 0,
      "approval_required": false,
      "approval_observed": false,
      "latency_ms": 690,
      "errors": [
        "retry attempt 1: tool result was unsatisfactory or route is error"
      ]
    },
    {
      "scenario_id": "S16_gq_refund_days",
      "success": true,
      "expected_route": "simple",
      "actual_route": "simple",
      "nodes_visited": 4,
      "retry_count": 0,
      "interrupt_count": 0,
      "approval_required": false,
      "approval_observed": false,
      "latency_ms": 2233,
      "errors": []
    },
    {
      "scenario_id": "S17_gq_refund_exclusion",
      "success": true,
      "expected_route": "simple",
      "actual_route": "simple",
      "nodes_visited": 4,
      "retry_count": 0,
      "interrupt_count": 0,
      "approval_required": false,
      "approval_observed": false,
      "latency_ms": 2366,
      "errors": []
    },
    {
      "scenario_id": "S18_gq_refund_processing",
      "success": true,
      "expected_route": "risky",
      "actual_route": "risky",
      "nodes_visited": 8,
      "retry_count": 0,
      "interrupt_count": 1,
      "approval_required": true,
      "approval_observed": true,
      "latency_ms": 1779,
      "errors": []
    },
    {
      "scenario_id": "S19_gq_sla_p1_response",
      "success": true,
      "expected_route": "simple",
      "actual_route": "simple",
      "nodes_visited": 4,
      "retry_count": 0,
      "interrupt_count": 0,
      "approval_required": false,
      "approval_observed": false,
      "latency_ms": 2158,
      "errors": []
    },
    {
      "scenario_id": "S20_gq_sla_p1_resolution",
      "success": true,
      "expected_route": "simple",
      "actual_route": "simple",
      "nodes_visited": 4,
      "retry_count": 0,
      "interrupt_count": 0,
      "approval_required": false,
      "approval_observed": false,
      "latency_ms": 1578,
      "errors": []
    },
    {
      "scenario_id": "S21_gq_sla_escalate",
      "success": true,
      "expected_route": "simple",
      "actual_route": "simple",
      "nodes_visited": 4,
      "retry_count": 0,
      "interrupt_count": 0,
      "approval_required": false,
      "approval_observed": false,
      "latency_ms": 1687,
      "errors": []
    },
    {
      "scenario_id": "S22_gq_account_lock",
      "success": true,
      "expected_route": "simple",
      "actual_route": "simple",
      "nodes_visited": 4,
      "retry_count": 0,
      "interrupt_count": 0,
      "approval_required": false,
      "approval_observed": false,
      "latency_ms": 2172,
      "errors": []
    },
    {
      "scenario_id": "S23_gq_vpn_devices",
      "success": true,
      "expected_route": "simple",
      "actual_route": "simple",
      "nodes_visited": 4,
      "retry_count": 0,
      "interrupt_count": 0,
      "approval_required": false,
      "approval_observed": false,
      "latency_ms": 2421,
      "errors": []
    },
    {
      "scenario_id": "S24_gq_hr_leave",
      "success": true,
      "expected_route": "simple",
      "actual_route": "simple",
      "nodes_visited": 4,
      "retry_count": 0,
      "interrupt_count": 0,
      "approval_required": false,
      "approval_observed": false,
      "latency_ms": 1810,
      "errors": []
    },
    {
      "scenario_id": "S25_gq_admin_access",
      "success": true,
      "expected_route": "missing_info",
      "actual_route": "missing_info",
      "nodes_visited": 4,
      "retry_count": 0,
      "interrupt_count": 0,
      "approval_required": false,
      "approval_observed": false,
      "latency_ms": 727,
      "errors": []
    }
  ]
}
```

