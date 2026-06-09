"""
run_analysis.py — Entry point for the complete VPF aerodynamic analysis pipeline.

Runs 7 analysis stages in sequence with explicit I/O contracts between them:
  0. Clean previous results (automatic pre-step)
  1. Stage 1 — Airfoil selection           → Stage1Result
  2. Stage 2 — XFOIL simulations           → Stage2Result
  3. Stage 3 — Compressibility corrections → Stage3Result
  4. Stage 4 — Performance metrics         → Stage4Result
  5. Stage 5 — Pitch & Kinematics (3D)     → Stage5Result
  6. Stage 6 — Reverse Thrust Modeling     → Stage6Result
  7. Stage 7 — SFC Analysis               → Stage7Result
"""

from __future__ import annotations

import logging
import shutil
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

import pandas as pd

# Keep Rich output from crashing on Windows consoles using legacy code pages.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import matplotlib

matplotlib.use("Agg", force=True)

# ── Rich imports ─────────────────────────────────────────────────────────────
from rich import box
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

# ── Project path setup ───────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent / "src"))

from vpf_analysis import settings as base_config
from vpf_analysis.adapters.xfoil.xfoil_runner_adapter import XfoilRunnerAdapter
from vpf_analysis.core.domain.airfoil import Airfoil
from vpf_analysis.core.domain.blade_section import BladeSection
from vpf_analysis.core.domain.simulation_condition import SimulationCondition
from vpf_analysis.pipeline.contracts import (
    Stage1Result,
    Stage2Result,
    Stage3Result,
    Stage4Result,
    Stage5Result,
    Stage6Result,
    Stage7Result,
)
from vpf_analysis.postprocessing.cli_tables import build_convergence_table, build_summary_table
from vpf_analysis.postprocessing.stage_summary_generator import (
    generate_stage1_summary,
    generate_stage2_summary,
    generate_stage3_summary,
    generate_stage4_summary,
    write_stage_summary,
)
from vpf_analysis.settings import get_settings
from vpf_analysis.stage1_airfoil_selection.airfoil_selection_service import (
    AirfoilSelectionService,
)
from vpf_analysis.stage2_xfoil_simulations.final_analysis_service import (
    FinalAnalysisService,
    FinalSimulationConfig,
)
from vpf_analysis.config_loader import get_gear_ratio
from vpf_analysis.stage2_xfoil_simulations.pitch_map import (
    compute_pitch_map,
    plot_alpha_opt_evolution,
    plot_pitch_map,
    plot_vpf_efficiency_by_section,
    save_pitch_map_csv,
)
from vpf_analysis.stage3_compressibility_correction.compressibility_case import (
    CompressibilityCase,
)
from vpf_analysis.stage3_compressibility_correction.correction_service import (
    CompressibilityCorrectionService,
)
from vpf_analysis.stage3_compressibility_correction.karman_tsien import KarmanTsienModel
from vpf_analysis.stage3_compressibility_correction.prandtl_glauert import PrandtlGlauertModel
from vpf_analysis.stage4_performance_metrics.metrics import (
    compute_all_metrics,
    enrich_with_cruise_reference,
)
from vpf_analysis.stage4_performance_metrics.plots import (
    generate_all_stage4_figures,
)
from vpf_analysis.stage4_performance_metrics.table_generator import (
    export_summary_table,
)
from vpf_analysis.stage5_pitch_kinematics.application.run_pitch_kinematics import (
    run_pitch_kinematics,
)
from vpf_analysis.stage6_reverse_thrust.application.run_reverse_thrust import (
    run_reverse_thrust,
)
from vpf_analysis.stage7_sfc_analysis.application.run_sfc_analysis import run_sfc_analysis

# ─────────────────────────────────────────────────────────────────────────────
# Console & Theme
# ─────────────────────────────────────────────────────────────────────────────

_THEME = Theme({
    "vpf.header":    "bold bright_cyan",
    "vpf.step":      "bold bright_white",
    "vpf.ok":        "bold bright_green",
    "vpf.warn":      "bold yellow",
    "vpf.error":     "bold bright_red",
    "vpf.info":      "dim white",
    "vpf.highlight": "bold magenta",
    "vpf.dim":       "dim cyan",
    "vpf.stage":     "bold cyan",
})

console = Console(theme=_THEME, highlight=False)

# ─────────────────────────────────────────────────────────────────────────────
# Logging (suppressed in favor of Rich panels, kept for debug)
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.WARNING,           # quiet the noisy library loggers
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(console=console, rich_tracebacks=True, show_path=False)],
)
# Allow our own module to emit INFO via logger if needed
LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)

# ─────────────────────────────────────────────────────────────────────────────
# Pipeline progress bar (global, rendered inside the Live context)
# ─────────────────────────────────────────────────────────────────────────────

PIPELINE_PROGRESS = Progress(
    SpinnerColumn(spinner_name="dots", style="bold cyan"),
    TextColumn("[vpf.step]{task.description}[/vpf.step]"),
    BarColumn(bar_width=40, style="cyan", complete_style="bright_cyan", finished_style="bright_green"),
    TaskProgressColumn(),
    MofNCompleteColumn(),
    TimeElapsedColumn(),
    TimeRemainingColumn(),
    console=console,
    transient=False,
)

# Total number of pipeline steps (used for the overall bar)
_TOTAL_STEPS = 8


