# Setup and Execution

## Environment Requirements

| Requirement | Detail |
|---|---|
| Python | Python 3.10+ is recommended. Local cache artifacts show use of Python 3.12 and 3.13. |
| Operating system | The current workspace is Windows. Most project logic is Python and should be portable if XFOIL is available. |
| XFOIL | Required to regenerate Stage 1 and Stage 2 from scratch. |
| Python dependencies | Declared in `requirements.txt`. |

## Detected Dependencies

`requirements.txt` declares:

```text
numpy
pandas
matplotlib
pytest
pyyaml
rich
```

Risk detected: `src/vpf_analysis/stage6_reverse_thrust/reverse_thrust_core.py` imports `scipy.ndimage.uniform_filter1d` inside `_stall_margin()`. The current main Stage 6 flow only computes mechanism weight and does not call that path. If the full BEM reverse-thrust sweep is enabled, `scipy` should likely be added to `requirements.txt`. This is **pending confirmation** as an official dependency.

## Installation

From the repository root:

```powershell
cd C:\Users\Alvaro\Desktop\vpf\vpf
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If PowerShell blocks virtual-environment activation:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
.\.venv\Scripts\Activate.ps1
```

## XFOIL Configuration

`src/vpf_analysis/settings.py` searches for XFOIL in this order:

1. `XFOIL_EXE`
2. `XFOIL_EXECUTABLE`
3. `../XFOIL6.99/xfoil.exe`
4. `./XFOIL6.99/xfoil.exe`
5. `~/Downloads/XFOIL6.99/xfoil.exe`
6. `xfoil` on `PATH`

Windows example:

```powershell
$env:XFOIL_EXE = "C:\path\to\XFOIL6.99\xfoil.exe"
```

## Full Pipeline Execution

```powershell
python run_analysis.py
```

When executed from the beginning, the pipeline resets stage result directories. Copy any result set you want to preserve before a full rerun.

## Partial Execution

`run_analysis.py` supports stage ranges:

```powershell
python run_analysis.py --from-stage 3 --to-stage 7
```

| Option | Meaning |
|---|---|
| `--from-stage N` | Start from analysis stage N, where stages are numbered 1 through 7. Previous result files must already exist. |
| `--to-stage N` | Stop after analysis stage N. |

Important: the CLI has 8 steps because step 1 cleans results. Result folders are named Stage 1 to Stage 7.

## Direct Stage Execution

Some stages can be run directly:

```powershell
python -m vpf_analysis.stage5_pitch_kinematics.application.run_pitch_kinematics
python -m vpf_analysis.stage6_reverse_thrust.application.run_reverse_thrust
python -m vpf_analysis.stage7_sfc_analysis.application.run_sfc_analysis
```

If `vpf_analysis` is not importable from a checkout:

```powershell
$env:PYTHONPATH = ".\src"
python -m vpf_analysis.stage7_sfc_analysis.application.run_sfc_analysis
```

`run_analysis.py` and `run_sensitivity.py` insert `src` into `sys.path` themselves.

## Sensitivity Analysis

Requires existing Stage 3 and Stage 4 outputs:

```powershell
python run_sensitivity.py
```

Outputs:

- `results/sensitivity/sensitivity_table.csv`
- `results/sensitivity/sensitivity_heatmap.png`

## Tests

Run the full test suite:

```powershell
pytest
```

Useful targeted tests:

```powershell
pytest tests/test_sfc_model.py -v
pytest tests/test_prandtl_glauert.py -v
pytest tests/test_pipeline_contracts.py -v
```

## Important Paths

| Path | Purpose |
|---|---|
| `config/analysis_config.yaml` | Aerodynamic simulation parameters. |
| `config/engine_parameters.yaml` | Engine, mission, SFC, and reverse-thrust parameters. |
| `data/airfoils/` | XFOIL airfoil geometry input. |
| `results/` | Generated outputs. |
| `results/.polar_cache/` | Optional polar cache if `xfoil_cache: true`. |

## Common Execution Problems

| Problem | Likely Cause | Suggested Fix |
|---|---|---|
| `XFOIL executable not found` | XFOIL is not in any searched path. | Set `XFOIL_EXE` or add XFOIL to `PATH`. |
| Stage 7 writes no results | `summary_table.csv` from Stage 4 is missing. | Run the pipeline through Stage 4 first. |
| Stage 5 does nothing | Stage 2 or Stage 3 polars are missing. | Run earlier stages. |
| `ModuleNotFoundError: vpf_analysis` with `python -m` | `src` is not on `PYTHONPATH`. | Set `$env:PYTHONPATH = ".\src"`. |
| XFOIL convergence warnings | Difficult alpha range, high Reynolds, timeout, or profile behavior. | Review `analysis_config.yaml` XFOIL settings and Stage 2 summaries. |
| Reverse BEM path fails due to `scipy` | `scipy` is not declared in dependencies. | Install `scipy` if that path is intentionally used. |
