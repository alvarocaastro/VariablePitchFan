"""Pure functions for pitch kinematics: cascade, rotational, twist, loading."""

from __future__ import annotations

import logging
import math
import warnings
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from vpf_analysis.settings import get_settings as _get_settings
from vpf_analysis.config_loader import (
    get_gear_ratio,
    get_omega_map,
    get_radii,
    get_reference_mach,
    get_reynolds_map,
    get_target_mach,
    get_va_map,
)
from vpf_analysis.postprocessing.aerodynamics_utils import (
    find_second_peak_row,
    resolve_efficiency_column,
)
from vpf_analysis.stage5_pitch_kinematics.core.domain.pitch_kinematics_result import (
    KinematicsResult,
    OptimalIncidence,
    PitchAdjustment,
)

_physics = _get_settings().physics
_CARTER_M_NACA6: float = _physics.CARTER_M_NACA6
_SNEL_A: float = _physics.SNEL_A
_ALPHA_MIN_OPT: float = _physics.ALPHA_MIN_OPT_DEG
_CL_MIN_VIABLE: float = _physics.CL_MIN_3D
_PHI_MIN_DESIGN = _physics.PHI_DESIGN_MIN
_PHI_MAX_DESIGN = _physics.PHI_DESIGN_MAX
_PSI_MIN_DESIGN = _physics.PSI_DESIGN_MIN
_PSI_MAX_DESIGN = _physics.PSI_DESIGN_MAX

_DU_SELIG_A: float = _physics.DU_SELIG_A

LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cascade corrections (cascade_correction_service)
# ---------------------------------------------------------------------------


@dataclass
class CascadeResult:
    """Cascade correction results for a blade section."""
    section: str
    radius_m: float
    chord_m: float
    blade_spacing_m: float
    solidity: float
    k_weinig: float
    delta_carter_deg: float
    cl_2d_at_alpha_opt: float
    cl_cascade_at_alpha_opt: float

    @property
    def c_over_r(self) -> float:
        return self.chord_m / self.radius_m if self.radius_m > 0 else float("nan")


def _weinig_factor(sigma: float) -> float:
    """Weinig (1935) cascade correction: quadratic fit to Cumpsty (2004) Fig. 3.11.

    k = 1 − 0.130σ − 0.020σ²  (γ≈0° stagger, thin airfoil; validated σ∈[0.5, 2.5]).
    Fitted to tabulated values: σ=0.5→k=0.93, σ=1.0→k=0.85, σ=1.5→k=0.74, σ=2.0→k=0.63.
    The prior linear formula k=1−0.12σ over-estimated k by ≈10% at σ=1.73 (root).
    """
    if sigma <= 0.0:
        return 1.0
    k = 1.0 - 0.130 * sigma - 0.020 * sigma ** 2
    return max(min(k, 0.99), 0.55)


def _carter_deviation(theta_deg: float, sigma: float, m: float = _CARTER_M_NACA6) -> float:
    # Carter's rule for cascade deviation angle δ [°]:
    #   δ = m × θ / √σ
    # where θ = blade camber angle [°], σ = chord/pitch = solidity, m = 0.23 for NACA 6-series
    # (tabulated m for a/c=0.5 mean-line location from Dixon & Hall 2013, Table 3.2).
    # Source: Carter (1950), ARC R&M 2479; Dixon & Hall (2013) §3.5.
    if sigma <= 0.0:
        return 0.0
    return m * theta_deg / math.sqrt(sigma)


def compute_cascade_corrections(
    blade_geometry: dict,
    alpha_opt_by_section: dict[str, float],
    df_polars: pd.DataFrame,
) -> list[CascadeResult]:
    """Compute cascade corrections for each blade section."""
    Z = blade_geometry["num_blades"]
    solidities: dict[str, float] = blade_geometry["solidity"]
    theta = blade_geometry["theta_camber_deg"]
    radii = get_radii()

    results: list[CascadeResult] = []
    for section, r in radii.items():
        sigma = solidities.get(section, 1.0)
        s = 2.0 * math.pi * r / Z          # blade spacing [m]
        c = sigma * s                        # chord recovered for output only

        k_w = _weinig_factor(sigma)
        delta_c = _carter_deviation(theta, sigma)

        alpha_ref = alpha_opt_by_section.get(section, float("nan"))
        cl_2d = _lookup_cl(df_polars, section, "cruise", alpha_ref)
        cl_cascade = cl_2d * k_w if not math.isnan(cl_2d) else float("nan")

        results.append(CascadeResult(
            section=section,
            radius_m=r,
            chord_m=c,
            blade_spacing_m=s,
            solidity=sigma,
            k_weinig=k_w,
            delta_carter_deg=delta_c,
            cl_2d_at_alpha_opt=cl_2d,
            cl_cascade_at_alpha_opt=cl_cascade,
        ))

    return results


