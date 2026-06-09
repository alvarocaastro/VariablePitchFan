# Stage 3 README - Compressibility Correction

## Purpose of This Stage

Stage 3 converts raw low/reference-Mach XFOIL polars into corrected polars at the target relative Mach numbers for each flight condition. It accounts for compressibility effects that are important in a high-speed fan environment.

This stage answers: **how do the airfoil polars change when corrected from XFOIL reference Mach to the fan's operating Mach?**

## Inputs

| Input | Path | Description |
|---|---|---|
| Raw Stage 2 polars | `results/stage2_xfoil_simulations/polars/*.csv` | Baseline XFOIL polar data. |
| Target Mach values | `config/analysis_config.yaml`, `target_mach` | Mach per flight condition. |
| Airfoil geometry parameters | `config/analysis_config.yaml`, `airfoil_geometry` | Thickness ratio and Korn factor. |
| Reynolds and Ncrit metadata | Stage 2 polars/config | Preserved in corrected outputs. |

## Code Location

| File | Responsibility |
|---|---|
| `src/vpf_analysis/stage3_compressibility_correction/correction_service.py` | Orchestrates correction and writes plots/CSVs. |
| `src/vpf_analysis/stage3_compressibility_correction/prandtl_glauert.py` | Prandtl-Glauert correction. |
| `src/vpf_analysis/stage3_compressibility_correction/karman_tsien.py` | Karman-Tsien correction and corrected efficiency. |
| `src/vpf_analysis/stage3_compressibility_correction/critical_mach.py` | Critical Mach and wave-drag estimates. |

## Method

Stage 3 applies a correction chain:

1. Read one Stage 2 raw polar.
2. Apply Prandtl-Glauert correction to lift and moment.
3. Apply Karman-Tsien nonlinear correction.
4. Estimate wave-drag impact using critical Mach/drag-divergence logic.
5. Compute corrected drag and corrected lift-to-drag ratio.
6. Write a canonical `ld_corrected` column.
7. Generate per-case correction plots.

## Outputs

| Output | Path | Meaning |
|---|---|---|
| `corrected_polar.csv` | `results/stage3_compressibility_correction/{flight}/{section}/` | Corrected polar for one condition-section pair. |
| `corrected_plots.png` | Same per-case folder | Visual comparison of raw, PG, and KT behavior. |
| `correction_comparison_{section}.png` | `results/stage3_compressibility_correction/figures/` | Cross-condition corrected comparison for a blade section. |
| `finalresults_stage3.txt` | `results/stage3_compressibility_correction/` | Stage summary. |

## Current Key Results

The current result set contains **12 corrected polar files**, one for each combination of 4 flight conditions and 3 blade sections.

Example: `results/stage3_compressibility_correction/cruise/mid_span/corrected_polar.csv` contains 184 rows. Its detected `ld_corrected` range is approximately:

| Case | Minimum `ld_corrected` | Maximum `ld_corrected` | Average `ld_corrected` |
|---|---:|---:|---:|
| cruise / mid_span | -61.289 | 41.461 | 23.471 |

The maximum value aligns with the Stage 4 cruise/mid-span `max_efficiency`.

## Figure Interpretation

### Per-Case `corrected_plots.png`

This figure has two panels:

- `CL` versus `alpha`;
- `CL/CD` versus `alpha`.

It compares:

- raw XFOIL baseline at reference Mach;
- Prandtl-Glauert correction;
- Karman-Tsien correction at target Mach.

What it demonstrates:

- how compressibility changes lift slope and efficiency;
- whether corrected efficiency remains physically plausible;
- whether high-Mach conditions suffer an efficiency penalty.

How to interpret it:

- A large separation between raw and corrected curves means compressibility is important.
- A strong efficiency drop near the useful alpha range indicates drag-rise or wave-drag effects.
- Negative `CL/CD` values are possible at negative lift/drag combinations and should not be interpreted as useful operating points.

### `correction_comparison_{section}.png`

These figures compare corrected `CL` and `CL/CD` curves across flight conditions for one blade section.

What they demonstrate:

- condition-to-condition differences after correction;
- how target Mach changes the useful efficiency envelope;
- whether a section is more sensitive to high-Mach operation.

## Important Considerations

- `ld_corrected` is the canonical corrected efficiency column for downstream stages.
- Stage 4, Stage 5, and Stage 7 rely heavily on these corrected polars.
- Corrections are engineering models, not CFD.
- Target Mach is configured per flight condition, not per blade section in the current setup.

## Model Restrictions

| Restriction | Meaning |
|---|---|
| Analytical compressibility corrections | PG and KT are approximations, especially near transonic regimes. |
| Wave-drag model | Korn/Lock-style logic is empirical. |
| No shock-resolved analysis | Shock structure and fan-cascade transonic effects are not explicitly solved. |
| Discrete Mach values | The stage corrects configured conditions, not a continuous Mach sweep. |

## Downstream Role

Stage 3 produces the corrected polars consumed by Stage 4 metrics, Stage 5 kinematics, and Stage 7 SFC analysis.

