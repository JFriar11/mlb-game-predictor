"""add prospective live prediction record contract

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "live_prediction_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("game_pk", sa.Integer(), nullable=False),
        sa.Column("prediction_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scheduled_start_time_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lineup_confirmation_state", sa.String(30), nullable=False),
        sa.Column("home_starter_id", sa.Integer()),
        sa.Column("away_starter_id", sa.Integer()),
        sa.Column("feature_version", sa.String(40), nullable=False),
        sa.Column("model_version", sa.String(40), nullable=False),
        sa.Column("expected_home_runs", sa.Float(), nullable=False),
        sa.Column("expected_away_runs", sa.Float(), nullable=False),
        sa.Column("distribution_name", sa.String(40), nullable=False),
        sa.Column("distribution_parameters_json", sa.Text(), nullable=False),
        sa.Column("raw_home_win_probability", sa.Float(), nullable=False),
        sa.Column("calibrated_home_win_probability", sa.Float(), nullable=False),
        sa.Column("prediction_intervals_json", sa.Text(), nullable=False),
        sa.Column("extra_inning_adjustment", sa.Float(), nullable=False),
        sa.Column("data_quality_warnings_json", sa.Text(), nullable=False),
        sa.Column("observed_home_runs", sa.Integer()),
        sa.Column("observed_away_runs", sa.Integer()),
        sa.Column("observed_home_win", sa.Boolean()),
        sa.Column("observed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "expected_home_runs >= 0 AND expected_away_runs >= 0 "
            "AND raw_home_win_probability BETWEEN 0 AND 1 "
            "AND calibrated_home_win_probability BETWEEN 0 AND 1",
            name="ck_live_prediction_values",
        ),
        sa.UniqueConstraint(
            "game_pk", "prediction_timestamp", "model_version", name="uq_live_prediction"
        ),
    )


def downgrade() -> None:
    op.drop_table("live_prediction_records")