def apply_weinig_to_polar(
    df: pd.DataFrame,
    k_weinig: float,
    cl_col: str = "cl",
) -> pd.DataFrame:
    """Apply the Weinig correction to a full polar."""
    df = df.copy()
    cd_col = "cd_corrected" if "cd_corrected" in df.columns else "cd"
    df["cl_cascade"] = df[cl_col] * k_weinig
    df["ld_cascade"] = df["cl_cascade"] / df[cd_col].replace(0, float("nan"))
    return df


def _lookup_cl(
    df: pd.DataFrame,
    section: str,
    condition: str,
    alpha: float,
    tol: float = 0.5,
) -> float:
    if math.isnan(alpha):
        return float("nan")
    cl_col = "cl_corrected" if "cl_corrected" in df.columns else "cl"
    mask = (df["section"] == section) & (df["condition"] == condition)
    sub = df[mask].copy()
    if sub.empty:
        return float("nan")
    sub = sub.sort_values("alpha")
    close = sub[(sub["alpha"] - alpha).abs() <= tol]
    if close.empty:
        return float("nan")
    idx = (close["alpha"] - alpha).abs().idxmin()
    return float(close.loc[idx, cl_col])


# ---------------------------------------------------------------------------
# Rotational corrections (rotational_correction_service)
# ---------------------------------------------------------------------------


@dataclass
class DuSeligCorrectionResult:
    """3D rotational correction results using the Du-Selig (2000) model."""
    condition: str
    section: str
    radius_m: float
    chord_m: float
    c_over_r: float
    lambda_r: float
    du_selig_factor: float
    alpha_opt_2d: float
    cl_cd_max_2d: float
    alpha_opt_3d: float
    cl_cd_max_3d: float
    delta_cl_du_selig_at_opt: float
    cl_gain_pct: float


@dataclass
class RotationalCorrectionResult:
    """3D rotational correction results for a (condition, section) case."""
    condition: str
    section: str
    radius_m: float
    chord_m: float
    c_over_r: float
    snel_factor: float
    alpha_opt_2d: float
    cl_cd_max_2d: float
    alpha_opt_3d: float
    cl_cd_max_3d: float
    delta_cl_snel_at_opt: float
    cl_gain_pct: float


_SNEL_WARNED: bool = False


def _apply_snel(df: pd.DataFrame, c_over_r: float, cl_col: str) -> pd.DataFrame:
    df = df.copy()
    # Ref: Snel, H. et al. (1994), ECN-C-94-107 — ΔCL = 3.1·(c/r)²·(CL_pot − CL_2D); simplified to ΔCL = A·(c/r)²·CL_2D
    snel_factor = _SNEL_A * c_over_r ** 2
    cd_col = "cd_corrected" if "cd_corrected" in df.columns else "cd"
    df["delta_cl_snel"] = snel_factor * df[cl_col]
    df["cl_3d"] = df[cl_col] + df["delta_cl_snel"]
    df["ld_3d"] = df["cl_3d"] / df[cd_col].replace(0.0, float("nan"))
    # Snel (1994) was validated for wind turbines at tip-speed ratios λ_r > 3.
    # For turbofan fans λ_r ≈ 0.75–1.5 and c/r is large at the root → corrections
    # are unrealistically large. Use Du-Selig (1998) as the primary model.
    if c_over_r > 0.5:
        global _SNEL_WARNED
        if not _SNEL_WARNED:
            _SNEL_WARNED = True
            LOGGER.warning(
                "Snel correction: c/r=%.3f exceeds validation domain (wind-turbines, c/r≤0.3). "
                "Snel factor=%.2f → +%.0f%% ΔCL — physically unrealistic for fans. "
                "Du-Selig is the primary 3D model; Snel shown for comparison only.",
                c_over_r, snel_factor, snel_factor * 100.0,
            )
    return df


