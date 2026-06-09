"""Paths, XFOIL discovery, airfoil catalogue, and settings loader. Use get_settings() for access."""

from __future__ import annotations

import math
import os
import shutil
from pathlib import Path
from typing import Any, Final, TypedDict

import yaml

from vpf_analysis.config.domain import (  # noqa: F401  (re-exported for backwards compat)
    AirfoilGeometry,
    BladeGeometry,
    FanGeometry,
    PhysicsConstants,
    PipelineSettings,
    ResolvedSelectionCondition,
    XfoilSettings,
)


# Path constants

ROOT_DIR: Final[Path] = Path(__file__).resolve().parents[2]
AIRFOIL_DATA_DIR: Final[Path] = ROOT_DIR / "data" / "airfoils"
RESULTS_DIR: Final[Path] = ROOT_DIR / "results"

STAGE_DIR_NAMES: Final[dict[int, str]] = {
    1: "stage1_airfoil_selection",
    2: "stage2_xfoil_simulations",
    3: "stage3_compressibility_correction",
    4: "stage4_performance_metrics",
    5: "stage5_pitch_kinematics",
    6: "stage6_reverse_thrust",
    7: "stage7_sfc_analysis",
}


def get_stage_dir(stage_num: int) -> Path:
    """Return the canonical results directory for a numbered stage."""
    try:
        return RESULTS_DIR / STAGE_DIR_NAMES[stage_num]
    except KeyError as exc:
        raise ValueError(f"Unknown stage number: {stage_num}") from exc



# XFOIL executable discovery

def _normalize_xfoil_candidate(raw_path: str | Path) -> Path:
    candidate = Path(raw_path).expanduser()
    executable_name = "xfoil.exe" if os.name == "nt" else "xfoil"
    if candidate.name.lower() not in {"xfoil", "xfoil.exe"}:
        return candidate / executable_name
    return candidate


def _build_xfoil_search_paths() -> tuple[Path, ...]:
    raw_candidates: list[Path] = []
    env_path = os.getenv("XFOIL_EXE") or os.getenv("XFOIL_EXECUTABLE")
    if env_path:
        raw_candidates.append(_normalize_xfoil_candidate(env_path))
    raw_candidates.extend([
        _normalize_xfoil_candidate(ROOT_DIR.parent / "XFOIL6.99"),
        _normalize_xfoil_candidate(ROOT_DIR / "XFOIL6.99"),
        _normalize_xfoil_candidate(Path.home() / "Downloads" / "XFOIL6.99"),
    ])
    which_result = shutil.which("xfoil")
    if which_result:
        raw_candidates.append(Path(which_result))
    seen: set[str] = set()
    unique: list[Path] = []
    for c in raw_candidates:
        key = str(c).lower()
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return tuple(unique)


def _resolve_xfoil_executable() -> Path:
    for candidate in XFOIL_SEARCH_PATHS:
        if candidate.is_file():
            return candidate
    return XFOIL_SEARCH_PATHS[0]


XFOIL_SEARCH_PATHS: Final[tuple[Path, ...]] = _build_xfoil_search_paths()
XFOIL_EXECUTABLE: Final[Path] = _resolve_xfoil_executable()

MACH_DEFAULT: Final[float] = 0.2
N_CRIT_DEFAULT: Final[float] = 9.0


# Airfoil definitions


class AirfoilSpec(TypedDict):
    """Specification of a single airfoil for the analysis."""
    name: str
    dat_file: str
    family: str
    comment: str


def _load_airfoils() -> list[AirfoilSpec]:
    path = ROOT_DIR / "config" / "airfoils.yaml"
    with path.open("r", encoding="utf-8") as f:
        data: dict = yaml.safe_load(f)
    return data["airfoils"]


AIRFOILS: Final[list[AirfoilSpec]] = _load_airfoils()


# Settings cache

_SETTINGS_CACHE: PipelineSettings | None = None


def get_settings(
    analysis_config_path: Path | None = None,
) -> PipelineSettings:
    """Return cached PipelineSettings. First call loads YAML; subsequent calls are instant."""
    global _SETTINGS_CACHE
    if _SETTINGS_CACHE is not None:
        return _SETTINGS_CACHE
    _SETTINGS_CACHE = _load_settings(analysis_config_path)
    return _SETTINGS_CACHE


def clear_settings_cache() -> None:
    """Invalidate the settings cache (useful in tests)."""
    global _SETTINGS_CACHE
    _SETTINGS_CACHE = None


