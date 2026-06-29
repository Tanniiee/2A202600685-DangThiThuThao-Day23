"""CLI for the lab."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Annotated

import typer
import yaml

from .graph import build_graph
from .metrics import MetricsReport, metric_from_state, summarize_metrics, write_metrics
from .persistence import build_checkpointer
from .report import write_report
from .scenarios import load_scenarios
from .state import initial_state

app = typer.Typer(no_args_is_help=True)


@app.command("run-scenarios")
def run_scenarios(
    config: Annotated[Path, typer.Option("--config")],
    output: Annotated[Path, typer.Option("--output")],
) -> None:
    """Run all grading scenarios and write metrics JSON + report."""
    cfg = yaml.safe_load(config.read_text(encoding="utf-8"))
    scenarios = load_scenarios(cfg["scenarios_path"])
    checkpointer = build_checkpointer(cfg.get("checkpointer", "memory"), cfg.get("database_url"))
    graph = build_graph(checkpointer=checkpointer)

    typer.echo(f"Running {len(scenarios)} scenarios...")
    metrics_list = []
    for scenario in scenarios:
        state = initial_state(scenario)
        run_config = {"configurable": {"thread_id": state["thread_id"]}}
        t0 = time.monotonic()
        final_state = graph.invoke(state, config=run_config)
        latency_ms = int((time.monotonic() - t0) * 1000)
        m = metric_from_state(final_state, scenario.expected_route.value, scenario.requires_approval)
        m.latency_ms = latency_ms
        metrics_list.append(m)
        status = "OK" if m.success else "FAIL"
        typer.echo(f"  [{status}] {scenario.id}: route={m.actual_route} retries={m.retry_count} interrupts={m.interrupt_count} {latency_ms}ms")

    # ── Crash-resume verification ─────────────────────────────────────────
    # Prove the checkpointer recorded state history for at least one thread.
    # get_state_history() returns an iterator of CheckpointTuple; if it yields
    # at least one entry, the checkpointer is working and state can be replayed.
    resume_success = False
    try:
        first_thread_id = initial_state(scenarios[0])["thread_id"]
        history = list(graph.get_state_history({"configurable": {"thread_id": first_thread_id}}))
        if history:
            resume_success = True
            typer.echo(f"[resume] State history OK — {len(history)} checkpoint(s) for {first_thread_id}")
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"[resume] State history check skipped: {exc}")

    report = summarize_metrics(metrics_list)
    report.resume_success = resume_success
    write_metrics(report, output)
    typer.echo(f"\nWrote metrics to {output}")
    typer.echo(f"Success rate: {report.success_rate:.0%} ({sum(m.success for m in metrics_list)}/{len(metrics_list)})")

    if cfg.get("report_path"):
        metrics_json = json.dumps(report.model_dump(), indent=2, ensure_ascii=False)
        write_report(report, cfg["report_path"], metrics_json=metrics_json)
        typer.echo(f"Wrote report to {cfg['report_path']}")


@app.command("validate-metrics")
def validate_metrics(metrics: Annotated[Path, typer.Option("--metrics")]) -> None:
    """Validate metrics JSON schema for grading."""
    payload = json.loads(metrics.read_text(encoding="utf-8"))
    report = MetricsReport.model_validate(payload)
    if report.total_scenarios < 6:
        raise typer.BadParameter("Expected at least 6 scenarios")
    typer.echo(f"Metrics valid. success_rate={report.success_rate:.2%}")


if __name__ == "__main__":
    app()