def _find_second_peak_3d(df: pd.DataFrame) -> tuple[float, float]:
    try:
        row = find_second_peak_row(
            df, "ld_3d", alpha_min=_ALPHA_MIN_OPT, cl_min=_CL_MIN_VIABLE, cl_col="cl_3d",
        )
        return float(row["alpha"]), float(row["ld_3d"])
    except (ValueError, KeyError):
        return float("nan"), float("nan")


def compute_rotational_corrections(
    df_polars: pd.DataFrame,
    blade_geometry: dict,
    alpha_opt_2d_map: dict[tuple, float],
    cl_cd_max_2d_map: dict[tuple, float],
) -> list[RotationalCorrectionResult]:
    """Compute Snel 3D corrections for each (condition, section)."""
    Z = blade_geometry["num_blades"]
    solidities: dict[str, float] = blade_geometry["solidity"]
    radii = get_radii()

    if "cl_cascade" in df_polars.columns:
        cl_col = "cl_cascade"
    elif "cl_corrected" in df_polars.columns:
        cl_col = "cl_corrected"
    else:
        cl_col = "cl"

    results: list[RotationalCorrectionResult] = []
    conditions = df_polars["condition"].unique()
    sections = list(radii.keys())

    for condition in conditions:
        for section in sections:
            r = radii.get(section, float("nan"))
            sigma = solidities.get(section, 1.0)
            # c/r = σ·2π/Z  (independent of r — pure non-dimensional relation)
            c_over_r = sigma * 2.0 * math.pi / Z if Z > 0 else 0.0
            c = c_over_r * r                   # chord in metres (for output only)
            snel_factor = _SNEL_A * c_over_r ** 2

            mask = (df_polars["condition"] == condition) & (df_polars["section"] == section)
            df_sub = df_polars[mask].sort_values("alpha").reset_index(drop=True)
            if df_sub.empty:
                continue

            df_3d = _apply_snel(df_sub, c_over_r, cl_col)
            alpha_3d, ld_3d = _find_second_peak_3d(df_3d)

            alpha_2d = alpha_opt_2d_map.get((condition, section), float("nan"))
            ld_2d = cl_cd_max_2d_map.get((condition, section), float("nan"))

            if not math.isnan(alpha_3d):
                close = df_3d[(df_3d["alpha"] - alpha_3d).abs() < 0.5]
                if not close.empty:
                    idx = (close["alpha"] - alpha_3d).abs().idxmin()
                    delta_cl = float(close.loc[idx, "delta_cl_snel"])
                    cl_base = float(close.loc[idx, cl_col])
                    gain_pct = 100.0 * delta_cl / cl_base if cl_base > 0 else 0.0
                else:
                    delta_cl = float("nan")
                    gain_pct = float("nan")
            else:
                delta_cl = float("nan")
                gain_pct = float("nan")

            results.append(RotationalCorrectionResult(
                condition=condition,
                section=section,
                radius_m=r,
                chord_m=c,
                c_over_r=c_over_r,
                snel_factor=snel_factor,
                alpha_opt_2d=alpha_2d,
                cl_cd_max_2d=ld_2d,
                alpha_opt_3d=alpha_3d,
                cl_cd_max_3d=ld_3d,
                delta_cl_snel_at_opt=delta_cl,
                cl_gain_pct=gain_pct,
            ))

    return results