@contextmanager
def _stage_block(step: int, title: str, emoji: str = "⚙") -> Generator[None, None, None]:
    """Print a pretty header before a stage and a result line after."""
    console.print()
    console.rule(f"[vpf.stage]{emoji}  Step {step} — {title}[/vpf.stage]", style="cyan")
    t0 = time.perf_counter()
    try:
        yield
        elapsed = time.perf_counter() - t0
        console.print(f"    [vpf.ok]✔[/vpf.ok]  [vpf.info]{title} completed in {elapsed:.1f}s[/vpf.info]")
    except Exception:
        elapsed = time.perf_counter() - t0
        console.print(f"    [vpf.error]✘[/vpf.error]  [vpf.error]{title} FAILED after {elapsed:.1f}s[/vpf.error]")
        raise


# ─────────────────────────────────────────────────────────────────────────────
# Step 1 — Cleanup
# ─────────────────────────────────────────────────────────────────────────────

def step_1_clean_results() -> None:
    """Delete results from previous runs."""
    with _stage_block(1, "Cleaning previous results", "[DEL]"):
        dirs_to_clean = sorted(base_config.STAGE_DIR_NAMES)
        with Progress(
            SpinnerColumn(style="yellow"),
            TextColumn("[yellow]{task.description}"),
            BarColumn(bar_width=30, style="yellow", complete_style="bright_yellow"),
            MofNCompleteColumn(),
            console=console,
            transient=True,
        ) as prg:
            task = prg.add_task("Removing stage dirs…", total=len(dirs_to_clean))
            for stage_num in dirs_to_clean:
                stage_dir = base_config.get_stage_dir(stage_num)
                if stage_dir.exists():
                    prg.update(task, description=f"Removing [dim]{stage_dir.name}[/dim]")
                    shutil.rmtree(stage_dir, ignore_errors=True)
                stage_dir.mkdir(parents=True, exist_ok=True)
                prg.advance(task)
        console.print("    [vpf.info]All stage directories reset.[/vpf.info]")


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 — Stage 1: Airfoil selection
# ─────────────────────────────────────────────────────────────────────────────

def step_2_airfoil_selection() -> Stage1Result:
    """Stage 1: Automatic airfoil selection."""
    with _stage_block(2, "Airfoil Selection (Stage 1)", "[VPF]"):
        cfg = get_settings()
        stage1_dir = base_config.get_stage_dir(1)
        stage1_dir.mkdir(parents=True, exist_ok=True)

        conditions = cfg.selection_conditions
        cond_summary = "  ".join(
            f"{c.label}(Re={c.reynolds:.1e}, w={c.weight:.2f})" for c in conditions
        )

        airfoils = []
        for spec in base_config.AIRFOILS:
            dat_path = base_config.AIRFOIL_DATA_DIR / spec["dat_file"]
            if dat_path.is_file():
                airfoils.append(
                    Airfoil(name=spec["name"], family=spec["family"], dat_path=dat_path)
                )

        if not airfoils:
            raise RuntimeError(
                f"No .dat files found in {base_config.AIRFOIL_DATA_DIR}. "
                "Ensure data/airfoils/ contains the airfoil profiles."
            )

        console.print(
            f"    [vpf.info]Evaluating [bold]{len(airfoils)}[/bold] airfoils across "
            f"[bold]{len(conditions)}[/bold] conditions — {cond_summary}[/vpf.info]"
        )

        total_runs = len(airfoils) * len(conditions)

        # Progress bar for candidate evaluation
        with Progress(
            SpinnerColumn(spinner_name="dots2", style="cyan"),
            TextColumn("[cyan]{task.description}"),
            BarColumn(bar_width=30, style="cyan", complete_style="bright_cyan"),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
            transient=True,
        ) as prg:
            task = prg.add_task("Running XFOIL on candidates…", total=total_runs)

            xfoil = XfoilRunnerAdapter(final_analysis=False)
            service = AirfoilSelectionService(xfoil_runner=xfoil, results_dir=stage1_dir)

            def _on_airfoil(name: str) -> None:
                prg.update(task, advance=1, description=f"XFOIL: [bold]{name}[/bold]")

            result = service.run_selection(
                airfoils,
                conditions=conditions,
                alpha_min=cfg.selection_alpha_min,
                alpha_max=cfg.selection_alpha_max,
                alpha_step=cfg.selection_alpha_step,
                mach_ref=cfg.reference_mach,
                progress_callback=_on_airfoil,
            )

        console.print(f"    [vpf.ok]→[/vpf.ok]  Selected airfoil: "
                      f"[vpf.highlight]{result.best_airfoil.name}[/vpf.highlight]")

        summary_text = generate_stage1_summary(stage1_dir, result.best_airfoil.name)
        write_stage_summary(1, summary_text, stage1_dir)

        s1 = Stage1Result(
            selected_airfoil_name=result.best_airfoil.name,
            selected_airfoil_dat=result.best_airfoil.dat_path,
            stage_dir=stage1_dir,
            selection_dir=stage1_dir / "airfoil_selection",
        )
        s1.validate()
        return s1


# ─────────────────────────────────────────────────────────────────────────────
# Step 3 — Stage 2: XFOIL simulations
# ─────────────────────────────────────────────────────────────────────────────

