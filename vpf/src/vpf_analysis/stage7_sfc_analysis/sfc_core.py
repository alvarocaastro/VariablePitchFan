"""Pure functions for SFC analysis: propulsion model, mission fuel burn, summary."""

from __future__ import annotations

import logging
import math as _math
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from vpf_analysis.config_loader import get_flight_conditions
from vpf_analysis.stage7_sfc_analysis.core.domain.sfc_parameters import (
    EPSILON_CAP,
    ETA_FAN_ABS_CAP,
    ETA_FAN_COMBINED_CAP,
    ETA_FAN_DELTA_CAP,
    ETA_FAN_MAP_CAP,
    FAN_MAP_LOSS_COEFFICIENT,
    EngineBaseline,
    MissionFuelBurnResult,
    MissionSummary,
    SfcAnalysisResult,
    SfcSectionResult,
    SfcSensitivityPoint,
)

LOGGER = logging.getLogger(__name__)

_DEFAULT_TAU_VALUES: list[float] = [0.05, 0.08, 0.10, 0.15, 0.20, 0.30, 0.50, 0.65]

# Cascade reverser seal leakage adds ~0.75% SFC to the fixed-pitch baseline
# (Butterfield et al., ASME GT2004-53713; Walsh & Fletcher, §12.3)
_SEAL_LEAKAGE_PENALTY: float = 0.0075

# ---------------------------------------------------------------------------
# Propulsion model (propulsion_model_service)
# ---------------------------------------------------------------------------


def compute_bypass_sensitivity_factor(bypass_ratio: float) -> float:
    """Net thrust fraction produced by the bypass stream: k = BPR/(1+BPR).

    For a turbofan, the specific thrust is shared between bypass and core streams.
    In the high-BPR limit the fan dominates: as BPR → ∞, k → 1 (all thrust from fan).
    For BPR=15 (UHBPR): k = 15/16 = 0.9375.
    Source: Saravanamuttoo et al. (2017), Gas Turbine Theory, §5.14.
    """
    if bypass_ratio <= 0:
        raise ValueError("bypass_ratio must be positive.")
    return bypass_ratio / (1.0 + bypass_ratio)


def compute_propulsion_efficiency(v0: float, vj: float) -> float:
    """Propulsive efficiency: η_prop = 2 / (1 + V_j / V_0)."""
    if v0 <= 0:
        raise ValueError("Flight speed must be positive.")
    if vj <= 0:
        raise ValueError("Jet speed must be positive.")
    return 2.0 / (1.0 + vj / v0)


def compute_fan_efficiency_improvement(
    epsilon_values: list[float],
    fan_efficiency_baseline: float,
    tau: float = 0.08,
    epsilon_cap: float = EPSILON_CAP,
    eta_fan_delta_cap: float = ETA_FAN_DELTA_CAP,
    eta_fan_abs_cap: float = ETA_FAN_ABS_CAP,
) -> tuple[float, float, float]:
    """Estimate the fan efficiency improvement from the per-section ε ratios."""
    if fan_efficiency_baseline <= 0:
        raise ValueError("fan_efficiency_baseline must be positive.")
    if not epsilon_values:
        raise ValueError("epsilon_values cannot be empty.")

    delta_etas = [(min(eps, epsilon_cap) - 1.0) * tau for eps in epsilon_values]
    delta_eta_raw = sum(delta_etas) / len(delta_etas)
    delta_eta_capped = min(delta_eta_raw, eta_fan_delta_cap)

    eta_fan_new = min(
        fan_efficiency_baseline * (1.0 + delta_eta_capped),
        eta_fan_abs_cap,
    )
    delta_eta_applied = eta_fan_new - fan_efficiency_baseline

    return eta_fan_new, delta_eta_raw, delta_eta_applied


def compute_fan_map_efficiency_gain(
    phi_condition: float,
    phi_design: float,
    k_map: float = FAN_MAP_LOSS_COEFFICIENT,
    map_cap: float = ETA_FAN_MAP_CAP,
) -> float:
    """Fan efficiency gain from the fan-map mechanism (flow coefficient φ).

    VPF restores the design flow coefficient at off-design conditions by re-pitching
    the blade; this recovers the efficiency loss from operating away from the fan's
    peak efficiency point on its characteristic map. Modelled as a quadratic loss:
        Δη_map = k_map × ((φ − φ_opt) / φ_opt)²
    with k_map fitted to typical UHBR fan maps from Dixon & Hall (2013) Fig. 5.8.
    A cap of 0.015 prevents extrapolation beyond the map's off-design data range.
    Source: Dixon & Hall (2013), §5.3–5.4; Cumpsty (2004), Compressor Aerodynamics ch. 3.
    """
    if phi_design <= 0:
        return 0.0
    delta_phi_rel = (phi_condition - phi_design) / phi_design
    delta_eta_map = k_map * delta_phi_rel ** 2
    return min(delta_eta_map, map_cap)


