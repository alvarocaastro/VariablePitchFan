# Data Documentation

## Input Data

### Aerodynamic Configuration

Path: `config/analysis_config.yaml`

| Section | Key Fields | Use |
|---|---|---|
| `reference_mach` | `0.2` | Baseline Mach used for XFOIL before later corrections. |
| `target_mach` | `takeoff`, `climb`, `cruise`, `descent` | Target relative Mach for Stage 3 corrections. |
| `reynolds` | condition x section | XFOIL Reynolds number for each case. |
| `ncrit` | condition | XFOIL transition parameter. |
| `alpha` | `min`, `max`, `step` | Main angle-of-attack sweep. |
| `selection` | weighted conditions | Stage 1 airfoil selection setup. |
| `xfoil` | iterations, timeouts, retries | XFOIL robustness settings. |
| `fan_geometry` | RPM, radii, axial velocity | Kinematics and SFC calculations. |
| `blade_geometry` | blade count, solidity, camber | Cascade, twist, and 3D corrections. |
| `airfoil_geometry` | `thickness_ratio`, `korn_kappa` | Wave drag and critical Mach calculations. |

### Engine and Mission Configuration

Path: `config/engine_parameters.yaml`

| Field | Use |
|---|---|
| `baseline_sfc` | Cruise reference SFC. |
| `fan_efficiency` | Baseline fan efficiency. |
| `bypass_ratio` | Propulsion sensitivity factor `BPR/(1+BPR)`. |
| `sfc_multipliers` | Per-flight-phase SFC scaling. |
| `profile_efficiency_transfer` | `tau`, the transfer coefficient from 2D profile gain to fan efficiency. |
| `mission` | Phase duration, thrust fraction, design thrust, fuel price. |
| `reverse_thrust` | Mechanism weight and conventional reverser assumptions. |

### Airfoil Catalog

Path: `config/airfoils.yaml`

| Airfoil | File | Family |
|---|---|---|
| NACA 65-210 | `naca_65-210.dat` | NACA 65-series |
| NACA 65-410 | `naca_65-410.dat` | NACA 65-series |
| NACA 63-215 | `naca_63-215.dat` | NACA 63-series |
| NACA 0012 | `naca_0012.dat` | NACA 00-series |

### Airfoil Coordinate Files

Path: `data/airfoils/*.dat`

Expected format: XFOIL-compatible `.dat` airfoil files containing a name/header and coordinate pairs. Airfoil file parsing behavior is covered by `tests/test_airfoil_reader.py`.

## Main Intermediate Data

| Stage | File | Main Columns |
|---|---|---|
| Stage 1 | `scores.csv` | `airfoil`, `max_ld`, `alpha_opt`, `stall_alpha`, `stability_margin`, `robustness_ld`, `total_score` |
| Stage 2 | `polars/{flight}_{section}.csv` | `alpha`, `cl`, `cd`, `cm`, `ld`, `re`, `ncrit` |
| Stage 2 | `pitch_map/blade_pitch_map.csv` | `flight`, `section`, `alpha_opt`, `phi_deg`, `beta_deg` |
| Stage 3 | `{flight}/{section}/corrected_polar.csv` | `alpha`, `cl`, `cl_pg`, `cl_kt`, `cd`, `cd_corrected`, `ld_pg`, `ld_corrected`, `mach_target`, `re`, `ncrit` |
| Stage 4 | `tables/summary_table.csv` | Aerodynamic metrics and fixed-pitch reference fields. |
| Stage 5 | `tables/*.csv` | Cascade, rotation, incidence, twist, off-design, loading, kinematics. |
| Stage 6 | `tables/mechanism_weight.csv` | Mechanism weights and SFC impacts. |
| Stage 7 | `tables/*.csv` | SFC, sensitivity, mission fuel burn, GE9X sweep. |

## Transformations

| Transformation | Location | Description |
|---|---|---|
| XFOIL parsing | `adapters/xfoil/xfoil_parser.py` | Converts XFOIL text output into DataFrames. |
| `ld` computation | XFOIL parser and postprocessing | Lift-to-drag ratio `CL/CD`. |
| Second-peak selection | `aerodynamics_utils.py`, `scoring.py`, `metrics.py` | Avoids low-incidence laminar-bubble artifacts. |
| Prandtl-Glauert correction | `prandtl_glauert.py` | Compressibility correction for `CL` and `CM`. |
| Karman-Tsien correction | `karman_tsien.py` | Nonlinear compressibility correction. |
| Korn/wave drag | `critical_mach.py` | Adds wave-drag increment when applicable. |
| Fixed-pitch enrichment | `metrics.enrich_with_cruise_reference()` | Computes fixed-pitch incidence, `delta_alpha`, and efficiency gain. |
| Weinig/Carter cascade | `pitch_kinematics_core.py` | Corrects lift and flow deviation due to cascade effects. |
| Snel/Du-Selig 3D rotation | `pitch_kinematics_core.py` | Estimates rotational lift effects. |
| SFC conversion | `sfc_core.py` | Converts aerodynamic ratios into fan efficiency and SFC estimates. |

## Existing Validations

| Validation | Location |
|---|---|
| Required file and directory checks | `validation/validators.py` |
| Required CSV columns | `require_csv_columns()` |
| Physical ranges | `validate_physical_ranges()` |
| Alpha range | `validate_alpha_range()` |
| Polar quality | `validate_polar_quality()` |
| XFOIL convergence | `check_xfoil_convergence()` |
| Stage contracts | `pipeline/contracts.py` |

## Output Data

Outputs are documented in detail in `results.md`. In summary:

- CSV files are numerical tables for analysis and traceability.
- PNG files are diagnostic, comparison, validation, or presentation figures.
- TXT files are stage summaries.
- TEX is a Stage 7 LaTeX table export.

## Data Limitations and Assumptions

| Limitation | Status |
|---|---|
| Flight conditions are discrete, not a continuous mission profile. | Confirmed. |
| Reynolds numbers are fixed in YAML and not automatically recomputed when geometry changes. | Confirmed. |
| Polars depend on XFOIL version and convergence behavior. | Confirmed. |
| Deep reverse-thrust extrapolation uses Viterna-Corrigan if the BEM path is enabled. | Present in code, pending experimental validation. |
| `results/` is ignored by Git. | Confirmed in `.gitignore`. |

