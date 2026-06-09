# Stage 1 README - Airfoil Selection

## Purpose of This Stage

Stage 1 selects the airfoil that will be used by the rest of the VPF analysis pipeline. It compares candidate NACA airfoils under mission-weighted operating conditions and chooses the candidate with the best combined aerodynamic score.

This stage answers the question: **which 2D airfoil profile is the most suitable starting point for the fan-blade section analysis?**

## Inputs

| Input | Path | Description |
|---|---|---|
| Airfoil catalog | `config/airfoils.yaml` | Candidate names, `.dat` files, family, and comments. |
| Airfoil geometry | `data/airfoils/*.dat` | XFOIL-compatible coordinate files. |
| Selection setup | `config/analysis_config.yaml`, `selection` section | Mission-weighted conditions, alpha range, Reynolds, Ncrit. |
| XFOIL executable | External | Generates polar data for each airfoil-condition pair. |

## Code Location

| File | Responsibility |
|---|---|
| `src/vpf_analysis/stage1_airfoil_selection/airfoil_selection_service.py` | Orchestrates XFOIL runs, writes Stage 1 outputs, selects the best airfoil. |
| `src/vpf_analysis/stage1_airfoil_selection/scoring.py` | Computes and normalizes scores. |
| `src/vpf_analysis/adapters/xfoil/xfoil_parser.py` | Parses XFOIL polar files. |
| `src/vpf_analysis/xfoil_runner.py` | Runs XFOIL as an external subprocess. |

## Method

Stage 1 performs these steps:

1. Load candidate airfoils from `config/airfoils.yaml`.
2. Resolve mission-weighted selection conditions from `analysis_config.yaml`.
3. Run XFOIL for every airfoil-condition pair.
4. Parse polar data.
5. Compute a score based on:
   - maximum usable `CL/CD`;
   - selected `alpha_opt`;
   - stall angle;
   - stall margin;
   - robustness around the efficiency peak.
6. Normalize scores per condition.
7. Aggregate the normalized scores using condition weights.
8. Select the best airfoil.

The scoring intentionally searches for a usable efficiency peak rather than blindly trusting any low-alpha numerical maximum.

## Outputs

| Output | Path | Meaning |
|---|---|---|
| `scores.csv` | `results/stage1_airfoil_selection/airfoil_selection/scores.csv` | Ranking and score components for candidate airfoils. |
| `selected_airfoil.dat` | `results/stage1_airfoil_selection/airfoil_selection/selected_airfoil.dat` | Text marker containing the selected airfoil name. |
| `*_polar.txt` | `results/stage1_airfoil_selection/airfoil_selection/` | Raw XFOIL polar text files. |
| `polar_comparison.png` | `results/stage1_airfoil_selection/airfoil_selection/polar_comparison.png` | Visual comparison of candidate `CL/CD` curves. |
| `finalresults_stage1.txt` | `results/stage1_airfoil_selection/finalresults_stage1.txt` | Human-readable summary. |

## Current Key Results

Current detected ranking:

| Rank | Airfoil | `max_ld` | `alpha_opt` | Stall Angle | Stall Margin | Total Score |
|---:|---|---:|---:|---:|---:|---:|
| 1 | NACA 65-410 | 100.873 | 7.30 deg | 16.30 deg | 9.00 deg | 2.2245 |
| 2 | NACA 0012 | 96.583 | 9.85 deg | 17.95 deg | 8.10 deg | 0.8571 |
| 3 | NACA 63-215 | 93.225 | 8.05 deg | 17.95 deg | 9.90 deg | 0.5872 |
| 4 | NACA 65-210 | 92.804 | 7.90 deg | 15.10 deg | 7.20 deg | 0.4307 |

The selected airfoil is **NACA 65-410**.

## Figure Interpretation

### `polar_comparison.png`

This figure plots `CL/CD` versus angle of attack for the candidate airfoils in the primary selection condition.

How to read it:

- The horizontal axis is angle of attack, `alpha`.
- The vertical axis is aerodynamic efficiency, `CL/CD`.
- Each line represents one candidate airfoil.
- Vertical markers show the selected optimum angle for each candidate.

What it demonstrates:

- The selected profile is not chosen only by the highest visible peak.
- The scoring combines peak performance, stall margin, and robustness across configured conditions.
- A candidate with a good single-condition peak may still lose if it performs less consistently across the weighted mission conditions.

## Important Considerations

- Stage 1 depends on XFOIL convergence. A failed XFOIL run can produce `NaN` score components.
- The comparison figure shows the primary condition; the final score is mission-weighted.
- The `.dat` file named `selected_airfoil.dat` is a text marker in the current implementation, not a copied airfoil-coordinate file.
- Stage 1 uses 2D airfoil behavior. Later stages add compressibility and 3D effects.

## Model Restrictions

| Restriction | Meaning |
|---|---|
| XFOIL-based 2D analysis | Does not capture full rotating fan, cascade, shock, or tip effects. |
| Discrete selection conditions | The airfoil is not tested over a continuous flight envelope. |
| Empirical peak filtering | The second-peak logic avoids artifacts but remains a modeling choice. |
| No experimental validation in this stage | The selected airfoil is best within the configured model, not proven optimal in hardware. |

## Downstream Role

The selected airfoil feeds Stage 2. All final XFOIL simulations, compressibility corrections, kinematics, and SFC calculations depend on this initial selection.

