"""TUI rendering with Rich."""

from __future__ import annotations

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from .collector import HostMetrics
from .history import History


def _fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def _bar(percent: float, width: int = 24) -> Text:
    filled = int(percent / 100 * width)
    bar = "█" * filled + "░" * (width - filled)
    color = "red" if percent >= 90 else "yellow" if percent >= 70 else "green"
    t = Text()
    t.append("[", style="dim")
    t.append(bar, style=color)
    t.append("]", style="dim")
    return t


def _pct(percent: float) -> str:
    color = "red" if percent >= 90 else "yellow" if percent >= 70 else "green"
    return f"[{color}]{percent:.1f}%[/{color}]"


def build_layout(host: str, metrics: HostMetrics, hist: History, interval: int) -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="footer", size=1),
    )

    # ── Header ───────────────────────────────────────────────────────────────
    if metrics.error:
        header_text = Text(f" ✗  {host}  —  {metrics.error}", style="bold red")
    else:
        collector_badge = (
            "[dim cyan]py[/dim cyan]" if metrics.collector == "python3"
            else "[dim yellow]sh[/dim yellow]"
        )
        header_text = Text.from_markup(
            f" [bold cyan]{host}[/bold cyan]"
            f"  [dim]│[/dim]  {metrics.os}"
            f"  [dim]│[/dim]  [dim]kernel:[/dim] {metrics.kernel}"
            f"  [dim]│[/dim]  [dim]uptime:[/dim] {metrics.uptime}"
            f"  [dim]│[/dim]  {collector_badge}"
        )

    layout["header"].update(Panel(header_text, box=box.SIMPLE_HEAVY))

    # ── Body ─────────────────────────────────────────────────────────────────
    if metrics.error:
        layout["body"].update(
            Panel(
                Text(f"\n  Cannot connect to host.\n\n  {metrics.error}", style="red"),
                title="Error",
                box=box.ROUNDED,
            )
        )
    else:
        table = Table(box=box.SIMPLE, expand=True, show_header=False, padding=(0, 1))
        table.add_column("metric", style="bold dim", width=5)
        table.add_column("bar", width=24)
        table.add_column("pct", width=7)
        table.add_column("values", style="dim", width=26)
        table.add_column("spark", style="cyan", min_width=20)

        la = metrics.load_avg
        table.add_row(
            "CPU",
            _bar(metrics.cpu),
            _pct(metrics.cpu),
            f"load: {la[0]:.2f}  {la[1]:.2f}  {la[2]:.2f}",
            hist.cpu_spark(32),
        )
        table.add_row(
            "RAM",
            _bar(metrics.mem_percent),
            _pct(metrics.mem_percent),
            f"{_fmt_bytes(metrics.mem_used)} / {_fmt_bytes(metrics.mem_total)}",
            hist.mem_spark(32),
        )
        table.add_row(
            "DISK",
            _bar(metrics.disk_percent),
            _pct(metrics.disk_percent),
            f"{_fmt_bytes(metrics.disk_used)} / {_fmt_bytes(metrics.disk_total)}",
            hist.disk_spark(32),
        )

        layout["body"].update(
            Panel(table, title="[bold]Metrics[/bold]", box=box.ROUNDED)
        )

    # ── Footer ────────────────────────────────────────────────────────────────
    layout["footer"].update(
        Text(
            f"  refresh: {interval}s  │  samples: {hist.sample_count}"
            f"  │  q / Ctrl+C to quit",
            style="dim",
        )
    )

    return layout


def make_live() -> Live:
    return Live(
        renderable=Text("Connecting..."),
        refresh_per_second=4,
        screen=True,
    )