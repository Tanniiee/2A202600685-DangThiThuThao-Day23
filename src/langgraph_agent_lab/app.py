"""Streamlit UI for the LangGraph Agent Lab.

Run:
    streamlit run src/langgraph_agent_lab/app.py

Features:
- Run individual queries interactively
- Run all scenarios and view metrics
- Display Mermaid graph diagram
- Show step-by-step event log and retry/approval details
- LangSmith trace link (if configured)
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import streamlit as st

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="LangGraph Agent Lab — Day 08",
    page_icon="🤖",
    layout="wide",
)

# ── Load .env if present ─────────────────────────────────────────────────────
env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if v and not v.startswith("...") and "sk-..." not in v and "AIza..." not in v:
                os.environ.setdefault(k, v)

# ── Lazy imports (after env is loaded) ───────────────────────────────────────
@st.cache_resource(show_spinner="Building graph...")
def get_graph():
    from langgraph_agent_lab.graph import build_graph
    from langgraph_agent_lab.persistence import build_checkpointer
    checkpointer = build_checkpointer("memory")
    return build_graph(checkpointer=checkpointer)


def run_query(query: str, scenario_id: str = "ui-run") -> dict:
    from langgraph_agent_lab.state import Scenario, Route, initial_state
    graph = get_graph()
    scenario = Scenario(id=scenario_id, query=query, expected_route=Route.SIMPLE)
    state = initial_state(scenario)
    config = {"configurable": {"thread_id": state["thread_id"]}}
    return graph.invoke(state, config=config)


def run_all_scenarios() -> tuple[list[dict], object]:
    import yaml
    from langgraph_agent_lab.scenarios import load_scenarios
    from langgraph_agent_lab.state import initial_state
    from langgraph_agent_lab.metrics import metric_from_state, summarize_metrics
    graph = get_graph()
    cfg_path = Path(__file__).parent.parent.parent / "configs" / "lab.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    scenarios_path = Path(__file__).parent.parent.parent / cfg["scenarios_path"]
    scenarios = load_scenarios(scenarios_path)
    results = []
    for scenario in scenarios:
        state = initial_state(scenario)
        run_config = {"configurable": {"thread_id": state["thread_id"]}}
        t0 = time.monotonic()
        final = graph.invoke(state, config=run_config)
        ms = int((time.monotonic() - t0) * 1000)
        m = metric_from_state(final, scenario.expected_route.value, scenario.requires_approval)
        m.latency_ms = ms
        results.append({"scenario": scenario, "state": final, "metric": m})
    report = summarize_metrics([r["metric"] for r in results])
    return results, report


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.title("🤖 LangGraph Lab")
    st.caption("Day 08 — Agentic Orchestration")
    st.divider()

    api_key = os.getenv("OPENAI_API_KEY", "")
    if api_key and not api_key.startswith("sk-..."):
        st.success("✅ OpenAI key loaded")
    else:
        st.error("❌ No OpenAI API key — set OPENAI_API_KEY in .env")

    langsmith = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
    if langsmith:
        project = os.getenv("LANGCHAIN_PROJECT", "day08-langgraph-lab")
        st.success(f"✅ LangSmith tracing ON\nProject: `{project}`")
        st.caption("[Open LangSmith →](https://smith.langchain.com)")
    else:
        st.info("ℹ️ LangSmith tracing OFF\nSet LANGCHAIN_TRACING_V2=true in .env to enable")

    st.divider()
    page = st.radio("Navigation", ["💬 Interactive", "🧪 Run Scenarios", "🗺️ Graph Diagram"])

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: INTERACTIVE
# ══════════════════════════════════════════════════════════════════════════════
if page == "💬 Interactive":
    st.header("💬 Interactive Agent")
    st.caption("Type any support query and watch the agent route it through the graph.")

    with st.form("query_form"):
        query = st.text_area(
            "Your query",
            placeholder="e.g. Refund order #12345 and send confirmation email",
            height=80,
        )
        submitted = st.form_submit_button("▶ Run", use_container_width=True)

    if submitted and query.strip():
        if not (os.getenv("OPENAI_API_KEY", "").replace("sk-...", "").strip()):
            st.error("Please set OPENAI_API_KEY in your .env file first.")
        else:
            with st.spinner("Running graph..."):
                t0 = time.monotonic()
                result = run_query(query.strip())
                ms = int((time.monotonic() - t0) * 1000)

            route = result.get("route", "unknown")
            answer = result.get("final_answer") or result.get("pending_question", "")
            events = result.get("events", [])
            errors = result.get("errors", [])
            approval = result.get("approval")

            # ── Route badge ──────────────────────────────────────────────
            colour = {
                "simple": "🟢", "tool": "🔵", "missing_info": "🟡",
                "risky": "🟠", "error": "🔴",
            }.get(route, "⚪")
            col1, col2, col3 = st.columns(3)
            col1.metric("Route", f"{colour} {route}")
            col2.metric("Latency", f"{ms} ms")
            col3.metric("Nodes visited", len(events))

            # ── Answer ───────────────────────────────────────────────────
            if answer:
                st.subheader("🗣️ Agent Response")
                st.info(answer)

            # ── Approval ─────────────────────────────────────────────────
            if approval:
                status = "✅ Approved" if approval.get("approved") else "❌ Rejected"
                st.subheader("👤 Approval Decision")
                st.write(f"**{status}** — Reviewer: `{approval.get('reviewer')}`")
                if approval.get("comment"):
                    st.caption(approval["comment"])

            # ── Event log ────────────────────────────────────────────────
            st.subheader("📋 Event Log")
            for i, ev in enumerate(events):
                icon = {"completed": "✅", "error": "❌", "retrying": "🔁", "failed": "💀"}.get(ev.get("event_type", ""), "📌")
                node = ev.get("node", "?")
                msg = ev.get("message", "")
                st.markdown(f"`{i+1}.` {icon} **{node}** — {msg}")

            # ── Retry / error log ────────────────────────────────────────
            if errors:
                st.subheader("⚠️ Retry / Error Log")
                for err in errors:
                    st.warning(err)

            # ── Tool results ─────────────────────────────────────────────
            tool_results = result.get("tool_results", [])
            if tool_results:
                with st.expander("🔧 Tool Results"):
                    for tr in tool_results:
                        st.code(tr)

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: RUN SCENARIOS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🧪 Run Scenarios":
    st.header("🧪 Run All Scenarios")
    st.caption("Executes all scenarios from `data/sample/scenarios.jsonl` and shows metrics.")

    if not (os.getenv("OPENAI_API_KEY", "").replace("sk-...", "").strip()):
        st.error("Please set OPENAI_API_KEY in your .env file first.")
    else:
        if st.button("▶ Run all scenarios", use_container_width=True):
            progress = st.progress(0, text="Starting...")
            status_box = st.empty()

            # Patch to show progress per scenario
            import yaml
            from langgraph_agent_lab.scenarios import load_scenarios
            from langgraph_agent_lab.state import initial_state
            from langgraph_agent_lab.metrics import metric_from_state, summarize_metrics
            graph = get_graph()
            cfg_path = Path(__file__).parent.parent.parent / "configs" / "lab.yaml"
            cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
            scenarios_path = Path(__file__).parent.parent.parent / cfg["scenarios_path"]
            scenarios = load_scenarios(scenarios_path)

            results = []
            for i, scenario in enumerate(scenarios):
                status_box.info(f"Running {scenario.id} ({i+1}/{len(scenarios)})...")
                state = initial_state(scenario)
                run_config = {"configurable": {"thread_id": state["thread_id"]}}
                t0 = time.monotonic()
                final = graph.invoke(state, config=run_config)
                ms = int((time.monotonic() - t0) * 1000)
                m = metric_from_state(final, scenario.expected_route.value, scenario.requires_approval)
                m.latency_ms = ms
                results.append({"scenario": scenario, "state": final, "metric": m})
                progress.progress((i + 1) / len(scenarios), text=f"{scenario.id}: {'✅' if m.success else '❌'}")

            status_box.empty()
            report = summarize_metrics([r["metric"] for r in results])

            # Save outputs
            out_dir = Path(__file__).parent.parent.parent / "outputs"
            out_dir.mkdir(exist_ok=True)
            metrics_json = json.dumps(report.model_dump(), indent=2, ensure_ascii=False)
            (out_dir / "metrics.json").write_text(metrics_json, encoding="utf-8")

            from langgraph_agent_lab.report import write_report
            report_path = Path(__file__).parent.parent.parent / cfg.get("report_path", "reports/lab_report.md")
            write_report(report, report_path, metrics_json=metrics_json)

            st.success(f"Done! Success rate: **{report.success_rate:.0%}** ({sum(r['metric'].success for r in results)}/{len(results)})")

            # ── Summary metrics ──────────────────────────────────────────
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Success rate", f"{report.success_rate:.0%}")
            c2.metric("Avg nodes", f"{report.avg_nodes_visited:.1f}")
            c3.metric("Total retries", report.total_retries)
            c4.metric("Total interrupts", report.total_interrupts)

            # ── Per-scenario table ───────────────────────────────────────
            st.subheader("Per-scenario results")
            table_data = []
            for r in results:
                m = r["metric"]
                table_data.append({
                    "Scenario": m.scenario_id,
                    "Expected": m.expected_route,
                    "Actual": m.actual_route or "N/A",
                    "OK": "✅" if m.success else "❌",
                    "Retries": m.retry_count,
                    "Interrupts": m.interrupt_count,
                    "Latency (ms)": m.latency_ms,
                })
            st.dataframe(table_data, use_container_width=True)

            # ── Raw JSON ─────────────────────────────────────────────────
            with st.expander("📄 Raw metrics.json"):
                st.code(metrics_json, language="json")

            st.info(f"📁 Saved: `outputs/metrics.json` and `{report_path}`")

# ══════════════════════════════════════════════════════════════════════════════
# PAGE: GRAPH DIAGRAM
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🗺️ Graph Diagram":
    st.header("🗺️ Graph Architecture")

    st.subheader("Mermaid Flow Diagram")
    st.markdown("""