def _apply_du_selig(
    df: pd.DataFrame,
    c_over_r: float,
    lambda_r: float,
    cl_col: str,
) -> pd.DataFrame:
    """Du-Selig (1998) 3D rotational correction — primary model for fan blades.

    Includes tip-speed-ratio dependence (f_lambda) absent from Snel (1994), making it
    valid for low-λ_r turbomachinery applications unlike the wind-turbine-derived Snel model.
    Du-Selig, Z. & Selig, M.S. (1998), J. Sol. Energy Eng. 120(2), 97-106.
    """
    df = df.copy()
    cd_col = "cd_corrected" if "cd_corrected" in df.columns else "cd"
    f_lambda = lambda_r ** 2 / (lambda_r ** 2 + 1.0) if lambda_r >= 0 else 0.0  # Ref: Du & Selig (1998), AIAA-1998-0021, eq. 20 — f(λ_r) = λ_r²/(λ_r²+1)
    du_selig_factor = _DU_SELIG_A * f_lambda * (c_over_r ** 1.6)  # Ref: Du & Selig (1998), AIAA-1998-0021 — ΔCL = 1.6·f(λ_r)·(c/r)^1.6·CL_2D
    df["delta_cl_du_selig"] = du_selig_factor * df[cl_col]
    df["cl_3d_ds"] = df[cl_col] + df["delta_cl_du_selig"]
    df["ld_3d_ds"] = df["cl_3d_ds"] / df[cd_col].replace(0.0, float("nan"))
    # Aliases used by downstream functions (ld_3d, cl_3d) that previously consumed Snel output
    df["cl_3d"] = df["cl_3d_ds"]
    df["ld_3d"] = df["ld_3d_ds"]
    return df


def _find_second_peak_du_selig(df: pd.DataFrame) -> tuple[float, float]:
    try:
        row = find_second_peak_row(
            df, "ld_3d_ds", alpha_min=_ALPHA_MIN_OPT, cl_min=_CL_MIN_VIABLE, cl_col="cl_3d_ds",
        )
        return float(row["alpha"]), float(row["ld_3d_ds"])
    except (ValueError, KeyError):
        return float("nan"), float("nan")


def compute_rotational_corrections_du_selig(
    df_polars: pd.DataFrame,
    blade_geometry: dict,
    alpha_opt_2d_map: dict[tuple, float],
    cl_cd_max_2d_map: dict[tuple, float],
    gear_ratio: float = 1.0,
) -> list[DuSeligCorrectionResult]:
    """Compute Du-Selig 3D corrections for each (condition, section)."""

    Z = blade_geometry["num_blades"]
    solidities: dict[str, float] = blade_geometry["solidity"]
    radii = get_radii()
    va_map = get_va_map(gear_ratio)
    omega_map = get_omega_map(gear_ratio)

    if "cl_cascade" in df_polars.columns:
        cl_col = "cl_cascade"
    elif "cl_corrected" in df_polars.columns:
        cl_col = "cl_corrected"
    else:
        cl_col = "cl"

    results: list[DuSeligCorrectionResult] = []
    conditions = df_polars["condition"].unique()
    sections = list(radii.keys())

    for condition in conditions:
        va = va_map.get(condition, 150.0)
        omega = omega_map.get(condition, next(iter(omega_map.values())))
        for section in sections:
            r = radii.get(section, float("nan"))
            sigma = solidities.get(section, 1.0)
            c_over_r = sigma * 2.0 * math.pi / Z if Z > 0 else 0.0
            c = c_over_r * r
            u = omega * r
            lambda_r = u / va if va > 0 else 0.0

            mask = (df_polars["condition"] == condition) & (df_polars["section"] == section)
            df_sub = df_polars[mask].sort_values("alpha").reset_index(drop=True)
            if df_sub.empty:
                continue

            df_3d = _apply_du_selig(df_sub, c_over_r, lambda_r, cl_col)
            alpha_3d, ld_3d = _find_second_peak_du_selig(df_3d)

            alpha_2d = alpha_opt_2d_map.get((condition, section), float("nan"))
            ld_2d = cl_cd_max_2d_map.get((condition, section), float("nan"))

            f_lambda = lambda_r ** 2 / (lambda_r ** 2 + 1.0) if lambda_r >= 0 else 0.0
            du_selig_factor = _DU_SELIG_A * f_lambda * (c_over_r ** 1.6)

            if not math.isnan(alpha_3d):
                close = df_3d[(df_3d["alpha"] - alpha_3d).abs() < 0.5]
                if not close.empty:
                    idx = (close["alpha"] - alpha_3d).abs().idxmin()
                    delta_cl = float(close.loc[idx, "delta_cl_du_selig"])
                    cl_base = float(close.loc[idx, cl_col])
                    gain_pct = 100.0 * delta_cl / cl_base if cl_base > 0 else 0.0
                else:
                    delta_cl = float("nan")
                    gain_pct = float("nan")
            else:
                delta_cl = float("nan")
                gain_pct = float("nan")

            results.append(DuSeligCorrectionResult(
                condition=condition,
                section=section,
                radius_m=r,
                chord_m=c,
                c_over_r=c_over_r,
                lambda_r=lambda_r,
                du_selig_factor=du_selig_factor,
                alpha_opt_2d=alpha_2d,
                cl_cd_max_2d=ld_2d,
                alpha_opt_3d=alpha_3d,
                cl_cd_max_3d=ld_3d,
                delta_cl_du_selig_at_opt=delta_cl,
                cl_gain_pct=gain_pct,
            ))

    return results


