"""Stage 4 figures: aerodynamic efficiency and polar comparisons.

Reads corrected polars from Stage 3 (results/stage3_compressibility_correction/polars/)
and produces three essential figures per pipeline run:
  - polar_efficiency_{flight}_{section}.png  — Cl/Cd vs α with η_max annotation
  - lift_drag_curves_{flight}.png            — multi-section polar overlay
  - compressibility_comparison.png           — penalty overview across conditions
"""

from __future__ import annotations

import logging
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from vpf_analysis.config_loader import get_plot_settings
from vpf_analysis.postprocessing.aerodynamics_utils import (
    find_second_peak_row,
    resolve_efficiency_column,
    resolve_polar_file,
)
from vpf_analysis.shared.plot_style import (
    COLORS,
    FLIGHT_LABELS,
    SECTION_COLORS,
    SECTION_LABELS,
    apply_style,
)
from vpf_analysis.stage4_performance_metrics.metrics import AerodynamicMetrics

LOGGER = logging.getLogger(__name__)

_FLIGHT_ORDER = ["takeoff", "climb", "cruise", "descent"]

_ALPHA_MIN = -2.0
_ALPHA_MAX = 14.0


def _load_efficiency_curve(
    polars_dir: Path, condition: str, section: str
) -> tuple[np.ndarray, np.ndarray] | None:
    """Return (alpha, efficiency) arrays for a given case, or None if unavailable."""
    polar_file = resolve_polar_file(polars_dir, condition, section)
    if polar_file is None:
        return None
    try:
        df = pd.read_csv(polar_file)
        eff_col = resolve_efficiency_column(df)
        df_clean = (
            df[["alpha", eff_col]]
            .replace([np.inf, -np.inf], np.nan)
            .dropna()
            .sort_values("alpha")
        )
        mask = (df_clean["alpha"] >= _ALPHA_MIN) & (df_clean["alpha"] <= _ALPHA_MAX)
        df_clean = df_clean[mask]
        if df_clean.empty:
            return None
        return df_clean["alpha"].to_numpy(), df_clean[eff_col].to_numpy()
    except Exception:
        return None


def _lookup_eff_at_alpha(
    polars_dir: Path, condition: str, section: str, alpha_target: float
) -> float | None:
    """Return (CL/CD) at the nearest polar point to alpha_target."""
    result = _load_efficiency_curve(polars_dir, condition, section)
    if result is None:
        return None
    alphas, effs = result
    idx = int(np.argmin(np.abs(alphas - alpha_target)))
    return float(effs[idx])


def _smart_annotation(
    ax: plt.Axes,
    x: float,
    y: float,
    label: str,
    x_range: float,
    y_range: float,
) -> None:
    x_lo, x_hi = ax.get_xlim()
    y_lo, y_hi = ax.get_ylim()
    # Offset away from whichever edge the point is near (threshold: 65 % / 75 %)
    x_frac = (x - x_lo) / max(x_hi - x_lo, 1e-9)
    y_frac = (y - y_lo) / max(y_hi - y_lo, 1e-9)
    dx = 0.06 * x_range * (1.0 if x_frac <= 0.65 else -1.0)
    dy = 0.06 * y_range * (1.0 if y_frac <= 0.75 else -1.0)
    ax.annotate(
        label, xy=(x, y), xytext=(x + dx, y + dy),
        arrowprops=dict(arrowstyle="->", color="#B22222", lw=1.2),
        fontsize=9, fontweight="bold", color="#B22222", zorder=7,
    )


def _load_corrected_polar(
    stage3_dir: Path,
    condition: str,
    section: str,
) -> pd.DataFrame | None:
    path = stage3_dir / condition.lower() / section / "corrected_polar.csv"
    if not path.exists():
        LOGGER.warning("Corrected polar not found: %s", path)
        return None
    return pd.read_csv(path)


