"""contracts.py — typed I/O contracts between VPF pipeline stages."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Stage 1 — Airfoil selection

@dataclass
class Stage1Result:
    """Output of Stage 1: automatic airfoil selection."""
    selected_airfoil_name: str
    selected_airfoil_dat: Path
    stage_dir: Path
    selection_dir: Path

    def validate(self) -> None:
        from vpf_analysis.validation.validators import require_dir, require_file
        require_file(self.selected_airfoil_dat, "selected airfoil .dat")
        require_dir(self.stage_dir, "Stage 1 results dir")



# Stage 2 —XFOIL simulations (12 polars)

@dataclass
class Stage2Result:
    """Output of Stage 2: XFOIL polars per condition and section."""
    source_polars: Path                                       # stage2/simulation_plots/
    alpha_eff_map: dict[tuple[str, str], float]     # (flight, section) → α_opt
    stall_map: dict[tuple[str, str], tuple[float, float]]  # (flight, section) → (α_stall, CL_max)
    n_simulations: int
    n_convergence_warnings: int
    stage_dir: Path

    def validate(self) -> None:
        from vpf_analysis.validation.validators import require_dir
        require_dir(self.source_polars, "Stage 2 simulation_plots")
        require_dir(self.stage_dir, "Stage 2 results dir")
        if self.n_simulations == 0:
            raise ValueError("Stage 2: no XFOIL simulations were executed")
        if len(self.alpha_eff_map) < self.n_simulations:
            raise ValueError(
                f"Stage 2: alpha_eff_map incomplete "
                f"({len(self.alpha_eff_map)} of {self.n_simulations} cases)"
            )



# Stage 3 —Compressibility corrections

@dataclass
class Stage3Result:
    """Output of Stage 3: PG and K-T corrected polars."""
    corrected_dir: Path           # stage3/
    n_cases_corrected: int
    n_cases_failed: int
    stage_dir: Path

    @property
    def success_rate(self) -> float:
        total = self.n_cases_corrected + self.n_cases_failed
        return self.n_cases_corrected / total if total > 0 else 0.0

    def validate(self) -> None:
        from vpf_analysis.validation.validators import require_dir
        require_dir(self.corrected_dir, "Stage 3 corrected polars dir")
        if self.n_cases_corrected == 0:
            raise ValueError("Stage 3: no corrected polars — check Stage 2 outputs")
        polar_files = list(self.corrected_dir.rglob("corrected_polar.csv"))
        if not polar_files:
            raise ValueError(
                f"Stage 3: corrected_dir exists but contains no "
                f"corrected_polar.csv: {self.corrected_dir}"
            )



# Stage 4 —Performance metrics

@dataclass
class Stage4Result:
    """Output of Stage 4: aerodynamic metrics and figures."""
    metrics: list[Any]    # list[AerodynamicMetrics] (Any to avoid circular import)
    tables_dir: Path
    figures_dir: Path
    stage_dir: Path

    def validate(self) -> None:
        from vpf_analysis.validation.validators import require_dir
        require_dir(self.stage_dir, "Stage 4 results dir")
        require_dir(self.tables_dir, "Stage 4 tables dir")
        if not self.metrics:
            raise ValueError("Stage 4: metrics list is empty")



# Stage 5 —Pitch & Kinematics

@dataclass
class Stage5Result:
    """Output of Stage 5: full kinematics and 3D aerodynamic analysis."""
    tables_dir: Path
    figures_dir: Path
    n_tables: int
    n_figures: int
    twist_total_deg: float
    max_off_design_loss_pct: float
    stage_dir: Path

    def validate(self) -> None:
        from vpf_analysis.validation.validators import require_dir
        require_dir(self.tables_dir, "Stage 5 tables dir")
        require_dir(self.figures_dir, "Stage 5 figures dir")
        if self.n_tables < 9:
            raise ValueError(
                f"Stage 5: only {self.n_tables} tables (expected ≥9)"
            )
        if math.isnan(self.twist_total_deg):
            raise ValueError("Stage 5: twist_total_deg is NaN")
        if math.isnan(self.max_off_design_loss_pct):
            raise ValueError("Stage 5: max_off_design_loss_pct is NaN")



# Stage 6 —Reverse Thrust Modeling

@dataclass
class Stage6Result:
    """Output of Stage 6: VPF reverse thrust — theoretical mechanism weight analysis."""
    tables_dir: Path
    figures_dir: Path
    n_tables: int
    n_figures: int
    mechanism_weight_kg: float
    sfc_cruise_penalty_pct: float
    stage_dir: Path

    def validate(self) -> None:
        from vpf_analysis.validation.validators import require_dir
        require_dir(self.stage_dir, "Stage 6 results dir")
        require_dir(self.tables_dir, "Stage 6 tables dir")
        require_dir(self.figures_dir, "Stage 6 figures dir")
        if self.n_tables < 1:
            raise ValueError(f"Stage 6: {self.n_tables} tables (expected ≥1)")
        if self.mechanism_weight_kg <= 0:
            raise ValueError("Stage 6: mechanism_weight_kg must be positive")
        if math.isnan(self.sfc_cruise_penalty_pct):
            raise ValueError("Stage 6: sfc_cruise_penalty_pct is NaN")



# Stage 7 —SFC Analysis

@dataclass
class Stage7Result:
    """Output of Stage 7: VPF impact on specific fuel consumption."""
    tables_dir: Path
    figures_dir: Path
    mean_sfc_reduction_pct: float
    stage_dir: Path
    ge9x_fuel_saving_pct: float = float("nan")

    def validate(self) -> None:
        from vpf_analysis.validation.validators import require_dir
        require_dir(self.stage_dir, "Stage 7 results dir")
        require_dir(self.tables_dir, "Stage 7 tables dir")
        require_dir(self.figures_dir, "Stage 7 figures dir")
        if math.isnan(self.mean_sfc_reduction_pct):
            raise ValueError(
                "Stage 7: mean_sfc_reduction_pct is NaN — "
                "check that sfc_analysis.csv contains column 'sfc_reduction'"
            )