def compute_combined_fan_efficiency_improvement(
    epsilon_values: list[float],
    phi_values: list[float],
    phi_design: float,
    fan_efficiency_baseline: float,
    tau: float = 0.08,
    epsilon_cap: float = EPSILON_CAP,
    eta_fan_delta_cap: float = ETA_FAN_DELTA_CAP,
    eta_fan_combined_cap: float = ETA_FAN_COMBINED_CAP,
    eta_fan_abs_cap: float = ETA_FAN_ABS_CAP,
    k_map: float = FAN_MAP_LOSS_COEFFICIENT,
    map_cap: float = ETA_FAN_MAP_CAP,
) -> tuple:
    """Fan efficiency improvement combining profile and map mechanisms."""
    if fan_efficiency_baseline <= 0:
        raise ValueError("fan_efficiency_baseline must be positive.")
    if not epsilon_values:
        raise ValueError("epsilon_values cannot be empty.")

    profile_deltas = [(min(eps, epsilon_cap) - 1.0) * tau for eps in epsilon_values]
    delta_eta_profile = min(
        sum(profile_deltas) / len(profile_deltas),
        eta_fan_delta_cap,
    )

    if phi_values and phi_design > 0:
        map_deltas = [
            compute_fan_map_efficiency_gain(phi, phi_design, k_map, map_cap)
            for phi in phi_values
        ]
        delta_eta_map = min(sum(map_deltas) / len(map_deltas), map_cap)
    else:
        delta_eta_map = 0.0

    delta_eta_combined = min(delta_eta_profile + delta_eta_map, eta_fan_combined_cap)

    eta_fan_new = min(
        fan_efficiency_baseline * (1.0 + delta_eta_combined),
        eta_fan_abs_cap,
    )
    delta_eta_applied = eta_fan_new - fan_efficiency_baseline

    return eta_fan_new, delta_eta_profile, delta_eta_map, delta_eta_applied


def compute_sfc_improvement(
    sfc_baseline: float,
    delta_eta_fan: float,
    eta_fan_baseline: float,
    k: float = 1.0,
) -> float:
    """SFC_new = SFC_base / (1 + k × Δη_fan / η_fan_base).

    Linearised relationship between fan efficiency gain and TSFC reduction.
    Derived by differentiating the Breguet range equation thrust-specific fuel
    consumption with respect to fan polytropic efficiency, then applying the
    bypass-ratio weighting factor k = BPR/(1+BPR):
        TSFC ∝ 1 / (η_fan × η_thermal × η_propulsive)
        → ΔTSFC/TSFC ≈ −k × Δη_fan / η_fan    (first-order Taylor expansion)
    Rearranging: SFC_new = SFC_base / (1 + k × Δη_fan / η_fan_base).
    Source: Saravanamuttoo et al. (2017) §5.14; Walsh & Fletcher (2004) §3.2.
    """
    if sfc_baseline <= 0:
        raise ValueError("sfc_baseline must be positive.")
    if eta_fan_baseline <= 0:
        raise ValueError("eta_fan_baseline must be positive.")
    if delta_eta_fan < 0:
        LOGGER.debug("delta_eta_fan < 0 (%.4f) — SFC will increase slightly.", delta_eta_fan)
    sensitivity = k * delta_eta_fan / eta_fan_baseline
    return max(sfc_baseline / (1.0 + sensitivity), 0.0)


def compute_sfc_reduction_percent(sfc_baseline: float, sfc_new: float) -> float:
    """Percentage SFC reduction: [(SFC_base − SFC_new) / SFC_base] × 100."""
    if sfc_baseline <= 0:
        raise ValueError("Baseline SFC must be positive.")
    return ((sfc_baseline - sfc_new) / sfc_baseline) * 100.0


# ---------------------------------------------------------------------------
# SFC analysis (sfc_analysis_service)
# ---------------------------------------------------------------------------


