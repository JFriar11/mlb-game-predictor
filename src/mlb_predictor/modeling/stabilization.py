import numpy as np
import pandas as pd


def stabilize_small_samples(frame: pd.DataFrame) -> pd.DataFrame:
    """Apply fixed, leakage-safe shrinkage and clipping without fitting future data."""
    result = frame.copy()

    lineup_weight = result["lineup_prior_pa"] / (result["lineup_prior_pa"] + 200.0)
    result["lineup_on_base_rate"] = (
        lineup_weight * result["lineup_on_base_rate"] + (1 - lineup_weight) * 0.320
    ).clip(0.180, 0.450)
    result["lineup_strikeout_rate"] = (
        lineup_weight * result["lineup_strikeout_rate"] + (1 - lineup_weight) * 0.225
    ).clip(0.080, 0.450)
    result["lineup_home_run_rate"] = (
        lineup_weight * result["lineup_home_run_rate"] + (1 - lineup_weight) * 0.030
    ).clip(0.005, 0.100)

    starter_weight = result["starter_prior_starts"] / (result["starter_prior_starts"] + 5.0)
    result["starter_era"] = (
        starter_weight * result["starter_era"] + (1 - starter_weight) * 4.5
    ).clip(0.5, 10.0)
    result["starter_strikeout_rate"] = (
        starter_weight * result["starter_strikeout_rate"] + (1 - starter_weight) * 0.225
    ).clip(0.05, 0.50)
    result["starter_walk_rate"] = (
        starter_weight * result["starter_walk_rate"] + (1 - starter_weight) * 0.085
    ).clip(0.01, 0.30)
    result["starter_outs_per_start"] = (
        starter_weight * result["starter_outs_per_start"] + (1 - starter_weight) * 15.0
    ).clip(3.0, 27.0)

    bullpen_weight = result["bullpen_prior_outs"] / (result["bullpen_prior_outs"] + 54.0)
    result["bullpen_era_30d"] = (
        bullpen_weight * result["bullpen_era_30d"] + (1 - bullpen_weight) * 4.5
    ).clip(1.0, 10.0)
    result["bullpen_strikeout_rate_30d"] = (
        bullpen_weight * result["bullpen_strikeout_rate_30d"] + (1 - bullpen_weight) * 0.225
    ).clip(0.05, 0.50)
    result["bullpen_walk_rate_30d"] = (
        bullpen_weight * result["bullpen_walk_rate_30d"] + (1 - bullpen_weight) * 0.085
    ).clip(0.01, 0.30)

    for column in (
        "team_prior_games",
        "lineup_prior_pa",
        "starter_prior_starts",
        "bullpen_prior_outs",
        "bullpen_recent_outs",
    ):
        result[column] = np.log1p(result[column])
    return result