```mermaid
flowchart TD
    START([START]) --> intake[intake]
    intake --> classify[classify\\nLLM structured output]

    classify -->|simple| answer
    classify -->|tool| tool
    classify -->|missing_info| clarify
    classify -->|risky| risky_action
    classify -->|error| retry

    tool[tool\\nmock + error sim] --> evaluate[evaluate\\nheuristic]
    evaluate -->|success| answer[answer\\nLLM grounded]
    evaluate -->|needs_retry| retry[retry\\nincrement attempt]

    retry -->|attempt < max| tool
    retry -->|attempt >= max| dead_letter[dead_letter\\nescalate]

    risky_action[risky_action\\nprepare descriptor] --> approval[approval\\nHITL / mock]
    approval -->|approved| tool
    approval -->|rejected| clarify[clarify\\nask for info]

    clarify --> finalize
    answer --> finalize[finalize\\naudit event]
    dead_letter --> finalize
    finalize --> END([END])

    style classify fill:#4A90D9,color:#fff
    style answer fill:#4A90D9,color:#fff
    style approval fill:#E67E22,color:#fff
    style retry fill:#E74C3C,color:#fff
    style dead_letter fill:#C0392B,color:#fff
    style finalize fill:#27AE60,color:#fff
```
""")

    st.divider()
    st.subheader("Route Summary")
    st.markdown("""
| Route | Path |
|---|---|
| `simple` | intake → classify → **answer** → finalize → END |
| `tool` | intake → classify → **tool → evaluate** → answer → finalize → END |
| `missing_info` | intake → classify → **clarify** → finalize → END |
| `risky` | intake → classify → **risky_action → approval** → tool → evaluate → answer → finalize → END |
| `error` | intake → classify → **retry** → tool → evaluate ↩ retry loop → finalize → END |
| `dead_letter` | ... → retry (max) → **dead_letter** → finalize → END |
""")

    st.divider()
    st.subheader("State field reducers")
    st.markdown("""
| Type | Fields |
|---|---|
| **Overwrite** | `query`, `route`, `risk_level`, `attempt`, `max_attempts`, `final_answer`, `evaluation_result`, `pending_question`, `proposed_action`, `approval` |
| **Append** | `messages`, `tool_results`, `errors`, `events` |
""")