def plot_efficiency_penalty_overview(
    metrics: list[AerodynamicMetrics],
    polars_dir: Path,
    output_path: Path,
    summary_section: str = "mid_span",
) -> None:
    """CL/CD vs α for all flight conditions with VPF vs fixed-pitch operating points.

    Saved as ``compressibility_comparison.png``.
    """
    alpha_design: float | None = None
    for m in metrics:
        if m.flight_condition == "cruise" and m.blade_section == summary_section:
            alpha_design = m.alpha_design if m.alpha_design == m.alpha_design else m.alpha_opt
            break

    flights = [f for f in _FLIGHT_ORDER if any(
        m.flight_condition == f and m.blade_section == summary_section for m in metrics
    )]
    metrics_map: dict[str, AerodynamicMetrics] = {
        m.flight_condition: m
        for m in metrics if m.blade_section == summary_section
    }

    ann_rows: list[tuple[str, float, float, float, float]] = []  # (flight, alpha_opt, alpha_fixed, eff_opt, eff_fixed)

    with apply_style():
        fig, ax = plt.subplots(figsize=(8.0, 5.5))

        for flight in flights:
            curve = _load_efficiency_curve(polars_dir, flight, summary_section)
            if curve is None:
                continue
            alphas, effs = curve
            color = COLORS.get(flight, "#BBBBBB")
            label = FLIGHT_LABELS.get(flight, flight)
            ax.plot(alphas, effs, color=color, label=label)

            m = metrics_map.get(flight)
            if m is None:
                continue

            ax.plot(m.alpha_opt, m.max_efficiency, marker="o", markersize=8,
                    color=color, zorder=5)

            if alpha_design is not None and flight != "cruise":
                eff_fixed = _lookup_eff_at_alpha(
                    polars_dir, flight, summary_section, alpha_design
                )
                if eff_fixed is not None:
                    ax.plot(
                        alpha_design, eff_fixed,
                        marker="o", markersize=8, color=color,
                        markerfacecolor="white", markeredgewidth=1.5, zorder=5,
                    )
                    ann_rows.append((
                        flight,
                        m.alpha_opt, alpha_design,
                        m.max_efficiency, eff_fixed,
                    ))

        if alpha_design is not None:
            ax.axvline(
                alpha_design, color="#AAAAAA", linestyle="--", linewidth=1.2,
                label=f"$\\alpha_{{design}}$ = {alpha_design:.1f}°",
            )

        ax.set_xlim(right=12.0)
        section_label = SECTION_LABELS.get(summary_section, summary_section)
        ax.set_xlabel(r"$\alpha$ [°]")
        ax.set_ylabel(r"$C_L/C_D$")
        ax.set_title(f"Fixed-pitch penalty — Section {section_label}")
        ax.legend(
            title="Condition",
            bbox_to_anchor=(1.02, 1),
            loc="upper left",
            borderaxespad=0,
        )
        fig.tight_layout()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, bbox_inches="tight")
        plt.close(fig)

    # ── CSV with VPF vs fixed-pitch penalty data (for LaTeX table) ───────────
    if ann_rows:
        tables_dir = output_path.parent.parent / "tables"
        tables_dir.mkdir(parents=True, exist_ok=True)
        rows = [
            {
                "condition":        f,
                "alpha_opt_deg":    ao,
                "alpha_fixed_deg":  af,
                "clcd_opt":         eo,
                "clcd_fixed":       ef,
                "delta_alpha_deg":  ao - af,
                "delta_clcd":       eo - ef,
            }
            for f, ao, af, eo, ef in ann_rows
        ]
        pd.DataFrame(rows).to_csv(
            tables_dir / "fixed_pitch_penalty.csv", index=False, float_format="%.2f"
        )


