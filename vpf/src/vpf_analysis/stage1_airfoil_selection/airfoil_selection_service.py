from __future__ import annotations

import dataclasses
import logging
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable, Sequence

import numpy as np
import pandas as pd

from vpf_analysis.adapters.xfoil.xfoil_parser import parse_polar_file
from vpf_analysis.config.domain import ResolvedSelectionCondition
from vpf_analysis.core.domain.airfoil import Airfoil
from vpf_analysis.core.domain.simulation_condition import SimulationCondition
from vpf_analysis.ports.xfoil_runner_port import XfoilRunnerPort
from vpf_analysis.stage1_airfoil_selection.scoring import (
    AirfoilScore,
    aggregate_weighted_scores,
    score_airfoil,
)

LOGGER = logging.getLogger(__name__)

# Paul Tol bright palette — 4 distinct colours for candidate airfoils
_TOLS = ["#4477AA", "#EE6677", "#228833", "#CCBB44"]


@dataclass(frozen=True)
class AirfoilSelectionResult:
    best_airfoil: Airfoil
    scores: list[AirfoilScore]
    polars: pd.DataFrame


class AirfoilSelectionService:
    """Compare candidate airfoils across multiple mission conditions and select the best."""

    def __init__(self, xfoil_runner: XfoilRunnerPort, results_dir: Path) -> None:
        self._xfoil = xfoil_runner
        self._results_dir = results_dir

    def run_selection(
        self,
        airfoils: Sequence[Airfoil],
        conditions: Sequence[ResolvedSelectionCondition],
        alpha_min: float,
        alpha_max: float,
        alpha_step: float,
        mach_ref: float,
        progress_callback: Callable[[str], None] | None = None,
    ) -> AirfoilSelectionResult:
        """Run XFOIL for every (airfoil × condition) pair and return a mission-weighted result."""

        out_dir = self._results_dir / "airfoil_selection"
        out_dir.mkdir(parents=True, exist_ok=True)

        primary_label = max(conditions, key=lambda c: c.weight).label
        weights = {c.label: c.weight for c in conditions}

        LOGGER.info(
            "Evaluating %d airfoil candidates across %d conditions (primary: %s)",
            len(airfoils), len(conditions), primary_label,
        )

        # scores_by_condition[label] → list aligned with airfoils order
        scores_by_condition: dict[str, list[AirfoilScore]] = {c.label: [] for c in conditions}
        all_rows: list[pd.DataFrame] = []

        for cond in conditions:
            sim_cond = SimulationCondition(
                name=cond.label,
                mach_rel=mach_ref,
                reynolds=cond.reynolds,
                alpha_min=alpha_min,
                alpha_max=alpha_max,
                alpha_step=alpha_step,
                ncrit=cond.ncrit,
            )
            LOGGER.info(
                "  Condition %s: Re=%.2e  Ncrit=%.1f  M=%.2f",
                cond.label, cond.reynolds, cond.ncrit, mach_ref,
            )

            for airfoil in airfoils:
                if progress_callback is not None:
                    progress_callback(f"{airfoil.name} [{cond.label}]")

                raw_polars_dir = out_dir / "raw_polars"
                raw_polars_dir.mkdir(parents=True, exist_ok=True)
                out_file = raw_polars_dir / f"{airfoil.name.replace(' ', '_')}_{cond.label}_polar.txt"

                try:
                    self._xfoil.run_polar(airfoil.dat_path, sim_cond, out_file)
                except Exception as exc:
                    LOGGER.warning(
                        "  XFOIL failed for %s @ %s: %s — skipping.", airfoil.name, cond.label, exc
                    )
                    scores_by_condition[cond.label].append(
                        AirfoilScore(
                            airfoil=airfoil.name,
                            max_ld=np.nan, alpha_opt=np.nan, stall_alpha=np.nan,
                            stability_margin=np.nan, robustness_ld=np.nan, total_score=np.nan,
                        )
                    )
                    continue

                df = self._build_polar_df(out_file, airfoil, sim_cond)
                if df.empty:
                    LOGGER.warning(
                        "  Polar empty for %s @ %s — skipping.", airfoil.name, cond.label
                    )
                    scores_by_condition[cond.label].append(
                        AirfoilScore(
                            airfoil=airfoil.name,
                            max_ld=np.nan, alpha_opt=np.nan, stall_alpha=np.nan,
                            stability_margin=np.nan, robustness_ld=np.nan, total_score=np.nan,
                        )
                    )
                    continue

                scores_by_condition[cond.label].append(score_airfoil(df))
                all_rows.append(df)

        polars = pd.concat(all_rows, ignore_index=True) if all_rows else pd.DataFrame()

        if all(np.isnan(s.total_score) for sl in scores_by_condition.values() for s in sl):
            raise RuntimeError(
                "No airfoil could be scored (all XFOIL runs failed or produced empty polars)."
            )

        scores = aggregate_weighted_scores(scores_by_condition, weights, primary_label)

        for score in scores:
            LOGGER.info(
                "  %s -> (CL/CD)=%.2f  α_opt=%.1f°  stall=%.1f°  margin=%.1f°  robustness=%.2f  score=%.3f",
                score.airfoil, score.max_ld, score.alpha_opt, score.stall_alpha,
                score.stability_margin, score.robustness_ld, score.total_score,
            )

        best = max(scores, key=lambda s: s.total_score if not np.isnan(s.total_score) else -np.inf)
        LOGGER.info("Selected airfoil: %s (score=%.3f)", best.airfoil, best.total_score)

        selected_path = out_dir / "selected_airfoil.dat"
        selected_path.write_text(best.airfoil, encoding="utf-8")

        best_airfoil = next(a for a in airfoils if a.name == best.airfoil)

        # Figure: polars from the primary condition only (most meaningful display)
        primary_polars = (
            polars[polars["condition"] == primary_label] if not polars.empty else polars
        )
        self._save_comparison_figure(primary_polars, scores, out_dir, primary_label)
        self._save_scores_csv(scores, out_dir)

        return AirfoilSelectionResult(best_airfoil=best_airfoil, scores=scores, polars=polars)

    @staticmethod
    def _save_comparison_figure(
        polars: pd.DataFrame,
        scores: list[AirfoilScore],
        out_dir: Path,
        primary_label: str,
    ) -> None:
        import matplotlib.pyplot as plt

        from vpf_analysis.shared.plot_style import apply_style

        with apply_style():
            fig, ax = plt.subplots(figsize=(11, 6))
            for i, score in enumerate(scores):
                color = _TOLS[i % len(_TOLS)]
                sub = polars[polars["airfoil"] == score.airfoil].sort_values("alpha")
                if sub.empty:
                    continue
                ax.plot(sub["alpha"], sub["ld"], color=color, label=score.airfoil)
                ax.axvline(score.alpha_opt, color=color, linestyle="--", linewidth=1.0)
            ax.set_xlabel(r"$\alpha$ [°]", fontsize=13)
            ax.set_ylabel(r"$C_L/C_D$", fontsize=13)
            ax.set_title(
                f"Airfoil Selection — XFOIL 2D — {primary_label.replace('_', ' ').title()} Condition",
                fontsize=15, fontweight="bold",
            )
            ax.legend(
                loc="upper left", bbox_to_anchor=(1.02, 1.0),
                title="Airfoil", fontsize=11, title_fontsize=12,
            )
            fig.tight_layout()
            fig.savefig(out_dir / "polar_comparison.png")
            plt.close(fig)

    @staticmethod
    def _save_scores_csv(scores: list[AirfoilScore], out_dir: Path) -> None:
        rows = [dataclasses.asdict(s) for s in scores]
        pd.DataFrame(rows).to_csv(out_dir / "scores.csv", index=False)

    @staticmethod
    def _build_polar_df(
        polar_path: Path,
        airfoil: Airfoil,
        condition: SimulationCondition,
    ) -> pd.DataFrame:
        df = parse_polar_file(polar_path)
        if df.empty:
            return df
        df.insert(0, "airfoil", airfoil.name)
        df.insert(1, "condition", condition.name)
        df.insert(2, "mach", condition.mach_rel)
        df.insert(3, "re", condition.reynolds)
        return df
