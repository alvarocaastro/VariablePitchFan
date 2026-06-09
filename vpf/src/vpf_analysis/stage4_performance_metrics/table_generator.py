"""
Table generation for thesis export.

Produces summary_table.csv — comprehensive: Re, Ncrit, (CL/CD)_max, alpha_opt, CL_max,
CL_at_opt, CD_at_opt, stall_margin, eff_at_design_alpha, eff_gain.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from vpf_analysis.stage4_performance_metrics.metrics import AerodynamicMetrics


def export_summary_table(
    metrics: list[AerodynamicMetrics],
    output_path: Path,
) -> None:
    """Export comprehensive summary table with all metrics to CSV."""
    rows = []
    for m in metrics:
        rows.append(
            {
                "flight_condition": m.flight_condition,
                "blade_section": m.blade_section,
                "reynolds": m.reynolds,
                "ncrit": m.ncrit,
                "max_efficiency": m.max_efficiency,
                "alpha_opt_deg": m.alpha_opt,
                "cl_max": m.cl_max,
                "cl_at_opt": m.cl_at_opt,
                "cd_at_opt": m.cd_at_opt,
                "stall_margin_deg": m.stall_margin,
                "cm_at_opt": m.cm_at_opt,
                "alpha_design_deg": m.alpha_design,
                "delta_alpha_deg": m.delta_alpha,
                "eff_at_design_alpha": m.eff_at_design_alpha,
                "eff_gain": m.eff_gain,
                "eff_gain_pct": m.eff_gain_pct,
            }
        )

    df = pd.DataFrame(rows)
    df = df.sort_values(["flight_condition", "blade_section"])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False, float_format="%.6f")


