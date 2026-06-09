"""Reference engine parameters for turbofan SFC analysis."""

from __future__ import annotations

import numpy as np

# GE9X-105B1A (Boeing 777X) — public data
GE9X_PARAMS: dict = {
    "name": "GE9X-105B1A",
    "BPR": 15.0,             # UHBPR target (enabled by VPF)
    "OPR": 60.0,
    "T4_cruise": 1450.0,    # K — TET in cruise
    "T4_takeoff": 1800.0,   # K — TET at takeoff
    "eta_fan": 0.93,
    "eta_comp": 0.90,
    "eta_turb": 0.92,
    "eta_nozzle": 0.98,
    "eta_combustor": 0.999,
    "LHV": 43.2e6,          # J/kg  (Jet-A)
    "cp_air": 1005.0,       # J/kg·K
    "cp_gas": 1148.0,       # J/kg·K
    "gamma_c": 1.4,
    "gamma_t": 1.33,
    "SFC_ref_cruise": 0.49,  # lb/lbf·h — public GE9X value
    "altitude_cruise_ft": 35000.0,
    "Mach_cruise": 0.85,
    "FPR": 1.30,             # Fan Pressure Ratio — reduced to 1.30 for UHBPR cycle
}

# Reference engines used for interpolated estimates
_REFERENCE_ENGINES = [
    {"name": "GE90-115B",   "BPR": 8.7,  "OPR": 42.0, "SFC_cruise": 0.520,
     "eta_fan": 0.92, "eta_turb": 0.91, "eta_comp": 0.89},
    {"name": "Trent XWB-97","BPR": 9.3,  "OPR": 52.0, "SFC_cruise": 0.478,
     "eta_fan": 0.93, "eta_turb": 0.92, "eta_comp": 0.90},
    {"name": "PW1100G",     "BPR": 12.5, "OPR": 50.0, "SFC_cruise": 0.463,
     "eta_fan": 0.94, "eta_turb": 0.91, "eta_comp": 0.90},
]


def estimate_GE9X_from_similar(engines: list[dict] | None = None) -> dict:
    """Weighted interpolation by OPR proximity to estimate GE9X-like parameters."""
    if engines is None:
        engines = _REFERENCE_ENGINES
    OPR_target = 60.0
    weights = np.array([1.0 / abs(e["OPR"] - OPR_target) for e in engines])
    weights /= weights.sum()
    estimated: dict = {}
    for key in ["BPR", "SFC_cruise", "eta_fan", "eta_turb", "eta_comp"]:
        estimated[key] = float(sum(w * e[key] for w, e in zip(weights, engines)))
    estimated["OPR"] = OPR_target
    return estimated


# SI ↔ Anglo conversion helpers
def sfc_lbh_to_si(sfc_lbh: float) -> float:
    """Convert SFC from lb/lbf·h to kg/N·s."""
    return sfc_lbh / (3600.0 * 2.20462 / 0.224809)


def sfc_si_to_lbh(sfc_si: float) -> float:
    """Convert SFC from kg/N·s to lb/lbf·h."""
    return sfc_si * (3600.0 * 2.20462 / 0.224809)