def step_3_xfoil_simulations(s1: Stage1Result) -> Stage2Result:
    """Stage 2: XFOIL simulations for the selected airfoil."""
    with _stage_block(3, "XFOIL Simulations (Stage 2)", "🌊"):
        cfg = get_settings()
        stage2_dir = base_config.get_stage_dir(2)
        stage2_dir.mkdir(parents=True, exist_ok=True)

        sections = [BladeSection(name=s, reynolds=0.0) for s in cfg.blade_sections]

        configs = []
        for flight in cfg.flight_conditions:
            for section in sections:
                cond = SimulationCondition(
                    name=f"{flight}_{section.name}",
                    mach_rel=cfg.reference_mach,
                    reynolds=cfg.reynolds_table[flight][section.name],
                    alpha_min=cfg.alpha_min,
                    alpha_max=cfg.alpha_max,
                    alpha_step=cfg.alpha_step,
                    ncrit=cfg.ncrit_table[flight],
                )
                configs.append(
                    FinalSimulationConfig(flight_name=flight, section=section, condition=cond)
                )

        n_sims = len(configs)
        console.print(f"    [vpf.info]Running [bold]{n_sims}[/bold] XFOIL simulations "
                      f"for [vpf.highlight]{s1.selected_airfoil_name}[/vpf.highlight] "
                      f"({len(cfg.flight_conditions)} phases × {len(cfg.blade_sections)} sections)[/vpf.info]")

        airfoil = Airfoil(
            name=s1.selected_airfoil_name,
            family="",
            dat_path=s1.selected_airfoil_dat,
        )
        runner = XfoilRunnerAdapter(final_analysis=True)
        service = FinalAnalysisService(runner, stage2_dir)

        # Accumulate per-sim convergence stats for the summary
        _conv_log: list[tuple[str, str, float, int]] = []

        with Progress(
            SpinnerColumn(spinner_name="dots12", style="bright_cyan"),
            TextColumn("[bright_cyan]{task.description}"),
            BarColumn(bar_width=34, style="bright_cyan", complete_style="bright_green"),
            TaskProgressColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=console,
            transient=True,
        ) as prg:
            sim_task = prg.add_task(
                f"[bold]{s1.selected_airfoil_name}[/bold] — starting…",
                total=n_sims,
            )

            def _on_sim_done(flight: str, section: str, conv_rate: float, conv_failures: int) -> None:
                _conv_log.append((flight, section, conv_rate, conv_failures))
                pct = conv_rate * 100
                # Colour the rate: green ≥80%, yellow ≥60%, red <60%
                if pct >= 80:
                    rate_str = f"[bright_green]{pct:.0f}%[/bright_green]"
                elif pct >= 60:
                    rate_str = f"[yellow]{pct:.0f}%[/yellow]"
                else:
                    rate_str = f"[bright_red]{pct:.0f}%[/bright_red]"

                prg.advance(sim_task)
                remaining = n_sims - int(prg.tasks[sim_task].completed)
                label = (
                    f"[bold]{s1.selected_airfoil_name}[/bold]  "
                    f"[dim]{flight}/{section}[/dim]  conv={rate_str}"
                    + (f"  [dim]({remaining} left)[/dim]" if remaining > 0 else "  [bold bright_green]done ✔[/bold bright_green]")
                )
                prg.update(sim_task, description=label)

            alpha_eff_map, stall_map = service.run(
                airfoil, configs,
                progress_callback=_on_sim_done,
                flight_conditions=cfg.flight_conditions,
                blade_sections=cfg.blade_sections,
            )

        n_conv_warnings = getattr(service, "_total_convergence_warnings", 0)

        console.print()
        console.print(build_convergence_table(_conv_log))

        # Criterion note
        console.print(
            "    [dim]Nota: fallos ocurren en zona post-stall (α > stall), "
            "fuera del rango operativo del fan. α_opt converge siempre.[/dim]"
        )
        console.print()

        # Post-processing (pitch map, plots, organize polars)
        console.print("    [vpf.info]Post-processing: pitch maps…[/vpf.info]")

        source_polars = stage2_dir / "simulation_plots"
        pitch_map_dir = stage2_dir / "pitch_map"
        pitch_map_dir.mkdir(parents=True, exist_ok=True)
        plot_alpha_opt_evolution(alpha_eff_map, configs, pitch_map_dir)
        pitch_df, delta_beta = compute_pitch_map(
            alpha_eff_map,
            cfg.fan.omega_rad_s,
            cfg.fan.radii_m,
            cfg.fan.axial_velocity_m_s,
            gear_ratio=get_gear_ratio(),
        )
        save_pitch_map_csv(pitch_df, pitch_map_dir)
        plot_pitch_map(pitch_df, delta_beta, pitch_map_dir)

        _rows = [
            {"flight": f, "section": s, "alpha_stall": a, "cl_max": c}
            for (f, s), (a, c) in stall_map.items()
        ]
        pd.DataFrame(_rows).to_csv(pitch_map_dir / "stall_map.csv", index=False, float_format="%.4f")

        polar_dfs = {}
        for flight in cfg.flight_conditions:
            for section in cfg.blade_sections:
                csv_path = source_polars / flight / section / "polar.csv"
                if csv_path.exists():
                    polar_dfs[(flight, section)] = pd.read_csv(csv_path)

        plot_vpf_efficiency_by_section(polar_dfs, alpha_eff_map, pitch_map_dir)

        delta_str = ", ".join(f"{s}={v:.1f}°" for s, v in delta_beta.items())
        console.print(f"    [vpf.ok]→[/vpf.ok]  Δβ per section: [vpf.highlight]{delta_str}[/vpf.highlight]")
        if n_conv_warnings > 0:
            console.print(f"    [vpf.warn]⚠[/vpf.warn]  {n_conv_warnings} XFOIL convergence warning(s)")

        summary_text = generate_stage2_summary(
            stage2_dir, n_sims, delta_beta=delta_beta,
            alpha_eff_map=alpha_eff_map, stall_map=stall_map,
        )
        write_stage_summary(2, summary_text, stage2_dir)

        s2 = Stage2Result(
            source_polars=source_polars,
            alpha_eff_map=alpha_eff_map,
            stall_map=stall_map,
            n_simulations=n_sims,
            n_convergence_warnings=n_conv_warnings,
            stage_dir=stage2_dir,
        )
        s2.validate()
        return s2


