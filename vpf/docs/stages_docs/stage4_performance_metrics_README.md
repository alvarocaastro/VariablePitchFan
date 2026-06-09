# Stage 4 README - Aerodynamic Performance Metrics

## Purpose of This Stage

Stage 4 converts corrected polars into interpretable aerodynamic performance metrics. It identifies optimum operating points, compares VPF operation with fixed-pitch operation, and generates figures that explain where the VPF benefit comes from.

This stage answers: **what aerodynamic gain does variable pitch provide after compressibility corrections?**

## Inputs

| Input | Path | Description |
|---|---|---|
| Corrected polars | `results/stage3_compressibility_correction/{flight}/{section}/corrected_polar.csv` | Stage 3 output. |
| Reynolds and Ncrit tables | `config/analysis_config.yaml` | Metadata written into performance tables. |
| Fan velocity data | `config/analysis_config.yaml` | Used to compute fixed-pitch incidence from velocity triangles. |

## Code Location

| File | Responsibility |
|---|---|
| `src/vpf_analysis/stage4_performance_metrics/metrics.py` | Computes aerodynamic metrics and fixed-pitch reference. |
| `src/vpf_analysis/stage4_performance_metrics/table_generator.py` | Writes CSV tables. |
| `src/vpf_analysis/stage4_performance_metrics/plots.py` | Generates Stage 4 figures. |

## Method

Stage 4:

1. Reads all Stage 3 corrected polars.
2. Resolves the correct efficiency column, normally `ld_corrected`.
3. Finds a usable optimum operating point with second-peak and minimum-lift logic.
4. Computes:
   - `max_efficiency`;
   - `alpha_opt_deg`;
   - `cl_max`;
   - `cl_at_opt`;
   - `cd_at_opt`;
   - `stall_margin_deg`;
   - `cm_at_opt`.
5. Computes fixed-pitch reference behavior using cruise blade angle and off-design velocity triangles.
6. Computes VPF gain:
   - `eff_at_design_alpha`;
   - `eff_gain`;
   - `eff_gain_pct`.
7. Exports tables and figures.

## Outputs

| Output | Path | Meaning |
|---|---|---|
| `summary_table.csv` | `results/stage4_performance_metrics/tables/summary_table.csv` | Main aerodynamic performance table. |
| `clcd_max_by_section.csv` | `results/stage4_performance_metrics/tables/clcd_max_by_section.csv` | Focused optimum `CL/CD` table. |
| Stage 4 figures | `results/stage4_performance_metrics/figures/` | Efficiency, lift/drag, and map figures. |
| `finalresults_stage4.txt` | `results/stage4_performance_metrics/` | Stage summary. |

## Current Key Results

Current performance metrics:

| Condition | Section | `max_efficiency` | `alpha_opt` | Stall Margin | `eff_gain_pct` |
|---|---|---:|---:|---:|---:|
| climb | root | 48.671 | 3.10 deg | 13.95 deg | 18.79% |
| climb | mid_span | 50.095 | 3.10 deg | 14.85 deg | 16.17% |
| climb | tip | 51.077 | 3.10 deg | 15.45 deg | 14.99% |
| cruise | root | 38.655 | 8.20 deg | 7.80 deg | 0.00% |
| cruise | mid_span | 41.461 | 9.10 deg | 7.95 deg | 0.00% |
| cruise | tip | 43.218 | 9.55 deg | 8.10 deg | 0.00% |
| descent | root | 116.288 | 4.90 deg | 11.85 deg | 88.79% |
| descent | mid_span | 129.512 | 5.20 deg | 12.45 deg | 107.57% |
| descent | tip | 139.273 | 5.35 deg | 12.90 deg | 95.52% |
| takeoff | root | 44.072 | 9.40 deg | 8.55 deg | 3.69% |
| takeoff | mid_span | 45.824 | 9.40 deg | 9.45 deg | 1.82% |
| takeoff | tip | 46.864 | 10.00 deg | 9.30 deg | 0.46% |

Key interpretation:

- Cruise is the fixed-pitch reference, so `eff_gain_pct` is zero by definition.
- Descent shows the largest modeled VPF aerodynamic gain.
- Takeoff shows comparatively small corrected efficiency gain in the current results.

## Figure Interpretation

### `compressibility_comparison.png`

Shows corrected `CL/CD` versus `alpha` for the summary section, with VPF optimum and fixed-pitch operating points.

It demonstrates:

- the efficiency penalty of using a fixed cruise reference outside cruise;
- how much `delta_alpha` is required;
- which conditions gain most from VPF operation.

### `polar_efficiency_{flight}_{section}.png`

One figure per condition-section pair.

It demonstrates:

- corrected aerodynamic efficiency curve;
- selected optimum point;
- whether the peak is well-defined.

### `lift_drag_curves_{flight}.png`

One figure per flight condition, comparing root, mid-span, and tip.

It demonstrates:

- radial differences in corrected efficiency;
- lift behavior by section;
- whether one section dominates performance limitations.

### `efficiency_map_{section}.png`

Contour map of `CL/CD` in `alpha` versus Mach space for one section.

It demonstrates:

- the approximate operating envelope;
- where each flight condition sits relative to efficient regions;
- how strongly Mach affects each section.

Important limitation: the map interpolates across discrete flight-condition Mach values; it is not a dedicated dense Mach sweep.

## Important Considerations

- Stage 4 is the main bridge between corrected aerodynamics and SFC analysis.
- `summary_table.csv` is consumed by Stage 7.
- Fixed-pitch reference is based on cruise blade angle and velocity triangles, not simply a constant `alpha` copied everywhere.
- Very large `eff_gain_pct` values should be interpreted in the context of fixed-pitch off-design penalty, not as absolute fan efficiency gain.

## Model Restrictions

| Restriction | Meaning |
|---|---|
| Three-section approximation | Does not integrate a continuous blade span. |
| Corrected polar dependency | All metrics inherit Stage 3 correction assumptions. |
| Peak selection model | Optimum depends on filters and peak logic. |
| Fixed-pitch reference model | Based on simplified velocity triangles. |

## Downstream Role

Stage 4 feeds Stage 7 SFC analysis directly and also supports interpretation of Stage 5 kinematic refinements.