def compute_sfc_analysis(
    metrics_df: pd.DataFrame,
    engine_baseline: EngineBaseline,
    config_path: Path | None = None,
    stage5_dir: Path | None = None,
    stage3_dir: Path | None = None,
) -> tuple[list[SfcAnalysisResult], list[SfcSectionResult]]:
    """Compute the SFC analysis for all flight conditions."""
    tau, sfc_multipliers = _load_config(config_path)
    k = compute_bypass_sensitivity_factor(engine_baseline.bypass_ratio)
    flight_conditions = get_flight_conditions()

    try:
        from vpf_analysis.config_loader import (
            get_gear_ratio, get_omega_map, get_phi_design, get_r_rel, get_radii, get_va_map,
        )
        _gear_ratio = get_gear_ratio()
        _va = get_va_map(_gear_ratio)
        _radii = get_radii()
        _omega_map = get_omega_map(_gear_ratio)
        _omega_cruise = _omega_map.get("cruise", next(iter(_omega_map.values())))
        _use_map = True
        _phi_design_cfg = get_phi_design()
        _r_rel_cfg = get_r_rel()
        _phi_design: dict = {
            sec: _phi_design_cfg.get("cruise", 0.411) / _r_rel_cfg.get(sec, 1.0)
            for sec in _radii
        }
    except Exception as exc:
        LOGGER.warning("Could not load kinematic data for map mechanism: %s — profile only.", exc)
        _use_map = False
        _va = {}
        _radii = {}
        _omega_map = {}
        _omega_cruise = 0.0
        _phi_design = {}

    _s5: dict | None = None
    if stage5_dir is not None and stage5_dir.is_dir():
        try:
            _s5 = _load_stage5_tables(stage5_dir)
            LOGGER.info("Stage 5 3D data loaded from %s", stage5_dir)
        except Exception as exc:
            LOGGER.warning("Could not load Stage 5: %s — falling back to Stage 4.", exc)

    _annular_w = _annular_weights(_radii) if _radii else {}

    section_results: list[SfcSectionResult] = []
    sfc_results: list[SfcAnalysisResult] = []

    for condition in flight_conditions:
        cond_df = metrics_df[metrics_df["flight_condition"] == condition]
        if cond_df.empty:
            LOGGER.warning("No Stage 4 data for condition '%s' — skipped.", condition)
            continue

        _va_cond = _va.get(condition, 0.0) if _use_map else 0.0

        cond_sections: list[SfcSectionResult] = []
        for _, row in cond_df.iterrows():
            section = str(row.get("blade_section", "unknown"))

            if _s5 is not None and stage3_dir is not None:
                sr_base = _compute_section_result_stage5(condition, row, tau, _s5, stage3_dir)
            else:
                sr_base = _compute_section_result(condition, row, tau)

            if condition.lower() == "cruise":
                phi_des = _phi_design.get(section, float("nan"))
                phi_cond = phi_des
                delta_eta_map = 0.0
            elif _use_map and section in _radii and _omega_cruise > 0:
                _omega_cond = _omega_map.get(condition, _omega_cruise) if _omega_map else _omega_cruise
                u_sec = _omega_cond * _radii[section]
                phi_cond = _va_cond / u_sec if u_sec > 0 else float("nan")
                phi_des = _phi_design.get(section, float("nan"))
                delta_eta_map = (
                    compute_fan_map_efficiency_gain(phi_cond, phi_des)
                    if not _math.isnan(phi_cond) and not _math.isnan(phi_des)
                    else 0.0
                )
            else:
                phi_cond = float("nan")
                phi_des = _phi_design.get(section, float("nan"))
                delta_eta_map = 0.0

            delta_eta_total = sr_base.delta_eta_profile + delta_eta_map

            import dataclasses as _dc
            sr = _dc.replace(
                sr_base,
                phi_condition=phi_cond,
                phi_design=phi_des,
                delta_eta_map=delta_eta_map,
                delta_eta_total=delta_eta_total,
            )
            cond_sections.append(sr)
        section_results.extend(cond_sections)

        epsilon_values = [s.epsilon for s in cond_sections]
        epsilon_w_values = [
            (s.epsilon, _annular_w.get(s.blade_section, 1.0))
            for s in cond_sections
        ]
        phi_values = [
            s.phi_condition for s in cond_sections if not _math.isnan(s.phi_condition)
        ]
        phi_design_val = _mean(
            [s.phi_design for s in cond_sections if not _math.isnan(s.phi_design)]
        )
        delta_alpha_vals = [s.delta_alpha_deg for s in cond_sections]
        cl_cd_fixed_vals = [s.cl_cd_fixed for s in cond_sections]
        cl_cd_vpf_vals = [s.cl_cd_vpf for s in cond_sections]

        epsilon_weighted = (
            _weighted_mean(epsilon_w_values) if epsilon_w_values else _mean(epsilon_values)
        )

        phi_values_agg = [] if condition.lower() == "cruise" else phi_values

        (eta_fan_new, delta_eta_profile, delta_eta_map_mean, delta_eta_applied) = (
            compute_combined_fan_efficiency_improvement(
                epsilon_values=[epsilon_weighted] * len(epsilon_values),
                phi_values=phi_values_agg,
                phi_design=phi_design_val if not _math.isnan(phi_design_val) else 0.0,
                fan_efficiency_baseline=engine_baseline.fan_efficiency,
                tau=tau,
            )
        )

        sfc_multiplier = sfc_multipliers.get(condition, 1.0)
        sfc_baseline = engine_baseline.baseline_sfc * sfc_multiplier * (1.0 + _SEAL_LEAKAGE_PENALTY)
        sfc_new = compute_sfc_improvement(
            sfc_baseline=sfc_baseline,
            delta_eta_fan=delta_eta_applied,
            eta_fan_baseline=engine_baseline.fan_efficiency,
            k=k,
        )
        sfc_reduction = compute_sfc_reduction_percent(sfc_baseline, sfc_new)

        sfc_results.append(SfcAnalysisResult(
            condition=condition,
            cl_cd_fixed=_mean(cl_cd_fixed_vals),
            cl_cd_vpf=_mean(cl_cd_vpf_vals),
            epsilon_mean=epsilon_weighted,
            delta_alpha_mean_deg=_mean(delta_alpha_vals),
            fan_efficiency_baseline=engine_baseline.fan_efficiency,
            fan_efficiency_new=eta_fan_new,
            delta_eta_fan=delta_eta_applied,
            k_sensitivity=k,
            sfc_baseline=sfc_baseline,
            sfc_new=sfc_new,
            sfc_reduction_percent=sfc_reduction,
            delta_eta_profile=delta_eta_profile,
            delta_eta_map=delta_eta_map_mean,
            phi_design=phi_design_val if not _math.isnan(phi_design_val) else float("nan"),
            phi_condition=_mean(phi_values) if phi_values else float("nan"),
        ))

    return sfc_results, section_results


