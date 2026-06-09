"""
run_reverse_thrust.py
---------------------
Stage 6: VPF Reverse Thrust — mechanism weight analysis.

The variable-pitch fan reverses thrust by rotating blades to negative pitch
angles, redirecting fan airflow to produce braking force without cascade
blocker doors.

Analysis performed:
  1. Mechanism weight — quantifies VPF actuator vs conventional cascade reverser
     weight and the resulting cruise SFC impact (Breguet first-order estimate).

Inputs:
    config/engine_parameters.yaml  (reverse_thrust section)

Outputs (results/stage6_reverse_thrust/):
    tables/mechanism_weight.csv
    figures/mechanism_weight_comparison.png
    reverse_thrust_summary.txt
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from vpf_analysis import settings as base_config
from vpf_analysis.stage6_reverse_thrust.adapters.filesystem.results_writer import (
    ReverseResultsWriter,
)
from vpf_analysis.stage6_reverse_thrust.core.domain.reverse_thrust_result import (
    MechanismWeightResult,
)
from vpf_analysis.stage6_reverse_thrust.reverse_thrust_core import (
    compute_mechanism_weight,
)

LOGGER = logging.getLogger(__name__)


def _load_reverse_config() -> dict:
    cfg_path = base_config.ROOT_DIR / "config" / "engine_parameters.yaml"
    with cfg_path.open() as f:
        cfg = yaml.safe_load(f)
    if "reverse_thrust" not in cfg:
        raise KeyError("engine_parameters.yaml missing 'reverse_thrust' section")
    return cfg


def run_reverse_thrust() -> None:
    """Execute Stage 6: mechanism weight analysis."""
    LOGGER.info("=" * 60)
    LOGGER.info("Stage 6: VPF Reverse Thrust — Weight Analysis")
    LOGGER.info("=" * 60)

    cfg     = _load_reverse_config()
    rt_cfg  = cfg["reverse_thrust"]
    mission = cfg.get("mission", {})
    phases  = mission.get("phases", {})

    out_dir = base_config.get_stage_dir(6)
    out_dir.mkdir(parents=True, exist_ok=True)

    design_thrust_kN       = float(mission.get("design_thrust_kN", 467.0))
    cruise_thrust_fraction = float(phases.get("cruise", {}).get("thrust_fraction", 0.25))

    # ── Mechanism weight ─────────────────────────────────────────────────────
    mechanism_weight = compute_mechanism_weight(
        engine_dry_weight_kg=float(rt_cfg["engine_dry_weight_kg"]),
        mechanism_weight_fraction=float(rt_cfg["mechanism_weight_fraction"]),
        conventional_reverser_fraction=float(rt_cfg["conventional_reverser_fraction"]),
        design_thrust_kN=design_thrust_kN,
        cruise_thrust_fraction=cruise_thrust_fraction,
        aircraft_L_D=float(rt_cfg["aircraft_L_D"]),
        d_scale_factor=float(rt_cfg.get("fan_diameter_ratio", 1.0)) ** 2.5,
    )

    LOGGER.info(
        "Mechanism weight: %.0f kg | saving vs cascade: %.0f kg | "
        "SFC penalty: +%.3f%% | SFC benefit vs cascade: -%.3f%%",
        mechanism_weight.mechanism_weight_kg,
        mechanism_weight.weight_saving_vs_conventional_kg,
        mechanism_weight.sfc_cruise_penalty_pct,
        mechanism_weight.sfc_benefit_vs_conventional_pct,
    )

    # ── Write outputs ────────────────────────────────────────────────────────
    writer = ReverseResultsWriter(out_dir)
    writer.write_mechanism_weight(mechanism_weight)
    writer.write_figures(mechanism_weight)

    _write_summary(out_dir, mechanism_weight)
    LOGGER.info("Stage 6 complete. Outputs: %s", out_dir)


def _write_summary(out_dir: Path, mw: MechanismWeightResult) -> None:
    lines = [
        "Stage 6 — VPF Reverse Thrust: Mechanism Weight Analysis",
        "=" * 58,
        "",
        "CONCEPT",
        "  Variable-pitch fans reverse thrust by rotating blades to negative",
        "  pitch angles during landing rollout. This eliminates cascade reverser",
        "  doors, blocker doors, and nacelle structural reinforcement.",
        "",
        "REVERSAL EFFECTIVENESS BY MECHANISM TYPE",
        "  Through-feather (VPF):  35–40 % of forward takeoff thrust",
        "    Blade passes through flat pitch → negative pitch angles.",
        "    Higher effectiveness vs cascade due to full fan face coverage.",
        "  Flat-feather (cascade TRU): 20–30 % of forward takeoff thrust",
        "    Blocked by blocker-door geometry and duct pressure losses.",
        "",
        "MECHANISM WEIGHT  (D^2.5 scaling law: W ∝ D_fan^2.5, Raymer 2018)",
        f"  VPF mechanism (both engines):  {mw.mechanism_weight_kg:.0f} kg",
        f"  Cascade TRU equivalent:        {mw.conventional_reverser_weight_kg:.0f} kg",
        f"  Weight saving vs cascade TRU:  {mw.weight_saving_vs_conventional_kg:.0f} kg",
        "",
        "SFC IMPACT AT CRUISE",
        f"  Penalty vs no reverser:        +{mw.sfc_cruise_penalty_pct:.3f}%",
        f"  Benefit vs cascade reverser:   -{mw.sfc_benefit_vs_conventional_pct:.3f}%",
        "",
        "CONCLUSION",
        "  The VPF pitch mechanism adds weight (+SFC penalty) but eliminates the",
        "  cascade TRU, blocker doors and nacelle reinforcement. Net balance",
        f"  vs a conventional TRU: {mw.weight_saving_vs_conventional_kg:.0f} kg saved,",
        f"  {mw.sfc_benefit_vs_conventional_pct:.3f}% SFC improvement at cruise.",
        "  Through-feather reversal yields 35–40% effectiveness vs 20–30% for",
        "  cascade flat-feather, improving stopping distance margins.",
        "",
        "References:",
        "  - Cumpsty & Heyes, Jet Propulsion, Cambridge (2015)",
        "  - Walsh & Fletcher, Gas Turbine Performance, Blackwell (2004)",
        "  - Butterfield et al., Variable-pitch fans for turbofan thrust reversal,",
        "    ASME Turbo Expo GT2004-53713",
        "  - Raymer, Aircraft Design: A Conceptual Approach, AIAA (2018)",
    ]
    (out_dir / "reverse_thrust_summary.txt").write_text("\n".join(lines), encoding="utf-8")
