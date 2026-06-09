"""
Tests for aerodynamic efficiency calculation.

Efficiency formula: efficiency = CL / CD
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def calculate_efficiency(cl: float, cd: float) -> float:
    """
    Calculate aerodynamic efficiency (L/D ratio).

    Parameters
    ----------
    cl : float
        Lift coefficient.
    cd : float
        Drag coefficient.

    Returns
    -------
    float
        Efficiency (CL/CD). Returns NaN if CD is zero or negative.
    """
    if cd <= 0:
        return float("nan")
    return cl / cd


class TestEfficiencyCalculation:
    """Test suite for aerodynamic efficiency calculation."""

    def test_correct_numerical_result(self) -> None:
        """Test that efficiency calculation returns correct numerical result."""
        cl = 0.6
        cd = 0.03

        efficiency = calculate_efficiency(cl, cd)

        expected = cl / cd  # 0.6 / 0.03 = 20.0
        assert efficiency == pytest.approx(expected, abs=1e-10)

    def test_handles_small_drag_values(self) -> None:
        """Test efficiency calculation with small drag values."""
        cl = 0.5
        cd = 0.001  # Very small drag

        efficiency = calculate_efficiency(cl, cd)

        assert efficiency == pytest.approx(500.0, abs=1e-6)

    def test_division_by_zero_returns_nan(self) -> None:
        """Test that division by zero (CD=0) returns NaN."""
        cl = 0.5
        cd = 0.0

        efficiency = calculate_efficiency(cl, cd)

        assert np.isnan(efficiency)

    def test_negative_drag_returns_nan(self) -> None:
        """Test that negative drag returns NaN."""
        cl = 0.5
        cd = -0.01

        efficiency = calculate_efficiency(cl, cd)

        assert np.isnan(efficiency)

    @pytest.mark.parametrize(
        "cl,cd,expected_efficiency",
        [
            (0.3, 0.02, 15.0),
            (0.6, 0.03, 20.0),
            (0.9, 0.05, 18.0),
            (1.2, 0.08, 15.0),
        ],
    )
    def test_parameterized_efficiency_cases(
        self, cl: float, cd: float, expected_efficiency: float
    ) -> None:
        """Test multiple efficiency calculation cases using parametrization."""
        efficiency = calculate_efficiency(cl, cd)
        assert efficiency == pytest.approx(expected_efficiency, abs=1e-6)

    def test_efficiency_in_dataframe(self, sample_polar_data: pd.DataFrame) -> None:
        """Efficiency column must equal CL/CD element-wise for all rows."""
        df = sample_polar_data.copy()

        df["efficiency"] = df.apply(
            lambda row: calculate_efficiency(row["cl"], row["cd"]), axis=1
        )

        expected_efficiency = df["cl"] / df["cd"]
        assert df["efficiency"].equals(expected_efficiency)

    def test_efficiency_with_zero_drag_in_dataframe(self) -> None:
        """Test efficiency calculation in DataFrame with zero drag."""
        df = pd.DataFrame(
            {
                "cl": [0.3, 0.6, 0.9],
                "cd": [0.02, 0.0, 0.05],  # One zero drag value
            }
        )

        df["efficiency"] = df.apply(
            lambda row: calculate_efficiency(row["cl"], row["cd"]), axis=1
        )

        # First and third should be valid
        assert df["efficiency"].iloc[0] == pytest.approx(15.0, abs=1e-6)
        assert df["efficiency"].iloc[2] == pytest.approx(18.0, abs=1e-6)

        # Second should be NaN
        assert np.isnan(df["efficiency"].iloc[1])

    def test_efficiency_increases_with_cl(self) -> None:
        """Test that efficiency increases when CL increases (for constant CD)."""
        cd = 0.03
        cl_values = [0.3, 0.6, 0.9, 1.2]

        efficiencies = [calculate_efficiency(cl, cd) for cl in cl_values]

        # Each efficiency should be larger than the previous
        for i in range(len(efficiencies) - 1):
            assert efficiencies[i + 1] > efficiencies[i]

    def test_efficiency_decreases_with_cd(self) -> None:
        """Test that efficiency decreases when CD increases (for constant CL)."""
        cl = 0.6
        cd_values = [0.01, 0.02, 0.03, 0.05]

        efficiencies = [calculate_efficiency(cl, cd) for cd in cd_values]

        # Each efficiency should be smaller than the previous
        for i in range(len(efficiencies) - 1):
            assert efficiencies[i + 1] < efficiencies[i]
