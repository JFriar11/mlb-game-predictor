"""Retain optional prediction-time input evidence independently of forecasts.

Revision ID: 0014
Revises: 0013
"""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prediction_input_snapshots",
        sa.Column(
            "prediction_id",
            sa.Integer(),
            sa.ForeignKey("live_prediction_records.id"),
            primary_key=True,
        ),
        sa.Column("snapshot_version", sa.String(40), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(60), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("prediction_input_snapshots")
