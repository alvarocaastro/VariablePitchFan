"""YAML configuration loader with a module-level cache."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import yaml

from vpf_analysis import settings as base_config
from vpf_analysis.settings import _isa_atmosphere

_CONFIG_CACHE: dict[str, Any] | None = None


def load_config(config_path: Path | None = None) -> dict[str, Any]:
    """Load and cache analysis_config.yaml. Subsequent calls return the cache."""
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE
    if config_path is None:
        config_path = base_config.ROOT_DIR / "config" / "analysis_config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as f:
        _CONFIG_CACHE = yaml.safe_load(f)
    return _CONFIG_CACHE


# ── Non-dimensional fan geometry accessors ────────────────────────────────────

def get_M_tip_design() -> dict[str, float]:
    """Tip Mach number U_tip/a per flight condition."""
    return {k: float(v) for k, v in load_config()["fan_geometry"]["M_tip_design"].items()}


def get_phi_design() -> dict[str, float]:
    """Flow coefficient φ = Va/(ω·r_tip) per flight condition."""
    return {k: float(v) for k, v in load_config()["fan_geometry"]["phi_design"].items()}


def get_r_rel() -> dict[str, float]:
    """Non-dimensional blade radii r/r_tip per section."""
    return {k: float(v) for k, v in load_config()["fan_geometry"]["r_rel"].items()}


def get_r_tip_m() -> float:
    """Tip radius [m] — sole dimensional anchor."""
    return float(load_config()["fan_geometry"]["r_tip_m"])


def get_hub_to_tip_ratio() -> float:
    """Hub-to-tip radius ratio r_hub/r_tip."""
    return float(load_config()["fan_geometry"]["hub_to_tip_ratio"])


def get_altitude_m() -> dict[str, float]:
    """ISA pressure altitude [m] per flight condition."""
    return {k: float(v) for k, v in load_config()["fan_geometry"]["altitude_m"].items()}


# ── Derived dimensional quantities (computed at runtime) ─────────────────────

def get_radii() -> dict[str, float]:
    """Absolute blade radii [m] per section: r_rel × r_tip_m."""
    r_tip = get_r_tip_m()
    return {sec: rr * r_tip for sec, rr in get_r_rel().items()}


def get_omega_map(gear_ratio: float = 1.0) -> dict[str, float]:
    """Angular velocity [rad/s] per condition: M_tip × a(h) / r_tip / gear_ratio."""
    r_tip = get_r_tip_m()
    alt = get_altitude_m()
    return {
        cond: M * _isa_atmosphere(alt[cond])[0] / r_tip / gear_ratio
        for cond, M in get_M_tip_design().items()
    }


def get_va_map(gear_ratio: float = 1.0) -> dict[str, float]:
    """Axial fan-face velocity Va [m/s] per condition: phi × omega × r_tip."""
    r_tip = get_r_tip_m()
    omega = get_omega_map(gear_ratio)
    return {
        cond: phi * omega[cond] * r_tip
        for cond, phi in get_phi_design().items()
    }


def get_reynolds_map() -> dict[str, dict[str, float]]:
    """Reynolds numbers Re = rho·W_rel·c/mu per (flight condition, blade section).

    chord c [m] = sigma · 2π · r / Z  from blade_geometry.solidity.
    """
    bg = get_blade_geometry()
    num_blades = bg["num_blades"]
    solidity = bg["solidity"]
    alt = get_altitude_m()
    radii = get_radii()
    omega = get_omega_map()
    va = get_va_map()
    result: dict[str, dict[str, float]] = {}
    for cond, h in alt.items():
        _, rho, mu = _isa_atmosphere(h)
        result[cond] = {}
        for sec, r_sec in radii.items():
            U_sec = omega[cond] * r_sec
            W_rel = math.sqrt(va[cond] ** 2 + U_sec ** 2)
            chord = solidity.get(sec, 1.0) * 2.0 * math.pi * r_sec / num_blades
            result[cond][sec] = rho * W_rel * chord / mu
    return result


# ── Standard accessors (unchanged) ───────────────────────────────────────────

def get_ncrit_table() -> dict[str, float]:
    return {k: float(v) for k, v in load_config()["ncrit"].items()}


def get_target_mach() -> dict[str, float]:
    return {k: float(v) for k, v in load_config()["target_mach"].items()}


def get_target_mach_per_section() -> dict[str, dict[str, float]]:
    """Per-section relative Mach: {condition: {section: M_rel}}.

    Sections with M_rel >= 1.0 are supersonic and must be excluded from
    XFOIL/KT analysis. Returns empty dict if key absent in YAML.
    """
    raw = load_config().get("target_mach_per_section", {})
    return {
        cond: {sec: float(m) for sec, m in sections.items()}
        for cond, sections in raw.items()
    }


def get_alpha_range() -> dict[str, float]:
    return {k: float(v) for k, v in load_config()["alpha"].items()}


def get_selection_alpha_range() -> dict[str, float]:
    sel = load_config()["selection"]
    return {
        "min":  float(sel.get("alpha_min",  -2.0)),
        "max":  float(sel.get("alpha_max",  15.0)),
        "step": float(sel.get("alpha_step",  0.15)),
    }


def get_selection_conditions() -> list[dict]:
    """Return raw selection condition specs from the YAML (label, flight_condition, section, weight)."""
    return list(load_config()["selection"].get("conditions", []))


def get_plot_settings() -> dict[str, Any]:
    return load_config()["plotting"]


def get_reference_mach() -> float:
    return float(load_config()["reference_mach"])


def get_flight_conditions() -> list[str]:
    return load_config()["flight_conditions"]


def get_blade_sections() -> list[str]:
    return load_config()["blade_sections"]


def get_airfoil_thickness_ratio() -> float:
    return float(load_config()["airfoil_geometry"]["thickness_ratio"])


def get_korn_kappa() -> float:
    return float(load_config()["airfoil_geometry"]["korn_kappa"])


def get_blade_geometry() -> dict[str, Any]:
    """Blade cascade geometry: num_blades, solidity per section, theta_camber_deg."""
    bg = load_config()["blade_geometry"]
    return {
        "num_blades": int(bg["num_blades"]),
        "solidity": {k: float(v) for k, v in bg["solidity"].items()},
        "theta_camber_deg": float(bg["theta_camber_deg"]),
    }


def get_gear_ratio() -> float:
    """Shaft-to-fan speed ratio from engine_parameters.yaml (1.0 = direct-drive)."""
    engine_cfg_path = base_config.ROOT_DIR / "config" / "engine_parameters.yaml"
    with engine_cfg_path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return float(cfg.get("gear_ratio", 1.0))


def get_fleet_co2_config() -> dict[str, Any]:
    """Fleet CO₂ annualisation config from engine_parameters.yaml."""
    engine_cfg_path = base_config.ROOT_DIR / "config" / "engine_parameters.yaml"
    with engine_cfg_path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    fc = cfg.get("fleet_co2", {})
    return {
        "aircraft_count": int(fc.get("aircraft_count", 205)),
        "flights_per_day_per_aircraft": int(fc.get("flights_per_day_per_aircraft", 2)),
    }


def get_mission_profile() -> dict[str, Any]:
    """Mission profile from engine_parameters.yaml: phases, design_thrust_kN, fuel_price."""
    engine_cfg_path = base_config.ROOT_DIR / "config" / "engine_parameters.yaml"
    with engine_cfg_path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    mission = cfg.get("mission", {})
    return {
        "phases": {
            k: {"duration_min": float(v["duration_min"]), "thrust_fraction": float(v["thrust_fraction"])}
            for k, v in mission.get("phases", {}).items()
        },
        "design_thrust_kN": float(mission.get("design_thrust_kN", 105.0)),
        "fuel_price_usd_per_kg": float(mission.get("fuel_price_usd_per_kg", 0.90)),
    }


def clear_cache() -> None:
    """Invalidate the config cache (useful in tests)."""
    global _CONFIG_CACHE
    _CONFIG_CACHE = None
