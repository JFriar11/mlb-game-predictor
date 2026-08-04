"""Add leakage-auditable pregame feature snapshots.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pregame_feature_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "game_pk",
            sa.Integer(),
            sa.ForeignKey("games.game_pk", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("offense_team_id", sa.Integer(), sa.ForeignKey("teams.team_id"), nullable=False),
        sa.Column("opponent_team_id", sa.Integer(), sa.ForeignKey("teams.team_id"), nullable=False),
        sa.Column("starter_id", sa.Integer(), sa.ForeignKey("players.player_id"), nullable=False),
        sa.Column("venue_id", sa.Integer(), sa.ForeignKey("venues.venue_id"), nullable=False),
        sa.Column("is_home", sa.Boolean(), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("feature_version", sa.String(40), nullable=False),
        sa.Column("max_source_game_date", sa.Date()),
        sa.Column("team_prior_games", sa.Integer(), nullable=False),
        sa.Column("team_runs_avg_10", sa.Float(), nullable=False),
        sa.Column("team_runs_allowed_avg_10", sa.Float(), nullable=False),
        sa.Column("team_runs_avg_season", sa.Float(), nullable=False),
        sa.Column("lineup_prior_pa", sa.Integer(), nullable=False),
        sa.Column("lineup_on_base_rate", sa.Float(), nullable=False),
        sa.Column("lineup_strikeout_rate", sa.Float(), nullable=False),
        sa.Column("lineup_home_run_rate", sa.Float(), nullable=False),
        sa.Column("starter_prior_starts", sa.Integer(), nullable=False),
        sa.Column("starter_era", sa.Float(), nullable=False),
        sa.Column("starter_strikeout_rate", sa.Float(), nullable=False),
        sa.Column("starter_walk_rate", sa.Float(), nullable=False),
        sa.Column("starter_outs_per_start", sa.Float(), nullable=False),
        sa.Column("bullpen_prior_outs", sa.Integer(), nullable=False),
        sa.Column("bullpen_era_30d", sa.Float(), nullable=False),
        sa.Column("bullpen_strikeout_rate_30d", sa.Float(), nullable=False),
        sa.Column("bullpen_walk_rate_30d", sa.Float(), nullable=False),
        sa.Column("bullpen_recent_outs", sa.Integer(), nullable=False),
        sa.Column("days_rest", sa.Integer(), nullable=False),
        sa.Column("fallback_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "offense_team_id <> opponent_team_id", name="ck_features_distinct_teams"
        ),
        sa.CheckConstraint(
            "team_prior_games >= 0 AND lineup_prior_pa >= 0 AND starter_prior_starts >= 0 "
            "AND bullpen_prior_outs >= 0 AND bullpen_recent_outs >= 0 AND fallback_count >= 0",
            name="ck_features_nonnegative_samples",
        ),
        sa.UniqueConstraint(
            "game_pk", "offense_team_id", "feature_version", name="uq_features_game_team_version"
        ),
    )
    op.create_index(
        "ix_features_version_as_of", "pregame_feature_snapshots", ["feature_version", "as_of"]
    )


def downgrade() -> None:
    op.drop_index("ix_features_version_as_of", table_name="pregame_feature_snapshots")
    op.drop_table("pregame_feature_snapshots")
