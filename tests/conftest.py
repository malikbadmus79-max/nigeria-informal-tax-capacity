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


def _month_flags(months):
    """s8q9__0..s8q9__16 flags; None gives all-missing flags."""
    return {f"s8q9__{k}": (float("nan") if months is None else float(k in months)) for k in range(17)}


@pytest.fixture
def audit_frames():
    """Synthetic sect8b, sect8c and secta with known answers for the audit.

    Four enterprises in three households, plus one household without an enterprise.
    Household 3 has no weight. ea code 10 is reused in two states, as in the real file.
    Households 1 and 2 were interviewed in February 2024, households 3 and 4 in March 2024.
    """
    nan = float("nan")
    feb_window = list(range(3, 15))  # March 2023 to February 2024, the window for a February 2024 interview
    common = dict(sector="2. RURAL", s8q10="1. HOME", s8q11="2. NO", s8q11b="2. NO")
    ent = pd.DataFrame([
        {**common, "zone": "1. X", "state": "1. A", "lga": "1. L1", "ea": 10, "hhid": 1, "ent_id": 1,
         "s8q3": "1. CURRENTLY OPERATING", "s8q2b": "4711. Retail", "s8q11b": "1. YES",
         "s8q6_1": 1, "s8q6_2": nan, "s8q29": 100, "s8q30": 50, **_month_flags(feb_window)},
        {**common, "zone": "1. X", "state": "1. A", "lga": "1. L1", "ea": 10, "hhid": 1, "ent_id": 2,
         "s8q3": "1. CURRENTLY OPERATING", "s8q2b": "4711. Retail", "s8q10": "4. MARKET", "s8q11": "1. YES",
         "s8q6_1": 1, "s8q6_2": 2.0, "s8q29": 0, "s8q30": 0, **_month_flags([0, 1, 16])},
        {**common, "zone": "2. Y", "state": "2. B", "lga": "2. L2", "ea": 10, "hhid": 2, "ent_id": 1,
         "s8q3": "3. CLOSED, TEMPORARILY", "s8q2b": "4921. Transport",
         "s8q6_1": 1, "s8q6_2": nan, "s8q29": 200, "s8q30": -10, **_month_flags([4, 5, 6, 7, 8, 9])},
        {**common, "zone": "1. X", "state": "1. A", "lga": "1. L3", "ea": 11, "hhid": 3, "ent_id": 1,
         "s8q3": "1. CURRENTLY OPERATING", "s8q2b": "1410. Apparel",
         "s8q6_1": 2, "s8q6_2": nan, "s8q29": 50, "s8q30": 80, **_month_flags(None)},
    ])
    workers = pd.DataFrame({
        "hhid": [1, 1, 2, 3], "ent_id": [1, 2, 1, 1], "indiv": [1, 1, 1, 2],
        "s8q12bnb": [12, 3, 6, 10],
    })
    cover = pd.DataFrame({
        "zone": ["1. X", "2. Y", "1. X", "2. Y"],
        "state": ["1. A", "2. B", "1. A", "2. B"],
        "lga": ["1. L1", "2. L2", "1. L3", "2. L4"],
        "ea": [10, 10, 11, 12],
        "hhid": [1, 2, 3, 4],
        "cluster": [101, 102, 103, 104],
        "strata": [1, 2, 1, 2],
        "wt_wave5": [500.0, 700.0, nan, 300.0],
        "wt_cross_wave5": [500.0, 700.0, nan, 300.0],
        "interview_result": ["1. COMPLETE"] * 4,
        "InterviewStart": ["2024-02-10T09:00:00", "2024-02-11T09:00:00",
                           "2024-03-05T09:00:00", "2024-03-06T09:00:00"],
    })
    return ent, workers, cover


@pytest.fixture
def audit_zip(tmp_path, audit_frames):
    ent, workers, cover = audit_frames
    path = tmp_path / "audit.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("Post Harvest Wave 5/Household/sect8b_harvestw5.csv", ent.to_csv(index=False))
        z.writestr("Post Harvest Wave 5/Household/sect8c_harvestw5.csv", workers.to_csv(index=False))
        z.writestr("Post Harvest Wave 5/Household/secta_harvestw5.csv", cover.to_csv(index=False))
    return path


@pytest.fixture
def design_frames():
    """Synthetic sect8b and secta with a usable design: 24 households in 8 PSUs (3 households each) and
    2 strata, about 29 enterprises including closed, two-owner and March-interviewed ones."""
    nan = float("nan")
    hh_rows, ent_rows, j = [], [], 0
    for i in range(24):
        zone = 1 if i < 12 else 2
        march = i % 4 == 3
        hh_rows.append({
            "zone": f"{zone}. Z{zone}", "state": f"{zone}. S{zone}", "lga": f"{zone}. L{zone}", "ea": i // 3,
            "sector": "1. URBAN" if (i // 3) % 2 == 0 else "2. RURAL", "hhid": i + 1, "strata": zone,
            "wt_cross_wave5": 100.0 + 10 * i,
            "InterviewStart": "2024-03-05T09:00:00" if march else "2024-02-10T09:00:00",
        })
        window = list(range(4, 16)) if march else list(range(3, 15))
        for ent_id in ([1, 2] if i % 5 == 0 else [1]):
            status = ("3. CLOSED, TEMPORARILY" if j % 7 == 6 else
                      "4. CLOSED, SEASONALLY" if j % 11 == 10 else "1. CURRENTLY OPERATING")
            months = window[: 12 - (j % 3) * 2]
            ent_rows.append({
                "zone": hh_rows[-1]["zone"], "state": hh_rows[-1]["state"], "lga": hh_rows[-1]["lga"],
                "ea": hh_rows[-1]["ea"], "sector": hh_rows[-1]["sector"], "hhid": i + 1, "ent_id": ent_id,
                "s8q2b": "4711. Retail", "s8q3": status, "s8q10": "1. HOME",
                "s8q11": "1. YES" if j % 5 == 0 else "2. NO", "s8q11b": "1. YES" if j % 2 == 0 else "2. NO",
                "s8q6_1": 1, "s8q6_2": 2.0 if j % 4 == 0 else nan,
                "s8q29": 200000, "s8q30": 20000 + 9000 * (j % 10), **_month_flags(months),
            })
            j += 1
    return pd.DataFrame(ent_rows), pd.DataFrame(hh_rows)
