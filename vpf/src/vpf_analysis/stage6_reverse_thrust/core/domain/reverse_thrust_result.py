"""
reverse_thrust_result.py
------------------------
Domain dataclasses for Stage 6 — VPF Reverse Thrust.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MechanismWeightResult:
    """VPF pitch mechanism weight and SFC impact compared to alternatives."""
    # Absolute weights (both engines combined)
    mechanism_weight_kg: float               # VPF actuator + pitch links + root reinforcement
    conventional_reverser_weight_kg: float   # Cascade + blocker doors + nacelle reinforcement

    # Balance vs alternatives
    weight_saving_vs_conventional_kg: float  # > 0 means VPF is lighter

    # SFC impact at cruise (first-order Breguet approximation)
    sfc_cruise_penalty_pct: float            # ΔSFC from carrying mechanism (vs no reverser)
    sfc_benefit_vs_conventional_pct: float   # ΔSFC improvement vs conventional reverser
