"""GE9X turbofan SFC parametric analysis for Stage 7.

Loads mid-span Cl/Cd data from Stage 4 results, identifies the reference
(fixed-pitch cruise β) and optimised (VPF α_opt) operating points, then
produces an ε → SFC-improvement sweep with figures and a LaTeX table.

Physical model: ε = Cl/Cd_new / Cl/Cd_ref → Δη_fan → ΔSFC (fan efficiency chain).
Thrust is fixed by aircraft drag; VPF changes only η_fan, not F_required.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from vpf_analysis.postprocessing.latex_exporter import export_table
from vpf_analysis.stage7_sfc_analysis.core.domain.sfc_parameters import ETA_FAN_DELTA_CAP
from vpf_analysis.stage7_sfc_analysis.engine.engine_data import (
    GE9X_PARAMS,
    sfc_lbh_to_si,
    sfc_si_to_lbh,
)
from vpf_analysis.stage7_sfc_analysis.engine.sfc_model import (
    _ETA_FAN_DEFAULT,
    _K_BPR_DEFAULT,
    compute_sfc_improvement,
)
from vpf_analysis.stage7_sfc_analysis.engine.turbofan_cycle import compute_turbofan_sfc

LOGGER = logging.getLogger(__name__)

# ε sweep: 0.90 to 3.0 (physically meaningful range for VPF off-design conditions)
_EPS_SWEEP = np.linspace(0.90, 3.00, 200)

_CONDITION_ORDER = ["takeoff", "climb", "cruise", "descent"]

# SFC cap value derived from model parameters (for annotation)
_SFC_CAP_PCT: float = _K_BPR_DEFAULT * ETA_FAN_DELTA_CAP / _ETA_FAN_DEFAULT * 100.0


def _load_clcd_at_alpha_opt(
    pitch_map_csv: Path,
    polars_dir: Path,
) -> dict[str, float]:
    """Return {condition: Cl/Cd at α_opt} for mid-span section."""
    pitch_df = pd.read_csv(pitch_map_csv)
    mid_rows = pitch_df[pitch_df["section"] == "mid_span"].set_index("flight")
    clcd_map: dict[str, float] = {}
    for cond in _CONDITION_ORDER:
        if cond not in mid_rows.index:
            continue
        alpha_opt = float(mid_rows.loc[cond, "alpha_opt"])
        polar_path = polars_dir / f"{cond}_mid_span.csv"
        if not polar_path.exists():
            continue
        pf = pd.read_csv(polar_path)
        for col in ("ld_corrected", "ld"):
            if col in pf.columns:
                eff_col = col
                break
        else:
            continue
        pf = pf.replace([float("inf"), float("-inf")], pd.NA).dropna(subset=[eff_col, "alpha"])
        if pf.empty:
            continue
        ld_interp = (
            pf.set_index("alpha")[eff_col]
            .reindex(sorted(set(pf["alpha"].tolist() + [alpha_opt])))
            .interpolate(method="index")
        )
        val = ld_interp.loc[alpha_opt]
        clcd_map[cond] = float(val.iloc[0] if hasattr(val, "iloc") else val)
    return clcd_map


def run_ge9x_analysis(
    stage4_dir: Path,
    stage2_dir: Path,
    tables_dir: Path,
) -> float | None:
    """Run GE9X parametric SFC analysis. Returns SFC_improvement_pct at takeoff α_opt, or None."""
    pitch_map_csv = stage2_dir / "pitch_map" / "blade_pitch_map.csv"
    polars_dir    = stage2_dir / "polars"

    if not pitch_map_csv.exists():
        pitch_map_csv = stage4_dir / "tables" / "blade_pitch_map.csv"
    if not pitch_map_csv.exists():
        LOGGER.warning("blade_pitch_map.csv not found — skipping GE9X analysis")
        return None

    # ── Validate cycle model ──────────────────────────────────────────────
    cycle = compute_turbofan_sfc(GE9X_PARAMS, "cruise")
    LOGGER.info(
        "GE9X cycle validation: SFC_cruise = %.4f lb/lbf·h  (ref %.2f, delta %+.1f%%)",
        cycle["SFC_lbh"], GE9X_PARAMS["SFC_ref_cruise"], cycle["validation_delta_pct"],
    )
    SFC_design_si = sfc_lbh_to_si(GE9X_PARAMS["SFC_ref_cruise"])

    # ── Load Cl/Cd at α_opt per condition ────────────────────────────────
    clcd_opt = _load_clcd_at_alpha_opt(pitch_map_csv, polars_dir)
    if not clcd_opt:
        LOGGER.warning("No Cl/Cd data found for GE9X analysis")
        return None

    ClCd_ref = clcd_opt.get("cruise", 100.0)
    LOGGER.info("Cl/Cd reference (cruise, fixed pitch, mid-span): %.2f", ClCd_ref)
    for cond, val in clcd_opt.items():
        eps = val / ClCd_ref
        LOGGER.info("  Cl/Cd at α_opt (%s): %.2f  (ε = %.3f)", cond, val, eps)

    # ── Parametric sweep (ε-based) ────────────────────────────────────────
    clcd_sweep = _EPS_SWEEP * ClCd_ref
    sweep_rows = [
        compute_sfc_improvement(ClCd_ref, float(clcd), SFC_design_si)
        for clcd in clcd_sweep
    ]
    df_sweep = pd.DataFrame(sweep_rows)
    df_sweep["SFC_lbh"] = df_sweep["SFC_new_kgNs"].apply(sfc_si_to_lbh)
    df_sweep.to_csv(tables_dir / "ge9x_sfc_parametric.csv", index=False, float_format="%.6f")

    # ── Key-points table (centred on linear→saturation transition) ────────
    # ε values: cover linear regime (1.0–1.08) and confirm saturation above it
    key_epsilons = [1.000, 1.020, 1.040, 1.060, 1.080, 1.100, 1.300, 1.500]
    key_rows = [
        compute_sfc_improvement(ClCd_ref, ClCd_ref * eps, SFC_design_si)
        for eps in key_epsilons
    ]
    df_key = pd.DataFrame(key_rows)
    df_key["SFC_lbh"] = df_key["SFC_new_kgNs"].apply(sfc_si_to_lbh)
    df_key.to_csv(tables_dir / "ge9x_sfc_improvement.csv", index=False, float_format="%.6f")

    # ── LaTeX table ───────────────────────────────────────────────────────
    export_table(
        df_key[["epsilon", "ClCd_new", "delta_eta_fan", "SFC_improvement_pct"]].rename(
            columns={
                "epsilon":             r"$\varepsilon$ [-]",
                "ClCd_new":            r"$(C_L/C_D)_\mathrm{VPF}$ [-]",
                "delta_eta_fan":       r"$\Delta\eta_\mathrm{fan}$ [-]",
                "SFC_improvement_pct": r"$\Delta$SFC [\%]",
            }
        ),
        output_path=tables_dir / "ge9x_sfc_improvement.tex",
        caption=(
            r"GE9X-105B1A SFC improvement as a function of the aerodynamic efficiency"
            r" ratio $\varepsilon = (C_L/C_D)_\mathrm{VPF}\,/\,(C_L/C_D)_\mathrm{ref}$"
            r" (cruise mid-span, fixed pitch). The improvement saturates at"
            rf" $\approx\!{_SFC_CAP_PCT:.1f}\,\%$ for $\varepsilon \gtrsim 1.08$ due to the"
            r" physical limit $\Delta\eta_\mathrm{{fan}} \leq 4\,\%$ (Cumpsty, 2004)."
        ),
        label="ge9x_sfc_improvement",
    )
    LOGGER.info("LaTeX table written: ge9x_sfc_improvement.tex")

    takeoff_clcd = clcd_opt.get("takeoff", None)
    if takeoff_clcd is not None:
        res = compute_sfc_improvement(ClCd_ref, takeoff_clcd, SFC_design_si)
        LOGGER.info(
            "GE9X: takeoff Cl/Cd=%.2f (ε=%.3f) → ΔSFC=%.2f%%",
            takeoff_clcd, takeoff_clcd / ClCd_ref, res["SFC_improvement_pct"],
        )
        return float(res["SFC_improvement_pct"])
    return None