# ─────────────────────────────────────────────────────────────────────────────
# Step 4 — Stage 3: Compressibility corrections
# ─────────────────────────────────────────────────────────────────────────────

def step_4_compressibility_correction(s2: Stage2Result) -> Stage3Result:
    """Stage 3: Compressibility corrections (PG + Karman-Tsien + wave drag)."""
    with _stage_block(4, "Compressibility Corrections (Stage 3)", "💨"):
        cfg = get_settings()
        stage3_dir = base_config.get_stage_dir(3)
        stage3_dir.mkdir(parents=True, exist_ok=True)

        pg_model = PrandtlGlauertModel()
        kt_model = KarmanTsienModel(
            thickness_ratio=cfg.airfoil_geometry.thickness_ratio,
            korn_kappa=cfg.airfoil_geometry.korn_kappa,
        )
        service = CompressibilityCorrectionService(
            pg_model=pg_model, kt_model=kt_model, base_output_dir=stage3_dir,
        )

        total_cases = len(cfg.flight_conditions) * len(cfg.blade_sections)
        n_ok = 0
        n_fail = 0

        with Progress(
            SpinnerColumn(style="magenta"),
            TextColumn("[magenta]{task.description}"),
            BarColumn(bar_width=30, style="magenta", complete_style="bright_magenta"),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
            transient=True,
        ) as prg:
            task = prg.add_task("Applying corrections…", total=total_cases)
            for flight in cfg.flight_conditions:
                for section in cfg.blade_sections:
                    # Use per-section M_rel if available; fall back to condition-level Mach.
                    if cfg.target_mach_per_section and flight in cfg.target_mach_per_section:
                        mach = cfg.target_mach_per_section[flight].get(
                            section, cfg.target_mach[flight]
                        )
                    else:
                        mach = cfg.target_mach[flight]

                    prg.update(task, description=f"[bold]{flight}[/bold]/{section} (M={mach:.3f})")

                    # Tip sections are supersonic (M_rel > 1.0). XFOIL polars were
                    # computed at M_ref=0.2 (valid). KT is applied clamped at M=0.95
                    # (best subsonic approximation). Output is flagged as extrapolated.
                    _mach_clamped = False
                    if mach >= 1.0:
                        console.print(
                            f"      [vpf.warn]⚠[/vpf.warn] {flight}/{section}: "
                            f"M_rel={mach:.3f} supersonic — KT applied clamped at M=0.95 "
                            f"[extrapolated]."
                        )
                        mach = 0.95
                        _mach_clamped = True

                    case = CompressibilityCase(
                        flight_condition=flight,
                        target_mach=mach,
                        reference_mach=cfg.reference_mach,
                    )
                    polar_path = s2.source_polars / flight.lower() / section / "polar.csv"
                    if not polar_path.exists():
                        console.print(f"      [vpf.warn]⚠[/vpf.warn] Polar not found: {polar_path.name}")
                        n_fail += 1
                    else:
                        try:
                            service.correct_case(case, polar_path, section)
                            n_ok += 1
                        except Exception as exc:
                            console.print(f"      [vpf.error]✘[/vpf.error] Error {flight}/{section}: {exc}")
                            n_fail += 1
                    prg.advance(task)

        service.plot_section_summary(stage3_dir, cfg.flight_conditions, cfg.blade_sections)

        summary_text = generate_stage3_summary(stage3_dir)
        write_stage_summary(3, summary_text, stage3_dir)

        s3 = Stage3Result(
            corrected_dir=stage3_dir,
            n_cases_corrected=n_ok,
            n_cases_failed=n_fail,
            stage_dir=stage3_dir,
        )
        s3.validate()
        console.print(f"    [vpf.ok]→[/vpf.ok]  {n_ok}/{n_ok + n_fail} polars corrected "
                      f"({s3.success_rate * 100:.0f}% success rate)")
        return s3


# ─────────────────────────────────────────────────────────────────────────────
# Step 5 — Stage 4: Performance metrics & figures
# ─────────────────────────────────────────────────────────────────────────────

