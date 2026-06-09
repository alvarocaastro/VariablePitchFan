"""
Tests for Prandtl-Glauert compressibility correction.

Formula:
    beta = sqrt(1 - M^2)
    C_corrected = C / beta
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd
import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vpf_analysis.stage3_compressibility_correction.prandtl_glauert import (
    PrandtlGlauertModel,
)
from vpf_analysis.stage3_compressibility_correction.compressibility_case import (
    CompressibilityCase,
)


class TestPrandtlGlauertCorrection:
    """Test suite for Prandtl-Glauert compressibility correction."""

    def test_corrected_coefficient_larger_than_original_when_mach_positive(
        self,
    ) -> None:
        """Verify corrected coefficient is larger than original when Mach > 0."""
        model = PrandtlGlauertModel()

        # Reference Mach (incompressible)
        reference_mach = 0.2
        # Target Mach (compressible)
        target_mach = 0.7

        case = CompressibilityCase(
            flight_condition="Test",
            target_mach=target_mach,
            reference_mach=reference_mach,
        )

        # Original lift coefficient
        original_cl = 0.5
        df = pd.DataFrame({"cl": [original_cl], "cd": [0.02]})

        corrected_df = model.correct_polar(df, case)

        assert corrected_df["cl_pg"].iloc[0] > original_cl

    def test_correction_increases_as_mach_increases(self) -> None:
        """Verify correction increases as Mach number increases."""
        model = PrandtlGlauertModel()
        reference_mach = 0.2
        original_cl = 0.5

        mach_values = [0.3, 0.5, 0.7, 0.85]
        corrections = []

        for mach in mach_values:
            case = CompressibilityCase(
                flight_condition="Test",
                target_mach=mach,
                reference_mach=reference_mach,
            )
            df = pd.DataFrame({"cl": [original_cl], "cd": [0.02]})
            corrected_df = model.correct_polar(df, case)
            corrections.append(corrected_df["cl_pg"].iloc[0])

        # Each correction should be larger than the previous
        for i in range(len(corrections) - 1):
            assert corrections[i + 1] > corrections[i], (
                f"Correction should increase with Mach: "
                f"{mach_values[i]} -> {mach_values[i+1]}"
            )

    def test_mach_zero_returns_original_value(self) -> None:
        """Verify Mach = 0 returns the original value (no correction)."""
        model = PrandtlGlauertModel()

        case = CompressibilityCase(
            flight_condition="Test",
            target_mach=0.0,
            reference_mach=0.0,
        )

        original_cl = 0.5
        df = pd.DataFrame({"cl": [original_cl], "cd": [0.02]})

        corrected_df = model.correct_polar(df, case)

        # When both Mach numbers are 0, beta_ref = beta_target = 1.0
        # So correction_factor = 1.0 / 1.0 = 1.0
        assert corrected_df["cl_pg"].iloc[0] == pytest.approx(
            original_cl, abs=1e-10
        )

    def test_invalid_mach_greater_than_one_raises_error(self) -> None:
        """Test that Mach >= 1.0 raises ValueError."""
        model = PrandtlGlauertModel()

        with pytest.raises(ValueError, match="Mach.*>= 1.0"):
            model.compute_beta(1.0)

        with pytest.raises(ValueError, match="Mach.*>= 1.0"):
            model.compute_beta(1.5)

    def test_beta_calculation_correct(self) -> None:
        """Test that beta calculation is mathematically correct."""
        model = PrandtlGlauertModel()

        test_cases = [
            (0.0, 1.0),  # M=0 -> beta=1
            (0.2, math.sqrt(1 - 0.2**2)),  # M=0.2
            (0.5, math.sqrt(1 - 0.5**2)),  # M=0.5
            (0.7, math.sqrt(1 - 0.7**2)),  # M=0.7
            (0.85, math.sqrt(1 - 0.85**2)),  # M=0.85
        ]

        for mach, expected_beta in test_cases:
            beta = model.compute_beta(mach)
            assert beta == pytest.approx(expected_beta, abs=1e-10)

    def test_correction_preserves_dataframe_structure(self) -> None:
        """Verify that correction preserves DataFrame structure and adds new columns."""
        model = PrandtlGlauertModel()

        case = CompressibilityCase(
            flight_condition="Test",
            target_mach=0.7,
            reference_mach=0.2,
        )

        df = pd.DataFrame(
            {
                "alpha": [0.0, 5.0, 10.0],
                "cl": [0.3, 0.6, 0.9],
                "cd": [0.02, 0.03, 0.05],
            }
        )

        corrected_df = model.correct_polar(df, case)

        # Original columns should be preserved
        assert "alpha" in corrected_df.columns
        assert "cl" in corrected_df.columns
        assert "cd" in corrected_df.columns

        # New columns should be added
        assert "cl_pg" in corrected_df.columns
        assert "cd_corrected" in corrected_df.columns
        assert "ld_pg" in corrected_df.columns
        assert "mach_target" in corrected_df.columns

        # Number of rows should be preserved
        assert len(corrected_df) == len(df)

    def test_drag_not_corrected(self) -> None:
        """Verify that drag coefficient is not corrected (strategy: unchanged)."""
        model = PrandtlGlauertModel()

        case = CompressibilityCase(
            flight_condition="Test",
            target_mach=0.7,
            reference_mach=0.2,
        )

        original_cd = 0.03
        df = pd.DataFrame({"cl": [0.5], "cd": [original_cd]})

        corrected_df = model.correct_polar(df, case)

        # Drag should remain unchanged
        assert corrected_df["cd_corrected"].iloc[0] == pytest.approx(
            original_cd, abs=1e-10
        )

    @pytest.mark.parametrize(
        "reference_mach,target_mach,original_cl,expected_factor",
        [
            (0.0, 0.0, 1.0, 1.0),  # No correction
            (0.2, 0.5, 1.0, math.sqrt(1 - 0.2**2) / math.sqrt(1 - 0.5**2)),
            (0.2, 0.7, 1.0, math.sqrt(1 - 0.2**2) / math.sqrt(1 - 0.7**2)),
        ],
    )
    def test_correction_factor_calculation(
        self,
        reference_mach: float,
        target_mach: float,
        original_cl: float,
        expected_factor: float,
    ) -> None:
        """Test correction factor calculation for various Mach numbers."""
        model = PrandtlGlauertModel()

        case = CompressibilityCase(
            flight_condition="Test",
            target_mach=target_mach,
            reference_mach=reference_mach,
        )

        df = pd.DataFrame({"cl": [original_cl], "cd": [0.02]})
        corrected_df = model.correct_polar(df, case)

        correction_factor = corrected_df["cl_pg"].iloc[0] / original_cl
        assert correction_factor == pytest.approx(expected_factor, abs=1e-6)
