"""Read GHS-Panel Wave 5 files directly from the downloaded zip.

The zip is never extracted into the repository, and no record-level data is written
anywhere that git tracks.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_config(path: str | Path | None = None) -> dict:
    path = Path(path) if path else PROJECT_ROOT / "config" / "assumptions.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def list_members(zip_path: str | Path) -> list[str]:
    with zipfile.ZipFile(zip_path) as z:
        return [n for n in z.namelist() if n.lower().endswith(".csv")]


def read_table(name: str, zip_path: str | Path | None = None) -> pd.DataFrame:
    """Read one survey file by its base name, e.g. 'sect8b_harvestw5'."""
    if zip_path is None:
        zip_path = PROJECT_ROOT / load_config()["data"]["zip_path"]
    target = name if name.lower().endswith(".csv") else f"{name}.csv"
    with zipfile.ZipFile(zip_path) as z:
        matches = [n for n in z.namelist() if Path(n).name.lower() == target.lower()]
        if len(matches) != 1:
            raise FileNotFoundError(f"{target}: found {len(matches)} matches in {zip_path}")
        with z.open(matches[0]) as f:
            return pd.read_csv(f, low_memory=False)