def compute_sfc_sensitivity(
    metrics_df: pd.DataFrame,
    engine_baseline: EngineBaseline,
    tau_values: list[float] | None = None,
    config_path: Path | None = None,
) -> list[SfcSensitivityPoint]:
    """Parametric sweep of SFC over the transfer coefficient τ."""
    if tau_values is None:
        tau_values = _DEFAULT_TAU_VALUES

    _, sfc_multipliers = _load_config(config_path)
    k = compute_bypass_sensitivity_factor(engine_baseline.bypass_ratio)
    flight_conditions = get_flight_conditions()

    points: list[SfcSensitivityPoint] = []

    for tau in tau_values:
        for condition in flight_conditions:
            cond_df = metrics_df[metrics_df["flight_condition"] == condition]
            if cond_df.empty:
                continue

            epsilon_values = []
            for _, row in cond_df.iterrows():
                cl_cd_fixed = float(row.get("eff_at_design_alpha", 0.0))
                cl_cd_vpf = float(row.get("max_efficiency", 0.0))
                if cl_cd_fixed > 0:
                    epsilon_values.append(cl_cd_vpf / cl_cd_fixed)

            if not epsilon_values:
                continue

            eta_fan_new, _, _, delta_eta_applied = compute_combined_fan_efficiency_improvement(
                epsilon_values=epsilon_values,
                phi_values=[],
                phi_design=0.0,
                fan_efficiency_baseline=engine_baseline.fan_efficiency,
                tau=tau,
            )

            sfc_multiplier = sfc_multipliers.get(condition, 1.0)
            sfc_baseline = engine_baseline.baseline_sfc * sfc_multiplier
            sfc_new = compute_sfc_improvement(
                sfc_baseline=sfc_baseline,
                delta_eta_fan=delta_eta_applied,
                eta_fan_baseline=engine_baseline.fan_efficiency,
                k=k,
            )
            sfc_reduction = compute_sfc_reduction_percent(sfc_baseline, sfc_new)

            points.append(SfcSensitivityPoint(
                tau=tau,
                condition=condition,
                epsilon_mean=_mean(epsilon_values),
                delta_eta_fan=delta_eta_applied,
                eta_fan_new=eta_fan_new,
                sfc_baseline=sfc_baseline,
                sfc_new=sfc_new,
                sfc_reduction_pct=sfc_reduction,
            ))

    return points


def _compute_section_result(condition: str, row: pd.Series, tau: float) -> SfcSectionResult:
    cl_cd_fixed = float(row.get("eff_at_design_alpha", 0.0))
    cl_cd_vpf = float(row.get("max_efficiency", 0.0))
    delta_alpha = float(row.get("delta_alpha_deg", 0.0))
    section = str(row.get("blade_section", "unknown"))

    if cl_cd_fixed > 0:
        epsilon = cl_cd_vpf / cl_cd_fixed
    else:
        epsilon = 1.0
        LOGGER.warning("eff_at_design_alpha = 0 for %s/%s — assuming ε = 1.0", condition, section)

    epsilon_eff = min(epsilon, EPSILON_CAP)
    delta_eta_profile = (epsilon_eff - 1.0) * tau
    efficiency_gain_pct = (epsilon_eff - 1.0) * 100.0

    return SfcSectionResult(
        condition=condition,
        blade_section=section,
        cl_cd_fixed=cl_cd_fixed,
        cl_cd_vpf=cl_cd_vpf,
        epsilon=epsilon,
        epsilon_eff=epsilon_eff,
        delta_eta_profile=delta_eta_profile,
        efficiency_gain_pct=efficiency_gain_pct,
        delta_alpha_deg=delta_alpha,
    )


