"""
Domain model for a complete correction result.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class CorrectionResult:
    """Complete result of compressibility correction for one case."""

    case: str
    section: Optional[str]
    output_dir: Path
    corrected_polar_path: Path
    corrected_cl_alpha_path: Path
    corrected_efficiency_path: Path
    corrected_plot_path: Path
