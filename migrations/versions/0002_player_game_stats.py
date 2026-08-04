"""Add player-game batting and pitching tables.

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "player_game_batting",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "game_pk",
            sa.Integer(),
            sa.ForeignKey("games.game_pk", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.team_id"), nullable=False),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.player_id"), nullable=False),
        sa.Column("is_home", sa.Boolean(), nullable=False),
        sa.Column("plate_appearances", sa.Integer(), nullable=False),
        sa.Column("at_bats", sa.Integer(), nullable=False),
        sa.Column("runs", sa.Integer(), nullable=False),
        sa.Column("hits", sa.Integer(), nullable=False),
        sa.Column("doubles", sa.Integer(), nullable=False),
        sa.Column("triples", sa.Integer(), nullable=False),
        sa.Column("home_runs", sa.Integer(), nullable=False),
        sa.Column("rbi", sa.Integer(), nullable=False),
        sa.Column("base_on_balls", sa.Integer(), nullable=False),
        sa.Column("strike_outs", sa.Integer(), nullable=False),
        sa.Column("stolen_bases", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "plate_appearances >= 0 AND at_bats >= 0 AND runs >= 0 AND hits >= 0 "
            "AND doubles >= 0 AND triples >= 0 AND home_runs >= 0 AND rbi >= 0 "
            "AND base_on_balls >= 0 AND strike_outs >= 0 AND stolen_bases >= 0",
            name="ck_batting_nonnegative",
        ),
        sa.UniqueConstraint("game_pk", "team_id", "player_id", name="uq_batting_game_team_player"),
    )
    op.create_table(
        "player_game_pitching",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "game_pk",
            sa.Integer(),
            sa.ForeignKey("games.game_pk", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.team_id"), nullable=False),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.player_id"), nullable=False),
        sa.Column("is_home", sa.Boolean(), nullable=False),
        sa.Column("is_starter", sa.Boolean(), nullable=False),
        sa.Column("outs_recorded", sa.Integer(), nullable=False),
        sa.Column("batters_faced", sa.Integer(), nullable=False),
        sa.Column("pitches_thrown", sa.Integer(), nullable=False),
        sa.Column("strikes", sa.Integer(), nullable=False),
        sa.Column("hits_allowed", sa.Integer(), nullable=False),
        sa.Column("runs_allowed", sa.Integer(), nullable=False),
        sa.Column("earned_runs", sa.Integer(), nullable=False),
        sa.Column("base_on_balls", sa.Integer(), nullable=False),
        sa.Column("strike_outs", sa.Integer(), nullable=False),
        sa.Column("home_runs_allowed", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "outs_recorded >= 0 AND batters_faced >= 0 AND pitches_thrown >= 0 "
            "AND strikes >= 0 AND hits_allowed >= 0 AND runs_allowed >= 0 "
            "AND earned_runs >= 0 AND base_on_balls >= 0 AND strike_outs >= 0 "
            "AND home_runs_allowed >= 0",
            name="ck_pitching_nonnegative",
        ),
        sa.UniqueConstraint("game_pk", "team_id", "player_id", name="uq_pitching_game_team_player"),
    )


def downgrade() -> None:
    op.drop_table("player_game_pitching")
    op.drop_table("player_game_batting")