def _compute_section_result_stage5(
    condition: str,
    row: pd.Series,
    tau: float,
    s5: Dict,
    stage3_dir: Path,
) -> SfcSectionResult:
    section = str(row.get("blade_section", "unknown"))
    delta_alpha = float(row.get("delta_alpha_deg", 0.0))

    btd = s5["blade_twist_design"]
    kin = s5["kinematics"]

    row_btd = btd[btd["section"] == section]
    row_kin_cond = kin[(kin["condition"] == condition) & (kin["section"] == section)]

    if row_btd.empty or row_kin_cond.empty:
        LOGGER.warning(
            "Incomplete Stage 5 kinematic data for %s/%s — fallback.", condition, section
        )
        return _compute_section_result(condition, row, tau)

    beta_metal = float(row_btd["beta_metal_deg"].iloc[0])
    phi_cond = float(row_kin_cond["inflow_angle_phi_deg"].iloc[0])
    alpha_fixed = beta_metal - phi_cond

    if condition.lower() == "cruise":
        return SfcSectionResult(
            condition=condition,
            blade_section=section,
            cl_cd_fixed=(
                float(row.get("eff_at_design_alpha", 0.0))
                or float(row.get("max_efficiency", 1.0))
            ),
            cl_cd_vpf=float(row.get("max_efficiency", 1.0)),
            epsilon=1.0,
            epsilon_eff=1.0,
            delta_eta_profile=0.0,
            efficiency_gain_pct=0.0,
            delta_alpha_deg=delta_alpha,
        )

    polar_path = stage3_dir / condition.lower() / section / "corrected_polar.csv"
    if not polar_path.is_file():
        LOGGER.warning("Stage 3 polar not found: %s — fallback to Stage 4.", polar_path)
        return _compute_section_result(condition, row, tau)

    polar_df = pd.read_csv(polar_path)
    alphas = polar_df["alpha"].values
    cl_kt_arr = polar_df["cl_kt"].values
    cd_arr = polar_df["cd_corrected"].values

    with np.errstate(divide="ignore", invalid="ignore"):
        cl_cd_arr = np.where(cd_arr > 0.0, cl_kt_arr / cd_arr, np.nan)

    def _interp_cl_cd(alpha: float) -> float:
        a = float(np.clip(alpha, alphas.min(), alphas.max()))
        cl = float(np.interp(a, alphas, cl_kt_arr))
        cd = float(np.interp(a, alphas, cd_arr))
        return cl / cd if cd > 0.0 else float("nan")

    valid = np.isfinite(cl_cd_arr)
    if not valid.any():
        LOGGER.warning("No valid CL/CD in polar for %s/%s — fallback.", condition, section)
        return _compute_section_result(condition, row, tau)

    cl_cd_vpf = float(np.nanmax(cl_cd_arr))
    cl_cd_fixed = _interp_cl_cd(alpha_fixed)

    if _math.isnan(cl_cd_fixed) or cl_cd_fixed <= 0.0:
        epsilon = 1.0
        LOGGER.warning("Invalid CL/CD_fixed for %s/%s — epsilon=1.", condition, section)
    else:
        epsilon = cl_cd_vpf / cl_cd_fixed

    epsilon_eff = min(epsilon, EPSILON_CAP)
    delta_eta_profile = (epsilon_eff - 1.0) * tau
    efficiency_gain_pct = (epsilon_eff - 1.0) * 100.0

    return SfcSectionResult(
        condition=condition,
        blade_section=section,
        cl_cd_fixed=cl_cd_fixed,
        cl_cd_vpf=cl_cd_vpf,
        epsilon=epsilon,
        epsilon_eff=epsilon_eff,
        delta_eta_profile=delta_eta_profile,
        efficiency_gain_pct=efficiency_gain_pct,
        delta_alpha_deg=delta_alpha,
    )


def _load_stage5_tables(stage5_dir: Path) -> Dict:
    td = stage5_dir / "tables"
    return {
        "optimal_incidence": pd.read_csv(td / "optimal_incidence.csv"),
        "blade_twist_design": pd.read_csv(td / "blade_twist_design.csv"),
        "kinematics": pd.read_csv(td / "kinematics_analysis.csv"),
        "cascade": pd.read_csv(td / "cascade_corrections.csv"),
    }


def _annular_weights(radii: dict[str, float]) -> dict[str, float]:
    sections = ["root", "mid_span", "tip"]
    r = [radii.get(s, 0.0) for s in sections]
    if any(v <= 0 for v in r):
        return {}
    # Hub radius from fan geometry (hub_to_tip_ratio × r_tip).
    # Fallback: extrapolate inward from root with equal section spacing.
    try:
        from vpf_analysis.settings import get_settings
        _fan = get_settings().fan
        r_hub = _fan.hub_to_tip_ratio * _fan.r_tip_m
    except Exception:
        r_hub = max(r[0] - (r[1] - r[0]) / 2.0, 0.0)
    boundaries = [r_hub, (r[0] + r[1]) / 2.0, (r[1] + r[2]) / 2.0, r[2]]
    areas = [boundaries[i + 1] ** 2 - boundaries[i] ** 2 for i in range(3)]
    total = sum(areas)
    if total <= 0:
        return {}
    return {s: a / total for s, a in zip(sections, areas)}


