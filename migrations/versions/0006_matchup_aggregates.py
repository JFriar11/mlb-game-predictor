"""add handedness and pitch-group game aggregates

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "player_game_handed_batting",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "game_pk",
            sa.Integer(),
            sa.ForeignKey("games.game_pk", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("batter_id", sa.Integer(), sa.ForeignKey("players.player_id"), nullable=False),
        sa.Column("pitcher_hand", sa.String(1), nullable=False),
        sa.Column("plate_appearances", sa.Integer(), nullable=False),
        sa.Column("at_bats", sa.Integer(), nullable=False),
        sa.Column("hits", sa.Integer(), nullable=False),
        sa.Column("walks", sa.Integer(), nullable=False),
        sa.Column("strikeouts", sa.Integer(), nullable=False),
        sa.Column("home_runs", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "game_pk", "batter_id", "pitcher_hand", name="uq_handed_batting_game_player_hand"
        ),
        sa.CheckConstraint(
            "plate_appearances >= 0 AND at_bats >= 0 AND hits >= 0 AND walks >= 0 "
            "AND strikeouts >= 0 AND home_runs >= 0",
            name="ck_handed_batting_nonnegative",
        ),
    )
    op.create_table(
        "player_game_pitch_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "game_pk",
            sa.Integer(),
            sa.ForeignKey("games.game_pk", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.player_id"), nullable=False),
        sa.Column("role", sa.String(8), nullable=False),
        sa.Column("pitch_group", sa.String(12), nullable=False),
        sa.Column("pitches", sa.Integer(), nullable=False),
        sa.Column("swings", sa.Integer(), nullable=False),
        sa.Column("whiffs", sa.Integer(), nullable=False),
        sa.Column("balls_in_play", sa.Integer(), nullable=False),
        sa.Column("hits_on_contact", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "game_pk", "player_id", "role", "pitch_group", name="uq_pitch_group_game_player"
        ),
        sa.CheckConstraint(
            "pitches >= 0 AND swings >= 0 AND whiffs >= 0 AND balls_in_play >= 0 "
            "AND hits_on_contact >= 0",
            name="ck_pitch_group_nonnegative",
        ),
    )


def downgrade() -> None:
    op.drop_table("player_game_pitch_groups")
    op.drop_table("player_game_handed_batting")
