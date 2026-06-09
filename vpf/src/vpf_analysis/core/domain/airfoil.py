from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Airfoil:
    name: str
    family: str
    dat_path: Path