def generate_efficiency_plots(
    polars_dir: Path,
    figures_dir: Path,
    flight_conditions: list[str],
    blade_sections: list[str],
) -> None:
    """Generate CL/CD vs α curves for each (condition, section) pair.

    Saved as ``polar_efficiency_{flight}_{section}.png``.
    """
    figures_dir.mkdir(parents=True, exist_ok=True)
    settings = get_plot_settings()
    w = settings["figure_size"]["width"]
    h = settings["figure_size"]["height"]

    for flight in flight_conditions:
        for section in blade_sections:
            polar_file = resolve_polar_file(polars_dir, flight, section)
            if polar_file is None:
                continue

            df = pd.read_csv(polar_file)
            try:
                eff_col = resolve_efficiency_column(df)
            except (ValueError, KeyError):
                continue

            try:
                row_opt = find_second_peak_row(df, eff_col)
                alpha_opt = float(row_opt["alpha"])
                ld_max = float(row_opt[eff_col])
                has_opt = True
            except (ValueError, KeyError):
                has_opt = False
                alpha_opt = float("nan")
                ld_max = float("nan")

            # Clean inf/nan so the plotted curve matches what find_second_peak_row sees
            df_plot = (
                df[["alpha", eff_col]]
                .replace([np.inf, -np.inf], np.nan)
                .dropna()
                .sort_values("alpha")
            )
            df_plot = df_plot[
                (df_plot["alpha"] >= _ALPHA_MIN) & (df_plot["alpha"] <= _ALPHA_MAX)
            ]

            fig, ax = plt.subplots(figsize=(w, h))
            color = SECTION_COLORS.get(section, "#2166AC")
            ax.plot(df_plot["alpha"], df_plot[eff_col], color=color, label=r"$C_L/C_D$", zorder=3)

            if has_opt:
                ax.plot(
                    alpha_opt, ld_max,
                    marker="*", color="#B22222", markersize=12,
                    markeredgecolor="darkred", markeredgewidth=0.8,
                    zorder=6, linestyle="none",
                )
                ax.axvline(alpha_opt, color="#B22222", linestyle="--",
                           linewidth=0.9, alpha=0.75, zorder=4)
                alpha_range = float(
                    df_plot["alpha"].max() - df_plot["alpha"].min()
                ) if not df_plot.empty else 1.0
                ld_range = float(
                    df_plot[eff_col].max() - df_plot[eff_col].min()
                ) if not df_plot.empty else 1.0
                _smart_annotation(
                    ax, alpha_opt, ld_max,
                    rf"$\alpha_{{opt}}$ = {alpha_opt:.1f}°",
                    alpha_range, ld_range,
                )

            ax.set_xlabel(r"Angle of attack $\alpha$ [°]")
            ax.set_ylabel(r"Lift-to-drag ratio $C_L/C_D$")
            section_label = section.replace("_", " ").title()
            ax.set_title(f"Aerodynamic efficiency — {flight.capitalize()} / {section_label}")
            ax.legend(loc="lower right")
            fig.tight_layout()
            fig.savefig(figures_dir / f"polar_efficiency_{flight}_{section}.png")
            plt.close(fig)


