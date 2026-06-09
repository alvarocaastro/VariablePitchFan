# Fan de Paso Variable (VPF) como Habilitador de Ciclos UHBPR

Python pipeline for the aerodynamic and propulsion analysis of a variable-pitch fan (VPF) as an enabling technology for Ultra-High Bypass Ratio (UHBPR) turbofan engines. The project covers airfoil selection, XFOIL simulations, compressibility corrections, pitch kinematics with cascade and rotational effects, reverse-thrust mechanism weight, and specific fuel consumption (SFC) impact estimation.

The study compares two configurations: a BPR≈10 direct-drive fan (GE9X-class baseline, fan diameter 3.40 m) and a BPR=15 UHBPR fan (enabled by VPF, fan diameter 4.16 m), both with FPR=1.30 and 16 wide-chord blades. VPF alone improves SFC by optimising blade pitch at each flight condition; VPF combined with a higher bypass ratio (GTF architecture) achieves further gains through improved propulsive efficiency.

A fan pressure ratio of 1.30 demands very small blade incidence angles across the operating envelope. Without variable pitch, the reduced FPR required for UHBPR cycles forces the fan to operate close to stall during takeoff — the blade angle optimised for cruise leaves insufficient margin at high thrust. The VPF resolves this conflict: it adjusts blade pitch in real time so the fan operates at peak efficiency and safe stall margin at every flight condition, making FPR=1.30 viable without the stall-margin penalties that would otherwise limit UHBPR cycle performance.

## Documentation

The complete technical documentation is in [`docs/`](docs/README.md).

Recommended starting points:

| Document | Purpose |
|---|---|
| [`docs/overview.md`](docs/overview.md) | Functional overview of the project. |
| [`docs/setup_and_execution.md`](docs/setup_and_execution.md) | Installation, configuration, and execution steps. |
| [`docs/project_structure.md`](docs/project_structure.md) | Repository structure and file responsibilities. |
| [`docs/technical_architecture.md`](docs/technical_architecture.md) | Architecture, modules, data flow, and dependencies. |
| [`docs/data_documentation.md`](docs/data_documentation.md) | Input data, intermediate data, outputs, and assumptions. |
| [`docs/results.md`](docs/results.md) | Detailed explanation of generated tables, figures, and results. |
| [`docs/stages_docs/`](docs/stages_docs/) | Stage-by-stage README files with purpose, outputs, figures, key values, and model limitations. |
| [`docs/code_reference.md`](docs/code_reference.md) | Reference for scripts, modules, functions, and classes. |
| [`docs/maintenance.md`](docs/maintenance.md) | Maintenance guidance and extension points. |
| [`docs/glossary.md`](docs/glossary.md) | Domain terms, variables, and metrics. |
| [`docs/design_decisions.md`](docs/design_decisions.md) | Non-obvious technical decisions and rationale. |

## Quick Start

Requirements:

- Python 3.10 or newer.
- XFOIL available through `PATH`, `XFOIL_EXE`, or `XFOIL_EXECUTABLE`.

Install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Run the full pipeline:

```powershell
python run_analysis.py
```

Run a stage range:

```powershell
python run_analysis.py --from-stage 3 --to-stage 7
```

Run the sensitivity analysis after the main results exist:

```powershell
python run_sensitivity.py
```

Run tests:

```powershell
pytest
```

## Main Workflow

The pipeline writes results under `results/`:

```text
results/
  stage1_airfoil_selection/
  stage2_xfoil_simulations/
  stage3_compressibility_correction/
  stage4_performance_metrics/
  stage5_pitch_kinematics/
  stage6_reverse_thrust/
  stage7_sfc_analysis/
  sensitivity/
```

High-level stages:

1. Select a candidate NACA airfoil using XFOIL and mission-weighted scoring.
2. Generate final XFOIL polars for four flight conditions and three blade sections.
3. Apply compressibility corrections and write corrected polars.
4. Compute aerodynamic metrics and fixed-pitch penalties.
5. Analyze pitch kinematics, cascade effects, 3D rotational corrections, blade twist, and stage loading.
6. Estimate reverse-thrust mechanism weight versus a conventional cascade reverser.
7. Estimate SFC reduction, mission fuel burn, and GE9X parametric behavior.

## Key Inputs

| Path | Purpose |
|---|---|
| `config/analysis_config.yaml` | Aerodynamic setup, fan geometry, Reynolds, Mach, Ncrit, XFOIL settings. |
| `config/engine_parameters.yaml` | Engine baseline, SFC model, mission profile, reverse-thrust assumptions. |
| `config/airfoils.yaml` | Candidate airfoil catalog. |
| `data/airfoils/*.dat` | Airfoil coordinate files consumed by XFOIL. |

## Important Notes

- `results/` is generated output and is ignored by Git except for `.gitkeep`.
- `docs/` intentionally contains Markdown files only.
- External reference PDFs and auxiliary reference material are stored in `references/`.
- Stage numbering in `run_analysis.py` now matches the analysis stages: `1` through `7`. Cleanup runs automatically before Stage 1 during a full run.
- The reverse-thrust stage currently documents a mechanism-weight and SFC trade study; full aerodynamic reverse-thrust validation is pending higher-fidelity data.

## License

See [`LICENSE`](LICENSE).
