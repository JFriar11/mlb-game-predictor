"""add multi-season feature provenance

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pregame_feature_snapshots",
        sa.Column("history_decay", sa.Float(), server_default="1", nullable=False),
    )
    for column in (
        "prior_season_team_games",
        "prior_season_lineup_pa",
        "prior_season_starter_starts",
        "prior_season_bullpen_outs",
    ):
        op.add_column(
            "pregame_feature_snapshots",
            sa.Column(column, sa.Integer(), server_default="0", nullable=False),
        )
    op.create_check_constraint(
        "ck_features_prior_samples_nonnegative",
        "pregame_feature_snapshots",
        "history_decay > 0 AND history_decay <= 1 "
        "AND prior_season_team_games >= 0 AND prior_season_lineup_pa >= 0 "
        "AND prior_season_starter_starts >= 0 AND prior_season_bullpen_outs >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_features_prior_samples_nonnegative",
        "pregame_feature_snapshots",
        type_="check",
    )
    for column in (
        "prior_season_bullpen_outs",
        "prior_season_starter_starts",
        "prior_season_lineup_pa",
        "prior_season_team_games",
        "history_decay",
    ):
        op.drop_column("pregame_feature_snapshots", column)
