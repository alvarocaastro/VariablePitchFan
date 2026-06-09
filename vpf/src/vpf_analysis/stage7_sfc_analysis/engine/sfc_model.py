"""SFC improvement model: Cl/Cd efficiency gain → SFC reduction via fan efficiency chain.

Physical chain (consistent with sfc_core.compute_sfc_improvement):
    ε   = ClCd_new / ClCd_ref
    Δη  = max(0, min((ε − 1) · τ, ETA_FAN_DELTA_CAP))
    SFC_new = SFC_ref / (1 + k_BPR · Δη / η_fan)

Thrust is fixed by aircraft drag (independent of blade Cl/Cd), so
SFC_improvement_pct = fuel_saving_pct (same quantity, thrust unchanged).

Previous model assumed F_required ∝ 1/Cl/Cd (thrust-demand), which conflates blade
aerodynamic efficiency with thrust requirement — physically incorrect at cruise.

Reference: Cumpsty (2004) ch. 8; Saravanamuttoo et al. (2017) §5.14.
"""

from __future__ import annotations

from vpf_analysis.stage7_sfc_analysis.core.domain.sfc_parameters import (
    EPSILON_CAP,
    ETA_FAN_DELTA_CAP,
)

_K_BPR_DEFAULT: float = 0.9375   # BPR=15: k = 15/16
_ETA_FAN_DEFAULT: float = 0.90


def compute_sfc_improvement(
    ClCd_ref: float,
    ClCd_new: float,
    SFC_design: float,
    tau: float = 0.08,
    eta_fan_base: float = _ETA_FAN_DEFAULT,
    k_bpr: float = _K_BPR_DEFAULT,
    epsilon_cap: float = EPSILON_CAP,
    eta_fan_delta_cap: float = ETA_FAN_DELTA_CAP,
    k_throttle: float = 0.08,  # unused — kept for call-site compatibility
) -> dict[str, float]:
    """Estimate SFC improvement when fan blade Cl/Cd improves from ref to new.

    Parameters
    ----------
    ClCd_ref : float
        Reference Cl/Cd (cruise fixed-pitch operating point).
    ClCd_new : float
        Achieved Cl/Cd (VPF-optimised operating point).
    SFC_design : float
        Engine SFC at design (cruise) point [kg/N·s].
    tau : float
        Efficiency transfer coefficient τ (2D blade Cl/Cd → 3D fan η).
        Calibrated range: 0.3–0.8; default 0.5 (Cumpsty, 2004 p. 280).
    """
    if ClCd_ref <= 0:
        raise ValueError("ClCd_ref must be positive")

    epsilon = ClCd_new / ClCd_ref
    epsilon_eff = min(epsilon, epsilon_cap)
    delta_eta_fan = max(0.0, min((epsilon_eff - 1.0) * tau, eta_fan_delta_cap))

    sensitivity = k_bpr * delta_eta_fan / eta_fan_base
    SFC_new = SFC_design / (1.0 + sensitivity)

    SFC_improvement_pct = (1.0 - SFC_new / SFC_design) * 100.0

    return {
        "ClCd_ref":            ClCd_ref,
        "ClCd_new":            ClCd_new,
        "F_ratio":             1.0,
        "epsilon":             epsilon,
        "delta_eta_fan":       delta_eta_fan,
        "SFC_design_kgNs":     SFC_design,
        "SFC_new_kgNs":        SFC_new,
        "SFC_improvement_pct": SFC_improvement_pct,
        "fuel_saving_pct":     SFC_improvement_pct,
        "delta_SFC_kgNs":      SFC_new - SFC_design,
    }
