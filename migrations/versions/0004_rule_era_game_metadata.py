"""add rule-era game metadata

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "games", sa.Column("scheduled_innings", sa.Integer(), server_default="9", nullable=False)
    )
    op.add_column(
        "games",
        sa.Column("tiebreaker_code", sa.String(length=2), server_default="N", nullable=False),
    )
    op.add_column("games", sa.Column("day_night", sa.String(length=10), nullable=True))
    op.add_column("games", sa.Column("original_date", sa.Date(), nullable=True))
    op.add_column("games", sa.Column("rescheduled_from_date", sa.Date(), nullable=True))
    op.add_column("games", sa.Column("resume_date", sa.Date(), nullable=True))
    op.add_column(
        "games",
        sa.Column(
            "is_suspended_resumption", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
    )
    op.create_check_constraint(
        "ck_games_scheduled_innings_positive", "games", "scheduled_innings > 0"
    )


def downgrade() -> None:
    op.drop_constraint("ck_games_scheduled_innings_positive", "games", type_="check")
    for column in (
        "is_suspended_resumption",
        "resume_date",
        "rescheduled_from_date",
        "original_date",
        "day_night",
        "tiebreaker_code",
        "scheduled_innings",
    ):
        op.drop_column("games", column)
