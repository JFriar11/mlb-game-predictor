"""Create Sprint 0 domain tables.

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "teams",
        sa.Column("team_id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("abbreviation", sa.String(10)),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "players",
        sa.Column("player_id", sa.Integer(), primary_key=True),
        sa.Column("full_name", sa.String(120), nullable=False),
        sa.Column("bat_side", sa.String(2)),
        sa.Column("throws", sa.String(2)),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "venues",
        sa.Column("venue_id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "games",
        sa.Column("game_pk", sa.Integer(), primary_key=True),
        sa.Column("game_date", sa.Date(), nullable=False),
        sa.Column("scheduled_start_time_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actual_start_time_utc", sa.DateTime(timezone=True)),
        sa.Column("season", sa.Integer(), nullable=False),
        sa.Column("game_type", sa.String(2), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("home_team_id", sa.Integer(), sa.ForeignKey("teams.team_id"), nullable=False),
        sa.Column("away_team_id", sa.Integer(), sa.ForeignKey("teams.team_id"), nullable=False),
        sa.Column("venue_id", sa.Integer(), sa.ForeignKey("venues.venue_id"), nullable=False),
        sa.Column("home_team_runs", sa.Integer(), nullable=False),
        sa.Column("away_team_runs", sa.Integer(), nullable=False),
        sa.Column("innings_played", sa.Integer(), nullable=False),
        sa.Column("doubleheader_code", sa.String(2), nullable=False),
        sa.Column("game_number", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("home_team_id <> away_team_id", name="ck_games_two_distinct_teams"),
        sa.CheckConstraint("home_team_runs >= 0", name="ck_games_home_runs_nonnegative"),
        sa.CheckConstraint("away_team_runs >= 0", name="ck_games_away_runs_nonnegative"),
        sa.CheckConstraint("innings_played > 0", name="ck_games_innings_positive"),
    )
    op.create_table(
        "game_starting_pitchers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "game_pk",
            sa.Integer(),
            sa.ForeignKey("games.game_pk", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.team_id"), nullable=False),
        sa.Column("pitcher_id", sa.Integer(), sa.ForeignKey("players.player_id"), nullable=False),
        sa.Column("throws", sa.String(2)),
        sa.Column("is_home", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("game_pk", "team_id", name="uq_starting_pitcher_game_team"),
        sa.UniqueConstraint("game_pk", "is_home", name="uq_starting_pitcher_game_side"),
    )
    op.create_table(
        "game_starting_lineups",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "game_pk",
            sa.Integer(),
            sa.ForeignKey("games.game_pk", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.team_id"), nullable=False),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.player_id"), nullable=False),
        sa.Column("batting_order", sa.Integer(), nullable=False),
        sa.Column("defensive_position", sa.String(5)),
        sa.Column("bat_side", sa.String(2)),
        sa.Column("is_home", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("batting_order BETWEEN 1 AND 9", name="ck_lineup_batting_order_1_9"),
        sa.UniqueConstraint(
            "game_pk", "team_id", "batting_order", name="uq_lineup_game_team_order"
        ),
        sa.UniqueConstraint("game_pk", "team_id", "player_id", name="uq_lineup_game_team_player"),
    )


def downgrade() -> None:
    op.drop_table("game_starting_lineups")
    op.drop_table("game_starting_pitchers")
    op.drop_table("games")
    op.drop_table("venues")
    op.drop_table("players")
    op.drop_table("teams")
