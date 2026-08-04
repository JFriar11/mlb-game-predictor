from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
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