def build_3d_polar_map(
    df_polars: pd.DataFrame,
    blade_geometry: dict,
) -> dict[tuple, pd.DataFrame]:
    """Build a map of Du-Selig-corrected 3D polars: {(condition, section): DataFrame}.

    Du-Selig (1998) is the primary 3D rotational correction for fan blades.
    Snel (1994) is computed in parallel for reference only (see compute_rotational_corrections).
    """
    Z = blade_geometry["num_blades"]
    solidities = blade_geometry["solidity"]
    _gear_ratio = get_gear_ratio()
    radii = get_radii()
    va_map = get_va_map(_gear_ratio)
    omega_map = get_omega_map(_gear_ratio)

    if "cl_cascade" in df_polars.columns:
        cl_col = "cl_cascade"
    elif "cl_corrected" in df_polars.columns:
        cl_col = "cl_corrected"
    else:
        cl_col = "cl"

    polar_map: dict[tuple, pd.DataFrame] = {}
    for condition in df_polars["condition"].unique():
        va = va_map.get(condition, 150.0)
        omega_cond = omega_map.get(condition, next(iter(omega_map.values())))
        for section, r in radii.items():
            sigma = solidities.get(section, 1.0)
            c_over_r = sigma * 2.0 * math.pi / Z if Z > 0 else 0.0
            u = omega_cond * r
            lambda_r = u / va if va > 0 else 0.0
            mask = (df_polars["condition"] == condition) & (df_polars["section"] == section)
            df_sub = df_polars[mask].sort_values("alpha").reset_index(drop=True)
            if df_sub.empty:
                continue
            df_3d = _apply_du_selig(df_sub, c_over_r, lambda_r, cl_col)
            polar_map[(condition, section)] = df_3d

    return polar_map


# ---------------------------------------------------------------------------
# Optimal incidence (optimal_incidence_service)
# ---------------------------------------------------------------------------


def compute_optimal_incidence(
    df: pd.DataFrame,
    condition: str,
    section: str,
    reynolds: float,
    mach: float,
) -> OptimalIncidence:
    """Compute the optimal incidence point for a given polar."""
    eff_col = resolve_efficiency_column(df)
    row_opt = find_second_peak_row(df, eff_col)
    return OptimalIncidence(
        condition=condition,
        section=section,
        reynolds=reynolds,
        mach=mach,
        alpha_opt=float(row_opt["alpha"]),
        cl_cd_max=float(row_opt[eff_col]),
    )


def compute_all_optimal_incidences(
    df_polars: pd.DataFrame,
    df_corrected: pd.DataFrame | None = None,
) -> list[OptimalIncidence]:
    """Compute optimal incidence for all conditions and sections."""
    reynolds_table = get_reynolds_map()
    target_mach = get_target_mach()
    reference_mach = get_reference_mach()

    all_incidences: list[OptimalIncidence] = []

    conditions = df_polars["condition"].unique() if "condition" in df_polars.columns else []
    sections = df_polars["section"].unique() if "section" in df_polars.columns else []

    for condition in conditions:
        for section in sections:
            df_case = df_polars[
                (df_polars["condition"] == condition) & (df_polars["section"] == section)
            ]
            if df_case.empty:
                continue

            if df_corrected is not None and not df_corrected.empty:
                df_corr_case = df_corrected[
                    (df_corrected["condition"] == condition)
                    & (df_corrected["section"] == section)
                ]
                if not df_corr_case.empty:
                    df_case = df_corr_case

            try:
                reynolds = reynolds_table[condition][section]
            except KeyError:
                if "re" in df_case.columns:
                    reynolds = float(df_case["re"].iloc[0])
                else:
                    LOGGER.warning("Re not found for %s/%s — skipping.", condition, section)
                    continue

            mach = (
                target_mach.get(condition, reference_mach)
                if df_corrected is not None and not df_corrected.empty
                else reference_mach
            )

            try:
                incidence = compute_optimal_incidence(df_case, condition, section, reynolds, mach)
                all_incidences.append(incidence)
            except Exception as exc:
                LOGGER.warning(
                    "Could not compute optimal incidence for %s/%s: %s", condition, section, exc
                )

    return all_incidences


