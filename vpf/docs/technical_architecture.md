# Technical Architecture

## Architectural Overview

The project is organized as a staged analysis pipeline with a clear separation between:

- YAML configuration.
- Domain dataclasses and contracts.
- External adapters.
- Stage-level calculation services.
- Postprocessing, validation, and plotting.

Stages exchange data primarily through files in `results/`. This makes intermediate results inspectable and allows later stages to be rerun from existing artifacts.

## Main Components

| Component | Path | Responsibility |
|---|---|---|
| Orchestrator | `run_analysis.py` | Runs the complete pipeline or a selected range. |
| Sensitivity script | `run_sensitivity.py` | Sweeps `tau` and RPM deviation using existing outputs. |
| Settings | `src/vpf_analysis/settings.py` | Paths, XFOIL discovery, airfoil catalog, typed settings. |
| YAML loader | `src/vpf_analysis/config_loader.py` | Lightweight accessors for configuration values. |
| Config domain | `src/vpf_analysis/config/domain.py` | Dataclasses and physical constants. |
| XFOIL runner | `src/vpf_analysis/xfoil_runner.py` | Subprocess execution, retries, cache, convergence detection. |
| Contracts | `src/vpf_analysis/pipeline/contracts.py` | Stage output validation. |
| Validation | `src/vpf_analysis/validation/validators.py` | File, CSV, polar, range, and convergence checks. |
| Postprocessing | `src/vpf_analysis/postprocessing/` | Summary files, CLI tables, LaTeX export, aerodynamic helpers. |

## Data Flow

```text
config/*.yaml + data/airfoils/*.dat
        |
        v
Stage 1: airfoil selection
        |
        v
Stage 2: final XFOIL polars and pitch map
        |
        v
Stage 3: compressibility-corrected polars
        |
        v
Stage 4: aerodynamic metrics and performance figures
        |
        v
Stage 5: cascade, rotation, twist, kinematics, loading
        |
        v
Stage 6: reverse-thrust mechanism weight
        |
        v
Stage 7: SFC, mission fuel burn, GE9X parametric analysis
```

## Internal Dependencies

| From | To | Dependency Type |
|---|---|---|
| `run_analysis.py` | All stages | Orchestration. |
| Stages 1 and 2 | `adapters/xfoil`, `xfoil_runner.py` | XFOIL execution. |
| Stages 3 to 7 | `config_loader.py`, `settings.py` | Shared parameters. |
| Stages 4 to 7 | `postprocessing/aerodynamics_utils.py` | Peak selection and efficiency-column resolution. |
| Stage 7 | Stage 3, Stage 4, Stage 5 output files | Reads CSV artifacts from disk. |
| `stage_summary_generator.py` | `results/` outputs | Reads outputs and writes text summaries. |

## External Dependencies

| Dependency | Use |
|---|---|
| `numpy` | Numerical arrays, interpolation, parameter sweeps. |
| `pandas` | CSV I/O and tabular transformations. |
| `matplotlib` | PNG figure generation. |
| `pyyaml` | YAML configuration loading. |
| `rich` | Command-line progress and tables. |
| `pytest` | Tests. |
| XFOIL | 2D viscous airfoil polar generation. |
| `scipy` | Imported inside reverse-thrust BEM support, but not declared. Pending confirmation. |

## Stage Architecture

| Stage | Internal Design |
|---|---|
| Stage 1 | `AirfoilSelectionService` runs XFOIL for airfoil-condition pairs; `scoring.py` computes and aggregates scores. |
| Stage 2 | `FinalAnalysisService` creates final polars and per-case plots; `pitch_map.py` converts `alpha_opt` to pitch angle. |
| Stage 3 | `CompressibilityCorrectionService` coordinates PG and Karman-Tsien corrections; `critical_mach.py` estimates drag rise. |
| Stage 4 | `metrics.py` produces `AerodynamicMetrics`; `table_generator.py` exports CSVs; `plots.py` generates figures. |
| Stage 5 | `pitch_kinematics_core.py` holds pure calculation functions; `run_pitch_kinematics.py` orchestrates outputs. |
| Stage 6 | `run_reverse_thrust.py` currently focuses on mechanism weight; BEM-related functions exist in `reverse_thrust_core.py`. |
| Stage 7 | `sfc_core.py` computes SFC and mission effects; `engine/ge9x_analysis.py` runs a GE9X parametric sweep. |

## Detected Technical Decisions

- Aerodynamic configuration and engine/mission configuration are split into separate YAML files.
- Blade solidity is the primary cascade geometry input.
- Reynolds numbers are explicitly provided in YAML rather than recomputed at runtime.
- `ld_corrected` is the canonical corrected-efficiency column.
- The pipeline uses second-peak logic to avoid low-incidence XFOIL artifacts.
- Stages communicate via files for traceability and restartability.
- SFC conversion uses damping factors and caps to avoid over-crediting 2D gains.

## Technical Risks

| Risk | Impact | Recommendation |
|---|---|---|
| Strong dependency on XFOIL | Stages 1 and 2 cannot be reproduced without it. | Document the XFOIL version and executable path. |
| XFOIL convergence warnings | Incomplete polars or unreliable peaks. | Review Stage 2 summaries and convergence logs. |
| Missing `scipy` dependency | Full reverse BEM path may fail. | Add `scipy` if that path becomes supported. |
| `results/` ignored by Git | Generated outputs are not versioned by default. | Archive final result sets explicitly. |
| Stage numbering ambiguity | CLI step numbers differ from result-stage numbers. | Preserve the mapping in documentation. |
| Empirical models | Carter, Snel, Du-Selig, and SFC caps contain assumptions. | Validate against references or experimental data before design decisions. |

