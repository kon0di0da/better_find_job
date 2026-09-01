"""Create the interview schema.

Revision ID: interview_0001
Revises: knowledge_0001
"""

from alembic import op

from migrations.sql_loader import execute_sql_file

revision = "interview_0001"
down_revision = "knowledge_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_sql_file(op.get_bind(), __file__, "0001_initial.up.sql")


def downgrade() -> None:
    execute_sql_file(op.get_bind(), __file__, "0001_initial.down.sql")