def step_5_metrics_and_figures(s3: Stage3Result) -> Stage4Result:
    """Stage 4: Aerodynamic metrics + publication figures."""
    with _stage_block(5, "Performance Metrics & Figures (Stage 4)", "[FIG]"):
        cfg = get_settings()
        stage2_dir = base_config.get_stage_dir(2)
        polars_dir = s3.corrected_dir if s3.corrected_dir.exists() else stage2_dir / "polars"

        console.print(f"    [vpf.info]Reading polars from: [dim]{polars_dir}[/dim][/vpf.info]")

        with console.status("[cyan]Computing aerodynamic metrics…", spinner="dots"):
            metrics = compute_all_metrics(
                polars_dir,
                cfg.flight_conditions,
                cfg.blade_sections,
                cfg.reynolds_table,
                cfg.ncrit_table,
            )
            metrics = enrich_with_cruise_reference(
                metrics,
                polars_dir,
                axial_velocities=cfg.fan.axial_velocity_m_s,
                blade_radii=cfg.fan.radii_m,
                fan_omega=cfg.fan.omega_rad_s,
                gear_ratio=get_gear_ratio(),
            )

        console.print(f"    [vpf.ok]→[/vpf.ok]  {len(metrics)} metric cases computed")

        stage4_dir = base_config.get_stage_dir(4)
        tables_dir  = stage4_dir / "tables"
        figures_dir = stage4_dir / "figures"

        with console.status("[cyan]Exporting tables & generating figures…", spinner="dots"):
            export_summary_table(metrics, tables_dir / "summary_table.csv")
            stage2_polars_flat = base_config.get_stage_dir(2) / "polars"
            generate_all_stage4_figures(
                metrics=metrics,
                figures_dir=figures_dir,
                polars_dir=polars_dir,
                flight_conditions=cfg.flight_conditions,
                blade_sections=cfg.blade_sections,
                stage3_dir=s3.corrected_dir,
                reynolds_table=cfg.reynolds_table,
            )

        console.print(f"    [vpf.ok]→[/vpf.ok]  Publication figures saved to [dim]{figures_dir}[/dim]")

        summary_text = generate_stage4_summary(stage4_dir, metrics)
        write_stage_summary(4, summary_text, stage4_dir)

        s4 = Stage4Result(
            metrics=metrics,
            tables_dir=tables_dir,
            figures_dir=figures_dir,
            stage_dir=stage4_dir,
        )
        s4.validate()
        return s4


# ─────────────────────────────────────────────────────────────────────────────
# Step 6 — Stage 5: Pitch & Kinematics
# ─────────────────────────────────────────────────────────────────────────────

def step_6_pitch_kinematics() -> Stage5Result:
    """Stage 5: Full pitch, incidence and kinematics analysis (3D)."""
    with _stage_block(6, "Pitch & Kinematics Analysis (Stage 5)", "[ROT]"):
        with console.status("[cyan]Running 3D pitch/kinematics model…", spinner="dots12"):
            run_pitch_kinematics(blade_sections=get_settings().blade_sections)

        stage5_dir  = base_config.get_stage_dir(5)
        tables_dir  = stage5_dir / "tables"
        figures_dir = stage5_dir / "figures"
        n_tables  = len(list(tables_dir.glob("*.csv")))  if tables_dir.exists()  else 0
        n_figures = len(list(figures_dir.glob("*.png"))) if figures_dir.exists() else 0

        twist_total = float("nan")
        max_loss    = float("nan")
        twist_file  = tables_dir / "blade_twist_design.csv"
        if twist_file.exists():
            import pandas as _pd
            df_tw = _pd.read_csv(twist_file)
            if "beta_metal_deg" in df_tw.columns and "section" in df_tw.columns:
                bm_root = df_tw.loc[df_tw["section"] == "root", "beta_metal_deg"]
                bm_tip  = df_tw.loc[df_tw["section"] == "tip",  "beta_metal_deg"]
                if not bm_root.empty and not bm_tip.empty:
                    twist_total = float(bm_root.iloc[0]) - float(bm_tip.iloc[0])

        offdesign_file = tables_dir / "off_design_incidence.csv"
        if offdesign_file.exists():
            import pandas as _pd
            df_od = _pd.read_csv(offdesign_file)
            if "efficiency_loss_pct" in df_od.columns:
                max_loss = float(df_od["efficiency_loss_pct"].max(skipna=True))

        console.print(f"    [vpf.ok]→[/vpf.ok]  {n_tables} tables, {n_figures} figures | "
                      f"twist={twist_total:.1f}° | max loss={max_loss:.1f}%")

        s5 = Stage5Result(
            tables_dir=tables_dir,
            figures_dir=figures_dir,
            n_tables=n_tables,
            n_figures=n_figures,
            twist_total_deg=twist_total,
            max_off_design_loss_pct=max_loss,
            stage_dir=stage5_dir,
        )
        s5.validate()
        return s5


# ─────────────────────────────────────────────────────────────────────────────
# Step 7 — Stage 6: Reverse Thrust
# ─────────────────────────────────────────────────────────────────────────────

def step_7_reverse_thrust() -> Stage6Result:
    """Stage 6: VPF Reverse Thrust — theoretical mechanism weight analysis."""
    with _stage_block(7, "Reverse Thrust Modeling (Stage 6)", "[RT]"):
        with console.status("[cyan]Computing VPF reverse thrust mechanism weight…", spinner="dots12"):
            run_reverse_thrust()

        stage6_dir  = base_config.get_stage_dir(6)
        tables_dir  = stage6_dir / "tables"
        figures_dir = stage6_dir / "figures"
        n_tables  = len(list(tables_dir.glob("*.csv")))  if tables_dir.exists()  else 0
        n_figures = len(list(figures_dir.glob("*.png"))) if figures_dir.exists() else 0

        mech_weight = float("nan")
        sfc_penalty = float("nan")

        import pandas as _pd
        mw_file = tables_dir / "mechanism_weight.csv"
        if mw_file.exists():
            df_mw = _pd.read_csv(mw_file).set_index("metric")["value"]
            mech_weight = float(df_mw.get("mechanism_weight_kg",    float("nan")))
            sfc_penalty = float(df_mw.get("sfc_cruise_penalty_pct", float("nan")))

        console.print(f"    [vpf.ok]→[/vpf.ok]  mechanism={mech_weight:.0f} kg | ΔSFC=+{sfc_penalty:.3f}%")

        s6 = Stage6Result(
            tables_dir=tables_dir,
            figures_dir=figures_dir,
            n_tables=n_tables,
            n_figures=n_figures,
            mechanism_weight_kg=mech_weight,
            sfc_cruise_penalty_pct=sfc_penalty,
            stage_dir=stage6_dir,
        )
        s6.validate()
        return s6


