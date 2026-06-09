"""
Tests for airfoil .dat file reading functionality.

Verifies that airfoil coordinate files are loaded correctly.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def read_airfoil_dat(file_path: Path) -> pd.DataFrame:
    """
    Read airfoil coordinates from a .dat file.

    Parameters
    ----------
    file_path : Path
        Path to the .dat file.

    Returns
    -------
    pd.DataFrame
        DataFrame with columns 'x' and 'y' containing coordinates.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Airfoil file not found: {file_path}")

    rows = []
    with file_path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue

            # Skip header lines (non-numeric first character)
            if stripped[0].isalpha():
                continue

            parts = stripped.split()
            if len(parts) < 2:
                continue

            try:
                x = float(parts[0])
                y = float(parts[1])
                rows.append({"x": x, "y": y})
            except ValueError:
                continue

    if not rows:
        raise ValueError(f"No valid coordinate data found in {file_path}")

    return pd.DataFrame(rows)


class TestAirfoilReader:
    """Test suite for airfoil file reading."""

    def test_coordinates_loaded_correctly(
        self, sample_airfoil_dat: Path
    ) -> None:
        """Verify that coordinates are loaded correctly from .dat file."""
        df = read_airfoil_dat(sample_airfoil_dat)

        assert list(df.columns) == ["x", "y"]
        assert len(df) == 131  # naca_0012.dat has 131 coordinate rows

    def test_number_of_points_is_reasonable(
        self, sample_airfoil_dat: Path
    ) -> None:
        """naca_0012.dat has exactly 131 coordinate rows."""
        df = read_airfoil_dat(sample_airfoil_dat)
        assert len(df) == 131

    def test_x_coordinates_within_valid_range(
        self, sample_airfoil_dat: Path
    ) -> None:
        """Verify that x coordinates are within [0, 1] (normalized chord)."""
        df = read_airfoil_dat(sample_airfoil_dat)

        # X coordinates should be between 0 and 1 (normalized chord)
        assert (df["x"] >= 0.0).all(), "X coordinates should be >= 0"
        assert (df["x"] <= 1.0).all(), "X coordinates should be <= 1"

    def test_file_not_found_raises_error(self, tmp_path: Path) -> None:
        """Test that missing file raises FileNotFoundError."""
        non_existent = tmp_path / "nonexistent.dat"

        with pytest.raises(FileNotFoundError):
            read_airfoil_dat(non_existent)

    def test_empty_file_raises_error(self, tmp_path: Path) -> None:
        """Test that empty file raises ValueError."""
        empty_file = tmp_path / "empty.dat"
        empty_file.write_text("")

        with pytest.raises(ValueError, match="No valid coordinate data"):
            read_airfoil_dat(empty_file)

    def test_file_with_only_header_raises_error(self, tmp_path: Path) -> None:
        """Test that file with only header (no coordinates) raises error."""
        header_only = tmp_path / "header_only.dat"
        header_only.write_text("NACA 0012\nSome header text\n")

        with pytest.raises(ValueError, match="No valid coordinate data"):
            read_airfoil_dat(header_only)

    def test_coordinates_are_numeric(self, sample_airfoil_dat: Path) -> None:
        """Verify that all coordinates are numeric."""
        df = read_airfoil_dat(sample_airfoil_dat)

        # All values should be numeric
        assert df["x"].dtype in [float, "float64"]
        assert df["y"].dtype in [float, "float64"]

    def test_airfoil_closed_trailing_edge(
        self, sample_airfoil_dat: Path
    ) -> None:
        """Verify that airfoil has closed trailing edge (x≈1.0 appears)."""
        df = read_airfoil_dat(sample_airfoil_dat)

        # Should have points near x=1.0 (trailing edge)
        # Allow some tolerance for floating point precision
        trailing_edge_points = df[df["x"] >= 0.99]
        assert len(trailing_edge_points) >= 1, "Trailing edge (x≈1.0) not found"

    def test_airfoil_leading_edge_present(
        self, sample_airfoil_dat: Path
    ) -> None:
        """Verify that airfoil has leading edge (x=0.0 or very close)."""
        df = read_airfoil_dat(sample_airfoil_dat)

        # Should have points near x=0.0 (leading edge)
        leading_edge_points = df[df["x"] <= 0.01]
        assert len(leading_edge_points) >= 1, "Leading edge (x≈0.0) not found"

    def test_y_coordinates_reasonable_range(
        self, sample_airfoil_dat: Path
    ) -> None:
        """Verify that y coordinates are in reasonable range for normalized airfoil."""
        df = read_airfoil_dat(sample_airfoil_dat)

        # Y coordinates for normalized airfoils are typically in [-0.2, 0.2]
        # (allowing some margin for thick airfoils)
        assert (df["y"] >= -0.5).all(), "Y coordinates too negative"
        assert (df["y"] <= 0.5).all(), "Y coordinates too positive"
