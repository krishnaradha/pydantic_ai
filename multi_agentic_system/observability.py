"""Logfire integration and per-request result capture.

Responsibilities:

- :func:`configure_logfire` — wire up Logfire + pydantic-ai auto-instrumentation.
- :func:`build_run_result` — extract a :class:`~result_schema.RunResult` from a
  finished pydantic-ai ``AgentRunResult``, including state flow, token usage,
  and cost.
- :class:`TraceStore` — appends results as JSON Lines to ``data/traces/``, one
  file per calendar day, ready for a frontend to tail or query.
- :func:`render_result_table` — returns a Rich ``Table`` summarising the result
  for terminal display after each request.

Example:
    ::

        configure_logfire(settings)

        started_at = time.monotonic()
        result     = await assistant.run(query, deps=context)
        run_result = build_run_result(context, query, result, started_at)

        await store.save(run_result)
        console.print(render_result_table(run_result))
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.usage import Usage
from rich.columns import Columns
from rich.padding import Padding
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .config import Settings, get_logger
from .result_schema import (
    CostBreakdown,
    RunResult,
    StateStep,
    StepType,
    TokenUsage,
)

logger = get_logger(__name__)

__all__ = [
    "configure_logfire",
    "TraceStore",
    "build_run_result",
    "render_result_table",
]

_CONTENT_PREVIEW_CHARS = 500


def configure_logfire(settings: Settings) -> None:
    """Configure Logfire and auto-instrument pydantic-ai agents.

    If ``LOGFIRE_TOKEN`` is absent, Logfire runs in local-only mode — traces
    are still captured via :class:`TraceStore`, but the cloud dashboard is
    unavailable.

    Args:
        settings: Validated application settings.

    Raises:
        ImportError: If the ``logfire`` package is not installed.
    """
    try:
        import logfire  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError("logfire is not installed. Run: uv sync") from exc

    token = settings.logfire_token.get_secret_value() if settings.logfire_token else None

    logfire.configure(
        token=token,
        service_name="multi-agentic-system",
        send_to_logfire=token is not None,
    )
    logfire.instrument_pydantic_ai()
    logger.info(
        "Logfire configured (cloud=%s) — dashboard: https://logfire.pydantic.dev",
        token is not None,
    )


class TraceStore:
    """Appends :class:`~result_schema.RunResult` objects as JSON Lines to a daily log file.

    Files are written to ``<base_dir>/traces_YYYY-MM-DD.jsonl`` — one file per
    calendar day. A frontend can tail the file in real time or load it wholesale.

    Args:
        base_dir: Directory under which trace files are written.
    """

    def __init__(self, base_dir: str | Path = "data/traces") -> None:
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def _daily_path(self) -> Path:
        return self._base_dir / f"traces_{datetime.now(UTC).strftime('%Y-%m-%d')}.jsonl"

    async def save(self, result: RunResult) -> None:
        """Append *result* to today's JSONL file.

        Args:
            result: Completed run result to persist.
        """
        import asyncio  # noqa: PLC0415
        await asyncio.to_thread(self._write, result)

    def _write(self, result: RunResult) -> None:
        path = self._daily_path()
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(result.to_dict(), ensure_ascii=False) + "\n")
        logger.debug("Result saved: request_id=%s path=%s", result.request_id, path)

    def load_today(self) -> list[RunResult]:
        """Load all results written today.

        Returns:
            List of :class:`~result_schema.RunResult` objects, oldest first.
        """
        path = self._daily_path()
        if not path.exists():
            return []
        results: list[RunResult] = []
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                data["state_flow"] = [StateStep(**s) for s in data.get("state_flow", [])]
                data["usage"] = TokenUsage(**data.get("usage", {}))
                data["cost"] = CostBreakdown(**data.get("cost", {}))
                results.append(RunResult(**data))
        return results


def _extract_usage(raw: Usage) -> TokenUsage:
    cached = (raw.details or {}).get("cached_tokens", 0)
    return TokenUsage(
        input_tokens=raw.request_tokens or 0,
        output_tokens=raw.response_tokens or 0,
        cached_tokens=cached,
        total_tokens=raw.total_tokens or 0,
    )


def _preview(text: str) -> str:
    if len(text) <= _CONTENT_PREVIEW_CHARS:
        return text
    return text[:_CONTENT_PREVIEW_CHARS] + f"… [{len(text) - _CONTENT_PREVIEW_CHARS} chars omitted]"


def _extract_state_flow(messages: list) -> list[StateStep]:
    steps: list[StateStep] = []
    call_times: dict[str, float] = {}

    for message in messages:
        if isinstance(message, ModelRequest):
            for part in message.parts:
                if isinstance(part, SystemPromptPart):
                    continue
                if isinstance(part, UserPromptPart):
                    steps.append(StateStep(
                        index=len(steps),
                        step_type=StepType.USER_MESSAGE,
                        name=None,
                        content=_preview(str(part.content)),
                        duration_ms=None,
                    ))
                elif isinstance(part, ToolReturnPart):
                    duration = None
                    if part.tool_call_id in call_times:
                        duration = (time.monotonic() - call_times.pop(part.tool_call_id)) * 1000
                    steps.append(StateStep(
                        index=len(steps),
                        step_type=StepType.TOOL_RESULT,
                        name=part.tool_name,
                        content=_preview(str(part.content)),
                        duration_ms=duration,
                    ))

        elif isinstance(message, ModelResponse):
            for part in message.parts:
                if isinstance(part, TextPart):
                    steps.append(StateStep(
                        index=len(steps),
                        step_type=StepType.LLM_RESPONSE,
                        name=message.model_name,
                        content=_preview(part.content),
                        duration_ms=None,
                    ))
                elif isinstance(part, ToolCallPart):
                    call_times[part.tool_call_id] = time.monotonic()
                    args = (
                        part.args_as_json_str()
                        if hasattr(part, "args_as_json_str")
                        else str(part.args)
                    )
                    steps.append(StateStep(
                        index=len(steps),
                        step_type=StepType.TOOL_CALL,
                        name=part.tool_name,
                        content=_preview(args),
                        duration_ms=None,
                    ))

    return steps


def build_run_result(
    request_id: str,
    user_id: str,
    query: str,
    model: str,
    started_at: float,
    result: object = None,
    status: str = "success",
    error: str | None = None,
    final_output: str | None = None,
) -> RunResult:
    """Build a :class:`~result_schema.RunResult` from a finished agent run.

    Args:
        request_id: Correlation ID from :attr:`~models.AgentContext.request_id`.
        user_id: Identifier of the requesting user.
        query: Validated user query string.
        model: Model string from settings, e.g. ``"openai:gpt-4o"``.
        started_at: ``time.monotonic()`` captured before ``agent.run()``.
        result: Finished pydantic-ai result object exposing ``all_messages()``
            and ``usage()``. ``None`` on failure paths.
        status: Overall request status.
        error: Error string if the run failed.
        final_output: Explicit output string override. Required when *result*
            is a ``StreamedRunResult`` which has no ``.output`` attribute —
            pass the value from ``await streamed.get_data()`` instead.

    Returns:
        A fully populated :class:`~result_schema.RunResult`.
    """
    response_time_ms = (time.monotonic() - started_at) * 1000

    if result is not None:
        messages = result.all_messages()  # type: ignore[union-attr]
        raw_usage: Usage = result.usage()  # type: ignore[union-attr]
        usage = _extract_usage(raw_usage)
        state_flow = _extract_state_flow(messages)
        if final_output is None and status == "success":
            final_output = getattr(result, "output", None)
    else:
        usage = TokenUsage()
        state_flow = []
        final_output = None

    cost = CostBreakdown.from_usage(usage, model)

    return RunResult(
        request_id=request_id,
        user_id=user_id,
        query=query,
        timestamp=datetime.now(UTC).isoformat(),
        model=model,
        status=status,
        state_flow=state_flow,
        final_output=final_output,
        response_time_ms=round(response_time_ms, 2),
        usage=usage,
        cost=cost,
        error=error,
    )


_STEP_ICON = {
    StepType.USER_MESSAGE: "👤",
    StepType.LLM_RESPONSE: "🤖",
    StepType.TOOL_CALL:    "🔧",
    StepType.TOOL_RESULT:  "📤",
}
_STEP_COLOUR = {
    StepType.USER_MESSAGE: "cyan",
    StepType.LLM_RESPONSE: "bright_blue",
    StepType.TOOL_CALL:    "yellow",
    StepType.TOOL_RESULT:  "green",
}
_STATUS_COLOUR = {
    "success": "bold green",
    "error":   "bold red",
    "timeout": "bold yellow",
    "blocked": "bold magenta",
}
_STATUS_ICON = {
    "success": "✅",
    "error":   "❌",
    "timeout": "⏰",
    "blocked": "🚫",
}
_BAR_WIDTH = 20


def _bar(value: int, total: int, colour: str) -> str:
    if total == 0:
        return f"[dim]{'░' * _BAR_WIDTH}[/dim]"
    filled = round(_BAR_WIDTH * value / total)
    return f"[{colour}]{'█' * filled}[/{colour}][dim]{'░' * (_BAR_WIDTH - filled)}[/dim]"


def _metrics_table(run_result: RunResult) -> Table:
    status_colour = _STATUS_COLOUR.get(run_result.status, "white")
    status_icon = _STATUS_ICON.get(run_result.status, "")
    llm_calls = sum(1 for s in run_result.state_flow if s.step_type == StepType.LLM_RESPONSE)
    tool_calls = sum(1 for s in run_result.state_flow if s.step_type == StepType.TOOL_CALL)

    t = Table(box=None, show_header=False, padding=(0, 2))
    t.add_column(no_wrap=True)
    t.add_column(no_wrap=True)
    t.add_column(no_wrap=True)
    t.add_column(no_wrap=True)
    t.add_row(
        f"[dim]Status[/dim]\n[{status_colour}]{status_icon} {run_result.status.upper()}[/]",
        f"[dim]Response Time[/dim]\n[bold cyan]⏱  {run_result.response_time_ms:,.0f} ms[/bold cyan]",
        f"[dim]LLM Calls[/dim]\n[bold bright_blue]🤖 {llm_calls}[/bold bright_blue]",
        f"[dim]Tool Calls[/dim]\n[bold yellow]🔧 {tool_calls}[/bold yellow]",
    )
    return t


def _token_table(run_result: RunResult) -> Table:
    u = run_result.usage
    total = u.total_tokens or 1

    t = Table(title="[bold]Token Usage[/bold]", box=None, show_header=True, padding=(0, 1))
    t.add_column("Type",    style="dim",        no_wrap=True, min_width=8)
    t.add_column("Tokens",  justify="right",    no_wrap=True, min_width=7)
    t.add_column("Share",   justify="right",    no_wrap=True, min_width=5)
    t.add_column("",        no_wrap=True,       min_width=_BAR_WIDTH + 2)

    t.add_row("Input",  f"[cyan]{u.input_tokens:,}[/cyan]",
              f"[dim]{u.input_tokens / total * 100:.0f}%[/dim]",
              _bar(u.input_tokens, total, "cyan"))
    t.add_row("Output", f"[bright_blue]{u.output_tokens:,}[/bright_blue]",
              f"[dim]{u.output_tokens / total * 100:.0f}%[/dim]",
              _bar(u.output_tokens, total, "bright_blue"))
    t.add_row("Cached", f"[green]{u.cached_tokens:,}[/green]",
              f"[dim]{u.cached_tokens / max(u.input_tokens, 1) * 100:.0f}%↩[/dim]",
              _bar(u.cached_tokens, u.input_tokens or 1, "green"))
    t.add_section()
    t.add_row("[bold]Total[/bold]", f"[bold]{u.total_tokens:,}[/bold]", "", "")
    return t


def _cost_table(run_result: RunResult) -> Table:
    c = run_result.cost

    t = Table(title="[bold]Cost (USD)[/bold]", box=None, show_header=True, padding=(0, 1))
    t.add_column("Bucket", style="dim",      no_wrap=True, min_width=8)
    t.add_column("Amount", justify="right",  no_wrap=True, min_width=12)

    t.add_row("Input",  f"[cyan]${c.input_cost_usd:.6f}[/cyan]")
    t.add_row("Output", f"[bright_blue]${c.output_cost_usd:.6f}[/bright_blue]")
    t.add_row("Cached", f"[green]${c.cached_cost_usd:.6f}[/green]")
    t.add_section()
    t.add_row("[bold]Total[/bold]", f"[bold green]${c.total_cost_usd:.6f}[/bold green]")
    return t


def _flow_table(run_result: RunResult) -> Table:
    t = Table(title="[bold]State Flow[/bold]", box=None, show_header=True, padding=(0, 1))
    t.add_column("#",       justify="right", style="dim",     no_wrap=True, min_width=2)
    t.add_column("Type",    no_wrap=True,    min_width=14)
    t.add_column("Name",    style="dim",     no_wrap=True,    min_width=14)
    t.add_column("Preview", no_wrap=False,   min_width=30,    max_width=60)
    t.add_column("ms",      justify="right", style="dim",     no_wrap=True, min_width=6)

    for step in run_result.state_flow:
        colour = _STEP_COLOUR.get(step.step_type, "white")
        icon   = _STEP_ICON.get(step.step_type, "•")
        preview = step.content[:80] + ("…" if len(step.content) > 80 else "")
        dur = f"{step.duration_ms:.0f}" if step.duration_ms is not None else "—"
        t.add_row(
            str(step.index),
            f"[{colour}]{icon} {step.step_type}[/{colour}]",
            step.name or "—",
            preview,
            dur,
        )
    return t


def render_result_table(run_result: RunResult) -> Panel:
    """Render a dashboard :class:`~rich.panel.Panel` summarising the run result.

    Sections: summary metrics → token usage + cost (side by side) → state flow.

    Args:
        run_result: The completed run result to render.

    Returns:
        A Rich ``Panel`` ready to pass to ``console.print()``.
    """
    status_colour = _STATUS_COLOUR.get(run_result.status, "white")
    model_short = run_result.model.split(":")[-1]
    query_preview = run_result.query[:80] + ("…" if len(run_result.query) > 80 else "")

    sections: list = [
        Padding(_metrics_table(run_result), (1, 0, 0, 0)),
        Padding(Text(f'"{query_preview}"', style="italic dim"), (0, 0, 1, 0)),
        Columns(
            [
                Panel(_token_table(run_result), border_style="dim", expand=False),
                Panel(_cost_table(run_result),  border_style="dim", expand=False),
            ],
            equal=False,
            expand=False,
        ),
    ]

    if run_result.state_flow:
        sections.append(
            Padding(
                Panel(_flow_table(run_result), border_style="dim", expand=True),
                (1, 0, 0, 0),
            )
        )

    if run_result.error:
        sections.append(
            Padding(Text(f"Error: {run_result.error}", style="bold red"), (1, 0, 0, 0))
        )

    from rich.console import Group  # noqa: PLC0415
    return Panel(
        Group(*sections),
        title=f"[bold]Request Metrics[/bold]  "
              f"[dim]{run_result.request_id}[/dim]  "
              f"[{status_colour}]{model_short}[/{status_colour}]",
        subtitle=f"[dim]{run_result.timestamp}  ·  {run_result.user_id}[/dim]",
        border_style=_STATUS_COLOUR.get(run_result.status, "white").replace("bold ", ""),
        expand=False,
    )
