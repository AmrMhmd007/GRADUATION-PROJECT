"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

RULES for revisions after the baseline: make every operation idempotent
(inspect the live schema before adding a table/column/index), because a
database may already contain the change from a legacy migrate_*.py script or
from create_all(). Never delete or rewrite existing data without an explicit,
reviewed data step, and provide a downgrade whenever it is safe to do so.
"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
