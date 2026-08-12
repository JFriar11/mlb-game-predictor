"""add Sprint 4 matchup feature columns

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

FLOAT_COLUMNS = (
    "lineup_weighted_on_base_rate",
    "lineup_weighted_strikeout_rate",
    "lineup_weighted_home_run_rate",
    "lineup_projected_plate_appearances",
    "lineup_vs_starter_hand_on_base_rate",
    "lineup_vs_starter_hand_strikeout_rate",
    "lineup_vs_starter_hand_home_run_rate",
    "starter_fastball_rate",
    "starter_breaking_rate",
    "starter_offspeed_rate",
    "starter_other_pitch_rate",
    "lineup_pitch_mix_whiff_rate",
    "lineup_pitch_mix_hit_in_play_rate",
)
INTEGER_COLUMNS = (
    "lineup_vs_starter_hand_pa",
    "starter_pitch_group_prior_pitches",
    "lineup_pitch_group_prior_pitches",
    "matchup_fallback_count",
)


def upgrade() -> None:
    for column in FLOAT_COLUMNS:
        op.add_column("pregame_feature_snapshots", sa.Column(column, sa.Float(), nullable=True))
    for column in INTEGER_COLUMNS:
        op.add_column("pregame_feature_snapshots", sa.Column(column, sa.Integer(), nullable=True))


def downgrade() -> None:
    for column in (*INTEGER_COLUMNS, *FLOAT_COLUMNS):
        op.drop_column("pregame_feature_snapshots", column)