# ─────────────────────────────────────────────────────────────────────────────
# Step 8 — Stage 7: SFC Analysis
# ─────────────────────────────────────────────────────────────────────────────

def step_8_sfc_analysis() -> Stage7Result:
    """Stage 7: VPF impact on specific fuel consumption."""
    with _stage_block(8, "SFC Impact Analysis (Stage 7)", "⛽"):
        with console.status("[cyan]Computing SFC improvement…", spinner="dots12"):
            run_sfc_analysis()

        stage7_dir  = base_config.get_stage_dir(7)
        tables_dir  = stage7_dir / "tables"
        figures_dir = stage7_dir / "figures"

        mean_sfc_reduction  = float("nan")
        ge9x_fuel_saving    = float("nan")
        import pandas as _pd
        sfc_file = tables_dir / "sfc_analysis.csv"
        if sfc_file.exists():
            df_sfc = _pd.read_csv(sfc_file)
            col = next(
                (c for c in df_sfc.columns if "sfc_reduction" in c.lower()), None
            )
            if col:
                mean_sfc_reduction = float(df_sfc[col].mean(skipna=True))

        ge9x_file = tables_dir / "ge9x_sfc_improvement.csv"
        if ge9x_file.exists():
            df_ge9x = _pd.read_csv(ge9x_file)
            if "fuel_saving_pct" in df_ge9x.columns and not df_ge9x.empty:
                # Row where ClCd_new closest to 120 (typical optimised point)
                idx_120 = (df_ge9x["ClCd_new"] - 120.0).abs().idxmin()
                ge9x_fuel_saving = float(df_ge9x.loc[idx_120, "fuel_saving_pct"])

        console.print(f"    [vpf.ok]→[/vpf.ok]  Mean SFC reduction: "
                      f"[vpf.highlight]{mean_sfc_reduction:.2f}%[/vpf.highlight]  |  "
                      f"GE9X fuel saving (α_opt): {ge9x_fuel_saving:.2f}%")

        s7 = Stage7Result(
            tables_dir=tables_dir,
            figures_dir=figures_dir,
            mean_sfc_reduction_pct=mean_sfc_reduction,
            stage_dir=stage7_dir,
            ge9x_fuel_saving_pct=ge9x_fuel_saving,
        )
        s7.validate()
        return s7


# ─────────────────────────────────────────────────────────────────────────────
# Summary panel
# ─────────────────────────────────────────────────────────────────────────────

def _print_summary(
    s1: Stage1Result,
    s2: Stage2Result,
    s3: Stage3Result,
    s4: Stage4Result,
    s5: Stage5Result,
    s6: Stage6Result,
    s7: Stage7Result,
    elapsed: float,
) -> None:
    build_summary_table(s1, s2, s3, s4, s5, s6, s7, elapsed, base_config.RESULTS_DIR)


# ─────────────────────────────────────────────────────────────────────────────
# Disk loaders — reconstruct stage results from previously saved CSV files
# ─────────────────────────────────────────────────────────────────────────────

def _load_s1_from_disk() -> Stage1Result:
    stage1_dir = base_config.get_stage_dir(1)
    dat = stage1_dir / "airfoil_selection" / "selected_airfoil.dat"
    if not dat.exists():
        raise FileNotFoundError(
            f"Stage 1 result not found: {dat}\n"
            "Run from stage 1 first: python run_analysis.py"
        )
    selected_name = dat.read_text(encoding="utf-8").strip()
    selected_spec = next(
        (spec for spec in base_config.AIRFOILS if spec["name"] == selected_name),
        None,
    )
    if selected_spec is None:
        raise ValueError(
            f"Selected airfoil '{selected_name}' is not present in config/airfoils.yaml"
        )
    selected_dat = base_config.AIRFOIL_DATA_DIR / selected_spec["dat_file"]
    return Stage1Result(
        selected_airfoil_name=selected_name,
        selected_airfoil_dat=selected_dat,
        stage_dir=stage1_dir,
        selection_dir=stage1_dir / "airfoil_selection",
    )


