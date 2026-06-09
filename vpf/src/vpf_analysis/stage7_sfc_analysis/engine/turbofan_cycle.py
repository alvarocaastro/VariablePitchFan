"""Two-stream turbofan thermodynamic cycle model (GE9X reference).

Implements the 10-step cycle: intake → fan → compressor → combustion →
HPT → LPT → nozzles → net specific thrust → SFC.

All computations in SI units internally. Outputs include SFC in both kg/N·s
and lb/lbf·h for direct comparison with public engine data.
"""

from __future__ import annotations

import math


def _isa_conditions(altitude_ft: float) -> tuple[float, float]:  # (T0 [K], P0 [Pa])
    """Return (T0_amb [K], P0_amb [Pa]) for ISA at given altitude in feet."""
    h_m = altitude_ft * 0.3048
    if h_m <= 11_000:
        T = 288.15 - 0.0065 * h_m
        P = 101325.0 * (T / 288.15) ** 5.2561
    else:
        T = 216.65
        P = 22632.1 * math.exp(-0.0001577 * (h_m - 11_000))
    return T, P


def compute_turbofan_sfc(
    params: dict,
    phase: str = "cruise",
    FPR: float | None = None,
) -> dict[str, float | str]:
    """Compute SFC for a two-stream turbofan using a simplified thermodynamic cycle.

    Parameters
    ----------
    params : dict
        Engine parameters dict (e.g. GE9X_PARAMS from engine_data.py).
    phase : str
        "cruise" or "takeoff".
    FPR : float, optional
        Fan Pressure Ratio override; defaults to params.get("FPR", 1.30).

    Returns
    -------
    dict with keys:
        SFC_si    [kg/N·s]
        SFC_lbh   [lb/lbf·h]
        F_sp      [N per kg/s core]
        f         fuel-to-air ratio [-]
        T02, T023, T03, T04, T045, T05  [K]  — cycle temperatures
        V_jet_hot, V_jet_cold  [m/s]
        validation_delta_pct   % diff vs SFC_ref_cruise (cruise only)
    """
    BPR          = float(params["BPR"])
    OPR          = float(params["OPR"])
    eta_fan      = float(params["eta_fan"])
    eta_comp     = float(params["eta_comp"])
    eta_turb     = float(params["eta_turb"])
    eta_nozzle   = float(params["eta_nozzle"])
    eta_comb     = float(params["eta_combustor"])
    LHV          = float(params["LHV"])
    cp_air       = float(params["cp_air"])
    cp_gas       = float(params["cp_gas"])
    gamma_c      = float(params["gamma_c"])
    gamma_t      = float(params["gamma_t"])
    T4_key       = "T4_cruise" if phase == "cruise" else "T4_takeoff"
    T4           = float(params[T4_key])
    FPR          = float(FPR if FPR is not None else params.get("FPR", 1.30))

    if phase == "cruise":
        altitude_ft = float(params.get("altitude_cruise_ft", 35000.0))
        Mach        = float(params.get("Mach_cruise", 0.85))
    else:
        altitude_ft = 0.0
        Mach        = 0.25  # representative takeoff speed

    T_static, P_static = _isa_conditions(altitude_ft)
    R = 287.05  # J/kg·K

    # ── 1. Intake ─────────────────────────────────────────────────────────
    T02 = T_static * (1.0 + (gamma_c - 1.0) / 2.0 * Mach**2)
    P02 = P_static * (T02 / T_static) ** (gamma_c / (gamma_c - 1.0))
    V0  = Mach * math.sqrt(gamma_c * R * T_static)

    # ── 2. Fan (isentropic + efficiency) ──────────────────────────────────
    T023 = T02 * (1.0 + (FPR**((gamma_c - 1.0) / gamma_c) - 1.0) / eta_fan)
    P023 = P02 * FPR

    # ── 3. Core compressor ────────────────────────────────────────────────
    CPR  = OPR / FPR   # core pressure ratio
    T03  = T023 * (1.0 + (CPR**((gamma_c - 1.0) / gamma_c) - 1.0) / eta_comp)
    P03  = P023 * CPR

    # ── 4. Combustion ─────────────────────────────────────────────────────
    f = cp_gas * (T4 - T03) / (eta_comb * LHV - cp_gas * T4)

    # ── 5. HPT — drives core compressor ──────────────────────────────────
    W_comp = cp_air * (T03 - T023)
    T045   = T4 - W_comp / (cp_gas * eta_turb)
    P04    = P03   # negligible combustor pressure drop
    exp_t  = gamma_t / (gamma_t - 1.0)
    P045   = P04 * (T045 / T4) ** exp_t

    # ── 6. LPT — drives fan ───────────────────────────────────────────────
    W_fan  = (1.0 + BPR) * cp_air * (T023 - T02)
    T05    = T045 - W_fan / (cp_gas * eta_turb)
    P05    = P045 * (T05 / T045) ** exp_t

    # ── 7. Hot nozzle ─────────────────────────────────────────────────────
    P_amb  = P_static
    arg_h  = max(1.0 - (P_amb / P05) ** ((gamma_t - 1.0) / gamma_t), 0.0)
    V_jet_hot  = math.sqrt(2.0 * eta_nozzle * cp_gas * T05 * arg_h)

    # ── 8. Cold (bypass) nozzle ───────────────────────────────────────────
    arg_c  = max(1.0 - (P_amb / P023) ** ((gamma_c - 1.0) / gamma_c), 0.0)
    V_jet_cold = math.sqrt(2.0 * eta_nozzle * cp_air * T023 * arg_c)

    # ── 9. Net specific thrust (per unit core mass flow) ─────────────────
    F_sp = (1.0 + f) * V_jet_hot - V0 + BPR * (V_jet_cold - V0)

    # ── 10. SFC ───────────────────────────────────────────────────────────
    SFC_si  = f / F_sp if F_sp > 0.0 else float("inf")
    SFC_lbh = SFC_si * (3600.0 * 2.20462 / 0.224809)

    validation_delta_pct = float("nan")
    if phase == "cruise" and "SFC_ref_cruise" in params:
        ref = float(params["SFC_ref_cruise"])
        validation_delta_pct = (SFC_lbh - ref) / ref * 100.0

    return {
        "phase":       phase,
        "SFC_si":      SFC_si,
        "SFC_lbh":     SFC_lbh,
        "F_sp":        F_sp,
        "f":           f,
        "T02":  T02,  "T023": T023, "T03": T03,
        "T04":  T4,   "T045": T045, "T05": T05,
        "V_jet_hot":   V_jet_hot,
        "V_jet_cold":  V_jet_cold,
        "validation_delta_pct": validation_delta_pct,
    }
