from __future__ import annotations

import logging
from pathlib import Path

from vpf_analysis.core.domain.simulation_condition import SimulationCondition
from vpf_analysis.settings import get_settings
from vpf_analysis.xfoil_runner import XfoilPolarRequest, XfoilPolarResult, run_xfoil_polar

LOGGER = logging.getLogger(__name__)


class XfoilRunnerAdapter:
    """XFOIL adapter with timeouts and retries from PipelineSettings.

    ``final_analysis=True`` uses TIMEOUT_FINAL_S (Stage 2);
    ``False`` uses TIMEOUT_SELECTION_S (Stage 1).
    """

    def __init__(
        self,
        timeout_override: float | None = None,
        max_retries_override: int | None = None,
        final_analysis: bool = True,
    ) -> None:
        cfg = get_settings().xfoil
        self._timeout = (
            timeout_override
            if timeout_override is not None
            else (cfg.TIMEOUT_FINAL_S if final_analysis else cfg.TIMEOUT_SELECTION_S)
        )
        self._max_retries = (
            max_retries_override
            if max_retries_override is not None
            else cfg.MAX_RETRIES
        )

    def run_polar(self, airfoil_dat: Path, condition: SimulationCondition, output_file: Path) -> XfoilPolarResult:
        result = run_xfoil_polar(
            XfoilPolarRequest(
                airfoil_dat=airfoil_dat,
                re=condition.reynolds,
                alpha_start=condition.alpha_min,
                alpha_end=condition.alpha_max,
                alpha_step=condition.alpha_step,
                mach=condition.mach_rel,
                n_crit=condition.ncrit,
                output_file=output_file,
            ),
            timeout=self._timeout,
            max_retries=self._max_retries,
        )
        if result.convergence_failures > 0:
            LOGGER.info(
                "Polar %s/%s: %d non-converged points (rate=%.0f%%)",
                getattr(condition, "name", "?"), output_file.stem,
                result.convergence_failures, result.convergence_rate * 100,
            )
        return result
