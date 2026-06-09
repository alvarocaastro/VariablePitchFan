"""
Domain model for a compressibility correction case.

Represents a single correction scenario: one flight condition at a target Mach.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CompressibilityCase:
    """Single compressibility correction case."""

    flight_condition: str
    target_mach: float
    reference_mach: float
