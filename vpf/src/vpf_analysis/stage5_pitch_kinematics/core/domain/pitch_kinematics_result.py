"""
pitch_kinematics_result.py
--------------------------
Domain models for the integrated pitch and incidence analysis.

Consolidates the former OptimalIncidence (Stage 6) and KinematicsResult (Stage 7)
into a single module reflecting that both analyses form a continuous chain:
  OptimalIncidence → PitchAdjustment → KinematicsResult
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OptimalIncidence:
    """Optimal angle of attack for a flight condition and blade section."""

    condition: str
    section: str
    reynolds: float
    mach: float
    alpha_opt: float   # Optimal angle (2nd peak of CL/CD, α ≥ 3°)
    cl_cd_max: float   # Maximum efficiency at the optimal point


@dataclass(frozen=True)
class PitchAdjustment:
    """Required pitch adjustment relative to a reference condition (cruise)."""

    condition: str
    section: str
    alpha_opt: float
    delta_pitch: float  # Δα = α_opt(condition) − α_opt(cruise)


class KinematicsResult:
    """
    Velocity-triangle analysis result for a condition/section.

    Translates the aerodynamic Δα into the Δβ_mech that the pitch actuator must apply.
    """

    def __init__(
        self,
        condition: str,
        section: str,
        axial_velocity: float,
        tangential_velocity: float,
        inflow_angle_deg: float,
        alpha_aero_deg: float,
        beta_mech_deg: float,
        delta_beta_mech_deg: float = 0.0,
    ) -> None:
        self.condition            = condition
        self.section              = section
        self.axial_velocity       = axial_velocity        # V_ax [m/s]
        self.tangential_velocity  = tangential_velocity   # U = ω·r [m/s]
        self.inflow_angle_deg     = inflow_angle_deg      # φ [°]
        self.alpha_aero_deg       = alpha_aero_deg        # α_opt [°]
        self.beta_mech_deg        = beta_mech_deg         # β = α + φ [°]
        self.delta_beta_mech_deg  = delta_beta_mech_deg   # Δβ relative to cruise [°]