# ---------------------------------------------------------------------------
# Pitch adjustment (pitch_adjustment_service)
# ---------------------------------------------------------------------------

_LOG = logging.getLogger(__name__)


def compute_pitch_adjustments(
    optimal_incidences: list[OptimalIncidence],
    reference_condition: str = "cruise",
) -> list[PitchAdjustment]:
    """Compute pitch adjustments relative to a reference condition."""
    reference_alpha: dict[tuple[str, str], float] = {
        (inc.condition, inc.section): inc.alpha_opt
        for inc in optimal_incidences
        if inc.condition == reference_condition
    }

    if not reference_alpha:
        warnings.warn(
            f"compute_pitch_adjustments: no data found for reference_condition="
            f"'{reference_condition}'. All delta_pitch values will be 0.",
            RuntimeWarning,
            stacklevel=2,
        )
        _LOG.warning(
            "No optimal incidences found for reference condition '%s'; "
            "pitch adjustments will all be zero.",
            reference_condition,
        )

    adjustments: list[PitchAdjustment] = []
    for inc in optimal_incidences:
        key = (reference_condition, inc.section)
        alpha_ref = reference_alpha.get(key, inc.alpha_opt)
        delta_pitch = inc.alpha_opt - alpha_ref
        adjustments.append(
            PitchAdjustment(
                condition=inc.condition,
                section=inc.section,
                alpha_opt=inc.alpha_opt,
                delta_pitch=delta_pitch,
            )
        )

    return adjustments


# ---------------------------------------------------------------------------
# Blade twist (blade_twist_service)
# ---------------------------------------------------------------------------


@dataclass
class TwistDesignResult:
    """Design twist of the blade at the cruise design point."""
    section: str
    radius_m: float
    u_cruise_m_s: float
    phi_cruise_deg: float
    alpha_opt_3d_cruise: float
    beta_metal_deg: float
    twist_from_tip_deg: float


@dataclass
class OffDesignIncidenceResult:
    """Actual incidence and efficiency penalty under off-design conditions."""
    condition: str
    section: str
    va_m_s: float
    u_m_s: float
    phi_flow_deg: float
    delta_beta_hub_deg: float
    alpha_opt_3d: float
    alpha_actual_deg: float
    delta_alpha_compromise_deg: float
    cl_cd_max_3d: float
    cl_cd_actual: float
    efficiency_loss_pct: float


def compute_blade_twist(
    alpha_opt_3d_cruise: dict[str, float],
    va_cruise: float,
    omega: float,
    radii: dict[str, float],
) -> list[TwistDesignResult]:
    """Compute the blade design twist at cruise."""
    results: list[TwistDesignResult] = []
    for section, r in radii.items():
        u = omega * r
        if u <= 0:
            continue
        phi = math.degrees(math.atan2(va_cruise, u))
        alpha = alpha_opt_3d_cruise.get(section, float("nan"))
        beta_metal = alpha + phi if not math.isnan(alpha) else float("nan")
        results.append(TwistDesignResult(
            section=section,
            radius_m=r,
            u_cruise_m_s=u,
            phi_cruise_deg=phi,
            alpha_opt_3d_cruise=alpha,
            beta_metal_deg=beta_metal,
            twist_from_tip_deg=float("nan"),
        ))

    tip_beta = next(
        (res.beta_metal_deg for res in results if res.section == "tip"), float("nan")
    )
    for res in results:
        if not math.isnan(res.beta_metal_deg) and not math.isnan(tip_beta):
            res.twist_from_tip_deg = res.beta_metal_deg - tip_beta

    return results


