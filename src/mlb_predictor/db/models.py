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
