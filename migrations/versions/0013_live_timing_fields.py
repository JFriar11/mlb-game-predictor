"""add actual-start timing fields

Revision ID: 0013
Revises: 0012
"""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "live_prediction_records", sa.Column("actual_start_time_utc", sa.DateTime(timezone=True))
    )
    op.add_column("live_prediction_records", sa.Column("minutes_before_actual_start", sa.Float()))
    op.create_table(
        "watcher_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("game_pk", sa.Integer()),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details_json", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("watcher_events")
    op.drop_column("live_prediction_records", "minutes_before_actual_start")
    op.drop_column("live_prediction_records", "actual_start_time_utc")
