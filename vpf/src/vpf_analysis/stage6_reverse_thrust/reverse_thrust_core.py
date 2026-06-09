"""Pure functions for reverse thrust mechanism weight analysis."""

from __future__ import annotations

import logging
import math

from vpf_analysis.stage6_reverse_thrust.core.domain.reverse_thrust_result import (
    MechanismWeightResult,
)

LOGGER = logging.getLogger(__name__)

_G = 9.81


def compute_mechanism_weight(
    engine_dry_weight_kg: float,
    mechanism_weight_fraction: float,
    conventional_reverser_fraction: float,
    design_thrust_kN: float,
    cruise_thrust_fraction: float,
    aircraft_L_D: float,
    n_engines: int = 2,
    d_scale_factor: float = 1.0,
) -> MechanismWeightResult:
    """Compute VPF mechanism weight and its cruise SFC impact.

    Weight scaling law:  W ∝ D_fan^2.5  (Raymer 2018; Roskam Vol. V).
    ``d_scale_factor`` = (D_uhbpr / D_ref)^2.5, pre-computed from
    ``fan_diameter_ratio`` in engine_parameters.yaml.
    """
    d_scale = d_scale_factor
    LOGGER.info("D^2.5 weight scaling factor: %.4f", d_scale)

    mechanism_weight_kg = n_engines * engine_dry_weight_kg * mechanism_weight_fraction * d_scale
    conventional_weight_kg = n_engines * engine_dry_weight_kg * conventional_reverser_fraction * d_scale
    weight_saving_kg = conventional_weight_kg - mechanism_weight_kg

    t_cruise_total_N = n_engines * design_thrust_kN * 1000.0 * cruise_thrust_fraction

    delta_t_mechanism_N = mechanism_weight_kg * _G / aircraft_L_D
    sfc_penalty_pct = (delta_t_mechanism_N / t_cruise_total_N) * 100.0

    delta_t_saving_N = weight_saving_kg * _G / aircraft_L_D
    sfc_benefit_pct = (delta_t_saving_N / t_cruise_total_N) * 100.0

    return MechanismWeightResult(
        mechanism_weight_kg=mechanism_weight_kg,
        conventional_reverser_weight_kg=conventional_weight_kg,
        weight_saving_vs_conventional_kg=weight_saving_kg,
        sfc_cruise_penalty_pct=sfc_penalty_pct,
        sfc_benefit_vs_conventional_pct=sfc_benefit_pct,
    )