def compute_off_design_incidence(
    twist_results: list[TwistDesignResult],
    alpha_opt_3d_map: dict[tuple[str, str], float],
    cl_cd_max_3d_map: dict[tuple[str, str], float],
    polar_3d_map: dict[tuple[str, str], pd.DataFrame],
    axial_velocities: dict[str, float],
    omega: dict[str, float],
    radii: dict[str, float],
    reference_condition: str = "cruise",
    hub_section: str = "mid_span",
) -> list[OffDesignIncidenceResult]:
    """Compute actual incidence and efficiency loss in off-design conditions."""
    beta_metal: dict[str, float] = {r.section: r.beta_metal_deg for r in twist_results}
    _omega_fallback = next(iter(omega.values())) if omega else 0.0

    results: list[OffDesignIncidenceResult] = []
    conditions = sorted(set(cond for cond, _ in alpha_opt_3d_map.keys()))

    for condition in conditions:
        va = axial_velocities.get(condition, float("nan"))
        omega_cond = omega.get(condition, _omega_fallback)

        r_hub = radii.get(hub_section, float("nan"))
        u_hub = omega_cond * r_hub
        phi_hub = math.degrees(math.atan2(va, u_hub)) if u_hub > 0 else 0.0
        alpha_hub_target = alpha_opt_3d_map.get((condition, hub_section), float("nan"))
        beta_metal_hub = beta_metal.get(hub_section, float("nan"))

        if not any(math.isnan(x) for x in [alpha_hub_target, phi_hub, beta_metal_hub]):
            delta_beta_hub = alpha_hub_target + phi_hub - beta_metal_hub
        else:
            delta_beta_hub = 0.0

        if condition == reference_condition:
            delta_beta_hub = 0.0

        for section, r in radii.items():
            u = omega_cond * r
            phi = math.degrees(math.atan2(va, u)) if u > 0 else 0.0
            bm = beta_metal.get(section, float("nan"))

            if not math.isnan(bm):
                alpha_actual = bm + delta_beta_hub - phi
            else:
                alpha_actual = float("nan")

            alpha_opt = alpha_opt_3d_map.get((condition, section), float("nan"))
            delta_compromise = (
                alpha_actual - alpha_opt
                if not any(math.isnan(x) for x in [alpha_actual, alpha_opt])
                else float("nan")
            )

            cl_cd_max = cl_cd_max_3d_map.get((condition, section), float("nan"))
            cl_cd_actual = _lookup_ld_3d(polar_3d_map, condition, section, alpha_actual)
            loss = (
                100.0 * (1.0 - cl_cd_actual / cl_cd_max)
                if not any(math.isnan(x) for x in [cl_cd_actual, cl_cd_max]) and cl_cd_max > 0
                else float("nan")
            )

            results.append(OffDesignIncidenceResult(
                condition=condition,
                section=section,
                va_m_s=va,
                u_m_s=u,
                phi_flow_deg=phi,
                delta_beta_hub_deg=delta_beta_hub,
                alpha_opt_3d=alpha_opt,
                alpha_actual_deg=alpha_actual,
                delta_alpha_compromise_deg=delta_compromise,
                cl_cd_max_3d=cl_cd_max,
                cl_cd_actual=cl_cd_actual,
                efficiency_loss_pct=loss,
            ))

    return results


def _lookup_ld_3d(
    polar_map: dict[tuple[str, str], pd.DataFrame],
    condition: str,
    section: str,
    alpha: float,
    tol: float = 1.0,
) -> float:
    if math.isnan(alpha):
        return float("nan")
    df = polar_map.get((condition, section))
    if df is None or df.empty:
        return float("nan")
    ld_col = (
        "ld_3d" if "ld_3d" in df.columns
        else "ld_cascade" if "ld_cascade" in df.columns
        else "ld"
    )
    close = df[(df["alpha"] - alpha).abs() <= tol]
    if close.empty:
        return float("nan")
    idx = (close["alpha"] - alpha).abs().idxmin()
    val = float(close.loc[idx, ld_col])
    return val if not math.isnan(val) else float("nan")


# ---------------------------------------------------------------------------
# Stage loading (stage_loading_service)
# ---------------------------------------------------------------------------


