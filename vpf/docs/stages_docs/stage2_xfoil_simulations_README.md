# Stage 2 README - Final XFOIL Simulations and Pitch Map

## Purpose of This Stage

Stage 2 generates the final aerodynamic polars for the selected airfoil. It evaluates the selected profile across four flight conditions and three blade sections, then converts the optimum angle of attack into required blade pitch angles.

This stage answers: **how does the selected airfoil behave across the fan operating envelope, and how much pitch variation is required to keep it near optimum?**

## Inputs

| Input | Path | Description |
|---|---|---|
| Selected airfoil | Stage 1 output | The chosen airfoil, currently NACA 65-410. |
| Reynolds table | `config/analysis_config.yaml` | Reynolds values for each condition and blade section. |
| Ncrit table | `config/analysis_config.yaml` | XFOIL transition parameter per condition. |
| Alpha range | `config/analysis_config.yaml` | Main polar sweep, currently `-5` to `23` deg. |
| Fan geometry | `config/analysis_config.yaml` | RPM, radii, and axial velocities. |
| XFOIL executable | External | Generates final polars. |

## Code Location

| File | Responsibility |
|---|---|
| `src/vpf_analysis/stage2_xfoil_simulations/final_analysis_service.py` | Runs final XFOIL simulations and writes per-case plots. |
| `src/vpf_analysis/stage2_xfoil_simulations/pitch_map.py` | Computes pitch angles and VPF penalty figures. |
| `src/vpf_analysis/xfoil_runner.py` | Handles XFOIL execution, retries, and convergence detection. |

## Method

Stage 2:

1. Runs 12 XFOIL simulations:
   - 4 flight conditions: `takeoff`, `climb`, `cruise`, `descent`;
   - 3 blade sections: `root`, `mid_span`, `tip`.
2. Writes raw polar CSVs and XFOIL output files.
3. Detects `alpha_opt` from the `CL/CD` curve.
4. Detects stall behavior from the `CL` curve.
5. Computes velocity-triangle quantities:
   - `phi = atan(Va / U)`;
   - `beta = alpha_opt + phi`.
6. Writes the pitch map and VPF comparison plots.

## Outputs

| Output | Path | Meaning |
|---|---|---|
| `polars/{flight}_{section}.csv` | `results/stage2_xfoil_simulations/polars/` | Canonical raw polar CSVs. |
| `simulation_plots/{flight}/{section}/polar.csv` | Stage 2 nested folders | Per-case polar data colocated with plots. |
| `simulation_plots/{flight}/{section}/polar.dat` | Stage 2 nested folders | Raw XFOIL output file. |
| `pitch_map/blade_pitch_map.csv` | `results/stage2_xfoil_simulations/pitch_map/` | Required pitch angle by condition and section. |
| PNG figures | Stage 2 output folders | Per-case polar plots and VPF pitch-map plots. |
| `finalresults_stage2.txt` | `results/stage2_xfoil_simulations/` | Stage summary. |

## Current Key Results

Current pitch-map values:

| Flight | Section | `alpha_opt` | `phi` | `beta` |
|---|---|---:|---:|---:|
| takeoff | root | 7.150 | 54.015 | 61.165 |
| takeoff | mid_span | 7.000 | 36.125 | 43.125 |
| takeoff | tip | 7.600 | 23.236 | 30.836 |
| climb | root | 7.300 | 51.770 | 59.070 |
| climb | mid_span | 7.000 | 33.932 | 40.932 |
| climb | tip | 6.700 | 21.592 | 28.292 |
| cruise | root | 6.100 | 52.819 | 58.919 |
| cruise | mid_span | 7.300 | 34.943 | 42.243 |
| cruise | tip | 7.300 | 22.343 | 29.643 |
| descent | root | 7.300 | 48.394 | 55.694 |
| descent | mid_span | 7.000 | 30.830 | 37.830 |
| descent | tip | 7.450 | 19.345 | 26.795 |

These values show that the required pitch angle varies with flight condition and radial section.

## Figure Interpretation

### Per-Case `efficiency_plot.png`

Shows `CL/CD` versus angle of attack for one flight-condition and section pair.

It demonstrates:

- where the raw XFOIL polar predicts maximum 2D aerodynamic efficiency;
- whether the efficiency curve is smooth enough for peak detection;
- whether the selected operating point is plausible.

### Per-Case `cl_alpha_stall.png`

Shows `CL` versus angle of attack and marks the detected maximum lift/stall onset.

It demonstrates:

- available lift margin;
- whether `alpha_opt` is far enough from the detected stall region;
- whether XFOIL output remains physically smooth.

### Per-Case `polar_plot.png`

Shows `CL` versus `CD`.

It demonstrates:

- the shape of the aerodynamic polar;
- drag rise behavior in the raw XFOIL result;
- possible anomalies such as noisy drag data or convergence artifacts.

### `blade_pitch_map.png`

Shows required blade pitch angle `beta` by condition and section.

It demonstrates:

- pitch demand is not uniform along the blade span;
- VPF actuation requirements differ between root, mid-span, and tip;
- a single fixed cruise pitch cannot keep all conditions at their own optimum.

### `alpha_opt_evolution.png`

Shows how `alpha_opt` changes across flight phases for each section.

It demonstrates:

- the aerodynamic reason for variable pitch;
- phase-to-phase incidence variation;
- whether a condition has an unusually shifted optimum.

### `vpf_efficiency_{section}.png`

Shows `CL/CD` curves for all flight conditions within one blade section, with VPF operating points and the cruise fixed-pitch reference.

It demonstrates:

- how far non-cruise conditions move from their optimum under fixed pitch;
- whether VPF can recover a meaningful efficiency peak.

### `vpf_clcd_penalty.png`

Compares VPF optimum `CL/CD` against fixed cruise-pitch `CL/CD`.

It demonstrates:

- absolute efficiency difference;
- percentage retained efficiency under fixed pitch;
- which conditions and sections benefit most from pitch variation.

## Important Considerations

- Stage 2 polars are not yet corrected for the final target Mach; Stage 3 handles that.
- XFOIL may converge poorly at some alpha points. Review convergence warnings in the CLI and `finalresults_stage2.txt`.
- Raw `alpha_opt` values are later revised by Stage 4 and Stage 5 after compressibility and 3D corrections.
- The pitch map is a kinematic estimate based on representative radial sections.

## Model Restrictions

| Restriction | Meaning |
|---|---|
| 2D airfoil assumption | Does not represent full 3D fan flow. |
| XFOIL convergence dependence | Missing or noisy points can shift peaks. |
| Three-section representation | Root, mid-span, and tip are representative, not continuous. |
| No structural actuation model | `beta` is a required angle, not a detailed actuator design. |

## Downstream Role

Stage 2 provides raw polars to Stage 3 and pitch-map information used later in Stage 7 GE9X parametric analysis.

