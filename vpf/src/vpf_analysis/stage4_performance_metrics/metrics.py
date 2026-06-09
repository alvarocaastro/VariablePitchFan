"""Stage 4 metrics: aerodynamic performance from corrected polars.

Reads Stage 3 corrected polars, computes η_max (Cl/Cd), α_opt, Cl_max,
and Cl at fixed-pitch α_design for each flight condition × blade section.
Results are aggregated into summary_table.csv consumed by Stage 7 (SFC analysis).
"""

from __future__ import annotations

import dataclasses
import math
import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from vpf_analysis.postprocessing.aerodynamics_utils import (
    compute_stall_alpha,
    find_second_peak_row,
    lookup_efficiency_at_alpha,
    resolve_efficiency_column,
    resolve_polar_file,
)

LOGGER = logging.getLogger(__name__)

# Minimum CL for viable fan blade operation.
from vpf_analysis.settings import get_settings
CL_MIN_VIABLE: float = get_settings().physics.CL_MIN_VIABLE


@dataclass(frozen=True)
class AerodynamicMetrics:
    """Aerodynamic performance metrics for a single case."""

    flight_condition: str
    blade_section: str
    reynolds: float
    ncrit: float
    max_efficiency: float  # (CL/CD)_max
    alpha_opt: float  # Angle of attack at maximum efficiency
    cl_max: float  # Maximum lift coefficient
    cl_at_opt: float  # Lift coefficient at optimal angle
    cd_at_opt: float  # Drag coefficient at optimal angle
    stall_margin: float  # alpha_stall - alpha_opt (deg); safety margin before stall
    cm_at_opt: float  # Pitching-moment coefficient at the optimal angle
    # --- Design-reference fields (filled by enrich_with_cruise_reference) ---
    alpha_design: float = float("nan")   # alpha_opt at cruise for this section (fixed-blade angle)
    delta_alpha: float = float("nan")    # alpha_opt - alpha_design (VPF adjustment required)
    eff_at_design_alpha: float = float("nan")  # (CL/CD) at alpha_design (fixed-pitch performance)
    eff_gain: float = float("nan")       # max_efficiency - eff_at_design_alpha (absolute VPF gain)
    eff_gain_pct: float = float("nan")   # eff_gain / eff_at_design_alpha * 100 (%)


def _first_available(df: pd.DataFrame, candidates: tuple[str, ...]) -> str:
    """Return the first column name from *candidates* that exists in *df*.

    Raises ``KeyError`` if none of the candidates is present.
    """
    for col in candidates:
        if col in df.columns:
            return col
    raise KeyError(
        f"None of the expected columns {list(candidates)} found in DataFrame. "
        f"Available: {list(df.columns)}"
    )


