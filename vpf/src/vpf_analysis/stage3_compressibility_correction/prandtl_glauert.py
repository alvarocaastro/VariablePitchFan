"""
Prandtl–Glauert compressibility correction model.

This correction is valid as a first-order approximation for subsonic compressible
flow. It corrects lift and pressure-related coefficients but drag requires
separate treatment.

References
----------
Prandtl, L. (1927). Ges. Abh. 346-353; Glauert, H. (1928). ARCR&M 1135.
    Linear compressibility rule: C = C_incomp / β, β = √(1 − M²).
Anderson, J.D. (2017). Fundamentals of Aerodynamics, 6th ed., §11.4, eq. 11.51.
"""

from __future__ import annotations

import math

import pandas as pd

from vpf_analysis.stage3_compressibility_correction.compressibility_case import (
    CompressibilityCase,
)


class PrandtlGlauertModel:
    @staticmethod
    def compute_beta(mach: float) -> float:
        # Prandtl (1927) / Glauert (1928); Anderson (2017) eq. 11.51 — β = √(1 − M²)
        if mach >= 1.0:
            raise ValueError(f"Mach {mach} >= 1.0: correction not valid for supersonic")
        return math.sqrt(1.0 - mach * mach)

    def correct_polar(
        self, df: pd.DataFrame, case: CompressibilityCase
    ) -> pd.DataFrame:
        """Apply Prandtl–Glauert correction; adds cl_pg, cm_pg, cd_corrected, ld_pg."""
        beta_ref = self.compute_beta(case.reference_mach)
        beta_target = self.compute_beta(case.target_mach)

        correction_factor = beta_ref / beta_target

        df_corrected = df.copy()

        # Correct lift coefficient (Prandtl–Glauert applies to lift/pressure)
        df_corrected["cl_pg"] = df["cl"] * correction_factor

        # Correct pitching moment (same PG factor as CL — both arise from pressure)
        if "cm" in df.columns:
            df_corrected["cm_pg"] = df["cm"] * correction_factor

        # Drag: PG has no drag correction — wave drag added by KarmanTsienModel
        # Keep original CD here; KarmanTsienModel will overwrite cd_corrected
        df_corrected["cd_corrected"] = df["cd"]

        # Corrected efficiency (PG CL / original CD — updated later by K-T)
        df_corrected["ld_pg"] = (
            df_corrected["cl_pg"] / df_corrected["cd_corrected"]
        )

        # Store corrected Mach
        df_corrected["mach_target"] = case.target_mach

        return df_corrected