@dataclass
class StageLoadingResult:
    """Stage loading analysis result for a (condition, section) case."""
    condition: str
    section: str
    va_m_s: float
    u_m_s: float
    alpha_opt_3d_deg: float
    beta_mech_deg: float
    phi_flow_deg: float
    phi_coeff: float
    v_theta_m_s: float
    psi_loading: float
    w_specific_kj_kg: float
    in_design_zone: bool


def _in_design_zone(phi: float, psi: float) -> bool:
    return (
        _PHI_MIN_DESIGN <= phi <= _PHI_MAX_DESIGN
        and _PSI_MIN_DESIGN <= psi <= _PSI_MAX_DESIGN
    )


def compute_stage_loading(
    alpha_map_deg: dict[tuple[str, str], float],
    axial_velocities: dict[str, float],
    omega: dict[str, float],
    radii: dict[str, float],
) -> list[StageLoadingResult]:
    """Compute stage loading (φ, ψ, W_spec) for each (condition, section)."""
    _omega_fallback = next(iter(omega.values())) if omega else 0.0
    results: list[StageLoadingResult] = []

    for (condition, section), alpha_deg in alpha_map_deg.items():
        va = axial_velocities.get(condition, float("nan"))
        r = radii.get(section, float("nan"))

        if any(math.isnan(x) for x in [va, r, alpha_deg]):
            continue

        u = omega.get(condition, _omega_fallback) * r
        if u <= 0:
            continue
        phi_flow = math.degrees(math.atan2(va, u))
        beta_mech = alpha_deg + phi_flow
        phi_coeff = va / u  # Ref: Dixon & Hall (2013), Fluid Mechanics of Turbomachinery, §5.2 — φ = Va/U

        beta_rad = math.radians(beta_mech)
        tan_beta = math.tan(beta_rad)
        if abs(tan_beta) < 1e-6:
            v_theta = float("nan")
        else:
            v_theta = u - va / tan_beta

        psi = v_theta / u if u > 0 and not math.isnan(v_theta) else float("nan")  # Ref: Dixon & Hall (2013), §5.2 — ψ = Vθ/U
        w_spec = u * v_theta / 1000.0 if not math.isnan(v_theta) else float("nan")

        in_zone = (
            _in_design_zone(phi_coeff, psi)
            if not any(math.isnan(x) for x in [phi_coeff, psi])
            else False
        )

        results.append(StageLoadingResult(
            condition=condition,
            section=section,
            va_m_s=va,
            u_m_s=u,
            alpha_opt_3d_deg=alpha_deg,
            beta_mech_deg=beta_mech,
            phi_flow_deg=phi_flow,
            phi_coeff=phi_coeff,
            v_theta_m_s=v_theta,
            psi_loading=psi,
            w_specific_kj_kg=w_spec,
            in_design_zone=in_zone,
        ))

    return results


# ---------------------------------------------------------------------------
# Kinematics (kinematics_service)
# ---------------------------------------------------------------------------


def compute_kinematics(
    pitch_adjustments: list[PitchAdjustment],
    engine_config_path: Path,
    reference_condition: str = "cruise",
    gear_ratio: float = 1.0,
) -> list[KinematicsResult]:
    """Compute velocity triangles and mechanical pitch angle for each case."""
    omega_map = get_omega_map(gear_ratio)
    radii = get_radii()
    va_dict = get_va_map(gear_ratio)

    results: list[KinematicsResult] = []
    reference_beta: dict[str, float] = {}

    for adj in pitch_adjustments:
        va = va_dict.get(adj.condition, float("nan"))
        r = radii.get(adj.section, float("nan"))
        omega = omega_map.get(adj.condition, next(iter(omega_map.values())))
        u = omega * r if not math.isnan(r) else float("nan")
        phi = math.degrees(math.atan2(va, u)) if (u > 0 and not math.isnan(va)) else 0.0
        beta = adj.alpha_opt + phi

        results.append(KinematicsResult(
            condition=adj.condition,
            section=adj.section,
            axial_velocity=va,
            tangential_velocity=u,
            inflow_angle_deg=phi,
            alpha_aero_deg=adj.alpha_opt,
            beta_mech_deg=beta,
        ))

        if adj.condition == reference_condition:
            reference_beta[adj.section] = beta

    for res in results:
        ref_b = reference_beta.get(res.section, res.beta_mech_deg)
        res.delta_beta_mech_deg = res.beta_mech_deg - ref_b

    return results
