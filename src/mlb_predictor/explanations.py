"""Prediction-time evidence, independent of mutable discovery and postgame outcomes."""

from datetime import datetime
from typing import Annotated, Any, Literal, Self

import pandas as pd
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, FiniteFloat, model_validator

from mlb_predictor.modeling.dataset import MULTISEASON_FEATURE_COLUMNS
from mlb_predictor.modeling.stabilization import stabilize_small_samples

SNAPSHOT_VERSION = "pregame_inputs_v1"
SNAPSHOT_SOURCE = "live_pregame_feature_builder"
PositiveID = Annotated[int, Field(gt=0, strict=True)]
Lineup = Annotated[list[PositiveID], Field(min_length=9, max_length=9)]


class FeatureEvidence(BaseModel):
    """Exact pre-model inputs and the existing stabilization output, not attribution."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    snapshot_version: Literal["pregame_inputs_v1"] = SNAPSHOT_VERSION
    stabilization_version: Literal["small_sample_stabilization_v1"] = (
        "small_sample_stabilization_v1"
    )
    as_of: AwareDatetime
    game_pk: PositiveID
    artifact_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    home_lineup: Lineup
    away_lineup: Lineup
    home_team_id: PositiveID
    away_team_id: PositiveID
    home_starter_id: PositiveID
    away_starter_id: PositiveID
    raw: dict[Literal["home", "away"], dict[str, FiniteFloat]]
    stabilized: dict[Literal["home", "away"], dict[str, FiniteFloat]]

    @model_validator(mode="after")
    def accepted_inputs(self) -> Self:
        for lineup in (self.home_lineup, self.away_lineup):
            if len(set(lineup)) != 9:
                raise ValueError("lineup IDs must be unique")
        if self.home_team_id == self.away_team_id:
            raise ValueError("teams must be distinct")
        if set(self.home_lineup) & set(self.away_lineup):
            raise ValueError("opposing lineups cannot share players")
        for collection in (self.raw, self.stabilized):
            if set(collection) != {"home", "away"}:
                raise ValueError("both feature sides are required")
            for side, values in collection.items():
                if set(values) != set(MULTISEASON_FEATURE_COLUMNS):
                    raise ValueError("evidence must contain exactly accepted feature columns")
                if values["is_home"] != (side == "home"):
                    raise ValueError("feature side mismatch")
        for values in self.raw.values():
            for name in (
                "lineup_on_base_rate",
                "lineup_strikeout_rate",
                "lineup_home_run_rate",
                "starter_strikeout_rate",
                "starter_walk_rate",
                "bullpen_strikeout_rate_30d",
                "bullpen_walk_rate_30d",
            ):
                if not 0 <= values[name] <= 1:
                    raise ValueError("baseball rates must lie between zero and one")
            for name in (
                "fallback_count",
                "lineup_prior_pa",
                "starter_prior_starts",
                "bullpen_prior_outs",
                "team_prior_games",
                "prior_season_team_games",
            ):
                if values[name] < 0 or not values[name].is_integer():
                    raise ValueError("sample and fallback counts must be nonnegative integers")
        return self


def capture_feature_evidence(
    away: dict[str, Any],
    home: dict[str, Any],
    *,
    as_of: datetime,
    game_pk: int,
    artifact_sha256: str,
    home_lineup: tuple[int, ...],
    away_lineup: tuple[int, ...],
    home_team_id: int,
    away_team_id: int,
    home_starter_id: int,
    away_starter_id: int,
) -> FeatureEvidence:
    """Capture the inputs at generation; never query history again to fill old snapshots."""
    transformed = stabilize_small_samples(
        pd.DataFrame([away, home], columns=MULTISEASON_FEATURE_COLUMNS)
    )
    return FeatureEvidence(
        as_of=as_of,
        game_pk=game_pk,
        artifact_sha256=artifact_sha256,
        home_lineup=list(home_lineup),
        away_lineup=list(away_lineup),
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        home_starter_id=home_starter_id,
        away_starter_id=away_starter_id,
        raw={"away": away, "home": home},
        stabilized={"away": transformed.iloc[0].to_dict(), "home": transformed.iloc[1].to_dict()},
    )
