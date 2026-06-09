from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SimulationCondition:
    """Single aerodynamic simulation condition. ncrit: XFOIL transition param (4–6 turbofan, ~9 clean tunnel)."""

    name: str
    mach_rel: float
    reynolds: float
    alpha_min: float
    alpha_max: float
    alpha_step: float
    ncrit: float