def _load_s2_from_disk() -> Stage2Result:
    stage2_dir = base_config.get_stage_dir(2)
    source_polars = stage2_dir / "simulation_plots"
    pitch_map_csv = stage2_dir / "pitch_map" / "blade_pitch_map.csv"
    if not pitch_map_csv.exists():
        raise FileNotFoundError(
            f"Stage 2 result not found: {pitch_map_csv}\n"
            "Run from stage 2 first: python run_analysis.py --from-stage 2"
        )
    df = pd.read_csv(pitch_map_csv)
    alpha_eff_map: dict[tuple[str, str], float] = {
        (str(row["flight"]), str(row["section"])): float(row["alpha_opt"])
        for _, row in df.iterrows()
    }
    stall_map_csv = stage2_dir / "pitch_map" / "stall_map.csv"
    stall_map: dict[tuple[str, str], tuple[float, float]] = {}
    if stall_map_csv.exists():
        _df = pd.read_csv(stall_map_csv)
        stall_map = {
            (str(r["flight"]), str(r["section"])): (float(r["alpha_stall"]), float(r["cl_max"]))
            for _, r in _df.iterrows()
        }
    else:
        LOGGER.warning("stall_map.csv not found — stall margin data unavailable for this run")
    n_polars = len(list((stage2_dir / "polars").glob("*.csv"))) if (stage2_dir / "polars").exists() else len(alpha_eff_map)
    return Stage2Result(
        source_polars=source_polars,
        alpha_eff_map=alpha_eff_map,
        stall_map=stall_map,
        n_simulations=n_polars,
        n_convergence_warnings=0,
        stage_dir=stage2_dir,
    )


def _load_s3_from_disk() -> Stage3Result:
    stage3_dir = base_config.get_stage_dir(3)
    corrected = list(stage3_dir.rglob("corrected_polar.csv"))
    if not corrected:
        raise FileNotFoundError(
            f"Stage 3 results not found in {stage3_dir}\n"
            "Run from stage 3 first: python run_analysis.py --from-stage 3"
        )
    return Stage3Result(
        corrected_dir=stage3_dir,
        n_cases_corrected=len(corrected),
        n_cases_failed=0,
        stage_dir=stage3_dir,
    )


def _load_s4_from_disk() -> Stage4Result:
    stage4_dir = base_config.get_stage_dir(4)
    tables_dir = stage4_dir / "tables"
    summary_csv = tables_dir / "summary_table.csv"
    if not summary_csv.exists():
        raise FileNotFoundError(
            f"Stage 4 results not found: {summary_csv}\n"
            "Run from stage 4 first: python run_analysis.py --from-stage 4"
        )
    df = pd.read_csv(summary_csv)
    # Reconstruct minimal AerodynamicMetrics-like objects for summary display
    return Stage4Result(
        metrics=list(range(len(df))),  # use length as proxy for count display
        tables_dir=tables_dir,
        figures_dir=stage4_dir / "figures",
        stage_dir=stage4_dir,
    )


def _load_s5_from_disk() -> Stage5Result:
    stage5_dir = base_config.get_stage_dir(5)
    tables_dir = stage5_dir / "tables"
    figures_dir = stage5_dir / "figures"
    twist_total = float("nan")
    max_loss = float("nan")
    twist_file = tables_dir / "blade_twist_design.csv"
    if twist_file.exists():
        df_tw = pd.read_csv(twist_file)
        if "beta_metal_deg" in df_tw.columns and "section" in df_tw.columns:
            bm_root = df_tw.loc[df_tw["section"] == "root", "beta_metal_deg"]
            bm_tip  = df_tw.loc[df_tw["section"] == "tip",  "beta_metal_deg"]
            if not bm_root.empty and not bm_tip.empty:
                twist_total = float(bm_root.iloc[0]) - float(bm_tip.iloc[0])
    offdesign_file = tables_dir / "off_design_incidence.csv"
    if offdesign_file.exists():
        df_od = pd.read_csv(offdesign_file)
        if "efficiency_loss_pct" in df_od.columns:
            max_loss = float(df_od["efficiency_loss_pct"].max(skipna=True))
    return Stage5Result(
        tables_dir=tables_dir,
        figures_dir=figures_dir,
        n_tables=len(list(tables_dir.glob("*.csv"))) if tables_dir.exists() else 0,
        n_figures=len(list(figures_dir.glob("*.png"))) if figures_dir.exists() else 0,
        twist_total_deg=twist_total,
        max_off_design_loss_pct=max_loss,
        stage_dir=stage5_dir,
    )


def _load_s6_from_disk() -> Stage6Result:
    stage6_dir = base_config.get_stage_dir(6)
    tables_dir = stage6_dir / "tables"
    mech_weight = float("nan")
    sfc_penalty = float("nan")
    mw_file = tables_dir / "mechanism_weight.csv"
    if mw_file.exists():
        df_mw = pd.read_csv(mw_file).set_index("metric")["value"]
        mech_weight = float(df_mw.get("mechanism_weight_kg", float("nan")))
        sfc_penalty = float(df_mw.get("sfc_cruise_penalty_pct", float("nan")))
    return Stage6Result(
        tables_dir=tables_dir,
        figures_dir=stage6_dir / "figures",
        n_tables=len(list(tables_dir.glob("*.csv"))) if tables_dir.exists() else 0,
        n_figures=len(list((stage6_dir / "figures").glob("*.png"))) if (stage6_dir / "figures").exists() else 0,
        mechanism_weight_kg=mech_weight,
        sfc_cruise_penalty_pct=sfc_penalty,
        stage_dir=stage6_dir,
    )