def compute_metrics_from_polar(
    df: pd.DataFrame,
    flight_condition: str,
    blade_section: str,
    reynolds: float,
    ncrit: float,
    alpha_min: float | None = None,
) -> AerodynamicMetrics:
    """
    Compute aerodynamic metrics from polar data.

    The operating point is defined as the second CL/CD peak (alpha >= alpha_min),
    which avoids the laminar-separation-bubble artefact at very low angles
    produced by XFOIL for NACA 6-series profiles.

    Column priority (highest to lowest):

    - Efficiency : ``ld_corrected`` → ``ld_kt`` → ``ld`` → ``CL_CD``
    - Lift       : ``cl_corrected`` → ``cl_kt`` → ``cl``
    - Drag       : ``cd_corrected`` → ``cd``
    - Moment     : ``cm`` (optional; NaN when absent)

    Parameters
    ----------
    df:
        Polar DataFrame. Must contain ``alpha``, a lift column, a drag column,
        and at least one efficiency column.
    flight_condition:
        Flight condition identifier (e.g. ``"cruise"``).
    blade_section:
        Blade section identifier (e.g. ``"tip"``).
    reynolds:
        Reynolds number for this case.
    ncrit:
        Ncrit (transition criterion) for this case.

    Returns
    -------
    AerodynamicMetrics
        Computed metrics including stall margin and pitching moment.
    """
    if alpha_min is None:
        alpha_min = get_settings().physics.ALPHA_MIN_OPT_DEG

    eff_col = resolve_efficiency_column(df)

    # Prefer corrected/KT columns when available (Stage 3 output).
    cl_col = _first_available(df, ("cl_corrected", "cl_kt", "cl"))
    cd_col = _first_available(df, ("cd_corrected", "cd"))
    cm_col: str | None = "cm" if "cm" in df.columns else None

    # Apply minimum-CL constraint before finding the efficiency peak.
    # This replaces the old alpha_min=3° heuristic: instead of filtering by angle
    # (which excluded the true aerodynamic optimum in high-Mach corrected polars),
    # we filter by minimum viable lift coefficient. Points with CL < CL_MIN_VIABLE
    # cannot generate sufficient thrust regardless of their CL/CD ratio.
    df_viable = df[df[cl_col] >= CL_MIN_VIABLE]
    if df_viable.empty:
        LOGGER.warning(
            "No data with %s >= %.2f for %s/%s. Using full polar.",
            cl_col, CL_MIN_VIABLE, flight_condition, blade_section,
        )
        df_viable = df

    row_opt = find_second_peak_row(df_viable, eff_col, alpha_min=alpha_min)

    # Maximum lift over the entire cleaned range (not just second peak)
    df_clean = df[[cl_col]].replace(float("inf"), float("nan")).replace(float("-inf"), float("nan"))
    cl_max = float(df_clean[cl_col].max())

    # Stall margin: alpha_stall - alpha_opt
    alpha_stall = compute_stall_alpha(df, cl_col)
    stall_margin = alpha_stall - float(row_opt["alpha"])

    # Pitching moment at optimal angle (NaN if not available)
    cm_at_opt = float(row_opt[cm_col]) if cm_col is not None else float("nan")

    return AerodynamicMetrics(
        flight_condition=flight_condition,
        blade_section=blade_section,
        reynolds=reynolds,
        ncrit=ncrit,
        max_efficiency=float(row_opt[eff_col]),
        alpha_opt=float(row_opt["alpha"]),
        cl_max=cl_max,
        cl_at_opt=float(row_opt[cl_col]),
        cd_at_opt=float(row_opt[cd_col]),
        stall_margin=stall_margin,
        cm_at_opt=cm_at_opt,
    )


def compute_all_metrics(
    polars_dir: Path,
    flight_conditions: list[str],
    blade_sections: list[str],
    reynolds_table: dict[str, dict[str, float]],
    ncrit_table: dict[str, float],
    design_condition: str = "cruise",
) -> list[AerodynamicMetrics]:
    """Compute metrics for all (flight, section) polar files in polars_dir."""
    all_metrics: list[AerodynamicMetrics] = []

    for flight in flight_conditions:
        for section in blade_sections:
            polar_file = resolve_polar_file(polars_dir, flight, section)
            if polar_file is None:
                continue

            try:
                df = pd.read_csv(polar_file)
                reynolds = reynolds_table[flight][section]
                ncrit = ncrit_table[flight]
                _cfg = get_settings()
                _default_alpha_min = _cfg.physics.ALPHA_MIN_OPT_DEG
                if flight == design_condition:
                    alpha_min = _cfg.cruise_alpha_min.get(section, _default_alpha_min)
                else:
                    alpha_min = _default_alpha_min
                metrics = compute_metrics_from_polar(
                    df, flight, section, reynolds, ncrit, alpha_min=alpha_min
                )
                all_metrics.append(metrics)
            except Exception as exc:
                LOGGER.warning("Could not compute metrics for %s/%s: %s", flight, section, exc)

    return all_metrics