def generate_section_polar_comparison(
    stage3_dir: Path,
    figures_dir: Path,
    flight_conditions: list[str],
    blade_sections: list[str] | None = None,
) -> None:
    """Two-panel figure per condition: CL/CD and CL vs α for all sections.

    Saved as ``lift_drag_curves_{flight}.png``.
    """
    figures_dir.mkdir(parents=True, exist_ok=True)
    settings = get_plot_settings()
    w = settings["figure_size"]["width"]
    h = settings["figure_size"]["height"]
    sections = blade_sections or ["root", "mid_span", "tip"]

    for flight in flight_conditions:
        fig, (ax_eff, ax_cl) = plt.subplots(1, 2, figsize=(w * 2 + 0.5, h))
        any_plotted = False

        for section in sections:
            df = _load_corrected_polar(stage3_dir, flight, section)
            if df is None:
                continue

            try:
                eff_col = resolve_efficiency_column(df)
            except (ValueError, KeyError):
                LOGGER.warning(
                    "No efficiency column in %s/%s corrected polar.", flight, section
                )
                continue

            cl_col = "cl_corrected" if "cl_corrected" in df.columns else "cl"
            color = SECTION_COLORS.get(section, "#333333")
            section_label = section.replace("_", " ").title()

            try:
                row_opt = find_second_peak_row(df, eff_col)
                alpha_opt = float(row_opt["alpha"])
                ld_opt = float(row_opt[eff_col])
                cl_at_opt = float(row_opt[cl_col]) if cl_col in row_opt.index else None
                has_opt = True
            except (ValueError, KeyError):
                has_opt = False
                alpha_opt = ld_opt = cl_at_opt = None

            legend_lbl = (
                rf"{section_label} ($\alpha_{{opt}}$ = {alpha_opt:.1f}°)"
                if has_opt else section_label
            )

            # Clean efficiency data so the plotted curve matches find_second_peak_row
            df_eff_plot = (
                df[["alpha", eff_col]]
                .replace([np.inf, -np.inf], np.nan)
                .dropna()
                .sort_values("alpha")
            )
            ax_eff.plot(df_eff_plot["alpha"], df_eff_plot[eff_col], color=color, label=legend_lbl, zorder=3)
            if has_opt:
                ax_eff.plot(
                    alpha_opt, ld_opt, marker="*", color=color, markersize=11,
                    markeredgecolor="white", markeredgewidth=0.7, zorder=6, linestyle="none",
                )
                ax_eff.axvline(alpha_opt, color=color, linestyle=":", linewidth=0.8, alpha=0.5)

            ax_cl.plot(df["alpha"], df[cl_col], color=color, label=legend_lbl, zorder=3)
            if has_opt and cl_at_opt is not None:
                ax_cl.plot(
                    alpha_opt, cl_at_opt, marker="*", color=color, markersize=11,
                    markeredgecolor="white", markeredgewidth=0.7, zorder=6, linestyle="none",
                )

            any_plotted = True

        if not any_plotted:
            plt.close(fig)
            continue

        ax_eff.set_xlabel(r"Angle of attack $\alpha$ [°]")
        ax_eff.set_ylabel(r"$C_L/C_D$ (Kármán-Tsien corrected)")
        ax_eff.set_title(f"Efficiency polar — {flight.capitalize()}")
        ax_eff.legend(loc="lower right")

        ax_cl.set_xlabel(r"Angle of attack $\alpha$ [°]")
        ax_cl.set_ylabel(r"$C_L$ (Kármán-Tsien corrected)")
        ax_cl.set_title(f"Lift polar — {flight.capitalize()}")
        ax_cl.legend(loc="lower right")

        fig.suptitle(
            f"Blade section comparison — {flight.capitalize()}", fontsize=11, fontweight="bold"
        )
        fig.tight_layout()
        fig.savefig(figures_dir / f"lift_drag_curves_{flight}.png")
        plt.close(fig)



def generate_all_stage4_figures(
    metrics: list[AerodynamicMetrics],
    figures_dir: Path,
    polars_dir: Path | None = None,
    flight_conditions: list[str] | None = None,
    blade_sections: list[str] | None = None,
    stage3_dir: Path | None = None,
    **_kwargs,
) -> None:
    """Generate the essential Stage 4 figures.

    1. compressibility_comparison.png — fixed-pitch penalty overview (mid_span section)
    2. polar_efficiency_{flight}_{section}.png — CL/CD vs α per condition and section
    3. lift_drag_curves_{flight}.png — two-panel CL/CD + CL vs α, all sections per condition
    """
    figures_dir.mkdir(parents=True, exist_ok=True)

    if polars_dir is not None:
        plot_efficiency_penalty_overview(
            metrics, polars_dir,
            output_path=figures_dir / "compressibility_comparison.png",
        )

    if polars_dir is not None and flight_conditions and blade_sections:
        generate_efficiency_plots(polars_dir, figures_dir, flight_conditions, blade_sections)

    if stage3_dir is not None and stage3_dir.is_dir() and flight_conditions:
        generate_section_polar_comparison(
            stage3_dir, figures_dir, flight_conditions, blade_sections
        )
