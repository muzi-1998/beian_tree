import numpy as np
import pandas as pd

from src.d3_physical.reference_eligibility import production_calibration_mask_from_raw


def test_neutral_admission_is_score_free_and_preserves_observed_stasis(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Other dimension workbook must not be read")
    monkeypatch.setattr(pd, "read_excel", forbidden)
    index = pd.date_range("2025-08-01", periods=120, freq="min")
    values = pd.Series(1.0, index=index)
    temperature = pd.Series(20.0, index=index)
    imputed = pd.Series(False, index=index)
    valid = pd.Series(True, index=index)
    mask = production_calibration_mask_from_raw(values, temperature, imputed=imputed, time_valid=valid)
    assert mask.all()
    values.iloc[0:4] = [np.nan, -0.01, 21, 1]
    imputed.iloc[3] = True
    temperature.iloc[4] = np.nan
    valid.iloc[5] = False
    mask = production_calibration_mask_from_raw(values, temperature, imputed=imputed, time_valid=valid)
    assert not mask.iloc[:6].any()
    assert mask.iloc[6:].all()


def test_reference_rejects_insufficient_raw_hour_not_low_variance():
    index = pd.date_range("2025-08-01", periods=60, freq="min")
    values = pd.Series(np.nan, index=index)
    values.iloc[:29] = 0.0
    args = dict(imputed=pd.Series(False, index=index), time_valid=pd.Series(True, index=index))
    temperature = pd.Series(20.0, index=index)
    assert not production_calibration_mask_from_raw(values, temperature, **args).any()
    values.iloc[29] = 0.0
    assert production_calibration_mask_from_raw(values, temperature, **args).sum() == 30