def enrich_with_cruise_reference(
    metrics: list[AerodynamicMetrics],
    polars_dir: Path,
    design_condition: str = "cruise",
    axial_velocities: dict[str, float] | None = None,
    blade_radii: dict[str, float] | None = None,
    fan_omega: dict[str, float] | None = None,
    gear_ratio: float = 1.0,
) -> list[AerodynamicMetrics]:
    """Enrich metrics with design-reference fields relative to the cruise condition.

    Computes the **physically correct** fixed-pitch incidence for each off-design
    condition using velocity triangles:

        φ(cond, sec)   = arctan(Va_cond / U_sec)        [inflow angle]
        β_cruise(sec)  = α_opt_cruise(sec) + φ_cruise(sec)   [fixed blade angle]
        α_fixed(cond)  = β_cruise(sec) − φ(cond, sec)   [actual incidence w/o VPF]

    Without VPF, the blade stays at β_cruise regardless of flight condition.  At
    takeoff Va increases → φ increases → α_fixed becomes negative (blade under-
    loaded).  At descent Va decreases → φ decreases → α_fixed increases (risk of
    stall).  VPF adjusts β to keep α at its optimum for every condition.

    Fields written to each AerodynamicMetrics:

    - ``alpha_design``       : actual fixed-pitch incidence α_fixed for this case
                               (equals α_opt_cruise only at the design condition)
    - ``delta_alpha``        : α_opt − α_fixed (total VPF pitch benefit)
    - ``eff_at_design_alpha``: (CL/CD) at α_fixed in the condition's polar
    - ``eff_gain``           : max_efficiency − eff_at_design_alpha
    - ``eff_gain_pct``       : eff_gain / eff_at_design_alpha × 100

    If velocity-triangle data is not provided the function falls back to the
    simplified model (α_fixed = α_opt_cruise), which underestimates VPF gains.

    Parameters
    ----------
    metrics:
        List produced by ``compute_all_metrics``.
    polars_dir:
        Directory used to locate polar files.
    design_condition:
        Flight condition that defines the reference blade angle (default: ``"cruise"``).
    axial_velocities:
        Va [m/s] per flight condition, e.g. ``{"cruise": 150.0, "takeoff": 180.0}``.
    blade_radii:
        Blade radius [m] per section, e.g. ``{"root": 0.53, "mid_span": 1.00}``.
    fan_omega:
        Fan angular velocity [rad/s] per flight condition.

    Returns
    -------
    List[AerodynamicMetrics]
        New list with design-reference fields filled in.
    """
    # ------------------------------------------------------------------
    # Step 0: pre-compute inflow angles φ if kinematics data is available
    # ------------------------------------------------------------------
    use_triangles = (
        axial_velocities is not None
        and blade_radii is not None
        and fan_omega is not None
    )
    phi: dict[tuple[str, str], float] = {}   # (condition, section) → φ [deg]
    if use_triangles:
        _omega_fallback = next(iter(fan_omega.values())) if fan_omega else 0.0
        for cond, va in axial_velocities.items():
            omega = fan_omega.get(cond, _omega_fallback) / gear_ratio
            for sec, r in blade_radii.items():
                u = omega * r
                phi[(cond, sec)] = math.degrees(math.atan2(va, u))
        LOGGER.info("Velocity-triangle enrichment active (omega per condition)")
    else:
        LOGGER.warning(
            "Velocity-triangle data not provided — falling back to simplified "
            "model (α_fixed = α_opt_cruise). VPF gains will be underestimated."
        )

    # ------------------------------------------------------------------
    # Step 1: extract α_opt at the design condition per section
    # ------------------------------------------------------------------
    alpha_opt_design_map: dict[str, float] = {
        m.blade_section: m.alpha_opt
        for m in metrics
        if m.flight_condition == design_condition
    }

    if not alpha_opt_design_map:
        LOGGER.warning(
            "No metrics found for design condition '%s'. "
            "Design-reference fields will remain NaN.",
            design_condition,
        )
        return metrics

    # ------------------------------------------------------------------
    # Step 2: compute β_cruise per section (fixed blade angle)
    # β_cruise = α_opt_cruise + φ_cruise
    # ------------------------------------------------------------------
    beta_cruise: dict[str, float] = {}
    for section, alpha_opt_cruise in alpha_opt_design_map.items():
        if use_triangles:
            phi_cruise = phi.get((design_condition, section), float("nan"))
            if not math.isnan(phi_cruise):
                beta_cruise[section] = alpha_opt_cruise + phi_cruise
            else:
                beta_cruise[section] = float("nan")
                LOGGER.warning("φ_cruise missing for section %s — β_cruise set to NaN", section)
        else:
            beta_cruise[section] = float("nan")

    # ------------------------------------------------------------------
    # Step 3: enrich each case
    # ------------------------------------------------------------------
    enriched: list[AerodynamicMetrics] = []
    for m in metrics:
        alpha_opt_cruise = alpha_opt_design_map.get(m.blade_section, float("nan"))

        if m.flight_condition == design_condition:
            # At the design condition the blade is perfectly aligned → no gain
            enriched.append(dataclasses.replace(
                m,
                alpha_design=alpha_opt_cruise,
                delta_alpha=0.0,
                eff_at_design_alpha=m.max_efficiency,
                eff_gain=0.0,
                eff_gain_pct=0.0,
            ))
            continue

        # Compute α_fixed: actual incidence without VPF
        if use_triangles:
            bc = beta_cruise.get(m.blade_section, float("nan"))
            phi_cond = phi.get((m.flight_condition, m.blade_section), float("nan"))
            if not math.isnan(bc) and not math.isnan(phi_cond):
                alpha_fixed = bc - phi_cond
            else:
                # Fallback per section
                alpha_fixed = alpha_opt_cruise
        else:
            alpha_fixed = alpha_opt_cruise

        delta_alpha = m.alpha_opt - alpha_fixed

        # Evaluate (CL/CD) at α_fixed in the condition's corrected polar
        polar_file = resolve_polar_file(polars_dir, m.flight_condition, m.blade_section)
        eff_at_fixed = float("nan")
        if polar_file is not None:
            try:
                df = pd.read_csv(polar_file)
                eff_col = resolve_efficiency_column(df)
                eff_at_fixed = lookup_efficiency_at_alpha(df, eff_col, alpha_fixed)
            except Exception as exc:
                LOGGER.warning(
                    "Could not evaluate efficiency at α_fixed=%.2f° for %s/%s: %s",
                    alpha_fixed, m.flight_condition, m.blade_section, exc,
                )

        eff_gain = (
            m.max_efficiency - eff_at_fixed
            if not math.isnan(eff_at_fixed)
            else float("nan")
        )
        eff_gain_pct = (
            eff_gain / abs(eff_at_fixed) * 100
            if not math.isnan(eff_gain) and eff_at_fixed != 0
            else float("nan")
        )

        LOGGER.debug(
            "%s/%s: β_cruise=%.2f° φ=%.2f° α_fixed=%.2f° α_opt=%.2f° "
            "Δα=%.2f° CL/CD_fixed=%.1f CL/CD_vpf=%.1f gain=%.1f%%",
            m.flight_condition, m.blade_section,
            beta_cruise.get(m.blade_section, float("nan")),
            phi.get((m.flight_condition, m.blade_section), float("nan")),
            alpha_fixed, m.alpha_opt, delta_alpha,
            eff_at_fixed if not math.isnan(eff_at_fixed) else 0.0,
            m.max_efficiency, eff_gain_pct if not math.isnan(eff_gain_pct) else 0.0,
        )

        enriched.append(dataclasses.replace(
            m,
            alpha_design=alpha_fixed,
            delta_alpha=delta_alpha,
            eff_at_design_alpha=eff_at_fixed,
            eff_gain=eff_gain,
            eff_gain_pct=eff_gain_pct,
        ))

    return enriched
