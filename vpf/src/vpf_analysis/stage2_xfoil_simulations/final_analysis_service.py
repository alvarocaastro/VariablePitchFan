from __future__ import annotations

import logging
import shutil
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from vpf_analysis.adapters.xfoil.xfoil_parser import parse_polar_file
from vpf_analysis.core.domain.airfoil import Airfoil
from vpf_analysis.core.domain.blade_section import BladeSection
from vpf_analysis.core.domain.simulation_condition import SimulationCondition
from vpf_analysis.ports.xfoil_runner_port import XfoilRunnerPort
from vpf_analysis.shared.plot_style import apply_style

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class FinalSimulationConfig:
    """Configuration for a single (flight condition, blade section) simulation."""

    flight_name: str
    section: BladeSection
    condition: SimulationCondition


class FinalAnalysisService:
    """
    Run final XFOIL simulations for the selected airfoil only.

    Results are organised under:

        results/simulation_plots/<flight>/<section>/

    with:
        - polar.dat
        - cl_alpha.csv
        - cd_alpha.csv
        - polar_plot.png
    """

    def __init__(self, xfoil_runner: XfoilRunnerPort, base_results_dir: Path) -> None:
        self._xfoil = xfoil_runner
        self._base = base_results_dir / "simulation_plots"
        self._base_results_dir = base_results_dir

    def run(
        self,
        airfoil: Airfoil,
        configs: Iterable[FinalSimulationConfig],
        progress_callback: Callable[[str, str, float, int], None] | None = None,
        flight_conditions: list[str] | None = None,
        blade_sections: list[str] | None = None,
    ) -> tuple[dict[tuple[str, str], float], dict[tuple[str, str], tuple[float, float]]]:
        """
        Execute all final simulations.

        Parameters
        ----------
        airfoil : Airfoil
            Airfoil geometry to simulate.
        configs : Iterable[FinalSimulationConfig]
            One entry per (flight_condition, blade_section) combination.
        progress_callback : callable(flight_name, section_name, conv_rate, conv_failures) | None
            If provided, called after each config completes with the XFOIL
            convergence rate (0–1) and number of failed alpha points.
            Useful for updating a live progress bar in the calling script.

        Returns
        -------
        alpha_eff_map : (flight, section) -> alpha_opt
        stall_map     : (flight, section) -> (alpha_stall, cl_max)
        """
        alpha_eff_map: dict[tuple[str, str], float] = {}
        stall_map: dict[tuple[str, str], tuple[float, float]] = {}
        self._total_convergence_warnings = 0

        for cfg in configs:
            flight_dir = cfg.flight_name.lower()
            out_dir = self._base / flight_dir / cfg.section.name
            out_dir.mkdir(parents=True, exist_ok=True)

            polar_path = out_dir / "polar.dat"
            xfoil_result = self._xfoil.run_polar(airfoil.dat_path, cfg.condition, polar_path)
            if xfoil_result.convergence_failures > 0:
                self._total_convergence_warnings += 1

            conv_rate     = xfoil_result.convergence_rate
            conv_failures = xfoil_result.convergence_failures

            df = self._build_polar_df(polar_path, airfoil, cfg)
            if df.empty:
                if progress_callback is not None:
                    progress_callback(cfg.flight_name, cfg.section.name, conv_rate, conv_failures)
                continue

            self._export_csv(df, out_dir)
            alpha_eff, alpha_stall, cl_max = self._plot_all(df, out_dir, airfoil, cfg)
            alpha_eff_map[(cfg.flight_name, cfg.section.name)] = alpha_eff
            stall_map[(cfg.flight_name, cfg.section.name)] = (alpha_stall, cl_max)

            if progress_callback is not None:
                progress_callback(cfg.flight_name, cfg.section.name, conv_rate, conv_failures)

        if flight_conditions is not None and blade_sections is not None:
            polars_dir = self._base_results_dir / "polars"
            polars_dir.mkdir(parents=True, exist_ok=True)
            for flight in flight_conditions:
                for section in blade_sections:
                    source_file = self._base / flight.lower() / section / "polar.csv"
                    if source_file.exists():
                        shutil.copy2(source_file, polars_dir / f"{flight}_{section}.csv")

        return alpha_eff_map, stall_map

    @staticmethod
    def _build_polar_df(
        polar_path: Path,
        airfoil: Airfoil,
        cfg: FinalSimulationConfig,
    ) -> pd.DataFrame:
        """Parse XFOIL output and attach flight/section metadata columns."""
        df = parse_polar_file(polar_path)
        if df.empty:
            return df
        df.insert(0, "airfoil", airfoil.name)
        df.insert(1, "flight", cfg.flight_name)
        df.insert(2, "section", cfg.section.name)
        df.insert(3, "mach", cfg.condition.mach_rel)
        df.insert(4, "re", cfg.condition.reynolds)
        df.insert(5, "ncrit", cfg.condition.ncrit)
        return df

    @staticmethod
    def _export_csv(df: pd.DataFrame, out_dir: Path) -> None:
        cols = ["alpha", "cl", "cd", "cm", "ld", "re", "ncrit"]
        df[cols].to_csv(out_dir / "polar.csv", index=False, float_format="%.6f")

    @staticmethod
    def _plot_all(
        df: pd.DataFrame,
        out_dir: Path,
        airfoil: Airfoil,
        cfg: FinalSimulationConfig,
    ) -> tuple[float, float, float]:
        """Generate all polar plots and return (alpha_opt, alpha_stall, cl_max).

        The optimal angle is defined as the second CL/CD peak (alpha >= ALPHA_MIN_OPT)
        to avoid the laminar-separation-bubble artefact at very low angles.
        """
        from vpf_analysis.settings import get_settings
        alpha_min_opt = get_settings().physics.ALPHA_MIN_OPT_DEG

        from vpf_analysis.config.domain import PhysicsConstants
        _ph = PhysicsConstants()

        df_eff = df.replace([float("inf"), float("-inf")], pd.NA).dropna(subset=["ld"])
        if df_eff.empty:
            alpha_eff = float("nan")
        else:
            # First try: alpha >= ALPHA_MIN_OPT AND CL >= CL_MIN_3D to exclude laminar bubble.
            # The CL filter is critical for cruise conditions where XFOIL may only converge
            # at low alpha, causing the fallback to erroneously select the laminar-bubble peak.
            df_second_peak = df_eff[
                (df_eff["alpha"] >= alpha_min_opt) & (df_eff["cl"] >= _ph.CL_MIN_3D)
            ]
            # Second try: relax alpha constraint but keep CL filter
            if df_second_peak.empty:
                df_second_peak = df_eff[df_eff["cl"] >= _ph.CL_MIN_3D]
            # If still empty, return NaN — do not fabricate an operating point
            if df_second_peak.empty:
                LOGGER.warning(
                    "No valid second peak (CL >= %.2f) for %s/%s — alpha_opt=NaN.",
                    _ph.CL_MIN_3D, cfg.flight_name, cfg.section.name,
                )
                alpha_eff = float("nan")
            else:
                idx_max = df_second_peak["ld"].idxmax()
                alpha_eff = float(df_second_peak.loc[idx_max, "alpha"])

        # Stall detection: CL peak (only for alpha > 0 to avoid pre-stall artefacts)
        df_pos = df[df["alpha"] > 0.0].copy()
        if not df_pos.empty:
            idx_stall = df_pos["cl"].idxmax()
            alpha_stall = float(df_pos.loc[idx_stall, "alpha"])
            cl_stall    = float(df_pos.loc[idx_stall, "cl"])
        else:
            alpha_stall = float("nan")
            cl_stall    = float("nan")

        with apply_style():
            # 1) CL/CD vs alpha (eficiencia)
            fig_eff, ax_eff = plt.subplots(figsize=(5.5, 4.2))
            ax_eff.plot(df["alpha"], df["ld"], color="#4477AA", label=r"$C_L/C_D$")
            if not pd.isna(alpha_eff):
                ld_eff = float(df_second_peak.loc[idx_max, "ld"])
                ax_eff.scatter(alpha_eff, ld_eff, color="#EE6677", s=80, zorder=5,
                               edgecolors="white", linewidths=1.2,
                               label=rf"$\alpha_{{opt}}$ = {alpha_eff:.2f}°")
                ax_eff.axvline(alpha_eff, color="#EE6677", linestyle="--",
                               linewidth=1.4, alpha=0.8, zorder=4)

            ax_eff.set_xlabel(r"$\alpha$ [°]")
            ax_eff.set_ylabel(r"$C_L/C_D$")
            ax_eff.set_title(
                f"XFOIL 2D — Aerodynamic efficiency — {cfg.flight_name.capitalize()} / {cfg.section.name.replace('_', ' ')}"
            )
            ax_eff.legend(loc="lower right")
            fig_eff.tight_layout()
            fig_eff.savefig(out_dir / "efficiency_plot.png")
            plt.close(fig_eff)

            # 2) CL vs alpha with stall onset marker
            fig_cl, ax_cl = plt.subplots(figsize=(5.5, 4.2))
            ax_cl.plot(df["alpha"], df["cl"], color="#4477AA", label=r"$C_L$")

            if not pd.isna(alpha_stall):
                # Marker at CL_max (stall onset)
                ax_cl.scatter(alpha_stall, cl_stall, color="#EE6677", s=90, zorder=5,
                              edgecolors="white", linewidths=1.2,
                              label=rf"Stall onset: $\alpha_{{stall}}$ = {alpha_stall:.1f}°,  $C_{{L,max}}$ = {cl_stall:.3f}")
                ax_cl.axvline(alpha_stall, color="#EE6677", linestyle="--",
                              linewidth=1.4, alpha=0.8, zorder=4)
                # Horizontal reference at CL_max
                ax_cl.axhline(cl_stall, color="#EE6677", linestyle=":",
                              linewidth=1.0, alpha=0.6, zorder=3)
                # Annotation inside the plot
                ax_cl.annotate(
                    rf"$C_{{L,max}}$ = {cl_stall:.3f}",
                    xy=(alpha_stall, cl_stall),
                    xytext=(-45, 10), textcoords="offset points",
                    fontsize=8, color="#EE6677",
                    arrowprops=dict(arrowstyle="->", color="#EE6677", lw=1.0),
                )

            ax_cl.set_xlabel(r"$\alpha$ [°]")
            ax_cl.set_ylabel(r"$C_L$")
            ax_cl.set_title(
                f"XFOIL 2D — $C_L$ vs $\\alpha$ — {cfg.flight_name.capitalize()} / {cfg.section.name.replace('_', ' ').title()}"
            )
            ax_cl.legend(
                bbox_to_anchor=(0.5, -0.22), loc="upper center",
                borderaxespad=0, ncol=1,
            )
            fig_cl.tight_layout()
            fig_cl.savefig(out_dir / "cl_alpha_stall.png")
            plt.close(fig_cl)

            # 3) CL–CD polar
            fig_pol, ax_pol = plt.subplots(figsize=(5.5, 4.2))
            ax_pol.plot(df["cd"], df["cl"], color="#4477AA", linewidth=1.8)
            ax_pol.set_xlabel(r"$C_D$")
            ax_pol.set_ylabel(r"$C_L$")
            ax_pol.set_title(
                f"XFOIL 2D — $C_L$–$C_D$ polar — {cfg.flight_name.capitalize()} / {cfg.section.name.replace('_', ' ').title()}"
            )
            fig_pol.tight_layout()
            fig_pol.savefig(out_dir / "polar_plot.png")
            plt.close(fig_pol)

        return alpha_eff, alpha_stall, cl_stall