# Ref: ICAO Standard Atmosphere (Doc 7488 / ISO 2533:1975), Table 1 — sea-level values
_ISA_T0: Final[float] = 288.15     # K      — Ref: ICAO Doc 7488, Table 1
_ISA_P0: Final[float] = 101325.0   # Pa     — Ref: ICAO Doc 7488, Table 1
_ISA_R:  Final[float] = 287.05     # J/(kg·K) — Ref: NACA TN-1135 (1953), Appendix A
_ISA_G:  Final[float] = 9.80665    # m/s²   — Ref: ICAO Doc 7488, Table 1
_ISA_GAMMA: Final[float] = 1.4     # —       Ref: NACA TN-1135 (1953), §3 (diatomic gas, n=5)
_ISA_LAPSE: Final[float] = 0.0065  # K/m    — Ref: ICAO Doc 7488, Table 4 (troposphere lapse rate)
_ISA_MU0:   Final[float] = 1.7894e-5  # Pa·s at T0 — Ref: ICAO Doc 7488, Table 1


def _isa_atmosphere(altitude_m: float) -> tuple[float, float, float]:
    """Return (a [m/s], rho [kg/m³], mu [Pa·s]) for ISA standard troposphere."""
    h = max(0.0, min(altitude_m, 11000.0))
    T = _ISA_T0 - _ISA_LAPSE * h
    P = _ISA_P0 * (T / _ISA_T0) ** (_ISA_G / (_ISA_R * _ISA_LAPSE))
    rho = P / (_ISA_R * T)
    mu = _ISA_MU0 * (T / _ISA_T0) ** 0.7
    a = math.sqrt(_ISA_GAMMA * _ISA_R * T)  # Ref: NACA TN-1135 (1953), eq. 29b — a = √(γRT)
    return a, rho, mu


