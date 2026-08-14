"""add Sprint 9 live game state and prediction audit fields

Revision ID: 0011
Revises: 0010
"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "live_game_states",
        sa.Column("game_pk", sa.Integer(), primary_key=True),
        sa.Column("game_date", sa.Date(), nullable=False),
        sa.Column("scheduled_start_time_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("home_team_id", sa.Integer(), nullable=False),
        sa.Column("home_team_name", sa.String(100), nullable=False),
        sa.Column("away_team_id", sa.Integer(), nullable=False),
        sa.Column("away_team_name", sa.String(100), nullable=False),
        sa.Column("venue_id", sa.Integer()),
        sa.Column("venue_name", sa.String(120)),
        sa.Column("home_starter_id", sa.Integer()),
        sa.Column("away_starter_id", sa.Integer()),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("lineup_state", sa.String(30), nullable=False),
        sa.Column("home_lineup_json", sa.Text(), nullable=False),
        sa.Column("away_lineup_json", sa.Text(), nullable=False),
        sa.Column("source_retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
    )
    columns = (
        sa.Column("minutes_before_first_pitch", sa.Float(), nullable=False, server_default="0"),
        sa.Column("timing_classification", sa.String(30), nullable=False, server_default="unknown"),
        sa.Column("prediction_kind", sa.String(20), nullable=False, server_default="diagnostic"),
        sa.Column("is_official", sa.Boolean()),
        sa.Column(
            "source_retrieved_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "feature_cutoff_timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("calibration_version", sa.String(40), nullable=False, server_default="platt_v1"),
        sa.Column(
            "distribution_version", sa.String(40), nullable=False, server_default="nb_global_v1"
        ),
        sa.Column("code_version", sa.String(80), nullable=False, server_default="unknown"),
        sa.Column("run_probabilities_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("most_likely_scores_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("away_win_probability", sa.Float(), nullable=False, server_default="0"),
        sa.Column("regulation_tie_probability", sa.Float(), nullable=False, server_default="0"),
        sa.Column("completion_status", sa.String(40)),
        sa.Column("settlement_timestamp", sa.DateTime(timezone=True)),
    )
    for column in columns:
        op.add_column("live_prediction_records", column)
    op.create_index(
        "uq_live_official_prediction",
        "live_prediction_records",
        ["game_pk", "model_version"],
        unique=True,
        postgresql_where=sa.text("is_official IS TRUE"),
    )


def downgrade() -> None:
    op.drop_index("uq_live_official_prediction", table_name="live_prediction_records")
    for name in (
        "settlement_timestamp",
        "completion_status",
        "regulation_tie_probability",
        "away_win_probability",
        "most_likely_scores_json",
        "run_probabilities_json",
        "code_version",
        "distribution_version",
        "calibration_version",
        "feature_cutoff_timestamp",
        "source_retrieved_at",
        "is_official",
        "prediction_kind",
        "timing_classification",
        "minutes_before_first_pitch",
    ):
        op.drop_column("live_prediction_records", name)
    op.drop_table("live_game_states")
