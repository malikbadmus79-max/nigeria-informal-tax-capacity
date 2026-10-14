"""Synthetic fixtures. Tests never touch the real survey, so they run anywhere, including CI."""
import zipfile

import pandas as pd
import pytest


@pytest.fixture
def fake_zip(tmp_path):
    path = tmp_path / "fake.zip"
    ent = pd.DataFrame({"hhid": [1, 2], "ent_id": [1, 1], "s8q30": [100000, 50000]})
    cover = pd.DataFrame({"hhid": [1, 2], "ea": [10, 11], "strata": [1, 1], "wt_wave5": [500.0, 700.0]})
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("Post Harvest Wave 5/Household/sect8b_harvestw5.csv", ent.to_csv(index=False))
        z.writestr("Post Harvest Wave 5/Household/secta_harvestw5.csv", cover.to_csv(index=False))
    return path
