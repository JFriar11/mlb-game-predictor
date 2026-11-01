"""Ephemeral, offline what-if inference. Never attaches forecast objects to a session."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import AwareDatetime, Field, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from threadpoolctl import threadpool_limits

from mlb_predictor.api.schemas import Contract, Probability, RunDistribution, ScoreBin
from mlb_predictor.db.models import (
    Game,
    GameStartingLineup,
    GameStartingPitcher,
    Player,
    Team,
    Venue,
)
from mlb_predictor.explanations import Lineup, PositiveID, capture_feature_evidence
from mlb_predictor.live import (
    ACCEPTED_ARTIFACT_SHA256,
    MODEL_VERSION,
    predict_from_features,
    verify_accepted_artifact,
)
from mlb_predictor.live_features import build_live_feature_pair
from mlb_predictor.presentation import (
    Confidence,
    CountRange,
    Explanation,
    InputQuality,
    count_range,
    explain_inputs,
)


class SandboxRequest(Contract):
    as_of: AwareDatetime
    home_team_id: PositiveID
    away_team_id: PositiveID
    venue_id: PositiveID
    home_starter_id: PositiveID
    away_starter_id: PositiveID
    home_lineup: Lineup
    away_lineup: Lineup

    @model_validator(mode="after")
    def valid_matchup(self) -> Self:
        self.as_of = self.as_of.astimezone(UTC)
        if not datetime(2026, 1, 1, tzinfo=UTC) <= self.as_of <= datetime.now(UTC):
            raise ValueError("Use a history cutoff from 2026-01-01 through now (UTC).")
        if self.home_team_id == self.away_team_id:
            raise ValueError("Choose two different teams.")
        if any(len(set(ids)) != 9 for ids in (self.home_lineup, self.away_lineup)):
            raise ValueError("Each lineup must have nine different players.")
        if set(self.home_lineup) & set(self.away_lineup):
            raise ValueError("A hitter cannot appear on both teams.")
        if self.home_starter_id == self.away_starter_id:
            raise ValueError("Choose two different starting pitchers.")
        if self.home_starter_id in self.away_lineup or self.away_starter_id in self.home_lineup:
            raise ValueError("A starting pitcher cannot bat for the opposing team.")
        return self


class Choice(Contract):
    id: PositiveID
    name: str


class SandboxCatalog(Contract):
    teams: list[Choice]
    players: list[Choice]
    venues: list[Choice]
    latest_history_date: date | None
    default_as_of: AwareDatetime


class RetainedLineup(Contract):
    game_date: date
    lineup: list[int]
    starter_id: int
    venue_id: int


class SandboxTeam(Contract):
    expected_runs: Annotated[float, Field(ge=0)]
    run_distribution: RunDistribution
    run_ranges: dict[Literal["80", "95"], CountRange]


class SandboxResult(Contract):
    kind: Literal["hypothetical"] = "hypothetical"
    is_official: Literal[False] = False
    saved: Literal[False] = False
    model_version: str = MODEL_VERSION
    artifact_sha256: str = ACCEPTED_ARTIFACT_SHA256
    generated_at: AwareDatetime
    inputs: SandboxRequest
    latest_history_date: date | None
    home: SandboxTeam
    away: SandboxTeam
    calibrated_home_win_probability: Probability
    away_win_probability: Probability
    most_likely_score_bins: list[ScoreBin]
    warnings: list[str]
    explanation: Explanation
    confidence: Confidence


def catalog(session: Session) -> SandboxCatalog:
    """Names are discovery aids, not an assertion of current roster membership."""
    latest = session.scalar(select(func.max(Game.game_date)))
    default = (
        datetime.combine(latest + timedelta(days=1), datetime.min.time(), UTC)
        if latest
        else datetime.now(UTC)
    )
    default = max(datetime(2026, 1, 1, tzinfo=UTC), min(default, datetime.now(UTC)))
    return SandboxCatalog(
        teams=[
            Choice(id=x.team_id, name=x.name)
            for x in session.scalars(select(Team).order_by(Team.name))
        ],
        players=[
            Choice(id=x.player_id, name=x.full_name)
            for x in session.scalars(select(Player).order_by(Player.full_name, Player.player_id))
        ],
        venues=[
            Choice(id=x.venue_id, name=x.name)
            for x in session.scalars(select(Venue).where(Venue.venue_id > 0).order_by(Venue.name))
        ],
        latest_history_date=latest,
        default_as_of=default,
    )


def retained_lineup(session: Session, team_id: int, as_of: datetime) -> RetainedLineup | None:
    """Use only an initial lineup from a prior UTC calendar date."""
    cutoff = as_of.astimezone(UTC)
    games = session.scalars(
        select(Game)
        .where(
            or_(Game.home_team_id == team_id, Game.away_team_id == team_id),
            Game.game_date < cutoff.date(),
            Game.scheduled_start_time_utc < cutoff,
        )
        .order_by(Game.game_date.desc(), Game.game_pk.desc())
        .limit(30)
    )
    for game in games:
        lineup = list(
            session.scalars(
                select(GameStartingLineup.player_id)
                .where(
                    GameStartingLineup.game_pk == game.game_pk,
                    GameStartingLineup.team_id == team_id,
                )
                .order_by(GameStartingLineup.batting_order)
            )
        )
        starter = session.scalar(
            select(GameStartingPitcher.pitcher_id).where(
                GameStartingPitcher.game_pk == game.game_pk,
                GameStartingPitcher.team_id == team_id,
            )
        )
        if len(lineup) == len(set(lineup)) == 9 and starter is not None:
            return RetainedLineup(
                game_date=game.game_date, lineup=lineup, starter_id=starter, venue_id=game.venue_id
            )
    return None


def run_sandbox(session: Session, inputs: SandboxRequest, artifact: Path) -> SandboxResult:
    """Reuse the accepted feature/model path; perform no fitting, network calls or writes."""
    for model, ids in (
        (Team, [inputs.home_team_id, inputs.away_team_id]),
        (Venue, [inputs.venue_id]),
        (
            Player,
            [
                *inputs.home_lineup,
                *inputs.away_lineup,
                inputs.home_starter_id,
                inputs.away_starter_id,
            ],
        ),
    ):
        if any(session.get(model, identifier) is None for identifier in set(ids)):
            raise ValueError("Choose known teams, players and a venue from the local lists.")
    verify_accepted_artifact(artifact)
    values = inputs.model_dump()
    # Virtual ID required by the existing evidence interface; no game/record is created.
    away, home, flags = build_live_feature_pair(session, game_pk=1, **values)
    latest = session.scalar(
        select(func.max(Game.game_date)).where(
            Game.game_date < inputs.as_of.date(),
            Game.scheduled_start_time_utc < inputs.as_of,
        )
    )
    warnings = [
        "Hypothetical user lineup; not confirmed, official, saved or prospectively evaluated.",
        "Local history only; no current rosters, injuries or offseason updates are fetched.",
        "The model aggregates nine hitters; rearranging them does not change the prediction.",
        "Regular-season nine-inning model; custom/postseason matchups are not validated.",
        *flags,
    ]
    if latest is None or (inputs.as_of.date() - latest).days > 2:
        warnings.append(
            "History is missing or stale; rest/bullpen features may be unrepresentative."
        )
    for side, features in (("away", away), ("home", home)):
        if features["fallback_count"]:
            warnings.append(
                f"{side.title()} inputs use {int(features['fallback_count'])} historical fallbacks."
            )
    with threadpool_limits(limits=1):
        result = predict_from_features(away, home, artifact)
    evidence_values = {k: v for k, v in values.items() if k != "venue_id"}
    evidence = capture_feature_evidence(
        away, home, game_pk=1, artifact_sha256=ACCEPTED_ARTIFACT_SHA256, **evidence_values
    )
    probability = result["calibrated_home_win_probability"]
    return SandboxResult(
        generated_at=datetime.now(UTC),
        inputs=inputs,
        latest_history_date=latest,
        home=team_result(result, "home"),
        away=team_result(result, "away"),
        calibrated_home_win_probability=probability,
        away_win_probability=1 - probability,
        most_likely_score_bins=[
            ScoreBin(
                home_run_bucket="12+" if x["home"] == 12 else str(x["home"]),
                away_run_bucket="12+" if x["away"] == 12 else str(x["away"]),
                probability=x["probability"],
            )
            for x in result["most_likely_scores"]
        ],
        warnings=warnings,
        explanation=explain_inputs(evidence),
        confidence=Confidence(
            favorite="home" if probability > 0.5 else "away" if probability < 0.5 else "even",
            favorite_win_probability=max(probability, 1 - probability),
            probability_margin_over_even=abs(probability - 0.5),
            input_quality=InputQuality(
                status="limited",
                fallback_counts={
                    "home": int(home["fallback_count"]),
                    "away": int(away["fallback_count"]),
                },
                recorded_warnings=warnings,
                note="Retrospective calibration does not validate hypothetical matchups.",
            ),
        ),
    )


def team_result(result: dict[str, Any], side: str) -> SandboxTeam:
    """Keep censored display bins separate from uncensored count ranges."""
    mean = result[f"expected_{side}_runs"]
    return SandboxTeam(
        expected_runs=mean,
        run_distribution=RunDistribution(probabilities=result[f"{side}_pmf"]),
        run_ranges={
            str(int(level * 100)): count_range(mean, result["dispersion"], level)
            for level in (0.8, 0.95)
        },
    )
