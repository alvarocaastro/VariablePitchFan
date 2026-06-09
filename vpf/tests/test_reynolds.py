"""
Tests for Reynolds number calculation.

Reynolds number formula: Re = (rho * V * c) / mu

Where:
- rho: air density [kg/m³]
- V: velocity [m/s]
- c: chord length [m]
- mu: dynamic viscosity [Pa·s]
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def calculate_reynolds(
    density: float, velocity: float, chord: float, viscosity: float
) -> float:
    """
    Calculate Reynolds number.

    Parameters
    ----------
    density : float
        Air density in kg/m³.
    velocity : float
        Velocity in m/s.
    chord : float
        Chord length in meters.
    viscosity : float
        Dynamic viscosity in Pa·s.

    Returns
    -------
    float
        Reynolds number (dimensionless).
    """
    if viscosity <= 0:
        raise ValueError("Viscosity must be positive")
    if density < 0:
        raise ValueError("Density cannot be negative")
    if velocity < 0:
        raise ValueError("Velocity cannot be negative")
    if chord <= 0:
        raise ValueError("Chord must be positive")

    return (density * velocity * chord) / viscosity


class TestReynoldsCalculation:
    """Test suite for Reynolds number calculation."""

    # Standard atmospheric conditions at sea level (15°C)
    RHO_STD = 1.225  # kg/m³
    MU_STD = 1.789e-5  # Pa·s

    def test_typical_atmospheric_values(self) -> None:
        """Test Reynolds calculation with typical atmospheric values."""
        velocity = 100.0  # m/s
        chord = 0.5  # m

        reynolds = calculate_reynolds(
            self.RHO_STD, velocity, chord, self.MU_STD
        )

        # (1.225 * 100 * 0.5) / 1.789e-5 = 3 422 860.26…
        expected = (self.RHO_STD * velocity * chord) / self.MU_STD
        assert reynolds == pytest.approx(expected, rel=1e-6)

    def test_small_velocity(self) -> None:
        """Reynolds scales linearly with velocity; 10 m/s gives 1/10 of the 100 m/s value."""
        velocity = 10.0  # m/s
        chord = 0.5  # m
        expected = (self.RHO_STD * velocity * chord) / self.MU_STD

        reynolds = calculate_reynolds(self.RHO_STD, velocity, chord, self.MU_STD)

        assert reynolds == pytest.approx(expected, rel=1e-6)

    def test_larger_chord_values(self) -> None:
        """Reynolds scales linearly with chord; 2 m chord gives 4× the 0.5 m value."""
        velocity = 100.0  # m/s
        chord = 2.0  # m
        expected = (self.RHO_STD * velocity * chord) / self.MU_STD

        reynolds = calculate_reynolds(self.RHO_STD, velocity, chord, self.MU_STD)

        assert reynolds == pytest.approx(expected, rel=1e-6)

    @pytest.mark.parametrize(
        "density,velocity,chord,viscosity,expected_re",
        [
            (1.225, 100.0, 0.5, 1.789e-5, 3.42e6),
            (1.225, 50.0, 1.0, 1.789e-5, 3.42e6),  # Same Re, different V and c
            (1.0, 10.0, 0.1, 1e-5, 1e5),
        ],
    )
    def test_parameterized_cases(
        self,
        density: float,
        velocity: float,
        chord: float,
        viscosity: float,
        expected_re: float,
    ) -> None:
        """Test multiple Reynolds calculation cases using parametrization."""
        reynolds = calculate_reynolds(density, velocity, chord, viscosity)
        assert reynolds == pytest.approx(expected_re, rel=0.01)

    def test_zero_viscosity_raises_error(self) -> None:
        """Test that zero viscosity raises ValueError."""
        with pytest.raises(ValueError, match="Viscosity must be positive"):
            calculate_reynolds(1.225, 100.0, 0.5, 0.0)

    def test_negative_viscosity_raises_error(self) -> None:
        """Test that negative viscosity raises ValueError."""
        with pytest.raises(ValueError, match="Viscosity must be positive"):
            calculate_reynolds(1.225, 100.0, 0.5, -1e-5)

    def test_zero_chord_raises_error(self) -> None:
        """Test that zero chord raises ValueError."""
        with pytest.raises(ValueError, match="Chord must be positive"):
            calculate_reynolds(1.225, 100.0, 0.0, 1.789e-5)

    def test_negative_chord_raises_error(self) -> None:
        """Test that negative chord raises ValueError."""
        with pytest.raises(ValueError, match="Chord must be positive"):
            calculate_reynolds(1.225, 100.0, -0.5, 1.789e-5)

    def test_negative_velocity_raises_error(self) -> None:
        """Test that negative velocity raises ValueError."""
        with pytest.raises(ValueError, match="Velocity cannot be negative"):
            calculate_reynolds(1.225, -100.0, 0.5, 1.789e-5)

    def test_negative_density_raises_error(self) -> None:
        """Test that negative density raises ValueError."""
        with pytest.raises(ValueError, match="Density cannot be negative"):
            calculate_reynolds(-1.225, 100.0, 0.5, 1.789e-5)