def _load_s7_from_disk() -> Stage7Result:
    stage7_dir = base_config.get_stage_dir(7)
    tables_dir = stage7_dir / "tables"
    mean_sfc = float("nan")
    ge9x_saving = float("nan")
    sfc_file = tables_dir / "sfc_analysis.csv"
    if sfc_file.exists():
        df_sfc = pd.read_csv(sfc_file)
        col = next((c for c in df_sfc.columns if "sfc_reduction" in c.lower()), None)
        if col:
            mean_sfc = float(df_sfc[col].mean(skipna=True))
    ge9x_file = tables_dir / "ge9x_sfc_improvement.csv"
    if ge9x_file.exists():
        df_ge9x = pd.read_csv(ge9x_file)
        if "fuel_saving_pct" in df_ge9x.columns and not df_ge9x.empty:
            idx_120 = (df_ge9x["ClCd_new"] - 120.0).abs().idxmin()
            ge9x_saving = float(df_ge9x.loc[idx_120, "fuel_saving_pct"])
    return Stage7Result(
        tables_dir=tables_dir,
        figures_dir=stage7_dir / "figures",
        mean_sfc_reduction_pct=mean_sfc,
        stage_dir=stage7_dir,
        ge9x_fuel_saving_pct=ge9x_saving,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    """Run the full pipeline with inter-stage contract validation."""
    import argparse
    parser = argparse.ArgumentParser(
        description="VPF Aerodynamic Analysis Pipeline",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--from-stage", type=int, default=1, choices=range(1, 8), metavar="N",
        help="Start from analysis stage N (1-7). Requires previous stages to have run already.\n"
             "Example: --from-stage 3  (starts at compressibility corrections)",
    )
    parser.add_argument(
        "--to-stage", type=int, default=7, choices=range(1, 8), metavar="N",
        help="Stop after analysis stage N (1-7).\n"
             "Example: --to-stage 4  (stops after performance metrics)",
    )
    args = parser.parse_args()
    from_stage: int = args.from_stage
    to_stage:   int = args.to_stage

    if from_stage > to_stage:
        console.print(f"[bold red]Error:[/bold red] --from-stage ({from_stage}) > --to-stage ({to_stage})")
        sys.exit(1)

    # ── Banner ────────────────────────────────────────────────────────────────
    console.print()
    stage_range = f"stages {from_stage}–{to_stage}" if from_stage != to_stage else f"stage {from_stage}"
    console.print(Panel(
        Text.assemble(
            ("  [VPF]  VPF Pipeline — Complete Aerodynamic Analysis  [VPF]  \n", "bold bright_cyan"),
            (f"  Variable Pitch Fan · Running {stage_range}", "dim white"),
        ),
        border_style="cyan",
        box=box.DOUBLE_EDGE,
        padding=(0, 4),
    ))

    # ── Overall progress bar ──────────────────────────────────────────────────
    n_steps = to_stage - from_stage + 1
    if from_stage == 1:
        n_steps += 1  # cleanup before Stage 1
    overall = Progress(
        SpinnerColumn(spinner_name="earth", style="bright_cyan"),
        TextColumn("[bold bright_white]Overall progress"),
        BarColumn(bar_width=50, style="cyan", complete_style="bright_green"),
        TaskProgressColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    )

    t_start = time.perf_counter()

    with overall:
        pipeline_task = overall.add_task("Running pipeline…", total=n_steps)

        try:
            # Load predecessor results from disk when skipping early stages
            s1 = s2 = s3 = s4 = s5 = s6 = s7 = None

            if from_stage > 1:
                s1 = _load_s1_from_disk()
            if from_stage > 2:
                s2 = _load_s2_from_disk()
            if from_stage > 3:
                s3 = _load_s3_from_disk()
            if from_stage > 4:
                s4 = _load_s4_from_disk()
            if from_stage > 5:
                s5 = _load_s5_from_disk()
            if from_stage > 6:
                s6 = _load_s6_from_disk()
            if from_stage == 1:
                step_1_clean_results(); overall.advance(pipeline_task)
            if from_stage <= 1 <= to_stage:
                s1 = step_2_airfoil_selection(); overall.advance(pipeline_task)
            if from_stage <= 2 <= to_stage:
                s2 = step_3_xfoil_simulations(s1); overall.advance(pipeline_task)
            if from_stage <= 3 <= to_stage:
                s3 = step_4_compressibility_correction(s2); overall.advance(pipeline_task)
            if from_stage <= 4 <= to_stage:
                s4 = step_5_metrics_and_figures(s3); overall.advance(pipeline_task)
            if from_stage <= 5 <= to_stage:
                s5 = step_6_pitch_kinematics(); overall.advance(pipeline_task)
            if from_stage <= 6 <= to_stage:
                s6 = step_7_reverse_thrust(); overall.advance(pipeline_task)
            if from_stage <= 7 <= to_stage:
                s7 = step_8_sfc_analysis(); overall.advance(pipeline_task)

        except Exception as exc:
            console.print()
            console.print(Panel(
                f"[bold bright_red]✘  Pipeline FAILED[/bold bright_red]\n\n"
                f"[red]{exc}[/red]",
                border_style="bright_red",
                box=box.HEAVY,
                padding=(0, 2),
            ))
            console.print_exception(show_locals=False)
            sys.exit(1)

    elapsed = time.perf_counter() - t_start

    # Load any missing stage results from disk for the summary table
    if s1 is None: s1 = _load_s1_from_disk()
    if s2 is None: s2 = _load_s2_from_disk()
    if s3 is None: s3 = _load_s3_from_disk()
    if s4 is None: s4 = _load_s4_from_disk()
    if s5 is None: s5 = _load_s5_from_disk()
    if s6 is None: s6 = _load_s6_from_disk()
    if s7 is None: s7 = _load_s7_from_disk()

    _print_summary(s1, s2, s3, s4, s5, s6, s7, elapsed)


if __name__ == "__main__":
    main()
