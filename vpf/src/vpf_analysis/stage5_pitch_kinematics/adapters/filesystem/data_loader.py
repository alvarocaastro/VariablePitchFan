"""
data_loader.py
--------------
Carga los polares de Stage 2 y los polares corregidos de Stage 3
en DataFrames consolidados para el análisis de pitch y cinemática.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


class FilesystemDataLoader:
    """Carga los CSV de Stage 2 y Stage 3 en DataFrames."""

    @staticmethod
    def load_polar_data(polars_dir: Path) -> pd.DataFrame:
        """
        Carga los polares planos de Stage 2 (``polars/{condicion}_{seccion}.csv``).

        Añade columnas ``condition`` y ``section`` derivadas del nombre de archivo.
        """
        rows: list[pd.DataFrame] = []
        if not polars_dir.exists():
            return pd.DataFrame()

        for csv_path in polars_dir.glob("*.csv"):
            stem = csv_path.stem
            section = condition = None
            for suffix in ("mid_span", "root", "tip"):
                if stem.endswith(f"_{suffix}"):
                    section   = suffix
                    condition = stem[: -(len(suffix) + 1)].lower()
                    break
            if condition is None or section is None:
                continue

            df = pd.read_csv(csv_path)
            df["condition"] = condition
            df["section"]   = section
            rows.append(df)

        return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()

    @staticmethod
    def load_compressibility_data(stage3_dir: Path) -> pd.DataFrame:
        """
        Carga los polares corregidos de Stage 3
        (``{condicion}/{seccion}/corrected_polar.csv``).
        """
        rows: list[pd.DataFrame] = []
        if not stage3_dir.exists():
            return pd.DataFrame()

        for csv_path in stage3_dir.glob("*/*/corrected_polar.csv"):
            condition = csv_path.parent.parent.name.lower()
            section   = csv_path.parent.name
            df = pd.read_csv(csv_path)
            df["condition"] = condition
            df["section"]   = section
            rows.append(df)

        return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
