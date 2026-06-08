"""add users.region column

Revision ID: 4f2c8b9d1e3a
Revises: 0d6491da3ab7
Create Date: 2026-06-08 16:05:00.000000

"""
from alembic import op
import sqlalchemy as sa
from typing import Set


# revision identifiers, used by Alembic.
revision = '4f2c8b9d1e3a'
down_revision = '0d6491da3ab7'
branch_labels = None
depends_on = None


def _column_names(inspector, table_name: str) -> Set[str]:
    return {col['name'] for col in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    users_columns = _column_names(inspector, 'users')

    if 'region' not in users_columns:
        op.add_column('users', sa.Column('region', sa.String(length=100), nullable=True, server_default=''))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    users_columns = _column_names(inspector, 'users')

    if 'region' in users_columns:
        op.drop_column('users', 'region')
