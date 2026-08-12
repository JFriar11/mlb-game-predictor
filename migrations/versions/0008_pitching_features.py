"""add Sprint 5 pitching feature snapshots

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pitching_feature_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "game_pk",
            sa.Integer(),
            sa.ForeignKey("games.game_pk", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.team_id"), nullable=False),
        sa.Column("starter_id", sa.Integer(), sa.ForeignKey("players.player_id"), nullable=False),
        sa.Column("feature_version", sa.String(40), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("max_source_game_date", sa.Date()),
        sa.Column("starter_prior_starts", sa.Integer(), nullable=False),
        sa.Column("starter_avg_outs", sa.Float(), nullable=False),
        sa.Column("starter_avg_pitches", sa.Float(), nullable=False),
        sa.Column("starter_pitches_per_out", sa.Float(), nullable=False),
        sa.Column("starter_days_rest", sa.Integer(), nullable=False),
        sa.Column("team_prior_games", sa.Integer(), nullable=False),
        sa.Column("manager_avg_starter_outs", sa.Float(), nullable=False),
        sa.Column("manager_avg_starter_pitches", sa.Float(), nullable=False),
        sa.Column("bullpen_prior_appearances", sa.Integer(), nullable=False),
        sa.Column("bullpen_workload_1d", sa.Integer(), nullable=False),
        sa.Column("bullpen_workload_3d", sa.Integer(), nullable=False),
        sa.Column("available_reliever_count", sa.Integer(), nullable=False),
        sa.Column("unavailable_reliever_count", sa.Integer(), nullable=False),
        sa.Column("available_bullpen_era", sa.Float(), nullable=False),
        sa.Column("available_bullpen_strikeout_rate", sa.Float(), nullable=False),
        sa.Column("available_bullpen_walk_rate", sa.Float(), nullable=False),
        sa.Column("high_usage_available", sa.Integer(), nullable=False),
        sa.Column("fallback_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "starter_prior_starts >= 0 AND starter_days_rest >= 0 AND team_prior_games >= 0 "
            "AND bullpen_prior_appearances >= 0 AND bullpen_workload_1d >= 0 "
            "AND bullpen_workload_3d >= 0 AND available_reliever_count >= 0 "
            "AND unavailable_reliever_count >= 0",
            name="ck_pitching_features_nonnegative",
        ),
        sa.UniqueConstraint("game_pk", "team_id", "feature_version", name="uq_pitching_features"),
    )
    op.create_index(
        "ix_pitching_features_version_as_of",
        "pitching_feature_snapshots",
        ["feature_version", "as_of"],
    )


def downgrade() -> None:
    op.drop_index("ix_pitching_features_version_as_of", table_name="pitching_feature_snapshots")
    op.drop_table("pitching_feature_snapshots")
