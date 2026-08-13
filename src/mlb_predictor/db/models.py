from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Team(Base):
    __tablename__ = "teams"
    team_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    abbreviation: Mapped[str | None] = mapped_column(String(10))
    source: Mapped[str] = mapped_column(String(50))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Player(Base):
    __tablename__ = "players"
    player_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120))
    bat_side: Mapped[str | None] = mapped_column(String(2))
    throws: Mapped[str | None] = mapped_column(String(2))
    source: Mapped[str] = mapped_column(String(50))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Venue(Base):
    __tablename__ = "venues"
    venue_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    source: Mapped[str] = mapped_column(String(50))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Game(Base):
    __tablename__ = "games"
    __table_args__ = (
        CheckConstraint("home_team_id <> away_team_id", name="ck_games_two_distinct_teams"),
        CheckConstraint("home_team_runs >= 0", name="ck_games_home_runs_nonnegative"),
        CheckConstraint("away_team_runs >= 0", name="ck_games_away_runs_nonnegative"),
        CheckConstraint("innings_played > 0", name="ck_games_innings_positive"),
    )
    game_pk: Mapped[int] = mapped_column(Integer, primary_key=True)
    game_date: Mapped[date] = mapped_column(Date)
    scheduled_start_time_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actual_start_time_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    season: Mapped[int] = mapped_column(Integer)
    game_type: Mapped[str] = mapped_column(String(2))
    status: Mapped[str] = mapped_column(String(40))
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.team_id"))
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.team_id"))
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.venue_id"))
    home_team_runs: Mapped[int] = mapped_column(Integer)
    away_team_runs: Mapped[int] = mapped_column(Integer)
    innings_played: Mapped[int] = mapped_column(Integer)
    doubleheader_code: Mapped[str] = mapped_column(String(2), default="N")
    game_number: Mapped[int] = mapped_column(Integer, default=1)
    scheduled_innings: Mapped[int] = mapped_column(Integer, default=9)
    tiebreaker_code: Mapped[str] = mapped_column(String(2), default="N")
    day_night: Mapped[str | None] = mapped_column(String(10))
    original_date: Mapped[date | None] = mapped_column(Date)
    rescheduled_from_date: Mapped[date | None] = mapped_column(Date)
    resume_date: Mapped[date | None] = mapped_column(Date)
    is_suspended_resumption: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(50))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class GameStartingPitcher(Base):
    __tablename__ = "game_starting_pitchers"
    __table_args__ = (
        UniqueConstraint("game_pk", "team_id", name="uq_starting_pitcher_game_team"),
        UniqueConstraint("game_pk", "is_home", name="uq_starting_pitcher_game_side"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_pk: Mapped[int] = mapped_column(ForeignKey("games.game_pk", ondelete="CASCADE"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.team_id"))
    pitcher_id: Mapped[int] = mapped_column(ForeignKey("players.player_id"))
    throws: Mapped[str | None] = mapped_column(String(2))
    is_home: Mapped[bool] = mapped_column(Boolean)
    source: Mapped[str] = mapped_column(String(50))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class GameStartingLineup(Base):
    __tablename__ = "game_starting_lineups"
    __table_args__ = (
        CheckConstraint("batting_order BETWEEN 1 AND 9", name="ck_lineup_batting_order_1_9"),
        UniqueConstraint("game_pk", "team_id", "batting_order", name="uq_lineup_game_team_order"),
        UniqueConstraint("game_pk", "team_id", "player_id", name="uq_lineup_game_team_player"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_pk: Mapped[int] = mapped_column(ForeignKey("games.game_pk", ondelete="CASCADE"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.team_id"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.player_id"))
    batting_order: Mapped[int] = mapped_column(Integer)
    defensive_position: Mapped[str | None] = mapped_column(String(5))
    bat_side: Mapped[str | None] = mapped_column(String(2))
    is_home: Mapped[bool] = mapped_column(Boolean)
    source: Mapped[str] = mapped_column(String(50))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PlayerGameBatting(Base):
    __tablename__ = "player_game_batting"
    __table_args__ = (
        UniqueConstraint("game_pk", "team_id", "player_id", name="uq_batting_game_team_player"),
        CheckConstraint(
            "plate_appearances >= 0 AND at_bats >= 0 AND runs >= 0 AND hits >= 0 "
            "AND doubles >= 0 AND triples >= 0 AND home_runs >= 0 AND rbi >= 0 "
            "AND base_on_balls >= 0 AND strike_outs >= 0 AND stolen_bases >= 0",
            name="ck_batting_nonnegative",
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_pk: Mapped[int] = mapped_column(ForeignKey("games.game_pk", ondelete="CASCADE"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.team_id"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.player_id"))
    is_home: Mapped[bool] = mapped_column(Boolean)
    plate_appearances: Mapped[int] = mapped_column(Integer)
    at_bats: Mapped[int] = mapped_column(Integer)
    runs: Mapped[int] = mapped_column(Integer)
    hits: Mapped[int] = mapped_column(Integer)
    doubles: Mapped[int] = mapped_column(Integer)
    triples: Mapped[int] = mapped_column(Integer)
    home_runs: Mapped[int] = mapped_column(Integer)
    rbi: Mapped[int] = mapped_column(Integer)
    base_on_balls: Mapped[int] = mapped_column(Integer)
    strike_outs: Mapped[int] = mapped_column(Integer)
    stolen_bases: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(50))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PlayerGamePitching(Base):
    __tablename__ = "player_game_pitching"
    __table_args__ = (
        UniqueConstraint("game_pk", "team_id", "player_id", name="uq_pitching_game_team_player"),
        CheckConstraint(
            "outs_recorded >= 0 AND batters_faced >= 0 AND pitches_thrown >= 0 "
            "AND strikes >= 0 AND hits_allowed >= 0 AND runs_allowed >= 0 "
            "AND earned_runs >= 0 AND base_on_balls >= 0 AND strike_outs >= 0 "
            "AND home_runs_allowed >= 0",
            name="ck_pitching_nonnegative",
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_pk: Mapped[int] = mapped_column(ForeignKey("games.game_pk", ondelete="CASCADE"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.team_id"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.player_id"))
    is_home: Mapped[bool] = mapped_column(Boolean)
    is_starter: Mapped[bool] = mapped_column(Boolean)
    outs_recorded: Mapped[int] = mapped_column(Integer)
    batters_faced: Mapped[int] = mapped_column(Integer)
    pitches_thrown: Mapped[int] = mapped_column(Integer)
    strikes: Mapped[int] = mapped_column(Integer)
    hits_allowed: Mapped[int] = mapped_column(Integer)
    runs_allowed: Mapped[int] = mapped_column(Integer)
    earned_runs: Mapped[int] = mapped_column(Integer)
    base_on_balls: Mapped[int] = mapped_column(Integer)
    strike_outs: Mapped[int] = mapped_column(Integer)
    home_runs_allowed: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(50))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PregameFeatureSnapshot(Base):
    __tablename__ = "pregame_feature_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "game_pk", "offense_team_id", "feature_version", name="uq_features_game_team_version"
        ),
        CheckConstraint("offense_team_id <> opponent_team_id", name="ck_features_distinct_teams"),
        CheckConstraint(
            "team_prior_games >= 0 AND lineup_prior_pa >= 0 AND starter_prior_starts >= 0 "
            "AND bullpen_prior_outs >= 0 AND bullpen_recent_outs >= 0 "
            "AND fallback_count >= 0",
            name="ck_features_nonnegative_samples",
        ),
        Index("ix_features_version_as_of", "feature_version", "as_of"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_pk: Mapped[int] = mapped_column(ForeignKey("games.game_pk", ondelete="CASCADE"))
    offense_team_id: Mapped[int] = mapped_column(ForeignKey("teams.team_id"))
    opponent_team_id: Mapped[int] = mapped_column(ForeignKey("teams.team_id"))
    starter_id: Mapped[int] = mapped_column(ForeignKey("players.player_id"))
    venue_id: Mapped[int] = mapped_column(ForeignKey("venues.venue_id"))
    is_home: Mapped[bool] = mapped_column(Boolean)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    feature_version: Mapped[str] = mapped_column(String(40))
    max_source_game_date: Mapped[date | None] = mapped_column(Date)
    team_prior_games: Mapped[int] = mapped_column(Integer)
    team_runs_avg_10: Mapped[float] = mapped_column(Float)
    team_runs_allowed_avg_10: Mapped[float] = mapped_column(Float)
    team_runs_avg_season: Mapped[float] = mapped_column(Float)
    lineup_prior_pa: Mapped[int] = mapped_column(Integer)
    lineup_on_base_rate: Mapped[float] = mapped_column(Float)
    lineup_strikeout_rate: Mapped[float] = mapped_column(Float)
    lineup_home_run_rate: Mapped[float] = mapped_column(Float)
    starter_prior_starts: Mapped[int] = mapped_column(Integer)
    starter_era: Mapped[float] = mapped_column(Float)
    starter_strikeout_rate: Mapped[float] = mapped_column(Float)
    starter_walk_rate: Mapped[float] = mapped_column(Float)
    starter_outs_per_start: Mapped[float] = mapped_column(Float)
    bullpen_prior_outs: Mapped[int] = mapped_column(Integer)
    bullpen_era_30d: Mapped[float] = mapped_column(Float)
    bullpen_strikeout_rate_30d: Mapped[float] = mapped_column(Float)
    bullpen_walk_rate_30d: Mapped[float] = mapped_column(Float)
    bullpen_recent_outs: Mapped[int] = mapped_column(Integer)
    days_rest: Mapped[int] = mapped_column(Integer)
    fallback_count: Mapped[int] = mapped_column(Integer)
    history_decay: Mapped[float] = mapped_column(Float, default=1.0)
    prior_season_team_games: Mapped[int] = mapped_column(Integer, default=0)
    prior_season_lineup_pa: Mapped[int] = mapped_column(Integer, default=0)
    prior_season_starter_starts: Mapped[int] = mapped_column(Integer, default=0)
    prior_season_bullpen_outs: Mapped[int] = mapped_column(Integer, default=0)
    lineup_weighted_on_base_rate: Mapped[float | None] = mapped_column(Float)
    lineup_weighted_strikeout_rate: Mapped[float | None] = mapped_column(Float)
    lineup_weighted_home_run_rate: Mapped[float | None] = mapped_column(Float)
    lineup_projected_plate_appearances: Mapped[float | None] = mapped_column(Float)
    lineup_vs_starter_hand_pa: Mapped[int | None] = mapped_column(Integer)
    lineup_vs_starter_hand_on_base_rate: Mapped[float | None] = mapped_column(Float)
    lineup_vs_starter_hand_strikeout_rate: Mapped[float | None] = mapped_column(Float)
    lineup_vs_starter_hand_home_run_rate: Mapped[float | None] = mapped_column(Float)
    starter_pitch_group_prior_pitches: Mapped[int | None] = mapped_column(Integer)
    starter_fastball_rate: Mapped[float | None] = mapped_column(Float)
    starter_breaking_rate: Mapped[float | None] = mapped_column(Float)
    starter_offspeed_rate: Mapped[float | None] = mapped_column(Float)
    starter_other_pitch_rate: Mapped[float | None] = mapped_column(Float)
    lineup_pitch_group_prior_pitches: Mapped[int | None] = mapped_column(Integer)
    lineup_pitch_mix_whiff_rate: Mapped[float | None] = mapped_column(Float)
    lineup_pitch_mix_hit_in_play_rate: Mapped[float | None] = mapped_column(Float)
    matchup_fallback_count: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PlayerGameHandedBatting(Base):
    __tablename__ = "player_game_handed_batting"
    __table_args__ = (
        UniqueConstraint(
            "game_pk", "batter_id", "pitcher_hand", name="uq_handed_batting_game_player_hand"
        ),
        CheckConstraint(
            "plate_appearances >= 0 AND at_bats >= 0 AND hits >= 0 AND walks >= 0 "
            "AND strikeouts >= 0 AND home_runs >= 0",
            name="ck_handed_batting_nonnegative",
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_pk: Mapped[int] = mapped_column(ForeignKey("games.game_pk", ondelete="CASCADE"))
    batter_id: Mapped[int] = mapped_column(ForeignKey("players.player_id"))
    pitcher_hand: Mapped[str] = mapped_column(String(1))
    plate_appearances: Mapped[int] = mapped_column(Integer)
    at_bats: Mapped[int] = mapped_column(Integer)
    hits: Mapped[int] = mapped_column(Integer)
    walks: Mapped[int] = mapped_column(Integer)
    strikeouts: Mapped[int] = mapped_column(Integer)
    home_runs: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(50))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PlayerGamePitchGroup(Base):
    __tablename__ = "player_game_pitch_groups"
    __table_args__ = (
        UniqueConstraint(
            "game_pk", "player_id", "role", "pitch_group", name="uq_pitch_group_game_player"
        ),
        CheckConstraint(
            "pitches >= 0 AND swings >= 0 AND whiffs >= 0 AND balls_in_play >= 0 "
            "AND hits_on_contact >= 0",
            name="ck_pitch_group_nonnegative",
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_pk: Mapped[int] = mapped_column(ForeignKey("games.game_pk", ondelete="CASCADE"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.player_id"))
    role: Mapped[str] = mapped_column(String(8))
    pitch_group: Mapped[str] = mapped_column(String(12))
    pitches: Mapped[int] = mapped_column(Integer)
    swings: Mapped[int] = mapped_column(Integer)
    whiffs: Mapped[int] = mapped_column(Integer)
    balls_in_play: Mapped[int] = mapped_column(Integer)
    hits_on_contact: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(50))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PitchingFeatureSnapshot(Base):
    __tablename__ = "pitching_feature_snapshots"
    __table_args__ = (
        UniqueConstraint("game_pk", "team_id", "feature_version", name="uq_pitching_features"),
        CheckConstraint(
            "starter_prior_starts >= 0 AND starter_days_rest >= 0 "
            "AND team_prior_games >= 0 AND bullpen_prior_appearances >= 0 "
            "AND bullpen_workload_1d >= 0 AND bullpen_workload_3d >= 0 "
            "AND available_reliever_count >= 0 AND unavailable_reliever_count >= 0",
            name="ck_pitching_features_nonnegative",
        ),
        Index("ix_pitching_features_version_as_of", "feature_version", "as_of"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_pk: Mapped[int] = mapped_column(ForeignKey("games.game_pk", ondelete="CASCADE"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.team_id"))
    starter_id: Mapped[int] = mapped_column(ForeignKey("players.player_id"))
    feature_version: Mapped[str] = mapped_column(String(40))
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    max_source_game_date: Mapped[date | None] = mapped_column(Date)
    starter_prior_starts: Mapped[int] = mapped_column(Integer)
    starter_avg_outs: Mapped[float] = mapped_column(Float)
    starter_avg_pitches: Mapped[float] = mapped_column(Float)
    starter_pitches_per_out: Mapped[float] = mapped_column(Float)
    starter_days_rest: Mapped[int] = mapped_column(Integer)
    team_prior_games: Mapped[int] = mapped_column(Integer)
    manager_avg_starter_outs: Mapped[float] = mapped_column(Float)
    manager_avg_starter_pitches: Mapped[float] = mapped_column(Float)
    bullpen_prior_appearances: Mapped[int] = mapped_column(Integer)
    bullpen_workload_1d: Mapped[int] = mapped_column(Integer)
    bullpen_workload_3d: Mapped[int] = mapped_column(Integer)
    available_reliever_count: Mapped[int] = mapped_column(Integer)
    unavailable_reliever_count: Mapped[int] = mapped_column(Integer)
    available_bullpen_era: Mapped[float] = mapped_column(Float)
    available_bullpen_strikeout_rate: Mapped[float] = mapped_column(Float)
    available_bullpen_walk_rate: Mapped[float] = mapped_column(Float)
    high_usage_available: Mapped[int] = mapped_column(Integer)
    fallback_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EnvironmentFeatureSnapshot(Base):
    __tablename__ = "environment_feature_snapshots"
    __table_args__ = (
        UniqueConstraint("game_pk", "feature_version", name="uq_environment_features"),
        CheckConstraint(
            "park_prior_games >= 0 AND park_factor > 0 AND wind_speed_mph >= 0",
            name="ck_environment_features_valid",
        ),
        Index("ix_environment_features_version_as_of", "feature_version", "as_of"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_pk: Mapped[int] = mapped_column(ForeignKey("games.game_pk", ondelete="CASCADE"))
    feature_version: Mapped[str] = mapped_column(String(40))
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    max_source_game_date: Mapped[date | None] = mapped_column(Date)
    park_prior_games: Mapped[int] = mapped_column(Integer)
    park_factor: Mapped[float] = mapped_column(Float)
    temperature_f: Mapped[float] = mapped_column(Float)
    wind_speed_mph: Mapped[float] = mapped_column(Float)
    wind_out_component: Mapped[float] = mapped_column(Float)
    wind_cross_component: Mapped[float] = mapped_column(Float)
    elevation_ft: Mapped[float] = mapped_column(Float)
    roof_type: Mapped[str] = mapped_column(String(30))
    roof_closed_proxy: Mapped[bool] = mapped_column(Boolean)
    day_game: Mapped[bool] = mapped_column(Boolean)
    artificial_turf: Mapped[bool] = mapped_column(Boolean)
    weather_observed_proxy: Mapped[bool] = mapped_column(Boolean)
    fallback_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