def _load_settings(config_path: Path | None) -> PipelineSettings:
    """Load and validate parameters from YAML files."""
    if config_path is None:
        config_path = ROOT_DIR / "config" / "analysis_config.yaml"

    if not config_path.exists():
        raise FileNotFoundError(
            f"Configuration file not found: {config_path}"
        )

    with config_path.open("r", encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f)

    flight_conditions: list[str] = raw["flight_conditions"]
    blade_sections: list[str] = raw["blade_sections"]

    ncrit_table = {k: float(v) for k, v in raw["ncrit"].items()}
    target_mach = {k: float(v) for k, v in raw["target_mach"].items()}
    target_mach_per_section: dict[str, dict[str, float]] = {
        cond: {sec: float(m) for sec, m in sections.items()}
        for cond, sections in raw.get("target_mach_per_section", {}).items()
    }

    alpha_cfg = raw["alpha"]
    sel = raw.get("selection", {})
    sel_cfg = {
        "min":  sel.get("alpha_min",  -2.0),
        "max":  sel.get("alpha_max",  15.0),
        "step": sel.get("alpha_step",  0.15),
    }

    # Fan geometry — non-dimensional parameterisation
    fg = raw["fan_geometry"]
    M_tip = {k: float(v) for k, v in fg["M_tip_design"].items()}
    phi   = {k: float(v) for k, v in fg["phi_design"].items()}
    r_rel = {k: float(v) for k, v in fg["r_rel"].items()}
    r_tip_m = float(fg["r_tip_m"])
    hub_to_tip_ratio = float(fg["hub_to_tip_ratio"])
    alt_m = {k: float(v) for k, v in fg["altitude_m"].items()}

    # Derive dimensional kinematics
    omega_rad_s: dict[str, float] = {}
    va_m_s: dict[str, float] = {}
    for cond in flight_conditions:
        a_isa, _, _ = _isa_atmosphere(alt_m[cond])
        omega_rad_s[cond] = M_tip[cond] * a_isa / r_tip_m
        va_m_s[cond] = phi[cond] * omega_rad_s[cond] * r_tip_m
    radii_m: dict[str, float] = {sec: r_rel[sec] * r_tip_m for sec in blade_sections}

    fan = FanGeometry(
        M_tip=M_tip,
        phi_tip=phi,
        r_rel=r_rel,
        r_tip_m=r_tip_m,
        hub_to_tip_ratio=hub_to_tip_ratio,
        altitude_m=alt_m,
        omega_rad_s=omega_rad_s,
        radii_m=radii_m,
        axial_velocity_m_s=va_m_s,
    )

    # Blade geometry (needed to compute chord for Re)
    bg = raw["blade_geometry"]
    num_blades = int(bg["num_blades"])
    solidity = {k: float(v) for k, v in bg["solidity"].items()}

    # Reynolds table — derived from ISA + blade chord
    # c [m] = sigma * 2*pi*r / Z;  Re = rho * W_rel * c / mu
    reynolds_table: dict[str, dict[str, float]] = {}
    for cond in flight_conditions:
        a_isa, rho, mu = _isa_atmosphere(alt_m[cond])
        reynolds_table[cond] = {}
        for sec in blade_sections:
            r_sec = radii_m[sec]
            U_sec = omega_rad_s[cond] * r_sec
            W_rel = math.sqrt(va_m_s[cond] ** 2 + U_sec ** 2)
            chord = solidity.get(sec, 1.0) * 2.0 * math.pi * r_sec / num_blades
            reynolds_table[cond][sec] = rho * W_rel * chord / mu

    blade = BladeGeometry(
        num_blades=num_blades,
        solidity=solidity,
        theta_camber_deg=float(bg["theta_camber_deg"]),
    )

    ag = raw.get("airfoil_geometry", {})
    airfoil_geom = AirfoilGeometry(
        thickness_ratio=float(ag.get("thickness_ratio", 0.10)),
        korn_kappa=float(ag.get("korn_kappa", 0.87)),
    )

    # xfoil settings (optional section, falls back to hardcoded defaults)
    xf_raw = raw.get("xfoil", {})
    import dataclasses as _dc
    xfoil_settings = _dc.replace(
        XfoilSettings(),
        **{k: v for k, v in {
            "ITER":                 xf_raw.get("iter"),
            "TIMEOUT_SELECTION_S":  xf_raw.get("timeout_selection_s"),
            "TIMEOUT_FINAL_S":      xf_raw.get("timeout_final_s"),
            "MAX_RETRIES":          xf_raw.get("max_retries"),
            "RETRY_WAIT_S":         xf_raw.get("retry_wait_s"),
        }.items() if v is not None}
    )

    # Resolve selection conditions: look up Re and Ncrit from the tables already parsed.
    _raw_conditions = sel.get("conditions", [])
    if not _raw_conditions:
        # Backward-compat fallback: single condition using legacy keys.
        _raw_conditions = [{
            "label": "selection",
            "flight_condition": "cruise",
            "section": "mid_span",
            "weight": 1.0,
        }]
    for _c in _raw_conditions:
        _fc, _sec = _c["flight_condition"], _c["section"]
        if _fc not in reynolds_table:
            raise ValueError(
                f"selection_conditions: flight_condition '{_fc}' not in reynolds_table. "
                f"Valid: {list(reynolds_table)}"
            )
        if _sec not in reynolds_table[_fc]:
            raise ValueError(
                f"selection_conditions: section '{_sec}' not found for '{_fc}' in reynolds_table. "
                f"Valid: {list(reynolds_table[_fc])}"
            )
        if _fc not in ncrit_table:
            raise ValueError(
                f"selection_conditions: flight_condition '{_fc}' not in ncrit_table. "
                f"Valid: {list(ncrit_table)}"
            )
    _weight_sum = sum(float(c.get("weight", 1.0)) for c in _raw_conditions)
    selection_conditions = [
        ResolvedSelectionCondition(
            label=c["label"],
            flight_condition=c["flight_condition"],
            section=c["section"],
            reynolds=reynolds_table[c["flight_condition"]][c["section"]],
            ncrit=ncrit_table[c["flight_condition"]],
            weight=float(c.get("weight", 1.0)) / _weight_sum,
        )
        for c in _raw_conditions
    ]

    cruise_alpha_min_raw = raw.get("cruise_alpha_min", {})
    cruise_alpha_min = {k: float(v) for k, v in cruise_alpha_min_raw.items()}

    xfoil_cache = bool(raw.get("xfoil_cache", False))

    return PipelineSettings(
        physics=PhysicsConstants(),
        xfoil=xfoil_settings,
        flight_conditions=flight_conditions,
        blade_sections=blade_sections,
        reynolds_table=reynolds_table,
        ncrit_table=ncrit_table,
        target_mach=target_mach,
        target_mach_per_section=target_mach_per_section,
        reference_mach=float(raw.get("reference_mach", 0.2)),
        alpha_min=float(alpha_cfg["min"]),
        alpha_max=float(alpha_cfg["max"]),
        alpha_step=float(alpha_cfg["step"]),
        selection_alpha_min=float(sel_cfg["min"]),
        selection_alpha_max=float(sel_cfg["max"]),
        selection_alpha_step=float(sel_cfg["step"]),
        selection_conditions=selection_conditions,
        fan=fan,
        blade=blade,
        airfoil_geometry=airfoil_geom,
        cruise_alpha_min=cruise_alpha_min,
        xfoil_cache=xfoil_cache,
        results_dir=RESULTS_DIR,
    )
