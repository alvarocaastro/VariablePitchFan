"""Rich table builders for run_analysis CLI output."""
from __future__ import annotations

from pathlib import Path

from rich import box
from rich.panel import Panel
from rich.table import Table


def build_convergence_table(
    conv_log: list[tuple[str, str, float, int]],
) -> Table:
    """Return a Rich Table summarising XFOIL convergence for Stage 2."""
    table = Table(
        title="[bold bright_cyan]XFOIL Convergence Quality — Stage 2[/bold bright_cyan]",
        box=box.SIMPLE_HEAVY,
        border_style="cyan",
        header_style="bold white",
        show_lines=False,
        padding=(0, 1),
    )
    table.add_column("Flight", style="bold cyan", no_wrap=True)
    table.add_column("Section", style="white", no_wrap=True)
    table.add_column("Conv. rate", justify="right", no_wrap=True)
    table.add_column("Failed pts", justify="right", style="dim")
    table.add_column("Análisis OK?", justify="center", no_wrap=True)

    overall_rates: list[float] = []
    for flight, section, conv_rate, conv_failures in conv_log:
        pct = conv_rate * 100
        overall_rates.append(conv_rate)
        if pct >= 80:
            rate_str = f"[bright_green]{pct:.1f}%[/bright_green]"
            ok_str   = "[bright_green]✔ Sí[/bright_green]"
        elif pct >= 60:
            rate_str = f"[yellow]{pct:.1f}%[/yellow]"
            ok_str   = "[yellow]⚠ Aceptable[/yellow]"
        else:
            rate_str = f"[bright_red]{pct:.1f}%[/bright_red]"
            ok_str   = "[bright_red]✘ Revisar[/bright_red]"
        fail_str = str(conv_failures) if conv_failures > 0 else "[dim]0[/dim]"
        table.add_row(flight, section, rate_str, fail_str, ok_str)

    if overall_rates:
        mean_rate = sum(overall_rates) / len(overall_rates) * 100
        mean_color = (
            "bright_green" if mean_rate >= 80 else ("yellow" if mean_rate >= 60 else "bright_red")
        )
        table.add_section()
        table.add_row(
            "[bold]MEDIA[/bold]", "",
            f"[bold {mean_color}]{mean_rate:.1f}%[/bold {mean_color}]",
            "", "",
        )

    return table


def build_summary_table(
    s1, s2, s3, s4, s5, s6, s7, elapsed: float, results_dir: Path,
) -> None:
    """Print the final pipeline summary table and completion panel to the console."""
    from rich.console import Console
    console = Console()

    table = Table(
        title="[bold bright_cyan]VPF Pipeline — Results Summary[/bold bright_cyan]",
        box=box.ROUNDED,
        border_style="cyan",
        header_style="bold bright_white",
        show_lines=True,
    )
    table.add_column("Stage", style="bold cyan", justify="center", no_wrap=True)
    table.add_column("Description", style="white")
    table.add_column("Key Result", style="bright_green")

    table.add_row("1", "Airfoil Selection",
                  f"[vpf.highlight]{s1.selected_airfoil_name}[/vpf.highlight]")
    table.add_row("2", "XFOIL Simulations",
                  f"{s2.n_simulations} sims | {s2.n_convergence_warnings} warnings")
    table.add_row("3", "Compressibility Corrections",
                  f"{s3.n_cases_corrected}/{s3.n_cases_corrected + s3.n_cases_failed} cases "
                  f"({s3.success_rate * 100:.0f}%)")
    table.add_row("4", "Performance Metrics",
                  f"{len(s4.metrics)} metric cases")
    table.add_row("5", "Pitch & Kinematics",
                  f"twist={s5.twist_total_deg:.1f}° | max_loss={s5.max_off_design_loss_pct:.1f}%")
    table.add_row("6", "Reverse Thrust",
                  f"mechanism={s6.mechanism_weight_kg:.0f}kg | ΔSFC=+{s6.sfc_cruise_penalty_pct:.3f}% (theoretical)")
    table.add_row("7", "SFC Analysis",
                  f"[bold bright_green]Mean SFC reduction: {s7.mean_sfc_reduction_pct:.2f}%"
                  f"[/bold bright_green]")

    console.print()
    console.print(table)
    console.print()
    console.print(Panel(
        f"[bold bright_green]✔  Pipeline completed successfully[/bold bright_green]  "
        f"[dim]in {elapsed:.1f}s ({elapsed / 60:.1f} min)[/dim]\n\n"
        f"[dim]Results → {results_dir}[/dim]",
        border_style="bright_green",
        box=box.DOUBLE_EDGE,
        padding=(0, 2),
    ))