def _load_config(config_path: Path | None) -> tuple[float, dict]:
    tau = 0.08
    sfc_multipliers: dict = {}
    if config_path and config_path.exists():
        try:
            with config_path.open("r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            tau = float(cfg.get("profile_efficiency_transfer", tau))
            sfc_multipliers = cfg.get("sfc_multipliers", {})
        except Exception as exc:
            LOGGER.warning(
                "Could not read engine_parameters.yaml: %s — using τ=%.2f", exc, tau
            )
    return tau, sfc_multipliers


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _weighted_mean(values_weights: list[tuple[float, float]]) -> float:
    total_w = sum(w for _, w in values_weights)
    if total_w <= 0:
        return _mean([v for v, _ in values_weights])
    return sum(v * w for v, w in values_weights) / total_w


# ---------------------------------------------------------------------------
# Mission analysis (mission_analysis_service)
# ---------------------------------------------------------------------------

_LB_TO_KG: float = 0.453592
_LB_PER_KN: float = 224.809
_CO2_FACTOR: float = 3.16  # kg CO2 / kg fuel — Ref: ICAO CORSIA (2022), LCA Methodology, §1.4.5 aviation fuel baseline
_MIN_TO_HR: float = 1.0 / 60.0


def compute_mission_fuel_burn(
    sfc_results: list[SfcAnalysisResult],
    mission_profile: dict,
) -> tuple[MissionSummary, list[MissionFuelBurnResult]]:
    """Compute the total mission fuel saving with VPF."""
    sfc_map = {r.condition: r for r in sfc_results}

    design_thrust_kN: float = float(mission_profile.get("design_thrust_kN", 105.0))
    fuel_price: float = float(mission_profile.get("fuel_price_usd_per_kg", 0.90))
    phases: dict = mission_profile.get("phases", {})

    phase_results: list[MissionFuelBurnResult] = []

    for phase, params in phases.items():
        duration_min = float(params["duration_min"])
        thrust_fraction = float(params["thrust_fraction"])
        duration_hr = duration_min * _MIN_TO_HR
        thrust_kN = design_thrust_kN * thrust_fraction
        thrust_lbf = thrust_kN * _LB_PER_KN

        sfc_res = sfc_map.get(phase)
        if sfc_res is None:
            LOGGER.warning(
                "No SFC result for phase '%s' — omitted from mission analysis.", phase
            )
            continue

        fuel_baseline_kg = sfc_res.sfc_baseline * thrust_lbf * duration_hr * _LB_TO_KG
        fuel_vpf_kg = sfc_res.sfc_new * thrust_lbf * duration_hr * _LB_TO_KG
        fuel_saving_kg = fuel_baseline_kg - fuel_vpf_kg
        co2_saving_kg = fuel_saving_kg * _CO2_FACTOR
        cost_saving_usd = fuel_saving_kg * fuel_price

        phase_results.append(MissionFuelBurnResult(
            phase=phase,
            duration_min=duration_min,
            thrust_kN=thrust_kN,
            sfc_baseline=sfc_res.sfc_baseline,
            sfc_vpf=sfc_res.sfc_new,
            fuel_baseline_kg=fuel_baseline_kg,
            fuel_vpf_kg=fuel_vpf_kg,
            fuel_saving_kg=fuel_saving_kg,
            co2_saving_kg=co2_saving_kg,
            cost_saving_usd=cost_saving_usd,
        ))

    if not phase_results:
        LOGGER.error("No mission phase could be computed.")
        return MissionSummary(0, 0, 0, 0, 0, 0, []), []

    total_baseline = sum(p.fuel_baseline_kg for p in phase_results)
    total_vpf = sum(p.fuel_vpf_kg for p in phase_results)
    total_saving = sum(p.fuel_saving_kg for p in phase_results)
    total_co2 = sum(p.co2_saving_kg for p in phase_results)
    total_cost = sum(p.cost_saving_usd for p in phase_results)
    saving_pct = 100.0 * total_saving / total_baseline if total_baseline > 0 else 0.0

    summary = MissionSummary(
        total_fuel_baseline_kg=total_baseline,
        total_fuel_vpf_kg=total_vpf,
        total_fuel_saving_kg=total_saving,
        total_fuel_saving_pct=saving_pct,
        total_co2_saving_kg=total_co2,
        total_cost_saving_usd=total_cost,
        phase_results=phase_results,
    )
    return summary, phase_results


# ---------------------------------------------------------------------------
# Summary generator (summary_generator_service)
# ---------------------------------------------------------------------------


def generate_sfc_summary(
    sfc_results: list[SfcAnalysisResult],
    section_results: list[SfcSectionResult] | None = None,
    mission_summary: MissionSummary | None = None,
) -> str:
    """Generate a human-readable summary of the SFC analysis results."""
    lines = []
    lines.append("=" * 70)
    lines.append("SPECIFIC FUEL CONSUMPTION (SFC) IMPACT ANALYSIS — SUMMARY")
    lines.append("=" * 70)
    lines.append("")
    lines.append("Physical model (two independent mechanisms):")
    lines.append("")
    lines.append("  Mechanism 1 — Profile (2D → 3D via τ):")
    lines.append("    α_fixed(cond,sec) = β_cruise(sec) − φ(cond,sec)")
    lines.append("    ε(r, cond)        = CL/CD_vpf / CL/CD_fixed")
    lines.append("    Δη_profile        = mean_r[(min(ε,1.10)−1)×τ],  cap ≤ 0.04")
    lines.append("")
    lines.append("  Mechanism 2 — Fan map (flow coefficient φ):")
    lines.append("    Δη_map           = k_map × ((φ − φ_opt) / φ_opt)²,  cap ≤ 0.015")
    lines.append("")
    lines.append("  Combined:")
    lines.append("    Δη_fan           = min(Δη_profile + Δη_map, 0.048)")
    lines.append("    η_fan,new        = min(η_base × (1 + Δη_fan), 0.96)")
    lines.append("    SFC_new          = SFC_base / (1 + k × Δη_fan / η_base)")
    lines.append("    k = BPR/(1+BPR)")
    lines.append("")

    if section_results:
        lines.append("-" * 70)
        lines.append("1. EFFICIENCY RATIO ε PER SECTION")
        lines.append("-" * 70)
        lines.append("")
        conditions_order = ["takeoff", "climb", "cruise", "descent"]
        sections_order = ["root", "mid_span", "tip"]
        header = (
            f"  {'Condition':<12}  {'Section':<10}  {'CL/CD_fixed':>11}  "
            f"{'CL/CD_vpf':>9}  {'ε_raw':>7}  {'ε_eff':>5}  {'Δα [°]':>7}  {'Gain':>8}"
        )
        lines.append(header)
        lines.append("  " + "-" * 74)
        for cond in conditions_order:
            for sec in sections_order:
                row = next(
                    (r for r in section_results if r.condition == cond and r.blade_section == sec),
                    None,
                )
                if row is None:
                    continue
                epsilon_note = ">cap" if row.epsilon > EPSILON_CAP else "    "
                lines.append(
                    f"  {cond:<12}  {sec:<10}  {row.cl_cd_fixed:>10.2f}  "
                    f"{row.cl_cd_vpf:>9.2f}  {row.epsilon:>7.3f}  "
                    f"{row.epsilon_eff:>5.3f}  "
                    f"{row.delta_alpha_deg:>7.2f}  {row.efficiency_gain_pct:>7.1f}%"
                    f"  {epsilon_note}"
                )
        lines.append("")

        has_map = any(not _math.isnan(r.phi_condition) for r in section_results)
        if has_map:
            lines.append("-" * 70)
            lines.append("1b. FAN MAP MECHANISM PER SECTION")
            lines.append("-" * 70)
            lines.append("")
            header2 = (
                f"  {'Condition':<12}  {'Section':<10}  {'φ_design':>9}  "
                f"{'φ_cond':>8}  {'Δφ/φ [%]':>9}  {'Δη_map':>8}"
            )
            lines.append(header2)
            lines.append("  " + "-" * 64)
            for cond in conditions_order:
                for sec in sections_order:
                    row = next(
                        (r for r in section_results
                         if r.condition == cond and r.blade_section == sec),
                        None,
                    )
                    if row is None or _math.isnan(row.phi_condition):
                        continue
                    delta_phi_pct = (
                        (row.phi_condition - row.phi_design) / row.phi_design * 100.0
                        if row.phi_design > 0 else float("nan")
                    )
                    lines.append(
                        f"  {cond:<12}  {sec:<10}  {row.phi_design:>9.4f}  "
                        f"{row.phi_condition:>8.4f}  {delta_phi_pct:>+9.1f}%  "
                        f"{row.delta_eta_map:>8.5f}"
                    )
            lines.append("")

    lines.append("-" * 70)
    lines.append("2. MEAN AERODYNAMIC EFFICIENCY (per condition)")
    lines.append("-" * 70)
    lines.append("")
    for result in sorted(sfc_results, key=lambda x: x.condition):
        improvement = (result.epsilon_mean - 1.0) * 100.0
        lines.append(f"  {result.condition.upper():<10}")
        lines.append(f"    CL/CD fixed-pitch: {result.cl_cd_fixed:7.2f}")
        lines.append(
            f"    CL/CD VPF        : {result.cl_cd_vpf:7.2f}  "
            f"(ε_mean = {result.epsilon_mean:.3f}, +{improvement:.1f}%)"
        )
        lines.append(f"    Δα mean          : {result.delta_alpha_mean_deg:.2f}°")
        lines.append("")

    lines.append("-" * 70)
    lines.append("3. FAN EFFICIENCY — BREAKDOWN BY MECHANISM")
    lines.append("-" * 70)
    lines.append("")
    for result in sorted(sfc_results, key=lambda x: x.condition):
        lines.append(f"  {result.condition.upper():<10}")
        lines.append(f"    η_fan baseline   : {result.fan_efficiency_baseline:.4f}")
        if not _math.isnan(result.delta_eta_profile):
            lines.append(
                f"    Δη_profile       : {result.delta_eta_profile:+.5f}  (mechanism 1)"
            )
        if not _math.isnan(result.delta_eta_map):
            phi_info = ""
            if (
                not _math.isnan(result.phi_condition)
                and not _math.isnan(result.phi_design)
                and result.phi_design > 0
            ):
                delta_phi_pct = (
                    (result.phi_condition - result.phi_design) / result.phi_design * 100.0
                )
                phi_info = f"  φ={result.phi_condition:.4f} vs φ_opt={result.phi_design:.4f} ({delta_phi_pct:+.1f}%)"
            lines.append(
                f"    Δη_map           : {result.delta_eta_map:+.5f}  (mechanism 2){phi_info}"
            )
        lines.append(f"    Δη_fan applied   : {result.delta_eta_fan:+.5f}  (combined, after caps)")
        lines.append(f"    η_fan VPF        : {result.fan_efficiency_new:.4f}")
        lines.append(f"    k = BPR/(1+BPR)  = {result.k_sensitivity:.4f}")
        lines.append("")

    lines.append("-" * 70)
    lines.append("4. SFC IMPACT")
    lines.append("-" * 70)
    lines.append("")
    for result in sorted(sfc_results, key=lambda x: x.condition):
        lines.append(f"  {result.condition.upper():<10}")
        lines.append(f"    SFC baseline: {result.sfc_baseline:.4f} lb/(lbf·hr)")
        lines.append(f"    SFC VPF     : {result.sfc_new:.4f} lb/(lbf·hr)")
        lines.append(f"    Reduction   : {result.sfc_reduction_percent:6.2f}%")
        lines.append("")

    avg_reduction = sum(r.sfc_reduction_percent for r in sfc_results) / len(sfc_results)
    max_reduction = max(r.sfc_reduction_percent for r in sfc_results)
    max_cond = max(sfc_results, key=lambda r: r.sfc_reduction_percent).condition
    lines.append("-" * 70)
    lines.append("5. KEY RESULTS")
    lines.append("-" * 70)
    lines.append("")
    lines.append(f"  Simple-mean SFC reduction  : {avg_reduction:.2f}%  (equal weight per condition)")
    lines.append(f"  Maximum SFC reduction      : {max_reduction:.2f}%  ({max_cond})")

    # Mission-weighted SFC reduction: Σ(fuel_saving_i) / Σ(fuel_baseline_i)
    # This is the physically correct metric — it weights each phase by actual fuel consumed,
    # not by the number of flight conditions. Cruise dominates (480/525.5 min = 91.4%)
    # and VPF gains 0% at cruise (design point → optimal pitch already set). The simple
    # mean of 4 conditions overweights off-design improvements relative to their fuel impact.
    if mission_summary is not None and mission_summary.total_fuel_baseline_kg > 0:
        mw_reduction = mission_summary.total_fuel_saving_pct
        lines.append(
            f"  Mission-weighted reduction : {mw_reduction:.2f}%  "
            f"(weighted by fuel burn per phase — physically correct metric)"
        )
        lines.append("")
        lines.append(
            "  Note: The mission-weighted figure differs from the simple mean because")
        lines.append(
            f"  cruise dominates ({mission_summary.phase_results[2].duration_min:.0f} of "
            f"{sum(p.duration_min for p in mission_summary.phase_results):.0f} min) "
            "and VPF gives 0% gain at cruise by definition (design point = optimal pitch).")
    else:
        lines.append("")

    lines.append("")
    lines.append("  Literature range for VPF (Cumpsty 2004 p.280): 1–6%")
    lines.append(
        f"  → Peak SFC reduction within range: {'YES' if 1.0 <= max_reduction <= 6.0 else 'CHECK'}"
    )
    lines.append("")

    if mission_summary is not None and mission_summary.total_fuel_baseline_kg > 0:
        lines.append("-" * 70)
        lines.append("6. MISSION — TOTAL FUEL SAVING")
        lines.append("-" * 70)
        lines.append("")
        for p in mission_summary.phase_results:
            lines.append(
                f"  {p.phase:<10}  dur={p.duration_min:.0f}min  "
                f"saving={p.fuel_saving_kg:.1f}kg  CO₂={p.co2_saving_kg:.1f}kg"
            )
        lines.append(
            f"  TOTAL: saving={mission_summary.total_fuel_saving_kg:.1f}kg "
            f"({mission_summary.total_fuel_saving_pct:.2f}%)"
        )
        lines.append("")

    lines.append("=" * 70)
    return "\n".join(lines)
