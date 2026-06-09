from __future__ import annotations

from pathlib import Path
from typing import Protocol

from vpf_analysis.core.domain.simulation_condition import SimulationCondition
from vpf_analysis.xfoil_runner import XfoilPolarResult


class XfoilRunnerPort(Protocol):
    def run_polar(self, airfoil_dat: Path, condition: SimulationCondition, output_file: Path) -> XfoilPolarResult: ...

