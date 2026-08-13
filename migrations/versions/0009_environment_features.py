"""add Sprint 6 environment feature snapshots

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "environment_feature_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "game_pk",
            sa.Integer(),
            sa.ForeignKey("games.game_pk", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("feature_version", sa.String(40), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("max_source_game_date", sa.Date()),
        sa.Column("park_prior_games", sa.Integer(), nullable=False),
        sa.Column("park_factor", sa.Float(), nullable=False),
        sa.Column("temperature_f", sa.Float(), nullable=False),
        sa.Column("wind_speed_mph", sa.Float(), nullable=False),
        sa.Column("wind_out_component", sa.Float(), nullable=False),
        sa.Column("wind_cross_component", sa.Float(), nullable=False),
        sa.Column("elevation_ft", sa.Float(), nullable=False),
        sa.Column("roof_type", sa.String(30), nullable=False),
        sa.Column("roof_closed_proxy", sa.Boolean(), nullable=False),
        sa.Column("day_game", sa.Boolean(), nullable=False),
        sa.Column("artificial_turf", sa.Boolean(), nullable=False),
        sa.Column("weather_observed_proxy", sa.Boolean(), nullable=False),
        sa.Column("fallback_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "park_prior_games >= 0 AND park_factor > 0 AND wind_speed_mph >= 0",
            name="ck_environment_features_valid",
        ),
        sa.UniqueConstraint("game_pk", "feature_version", name="uq_environment_features"),
    )
    op.create_index(
        "ix_environment_features_version_as_of",
        "environment_feature_snapshots",
        ["feature_version", "as_of"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_environment_features_version_as_of", table_name="environment_feature_snapshots"
    )
    op.drop_table("environment_feature_snapshots")
